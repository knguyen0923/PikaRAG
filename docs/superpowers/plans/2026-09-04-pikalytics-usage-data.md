# Pikalytics Usage Data Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pull real VGC usage data (top moves, items, abilities) from Pikalytics for the current regulation's legal roster, and use it to augment `/stats` (a "Common build" line) and `/moves` (top moves by usage instead of the full legal learnset), falling back to today's behavior wherever no usage data exists for a species.

**Architecture:** A new, fully independent pipeline module (`pipeline/fetch_pikalytics.py`) fetches, parses, and caches per-species usage pages, and a refresh job (`pipeline/refresh_pikalytics_job.py`) writes the result to `data/processed/pikalytics_usage.json`. `bot/main.py` loads that file and threads it into `stats_response`/`moves_response` as a new optional argument — `/calc`, `/import`, `/scout`, `/team`, `bot/team_store.py`, `bot/pokepaste.py`, and `damage_calc/` are never touched.

**Tech Stack:** Python 3.9, `requests` (already a dependency), `re` (stdlib), pytest.

**Spec:** `docs/superpowers/specs/2026-09-04-pikalytics-usage-data-design.md`

## Global Constraints

- Pikalytics' real response format (confirmed via direct `curl`, not a summarizing tool): HTTP 200 with `content-type: text/markdown`, body containing `## Common Moves`, `## Common Abilities`, `## Common Items` sections in that order, each a list of `- **<name>**: <percent>%` lines. HTTP 404 with a plain-text body for an unrecognized species — detected by status code alone.
- Pikalytics' URL slug for a species is `pipeline.fetch_pokeapi.resolve_pokeapi_name(display_name)`, title-cased word by word on `-` (e.g. `"rotom-wash"` → `"Rotom-Wash"`, `"charizard-mega-x"` → `"Charizard-Mega-X"`). Reuse that existing function — do not reimplement form/Mega/regional parsing.
- A 404 for any species means "no usage data" — return `None`, never raise. A network error or any other non-200/non-404 status raises `PikalyticsFetchError`.
- No EV data and no usable teammate data exist on the page at all (confirmed) — the data model has exactly three fields: `moves`, `items`, `abilities`. Moves and items are capped at the top 6 by usage; abilities keep everything listed.
- `stats_response`/`moves_response` keep their existing signatures backward compatible: a new `usage=None` parameter, behaving identically to today when `usage` is `None` or has no entry for the matched species.
- `/calc`, `/import`, `/scout`, `/team`, `bot/team_store.py`, `bot/pokepaste.py`, and everything under `damage_calc/` must not change. The full pre-existing test suite must pass unmodified at the end of every task.
- `PIKALYTICS_FORMAT_CODE = "battledataregmbs3"` is a manually-set, manually-verified constant (VGC 2026 Reg M-B Season 3) — not derived from the regulation label in `legal_pokemon_m-*.json`.

---

### Task 1: Pikalytics fetch + parse module

**Files:**
- Create: `pipeline/fetch_pikalytics.py`
- Test: `tests/test_fetch_pikalytics.py`

**Interfaces:**
- Consumes: `pipeline.fetch_pokeapi.resolve_pokeapi_name(display_name: str) -> str` (existing, already tested); `pipeline.cache_utils.simple_cache_filename(display_name: str) -> str` (existing, already tested).
- Produces: `resolve_pikalytics_slug(display_name: str) -> str`; `parse_usage_markdown(markdown: str) -> dict` (returns `{"moves": [...], "items": [...], "abilities": [...]}`, each entry `{"name": str, "usage_pct": float}`); `fetch_pikalytics_usage(display_name: str, session=None) -> dict | None`; `PikalyticsFetchError(Exception)`; `fetch_all_usage(legal_names: list, cache_dir, session=None, delay_seconds: float = 0.5) -> dict` (returns `{"usage_by_species": {species: usage_dict}, "fetched": int, "cached": int, "failed": list[str]}`).

- [ ] **Step 1: Write failing tests for resolve_pikalytics_slug**

Create `tests/test_fetch_pikalytics.py`:

```python
import json
import pytest
import requests
from unittest.mock import MagicMock

from pipeline.fetch_pikalytics import (
    resolve_pikalytics_slug,
    parse_usage_markdown,
    fetch_pikalytics_usage,
    fetch_all_usage,
    PikalyticsFetchError,
)


def test_resolve_plain_name():
    assert resolve_pikalytics_slug("Garchomp") == "Garchomp"


def test_resolve_prefix_form_species():
    assert resolve_pikalytics_slug("Wash Rotom") == "Rotom-Wash"


def test_resolve_bracket_regional_form():
    assert resolve_pikalytics_slug("Ninetales [Alolan Form]") == "Ninetales-Alola"


def test_resolve_mega():
    assert resolve_pikalytics_slug("Mega Abomasnow") == "Abomasnow-Mega"


def test_resolve_mega_x_y():
    assert resolve_pikalytics_slug("Mega Charizard X") == "Charizard-Mega-X"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_fetch_pikalytics.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pipeline.fetch_pikalytics'`

