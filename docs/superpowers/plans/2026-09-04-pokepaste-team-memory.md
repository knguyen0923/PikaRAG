# Pokepaste Import + Team Memory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a Discord user load "my team" / "opponent's team" (via a full Pokepaste import or incremental scouting) and have `/calc` and `/ask` automatically draw on that stored data.

**Architecture:** A pure text parser (`bot/pokepaste.py`), a pure in-memory per-user store with merge/lookup/override-resolution helpers (`bot/team_store.py`), Discord-facing pure response functions (`bot/commands/team.py`), and a thin wiring layer in `bot/main.py` that does network fetch (URL → raw text) and calls into the pure pieces — same layering `/stats`, `/moves`, `/calc` already use.

**Tech Stack:** Python 3.9, discord.py `app_commands` (including `typing.Literal` for choice params), `requests` (already a dependency), pytest.

**Spec:** `docs/superpowers/specs/2026-09-04-pokepaste-team-memory-design.md`

## Global Constraints

- Team storage is in-memory only, keyed by Discord user ID — no disk/database writes. A bot restart clears everything. (Spec: "Scope", "Data model")
- Both `mine` and `opponent` lists are capped at 6 Pokemon. (Spec: "Data model", "Error handling")
- `/import` REPLACES a side outright. `/scout` MERGES into a side (adds a new species, or updates item/ability/tera_type/moves on an existing one without touching its other fields). (Spec: "Commands")
- `/calc` per-field precedence: explicit Discord option > stored team member's value > neutral default. If a species is stored on both `mine` and `opponent` for a user, `mine` wins the lookup. (Spec: "Feeding /calc")
- Real (non-31) IVs are parsed/stored for display only — never fed into `calculate_damage`. (Spec: "Out of scope")
- `calc_response`'s and (apart from one new optional parameter) `ask_response`'s existing signatures and tests do not change. All new "does this match a stored team member" logic lives in `bot/team_store.py` / `bot/main.py`, never inside those two functions. (Spec: "Feeding /calc", "Feeding /ask")
- TDD: write the failing test, watch it fail, write minimal code, watch it pass, then commit — every step in every task below.
- This project has no test-isolation fixture for module-level state. Tests against `bot/team_store.py` must use a distinct literal user-ID integer per test (never reuse one across tests) since the store is a module-level dict shared by the whole test session.

---

### Task 1: Pokepaste text parser

**Files:**
- Create: `bot/pokepaste.py`
- Test: `tests/test_pokepaste.py`

**Interfaces:**
- Produces: `parse_pokepaste(text: str) -> list[dict]`, `PokepasteParseError(Exception)`. Each returned dict has exactly these keys: `species` (str), `nickname` (str|None), `gender` (str|None, `"M"`/`"F"`), `item` (str|None), `ability` (str|None), `level` (int), `tera_type` (str|None), `evs` (dict with keys `hp`/`attack`/`defense`/`sp_attack`/`sp_defense`/`speed`, ints), `ivs` (same six keys, ints), `nature` (str), `moves` (list[str], 0-4 entries).

- [ ] **Step 1: Write failing tests for a single full-spec block**

Create `tests/test_pokepaste.py`:

```python
import pytest
from bot.pokepaste import parse_pokepaste, PokepasteParseError

_FULL_SPEC = """\
Iron Hands @ Assault Vest
Ability: Quark Drive
Level: 50
Tera Type: Water
EVs: 236 HP / 4 Atk / 4 Def / 116 SpD / 148 Spe
Adamant Nature
- Fake Out
- Wild Charge
- Drain Punch
- Heavy Slam
"""


def test_parses_species_item_and_moves():
    members = parse_pokepaste(_FULL_SPEC)

    assert len(members) == 1
    member = members[0]
    assert member["species"] == "Iron Hands"
    assert member["item"] == "Assault Vest"
    assert member["moves"] == ["Fake Out", "Wild Charge", "Drain Punch", "Heavy Slam"]


def test_parses_ability_level_tera_and_nature():
    member = parse_pokepaste(_FULL_SPEC)[0]

    assert member["ability"] == "Quark Drive"
    assert member["level"] == 50
    assert member["tera_type"] == "Water"
    assert member["nature"] == "Adamant"


def test_parses_evs_and_defaults_ivs_to_31():
    member = parse_pokepaste(_FULL_SPEC)[0]

    assert member["evs"] == {
        "hp": 236, "attack": 4, "defense": 4,
        "sp_attack": 0, "sp_defense": 116, "speed": 148,
    }
    assert member["ivs"] == {
        "hp": 31, "attack": 31, "defense": 31,
        "sp_attack": 31, "sp_defense": 31, "speed": 31,
    }
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_pokepaste.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bot.pokepaste'`

- [ ] **Step 3: Implement the parser**

Create `bot/pokepaste.py`:

