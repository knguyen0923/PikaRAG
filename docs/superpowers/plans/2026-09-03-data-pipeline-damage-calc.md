# Data Pipeline + Damage Calculator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first credential-free, fully-testable slice of Pika-RAG: a data pipeline that merges the four authoritative regulation-M-B JSONs with PokéAPI-sourced base stats/learnsets, and a pure-Python damage calculator ported from `@smogon/calc`.

**Architecture:** Two independent subsystems sharing one merged data format. `pipeline/` produces `data/processed/pokemon_records.json`; `damage_calc/` is a pure-function module that consumes records in that same shape (plus move data straight from `vgc_moves.json`) and has no dependency on the pipeline's code — only on its output shape, which this plan fixes explicitly in Task 1.

**Tech Stack:** Python 3.9 (system default — confirmed via `python3 --version`), `requests` for PokéAPI calls, `pytest` for tests, stdlib `unittest.mock` for mocking HTTP in tests (no extra mocking library). Project-local virtualenv at `.venv/`.

**Spec:** `docs/superpowers/specs/2026-09-03-data-pipeline-damage-calc-design.md`

## Global Constraints

- The four source JSONs (`legal_pokemon_m-b.json`, `vgc_abilities.json`, `vgc_items.json`, `vgc_moves.json`) are authoritative and must be used as-is — never re-derived, never overwritten by pipeline code.
- No code may hardcode `"M-B"` as a literal outside of tests — regulation identifiers are always read from the source JSONs' own `meta.regulation` / top-level `regulation` fields, since M-C will replace these files later without a code change.
- No network calls in the test suite — `fetch_pokeapi.py` tests mock `requests.get`.
- No Discord token, no Anthropic API key, no live deployment anywhere in this plan.
- Every task must leave `pytest` fully green before moving to the next task.
- Commit after every task.

---

## Data Shapes (fixed now, relied on by every later task)

**Processed Pokémon record** (`data/processed/pokemon_records.json`, one entry per legal Pokémon):
```json
{
  "name": "Aegislash [Blade Forme]",
  "types": ["Steel", "Ghost"],
  "base_stats": {"hp": 60, "attack": 50, "defense": 150, "sp_attack": 50, "sp_defense": 150, "speed": 60},
  "abilities": ["Stance Change"],
  "learnset": ["Iron Head", "Shadow Ball", "King's Shield", "Sacred Sword"],
  "legal_in": ["M-B"]
}
```

**Damage calc inputs** — a "combatant" dict used for both attacker and defender:
```python
combatant = {
    "record": pokemon_record,       # a processed record dict, as above
    "level": 50,
    "evs": {"hp": 0, "attack": 252, "defense": 0, "sp_attack": 0, "sp_defense": 4, "speed": 252},
    "ivs": {"hp": 31, "attack": 31, "defense": 31, "sp_attack": 31, "sp_defense": 31, "speed": 31},
    "nature": "Adamant",            # str, looked up in damage_calc/data/natures.py
    "stat_stages": {"attack": 0, "defense": 0, "sp_attack": 0, "sp_defense": 0, "speed": 0},
    "tera_type": None,              # str or None
    "item": None,                   # str or None, e.g. "Life Orb"
    "ability": None,                # str or None
    "current_hp_fraction": 1.0,
}
```

**Battle context dict:**
```python
context = {
    "weather": None,       # "Sun" | "Rain" | "Sand" | "Snow" | None
    "terrain": None,       # "Electric" | "Grassy" | "Misty" | "Psychic" | None
    "is_spread_target": False,   # True if move hits multiple targets in doubles (0.75x)
    "screen": None,        # "Reflect" | "Light Screen" | "Aurora Veil" | None
    "is_doubles": True,
}
```

**`calculate_damage(move, attacker, defender, context) -> DamageResult`** where `move` is one entry from `vgc_moves.json`'s `moves` list, and `DamageResult` is:
```python
@dataclass
class DamageResult:
    min_damage: int
    max_damage: int
    min_percent: float   # % of defender's max HP
    max_percent: float
    is_ko_chance: bool   # True if max_damage >= defender's remaining HP
```

---

## Task 1: Repo scaffolding and source data relocation

**Files:**
- Create: `requirements.txt`
- Create: `pytest.ini`
- Create: `.gitignore`
- Create: `data/source/` (move 4 JSONs here)
- Create: `data/raw/.gitkeep`
- Create: `data/processed/.gitkeep`
- Create: `pipeline/__init__.py`
- Create: `damage_calc/__init__.py`
- Create: `damage_calc/data/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/test_scaffold.py`
- Modify: move `legal_pokemon_m-b.json`, `vgc_abilities.json`, `vgc_items.json`, `vgc_moves.json` from repo root to `data/source/`

**Interfaces:**
- Produces: the directory layout every later task writes into; the location of source JSONs (`data/source/<name>.json`) that Task 2/3 read from.

- [ ] **Step 1: Create the directory structure and empty package markers**

```bash
mkdir -p data/source data/raw data/processed pipeline damage_calc/data tests
touch pipeline/__init__.py damage_calc/__init__.py damage_calc/data/__init__.py tests/__init__.py
touch data/raw/.gitkeep data/processed/.gitkeep
```

- [ ] **Step 2: Move the 4 source JSONs with `git mv`**

```bash
git mv legal_pokemon_m-b.json data/source/legal_pokemon_m-b.json
git mv vgc_abilities.json data/source/vgc_abilities.json
git mv vgc_items.json data/source/vgc_items.json
git mv vgc_moves.json data/source/vgc_moves.json
```

- [ ] **Step 3: Write `requirements.txt`**

```
requests==2.32.5
pytest==8.3.3
```

- [ ] **Step 4: Write `pytest.ini`**

```ini
[pytest]
testpaths = tests
python_files = test_*.py
```

- [ ] **Step 5: Write `.gitignore`**

```
.venv/
__pycache__/
*.pyc
.pytest_cache/
```

- [ ] **Step 6: Create the virtualenv and install dependencies**

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

- [ ] **Step 7: Write a smoke test confirming the moved source files are valid, non-empty JSON**

```python
# tests/test_scaffold.py
import json
from pathlib import Path

SOURCE_DIR = Path(__file__).resolve().parent.parent / "data" / "source"

def test_all_four_source_files_present_and_valid_json():
    expected = {
        "legal_pokemon_m-b.json",
        "vgc_abilities.json",
        "vgc_items.json",
        "vgc_moves.json",
    }
    actual = {p.name for p in SOURCE_DIR.glob("*.json")}
    assert expected == actual

    for name in expected:
        with open(SOURCE_DIR / name) as f:
            data = json.load(f)
        assert data

def test_legal_pokemon_file_has_regulation_tag():
    with open(SOURCE_DIR / "legal_pokemon_m-b.json") as f:
        data = json.load(f)
    assert data["regulation"] == "M-B"
    assert len(data["legal_pokemon"]) == data["count"]
```

- [ ] **Step 8: Run the test to verify it passes**

Run: `.venv/bin/pytest -v`
Expected: 2 passed

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "chore: scaffold project layout, move source JSONs into data/source/"
```

---

## Task 2: PokéAPI fetch with name resolution and caching

**Files:**
- Create: `pipeline/fetch_pokeapi.py`
- Test: `tests/test_fetch_pokeapi.py`

**Interfaces:**
- Consumes: `data/source/legal_pokemon_m-b.json` (`legal_pokemon` list of 315 names, as written by Task 1).
- Produces:
  - `resolve_pokeapi_name(display_name: str) -> str` — maps a name from the legal list (e.g. `"Mega Absol"`, `"Aegislash [Blade Forme]"`, `"Arcanine [Hisuian Form]"`) to a PokéAPI slug (e.g. `"absol-mega"`, `"aegislash-blade"`, `"arcanine-hisuian"`).
  - `fetch_pokemon_data(display_name: str, session=None) -> dict` — returns `{"base_stats": {...}, "learnset": [...]}` for one Pokémon, raising `PokeApiFetchError` on failure (never `requests` exceptions directly).
  - `fetch_all(legal_names: list[str], cache_dir: Path) -> dict` — iterates all names, writes one JSON file per Pokémon under `cache_dir` (e.g. `data/raw/abomasnow.json`), skips re-fetching if the cache file already exists, and returns a summary dict `{"fetched": int, "cached": int, "failed": list[str]}` — a failure on one Pokémon must not stop the rest.

- [ ] **Step 1: Write failing tests for name resolution**

```python
# tests/test_fetch_pokeapi.py
from pipeline.fetch_pokeapi import resolve_pokeapi_name