- [ ] **Step 3: Implement resolve_pikalytics_slug**

Create `pipeline/fetch_pikalytics.py`:

```python
import json
import re
import time
from pathlib import Path

import requests

from pipeline.cache_utils import simple_cache_filename
from pipeline.fetch_pokeapi import resolve_pokeapi_name

PIKALYTICS_FORMAT_CODE = "battledataregmbs3"  # VGC 2026 Reg M-B S3 -- manually
# verified against Pikalytics' current format list; re-verify whenever a new
# regulation file is dropped in (see spec's "Format code" section -- this is
# NOT derivable from our own regulation label).
PIKALYTICS_AI_BASE_URL = "https://www.pikalytics.com/ai/pokedex"
_TOP_N = 6


class PikalyticsFetchError(Exception):
    pass


def resolve_pikalytics_slug(display_name: str) -> str:
    """Pikalytics' URL slug for a species: this project's existing PokeAPI
    slug (which already solves Mega/regional/prefix-form/bracket naming),
    title-cased word by word on '-'. Confirmed empirically against a plain
    name, a prefix-form species, a bracket regional form, a Mega, and
    Mega X/Y forms.
    """
    pokeapi_slug = resolve_pokeapi_name(display_name)
    return "-".join(word.capitalize() for word in pokeapi_slug.split("-"))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_fetch_pikalytics.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Write failing tests for parse_usage_markdown**

Add to `tests/test_fetch_pikalytics.py`:

```python
_SAMPLE_MARKDOWN = """\
# Garchomp - Best Builds, Moves and Teams in Pokemon Champions VGC 2026 Reg M-B S3 Ranked Battle Data

> Find the best Garchomp builds...

## Best Garchomp Quick Info

| Property | Value |
|----------|-------|
| **Format** | Pokemon Champions VGC 2026 Reg M-B S3 |

## Common Moves
- **Dragon Claw**: 89.4%
- **Rock Slide**: 82.0%
- **Earthquake**: 80.7%
- **Protect**: 70.2%
- **Stomping Tantrum**: 40.3%
- **Poison Jab**: 18.3%
- **Rock Tomb**: 8.0%
- **Scale Shot**: 3.1%
- **Swords Dance**: 2.5%
- **Dragon Tail**: 2.0%

## Common Abilities
- **Rough Skin**: 98.5%
- **Sand Veil**: 1.5%

## Common Items
- **Life Orb**: 51.5%
- **Sitrus Berry**: 13.6%
- **Choice Scarf**: 12.7%
- **Roseli Berry**: 10.8%
- **Soft Sand**: 3.6%
- **White Herb**: 1.3%
- **Focus Sash**: 1.1%
- **Haban Berry**: 1.1%
- **Expert Belt**: 0.9%
- **Lum Berry**: 0.9%

## Common Teammates
- **Whimsicott**: undefined%
- **Charizard**: undefined%

## Featured Teams with Garchomp

### Team 1 by shaikhvgc786
*Record: 13-2*

**Pokemon**: Raichu-Mega-Y, Farigiraf, Mawile-Mega, Garchomp, Vivillon, Torkoal
"""


def test_parses_top_6_moves_sorted_by_usage():
    result = parse_usage_markdown(_SAMPLE_MARKDOWN)

    assert result["moves"] == [
        {"name": "Dragon Claw", "usage_pct": 89.4},
        {"name": "Rock Slide", "usage_pct": 82.0},
        {"name": "Earthquake", "usage_pct": 80.7},
        {"name": "Protect", "usage_pct": 70.2},
        {"name": "Stomping Tantrum", "usage_pct": 40.3},
        {"name": "Poison Jab", "usage_pct": 18.3},
    ]


def test_parses_top_6_items_sorted_by_usage():
    result = parse_usage_markdown(_SAMPLE_MARKDOWN)

    assert result["items"][0] == {"name": "Life Orb", "usage_pct": 51.5}
    assert len(result["items"]) == 6


def test_parses_all_abilities_uncapped():
    result = parse_usage_markdown(_SAMPLE_MARKDOWN)

    assert result["abilities"] == [
        {"name": "Rough Skin", "usage_pct": 98.5},
        {"name": "Sand Veil", "usage_pct": 1.5},
    ]


def test_ignores_teammates_section_and_undefined_percentages():
    result = parse_usage_markdown(_SAMPLE_MARKDOWN)

    all_names = [e["name"] for e in result["moves"] + result["items"] + result["abilities"]]
    assert "Whimsicott" not in all_names
    assert "evs" not in result
    assert "teammates" not in result


def test_missing_section_returns_empty_list():
    markdown_without_items = "## Common Moves\n- **Tackle**: 100.0%\n\n## Common Abilities\n- **Levitate**: 100.0%\n"

    result = parse_usage_markdown(markdown_without_items)

    assert result["items"] == []
    assert result["moves"] == [{"name": "Tackle", "usage_pct": 100.0}]
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `pytest tests/test_fetch_pikalytics.py -v`
Expected: FAIL — `parse_usage_markdown` not defined.