```python
import re

_STAT_ABBREV = {
    "hp": "hp", "atk": "attack", "def": "defense",
    "spa": "sp_attack", "spd": "sp_defense", "spe": "speed",
}
_DEFAULT_EVS = {"hp": 0, "attack": 0, "defense": 0, "sp_attack": 0, "sp_defense": 0, "speed": 0}
_DEFAULT_IVS = {"hp": 31, "attack": 31, "defense": 31, "sp_attack": 31, "sp_defense": 31, "speed": 31}
_DEFAULT_NATURE = "Hardy"
_DEFAULT_LEVEL = 50
_IGNORED_PREFIXES = ("Shiny:", "Happiness:", "Ball:")


class PokepasteParseError(Exception):
    pass


def _parse_stat_line(line: str) -> dict:
    stats = {}
    for part in line.split("/"):
        part = part.strip()
        if not part:
            continue
        amount_str, abbrev = part.split(" ", 1)
        stat_name = _STAT_ABBREV[abbrev.strip().lower()]
        stats[stat_name] = int(amount_str.strip())
    return stats


def _parse_first_line(line: str) -> dict:
    item = None
    if " @ " in line:
        line, item = line.rsplit(" @ ", 1)
        item = item.strip()
    line = line.strip()

    gender = None
    gender_match = re.search(r"\((M|F)\)\s*$", line)
    if gender_match:
        gender = gender_match.group(1)
        line = line[: gender_match.start()].strip()

    species_match = re.search(r"\(([^)]+)\)\s*$", line)
    if species_match:
        nickname = line[: species_match.start()].strip()
        species = species_match.group(1).strip()
    else:
        nickname = None
        species = line.strip()

    if not species:
        raise PokepasteParseError(f"Could not find a species name in: '{line}'")

    return {"species": species, "nickname": nickname, "gender": gender, "item": item}


def _parse_block(block: str) -> dict:
    lines = [ln.strip() for ln in block.strip().splitlines() if ln.strip()]
    if not lines:
        raise PokepasteParseError("Empty Pokemon block.")

    first = _parse_first_line(lines[0])
    member = {
        "species": first["species"],
        "nickname": first["nickname"],
        "gender": first["gender"],
        "item": first["item"],
        "ability": None,
        "level": _DEFAULT_LEVEL,
        "tera_type": None,
        "evs": dict(_DEFAULT_EVS),
        "ivs": dict(_DEFAULT_IVS),
        "nature": _DEFAULT_NATURE,
        "moves": [],
    }

    for line in lines[1:]:
        if line.startswith(_IGNORED_PREFIXES):
            continue
        elif line.startswith("Ability:"):
            member["ability"] = line.split(":", 1)[1].strip()
        elif line.startswith("Level:"):
            member["level"] = int(line.split(":", 1)[1].strip())
        elif line.startswith("Tera Type:"):
            member["tera_type"] = line.split(":", 1)[1].strip()
        elif line.startswith("EVs:"):
            member["evs"].update(_parse_stat_line(line.split(":", 1)[1]))
        elif line.startswith("IVs:"):
            member["ivs"].update(_parse_stat_line(line.split(":", 1)[1]))
        elif line.endswith(" Nature"):
            member["nature"] = line[: -len(" Nature")].strip()
        elif line.startswith("- "):
            if len(member["moves"]) >= 4:
                raise PokepasteParseError(f"More than 4 moves for '{member['species']}'.")
            member["moves"].append(line[2:].strip())
        else:
            raise PokepasteParseError(f"Unrecognized line for '{member['species']}': '{line}'")

    return member


def parse_pokepaste(text: str) -> list:
    blocks = [b for b in re.split(r"\n\s*\n", text.strip()) if b.strip()]
    if not blocks:
        raise PokepasteParseError("No Pokemon found in the given text.")
    if len(blocks) > 6:
        raise PokepasteParseError(f"A team can have at most 6 Pokemon, got {len(blocks)}.")

    members = []
    for i, block in enumerate(blocks, start=1):
        try:
            members.append(_parse_block(block))
        except PokepasteParseError as e:
            raise PokepasteParseError(f"Block {i}: {e}") from e
    return members
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_pokepaste.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Write failing tests for nickname, gender, and omitted-field defaults**

Add to `tests/test_pokepaste.py`:

```python
def test_parses_nickname_and_gender():
    member = parse_pokepaste("Bob (Flutter Mane) (F) @ Focus Sash\n- Moonblast\n")[0]

    assert member["nickname"] == "Bob"
    assert member["species"] == "Flutter Mane"
    assert member["gender"] == "F"


def test_no_nickname_when_no_parenthetical():
    member = parse_pokepaste("Garchomp @ Life Orb\n- Earthquake\n")[0]

    assert member["nickname"] is None
    assert member["species"] == "Garchomp"


def test_omitted_optional_fields_use_neutral_defaults():
    member = parse_pokepaste("Garchomp\n- Earthquake\n")[0]

    assert member["item"] is None
    assert member["ability"] is None
    assert member["tera_type"] is None
    assert member["nature"] == "Hardy"
    assert member["evs"] == {"hp": 0, "attack": 0, "defense": 0, "sp_attack": 0, "sp_defense": 0, "speed": 0}
    assert member["level"] == 50
```

- [ ] **Step 6: Run tests to verify they fail or pass**

Run: `pytest tests/test_pokepaste.py -v`
Expected: These three should already PASS given the Step 3 implementation (no new code needed) — this step is a verification checkpoint, not a red/green cycle. If any fails, fix `bot/pokepaste.py` before moving on.

- [ ] **Step 7: Write failing tests for multiple blocks and malformed input**

Add to `tests/test_pokepaste.py`:

```python
_TWO_MON_TEAM = """\
Garchomp @ Life Orb
- Earthquake

Flutter Mane @ Focus Sash
- Moonblast
"""


def test_parses_multiple_blank_line_separated_blocks():
    members = parse_pokepaste(_TWO_MON_TEAM)

    assert [m["species"] for m in members] == ["Garchomp", "Flutter Mane"]


def test_more_than_six_blocks_raises():
    seven_mon_text = "\n\n".join(f"Pokemon{i}\n- Tackle" for i in range(7))

    with pytest.raises(PokepasteParseError, match="at most 6"):
        parse_pokepaste(seven_mon_text)


def test_unrecognized_line_raises_with_block_number():
    with pytest.raises(PokepasteParseError, match="Block 1"):
        parse_pokepaste("Foo @ Life Orb\n@#$%\n- Earthquake\n")


def test_empty_text_raises():
    with pytest.raises(PokepasteParseError, match="No Pokemon found"):
        parse_pokepaste("")
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `pytest tests/test_pokepaste.py -v`
Expected: PASS (10 passed)

- [ ] **Step 9: Commit**

```bash
git add bot/pokepaste.py tests/test_pokepaste.py
git commit -m "feat(bot): add Pokepaste text parser"
```

---

### Task 2: Pokepaste URL fetch

**Files:**
- Create: `bot/pokepaste_fetch.py`
- Test: `tests/test_pokepaste_fetch.py`

**Interfaces:**
- Produces: `resolve_pokepaste_text(pokepaste: str, session=None) -> str`, `PokepasteFetchError(Exception)`.
- Consumes: nothing from other tasks (only `requests`, already a project dependency — see `pipeline/fetch_pokeapi.py` for the same injectable-`session` pattern this mirrors).

- [ ] **Step 1: Write failing tests**

Create `tests/test_pokepaste_fetch.py`:

```python
import pytest
import requests
from unittest.mock import MagicMock
from bot.pokepaste_fetch import resolve_pokepaste_text, PokepasteFetchError


def test_raw_text_passes_through_unchanged():
    result = resolve_pokepaste_text("Garchomp @ Life Orb\n- Earthquake\n")

    assert result == "Garchomp @ Life Orb\n- Earthquake\n"


def test_url_is_fetched_from_the_raw_endpoint():
    session = MagicMock()
    response = MagicMock(status_code=200, text="Garchomp @ Life Orb\n- Earthquake\n")
    session.get.return_value = response

    result = resolve_pokepaste_text("https://pokepast.es/abc123", session=session)

    assert result == "Garchomp @ Life Orb\n- Earthquake\n"
    session.get.assert_called_once_with("https://pokepast.es/abc123/raw")


def test_trailing_slash_url_still_resolves_to_raw_endpoint():
    session = MagicMock()
    session.get.return_value = MagicMock(status_code=200, text="Garchomp\n- Earthquake\n")

    resolve_pokepaste_text("https://pokepast.es/abc123/", session=session)

    session.get.assert_called_once_with("https://pokepast.es/abc123/raw")


def test_http_error_raises_pokepaste_fetch_error():
    session = MagicMock()
    session.get.return_value = MagicMock(status_code=404)

    with pytest.raises(PokepasteFetchError, match="404"):
        resolve_pokepaste_text("https://pokepast.es/nonexistent", session=session)


def test_network_error_raises_pokepaste_fetch_error():
    session = MagicMock()
    session.get.side_effect = requests.exceptions.ConnectionError("refused")

    with pytest.raises(PokepasteFetchError, match="Network error"):
        resolve_pokepaste_text("https://pokepast.es/abc123", session=session)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_pokepaste_fetch.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bot.pokepaste_fetch'`