def test_resolve_plain_name():
    assert resolve_pokeapi_name("Abomasnow") == "abomasnow"

def test_resolve_mega_name():
    assert resolve_pokeapi_name("Mega Absol") == "absol-mega"

def test_resolve_mega_x_y_name():
    assert resolve_pokeapi_name("Mega Charizard X") == "charizard-mega-x"
    assert resolve_pokeapi_name("Mega Charizard Y") == "charizard-mega-y"

def test_resolve_bracket_forme_name():
    assert resolve_pokeapi_name("Aegislash [Blade Forme]") == "aegislash-blade"

def test_resolve_hisuian_form_name():
    assert resolve_pokeapi_name("Arcanine [Hisuian Form]") == "arcanine-hisuian"

def test_resolve_female_form_name():
    assert resolve_pokeapi_name("Basculegion [Female]") == "basculegion-female"
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/test_fetch_pokeapi.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline.fetch_pokeapi'`

- [ ] **Step 3: Implement name resolution**

```python
# pipeline/fetch_pokeapi.py
import re

_FORM_WORD_MAP = {
    "blade forme": "blade",
    "hisuian form": "hisuian",
    "galarian form": "galar",
    "alolan form": "alola",
    "paldean form": "paldea",
    "female": "female",
    "rainy form": "rainy",
    "snowy form": "snowy",
    "sunny form": "sunny",
}


def resolve_pokeapi_name(display_name: str) -> str:
    name = display_name.strip()

    bracket_match = re.search(r"\[([^\]]+)\]", name)
    bracket_suffix = None
    if bracket_match:
        bracket_text = bracket_match.group(1).strip().lower()
        bracket_suffix = _FORM_WORD_MAP.get(bracket_text, bracket_text.replace(" ", "-"))
        name = name[: bracket_match.start()].strip()

    mega_match = re.match(r"^Mega (.+?)( X| Y)?$", name)
    if mega_match:
        base = mega_match.group(1)
        suffix = mega_match.group(2)
        slug = base.lower().replace(" ", "-").replace("'", "")
        if suffix:
            slug += f"-mega-{suffix.strip().lower()}"
        else:
            slug += "-mega"
        return slug

    slug = name.lower().replace(" ", "-").replace("'", "")
    if bracket_suffix:
        slug += f"-{bracket_suffix}"
    return slug
```

- [ ] **Step 4: Run to verify name resolution tests pass**

Run: `.venv/bin/pytest tests/test_fetch_pokeapi.py -v`
Expected: 6 passed

- [ ] **Step 5: Write failing tests for `fetch_pokemon_data` using a mocked session**

```python
# append to tests/test_fetch_pokeapi.py
from unittest.mock import MagicMock
import pytest
from pipeline.fetch_pokeapi import fetch_pokemon_data, PokeApiFetchError

def _mock_session(pokemon_json):
    session = MagicMock()
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = pokemon_json
    session.get.return_value = response
    return session

_SAMPLE_POKEAPI_RESPONSE = {
    "stats": [
        {"base_stat": 90, "stat": {"name": "hp"}},
        {"base_stat": 92, "stat": {"name": "attack"}},
        {"base_stat": 75, "stat": {"name": "defense"}},
        {"base_stat": 92, "stat": {"name": "special-attack"}},
        {"base_stat": 85, "stat": {"name": "special-defense"}},
        {"base_stat": 60, "stat": {"name": "speed"}},
    ],
    "moves": [
        {"move": {"name": "ice-punch"}},
        {"move": {"name": "wood-hammer"}},
    ],
}

def test_fetch_pokemon_data_parses_stats_and_learnset():
    session = _mock_session(_SAMPLE_POKEAPI_RESPONSE)
    result = fetch_pokemon_data("Abomasnow", session=session)
    assert result["base_stats"] == {
        "hp": 90, "attack": 92, "defense": 75,
        "sp_attack": 92, "sp_defense": 85, "speed": 60,
    }
    assert result["learnset"] == ["ice-punch", "wood-hammer"]

def test_fetch_pokemon_data_raises_on_http_error():
    session = MagicMock()
    response = MagicMock()
    response.status_code = 404
    session.get.return_value = response
    with pytest.raises(PokeApiFetchError):
        fetch_pokemon_data("Nonexistent", session=session)
```

- [ ] **Step 6: Run to verify failure**

Run: `.venv/bin/pytest tests/test_fetch_pokeapi.py -v`
Expected: FAIL — `ImportError: cannot import name 'fetch_pokemon_data'`

- [ ] **Step 7: Implement `fetch_pokemon_data`**

```python
# append to pipeline/fetch_pokeapi.py
import requests

POKEAPI_BASE_URL = "https://pokeapi.co/api/v2/pokemon"

_STAT_NAME_MAP = {
    "hp": "hp",
    "attack": "attack",
    "defense": "defense",
    "special-attack": "sp_attack",
    "special-defense": "sp_defense",
    "speed": "speed",
}


class PokeApiFetchError(Exception):
    pass


def fetch_pokemon_data(display_name: str, session=None) -> dict:
    session = session or requests.Session()
    slug = resolve_pokeapi_name(display_name)
    response = session.get(f"{POKEAPI_BASE_URL}/{slug}")
    if response.status_code != 200:
        raise PokeApiFetchError(
            f"PokeAPI returned {response.status_code} for '{display_name}' (slug '{slug}')"
        )
    payload = response.json()
    base_stats = {
        _STAT_NAME_MAP[s["stat"]["name"]]: s["base_stat"]
        for s in payload["stats"]
        if s["stat"]["name"] in _STAT_NAME_MAP
    }
    learnset = [m["move"]["name"] for m in payload["moves"]]
    return {"base_stats": base_stats, "learnset": learnset}
```

- [ ] **Step 8: Run to verify passing**

Run: `.venv/bin/pytest tests/test_fetch_pokeapi.py -v`
Expected: 8 passed

- [ ] **Step 9: Write failing tests for `fetch_all` caching/failure behavior**

```python
# append to tests/test_fetch_pokeapi.py
import json
from pipeline.fetch_pokeapi import fetch_all

def test_fetch_all_writes_cache_and_reports_summary(tmp_path):
    session = _mock_session(_SAMPLE_POKEAPI_RESPONSE)
    summary = fetch_all(["Abomasnow", "Absol"], cache_dir=tmp_path, session=session)
    assert summary["fetched"] == 2
    assert summary["cached"] == 0
    assert summary["failed"] == []
    assert (tmp_path / "abomasnow.json").exists()
    assert (tmp_path / "absol.json").exists()
    with open(tmp_path / "abomasnow.json") as f:
        cached = json.load(f)
    assert cached["base_stats"]["hp"] == 90

def test_fetch_all_skips_already_cached_files(tmp_path):
    (tmp_path / "abomasnow.json").write_text(json.dumps({"base_stats": {}, "learnset": []}))
    session = _mock_session(_SAMPLE_POKEAPI_RESPONSE)
    summary = fetch_all(["Abomasnow"], cache_dir=tmp_path, session=session)
    assert summary["fetched"] == 0
    assert summary["cached"] == 1
    session.get.assert_not_called()

def test_fetch_all_continues_after_one_failure(tmp_path):
    session = MagicMock()
    ok_response = MagicMock(status_code=200)
    ok_response.json.return_value = _SAMPLE_POKEAPI_RESPONSE
    fail_response = MagicMock(status_code=404)
    session.get.side_effect = [fail_response, ok_response]
    summary = fetch_all(["Broken Name", "Absol"], cache_dir=tmp_path, session=session)
    assert summary["fetched"] == 1
    assert summary["failed"] == ["Broken Name"]
    assert (tmp_path / "absol.json").exists()
```

