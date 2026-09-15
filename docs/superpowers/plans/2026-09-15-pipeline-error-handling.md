# Pipeline Error-Handling Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the highest-impact gaps this session's tech-debt audit of `pipeline/` found: a missing network timeout, an unhandled malformed-response crash, uncaught source-file load errors, an uncaught atomic-swap failure, and an uncaught freshness-timestamp write failure — all of which currently crash a scheduled refresh job with a raw traceback instead of the clean "ERROR: validation failed, live data left unchanged" message the rest of the ingestion-robustness work already established.

**Architecture:** `pipeline/fetch_pokeapi.py`'s `_get` helper gets the same `timeout=` kwarg `pipeline/fetch_pikalytics.py` already uses, and `fetch_pokemon_data` wraps its response-parsing in a try/except that converts a malformed-but-200 body into the existing `PokeApiFetchError` — `fetch_all`'s existing `except PokeApiFetchError` handling then covers it automatically, no changes needed there. `pipeline/refresh_job.py`'s `run_refresh` wraps its two source-file-loading call sites (the legal-Pokemon file and `build_records`) and its `os.replace` atomic swap in try/except blocks that return the same `validation_problems`/`swapped: False` summary shape a real validation failure already produces, and wraps `record_successful_refresh` separately so a freshness-tracking write failure doesn't discard an otherwise-successful data swap. `pipeline/build_records.py`'s `find_legal_pokemon_file` gets one new regression test locking in its existing (correct, just previously untested) multiple-candidate-file behavior — no source change there.

**Tech Stack:** Python 3.9 stdlib only (`json`, `os`) — no new dependencies.

**Spec:** None — derived directly from this session's two-pass audit of `pipeline/` (network calls, error handling, hardcoded assumptions, test coverage). The audit's 7 ranked findings are addressed here except #7 (no `pytest-cov`/coverage tooling in the repo at all), which is a tooling recommendation rather than a pipeline bug and is left for a separate decision — see "Out of scope."

## Global Constraints