- [ ] **Step 3: Implement the fetcher**

Create `bot/pokepaste_fetch.py`:

```python
import re

import requests

_URL_PATTERN = re.compile(r"^https?://", re.IGNORECASE)


class PokepasteFetchError(Exception):
    pass


def resolve_pokepaste_text(pokepaste: str, session=None) -> str:
    """Return raw Showdown-format team text.

    If `pokepaste` is a pokepast.es URL, fetches its plain-text export from
    the `/raw` route. Otherwise returns it unchanged (already raw text).
    """
    pokepaste = pokepaste.strip()
    if not _URL_PATTERN.match(pokepaste):
        return pokepaste

    session = session or requests.Session()
    url = pokepaste.rstrip("/") + "/raw"
    try:
        response = session.get(url)
    except requests.exceptions.RequestException as e:
        raise PokepasteFetchError(f"Network error fetching '{pokepaste}': {e}") from e
    if response.status_code != 200:
        raise PokepasteFetchError(f"Could not fetch '{pokepaste}' (got HTTP {response.status_code}).")
    return response.text
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_pokepaste_fetch.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add bot/pokepaste_fetch.py tests/test_pokepaste_fetch.py
git commit -m "feat(bot): fetch Pokepaste text from a pokepast.es URL"
```

---

### Task 3: In-memory team store

**Files:**
- Create: `bot/team_store.py`
- Test: `tests/test_team_store.py`

**Interfaces:**
- Produces:
  - `store_team(user_id: int, side: str, members: list) -> None` — replaces `side` outright; raises `ValueError` if `len(members) > 6`.
  - `get_team(user_id: int, side: str) -> list` — returns a copy of the stored list (empty list if nothing stored).
  - `merge_scout(user_id: int, side: str, member: dict) -> dict` — see Task 1's member dict shape. Adds `member` if its species isn't already stored on `side` (raising `ValueError` if `side` already has 6 distinct species); otherwise updates the existing entry's `item`/`ability`/`tera_type` from any non-`None` fields on `member`, and appends any of `member["moves"]` not already present (capped at 4 total). Returns the final stored dict for that species.
  - `find_team_member(user_id: int, name: str) -> dict | None` — case-insensitive species match, checking `mine` before `opponent`.
  - `resolve_calc_overrides(user_id: int, name: str, explicit_evs: str | None, explicit_nature: str | None, explicit_item: str | None, explicit_tera: str | None) -> tuple[str, str, str | None, str | None]` — returns `(evs, nature, item, tera)` using explicit > stored team member > neutral default (`"0/0/0/0/0/0"`, `"Hardy"`, `None`, `None`) precedence. The `evs` string uses the same `"hp/atk/def/spa/spd/spe"` order `bot/commands/calc.py`'s `_parse_evs` already expects.
- Consumes: nothing from other tasks (pure, self-contained module).

- [ ] **Step 1: Write failing tests for store/get/replace**

Create `tests/test_team_store.py`:

```python
from bot.team_store import store_team, get_team, merge_scout, find_team_member, resolve_calc_overrides

_GARCHOMP = {
    "species": "Garchomp", "nickname": None, "gender": None, "item": "Life Orb",
    "ability": "Rough Skin", "level": 50, "tera_type": "Dragon",
    "evs": {"hp": 4, "attack": 252, "defense": 0, "sp_attack": 0, "sp_defense": 0, "speed": 252},
    "ivs": {"hp": 31, "attack": 31, "defense": 31, "sp_attack": 31, "sp_defense": 31, "speed": 31},
    "nature": "Jolly", "moves": ["Earthquake", "Dragon Claw"],
}


def test_get_team_is_empty_for_a_user_with_nothing_stored():
    assert get_team(101, "mine") == []


def test_store_team_then_get_team_round_trips():
    store_team(102, "mine", [_GARCHOMP])

    assert get_team(102, "mine") == [_GARCHOMP]


def test_store_team_replaces_the_previous_contents():
    store_team(103, "mine", [_GARCHOMP])
    store_team(103, "mine", [])

    assert get_team(103, "mine") == []


def test_store_team_rejects_more_than_six():
    seven = [dict(_GARCHOMP, species=f"Mon{i}") for i in range(7)]

    try:
        store_team(104, "mine", seven)
        assert False, "expected ValueError"
    except ValueError as e:
        assert "6" in str(e)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_team_store.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bot.team_store'`

- [ ] **Step 3: Implement store/get**

Create `bot/team_store.py`:

```python
from typing import Optional

_MAX_TEAM_SIZE = 6
_DEFAULT_EVS_STRING = "0/0/0/0/0/0"
_DEFAULT_NATURE = "Hardy"
_EVS_STAT_ORDER = ["hp", "attack", "defense", "sp_attack", "sp_defense", "speed"]

_store: dict = {}


def _side_list(user_id: int, side: str) -> list:
    return _store.setdefault(user_id, {}).setdefault(side, [])


def store_team(user_id: int, side: str, members: list) -> None:
    if len(members) > _MAX_TEAM_SIZE:
        raise ValueError(f"A team can have at most {_MAX_TEAM_SIZE} Pokemon, got {len(members)}.")
    _store.setdefault(user_id, {})[side] = list(members)


def get_team(user_id: int, side: str) -> list:
    return list(_store.get(user_id, {}).get(side, []))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_team_store.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Write failing tests for merge_scout**

Add to `tests/test_team_store.py`:

```python
def test_merge_scout_adds_a_new_species():
    merge_scout(201, "opponent", dict(_GARCHOMP, moves=[]))

    assert get_team(201, "opponent") == [dict(_GARCHOMP, moves=[])]


def test_merge_scout_updates_item_on_an_existing_species_without_touching_other_fields():
    merge_scout(202, "opponent", dict(_GARCHOMP, item=None, moves=[]))

    merge_scout(202, "opponent", {
        "species": "Garchomp", "nickname": None, "gender": None,
        "item": "Focus Sash", "ability": None, "level": 50, "tera_type": None,
        "evs": {"hp": 0, "attack": 0, "defense": 0, "sp_attack": 0, "sp_defense": 0, "speed": 0},
        "ivs": {"hp": 31, "attack": 31, "defense": 31, "sp_attack": 31, "sp_defense": 31, "speed": 31},
        "nature": "Hardy", "moves": [],
    })

    stored = get_team(202, "opponent")[0]
    assert stored["item"] == "Focus Sash"
    assert stored["ability"] == "Rough Skin"  # untouched: the second call passed None


def test_merge_scout_adds_new_moves_without_dropping_known_ones():
    merge_scout(203, "opponent", dict(_GARCHOMP, moves=["Earthquake"]))

    merge_scout(203, "opponent", {
        "species": "Garchomp", "nickname": None, "gender": None,
        "item": None, "ability": None, "level": 50, "tera_type": None,
        "evs": {"hp": 0, "attack": 0, "defense": 0, "sp_attack": 0, "sp_defense": 0, "speed": 0},
        "ivs": {"hp": 31, "attack": 31, "defense": 31, "sp_attack": 31, "sp_defense": 31, "speed": 31},
        "nature": "Hardy", "moves": ["Dragon Claw"],
    })

    assert get_team(203, "opponent")[0]["moves"] == ["Earthquake", "Dragon Claw"]