- [ ] **Step 7: Implement parse_usage_markdown**

Add to `pipeline/fetch_pikalytics.py`:

```python
_ENTRY_PATTERN = re.compile(r"^-\s+\*\*(.+?)\*\*:\s+([\d.]+)%\s*$")


def _extract_section(markdown: str, heading: str) -> list:
    """Pull '- **Name**: XX.X%' entries out of a '## <heading>' section,
    stopping at the next '## ' heading or end of text. Lines that don't
    match the expected shape (e.g. Pikalytics' teammate rows, which are
    literally '- **Name**: undefined%') are silently skipped.
    """
    pattern = re.compile(
        rf"^## {re.escape(heading)}\s*$(.*?)(?=^## |\Z)",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(markdown)
    if not match:
        return []
    entries = []
    for line in match.group(1).splitlines():
        entry_match = _ENTRY_PATTERN.match(line.strip())
        if entry_match:
            entries.append({"name": entry_match.group(1), "usage_pct": float(entry_match.group(2))})
    return entries


def parse_usage_markdown(markdown: str) -> dict:
    moves = sorted(_extract_section(markdown, "Common Moves"), key=lambda e: -e["usage_pct"])
    items = sorted(_extract_section(markdown, "Common Items"), key=lambda e: -e["usage_pct"])
    abilities = sorted(_extract_section(markdown, "Common Abilities"), key=lambda e: -e["usage_pct"])
    return {"moves": moves[:_TOP_N], "items": items[:_TOP_N], "abilities": abilities}
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `pytest tests/test_fetch_pikalytics.py -v`
Expected: PASS (10 passed)

- [ ] **Step 9: Write failing tests for fetch_pikalytics_usage**

Add to `tests/test_fetch_pikalytics.py`:

```python
def _mock_session(status_code, text=None):
    session = MagicMock()
    response = MagicMock(status_code=status_code, text=text)
    session.get.return_value = response
    return session


def test_fetch_pikalytics_usage_parses_a_successful_response():
    session = _mock_session(200, text=_SAMPLE_MARKDOWN)

    result = fetch_pikalytics_usage("Garchomp", session=session)

    assert result["moves"][0]["name"] == "Dragon Claw"
    session.get.assert_called_once_with(
        "https://www.pikalytics.com/ai/pokedex/battledataregmbs3/Garchomp"
    )


def test_fetch_pikalytics_usage_returns_none_on_404():
    session = _mock_session(404, text="Pokemon not found")

    result = fetch_pikalytics_usage("Nonexistamon", session=session)

    assert result is None


def test_fetch_pikalytics_usage_raises_on_other_error_status():
    session = _mock_session(500)

    with pytest.raises(PikalyticsFetchError):
        fetch_pikalytics_usage("Garchomp", session=session)


def test_fetch_pikalytics_usage_wraps_network_exception():
    session = MagicMock()
    session.get.side_effect = requests.exceptions.ConnectionError("refused")

    with pytest.raises(PikalyticsFetchError):
        fetch_pikalytics_usage("Garchomp", session=session)
```

- [ ] **Step 10: Run tests to verify they fail**

Run: `pytest tests/test_fetch_pikalytics.py -v`
Expected: FAIL — `fetch_pikalytics_usage` not defined.

- [ ] **Step 11: Implement fetch_pikalytics_usage**

Add to `pipeline/fetch_pikalytics.py`:

```python
def fetch_pikalytics_usage(display_name: str, session=None) -> dict:
    """Fetch and parse one species' usage page.

    Returns the parsed usage dict, or None if Pikalytics has no page for
    this species (HTTP 404) -- an expected outcome for a fringe pick, not
    a failure. Raises PikalyticsFetchError on a network error or any other
    non-200 status.
    """
    session = session or requests.Session()
    slug = resolve_pikalytics_slug(display_name)
    url = f"{PIKALYTICS_AI_BASE_URL}/{PIKALYTICS_FORMAT_CODE}/{slug}"
    try:
        response = session.get(url)
    except requests.exceptions.RequestException as e:
        raise PikalyticsFetchError(f"Network error fetching '{display_name}' (slug '{slug}'): {e}") from e
    if response.status_code == 404:
        return None
    if response.status_code != 200:
        raise PikalyticsFetchError(f"Pikalytics returned {response.status_code} for '{display_name}' (slug '{slug}')")
    return parse_usage_markdown(response.text)