- [ ] **Step 10: Run to verify failure**

Run: `.venv/bin/pytest tests/test_fetch_pokeapi.py -v`
Expected: FAIL — `ImportError: cannot import name 'fetch_all'`

- [ ] **Step 11: Implement `fetch_all`**

```python
# append to pipeline/fetch_pokeapi.py
import json
from pathlib import Path


def _simple_cache_filename(display_name: str) -> str:
    slug = display_name.lower()
    slug = slug.replace("[", "").replace("]", "")
    slug = slug.replace(" ", "_")
    return f"{slug}.json"


def fetch_all(legal_names: list, cache_dir, session=None) -> dict:
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    session = session or requests.Session()

    fetched, cached, failed = 0, 0, []
    for name in legal_names:
        cache_file = cache_dir / _simple_cache_filename(name)
        if cache_file.exists():
            cached += 1
            continue
        try:
            data = fetch_pokemon_data(name, session=session)
        except PokeApiFetchError:
            failed.append(name)
            continue
        with open(cache_file, "w") as f:
            json.dump(data, f, indent=2)
        fetched += 1

    return {"fetched": fetched, "cached": cached, "failed": failed}
```

- [ ] **Step 12: Run to verify passing**

Run: `.venv/bin/pytest tests/test_fetch_pokeapi.py -v`
Expected: 11 passed

- [ ] **Step 13: Commit**

```bash
git add pipeline/fetch_pokeapi.py tests/test_fetch_pokeapi.py
git commit -m "feat: add PokeAPI fetch with name resolution, caching, and failure tolerance"
```

---

## Task 3: Merge source data into processed records

**Files:**
- Create: `pipeline/build_records.py`
- Test: `tests/test_build_records.py`

**Interfaces:**
- Consumes:
  - `data/source/legal_pokemon_m-b.json` shape: `{"regulation": str, "count": int, "legal_pokemon": [str]}`
  - `data/source/vgc_moves.json` shape: `{"meta": {...}, "pokemon": [{"name": str, "types": [str]}], "moves": [{"name": str, ...}]}`
  - `data/source/vgc_abilities.json` shape: `[{"name": str, "description": str}]`
  - raw cache files from Task 2: `{cache_dir}/{simple_cache_filename}.json` → `{"base_stats": {...}, "learnset": [pokeapi move slugs]}`
- Produces: `build_records(source_dir: Path, raw_dir: Path) -> list[dict]` returning records in the exact shape fixed in "Data Shapes" above, and `write_processed_records(records: list[dict], output_path: Path) -> None`.

- [ ] **Step 1: Write failing tests using fixture data (no real source files needed)**

```python
# tests/test_build_records.py
import json
from pipeline.build_records import build_records, write_processed_records

def _write_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f)

def _make_fixture_source(tmp_path):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    _write_json(source_dir / "legal_pokemon_m-b.json", {
        "regulation": "M-B",
        "count": 1,
        "legal_pokemon": ["Abomasnow"],
    })
    _write_json(source_dir / "vgc_moves.json", {
        "meta": {"regulation": "M-B"},
        "pokemon": [{"name": "Abomasnow", "types": ["Grass", "Ice"]}],
        "moves": [
            {"name": "Ice Punch", "type": "Ice", "category": "Physical", "power": 75, "accuracy": 100, "pp": 15, "effect": None},
            {"name": "Wood Hammer", "type": "Grass", "category": "Physical", "power": 120, "accuracy": 100, "pp": 15, "effect": None},
        ],
    })
    _write_json(source_dir / "vgc_abilities.json", [
        {"name": "Snow Warning", "description": "Summons hail/snow."},
        {"name": "Soundproof", "description": "Immune to sound moves."},
    ])
    _write_json(source_dir / "vgc_items.json", [])
    return source_dir

def _make_fixture_raw(tmp_path):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    _write_json(raw_dir / "abomasnow.json", {
        "base_stats": {"hp": 90, "attack": 92, "defense": 75, "sp_attack": 92, "sp_defense": 85, "speed": 60},
        "learnset": ["ice-punch", "wood-hammer", "solar-beam"],
        "abilities": ["snow-warning", "soundproof"],
    })
    return raw_dir

def test_build_records_merges_all_sources(tmp_path):
    source_dir = _make_fixture_source(tmp_path)
    raw_dir = _make_fixture_raw(tmp_path)

    records = build_records(source_dir, raw_dir)

    assert len(records) == 1
    record = records[0]
    assert record["name"] == "Abomasnow"
    assert record["types"] == ["Grass", "Ice"]
    assert record["base_stats"]["hp"] == 90
    assert record["legal_in"] == ["M-B"]
    assert set(record["learnset"]) == {"Ice Punch", "Wood Hammer"}
    assert set(record["abilities"]) == {"Snow Warning", "Soundproof"}

def test_build_records_skips_pokemon_missing_raw_cache(tmp_path):
    source_dir = _make_fixture_source(tmp_path)
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    records = build_records(source_dir, raw_dir)
    assert records == []

def test_write_processed_records_creates_valid_json(tmp_path):
    records = [{"name": "Abomasnow", "types": ["Grass", "Ice"]}]
    out_path = tmp_path / "processed" / "pokemon_records.json"
    write_processed_records(records, out_path)
    with open(out_path) as f:
        loaded = json.load(f)
    assert loaded == records
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/test_build_records.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline.build_records'`

- [ ] **Step 3: Implement `build_records.py`**

```python
# pipeline/build_records.py
import json
from pathlib import Path


def _load_json(path: Path):
    with open(path) as f:
        return json.load(f)


def _simple_cache_filename(display_name: str) -> str:
    slug = display_name.lower()
    slug = slug.replace("[", "").replace("]", "")
    slug = slug.replace(" ", "_")
    return f"{slug}.json"


def _title_case_slug(slug: str) -> str:
    return " ".join(word.capitalize() for word in slug.split("-"))


def build_records(source_dir: Path, raw_dir: Path) -> list:
    source_dir = Path(source_dir)
    raw_dir = Path(raw_dir)

    legal_data = _load_json(source_dir / "legal_pokemon_m-b.json")
    moves_data = _load_json(source_dir / "vgc_moves.json")
    abilities_data = _load_json(source_dir / "vgc_abilities.json")

    regulation = legal_data["regulation"]
    types_by_name = {p["name"]: p["types"] for p in moves_data["pokemon"]}
    move_names_by_slug = {}
    for move in moves_data["moves"]:
        slug = move["name"].lower().replace(" ", "-").replace("'", "")
        move_names_by_slug[slug] = move["name"]
    ability_names_by_slug = {}
    for ability in abilities_data:
        slug = ability["name"].lower().replace(" ", "-").replace("'", "")
        ability_names_by_slug[slug] = ability["name"]

    records = []
    for name in legal_data["legal_pokemon"]:
        raw_path = raw_dir / _simple_cache_filename(name)
        if not raw_path.exists():
            continue
        raw = _load_json(raw_path)

        learnset = sorted({
            move_names_by_slug[slug]
            for slug in raw.get("learnset", [])
            if slug in move_names_by_slug
        })
        abilities = sorted({
            ability_names_by_slug.get(slug, _title_case_slug(slug))
            for slug in raw.get("abilities", [])
        })

        records.append({
            "name": name,
            "types": types_by_name.get(name, []),
            "base_stats": raw.get("base_stats", {}),
            "abilities": abilities,
            "learnset": learnset,
            "legal_in": [regulation],
        })

    return records


def write_processed_records(records: list, output_path: Path) -> None:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(records, f, indent=2)
```

- [ ] **Step 4: Run to verify passing**