def test_merge_scout_rejects_a_seventh_distinct_species():
    for i in range(6):
        merge_scout(204, "opponent", dict(_GARCHOMP, species=f"Mon{i}", moves=[]))

    try:
        merge_scout(204, "opponent", dict(_GARCHOMP, species="Mon6", moves=[]))
        assert False, "expected ValueError"
    except ValueError as e:
        assert "6" in str(e)
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `pytest tests/test_team_store.py -v`
Expected: FAIL — `merge_scout` not defined.

- [ ] **Step 7: Implement merge_scout**

Add to `bot/team_store.py`:

```python
def merge_scout(user_id: int, side: str, member: dict) -> dict:
    team = _side_list(user_id, side)
    target = member["species"].strip().lower()
    for existing in team:
        if existing["species"].strip().lower() == target:
            for field in ("item", "ability", "tera_type"):
                if member.get(field) is not None:
                    existing[field] = member[field]
            for move in member.get("moves", []):
                if move not in existing["moves"] and len(existing["moves"]) < 4:
                    existing["moves"].append(move)
            return existing

    if len(team) >= _MAX_TEAM_SIZE:
        raise ValueError(f"'{side}' already has {_MAX_TEAM_SIZE} Pokemon -- nothing more can be added.")
    team.append(member)
    return member
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `pytest tests/test_team_store.py -v`
Expected: PASS (8 passed)

- [ ] **Step 9: Write failing tests for find_team_member and resolve_calc_overrides**

Add to `tests/test_team_store.py`:

```python
def test_find_team_member_matches_case_insensitively():
    store_team(301, "mine", [_GARCHOMP])

    assert find_team_member(301, "garchomp")["species"] == "Garchomp"


def test_find_team_member_checks_mine_before_opponent():
    store_team(302, "mine", [dict(_GARCHOMP, item="Life Orb")])
    store_team(302, "opponent", [dict(_GARCHOMP, item="Focus Sash")])

    assert find_team_member(302, "Garchomp")["item"] == "Life Orb"


def test_find_team_member_returns_none_when_not_found():
    assert find_team_member(303, "Nonexistent") is None


def test_resolve_calc_overrides_uses_neutral_defaults_when_nothing_stored_or_explicit():
    evs, nature, item, tera = resolve_calc_overrides(401, "Nonexistent", None, None, None, None)

    assert evs == "0/0/0/0/0/0"
    assert nature == "Hardy"
    assert item is None
    assert tera is None


def test_resolve_calc_overrides_falls_back_to_stored_team_member():
    store_team(402, "mine", [_GARCHOMP])

    evs, nature, item, tera = resolve_calc_overrides(402, "Garchomp", None, None, None, None)

    assert evs == "4/252/0/0/0/252"
    assert nature == "Jolly"
    assert item == "Life Orb"
    assert tera == "Dragon"


def test_resolve_calc_overrides_explicit_value_wins_over_stored_team_member():
    store_team(403, "mine", [_GARCHOMP])

    _, _, item, _ = resolve_calc_overrides(403, "Garchomp", None, None, "Choice Band", None)

    assert item == "Choice Band"
```

- [ ] **Step 10: Run tests to verify they fail**

Run: `pytest tests/test_team_store.py -v`
Expected: FAIL — `find_team_member`/`resolve_calc_overrides` not defined.

- [ ] **Step 11: Implement find_team_member and resolve_calc_overrides**

Add to `bot/team_store.py`:

```python
def find_team_member(user_id: int, name: str) -> Optional[dict]:
    target = name.strip().lower()
    for side in ("mine", "opponent"):
        for member in _side_list(user_id, side):
            if member["species"].strip().lower() == target:
                return member
    return None


def resolve_calc_overrides(
    user_id: int,
    name: str,
    explicit_evs: Optional[str],
    explicit_nature: Optional[str],
    explicit_item: Optional[str],
    explicit_tera: Optional[str],
) -> tuple:
    member = find_team_member(user_id, name)

    evs = explicit_evs
    if evs is None and member is not None:
        e = member["evs"]
        evs = "/".join(str(e[stat]) for stat in _EVS_STAT_ORDER)
    if evs is None:
        evs = _DEFAULT_EVS_STRING

    nature = explicit_nature
    if nature is None and member is not None:
        nature = member["nature"]
    if nature is None:
        nature = _DEFAULT_NATURE

    item = explicit_item
    if item is None and member is not None:
        item = member["item"]

    tera = explicit_tera
    if tera is None and member is not None:
        tera = member["tera_type"]

    return evs, nature, item, tera
```

- [ ] **Step 12: Run tests to verify they pass**

Run: `pytest tests/test_team_store.py -v`
Expected: PASS (14 passed)

- [ ] **Step 13: Commit**

```bash
git add bot/team_store.py tests/test_team_store.py
git commit -m "feat(bot): add in-memory per-user team store"
```

---

### Task 4: Team commands (import/scout/view response functions)

**Files:**
- Create: `bot/commands/team.py`
- Test: `tests/test_bot_team.py`

**Interfaces:**
- Consumes: `bot.pokepaste.parse_pokepaste`, `bot.pokepaste.PokepasteParseError` (Task 1); `bot.team_store.store_team`, `bot.team_store.merge_scout`, `bot.team_store.get_team` (Task 3); `bot.pokemon_lookup.find_record`, `bot.pokemon_lookup.suggest_names` (existing module).
- Produces:
  - `import_team_response(records: list, moves: list, user_id: int, side: str, pokepaste_text: str) -> str`
  - `scout_response(records: list, moves: list, user_id: int, species: str, item=None, ability=None, tera_type=None, move1=None, move2=None, move3=None, move4=None, side: str = "opponent") -> str`
  - `view_team_response(user_id: int, side: str) -> str`
  - `format_team_block(team: list, label: str) -> str` — returns `""` for an empty `team`; otherwise a multi-line block starting with `f"{label}:"`. Used by both `view_team_response` and (in Task 6) `/ask`'s context-building.

- [ ] **Step 1: Write failing tests for format_team_block and view_team_response**

Create `tests/test_bot_team.py`:

```python
from bot.commands.team import (
    import_team_response, scout_response, view_team_response, format_team_block,
)

_ABOMASNOW = {
    "name": "Abomasnow", "types": ["Grass", "Ice"],
    "base_stats": {"hp": 90, "attack": 92, "defense": 75, "sp_attack": 92, "sp_defense": 85, "speed": 60},
    "abilities": ["Snow Warning", "Soundproof"], "learnset": ["Blizzard", "Wood Hammer"], "legal_in": ["M-B"],
}
_GYARADOS = {
    "name": "Gyarados", "types": ["Water", "Flying"],
    "base_stats": {"hp": 95, "attack": 125, "defense": 79, "sp_attack": 60, "sp_defense": 100, "speed": 81},
    "abilities": ["Intimidate"], "learnset": ["Waterfall", "Dragon Dance"], "legal_in": ["M-B"],
}
_RECORDS = [_ABOMASNOW, _GYARADOS]