```

- [ ] **Step 12: Run tests to verify they pass**

Run: `pytest tests/test_fetch_pikalytics.py -v`
Expected: PASS (14 passed)

- [ ] **Step 13: Write failing tests for fetch_all_usage**

Add to `tests/test_fetch_pikalytics.py`:

```python
def test_fetch_all_usage_writes_cache_and_builds_usage_dict(tmp_path):
    session = _mock_session(200, text=_SAMPLE_MARKDOWN)

    result = fetch_all_usage(["Garchomp"], cache_dir=tmp_path, session=session, delay_seconds=0)

    assert result["fetched"] == 1
    assert result["cached"] == 0
    assert result["failed"] == []
    assert result["usage_by_species"]["Garchomp"]["moves"][0]["name"] == "Dragon Claw"
    assert (tmp_path / simple_cache_filename("Garchomp")).exists()


def test_fetch_all_usage_skips_already_cached_files(tmp_path):
    cache_file = tmp_path / simple_cache_filename("Garchomp")
    cache_file.write_text(json.dumps({"moves": [], "items": [], "abilities": []}))
    session = _mock_session(200, text=_SAMPLE_MARKDOWN)

    result = fetch_all_usage(["Garchomp"], cache_dir=tmp_path, session=session, delay_seconds=0)

    assert result["cached"] == 1
    assert result["fetched"] == 0
    session.get.assert_not_called()
    assert result["usage_by_species"]["Garchomp"] == {"moves": [], "items": [], "abilities": []}


def test_fetch_all_usage_caches_none_for_a_species_with_no_data(tmp_path):
    session = _mock_session(404, text="Pokemon not found")

    result = fetch_all_usage(["Nonexistamon"], cache_dir=tmp_path, session=session, delay_seconds=0)

    assert result["fetched"] == 1
    assert "Nonexistamon" not in result["usage_by_species"]
    cache_file = tmp_path / simple_cache_filename("Nonexistamon")
    assert cache_file.exists()
    assert json.loads(cache_file.read_text()) is None


def test_fetch_all_usage_does_not_refetch_a_cached_none(tmp_path):
    cache_file = tmp_path / simple_cache_filename("Nonexistamon")
    cache_file.write_text("null")
    session = _mock_session(200, text=_SAMPLE_MARKDOWN)

    result = fetch_all_usage(["Nonexistamon"], cache_dir=tmp_path, session=session, delay_seconds=0)

    assert result["cached"] == 1
    assert "Nonexistamon" not in result["usage_by_species"]
    session.get.assert_not_called()


def test_fetch_all_usage_continues_after_one_failure(tmp_path):
    session = MagicMock()
    ok_response = MagicMock(status_code=200, text=_SAMPLE_MARKDOWN)
    session.get.side_effect = [requests.exceptions.ConnectionError("refused"), ok_response]

    result = fetch_all_usage(["Broken", "Garchomp"], cache_dir=tmp_path, session=session, delay_seconds=0)

    assert result["failed"] == ["Broken"]
    assert "Garchomp" in result["usage_by_species"]
```

- [ ] **Step 14: Run tests to verify they fail**

Run: `pytest tests/test_fetch_pikalytics.py -v`
Expected: FAIL — `fetch_all_usage` not defined.

- [ ] **Step 15: Implement fetch_all_usage**

Add to `pipeline/fetch_pikalytics.py`:

```python
def fetch_all_usage(legal_names: list, cache_dir, session=None, delay_seconds: float = 0.5) -> dict:
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    session = session or requests.Session()

    usage_by_species = {}
    fetched, cached, failed = 0, 0, []
    for name in legal_names:
        cache_file = cache_dir / simple_cache_filename(name)
        if cache_file.exists():
            with open(cache_file) as f:
                data = json.load(f)
            cached += 1
        else:
            try:
                data = fetch_pikalytics_usage(name, session=session)
            except PikalyticsFetchError:
                failed.append(name)
                continue
            with open(cache_file, "w") as f:
                json.dump(data, f, indent=2)
            fetched += 1
            if delay_seconds:
                time.sleep(delay_seconds)
        if data is not None:
            usage_by_species[name] = data

    return {"usage_by_species": usage_by_species, "fetched": fetched, "cached": cached, "failed": failed}
```

- [ ] **Step 16: Run tests to verify they pass**

Run: `pytest tests/test_fetch_pikalytics.py -v`
Expected: PASS (19 passed)

- [ ] **Step 17: Run the full suite and commit**

Run: `pytest -q`
Expected: all pre-existing tests plus the 19 new ones pass, no other file changed.

```bash
git add pipeline/fetch_pikalytics.py tests/test_fetch_pikalytics.py
git commit -m "feat(pipeline): add Pikalytics usage data fetch + parse module"
```

---

### Task 2: Pikalytics refresh job entrypoint

**Files:**
- Create: `pipeline/refresh_pikalytics_job.py`
- Test: `tests/test_refresh_pikalytics_job.py`

**Interfaces:**
- Consumes: `pipeline.build_records.find_legal_pokemon_file(source_dir) -> Path` (existing, already tested); `pipeline.fetch_pikalytics.fetch_all_usage(...)` (Task 1).
- Produces: `run_pikalytics_refresh(source_dir, cache_dir, output_path, session=None) -> dict` (returns `fetch_all_usage`'s result dict plus a `"species_with_data"` key).

- [ ] **Step 1: Write a failing test for run_pikalytics_refresh**

Create `tests/test_refresh_pikalytics_job.py`:

```python
import json
from unittest.mock import MagicMock