- No new dependencies; no new files.
- Every fix in this plan preserves the existing validate-before-swap guarantee: on any failure (missing/corrupted source file, malformed network response, or a failed atomic swap), the live `data/processed/*.json` file the bot actually reads from is left completely untouched.
- A freshness-timestamp write failure (after a successful data swap) must NOT be treated as a refresh failure — the important side effect (the live data file) already succeeded; losing the "last successful refresh" bookkeeping is a lesser, separately-reported problem.
- `pipeline/fetch_pikalytics.py` already has a `timeout=(5, 10)` on its one request and its markdown-regex parsing degrades gracefully on unexpected content (already covered by the existing "no usage data" path) — neither needs a change in this plan.
- Out of scope: adding `pytest-cov`/coverage-percentage tooling to the repo (audit finding #7) — a repo-wide tooling decision, not a `pipeline/` bug fix; flagged for the user to decide separately, not bundled into this plan.

---

## File structure

- Modify `pipeline/fetch_pokeapi.py` — add `POKEAPI_REQUEST_TIMEOUT` constant, apply it in `_get`; wrap `fetch_pokemon_data`'s response-parsing in a try/except that raises `PokeApiFetchError` on a malformed body (Task 1).
- Modify `tests/test_fetch_pokeapi.py` — tests for the timeout and the malformed-response handling.
- Modify `pipeline/refresh_job.py` — wrap the legal-file load, the `build_records` call, `os.replace`, and `record_successful_refresh` each in their own error handling; add a `_empty_summary` helper; print a new warning line in `__main__` for a freshness-write failure (Task 2).
- Modify `tests/test_refresh_job.py` — tests for each of the four new failure paths.
- Modify `tests/test_build_records.py` — one new regression test for `find_legal_pokemon_file`'s existing multiple-candidate behavior; no source change (Task 3).

---

### Task 1: `pipeline/fetch_pokeapi.py` — request timeout and malformed-response handling

**Files:**
- Modify: `pipeline/fetch_pokeapi.py`
- Test: `tests/test_fetch_pokeapi.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: nothing consumed by a later task — Task 2 does not depend on this change (a malformed-response `PokeApiFetchError` from `fetch_pokemon_data` is already caught by `fetch_all`'s existing `except PokeApiFetchError`, unchanged by this plan).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_fetch_pokeapi.py`:

```python
def test_fetch_pokemon_data_uses_a_request_timeout():
    session = _mock_session(_SAMPLE_POKEAPI_RESPONSE)

    fetch_pokemon_data("Abomasnow", session=session)

    _args, kwargs = session.get.call_args
    assert kwargs["timeout"] == (5, 10)


def test_fetch_pokemon_data_raises_on_malformed_response_body():
    session = MagicMock()
    response = MagicMock(status_code=200)
    response.json.return_value = {"unexpected": "shape"}
    session.get.return_value = response

    with pytest.raises(PokeApiFetchError) as exc_info:
        fetch_pokemon_data("Abomasnow", session=session)
    assert "Malformed response body" in str(exc_info.value)


def test_fetch_pokemon_data_raises_on_a_non_json_response_body():
    session = MagicMock()
    response = MagicMock(status_code=200)
    response.json.side_effect = ValueError("not JSON")
    session.get.return_value = response

    with pytest.raises(PokeApiFetchError):
        fetch_pokemon_data("Abomasnow", session=session)


def test_fetch_all_continues_after_a_malformed_response(tmp_path):
    session = MagicMock()
    bad_response = MagicMock(status_code=200)
    bad_response.json.return_value = {"unexpected": "shape"}
    ok_response = MagicMock(status_code=200)
    ok_response.json.return_value = _SAMPLE_POKEAPI_RESPONSE
    session.get.side_effect = [bad_response, ok_response]

    summary = fetch_all(["Broken", "Absol"], cache_dir=tmp_path, session=session)

    assert summary["fetched"] == 1
    assert summary["failed"] == ["Broken"]
    assert (tmp_path / "absol.json").exists()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_fetch_pokeapi.py -v -k "timeout or malformed or non_json"`
Expected: `test_fetch_pokemon_data_uses_a_request_timeout` FAILs with `KeyError: 'timeout'` (no timeout kwarg passed yet); the two malformed-body tests FAIL because `fetch_pokemon_data` currently raises a raw `KeyError`/nothing wraps it, so `pytest.raises(PokeApiFetchError)` doesn't match; `test_fetch_all_continues_after_a_malformed_response` FAILs because the raw `KeyError` propagates out of `fetch_all`'s loop entirely instead of being caught and added to `failed`.

- [ ] **Step 3: Implement**

In `pipeline/fetch_pokeapi.py`, add this constant right after `POKEAPI_SPECIES_URL`:

```python
POKEAPI_REQUEST_TIMEOUT = (5, 10)  # (connect, read) seconds -- matches fetch_pikalytics.py's established pattern
```

Change `_get` from:

```python
def _get(session, url, display_name, slug):
    try:
        return session.get(url)
    except requests.exceptions.RequestException as e:
        raise PokeApiFetchError(
            f"Network error fetching '{display_name}' (slug '{slug}'): {e}"
        ) from e
```

to:

```python
def _get(session, url, display_name, slug):
    try:
        return session.get(url, timeout=POKEAPI_REQUEST_TIMEOUT)
    except requests.exceptions.RequestException as e:
        raise PokeApiFetchError(
            f"Network error fetching '{display_name}' (slug '{slug}'): {e}"
        ) from e
```

Change `fetch_pokemon_data`'s parsing block from:

```python
    payload = response.json()
    base_stats = {
        _STAT_NAME_MAP[s["stat"]["name"]]: s["base_stat"]
        for s in payload["stats"]
        if s["stat"]["name"] in _STAT_NAME_MAP
    }
    learnset = [m["move"]["name"] for m in payload["moves"]]
    abilities = [a["ability"]["name"] for a in payload["abilities"]]
    return {"base_stats": base_stats, "learnset": learnset, "abilities": abilities}
```

to:

```python
    try:
        payload = response.json()
        base_stats = {
            _STAT_NAME_MAP[s["stat"]["name"]]: s["base_stat"]
            for s in payload["stats"]
            if s["stat"]["name"] in _STAT_NAME_MAP
        }
        learnset = [m["move"]["name"] for m in payload["moves"]]
        abilities = [a["ability"]["name"] for a in payload["abilities"]]
    except (ValueError, KeyError, TypeError) as e:
        # ValueError covers a non-JSON body (json.JSONDecodeError is a
        # subclass); KeyError/TypeError cover a 200 response whose body
        # parses fine but doesn't have the expected shape.
        raise PokeApiFetchError(
            f"Malformed response body for '{display_name}' (slug '{slug}'): {e}"
        ) from e
    return {"base_stats": base_stats, "learnset": learnset, "abilities": abilities}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_fetch_pokeapi.py -v`
Expected: all PASS (new and pre-existing).

- [ ] **Step 5: Run the entire test suite as a final check**

Run: `pytest -q`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add pipeline/fetch_pokeapi.py tests/test_fetch_pokeapi.py
git commit -m "fix: add request timeout and malformed-response handling to fetch_pokeapi"
```

---

### Task 2: `pipeline/refresh_job.py` — clean handling of source-load, swap, and freshness-write failures

**Files:**
- Modify: `pipeline/refresh_job.py`
- Test: `tests/test_refresh_job.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `run_refresh(...)`'s return dict gains an optional `"freshness_write_failed"` key (a string, present only when `record_successful_refresh` raised `OSError`) — no other caller of `run_refresh` outside this file's own `__main__` block exists today, so this is the only place that needs to read the new key.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_refresh_job.py` (reuses the existing `_fixture_source` helper and `_SAMPLE_RESPONSE` already at the top of that file):

```python
def test_run_refresh_reports_a_clean_error_when_the_legal_file_is_missing(tmp_path):
    source_dir = tmp_path / "source"
    source_dir.mkdir()  # no legal_pokemon_*.json inside
    raw_dir = tmp_path / "raw"
    output_path = tmp_path / "processed" / "pokemon_records.json"

    summary = run_refresh(
        source_dir, raw_dir, output_path, session=MagicMock(), timestamp_path=tmp_path / "ts.json"
    )

    assert summary["swapped"] is False
    assert summary["validation_problems"]
    assert not output_path.exists()


def test_run_refresh_reports_a_clean_error_when_a_source_file_is_corrupted(tmp_path):
    source_dir = _fixture_source(tmp_path)
    (source_dir / "vgc_moves.json").write_text("{not valid json")
    raw_dir = tmp_path / "raw"
    output_path = tmp_path / "processed" / "pokemon_records.json"
    session = MagicMock()
    response = MagicMock(status_code=200)
    response.json.return_value = _SAMPLE_RESPONSE
    session.get.return_value = response

    summary = run_refresh(
        source_dir, raw_dir, output_path, session=session, timestamp_path=tmp_path / "ts.json"
    )

    assert summary["swapped"] is False
    assert summary["validation_problems"]
    assert not output_path.exists()


def test_run_refresh_reports_a_clean_error_when_the_atomic_swap_fails(tmp_path, monkeypatch):
    source_dir = _fixture_source(tmp_path)
    raw_dir = tmp_path / "raw"
    output_path = tmp_path / "processed" / "pokemon_records.json"
    output_path.parent.mkdir(parents=True)
    output_path.write_text("[]")  # pre-existing live data
    session = MagicMock()
    response = MagicMock(status_code=200)
    response.json.return_value = _SAMPLE_RESPONSE
    session.get.return_value = response

    def _boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr("pipeline.refresh_job.os.replace", _boom)

    summary = run_refresh(
        source_dir, raw_dir, output_path, session=session, timestamp_path=tmp_path / "ts.json"
    )

    assert summary["swapped"] is False
    assert summary["validation_problems"]
    assert output_path.read_text() == "[]"  # live data left completely untouched


def test_run_refresh_records_a_successful_swap_even_if_the_freshness_write_fails(tmp_path, monkeypatch):
    source_dir = _fixture_source(tmp_path)
    raw_dir = tmp_path / "raw"
    output_path = tmp_path / "processed" / "pokemon_records.json"
    session = MagicMock()
    response = MagicMock(status_code=200)
    response.json.return_value = _SAMPLE_RESPONSE
    session.get.return_value = response

    def _boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr("pipeline.refresh_job.record_successful_refresh", _boom)

    summary = run_refresh(
        source_dir, raw_dir, output_path, session=session, timestamp_path=tmp_path / "ts.json"
    )

    assert summary["swapped"] is True
    assert output_path.exists()
    assert summary["freshness_write_failed"] == "disk full"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_refresh_job.py -v -k "missing or corrupted or atomic_swap or freshness_write"`
Expected: all 4 FAIL. The first two crash with an uncaught `FileNotFoundError`/`json.JSONDecodeError` inside `run_refresh` instead of returning a summary; the third crashes with an uncaught `OSError` from the monkeypatched `os.replace`; the fourth crashes with an uncaught `OSError` from the monkeypatched `record_successful_refresh` (so `run_refresh` never returns a summary for `pytest` to assert on in any of the four).

- [ ] **Step 3: Implement**

In `pipeline/refresh_job.py`, add this right after the imports:

```python
_SOURCE_LOAD_ERRORS = (FileNotFoundError, json.JSONDecodeError, KeyError)


def _empty_summary(problem: str) -> dict:
    return {
        "fetched": 0, "cached": 0, "failed": [],
        "records_written": 0, "expected_count": 0,
        "validation_problems": [problem], "swapped": False,
    }
```

Change `run_refresh` from:

```python
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
```

to:

```python
def run_refresh(
    source_dir, raw_dir, output_path, session=None,
    timestamp_path=POKEAPI_TIMESTAMP_PATH, now_func=time.time,
) -> dict:
    source_dir = Path(source_dir)
    raw_dir = Path(raw_dir)
    output_path = Path(output_path)

    try:
        with open(find_legal_pokemon_file(source_dir)) as f:
            legal_data = json.load(f)
        legal_names = legal_data["legal_pokemon"]
        regulation = legal_data["regulation"]
        # The source file declares its own count; trust that as the expected
        # total so a truncated or partially-parsed legal_pokemon list is
        # caught too.
        expected_count = legal_data.get("count", len(legal_names))
    except _SOURCE_LOAD_ERRORS as e:
        return _empty_summary(f"Could not load legal-Pokemon source data: {e}")

    summary = fetch_all(legal_names, cache_dir=raw_dir, session=session)

    try:
        records = build_records(source_dir, raw_dir)
    except _SOURCE_LOAD_ERRORS as e:
        summary["records_written"] = 0
        summary["expected_count"] = expected_count
        summary["validation_problems"] = [f"Could not build records from source data: {e}"]
        summary["swapped"] = False
        return summary

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
    try:
        os.replace(temp_path, output_path)
    except OSError as e:
        summary["swapped"] = False
        summary["validation_problems"] = [f"Could not write live data (filesystem error): {e}"]
        return summary
    summary["swapped"] = True

    try:
        record_successful_refresh(timestamp_path, now_func())
    except OSError as e:
        summary["freshness_write_failed"] = str(e)
    return summary
```

Then in the `if __name__ == "__main__":` block, change:

```python
    for warning in check_all_freshness():
        print(f"\nWARNING: {warning}")

    if problems:
```

to:

```python
    for warning in check_all_freshness():
        print(f"\nWARNING: {warning}")

    if result.get("freshness_write_failed"):
        print(f"\nWARNING: could not record successful-refresh timestamp: {result['freshness_write_failed']}")

    if problems:
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_refresh_job.py -v`
Expected: all PASS (new and pre-existing — the two pre-existing happy-path tests, `test_run_refresh_fetches_and_writes_records` and `test_run_refresh_swaps_and_records_a_timestamp_on_a_clean_run`, are unaffected since this change only adds try/except around the same existing calls).

- [ ] **Step 5: Run the entire test suite as a final check**

Run: `pytest -q`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add pipeline/refresh_job.py tests/test_refresh_job.py
git commit -m "fix: handle source-load, atomic-swap, and freshness-write failures cleanly in run_refresh"
```

---

### Task 3: Regression test for `find_legal_pokemon_file`'s multiple-candidate behavior

**Files:**
- Modify: `tests/test_build_records.py`

**Interfaces:**
- Consumes: `find_legal_pokemon_file` (already exists, unchanged).
- Produces: nothing consumed by a later task — this is the final task in this plan, and it changes no source code at all.

- [ ] **Step 1: Write the test**

Change the import at the top of `tests/test_build_records.py` from:

```python
from pipeline.build_records import build_records, write_processed_records
```

to:

```python
from pipeline.build_records import build_records, find_legal_pokemon_file, write_processed_records
```

Then append:

```python
def test_find_legal_pokemon_file_picks_the_latest_when_multiple_exist(tmp_path):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "legal_pokemon_m-b.json").write_text("{}")
    (source_dir / "legal_pokemon_m-c.json").write_text("{}")

    result = find_legal_pokemon_file(source_dir)

    assert result.name == "legal_pokemon_m-c.json"
```

- [ ] **Step 2: Run the test**

Run: `pytest tests/test_build_records.py -v -k multiple_exist`
Expected: PASS immediately — `find_legal_pokemon_file`'s existing `sorted(...)[-1]` already picks the alphabetically-last match, which happens to be the correct "latest regulation" behavior given this project's `legal_pokemon_m-<letter>.json` naming. This step exists to lock that behavior in with a real test, not to fix a bug.

- [ ] **Step 3: Run the entire test suite as a final check**

Run: `pytest -q`
Expected: all PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/test_build_records.py
git commit -m "test: lock in find_legal_pokemon_file's multiple-candidate behavior"
```

---

## Self-review notes

- **Audit-finding coverage:** #1 (missing timeout) and #2/malformed-response (Task 1); #3 (`build_records`'s unhandled `_load_json` errors) and the two related but separately-ranked findings, uncaught `os.replace` failure and uncaught `record_successful_refresh` failure (Task 2); the untested-but-correct `find_legal_pokemon_file` multi-candidate behavior (Task 3) — all 6 addressed findings covered. #7 (no coverage tooling) is explicitly out of scope per Global Constraints, not silently dropped.
- **Placeholder scan:** no TBD/TODO; every step has complete, runnable code and an exact expected-failure/expected-pass description.
- **Type consistency checked:** `_empty_summary`'s returned dict has every key `pipeline/refresh_job.py`'s own `__main__` block reads (`fetched`, `cached`, `failed`, `records_written`, `expected_count`, `validation_problems`, `swapped`) — verified against the existing `__main__` block's `result["fetched"]`/`result["cached"]`/`result["failed"]`/etc. accesses before finalizing this plan, so an early-return summary can't crash `__main__` with a `KeyError` the way an unhandled exception used to crash `run_refresh` itself.
- **Regression risk audited:** every change in Task 1 and Task 2 wraps existing code in try/except without altering the happy path's control flow or return values, so the pre-existing tests in both files (confirmed by reading them before writing this plan) continue to exercise the same success-path assertions unchanged.