_ICE_BEAM = {"name": "Ice Beam", "type": "Ice", "category": "Special", "power": 90, "accuracy": 100, "pp": 12, "effect": None}
_WOOD_HAMMER = {"name": "Wood Hammer", "type": "Grass", "category": "Physical", "power": 120, "accuracy": 100, "pp": 15, "effect": None}
_MOVES = [_ICE_BEAM, _WOOD_HAMMER]

_ABOMASNOW_TEAM_MEMBER = {
    "species": "Abomasnow", "nickname": None, "gender": None, "item": "Focus Sash",
    "ability": "Snow Warning", "level": 50, "tera_type": "Ice",
    "evs": {"hp": 0, "attack": 0, "defense": 0, "sp_attack": 0, "sp_defense": 0, "speed": 0},
    "ivs": {"hp": 31, "attack": 31, "defense": 31, "sp_attack": 31, "sp_defense": 31, "speed": 31},
    "nature": "Hardy", "moves": ["Wood Hammer"],
}


def test_format_team_block_is_empty_string_for_no_team():
    assert format_team_block([], "Your team") == ""


def test_format_team_block_lists_each_member():
    block = format_team_block([_ABOMASNOW_TEAM_MEMBER], "Your team")

    assert block.startswith("Your team:")
    assert "Abomasnow" in block
    assert "Focus Sash" in block
    assert "Wood Hammer" in block


def test_view_team_response_reports_no_team_loaded():
    response = view_team_response(501, "mine")

    assert "no team" in response.lower()
    assert "/import" in response or "/scout" in response
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_bot_team.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bot.commands.team'`

- [ ] **Step 3: Implement format_team_block and view_team_response**

Create `bot/commands/team.py`:

```python
from bot.pokemon_lookup import find_record, suggest_names
from bot.pokepaste import parse_pokepaste, PokepasteParseError
from bot.team_store import get_team, merge_scout, store_team

_SIDE_LABELS = {"mine": "Your team", "opponent": "Opponent's team"}


def format_team_block(team: list, label: str) -> str:
    if not team:
        return ""
    lines = [f"{label}:"]
    for member in team:
        item = f" @ {member['item']}" if member["item"] else ""
        tera = f" -- Tera {member['tera_type']}" if member["tera_type"] else ""
        moves = ", ".join(member["moves"]) if member["moves"] else "no known moves"
        lines.append(f"- {member['species']}{item}{tera} -- {member['nature']} -- {moves}")
    return "\n".join(lines)


def view_team_response(user_id: int, side: str) -> str:
    team = get_team(user_id, side)
    if not team:
        return f"No team loaded for '{side}'. Use /import or /scout to load one."
    return format_team_block(team, _SIDE_LABELS[side])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_bot_team.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Write failing tests for import_team_response**

Add to `tests/test_bot_team.py`:

```python
_VALID_PASTE = """\
Abomasnow @ Focus Sash
Ability: Snow Warning
Tera Type: Ice
- Wood Hammer
"""


def test_import_team_response_stores_and_confirms():
    response = import_team_response(_RECORDS, _MOVES, 601, "mine", _VALID_PASTE)

    assert "Abomasnow" in response
    assert get_team(601, "mine")[0]["species"] == "Abomasnow"


def test_import_team_response_flags_unmatched_species():
    response = import_team_response(_RECORDS, _MOVES, 602, "mine", "Nonexistamon\n- Tackle\n")

    assert "not recognized" in response.lower()
    assert "Nonexistamon" in response


def test_import_team_response_flags_unmatched_moves():
    response = import_team_response(_RECORDS, _MOVES, 603, "mine", "Abomasnow\n- NotAMove\n")

    assert "not recognized" in response.lower()
    assert "NotAMove" in response


def test_import_team_response_reports_a_parse_error_without_storing_anything():
    response = import_team_response(_RECORDS, _MOVES, 604, "mine", "")

    assert "could not parse" in response.lower()
    assert get_team(604, "mine") == []
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `pytest tests/test_bot_team.py -v`
Expected: FAIL — `import_team_response` not defined.

- [ ] **Step 7: Implement import_team_response (and the shared validation helper)**

Add to `bot/commands/team.py`:

```python
def _validate_member(records: list, moves: list, member: dict) -> list:
    warnings = []
    if find_record(records, member["species"]) is None:
        suggestions = suggest_names(records, member["species"])
        if suggestions:
            warnings.append(f"'{member['species']}' not recognized. Did you mean: {', '.join(suggestions)}?")
        else:
            warnings.append(f"'{member['species']}' not recognized.")
    for move_name in member["moves"]:
        if find_record(moves, move_name) is None:
            suggestions = suggest_names(moves, move_name)
            if suggestions:
                warnings.append(f"Move '{move_name}' not recognized. Did you mean: {', '.join(suggestions)}?")
            else:
                warnings.append(f"Move '{move_name}' not recognized.")
    return warnings


def _format_warnings(warnings: list) -> list:
    if not warnings:
        return []
    return ["", "Warnings:"] + [f"- {w}" for w in warnings]


def import_team_response(records: list, moves: list, user_id: int, side: str, pokepaste_text: str) -> str:
    try:
        members = parse_pokepaste(pokepaste_text)
    except PokepasteParseError as e:
        return f"Could not parse team: {e}"

    warnings = []
    for member in members:
        warnings.extend(_validate_member(records, moves, member))

    try:
        store_team(user_id, side, members)
    except ValueError as e:
        return str(e)

    label = "your" if side == "mine" else "the opponent's"
    lines = [f"Loaded {len(members)} Pokemon into {label} team:"]
    lines.extend(f"- {m['species']}" for m in members)
    lines.extend(_format_warnings(warnings))
    return "\n".join(lines)
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `pytest tests/test_bot_team.py -v`
Expected: PASS (7 passed)

- [ ] **Step 9: Write failing tests for scout_response**

Add to `tests/test_bot_team.py`:

```python
def test_scout_response_adds_a_new_pokemon_with_partial_info():
    response = scout_response(_RECORDS, _MOVES, 701, "Abomasnow", side="opponent")

    assert "Abomasnow" in response
    assert get_team(701, "opponent")[0]["species"] == "Abomasnow"
    assert get_team(701, "opponent")[0]["moves"] == []


def test_scout_response_merges_a_newly_seen_move_into_an_existing_entry():
    scout_response(_RECORDS, _MOVES, 702, "Abomasnow", side="opponent")

    response = scout_response(_RECORDS, _MOVES, 702, "Abomasnow", move1="Wood Hammer", side="opponent")

    assert get_team(702, "opponent")[0]["moves"] == ["Wood Hammer"]
    assert "Wood Hammer" in response