from pipeline.refresh_pikalytics_job import run_pikalytics_refresh

_SAMPLE_MARKDOWN = """\
## Common Moves
- **Dragon Claw**: 89.4%
- **Earthquake**: 80.7%

## Common Abilities
- **Rough Skin**: 98.5%

## Common Items
- **Life Orb**: 51.5%
"""


def test_run_pikalytics_refresh_finds_legal_file_and_writes_output(tmp_path):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "legal_pokemon_m-b.json").write_text(json.dumps({
        "regulation": "M-B", "count": 1, "legal_pokemon": ["Garchomp"],
    }))
    cache_dir = tmp_path / "raw_pikalytics"
    output_path = tmp_path / "processed" / "pikalytics_usage.json"

    session = MagicMock()
    session.get.return_value = MagicMock(status_code=200, text=_SAMPLE_MARKDOWN)

    result = run_pikalytics_refresh(source_dir, cache_dir, output_path, session=session)

    assert result["fetched"] == 1
    assert result["species_with_data"] == 1
    written = json.loads(output_path.read_text())
    assert written["Garchomp"]["moves"][0]["name"] == "Dragon Claw"


def test_run_pikalytics_refresh_counts_species_with_no_data(tmp_path):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "legal_pokemon_m-b.json").write_text(json.dumps({
        "regulation": "M-B", "count": 1, "legal_pokemon": ["Nonexistamon"],
    }))
    cache_dir = tmp_path / "raw_pikalytics"
    output_path = tmp_path / "processed" / "pikalytics_usage.json"

    session = MagicMock()
    session.get.return_value = MagicMock(status_code=404, text="Pokemon not found")

    result = run_pikalytics_refresh(source_dir, cache_dir, output_path, session=session)

    assert result["species_with_data"] == 0
    written = json.loads(output_path.read_text())
    assert written == {}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_refresh_pikalytics_job.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pipeline.refresh_pikalytics_job'`

- [ ] **Step 3: Implement run_pikalytics_refresh**

Create `pipeline/refresh_pikalytics_job.py`:

```python
import json
from pathlib import Path

from pipeline.build_records import find_legal_pokemon_file
from pipeline.fetch_pikalytics import fetch_all_usage


def run_pikalytics_refresh(source_dir, cache_dir, output_path, session=None) -> dict:
    source_dir = Path(source_dir)
    output_path = Path(output_path)

    with open(find_legal_pokemon_file(source_dir)) as f:
        legal_data = json.load(f)
    legal_names = legal_data["legal_pokemon"]

    result = fetch_all_usage(legal_names, cache_dir=cache_dir, session=session)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(result["usage_by_species"], f, indent=2)

    result["species_with_data"] = len(result["usage_by_species"])
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_refresh_pikalytics_job.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Run the full suite and commit**

Run: `pytest -q`
Expected: all pre-existing tests plus the new ones pass.

```bash
git add pipeline/refresh_pikalytics_job.py tests/test_refresh_pikalytics_job.py
git commit -m "feat(pipeline): add Pikalytics usage data refresh job entrypoint"
```

---

### Task 3: Feed usage data into /stats and /moves

**Files:**
- Modify: `bot/commands/stats.py`
- Modify: `bot/commands/moves.py`
- Modify: `bot/main.py`
- Test: `tests/test_bot_stats.py` (existing)
- Test: `tests/test_bot_moves.py` (existing)
- Test: `tests/test_bot_main.py` (existing)

**Interfaces:**
- Consumes: nothing new from Tasks 1-2 at runtime (this task reads the already-written `data/processed/pikalytics_usage.json`, produced by Task 2's job, not by calling pipeline code directly).
- Produces (modified): `stats_response(records: list, name: str, usage: dict = None) -> str`; `moves_response(records: list, name: str, usage: dict = None) -> str`; `build_client(..., usage: dict = None)` gains the parameter and threads it into the `stats`/`moves` command bodies.

- [ ] **Step 1: Read the current stats.py, moves.py, and the relevant part of main.py**

Run: `cat bot/commands/stats.py bot/commands/moves.py` and look at `bot/main.py`'s `build_client` signature (`bot/main.py:47`) and the `stats`/`moves_command` command bodies (`bot/main.py:73`, `bot/main.py:78`, as of this plan's writing — confirm the exact current line numbers before editing, in case anything shifts them between now and when this task runs).

- [ ] **Step 2: Write failing tests for stats_response's usage argument**

Add to `tests/test_bot_stats.py` (existing file — keep its current fixtures and tests):

```python
def test_stats_response_appends_common_build_when_usage_data_exists():
    usage = {"Abomasnow": {
        "moves": [], "abilities": [{"name": "Snow Warning", "usage_pct": 98.5}],
        "items": [{"name": "Focus Sash", "usage_pct": 40.0}],
    }}

    response = stats_response(_RECORDS, "Abomasnow", usage=usage)

    assert "Common build" in response
    assert "40.0% Focus Sash" in response
    assert "98.5% Snow Warning" in response


