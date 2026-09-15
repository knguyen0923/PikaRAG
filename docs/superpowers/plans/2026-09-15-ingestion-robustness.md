# Ingestion Robustness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Catch a stuck/failing refresh job or a corrupted/truncated source file automatically, before bad data reaches the live bot — via schema validation that gates a live-file swap, and a freshness check that warns when a job hasn't run recently.

**Architecture:** Two new, independent, stdlib-only modules: `pipeline/validate.py` (plain-assertion schema checks — record shape, item shape, usage referential integrity, and an independent hard-coded legal-Pokemon-count sanity check — each returning a list of problem strings, empty means valid) and `pipeline/freshness.py` (writes a last-successful-refresh timestamp per job, and checks each job's own timestamp against its own cadence-derived threshold). `pipeline/refresh_job.py` and `pipeline/refresh_pikalytics_job.py` each gain a validate-before-swap step: build the new output in memory, validate it, and only write it live (via a temp file + atomic `os.replace`, protecting against a crash mid-write) if there are no hard failures — otherwise the previous live file is left untouched and the problems are logged. On a successful swap, each job records its own success timestamp; each job's `__main__` also prints a freshness warning for either job if its own timestamp is stale, satisfying the spec's "run as part of the same job" option without a new deployment artifact.

**Tech Stack:** Python 3.9, stdlib `json`/`time`/`os`/`pathlib` only — no new dependencies (matches this project's established preference; see [[local-llm-migration]], [[observability]]).

**Spec:** `docs/superpowers/specs/2026-09-13-ingestion-robustness-design.md`

## Global Constraints

- No new dependencies (no Pydantic/jsonschema) — plain Python assertions/checks only.
- Every validation function returns a list of problem strings; an empty list means valid. Never raises for a validation failure — the caller decides what to do with the list.
- The independent legal-count table (`EXPECTED_REGULATION_COUNTS`) is hard-coded and must NOT be derived from any source file's own declared `count` field — that's the exact circularity this check exists to break. Only a regulation whose live count has actually been confirmed (the same way this plan confirms M-C's 345, from `STATUS.md`'s deployment history) gets an entry; an unrecognized regulation returns no problems (nothing to compare against), not a failure. This deliberately keeps existing/synthetic test regulations (e.g. `"M-B"` in `tests/test_refresh_job.py`'s fixtures) out of the table's reach without needing to touch those fixtures.
- A refresh job's live output file is only ever replaced via a temp-file write followed by `os.replace()` — never written to directly — so a crash mid-write can't leave a partially-written live file, and a hard validation failure leaves the previous live file completely untouched (not even a stray temp file, since validation runs on the in-memory data before anything is written to disk).
- Freshness/staleness is a logged warning only — it never blocks a swap and never calls `sys.exit`. It's evaluated independently of any single refresh's outcome.
- A freshness check finding no timestamp file at all is "unknown," not "stale" — must not warn on a fresh setup that has never completed a refresh yet.
- The two refresh jobs' cadences differ (PokeAPI: weekly, Pikalytics: monthly — `deploy/systemd/pikarag-refresh-pokeapi.timer` / `pikarag-refresh-pikalytics.timer`), so each has its own timestamp file and its own threshold (14 days / 60 days respectively, loosely double each job's own cadence) — never share one threshold across both jobs.
- `pipeline/refresh_pikalytics_job.py`'s existing `stale_format_code` guard (in `__main__`, checking for zero species with usage data despite nothing outright failing) is additive to this plan's new checks, not replaced by them.
- `tests/test_refresh_job.py::test_run_refresh_reports_shortfall_when_a_fetch_fails` must be reworked (per the spec's explicit "Existing test needs rework" section) to assert the live file is left unchanged on a shortfall, not written with partial data as it does today.

---

## File structure

- Create `pipeline/validate.py` — `validate_records`, `validate_items`, `validate_usage`, `validate_write_count`, `validate_legal_count` (plus `REQUIRED_STATS`, `EXPECTED_REGULATION_COUNTS`, `COUNT_TOLERANCE`). Pure functions, no I/O.
- Create `tests/test_pipeline_validate.py` — full coverage of every validator, good and broken fixtures.
- Create `pipeline/freshness.py` — `record_successful_refresh` (write), `check_freshness` (read one, generic), `check_all_freshness` (checks both jobs' own files against their own thresholds), plus the path/threshold constants.
- Create `tests/test_pipeline_freshness.py` — mocked-`now` coverage of fresh/stale/missing-file cases for both jobs' thresholds.
- Modify `pipeline/refresh_job.py` — validate-before-swap using `pipeline/validate.py`, timestamp recording via `pipeline/freshness.py`, freshness warnings printed in `__main__`.
- Modify `tests/test_refresh_job.py` — rework the shortfall test per the spec, add coverage for a clean run still swapping and recording a timestamp.
- Modify `pipeline/refresh_pikalytics_job.py` — same validate-before-swap/timestamp/freshness-warning pattern, using `validate_usage`.
- Modify `tests/test_refresh_pikalytics_job.py` — add coverage for the new referential-validation gate and timestamp recording; confirm existing tests still pass unchanged.

---

### Task 1: `pipeline/validate.py` — schema and count validators

**Files:**
- Create: `pipeline/validate.py`
- Test: `tests/test_pipeline_validate.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `validate_records(records: list) -> list[str]`, `validate_items(items: list) -> list[str]`, `validate_usage(usage: dict, known_species: set) -> list[str]`, `validate_write_count(written: int, expected: int) -> list[str]`, `validate_legal_count(regulation: str, declared_count: int) -> list[str]`. Task 3 calls `validate_records`, `validate_write_count`, `validate_legal_count`. Task 4 calls `validate_usage`. Every function returns an empty list when there's nothing wrong.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_pipeline_validate.py`:

```python
from pipeline.validate import (
    COUNT_TOLERANCE,
    EXPECTED_REGULATION_COUNTS,
    validate_items,
    validate_legal_count,
    validate_records,
    validate_usage,
    validate_write_count,
)


def _good_record(name="Abomasnow"):
    return {
        "name": name,
        "types": ["Grass", "Ice"],
        "base_stats": {
            "hp": 90, "attack": 92, "defense": 75,
            "sp_attack": 92, "sp_defense": 85, "speed": 60,
        },
        "abilities": ["Snow Warning"],
        "learnset": ["Blizzard"],
        "legal_in": ["M-C"],
    }


def test_validate_records_returns_no_problems_for_good_data():
    assert validate_records([_good_record()]) == []


def test_validate_records_flags_a_record_missing_a_name():
    record = _good_record()
    del record["name"]

    problems = validate_records([record])

    assert len(problems) == 1
    assert "missing name" in problems[0]


def test_validate_records_flags_an_empty_learnset():
    record = _good_record()
    record["learnset"] = []

    problems = validate_records([record])

    assert len(problems) == 1
    assert "empty learnset" in problems[0]
    assert "Abomasnow" in problems[0]


def test_validate_records_flags_missing_base_stat_fields():
    record = _good_record()
    del record["base_stats"]["speed"]

    problems = validate_records([record])

    assert len(problems) == 1
    assert "missing base stat fields" in problems[0]
    assert "Abomasnow" in problems[0]


def test_validate_records_reports_a_problem_per_broken_record():
    bad_1 = _good_record(name="Gyarados")
    bad_1["learnset"] = []
    bad_2 = _good_record(name="Garchomp")
    del bad_2["base_stats"]["hp"]

    problems = validate_records([bad_1, bad_2])

    assert len(problems) == 2


def test_validate_items_returns_no_problems_for_good_data():
    items = [{"name": "Life Orb", "description": "Boosts move power."}]

    assert validate_items(items) == []


def test_validate_items_flags_missing_name():
    items = [{"description": "Boosts move power."}]

    problems = validate_items(items)

    assert len(problems) == 1
    assert "missing name" in problems[0]


def test_validate_items_flags_missing_description():
    items = [{"name": "Life Orb"}]

    problems = validate_items(items)

    assert len(problems) == 1
    assert "Life Orb" in problems[0]
    assert "no description" in problems[0]


def test_validate_usage_returns_no_problems_when_all_species_are_known():
    usage = {"Abomasnow": {"moves": [], "items": [], "abilities": []}}
    known_species = {"Abomasnow", "Garchomp"}

    assert validate_usage(usage, known_species) == []


def test_validate_usage_flags_an_unknown_species():
    usage = {"Bogusmon": {"moves": [], "items": [], "abilities": []}}
    known_species = {"Abomasnow", "Garchomp"}

    problems = validate_usage(usage, known_species)

    assert len(problems) == 1
    assert "Bogusmon" in problems[0]


def test_validate_usage_returns_no_problems_for_an_empty_usage_dict():
    assert validate_usage({}, {"Abomasnow"}) == []


def test_validate_legal_count_returns_no_problems_when_count_matches_the_table():
    expected = EXPECTED_REGULATION_COUNTS["M-C"]

    assert validate_legal_count("M-C", expected) == []


def test_validate_legal_count_flags_a_count_far_below_the_expected_table_value():
    problems = validate_legal_count("M-C", 10)

    assert len(problems) == 1
    assert "M-C" in problems[0]
    assert "10" in problems[0]


def test_validate_legal_count_allows_small_variation_within_tolerance():
    expected = EXPECTED_REGULATION_COUNTS["M-C"]
    slightly_off = int(expected * (1 + COUNT_TOLERANCE / 2))

    assert validate_legal_count("M-C", slightly_off) == []


def test_validate_legal_count_skips_an_unrecognized_regulation():
    # Regulations not in the table (old/retired ones like M-B, and
    # synthetic test regulations) have nothing to compare against --
    # "unknown," not a failure.
    assert validate_legal_count("M-B", 1) == []
    assert validate_legal_count("Totally-Made-Up-Reg", 999999) == []


def test_validate_write_count_returns_no_problems_when_counts_match():
    assert validate_write_count(345, 345) == []


def test_validate_write_count_flags_any_shortfall():
    problems = validate_write_count(343, 345)

    assert len(problems) == 1
    assert "343" in problems[0]
    assert "345" in problems[0]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_pipeline_validate.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pipeline.validate'`.

- [ ] **Step 3: Implement `pipeline/validate.py`**

```python
REQUIRED_STATS = {"hp", "attack", "defense", "sp_attack", "sp_defense", "speed"}

# Independent of any source file's own declared count -- exists specifically
# to catch a corrupted/truncated legal-Pokemon source file whose own "count"
# field is also wrong (the existing written-vs-declared check in
# validate_write_count can't catch this, since it only compares a source
# file against itself). Confirmed from this project's own deployment
# history (STATUS.md: "315 -> 345 legal Pokemon" for the M-B -> M-C
# transition), not derived from any pipeline output. Add a regulation only
# once its live count is confirmed the same way M-C's was -- an
# unrecognized regulation (including old ones like M-B, now retired, and
# any synthetic test regulation) returns no problems: nothing to compare
# against, not a failure.
EXPECTED_REGULATION_COUNTS = {
    "M-C": 345,
}
COUNT_TOLERANCE = 0.05


def validate_records(records: list) -> list:
    """Returns a list of problems found; empty means valid."""
    problems = []
    for r in records:
        if not r.get("name"):
            problems.append(f"record missing name: {r}")
        if not r.get("learnset"):
            problems.append(f"{r.get('name', '?')} has an empty learnset")
        if not r.get("base_stats", {}).keys() >= REQUIRED_STATS:
            problems.append(f"{r.get('name', '?')} missing base stat fields")
    return problems


def validate_items(items: list) -> list:
    """Returns a list of problems found; empty means valid."""
    problems = []
    for item in items:
        if not item.get("name"):
            problems.append(f"item missing name: {item}")
        if not item.get("description"):
            problems.append(f"{item.get('name', '?')} has no description")
    return problems


def validate_usage(usage: dict, known_species: set) -> list:
    """Referential check only: every usage entry must reference a known
    species. Does NOT check for completeness -- a species legitimately
    having no usage data is not a problem this function detects (see the
    ingestion-robustness spec's Purpose section for why)."""
    problems = []
    for species in usage:
        if species not in known_species:
            problems.append(f"usage data references unknown species: {species}")
    return problems


def validate_legal_count(regulation: str, declared_count: int) -> list:
    """Sanity-checks a source file's own declared legal-Pokemon count
    against an independent, hard-coded expected size for that regulation.
    Catches a corrupted/truncated source file whose own count field is
    also wrong -- validate_write_count can't, since it only compares the
    source file against itself."""
    expected = EXPECTED_REGULATION_COUNTS.get(regulation)
    if expected is None:
        return []
    lower = expected * (1 - COUNT_TOLERANCE)
    upper = expected * (1 + COUNT_TOLERANCE)
    if not (lower <= declared_count <= upper):
        return [
            f"{regulation}'s legal Pokemon count is {declared_count}, expected "
            f"around {expected} (+/-{int(COUNT_TOLERANCE * 100)}%) -- source file "
            f"may be truncated or corrupted"
        ]
    return []


def validate_write_count(written: int, expected: int) -> list:
    """Compares how many records were actually written against the source
    file's own declared count. Any shortfall -- whether from a fetch
    failure or a corrupted source file -- is a hard failure under this
    project's validate-before-swap design: partial/incomplete data must
    not go live silently."""
    if written != expected:
        return [
            f"wrote {written} records but the source file declares {expected} "
            f"legal Pokemon ({expected - written} missing)"
        ]
    return []
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_pipeline_validate.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add pipeline/validate.py tests/test_pipeline_validate.py
git commit -m "feat: add pipeline schema and count validators"
```

---

### Task 2: `pipeline/freshness.py` — refresh timestamp tracking

**Files:**
- Create: `pipeline/freshness.py`
- Test: `tests/test_pipeline_freshness.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `record_successful_refresh(timestamp_path, now: float) -> None`, `check_freshness(timestamp_path, now: float, max_age_seconds: float) -> Optional[str]`, `check_all_freshness(now_func=time.time) -> list[str]`, plus constants `POKEAPI_TIMESTAMP_PATH`, `PIKALYTICS_TIMESTAMP_PATH`, `POKEAPI_FRESHNESS_THRESHOLD_SECONDS`, `PIKALYTICS_FRESHNESS_THRESHOLD_SECONDS`. Task 3 calls `record_successful_refresh` and `check_all_freshness` with `POKEAPI_TIMESTAMP_PATH` as `run_refresh`'s default `timestamp_path`. Task 4 does the same with `PIKALYTICS_TIMESTAMP_PATH`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_pipeline_freshness.py`:

```python
import json

from pipeline.freshness import (
    PIKALYTICS_FRESHNESS_THRESHOLD_SECONDS,
    POKEAPI_FRESHNESS_THRESHOLD_SECONDS,
    check_all_freshness,
    check_freshness,
    record_successful_refresh,
)


def test_record_successful_refresh_writes_the_timestamp(tmp_path):
    timestamp_path = tmp_path / "last_refresh.json"

    record_successful_refresh(timestamp_path, now=1000.0)

    written = json.loads(timestamp_path.read_text())
    assert written == {"last_refresh": 1000.0}


def test_check_freshness_returns_none_when_the_file_is_missing(tmp_path):
    timestamp_path = tmp_path / "does_not_exist.json"

    result = check_freshness(timestamp_path, now=1000.0, max_age_seconds=100.0)

    assert result is None


def test_check_freshness_returns_none_when_within_the_threshold(tmp_path):
    timestamp_path = tmp_path / "last_refresh.json"
    record_successful_refresh(timestamp_path, now=1000.0)

    result = check_freshness(timestamp_path, now=1050.0, max_age_seconds=100.0)

    assert result is None


def test_check_freshness_returns_a_warning_when_past_the_threshold(tmp_path):
    timestamp_path = tmp_path / "last_refresh.json"
    record_successful_refresh(timestamp_path, now=1000.0)

    result = check_freshness(timestamp_path, now=1000.0 + 200.0, max_age_seconds=100.0)

    assert result is not None
    assert str(timestamp_path) in result


def test_check_freshness_uses_the_pokeapi_threshold_of_14_days(tmp_path):
    timestamp_path = tmp_path / "last_refresh_pokeapi.json"
    now = 10_000_000.0
    record_successful_refresh(timestamp_path, now=now)

    just_under = now + POKEAPI_FRESHNESS_THRESHOLD_SECONDS - 1
    just_over = now + POKEAPI_FRESHNESS_THRESHOLD_SECONDS + 1

    assert check_freshness(timestamp_path, just_under, POKEAPI_FRESHNESS_THRESHOLD_SECONDS) is None
    assert check_freshness(timestamp_path, just_over, POKEAPI_FRESHNESS_THRESHOLD_SECONDS) is not None


def test_check_freshness_uses_the_pikalytics_threshold_of_60_days(tmp_path):
    timestamp_path = tmp_path / "last_refresh_pikalytics.json"
    now = 10_000_000.0
    record_successful_refresh(timestamp_path, now=now)

    just_under = now + PIKALYTICS_FRESHNESS_THRESHOLD_SECONDS - 1
    just_over = now + PIKALYTICS_FRESHNESS_THRESHOLD_SECONDS + 1

    assert check_freshness(timestamp_path, just_under, PIKALYTICS_FRESHNESS_THRESHOLD_SECONDS) is None
    assert check_freshness(timestamp_path, just_over, PIKALYTICS_FRESHNESS_THRESHOLD_SECONDS) is not None


def test_check_all_freshness_returns_no_warnings_when_no_timestamps_exist_yet(monkeypatch, tmp_path):
    monkeypatch.setattr("pipeline.freshness.POKEAPI_TIMESTAMP_PATH", str(tmp_path / "pokeapi.json"))
    monkeypatch.setattr("pipeline.freshness.PIKALYTICS_TIMESTAMP_PATH", str(tmp_path / "pikalytics.json"))

    warnings = check_all_freshness(now_func=lambda: 1000.0)

    assert warnings == []


def test_check_all_freshness_reports_a_stale_job_by_name(monkeypatch, tmp_path):
    pokeapi_path = tmp_path / "pokeapi.json"
    pikalytics_path = tmp_path / "pikalytics.json"
    monkeypatch.setattr("pipeline.freshness.POKEAPI_TIMESTAMP_PATH", str(pokeapi_path))
    monkeypatch.setattr("pipeline.freshness.PIKALYTICS_TIMESTAMP_PATH", str(pikalytics_path))
    record_successful_refresh(pokeapi_path, now=0.0)
    record_successful_refresh(pikalytics_path, now=0.0)

    # Only the PokeAPI job's threshold (14 days) has elapsed, not the
    # Pikalytics job's (60 days) -- only one warning should appear.
    stale_for_pokeapi_only = POKEAPI_FRESHNESS_THRESHOLD_SECONDS + 1

    warnings = check_all_freshness(now_func=lambda: stale_for_pokeapi_only)

    assert len(warnings) == 1
    assert str(pokeapi_path) in warnings[0]
```

Note on the monkeypatching approach: `check_all_freshness` reads `POKEAPI_TIMESTAMP_PATH`/`PIKALYTICS_TIMESTAMP_PATH` as module-level globals at call time (not as function *default parameter values*, which Python would bind once at def-time and which a `monkeypatch.setattr` on the module afterward would then fail to affect). Implement it that way — see Step 3 below — so these tests actually exercise the override.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_pipeline_freshness.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pipeline.freshness'`.

- [ ] **Step 3: Implement `pipeline/freshness.py`**

```python
import json
import time
from pathlib import Path
from typing import Optional

POKEAPI_TIMESTAMP_PATH = "data/processed/.last_refresh_pokeapi.json"
PIKALYTICS_TIMESTAMP_PATH = "data/processed/.last_refresh_pikalytics.json"

# Loosely double each job's own cadence (deploy/systemd/*.timer: weekly for
# PokeAPI, monthly for Pikalytics) -- using the shorter threshold for both
# jobs would false-positive "stale" on the Pikalytics job every single
# month even when it's running exactly on schedule.
POKEAPI_FRESHNESS_THRESHOLD_SECONDS = 14 * 24 * 60 * 60
PIKALYTICS_FRESHNESS_THRESHOLD_SECONDS = 60 * 24 * 60 * 60


def record_successful_refresh(timestamp_path, now: float) -> None:
    timestamp_path = Path(timestamp_path)
    timestamp_path.parent.mkdir(parents=True, exist_ok=True)
    with open(timestamp_path, "w") as f:
        json.dump({"last_refresh": now}, f)


def check_freshness(timestamp_path, now: float, max_age_seconds: float) -> Optional[str]:
    """Returns a warning string if the last recorded refresh is older than
    max_age_seconds, or None if fresh. A missing timestamp file (no refresh
    has ever succeeded, or a fresh setup) is treated as "unknown," not
    "stale" -- returns None rather than false-positiving."""
    timestamp_path = Path(timestamp_path)
    if not timestamp_path.exists():
        return None
    with open(timestamp_path) as f:
        data = json.load(f)
    age_seconds = now - data["last_refresh"]
    if age_seconds > max_age_seconds:
        age_days = age_seconds / 86400
        threshold_days = max_age_seconds / 86400
        return (
            f"last successful refresh at {timestamp_path} was {age_days:.1f} days "
            f"ago (threshold: {threshold_days:.0f} days)"
        )
    return None


def check_all_freshness(now_func=time.time) -> list:
    """Checks both refresh jobs' own timestamp files against their own
    thresholds. Returns a list of warning strings (empty if both are fresh
    or unknown)."""
    now = now_func()
    warnings = [
        check_freshness(POKEAPI_TIMESTAMP_PATH, now, POKEAPI_FRESHNESS_THRESHOLD_SECONDS),
        check_freshness(PIKALYTICS_TIMESTAMP_PATH, now, PIKALYTICS_FRESHNESS_THRESHOLD_SECONDS),
    ]
    return [w for w in warnings if w is not None]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_pipeline_freshness.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add pipeline/freshness.py tests/test_pipeline_freshness.py
git commit -m "feat: add refresh freshness tracking"
```

---

### Task 3: Validate-before-swap in `pipeline/refresh_job.py`

**Files:**
- Modify: `pipeline/refresh_job.py` (full file)
- Modify: `tests/test_refresh_job.py` (rework 1 test, add 1 new test)

**Interfaces:**
- Consumes: `validate_records`, `validate_write_count`, `validate_legal_count` (Task 1); `record_successful_refresh`, `check_all_freshness`, `POKEAPI_TIMESTAMP_PATH` (Task 2).
- Produces: `run_refresh(...)`'s returned dict gains `"validation_problems"` (list, empty means the swap happened) and `"swapped"` (bool). Nothing later in this plan consumes this — Task 4 makes the equivalent change to the other job independently.

- [ ] **Step 1: Write the failing test — rework the shortfall test**

In `tests/test_refresh_job.py`, replace this existing test:

```python
def test_run_refresh_reports_shortfall_when_a_fetch_fails(tmp_path):
    # Two legal Pokemon, the second one 404s (and its species fallback 404s
    # too), so only one record can be written. The summary must expose the
    # shortfall rather than silently swallowing it.
    source_dir = _fixture_source(tmp_path, legal_pokemon=["Abomasnow", "Bogusmon"])
    raw_dir = tmp_path / "raw"
    output_path = tmp_path / "processed" / "pokemon_records.json"

    session = MagicMock()
    ok = MagicMock(status_code=200)
    ok.json.return_value = _SAMPLE_RESPONSE
    miss = MagicMock(status_code=404)
    session.get.side_effect = [ok, miss, miss]

    summary = run_refresh(source_dir, raw_dir, output_path, session=session)

    assert summary["failed"] == ["Bogusmon"]
    assert summary["expected_count"] == 2
    assert summary["records_written"] == 1
    assert summary["records_written"] < summary["expected_count"]
```

with:

```python
def test_run_refresh_leaves_the_live_file_unchanged_when_a_fetch_fails(tmp_path):
    # Two legal Pokemon, the second one 404s (and its species fallback 404s
    # too), so only one record can be built. Under validate-before-swap,
    # this shortfall is a hard failure -- the live file must not be
    # touched, not silently written with partial data.
    source_dir = _fixture_source(tmp_path, legal_pokemon=["Abomasnow", "Bogusmon"])
    raw_dir = tmp_path / "raw"
    output_path = tmp_path / "processed" / "pokemon_records.json"

    session = MagicMock()
    ok = MagicMock(status_code=200)
    ok.json.return_value = _SAMPLE_RESPONSE
    miss = MagicMock(status_code=404)
    session.get.side_effect = [ok, miss, miss]

    summary = run_refresh(source_dir, raw_dir, output_path, session=session)

    assert summary["failed"] == ["Bogusmon"]
    assert summary["expected_count"] == 2
    assert summary["records_written"] == 1
    assert summary["swapped"] is False
    assert summary["validation_problems"] != []
    assert not output_path.exists()
```

Then append this new test to the end of the file:

```python
def test_run_refresh_swaps_and_records_a_timestamp_on_a_clean_run(tmp_path):
    source_dir = _fixture_source(tmp_path)
    raw_dir = tmp_path / "raw"
    output_path = tmp_path / "processed" / "pokemon_records.json"
    timestamp_path = tmp_path / "last_refresh_pokeapi.json"

    session = MagicMock()
    response = MagicMock(status_code=200)
    response.json.return_value = _SAMPLE_RESPONSE
    session.get.return_value = response

    summary = run_refresh(
        source_dir, raw_dir, output_path, session=session,
        timestamp_path=timestamp_path, now_func=lambda: 12345.0,
    )

    assert summary["swapped"] is True
    assert summary["validation_problems"] == []
    assert output_path.exists()
    recorded = json.loads(timestamp_path.read_text())
    assert recorded == {"last_refresh": 12345.0}
```

- [ ] **Step 2: Run the tests to verify the new/changed ones fail**

Run: `pytest tests/test_refresh_job.py -v`
Expected: `test_run_refresh_leaves_the_live_file_unchanged_when_a_fetch_fails` FAILS (the current code still writes the file and has no `"swapped"`/`"validation_problems"` keys), and `test_run_refresh_swaps_and_records_a_timestamp_on_a_clean_run` FAILS with `TypeError: run_refresh() got an unexpected keyword argument 'timestamp_path'`. The other 2 pre-existing tests in the file still PASS.

- [ ] **Step 3: Implement the changes to `pipeline/refresh_job.py`**

Replace the full contents of `pipeline/refresh_job.py`:

```python
import json
import os
import sys
import time
from pathlib import Path

from pipeline.fetch_pokeapi import fetch_all
from pipeline.build_records import (
    build_records,
    find_legal_pokemon_file,
    write_processed_records,
)
from pipeline.freshness import (
    POKEAPI_TIMESTAMP_PATH,
    check_all_freshness,
    record_successful_refresh,
)
from pipeline.validate import validate_legal_count, validate_records, validate_write_count


def run_refresh(
    source_dir, raw_dir, output_path, session=None,
    timestamp_path=POKEAPI_TIMESTAMP_PATH, now_func=time.time,
) -> dict:
    source_dir = Path(source_dir)
    raw_dir = Path(raw_dir)
    output_path = Path(output_path)

    with open(find_legal_pokemon_file(source_dir)) as f:
        legal_data = json.load(f)
    legal_names = legal_data["legal_pokemon"]
    regulation = legal_data["regulation"]
    # The source file declares its own count; trust that as the expected total
    # so a truncated or partially-parsed legal_pokemon list is caught too.
    expected_count = legal_data.get("count", len(legal_names))

    summary = fetch_all(legal_names, cache_dir=raw_dir, session=session)

    records = build_records(source_dir, raw_dir)
    summary["records_written"] = len(records)
    summary["expected_count"] = expected_count

    problems = (
        validate_records(records)
        + validate_legal_count(regulation, expected_count)
        + validate_write_count(len(records), expected_count)
    )
    summary["validation_problems"] = problems

    if problems:
        summary["swapped"] = False
        return summary

    temp_path = output_path.with_name(output_path.name + ".tmp")
    write_processed_records(records, temp_path)
    os.replace(temp_path, output_path)
    summary["swapped"] = True
    record_successful_refresh(timestamp_path, now_func())
    return summary


if __name__ == "__main__":
    result = run_refresh(
        source_dir=Path("data/source"),
        raw_dir=Path("data/raw"),
        output_path=Path("data/processed/pokemon_records.json"),
    )

    written = result["records_written"]
    expected = result["expected_count"]
    failed = result["failed"]
    problems = result["validation_problems"]

    print(
        f"fetched={result['fetched']} cached={result['cached']} "
        f"failed={len(failed)} records_written={written} expected_count={expected}"
    )
    if failed:
        print(f"\nFAILED to fetch {len(failed)} Pokemon:")
        for name in failed:
            print(f"  - {name}")

    for warning in check_all_freshness():
        print(f"\nWARNING: {warning}")

    if problems:
        print("\nERROR: validation failed, live data left unchanged:")
        for problem in problems:
            print(f"  - {problem}")
        sys.exit(1)
    print("\nOK: all legal Pokemon resolved, validated, and written.")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_refresh_job.py -v`
Expected: all PASS.

- [ ] **Step 5: Run the entire test suite to verify nothing else broke**

Run: `pytest -q`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add pipeline/refresh_job.py tests/test_refresh_job.py
git commit -m "feat: validate-before-swap and freshness tracking in refresh_job"
```

---

### Task 4: Validate-before-swap in `pipeline/refresh_pikalytics_job.py`

**Files:**
- Modify: `pipeline/refresh_pikalytics_job.py` (full file)
- Modify: `tests/test_refresh_pikalytics_job.py` (add 2 new tests; confirm the 2 existing tests still pass unchanged)

**Interfaces:**
- Consumes: `validate_usage` (Task 1); `record_successful_refresh`, `check_all_freshness`, `PIKALYTICS_TIMESTAMP_PATH` (Task 2).
- Produces: `run_pikalytics_refresh(...)`'s returned dict gains `"validation_problems"` and `"swapped"`, mirroring Task 3's shape on the other job. Nothing later in this plan consumes this — final task.

- [ ] **Step 1: Write the failing tests**

Append these 2 tests to `tests/test_refresh_pikalytics_job.py`:

```python
def test_run_pikalytics_refresh_leaves_the_live_file_unchanged_on_an_unknown_species(tmp_path, monkeypatch):
    # The legal-Pokemon list only names Garchomp, but the fetched usage
    # data references a species outside that list -- a referential
    # integrity problem that should block the swap, same as a schema
    # problem on the PokeAPI side does. fetch_all_usage is driven by
    # legal_names, so to exercise the referential check we monkeypatch its
    # result directly rather than trying to make the real fetch return an
    # out-of-list species.
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "legal_pokemon_m-b.json").write_text(json.dumps({
        "regulation": "M-B", "count": 1, "legal_pokemon": ["Garchomp"],
    }))
    cache_dir = tmp_path / "raw_pikalytics"
    output_path = tmp_path / "processed" / "pikalytics_usage.json"
    output_path.parent.mkdir(parents=True)
    output_path.write_text('{"pre-existing": "data"}')

    session = MagicMock()
    monkeypatch.setattr(
        "pipeline.refresh_pikalytics_job.fetch_all_usage",
        lambda *a, **k: {
            "fetched": 1, "cached": 0, "failed": [],
            "usage_by_species": {"NotInLegalList": {"moves": [], "items": [], "abilities": []}},
        },
    )

    result = run_pikalytics_refresh(source_dir, cache_dir, output_path, session=session)

    assert result["swapped"] is False
    assert result["validation_problems"] != []
    assert output_path.read_text() == '{"pre-existing": "data"}'


def test_run_pikalytics_refresh_swaps_and_records_a_timestamp_on_a_clean_run(tmp_path):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "legal_pokemon_m-b.json").write_text(json.dumps({
        "regulation": "M-B", "count": 1, "legal_pokemon": ["Garchomp"],
    }))
    cache_dir = tmp_path / "raw_pikalytics"
    output_path = tmp_path / "processed" / "pikalytics_usage.json"
    timestamp_path = tmp_path / "last_refresh_pikalytics.json"

    session = MagicMock()
    session.get.return_value = MagicMock(status_code=200, text=_SAMPLE_MARKDOWN)

    result = run_pikalytics_refresh(
        source_dir, cache_dir, output_path, session=session,
        timestamp_path=timestamp_path, now_func=lambda: 54321.0,
    )

    assert result["swapped"] is True
    assert result["validation_problems"] == []
    recorded = json.loads(timestamp_path.read_text())
    assert recorded == {"last_refresh": 54321.0}
```

- [ ] **Step 2: Run the tests to verify the new ones fail**

Run: `pytest tests/test_refresh_pikalytics_job.py -v`
Expected: both new tests FAIL — the first because the current code writes `output_path` unconditionally regardless of species validity (no referential check exists yet), the second with `TypeError: run_pikalytics_refresh() got an unexpected keyword argument 'timestamp_path'`. The 2 pre-existing tests still PASS.

- [ ] **Step 3: Implement the changes to `pipeline/refresh_pikalytics_job.py`**

Replace the full contents of `pipeline/refresh_pikalytics_job.py`:

```python
import json
import os
import sys
import time
from pathlib import Path

from pipeline.build_records import find_legal_pokemon_file
from pipeline.fetch_pikalytics import fetch_all_usage
from pipeline.freshness import (
    PIKALYTICS_TIMESTAMP_PATH,
    check_all_freshness,
    record_successful_refresh,
)
from pipeline.validate import validate_usage


def run_pikalytics_refresh(
    source_dir, cache_dir, output_path, session=None,
    timestamp_path=PIKALYTICS_TIMESTAMP_PATH, now_func=time.time,
) -> dict:
    source_dir = Path(source_dir)
    output_path = Path(output_path)

    with open(find_legal_pokemon_file(source_dir)) as f:
        legal_data = json.load(f)
    legal_names = legal_data["legal_pokemon"]

    result = fetch_all_usage(legal_names, cache_dir=cache_dir, session=session)
    usage_by_species = result["usage_by_species"]
    result["species_with_data"] = len(usage_by_species)

    problems = validate_usage(usage_by_species, known_species=set(legal_names))
    result["validation_problems"] = problems

    if problems:
        result["swapped"] = False
        return result

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = output_path.with_name(output_path.name + ".tmp")
    with open(temp_path, "w") as f:
        json.dump(usage_by_species, f, indent=2)
    os.replace(temp_path, output_path)
    result["swapped"] = True
    record_successful_refresh(timestamp_path, now_func())
    return result


if __name__ == "__main__":
    summary = run_pikalytics_refresh(
        source_dir=Path("data/source"),
        cache_dir=Path("data/raw_pikalytics"),
        output_path=Path("data/processed/pikalytics_usage.json"),
    )
    print(
        f"fetched={summary['fetched']} cached={summary['cached']} "
        f"failed={len(summary['failed'])} species_with_data={summary['species_with_data']}"
    )
    if summary["failed"]:
        print(f"\nFAILED to fetch usage for {len(summary['failed'])} Pokemon:")
        for name in summary["failed"]:
            print(f"  - {name}")

    # Mirror refresh_job.py's coverage guard: a scheduled run that silently
    # writes a degenerate result is worse than one that fails loudly. Real
    # HTTP/network failures are an unambiguous problem. Zero species with
    # any usage data despite processing a full legal list is *also* a
    # failure signature (most likely a stale PIKALYTICS_FORMAT_CODE making
    # every page 404, which looks identical to "no usage data" per-species)
    # rather than a legitimate reg where nothing gets played.
    stale_format_code = summary["species_with_data"] == 0 and not summary["failed"]
    if stale_format_code:
        print(
            "\nERROR: every species came back with no usage data and nothing "
            "outright failed -- this looks like a stale PIKALYTICS_FORMAT_CODE "
            "rather than a real 0%-usage regulation."
        )

    for warning in check_all_freshness():
        print(f"\nWARNING: {warning}")

    if summary["validation_problems"]:
        print("\nERROR: validation failed, live data left unchanged:")
        for problem in summary["validation_problems"]:
            print(f"  - {problem}")

    if summary["failed"] or stale_format_code or summary["validation_problems"]:
        sys.exit(1)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_refresh_pikalytics_job.py -v`
Expected: all PASS (4 total: 2 pre-existing + 2 new).

- [ ] **Step 5: Run the entire test suite as a final check**

Run: `pytest -q`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add pipeline/refresh_pikalytics_job.py tests/test_refresh_pikalytics_job.py
git commit -m "feat: validate-before-swap and freshness tracking in refresh_pikalytics_job"
```

---

## Self-review notes

- **Spec coverage:** schema validation for records/items/usage via plain assertions, no new dependency (Task 1); an independent hard-coded legal-count table separate from the source file's own self-reported count, deliberately sparse (only the confirmed-live M-C entry) so it can't collide with the source file's own circularity or with existing test fixtures using retired/synthetic regulation names (Task 1); freshness timestamps per job with independently-derived thresholds (14 days / 60 days) and "missing file is unknown, not stale" semantics (Task 2); validate-before-swap via temp-file + `os.replace` in both refresh jobs, keeping the live file untouched (not even a stray temp file, since validation runs before any disk write) on a hard failure, with the freshness warning check folded into each job's own `__main__` rather than a new deployment artifact (Tasks 3-4); the spec's explicitly-called-out existing-test rework (Task 3, Step 1) — all covered. The `stale_format_code` guard is preserved as additive, not replaced (Task 4).
- **Out-of-scope items** (a schema-validation library, alerting beyond a log line, retroactive validation of already-committed data, format-code-drift/regulation-mismatch detection) are correctly not touched by any task.
- **Type/name consistency checked:** every `validate_*` function returns `list` (of strings), consumed identically by both jobs via `+`-concatenation into one `problems` list. `record_successful_refresh`/`check_freshness`/`check_all_freshness`'s signatures match exactly between their Task 2 definitions and their Task 3/4 call sites (`timestamp_path`, `now_func` parameter names line up with `run_refresh`/`run_pikalytics_refresh`'s new parameters of the same names). `EXPECTED_REGULATION_COUNTS`/`COUNT_TOLERANCE` are read only by `validate_legal_count`, never duplicated elsewhere.
- **Breaking-change fallout audited:** `run_refresh`'s and `run_pikalytics_refresh`'s new `timestamp_path`/`now_func` parameters are both added after the existing `session` parameter with defaults, so every existing call site (all keyword-argument-based in the test suite) continues to work unchanged. The one test the spec explicitly calls out for rework (`test_run_refresh_reports_shortfall_when_a_fetch_fails`) is reworked in Task 3; both `refresh_pikalytics_job` tests are confirmed to still pass unchanged in Task 4 since an empty or fully-known-species usage dict never trips the new `validate_usage` gate.