def test_scout_response_defaults_to_opponent_side_when_side_is_not_given():
    # No `side` kwarg here at all -- this is what actually proves the default,
    # unlike a call that explicitly passes side="opponent".
    scout_response(_RECORDS, _MOVES, 703, "Abomasnow")

    assert get_team(703, "opponent")[0]["species"] == "Abomasnow"
    assert get_team(703, "mine") == []


def test_scout_response_flags_unmatched_species():
    response = scout_response(_RECORDS, _MOVES, 704, "Nonexistamon", side="opponent")

    assert "not recognized" in response.lower()
```

- [ ] **Step 10: Run tests to verify they fail**

Run: `pytest tests/test_bot_team.py -v`
Expected: FAIL — `scout_response` not defined.

- [ ] **Step 11: Implement scout_response**

Add to `bot/commands/team.py`:

```python
_EMPTY_EVS = {"hp": 0, "attack": 0, "defense": 0, "sp_attack": 0, "sp_defense": 0, "speed": 0}
_MAX_IVS = {"hp": 31, "attack": 31, "defense": 31, "sp_attack": 31, "sp_defense": 31, "speed": 31}


def scout_response(
    records: list,
    moves: list,
    user_id: int,
    species: str,
    item=None,
    ability=None,
    tera_type=None,
    move1=None,
    move2=None,
    move3=None,
    move4=None,
    side: str = "opponent",
) -> str:
    member = {
        "species": species, "nickname": None, "gender": None,
        "item": item, "ability": ability, "level": 50, "tera_type": tera_type,
        "evs": dict(_EMPTY_EVS), "ivs": dict(_MAX_IVS), "nature": "Hardy",
        "moves": [m for m in (move1, move2, move3, move4) if m],
    }
    warnings = _validate_member(records, moves, member)

    try:
        stored = merge_scout(user_id, side, member)
    except ValueError as e:
        return str(e)

    label = "your" if side == "mine" else "the opponent's"
    moves_text = ", ".join(stored["moves"]) if stored["moves"] else "no known moves"
    lines = [f"Updated {stored['species']} in {label} team -- known moves: {moves_text}."]
    lines.extend(_format_warnings(warnings))
    return "\n".join(lines)
```

- [ ] **Step 12: Run tests to verify they pass**

Run: `pytest tests/test_bot_team.py -v`
Expected: PASS (11 passed)

- [ ] **Step 13: Commit**

```bash
git add bot/commands/team.py tests/test_bot_team.py
git commit -m "feat(bot): add import/scout/view team command functions"
```

---

### Task 5: Feed team context into /ask

**Files:**
- Modify: `bot/commands/ask.py`
- Modify: `tests/test_bot_ask.py`

**Interfaces:**
- Produces (modified): `ask_response(index, answerer, question: str, n_results: int = 5, extra_context: str | None = None) -> str`, `ask_response_async(...)` with the same new parameter, passed through.
- Consumes: nothing new (no import of `team_store` here — Task 6's `bot/main.py` builds the `extra_context` string and passes it in; this task only adds the parameter and the prepend behavior).

- [ ] **Step 1: Write failing test**

Add to `tests/test_bot_ask.py` (existing file — keep its current imports and tests, add this one):

```python
def test_ask_response_prepends_extra_context_when_given():
    index = _FakeIndex(context_matches=[{"text": "Gyarados base HP: 95.", "metadata": {}}])
    answerer = _FakeAnswerer(response_text="answer")

    ask_response(index, answerer, "How bulky is Gyarados?", extra_context="Your team: Gyarados")

    question, context_block = answerer.calls[0]
    assert context_block.startswith("Your team: Gyarados")
    assert "Gyarados base HP: 95." in context_block
```

(This reuses `_FakeIndex`/`_FakeAnswerer` already defined earlier in `tests/test_bot_ask.py`.)

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_bot_ask.py -v`
Expected: FAIL with `TypeError: ask_response() got an unexpected keyword argument 'extra_context'`

- [ ] **Step 3: Implement extra_context**

Modify `bot/commands/ask.py`:

```python
import asyncio
from typing import Optional

from rag.retrieve import build_context_block


def ask_response(
    index, answerer, question: str, n_results: int = 5, extra_context: Optional[str] = None
) -> str:
    context_block = build_context_block(index, question, n_results=n_results)
    if extra_context:
        context_block = f"{extra_context}\n\n{context_block}"
    return answerer.answer(question, context_block)


async def ask_response_async(
    index, answerer, question: str, n_results: int = 5, extra_context: Optional[str] = None
) -> str:
    """Run ask_response in a worker thread so the caller's event loop stays free.

    Both index.query (CPU-bound sentence-transformer encode) and
    answerer.answer (blocking network call) are synchronous; offloading the
    whole call keeps discord.py's event loop responsive during either one.
    """
    return await asyncio.to_thread(ask_response, index, answerer, question, n_results, extra_context)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_bot_ask.py -v`
Expected: PASS (all tests in the file, including the pre-existing ones)

- [ ] **Step 5: Commit**

```bash
git add bot/commands/ask.py tests/test_bot_ask.py
git commit -m "feat(bot): let /ask accept extra grounding context"
```

---

### Task 6: Wire /import, /scout, /team into the bot; feed /calc and /ask

**Files:**
- Modify: `bot/main.py`
- Modify: `tests/test_bot_main.py`

**Interfaces:**
- Consumes: `bot.pokepaste_fetch.resolve_pokepaste_text`, `PokepasteFetchError` (Task 2); `bot.team_store.get_team`, `bot.team_store.resolve_calc_overrides` (Task 3); `bot.commands.team.import_team_response`, `scout_response`, `view_team_response`, `format_team_block` (Task 4); `ask_response_async(..., extra_context=...)` (Task 5).
- Produces: three new registered commands (`import`, `scout`, `team`) and updated `calc`/`ask` command bodies on the `app_commands.CommandTree` returned by `build_client`.

**IMPORTANT — read before editing `bot/main.py`:** the file's `/moves` command handler is named `moves_command` (NOT `moves`) — it was previously named `moves`, which shadowed the `moves` data-list parameter in `build_client`'s closure and broke `/calc` for real users. It was already fixed in a separate commit before this plan started. Do not rename it back, and give the new `import`/`scout`/`team` handlers names that don't collide with `records`/`moves`/any other closure variable (`import_team`, `scout`, `team` are all safe — none match an existing parameter name).

- [ ] **Step 1: Write failing registration tests**

Add to `tests/test_bot_main.py` (existing file, keep current imports/tests):

```python
def test_import_command_is_registered_on_the_tree():
    _client, tree = build_client()
    commands = {command.name: command for command in tree.get_commands()}

    assert "import" in commands
    assert "team" in commands["import"].description.lower()


def test_scout_command_is_registered_on_the_tree():
    _client, tree = build_client()
    commands = {command.name: command for command in tree.get_commands()}

    assert "scout" in commands
    assert "pokemon" in commands["scout"].description.lower()


def test_team_view_command_is_registered_on_the_tree():
    _client, tree = build_client()
    commands = {command.name: command for command in tree.get_commands()}

    assert "team" in commands
    assert "opponent" in commands["team"].description.lower() or "team" in commands["team"].description.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_bot_main.py -v`