def test_stats_response_omits_common_build_when_no_usage_data():
    response = stats_response(_RECORDS, "Abomasnow", usage={})

    assert "Common build" not in response


def test_stats_response_usage_defaults_to_none_and_behaves_like_before():
    with_default = stats_response(_RECORDS, "Abomasnow")
    with_explicit_none = stats_response(_RECORDS, "Abomasnow", usage=None)

    assert with_default == with_explicit_none
    assert "Common build" not in with_default
```

(`_RECORDS` and `_ABOMASNOW` are the existing fixtures already defined in this test file — confirmed to contain an `"Abomasnow"` entry with `"abilities": ["Snow Warning", "Soundproof"]` and `"learnset": ["Blizzard", "Wood Hammer"]`.)

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_bot_stats.py -v`
Expected: FAIL with `TypeError: stats_response() got an unexpected keyword argument 'usage'`

- [ ] **Step 4: Implement stats_response's usage argument**

Modify `bot/commands/stats.py`:

```python
from bot.pokemon_lookup import find_record, not_found_message


def stats_response(records: list, name: str, usage: dict = None) -> str:
    record = find_record(records, name)
    if record is None:
        return not_found_message(records, name)

    types = "/".join(record["types"])
    stats = record["base_stats"]
    abilities = ", ".join(record["abilities"])
    response = (
        f"{record['name']} ({types}) — "
        f"HP {stats['hp']} / Atk {stats['attack']} / Def {stats['defense']} / "
        f"SpA {stats['sp_attack']} / SpD {stats['sp_defense']} / Spe {stats['speed']}. "
        f"Abilities: {abilities}."
    )

    species_usage = (usage or {}).get(record["name"])
    if species_usage:
        build_parts = []
        if species_usage.get("items"):
            top_item = species_usage["items"][0]
            build_parts.append(f"{top_item['usage_pct']}% {top_item['name']}")
        if species_usage.get("abilities"):
            top_ability = species_usage["abilities"][0]
            build_parts.append(f"{top_ability['usage_pct']}% {top_ability['name']}")
        if build_parts:
            response += f" Common build: {', '.join(build_parts)}."

    return response
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_bot_stats.py -v`
Expected: PASS (all tests in the file, including the pre-existing ones)

- [ ] **Step 6: Write failing tests for moves_response's usage argument**

Add to `tests/test_bot_moves.py` (existing file — keep its current fixtures and tests; `_RECORDS = [_ABOMASNOW]` is already confirmed to contain `"Abomasnow"` with `"learnset": ["Blizzard", "Wood Hammer"]`):

```python
def test_moves_response_shows_top_moves_when_usage_data_exists():
    usage = {"Abomasnow": {
        "moves": [{"name": "Blizzard", "usage_pct": 91.2}, {"name": "Wood Hammer", "usage_pct": 84.0}],
        "abilities": [], "items": [],
    }}

    response = moves_response(_RECORDS, "Abomasnow", usage=usage)

    assert "top moves" in response.lower()
    assert "Blizzard 91.2%" in response
    assert "Wood Hammer 84.0%" in response


def test_moves_response_falls_back_to_full_learnset_when_no_usage_data():
    response = moves_response(_RECORDS, "Abomasnow", usage={})

    assert "legal moveset" in response.lower()


def test_moves_response_falls_back_when_usage_entry_has_no_moves():
    usage = {"Abomasnow": {"moves": [], "abilities": [], "items": []}}

    response = moves_response(_RECORDS, "Abomasnow", usage=usage)

    assert "legal moveset" in response.lower()


def test_moves_response_usage_defaults_to_none_and_behaves_like_before():
    with_default = moves_response(_RECORDS, "Abomasnow")
    with_explicit_none = moves_response(_RECORDS, "Abomasnow", usage=None)

    assert with_default == with_explicit_none
    assert "legal moveset" in with_default.lower()
```

- [ ] **Step 7: Run tests to verify they fail**

Run: `pytest tests/test_bot_moves.py -v`
Expected: FAIL with `TypeError: moves_response() got an unexpected keyword argument 'usage'`

- [ ] **Step 8: Implement moves_response's usage argument**

Modify `bot/commands/moves.py`:

```python
from bot.pokemon_lookup import find_record, not_found_message


def moves_response(records: list, name: str, usage: dict = None) -> str:
    record = find_record(records, name)
    if record is None:
        return not_found_message(records, name)

    species_usage = (usage or {}).get(record["name"])
    top_moves = species_usage.get("moves") if species_usage else None
    if top_moves:
        moves_text = ", ".join(f"{m['name']} {m['usage_pct']}%" for m in top_moves)
        return f"{record['name']}'s top moves (by usage): {moves_text}."

    moves = ", ".join(record["learnset"])
    return f"{record['name']}'s legal moveset: {moves}."
```