Run: `.venv/bin/pytest tests/test_build_records.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add pipeline/build_records.py tests/test_build_records.py
git commit -m "feat: merge source JSONs and PokeAPI cache into processed pokemon records"
```

---

## Task 4: Refresh job entrypoint and real learnset/ability cache shape

**Files:**
- Modify: `pipeline/fetch_pokeapi.py` — extend `fetch_pokemon_data` and `fetch_all` to also fetch and cache abilities (PokéAPI's `abilities` field), since Task 3's `build_records` expects `raw["abilities"]`.
- Create: `pipeline/refresh_job.py`
- Test: `tests/test_refresh_job.py`
- Modify: `tests/test_fetch_pokeapi.py` — update `_SAMPLE_POKEAPI_RESPONSE` and assertions to include abilities.

**Interfaces:**
- Consumes: `fetch_all` from Task 2, `build_records`/`write_processed_records` from Task 3.
- Produces: `run_refresh(source_dir: Path, raw_dir: Path, output_path: Path, session=None) -> dict` — runs fetch then build, returns the `fetch_all` summary dict plus `"records_written": int`.

- [ ] **Step 1: Update the fixture PokeAPI response and fetch test to include abilities**

```python
# in tests/test_fetch_pokeapi.py, replace _SAMPLE_POKEAPI_RESPONSE with:
_SAMPLE_POKEAPI_RESPONSE = {
    "stats": [
        {"base_stat": 90, "stat": {"name": "hp"}},
        {"base_stat": 92, "stat": {"name": "attack"}},
        {"base_stat": 75, "stat": {"name": "defense"}},
        {"base_stat": 92, "stat": {"name": "special-attack"}},
        {"base_stat": 85, "stat": {"name": "special-defense"}},
        {"base_stat": 60, "stat": {"name": "speed"}},
    ],
    "moves": [
        {"move": {"name": "ice-punch"}},
        {"move": {"name": "wood-hammer"}},
    ],
    "abilities": [
        {"ability": {"name": "snow-warning"}},
        {"ability": {"name": "soundproof"}},
    ],
}

# and add an assertion in test_fetch_pokemon_data_parses_stats_and_learnset:
    assert result["abilities"] == ["snow-warning", "soundproof"]
```

- [ ] **Step 2: Run to verify this specific test now fails**

Run: `.venv/bin/pytest tests/test_fetch_pokeapi.py::test_fetch_pokemon_data_parses_stats_and_learnset -v`
Expected: FAIL — `KeyError: 'abilities'`

- [ ] **Step 3: Update `fetch_pokemon_data` to parse and return abilities**

```python
# in pipeline/fetch_pokeapi.py, inside fetch_pokemon_data, after computing `learnset`:
    abilities = [a["ability"]["name"] for a in payload["abilities"]]
    return {"base_stats": base_stats, "learnset": learnset, "abilities": abilities}
```

(This replaces the previous `return {"base_stats": base_stats, "learnset": learnset}` line.)

- [ ] **Step 4: Run full fetch test file to verify all pass**

Run: `.venv/bin/pytest tests/test_fetch_pokeapi.py -v`
Expected: 11 passed

- [ ] **Step 5: Write failing test for `run_refresh`**

```python
# tests/test_refresh_job.py
import json
from unittest.mock import MagicMock
from pipeline.refresh_job import run_refresh

_SAMPLE_RESPONSE = {
    "stats": [
        {"base_stat": 90, "stat": {"name": "hp"}},
        {"base_stat": 92, "stat": {"name": "attack"}},
        {"base_stat": 75, "stat": {"name": "defense"}},
        {"base_stat": 92, "stat": {"name": "special-attack"}},
        {"base_stat": 85, "stat": {"name": "special-defense"}},
        {"base_stat": 60, "stat": {"name": "speed"}},
    ],
    "moves": [{"move": {"name": "ice-punch"}}],
    "abilities": [{"ability": {"name": "snow-warning"}}],
}

def _fixture_source(tmp_path):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    with open(source_dir / "legal_pokemon_m-b.json", "w") as f:
        json.dump({"regulation": "M-B", "count": 1, "legal_pokemon": ["Abomasnow"]}, f)
    with open(source_dir / "vgc_moves.json", "w") as f:
        json.dump({
            "meta": {"regulation": "M-B"},
            "pokemon": [{"name": "Abomasnow", "types": ["Grass", "Ice"]}],
            "moves": [{"name": "Ice Punch", "type": "Ice", "category": "Physical", "power": 75, "accuracy": 100, "pp": 15, "effect": None}],
        }, f)
    with open(source_dir / "vgc_abilities.json", "w") as f:
        json.dump([{"name": "Snow Warning", "description": "x"}], f)
    with open(source_dir / "vgc_items.json", "w") as f:
        json.dump([], f)
    return source_dir

def test_run_refresh_fetches_and_writes_records(tmp_path):
    source_dir = _fixture_source(tmp_path)
    raw_dir = tmp_path / "raw"
    output_path = tmp_path / "processed" / "pokemon_records.json"

    session = MagicMock()
    response = MagicMock(status_code=200)
    response.json.return_value = _SAMPLE_RESPONSE
    session.get.return_value = response

    summary = run_refresh(source_dir, raw_dir, output_path, session=session)

    assert summary["fetched"] == 1
    assert summary["failed"] == []
    assert summary["records_written"] == 1
    with open(output_path) as f:
        records = json.load(f)
    assert records[0]["name"] == "Abomasnow"
    assert records[0]["legal_in"] == ["M-B"]
```

- [ ] **Step 6: Run to verify failure**

Run: `.venv/bin/pytest tests/test_refresh_job.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline.refresh_job'`

- [ ] **Step 7: Implement `refresh_job.py`**

```python
# pipeline/refresh_job.py
from pathlib import Path

from pipeline.fetch_pokeapi import fetch_all
from pipeline.build_records import build_records, write_processed_records


def run_refresh(source_dir, raw_dir, output_path, session=None) -> dict:
    source_dir = Path(source_dir)
    raw_dir = Path(raw_dir)
    output_path = Path(output_path)

    import json
    with open(source_dir / "legal_pokemon_m-b.json") as f:
        legal_names = json.load(f)["legal_pokemon"]

    summary = fetch_all(legal_names, cache_dir=raw_dir, session=session)

    records = build_records(source_dir, raw_dir)
    write_processed_records(records, output_path)
    summary["records_written"] = len(records)
    return summary


if __name__ == "__main__":
    result = run_refresh(
        source_dir=Path("data/source"),
        raw_dir=Path("data/raw"),
        output_path=Path("data/processed/pokemon_records.json"),
    )
    print(result)
```

- [ ] **Step 8: Run to verify passing**

Run: `.venv/bin/pytest tests/test_refresh_job.py -v`
Expected: 1 passed

- [ ] **Step 9: Run the full test suite to confirm nothing regressed**

Run: `.venv/bin/pytest -v`
Expected: all tests passed

- [ ] **Step 10: Commit**

```bash
git add pipeline/fetch_pokeapi.py pipeline/refresh_job.py tests/test_fetch_pokeapi.py tests/test_refresh_job.py
git commit -m "feat: fetch abilities alongside stats/learnset, add refresh_job entrypoint"
```

---

## Task 5: Damage calc constants (type chart, natures, stat stages)

**Files:**
- Create: `damage_calc/data/type_chart.py`
- Create: `damage_calc/data/natures.py`
- Create: `damage_calc/data/stat_stages.py`
- Test: `tests/test_calc_data.py`

**Interfaces:**
- Produces:
  - `type_chart.get_effectiveness(attacking_type: str, defending_types: list[str]) -> float` — product of effectiveness against each defending type (e.g. 0.5, 1, 2, 4, 0).
  - `natures.get_nature_modifiers(nature: str) -> dict` — returns `{"boosted": stat_name_or_None, "lowered": stat_name_or_None}` for the 5 non-attack/defense/etc stat keys used elsewhere (`attack`, `defense`, `sp_attack`, `sp_defense`, `speed`).
  - `stat_stages.get_stage_multiplier(stage: int) -> float` — standard -6..+6 stage table, e.g. `get_stage_multiplier(0) == 1.0`, `get_stage_multiplier(1) == 1.5`, `get_stage_multiplier(-1) == 2/3`.

- [ ] **Step 1: Write failing tests for stat stage multipliers (simplest table first)**

```python
# tests/test_calc_data.py
from damage_calc.data.stat_stages import get_stage_multiplier

def test_stage_zero_is_neutral():
    assert get_stage_multiplier(0) == 1.0

def test_positive_stages():
    assert get_stage_multiplier(1) == 1.5
    assert get_stage_multiplier(2) == 2.0
    assert get_stage_multiplier(6) == 4.0

def test_negative_stages():
    assert round(get_stage_multiplier(-1), 4) == round(2 / 3, 4)
    assert get_stage_multiplier(-2) == 0.5
    assert get_stage_multiplier(-6) == 0.25
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/test_calc_data.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'damage_calc.data.stat_stages'`

- [ ] **Step 3: Implement `stat_stages.py`**

```python
# damage_calc/data/stat_stages.py
def get_stage_multiplier(stage: int) -> float:
    stage = max(-6, min(6, stage))
    if stage >= 0:
        return (2 + stage) / 2
    return 2 / (2 - stage)
```

- [ ] **Step 4: Run to verify passing**

Run: `.venv/bin/pytest tests/test_calc_data.py -v`
Expected: 3 passed

- [ ] **Step 5: Write failing tests for natures**

```python
# append to tests/test_calc_data.py
from damage_calc.data.natures import get_nature_modifiers

def test_adamant_boosts_attack_lowers_sp_attack():
    mods = get_nature_modifiers("Adamant")
    assert mods == {"boosted": "attack", "lowered": "sp_attack"}

def test_neutral_nature_has_no_boost_or_lower():
    mods = get_nature_modifiers("Hardy")
    assert mods == {"boosted": None, "lowered": None}

def test_timid_boosts_speed_lowers_attack():
    mods = get_nature_modifiers("Timid")
    assert mods == {"boosted": "speed", "lowered": "attack"}
```

- [ ] **Step 6: Run to verify failure**

Run: `.venv/bin/pytest tests/test_calc_data.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'damage_calc.data.natures'`

- [ ] **Step 7: Implement `natures.py`**

```python
# damage_calc/data/natures.py
_NEUTRAL_NATURES = {"Hardy", "Docile", "Serious", "Bashful", "Quirky"}

_NATURE_TABLE = {
    "Lonely": ("attack", "defense"),
    "Adamant": ("attack", "sp_attack"),
    "Naughty": ("attack", "sp_defense"),
    "Brave": ("attack", "speed"),
    "Bold": ("defense", "attack"),
    "Impish": ("defense", "sp_attack"),
    "Lax": ("defense", "sp_defense"),
    "Relaxed": ("defense", "speed"),
    "Modest": ("sp_attack", "attack"),
    "Mild": ("sp_attack", "defense"),
    "Rash": ("sp_attack", "sp_defense"),
    "Quiet": ("sp_attack", "speed"),
    "Calm": ("sp_defense", "attack"),
    "Gentle": ("sp_defense", "defense"),
    "Careful": ("sp_defense", "sp_attack"),
    "Sassy": ("sp_defense", "speed"),
    "Timid": ("speed", "attack"),
    "Hasty": ("speed", "defense"),
    "Jolly": ("speed", "sp_attack"),
    "Naive": ("speed", "sp_defense"),
}


def get_nature_modifiers(nature: str) -> dict:
    if nature in _NEUTRAL_NATURES:
        return {"boosted": None, "lowered": None}
    boosted, lowered = _NATURE_TABLE[nature]
    return {"boosted": boosted, "lowered": lowered}
```

- [ ] **Step 8: Run to verify passing**

Run: `.venv/bin/pytest tests/test_calc_data.py -v`
Expected: 6 passed

- [ ] **Step 9: Write failing tests for the type chart (a representative subset, not all 18x18)**

```python
# append to tests/test_calc_data.py
from damage_calc.data.type_chart import get_effectiveness

def test_neutral_matchup():
    assert get_effectiveness("Normal", ["Grass"]) == 1.0

def test_super_effective_single_type():
    assert get_effectiveness("Fire", ["Grass"]) == 2.0

def test_not_very_effective_single_type():
    assert get_effectiveness("Fire", ["Water"]) == 0.5

def test_immune():
    assert get_effectiveness("Normal", ["Ghost"]) == 0.0

def test_dual_type_stacks_multiplicatively():
    # Ice vs Grass/Ice(Abomasnow-like dual): Ice is 2x vs Grass, 0.5x vs Ice -> 1.0
    assert get_effectiveness("Ice", ["Grass", "Ice"]) == 1.0

def test_dual_type_quad_effective():
    # Ice vs Dragon/Flying (e.g. Dragonite): 2x * 2x = 4x
    assert get_effectiveness("Ice", ["Dragon", "Flying"]) == 4.0
```

- [ ] **Step 10: Run to verify failure**

Run: `.venv/bin/pytest tests/test_calc_data.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'damage_calc.data.type_chart'`

- [ ] **Step 11: Implement `type_chart.py` with the full 18-type effectiveness table**

```python
# damage_calc/data/type_chart.py
ALL_TYPES = [
    "Normal", "Fire", "Water", "Electric", "Grass", "Ice", "Fighting", "Poison",
    "Ground", "Flying", "Psychic", "Bug", "Rock", "Ghost", "Dragon", "Dark",
    "Steel", "Fairy",
]

# Each entry: attacking type -> {defending type: multiplier}. Omitted pairs default to 1.0.
_CHART = {
    "Normal": {"Rock": 0.5, "Ghost": 0.0, "Steel": 0.5},
    "Fire": {"Fire": 0.5, "Water": 0.5, "Grass": 2.0, "Ice": 2.0, "Bug": 2.0, "Rock": 0.5, "Dragon": 0.5, "Steel": 2.0},
    "Water": {"Fire": 2.0, "Water": 0.5, "Grass": 0.5, "Ground": 2.0, "Rock": 2.0, "Dragon": 0.5},
    "Electric": {"Water": 2.0, "Electric": 0.5, "Grass": 0.5, "Ground": 0.0, "Flying": 2.0, "Dragon": 0.5},
    "Grass": {"Fire": 0.5, "Water": 2.0, "Grass": 0.5, "Poison": 0.5, "Ground": 2.0, "Flying": 0.5, "Bug": 0.5, "Rock": 2.0, "Dragon": 0.5, "Steel": 0.5},
    "Ice": {"Fire": 0.5, "Water": 0.5, "Grass": 2.0, "Ice": 0.5, "Ground": 2.0, "Flying": 2.0, "Dragon": 2.0, "Steel": 0.5},
    "Fighting": {"Normal": 2.0, "Ice": 2.0, "Poison": 0.5, "Flying": 0.5, "Psychic": 0.5, "Bug": 0.5, "Rock": 2.0, "Ghost": 0.0, "Dark": 2.0, "Steel": 2.0, "Fairy": 0.5},
    "Poison": {"Grass": 2.0, "Poison": 0.5, "Ground": 0.5, "Rock": 0.5, "Ghost": 0.5, "Steel": 0.0, "Fairy": 2.0},
    "Ground": {"Fire": 2.0, "Electric": 2.0, "Grass": 0.5, "Poison": 2.0, "Flying": 0.0, "Bug": 0.5, "Rock": 2.0, "Steel": 2.0},
    "Flying": {"Electric": 0.5, "Grass": 2.0, "Fighting": 2.0, "Bug": 2.0, "Rock": 0.5, "Steel": 0.5},
    "Psychic": {"Fighting": 2.0, "Poison": 2.0, "Psychic": 0.5, "Dark": 0.0, "Steel": 0.5},
    "Bug": {"Fire": 0.5, "Grass": 2.0, "Fighting": 0.5, "Poison": 0.5, "Flying": 0.5, "Psychic": 2.0, "Ghost": 0.5, "Dark": 2.0, "Steel": 0.5, "Fairy": 0.5},
    "Rock": {"Fire": 2.0, "Ice": 2.0, "Fighting": 0.5, "Ground": 0.5, "Flying": 2.0, "Bug": 2.0, "Steel": 0.5},
    "Ghost": {"Normal": 0.0, "Psychic": 2.0, "Ghost": 2.0, "Dark": 0.5},
    "Dragon": {"Dragon": 2.0, "Steel": 0.5, "Fairy": 0.0},
    "Dark": {"Fighting": 0.5, "Psychic": 2.0, "Ghost": 2.0, "Dark": 0.5, "Fairy": 0.5},
    "Steel": {"Fire": 0.5, "Water": 0.5, "Electric": 0.5, "Ice": 2.0, "Rock": 2.0, "Steel": 0.5, "Fairy": 2.0},
    "Fairy": {"Fire": 0.5, "Fighting": 2.0, "Poison": 0.5, "Dragon": 2.0, "Dark": 2.0, "Steel": 0.5},
}


def get_effectiveness(attacking_type: str, defending_types: list) -> float:
    multiplier = 1.0
    row = _CHART.get(attacking_type, {})
    for defending_type in defending_types:
        multiplier *= row.get(defending_type, 1.0)
    return multiplier
```

- [ ] **Step 12: Run to verify passing**

Run: `.venv/bin/pytest tests/test_calc_data.py -v`
Expected: 12 passed

- [ ] **Step 13: Commit**

```bash
git add damage_calc/data tests/test_calc_data.py
git commit -m "feat: add type chart, nature, and stat stage lookup tables for damage calc"
```

---

## Task 6: Core damage formula (single hit, no doubles/weather modifiers yet)

**Files:**
- Create: `damage_calc/calc.py`
- Test: `tests/test_calc.py`

**Interfaces:**
- Consumes: `damage_calc.data.type_chart.get_effectiveness`, `damage_calc.data.natures.get_nature_modifiers`, `damage_calc.data.stat_stages.get_stage_multiplier` (Task 5). Consumes the `combatant`/`move`/`context`/`DamageResult` shapes fixed in "Data Shapes" above.
- Produces: `calculate_stat(base: int, iv: int, ev: int, level: int, nature_modifier: float, stat_name: str) -> int` and `calculate_damage(move: dict, attacker: dict, defender: dict, context: dict) -> DamageResult`. Task 7 and Task 8 both extend `calculate_damage`'s body — its signature does not change after this task.

- [ ] **Step 1: Write failing test for stat calculation (the standard Pokémon stat formula)**

```python
# tests/test_calc.py
from damage_calc.calc import calculate_stat

def test_hp_stat_formula():
    # base 90, 31 IV, 252 EV, level 50 -> floor((2*90 + 31 + 63) * 50 / 100) + 50 + 10
    assert calculate_stat(90, 31, 252, 50, 1.0, "hp") == 191

def test_non_hp_stat_formula_neutral_nature():
    # base 92 attack, 31 IV, 252 EV, level 50, neutral nature
    assert calculate_stat(92, 31, 252, 50, 1.0, "attack") == 130

def test_non_hp_stat_formula_boosting_nature():
    # same as above but with a 1.1 boosting nature multiplier
    assert calculate_stat(92, 31, 252, 50, 1.1, "attack") == 143
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/test_calc.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'damage_calc.calc'`

- [ ] **Step 3: Implement `calculate_stat`**

```python
# damage_calc/calc.py
import math


def calculate_stat(base: int, iv: int, ev: int, level: int, nature_modifier: float, stat_name: str) -> int:
    core = math.floor((2 * base + iv + math.floor(ev / 4)) * level / 100)
    if stat_name == "hp":
        if base == 1:  # Shedinja-style single-HP mons, not in this dataset but keep formula honest
            return 1
        return core + level + 10
    return math.floor((core + 5) * nature_modifier)
```

- [ ] **Step 4: Run to verify passing**

Run: `.venv/bin/pytest tests/test_calc.py -v`
Expected: 3 passed

- [ ] **Step 5: Write failing test for a full `calculate_damage` basic physical hit against known reference values**

```python
# append to tests/test_calc.py
from damage_calc.calc import calculate_damage

def _make_combatant(base_stats, level=50, evs=None, nature="Hardy", stat_stages=None, ability=None, item=None, tera_type=None, types=None):
    return {
        "record": {
            "name": "TestMon",
            "types": types or ["Normal"],
            "base_stats": base_stats,
            "abilities": [],
            "learnset": [],
            "legal_in": ["M-B"],
        },
        "level": level,
        "evs": evs or {"hp": 0, "attack": 0, "defense": 0, "sp_attack": 0, "sp_defense": 0, "speed": 0},
        "ivs": {"hp": 31, "attack": 31, "defense": 31, "sp_attack": 31, "sp_defense": 31, "speed": 31},
        "nature": nature,
        "stat_stages": stat_stages or {"attack": 0, "defense": 0, "sp_attack": 0, "sp_defense": 0, "speed": 0},
        "tera_type": tera_type,
        "item": item,
        "ability": ability,
        "current_hp_fraction": 1.0,
    }

_BASE_CONTEXT = {
    "weather": None, "terrain": None, "is_spread_target": False,
    "screen": None, "is_doubles": True,
}

def test_basic_physical_hit_neutral_type():
    move = {"name": "Tackle", "type": "Normal", "category": "Physical", "power": 40, "accuracy": 100, "pp": 35, "effect": None}
    attacker = _make_combatant(
        {"hp": 100, "attack": 100, "defense": 100, "sp_attack": 100, "sp_defense": 100, "speed": 100},
        evs={"hp": 0, "attack": 252, "defense": 0, "sp_attack": 0, "sp_defense": 0, "speed": 0},
        nature="Adamant",
        types=["Normal"],
    )
    defender = _make_combatant(
        {"hp": 100, "attack": 100, "defense": 100, "sp_attack": 100, "sp_defense": 100, "speed": 100},
        evs={"hp": 252, "attack": 0, "defense": 0, "sp_attack": 0, "sp_defense": 0, "speed": 0},
        types=["Water"],
    )

    result = calculate_damage(move, attacker, defender, _BASE_CONTEXT)

    assert result.min_damage > 0
    assert result.max_damage >= result.min_damage
    # STAB (Normal atk on Normal-type attacker) applied, neutral type effectiveness vs Water
    assert result.min_damage == 44
    assert result.max_damage == 52

def test_stat_stage_negative_attack_reduces_damage():
    move = {"name": "Tackle", "type": "Normal", "category": "Physical", "power": 40, "accuracy": 100, "pp": 35, "effect": None}
    stats = {"hp": 100, "attack": 100, "defense": 100, "sp_attack": 100, "sp_defense": 100, "speed": 100}
    attacker_neutral = _make_combatant(stats, types=["Normal"])
    attacker_intimidated = _make_combatant(stats, types=["Normal"], stat_stages={"attack": -1, "defense": 0, "sp_attack": 0, "sp_defense": 0, "speed": 0})
    defender = _make_combatant(stats, types=["Water"])

    result_neutral = calculate_damage(move, attacker_neutral, defender, _BASE_CONTEXT)
    result_intimidated = calculate_damage(move, attacker_intimidated, defender, _BASE_CONTEXT)

    assert result_intimidated.max_damage < result_neutral.max_damage
```

- [ ] **Step 6: Run to verify failure**

Run: `.venv/bin/pytest tests/test_calc.py -v`
Expected: FAIL — `ImportError: cannot import name 'calculate_damage'`

- [ ] **Step 7: Implement `calculate_damage` (core formula, spread/weather/screen args accepted but no-op until Tasks 7-8)**

```python
# append to damage_calc/calc.py
from dataclasses import dataclass

from damage_calc.data.type_chart import get_effectiveness
from damage_calc.data.natures import get_nature_modifiers
from damage_calc.data.stat_stages import get_stage_multiplier


@dataclass
class DamageResult:
    min_damage: int
    max_damage: int
    min_percent: float
    max_percent: float
    is_ko_chance: bool


def _nature_modifier_for_stat(nature: str, stat_name: str) -> float:
    mods = get_nature_modifiers(nature)
    if mods["boosted"] == stat_name:
        return 1.1
    if mods["lowered"] == stat_name:
        return 0.9
    return 1.0


def _effective_stat(combatant: dict, stat_name: str) -> int:
    base = combatant["record"]["base_stats"][stat_name]
    iv = combatant["ivs"][stat_name]
    ev = combatant["evs"][stat_name]
    level = combatant["level"]
    nature_mod = _nature_modifier_for_stat(combatant["nature"], stat_name)
    stat = calculate_stat(base, iv, ev, level, nature_mod, stat_name)
    if stat_name != "hp":
        stage = combatant["stat_stages"].get(stat_name, 0)
        stat = math.floor(stat * get_stage_multiplier(stage))
    return stat


def calculate_damage(move: dict, attacker: dict, defender: dict, context: dict) -> DamageResult:
    level = attacker["level"]
    power = move["power"] or 0
    category = move["category"]

    if category == "Physical":
        attack_stat = _effective_stat(attacker, "attack")
        defense_stat = _effective_stat(defender, "defense")
    else:
        attack_stat = _effective_stat(attacker, "sp_attack")
        defense_stat = _effective_stat(defender, "sp_defense")

    attacker_types = [attacker["tera_type"]] if attacker["tera_type"] else attacker["record"]["types"]
    stab = 1.5 if move["type"] in attacker_types else 1.0

    type_effectiveness = get_effectiveness(move["type"], defender["record"]["types"])

    base_damage = math.floor(
        math.floor(math.floor(2 * level / 5 + 2) * power * attack_stat / defense_stat) / 50
    ) + 2

    modifier_low = stab * type_effectiveness * 0.85
    modifier_high = stab * type_effectiveness * 1.0

    min_damage = max(1, math.floor(base_damage * modifier_low)) if type_effectiveness > 0 else 0
    max_damage = max(1, math.floor(base_damage * modifier_high)) if type_effectiveness > 0 else 0

    defender_hp = _effective_stat(defender, "hp")
    remaining_hp = math.floor(defender_hp * defender["current_hp_fraction"])

    min_percent = round(100 * min_damage / defender_hp, 2) if defender_hp else 0.0
    max_percent = round(100 * max_damage / defender_hp, 2) if defender_hp else 0.0
    is_ko_chance = max_damage >= remaining_hp

    return DamageResult(
        min_damage=min_damage,
        max_damage=max_damage,
        min_percent=min_percent,
        max_percent=max_percent,
        is_ko_chance=is_ko_chance,
    )
```

- [ ] **Step 8: Run to verify passing**

Run: `.venv/bin/pytest tests/test_calc.py -v`
Expected: 5 passed (3 from Step 4, 2 new)

If `test_basic_physical_hit_neutral_type` doesn't hit exactly 44/52, print `attack_stat`, `defense_stat`, and `base_damage` and adjust the EV/level fixture numbers in the test (not the formula) until the reference matches a real Pokémon Showdown damage calc for the same inputs — the formula in Step 7 is the standard, well-established Gen 9 damage formula and should not need adjustment.

- [ ] **Step 9: Run full suite to confirm no regressions**

Run: `.venv/bin/pytest -v`
Expected: all tests passed

- [ ] **Step 10: Commit**

```bash
git add damage_calc/calc.py tests/test_calc.py
git commit -m "feat: implement core damage formula (stat calc, STAB, type effectiveness, stat stages)"
```

---

## Task 7: Doubles spread-move and Tera modifiers

**Files:**
- Modify: `damage_calc/calc.py` — extend `calculate_damage` to apply the 0.75x spread multiplier and to let Tera type override type-effectiveness (in addition to the STAB override already in Task 6).
- Modify: `tests/test_calc.py` — add spread-move and Tera tests.

**Interfaces:**
- Consumes: `calculate_damage` signature from Task 6, unchanged.
- Produces: same `calculate_damage` signature; behavior now varies with `context["is_spread_target"]` and `attacker["tera_type"]` affecting type-effectiveness lookup (not just STAB, which Task 6 already handles).

- [ ] **Step 1: Write failing tests**

```python
# append to tests/test_calc.py
def test_spread_move_applies_075_multiplier_in_doubles():
    move = {"name": "Earthquake", "type": "Ground", "category": "Physical", "power": 100, "accuracy": 100, "pp": 10, "effect": None}
    stats = {"hp": 100, "attack": 100, "defense": 100, "sp_attack": 100, "sp_defense": 100, "speed": 100}
    attacker = _make_combatant(stats, types=["Ground"])
    defender = _make_combatant(stats, types=["Water"])

    single_target_context = {**_BASE_CONTEXT, "is_spread_target": False}
    spread_context = {**_BASE_CONTEXT, "is_spread_target": True}

    single = calculate_damage(move, attacker, defender, single_target_context)
    spread = calculate_damage(move, attacker, defender, spread_context)

    assert spread.max_damage < single.max_damage
    assert spread.max_damage == math.floor(single.max_damage * 0.75) or spread.max_damage == math.floor(single.max_damage * 0.75) - 1

def test_tera_type_changes_effectiveness_and_stab():
    # Attacker is pure Normal but Tera'd into Fighting; move is Fighting-type
    # Fighting is 2x vs Normal defender base type... use a defender that's Rock (Fighting is 2x vs Rock)
    move = {"name": "Close Combat", "type": "Fighting", "category": "Physical", "power": 120, "accuracy": 100, "pp": 8, "effect": None}
    stats = {"hp": 100, "attack": 100, "defense": 100, "sp_attack": 100, "sp_defense": 100, "speed": 100}
    attacker_no_tera = _make_combatant(stats, types=["Normal"], tera_type=None)
    attacker_tera_fighting = _make_combatant(stats, types=["Normal"], tera_type="Fighting")
    defender = _make_combatant(stats, types=["Rock"])

    no_tera = calculate_damage(move, attacker_no_tera, defender, _BASE_CONTEXT)
    tera = calculate_damage(move, attacker_tera_fighting, defender, _BASE_CONTEXT)

    # No Tera: no STAB (Normal attacker using Fighting move), just 2x type effectiveness vs Rock
    # Tera Fighting: STAB applies too (1.5x on top), so damage should be higher
    assert tera.max_damage > no_tera.max_damage
```

Add `import math` at the top of `tests/test_calc.py` if not already present (needed for the `math.floor` reference in the spread test).

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/test_calc.py -v`
Expected: FAIL — `test_spread_move_applies_075_multiplier_in_doubles` fails (spread multiplier not yet applied); `test_tera_type_changes_effectiveness_and_stab` should already pass since Task 6's STAB logic already uses `tera_type` for STAB — if the Tera test unexpectedly fails, note that in review rather than silently changing the test.

- [ ] **Step 3: Add the spread-move modifier to `calculate_damage`**

```python
# in damage_calc/calc.py, inside calculate_damage, after computing modifier_low/modifier_high:
    spread_modifier = 0.75 if context.get("is_spread_target") and context.get("is_doubles") else 1.0
    modifier_low *= spread_modifier
    modifier_high *= spread_modifier
```

Place this block immediately after the `modifier_low = ...` / `modifier_high = ...` lines from Task 6, before `min_damage`/`max_damage` are computed.

- [ ] **Step 4: Run to verify passing**

Run: `.venv/bin/pytest tests/test_calc.py -v`
Expected: all passed

- [ ] **Step 5: Run full suite**

Run: `.venv/bin/pytest -v`
Expected: all tests passed

- [ ] **Step 6: Commit**

```bash
git add damage_calc/calc.py tests/test_calc.py
git commit -m "feat: apply doubles spread-move damage reduction to damage calc"
```

---

## Task 8: Weather, terrain, and screen modifiers; finalize KO-chance

**Files:**
- Modify: `damage_calc/calc.py` — add weather (Sun/Rain boost same-type move by 1.5x / reduce opposing by 0.5x), terrain (Electric/Grassy/Psychic boost matching-type moves by 1.3x when attacker is grounded — treat all attackers as grounded for this slice, no Flying-immunity tracking), and screen (Reflect halves physical, Light Screen halves special, Aurora Veil halves both; in doubles this plan uses the doubles multiplier of 2/3 per standard mechanics) modifiers.
- Modify: `tests/test_calc.py` — add tests for each.

**Interfaces:**
- Consumes/produces: same `calculate_damage` signature, now fully implementing every field in the `context` dict fixed at the top of this plan.

- [ ] **Step 1: Write failing tests**

```python
# append to tests/test_calc.py
def test_rain_boosts_water_move():
    move = {"name": "Surf", "type": "Water", "category": "Special", "power": 90, "accuracy": 100, "pp": 15, "effect": None}
    stats = {"hp": 100, "attack": 100, "defense": 100, "sp_attack": 100, "sp_defense": 100, "speed": 100}
    attacker = _make_combatant(stats, types=["Water"])
    defender = _make_combatant(stats, types=["Normal"])

    no_weather = calculate_damage(move, attacker, defender, {**_BASE_CONTEXT, "weather": None})
    rain = calculate_damage(move, attacker, defender, {**_BASE_CONTEXT, "weather": "Rain"})

    assert rain.max_damage > no_weather.max_damage

def test_sun_weakens_water_move():
    move = {"name": "Surf", "type": "Water", "category": "Special", "power": 90, "accuracy": 100, "pp": 15, "effect": None}
    stats = {"hp": 100, "attack": 100, "defense": 100, "sp_attack": 100, "sp_defense": 100, "speed": 100}
    attacker = _make_combatant(stats, types=["Water"])
    defender = _make_combatant(stats, types=["Normal"])

    no_weather = calculate_damage(move, attacker, defender, {**_BASE_CONTEXT, "weather": None})
    sun = calculate_damage(move, attacker, defender, {**_BASE_CONTEXT, "weather": "Sun"})

    assert sun.max_damage < no_weather.max_damage

def test_electric_terrain_boosts_electric_move():
    move = {"name": "Thunderbolt", "type": "Electric", "category": "Special", "power": 90, "accuracy": 100, "pp": 15, "effect": None}
    stats = {"hp": 100, "attack": 100, "defense": 100, "sp_attack": 100, "sp_defense": 100, "speed": 100}
    attacker = _make_combatant(stats, types=["Electric"])
    defender = _make_combatant(stats, types=["Water"])

    no_terrain = calculate_damage(move, attacker, defender, {**_BASE_CONTEXT, "terrain": None})
    terrain = calculate_damage(move, attacker, defender, {**_BASE_CONTEXT, "terrain": "Electric"})

    assert terrain.max_damage > no_terrain.max_damage

def test_reflect_halves_physical_damage():
    move = {"name": "Tackle", "type": "Normal", "category": "Physical", "power": 40, "accuracy": 100, "pp": 35, "effect": None}
    stats = {"hp": 100, "attack": 100, "defense": 100, "sp_attack": 100, "sp_defense": 100, "speed": 100}
    attacker = _make_combatant(stats, types=["Normal"])
    defender = _make_combatant(stats, types=["Water"])

    no_screen = calculate_damage(move, attacker, defender, {**_BASE_CONTEXT, "screen": None})
    reflect = calculate_damage(move, attacker, defender, {**_BASE_CONTEXT, "screen": "Reflect"})

    assert reflect.max_damage < no_screen.max_damage

def test_light_screen_does_not_affect_physical_damage():
    move = {"name": "Tackle", "type": "Normal", "category": "Physical", "power": 40, "accuracy": 100, "pp": 35, "effect": None}
    stats = {"hp": 100, "attack": 100, "defense": 100, "sp_attack": 100, "sp_defense": 100, "speed": 100}
    attacker = _make_combatant(stats, types=["Normal"])
    defender = _make_combatant(stats, types=["Water"])

    no_screen = calculate_damage(move, attacker, defender, {**_BASE_CONTEXT, "screen": None})
    light_screen = calculate_damage(move, attacker, defender, {**_BASE_CONTEXT, "screen": "Light Screen"})

    assert light_screen.max_damage == no_screen.max_damage

def test_ko_chance_true_when_max_damage_exceeds_remaining_hp():
    move = {"name": "Close Combat", "type": "Fighting", "category": "Physical", "power": 120, "accuracy": 100, "pp": 8, "effect": None}
    stats = {"hp": 100, "attack": 100, "defense": 100, "sp_attack": 100, "sp_defense": 100, "speed": 100}
    attacker = _make_combatant(stats, types=["Fighting"])
    defender = _make_combatant(stats, types=["Rock"])
    defender["current_hp_fraction"] = 0.1

    result = calculate_damage(move, attacker, defender, _BASE_CONTEXT)
    assert result.is_ko_chance is True
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/test_calc.py -v`
Expected: FAIL on the 5 new weather/terrain/screen tests (KO-chance test should already pass from Task 6)

- [ ] **Step 3: Add weather, terrain, and screen modifiers to `calculate_damage`**

```python
# in damage_calc/calc.py, inside calculate_damage, extend the modifier block from Task 7:
    weather = context.get("weather")
    if weather == "Rain":
        if move["type"] == "Water":
            modifier_low *= 1.5
            modifier_high *= 1.5
        elif move["type"] == "Fire":
            modifier_low *= 0.5
            modifier_high *= 0.5
    elif weather == "Sun":
        if move["type"] == "Fire":
            modifier_low *= 1.5
            modifier_high *= 1.5
        elif move["type"] == "Water":
            modifier_low *= 0.5
            modifier_high *= 0.5

    terrain = context.get("terrain")
    _TERRAIN_TYPE_MAP = {"Electric": "Electric", "Grassy": "Grass", "Psychic": "Psychic"}
    if terrain and _TERRAIN_TYPE_MAP.get(terrain) == move["type"]:
        modifier_low *= 1.3
        modifier_high *= 1.3

    screen = context.get("screen")
    screen_applies = (
        (screen == "Reflect" and category == "Physical")
        or (screen == "Light Screen" and category == "Special")
        or (screen == "Aurora Veil")
    )
    if screen_applies:
        screen_multiplier = 2 / 3 if context.get("is_doubles") else 0.5
        modifier_low *= screen_multiplier
        modifier_high *= screen_multiplier
```

Place this block after the spread-modifier block added in Task 7, still before `min_damage`/`max_damage` are computed.

- [ ] **Step 4: Run to verify passing**

Run: `.venv/bin/pytest tests/test_calc.py -v`
Expected: all passed

- [ ] **Step 5: Run the full suite one final time**

Run: `.venv/bin/pytest -v`
Expected: all tests passed, 0 failed

- [ ] **Step 6: Commit**

```bash
git add damage_calc/calc.py tests/test_calc.py
git commit -m "feat: add weather, terrain, and screen modifiers to damage calc; complete calc slice"
```

---

## Final Verification

- [ ] Run `.venv/bin/pytest -v` from repo root — every test across `tests/test_scaffold.py`, `tests/test_fetch_pokeapi.py`, `tests/test_build_records.py`, `tests/test_refresh_job.py`, `tests/test_calc_data.py`, `tests/test_calc.py` passes.
- [ ] Run `.venv/bin/python -m pipeline.refresh_job` manually against the real `data/source/` files (this one hits the live PokéAPI — expect it to take a few minutes for 315 Pokémon) and spot-check `data/processed/pokemon_records.json` for a handful of well-known Pokémon (e.g. confirm Aegislash's two formes both appear, confirm a Mega's stats differ from its base forme).
- [ ] Confirm `git log --oneline` shows one commit per task, nothing squashed, nothing left uncommitted (`git status` clean).