Expected: FAIL — `assert "import" in commands` (and similarly for `scout`/`team`) since those commands don't exist yet.

- [ ] **Step 3: Read the current bot/main.py in full before editing**

Run: `cat bot/main.py` (or open it in an editor) so the exact current import list, `build_client` signature, and existing command bodies are in view before making the edits below — this task modifies an existing file, not a fresh one. In particular, confirm the `/moves` handler is `moves_command`, not `moves` (see the note above the Step 1 tests).

- [ ] **Step 4: Add the new imports**

At the top of `bot/main.py`, alongside the existing `bot.commands.*` imports, add:

```python
from typing import Literal, Optional

from bot.commands.team import (
    format_team_block,
    import_team_response,
    scout_response,
    view_team_response,
)
from bot.pokepaste_fetch import PokepasteFetchError, resolve_pokepaste_text
from bot.team_store import get_team, resolve_calc_overrides
```

(If `Optional` is already imported from `typing`, extend that existing import line with `Literal` instead of adding a second `from typing import ...` line.)

- [ ] **Step 5: Register /import, /scout, /team inside build_client**

Inside `build_client`, alongside the existing `@tree.command(...)` blocks for `ping`/`ask`/`stats`/`moves_command`/`calc`, add:

```python
    @tree.command(name="import", description="Import a full Pokemon team from Pokepaste text or a pokepast.es URL.")
    async def import_team(
        interaction: discord.Interaction,
        side: Literal["mine", "opponent"],
        pokepaste: str,
    ) -> None:
        try:
            raw_text = resolve_pokepaste_text(pokepaste)
        except PokepasteFetchError as e:
            await interaction.response.send_message(str(e))
            return
        response = import_team_response(records, moves, interaction.user.id, side, raw_text)
        await interaction.response.send_message(response)

    @tree.command(name="scout", description="Add or update one Pokemon in a stored team with only what you currently know.")
    async def scout(
        interaction: discord.Interaction,
        species: str,
        item: Optional[str] = None,
        ability: Optional[str] = None,
        tera_type: Optional[str] = None,
        move1: Optional[str] = None,
        move2: Optional[str] = None,
        move3: Optional[str] = None,
        move4: Optional[str] = None,
        side: Literal["mine", "opponent"] = "opponent",
    ) -> None:
        response = scout_response(
            records, moves, interaction.user.id, species,
            item=item, ability=ability, tera_type=tera_type,
            move1=move1, move2=move2, move3=move3, move4=move4,
            side=side,
        )
        await interaction.response.send_message(response)

    @tree.command(name="team", description="View the Pokemon currently stored for your team or the opponent's team.")
    async def team(interaction: discord.Interaction, side: Literal["mine", "opponent"]) -> None:
        await interaction.response.send_message(view_team_response(interaction.user.id, side))
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_bot_main.py -v`
Expected: PASS (all tests in the file)

- [ ] **Step 7: Write a failing test for /calc's team-aware wiring**

Add to `tests/test_bot_main.py`:

```python
_CALC_TEST_RECORDS = [{
    "name": "Garchomp", "types": ["Dragon", "Ground"],
    "base_stats": {"hp": 108, "attack": 130, "defense": 95, "sp_attack": 80, "sp_defense": 85, "speed": 102},
    "abilities": ["Rough Skin"], "learnset": ["Earthquake"], "legal_in": ["M-B"],
}]
_CALC_TEST_MOVES = [
    {"name": "Earthquake", "type": "Ground", "category": "Physical", "power": 100, "accuracy": 100, "pp": 10, "effect": None},
]


def _max_damage_from_calc_response(text: str) -> int:
    return int(text.split(": ")[1].split("-")[1].split(" ")[0])


def test_calc_command_uses_a_stored_team_members_evs_and_item():
    # Exercises build_client's calc callback directly via the underlying
    # discord.app_commands.Command's `.callback`, bypassing real Discord I/O.
    from bot.team_store import store_team

    boosted_user_id, plain_user_id = 9001, 9002
    store_team(boosted_user_id, "mine", [{
        "species": "Garchomp", "nickname": None, "gender": None, "item": "Life Orb",
        "ability": "Rough Skin", "level": 50, "tera_type": None,
        "evs": {"hp": 0, "attack": 252, "defense": 0, "sp_attack": 0, "sp_defense": 0, "speed": 0},
        "ivs": {"hp": 31, "attack": 31, "defense": 31, "sp_attack": 31, "sp_defense": 31, "speed": 31},
        "nature": "Adamant", "moves": ["Earthquake"],
    }])

    _client, tree = build_client(records=_CALC_TEST_RECORDS, moves=_CALC_TEST_MOVES)
    calc_command = tree.get_command("calc")

    def _run(user_id):
        interaction = MagicMock()
        interaction.user.id = user_id
        interaction.response.send_message = AsyncMock()
        asyncio.run(calc_command.callback(
            interaction, attacker="Garchomp", defender="Garchomp", move="Earthquake",
        ))
        return interaction.response.send_message.call_args[0][0]

    boosted_text = _run(boosted_user_id)
    plain_text = _run(plain_user_id)  # no team stored for this user -> neutral defaults

    assert _max_damage_from_calc_response(boosted_text) > _max_damage_from_calc_response(plain_text)
```

- [ ] **Step 8: Run test to verify it fails**

Run: `pytest tests/test_bot_main.py -v -k test_calc_command_uses_a_stored_team_members_evs_and_item`
Expected: FAIL with `assert 51 > 51` (or similar) — today's `calc` callback ignores any stored team entirely, so both calls use the same neutral defaults and produce identical damage.

- [ ] **Step 9: Update /calc's signature and body to resolve team overrides**

In `bot/main.py`, change the `calc` command's parameter defaults for the four EVs/nature options from their current literal defaults to `None`, and resolve overrides before calling `calc_response`:

```python
    @tree.command(name="calc", description="Calculate a damage range for attacker's move vs defender.")
    async def calc(
        interaction: discord.Interaction,
        attacker: str,
        defender: str,
        move: str,
        attacker_evs: Optional[str] = None,
        attacker_nature: Optional[str] = None,
        attacker_item: Optional[str] = None,
        attacker_tera: Optional[str] = None,
        defender_evs: Optional[str] = None,
        defender_nature: Optional[str] = None,
        defender_item: Optional[str] = None,
        defender_tera: Optional[str] = None,
        defender_hp_percent: int = 100,
        weather: Optional[str] = None,
        terrain: Optional[str] = None,
        screen: Optional[str] = None,
        spread: bool = False,
    ) -> None:
        user_id = interaction.user.id
        resolved_attacker_evs, resolved_attacker_nature, resolved_attacker_item, resolved_attacker_tera = (
            resolve_calc_overrides(user_id, attacker, attacker_evs, attacker_nature, attacker_item, attacker_tera)
        )
        resolved_defender_evs, resolved_defender_nature, resolved_defender_item, resolved_defender_tera = (
            resolve_calc_overrides(user_id, defender, defender_evs, defender_nature, defender_item, defender_tera)
        )
        response = calc_response(
            records,
            moves,
            attacker,
            defender,
            move,
            attacker_evs=resolved_attacker_evs,
            attacker_nature=resolved_attacker_nature,
            attacker_item=resolved_attacker_item,
            attacker_tera=resolved_attacker_tera,
            defender_evs=resolved_defender_evs,
            defender_nature=resolved_defender_nature,
            defender_item=resolved_defender_item,
            defender_tera=resolved_defender_tera,
            defender_hp_percent=defender_hp_percent,
            weather=weather,
            terrain=terrain,
            screen=screen,
            spread=spread,
        )
        await interaction.response.send_message(response)
```

- [ ] **Step 10: Run tests to verify they pass**

Run: `pytest tests/test_bot_main.py -v`
Expected: PASS (all tests, including the strengthened Step 7/8 test)

- [ ] **Step 11: Write a failing test for /ask's team-context wiring**

Add to `tests/test_bot_main.py`:

```python
def test_ask_command_includes_stored_team_context():
    from unittest.mock import AsyncMock, MagicMock
    from bot.team_store import store_team

    user_id = 9003
    store_team(user_id, "mine", [{
        "species": "Garchomp", "nickname": None, "gender": None, "item": "Life Orb",
        "ability": "Rough Skin", "level": 50, "tera_type": "Dragon",
        "evs": {"hp": 0, "attack": 0, "defense": 0, "sp_attack": 0, "sp_defense": 0, "speed": 0},
        "ivs": {"hp": 31, "attack": 31, "defense": 31, "sp_attack": 31, "sp_defense": 31, "speed": 31},
        "nature": "Hardy", "moves": [],
    }])

    captured = {}

    class _FakeAnswerer:
        def answer(self, question, context_block):
            captured["context_block"] = context_block
            return "an answer"

    class _FakeIndex:
        def query(self, question, n_results=5):
            return []

    _client, tree = build_client(index=_FakeIndex(), answerer=_FakeAnswerer())
    ask_command = tree.get_command("ask")
    interaction = MagicMock()
    interaction.user.id = user_id
    interaction.response.send_message = AsyncMock()

    import asyncio
    asyncio.run(ask_command.callback(interaction, question="What's a good lead?"))

    assert "Garchomp" in captured["context_block"]
```

- [ ] **Step 12: Run test to verify it fails**

Run: `pytest tests/test_bot_main.py -v -k test_ask_command_includes_stored_team_context`
Expected: FAIL — today's `ask` callback never builds or passes `extra_context`, so `captured["context_block"]` won't contain "Garchomp".

- [ ] **Step 13: Update /ask's body to build and pass extra_context**

In `bot/main.py`, change the `ask` command body:

```python
    @tree.command(name="ask", description="Ask a question about VGC Pokemon stats and movesets.")
    async def ask(interaction: discord.Interaction, question: str) -> None:
        user_id = interaction.user.id
        team_blocks = [
            format_team_block(get_team(user_id, "mine"), "Your team"),
            format_team_block(get_team(user_id, "opponent"), "Opponent's team"),
        ]
        extra_context = "\n\n".join(block for block in team_blocks if block) or None
        await interaction.response.send_message(
            await ask_response_async(index, answerer, question, extra_context=extra_context)
        )
```

- [ ] **Step 14: Run all tests to verify they pass**

Run: `pytest -q`
Expected: PASS, all tests in the project (existing suite plus every test added in Tasks 1-6).

- [ ] **Step 15: Manual end-to-end smoke test**

Run:

```bash
python3 -c "
import json
from bot.main import build_client
from bot.team_store import get_team
import asyncio
from unittest.mock import AsyncMock, MagicMock

records = json.loads(open('data/processed/pokemon_records.json').read())
moves = json.loads(open('data/source/vgc_moves.json').read())['moves']
client, tree = build_client(records=records, moves=moves)
import_cmd = tree.get_command('import')
calc_cmd = tree.get_command('calc')

def run(cmd, user_id, **kwargs):
    interaction = MagicMock()
    interaction.user.id = user_id
    interaction.response.send_message = AsyncMock()
    asyncio.run(cmd.callback(interaction, **kwargs))
    return interaction.response.send_message.call_args[0][0]

print(run(import_cmd, 12345, side='mine', pokepaste='''Garchomp @ Life Orb
Ability: Rough Skin
Tera Type: Dragon
EVs: 4 HP / 252 Atk / 0 Def / 0 SpA / 0 SpD / 252 Spe
Jolly Nature
- Earthquake
- Dragon Claw
'''))
print(get_team(12345, 'mine'))

print('with stored team:', run(calc_cmd, 12345, attacker='Garchomp', defender='Garchomp', move='Earthquake'))
print('no team (fresh user):', run(calc_cmd, 99999, attacker='Garchomp', defender='Garchomp', move='Earthquake'))
"
```

Confirm: the `/import` output lists Garchomp with no unmatched-name warnings (Garchomp is in `pokemon_records.json` and Earthquake/Dragon Claw are in `vgc_moves.json`), `get_team` shows the stored EVs/nature/item/tera, and the "with stored team" `/calc` line shows higher damage than the "no team" line (Life Orb + 252 Atk Jolly vs. the flat neutral default).

- [ ] **Step 16: Commit**

```bash
git add bot/main.py tests/test_bot_main.py
git commit -m "feat(bot): wire /import, /scout, /team and feed stored teams into /calc and /ask"
```

---

## Self-Review Notes

- **Spec coverage:** Data model (Task 1, 3), parsing (Task 1), URL fetch (Task 2), storage/merge/lookup/override-resolution (Task 3), `/import`/`/scout`/`/team` commands (Task 4, 6), `/calc` feed (Task 6), `/ask` feed (Task 5, 6), error handling — malformed block/unmatched names/6-cap/bad URL/empty view (Tasks 1, 2, 3, 4) — all covered.
- **Placeholder scan:** every step has literal, runnable code; no "TBD"/"add validation"/"similar to Task N" left in.
- **Type consistency:** the team-member dict shape defined in Task 1 (`species`, `nickname`, `gender`, `item`, `ability`, `level`, `tera_type`, `evs`, `ivs`, `nature`, `moves`) is used identically in Task 3's test fixtures, Task 4's `scout_response`/`format_team_block`, and Task 6's manual smoke test — checked field-by-field while writing this plan.
- **Note on Task 6:** the plan was updated after a live bug was found and fixed on `main` before this worktree was created — the `/moves` command handler is `moves_command`, not `moves` (it previously shadowed the `moves` data parameter and broke `/calc`). This worktree branches from that fixed `main`, so the fix is already present; Task 6 just needs to not undo it.