- [ ] **Step 9: Run tests to verify they pass**

Run: `pytest tests/test_bot_moves.py -v`
Expected: PASS (all tests in the file, including the pre-existing ones)

- [ ] **Step 10: Write failing tests for build_client's usage wiring**

Add to `tests/test_bot_main.py` (existing file — keep its current imports/tests):

```python
def test_stats_command_uses_usage_data_when_provided():
    records = [{
        "name": "Abomasnow", "types": ["Grass", "Ice"],
        "base_stats": {"hp": 90, "attack": 92, "defense": 75, "sp_attack": 92, "sp_defense": 85, "speed": 60},
        "abilities": ["Snow Warning"], "learnset": ["Blizzard"], "legal_in": ["M-B"],
    }]
    usage = {"Abomasnow": {
        "moves": [], "abilities": [{"name": "Snow Warning", "usage_pct": 98.5}],
        "items": [{"name": "Focus Sash", "usage_pct": 40.0}],
    }}

    _client, tree = build_client(records=records, usage=usage)
    stats_cmd = tree.get_command("stats")
    interaction = MagicMock()
    interaction.user.id = 1
    interaction.response.send_message = AsyncMock()

    asyncio.run(stats_cmd.callback(interaction, name="Abomasnow"))

    sent_text = _extract_text(interaction.response.send_message)
    assert "Common build" in sent_text


def test_moves_command_uses_usage_data_when_provided():
    records = [{
        "name": "Abomasnow", "types": ["Grass", "Ice"],
        "base_stats": {"hp": 90, "attack": 92, "defense": 75, "sp_attack": 92, "sp_defense": 85, "speed": 60},
        "abilities": ["Snow Warning"], "learnset": ["Blizzard"], "legal_in": ["M-B"],
    }]
    usage = {"Abomasnow": {
        "moves": [{"name": "Blizzard", "usage_pct": 91.2}], "abilities": [], "items": [],
    }}

    _client, tree = build_client(records=records, usage=usage)
    moves_cmd = tree.get_command("moves")
    interaction = MagicMock()
    interaction.user.id = 1
    interaction.response.send_message = AsyncMock()

    asyncio.run(moves_cmd.callback(interaction, name="Abomasnow"))

    sent_text = _extract_text(interaction.response.send_message)
    assert "top moves" in sent_text.lower()
```

(`_extract_text` is the existing helper already defined at the top of this test file, extracting a sent message's embed description.)

- [ ] **Step 11: Run tests to verify they fail**

Run: `pytest tests/test_bot_main.py -v -k "usage"`
Expected: FAIL with `TypeError: build_client() got an unexpected keyword argument 'usage'`

- [ ] **Step 12: Wire usage into build_client, stats, and moves**

In `bot/main.py`, add `usage=None` to `build_client`'s parameter list (alongside `index`, `answerer`, `records`, `moves`):

```python
def build_client(
    index=None, answerer=None, records=None, moves=None, usage=None
) -> tuple[discord.Client, app_commands.CommandTree]:
```

Then update the `stats` and `moves_command` bodies to pass it through:

```python
    @tree.command(name="stats", description="Look up a Pokemon's base stats, types, and abilities.")
    @app_commands.checks.cooldown(1, _COOLDOWN_SECONDS)
    async def stats(interaction: discord.Interaction, name: str) -> None:
        await interaction.response.send_message(embed=_embed("stats", stats_response(records, name, usage=usage)))

    @tree.command(name="moves", description="Look up a Pokemon's legal moveset.")
    @app_commands.checks.cooldown(1, _COOLDOWN_SECONDS)
    async def moves_command(interaction: discord.Interaction, name: str) -> None:
        await interaction.response.send_message(embed=_embed("moves", moves_response(records, name, usage=usage)))
```

- [ ] **Step 13: Run tests to verify they pass**

Run: `pytest tests/test_bot_main.py -v`
Expected: PASS (all tests in the file)

- [ ] **Step 14: Wire usage loading into main()**

In `bot/main.py`, add a `_load_usage()` helper alongside `_load_records()`/`_load_moves()`:

```python
USAGE_DATA_PATH = Path("data/processed/pikalytics_usage.json")


def _load_usage() -> dict:
    if not USAGE_DATA_PATH.exists():
        return {}
    return json.loads(USAGE_DATA_PATH.read_text())
```

Then update `main()` to load and pass it:

```python
def main() -> None:
    token = os.environ["DISCORD_TOKEN"]
    records = _load_records()
    client, _tree = build_client(
        index=_build_real_index(records),
        answerer=HaikuAnswerer(),
        records=records,
        moves=_load_moves(),
        usage=_load_usage(),
    )
    client.run(token)
```

`_load_usage()` returning `{}` when the file doesn't exist yet means the bot runs identically to before this feature until someone actually runs the Pikalytics refresh job (Task 2) — no crash, no behavior change, matching the "backward compatible" constraint.

- [ ] **Step 15: Run the full suite and commit**

Run: `pytest -q`
Expected: every pre-existing test plus every new test in this task passes. Specifically confirm `tests/test_bot_calc.py`, `tests/test_team_store.py`, `tests/test_bot_team.py`, and `tests/test_pokepaste*.py` all still pass unmodified — proof this task didn't touch `/calc`/`/import`/`/scout`/`/team`.

```bash
git add bot/commands/stats.py bot/commands/moves.py bot/main.py tests/test_bot_stats.py tests/test_bot_moves.py tests/test_bot_main.py
git commit -m "feat(bot): feed Pikalytics usage data into /stats and /moves"
```

---

### Task 4: Run the real pipeline and verify end to end

**Files:**
- Create: `data/raw_pikalytics/*.json` (315 cache files, one per legal Pokemon — mirrors the existing checked-in `data/raw/*.json` PokeAPI cache convention)
- Create: `data/processed/pikalytics_usage.json`

**Interfaces:**
- Consumes: `pipeline.refresh_pikalytics_job.run_pikalytics_refresh(...)` (Task 2).
- Produces: nothing new for later tasks — this is the plan's final verification task.

- [ ] **Step 1: Run the real refresh job against the full legal roster**

Run:

```bash
python3 -m pipeline.refresh_pikalytics_job
```

Expected: takes a few minutes (315 species, ~0.5s delay between live fetches). Prints a summary line like `fetched=315 cached=0 failed=0 species_with_data=<N>` where `<N>` is somewhat less than 315 (not every legal Pokemon has Pikalytics usage data — that's expected, not a bug). If `failed` is non-empty, re-run the command (already-cached species are skipped on the second pass, so only the genuinely-failed ones retry) — a transient network error is more likely than a real bug at this stage, since Task 1's tests already prove the fetch/parse/cache logic works correctly in isolation.

- [ ] **Step 2: Spot-check the output**

Run:

```bash
python3 -c "
import json
usage = json.loads(open('data/processed/pikalytics_usage.json').read())
print(len(usage), 'species with usage data')
print(json.dumps(usage.get('Garchomp'), indent=2))
"
```

Confirm: a reasonable count (expect somewhere in the low hundreds, not 0 and not 315), and Garchomp's entry (or another well-known meta staple if Garchomp isn't legal in the current regulation) shows real moves/items/abilities with sane-looking percentages.

- [ ] **Step 3: Manual end-to-end smoke test through the real bot commands**

Run:

```bash
python3 -c "
import json, asyncio
from unittest.mock import AsyncMock, MagicMock
from bot.main import build_client

records = json.loads(open('data/processed/pokemon_records.json').read())
moves = json.loads(open('data/source/vgc_moves.json').read())['moves']
usage = json.loads(open('data/processed/pikalytics_usage.json').read())
client, tree = build_client(records=records, moves=moves, usage=usage)

def run(cmd_name, **kwargs):
    interaction = MagicMock()
    interaction.user.id = 1
    interaction.response.send_message = AsyncMock()
    asyncio.run(tree.get_command(cmd_name).callback(interaction, **kwargs))
    return interaction.response.send_message.call_args.kwargs['embed'].description

species_with_data = next(iter(usage))
print(run('stats', name=species_with_data))
print(run('moves', name=species_with_data))
print(run('stats', name='Nonexistamon'))
"
```

Confirm: the first two lines show real usage-augmented output (a "Common build" line on `/stats`, "top moves (by usage)" on `/moves`) for a species that actually has Pikalytics data; the third line still shows the existing "not recognized" behavior unaffected.

- [ ] **Step 4: Commit the real data**

```bash
git add data/raw_pikalytics/ data/processed/pikalytics_usage.json
git commit -m "data: first real Pikalytics usage data pipeline run"
```

---

## Self-Review Notes

- **Spec coverage:** confirmed page format and parsing (Task 1), URL slug reuse of `resolve_pokeapi_name` (Task 1), fetch/cache/politeness behavior including `None`-caching for 404s (Task 1), refresh job entrypoint mirroring `refresh_job.py`'s pattern (Task 2), `/stats`/`/moves` augmentation with backward-compatible fallback (Task 3), isolation from `/calc`/`/import`/`/scout`/`/team` proven by the full suite passing unmodified (Task 3 Step 15), and a real end-to-end pipeline run (Task 4) — all covered.
- **Placeholder scan:** every step has literal, runnable code. (The one non-literal line in Task 1 Step 1 is explicitly flagged as "do not include" scaffolding to prevent a copy-paste mistake, not a placeholder left for the implementer to fill in.)
- **Type consistency:** the usage-record shape (`moves`/`items`/`abilities`, each a list of `{"name", "usage_pct"}` dicts) is used identically across Task 1's parser, Task 2's refresh-job tests, and Task 3's `stats_response`/`moves_response` tests — checked field-by-field while writing this plan.
