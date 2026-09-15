# Damage Calculator Ability Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the missing Choice Scarf item, thread a per-combatant `ability` field through `/calc` end-to-end, and implement the six highest-value ability modifiers (Adaptability, Huge Power/Pure Power, Multiscale/Shadow Shield, Filter/Solid Rock/Prism Armor, Thick Fat, Tinted Lens) in the damage calculator.

**Architecture:** `damage_calc/calc.py` currently has zero ability handling anywhere — no code reads an `ability` key at all, even though `_make_combatant` in `tests/test_calc.py` already reserves the field. This plan (1) adds Choice Scarf to the existing `_ITEM_STAT_BOOST` table (no structural change needed), (2) threads `ability` through the whole `/calc` call chain the same way `item` already flows — `bot/team_store.py`'s `resolve_calc_overrides` gains a 7th param/5th return value, `bot/commands/calc.py`'s `calc_response`/`_build_combatant` gain an `ability` field, and `bot/main.py`'s `/calc` command gains `attacker_ability`/`defender_ability` parameters — and (3) adds six ability checks into `damage_calc/calc.py` at the same three "stages" the file already models (stat calculation, base power modifiers, final modifiers), following the exact patterns `_ITEM_STAT_BOOST` and the final-modifier numerator chain already establish. `/scout` and `/import` already collect and store a per-Pokemon `ability` (confirmed: `bot/commands/team.py`'s `scout_response` already builds `{"ability": ability, ...}`, and `bot/team_store.py`'s `merge_scout` already merges it) — this plan does not touch that side at all.

**Tech Stack:** Python 3.9, no new dependencies. Ability modifiers reuse the same `/4096` fixed-point numerator chaining (`_chain_numerators`/`_apply_numerator`) `damage_calc/calc.py` already uses for items/screens/berries, and the same simplified sequential-floor pattern (`math.floor(stat * multiplier)`) it already uses for item stat boosts (Choice Band/Specs/Assault Vest) — not the bit-exact numerator chain, to match the existing convention for that specific code path rather than introduce a second style.

**Spec:** None — this plan is derived directly from this session's research pass over `damage_calc/calc.py`, `bot/commands/calc.py`, `data/source/vgc_items.json`, and `data/source/vgc_abilities.json` (see conversation for the full ranked list of ~17 candidate gaps; this plan implements the top 8 of them).

## Global Constraints

- No new dependencies.
- An unrecognized/typo'd ability string is a silent no-op — it simply matches none of the ability tables below and has no effect, exactly mirroring how an unrecognized item already behaves in `_effective_stat`/`calculate_damage` today (`_ITEM_STAT_BOOST.get(item, (None, None))`). No new validation, canonicalization, or suggestion UX is added for `ability` in this plan — that would require threading a `vgc_abilities.json`-backed list through `bot/main.py` into `calc_response` the way `items` already works for item names, which is out of scope here (a real but separate gap: `_validate_member` in `bot/commands/team.py` doesn't validate `ability` either, at `/scout`/`/import` time).
- Every new ability check reads `combatant.get("ability")`, never `combatant["ability"]` — `_build_combatant` always sets the key, but `tests/test_calc.py`'s existing `_make_combatant` and any other future construction site should not be required to.
- Held-item modifiers and ability modifiers are independent, both-can-apply chains — a Pokemon has exactly one ability and at most one held item, so there is no double-counting risk between e.g. Thick Fat and a resist berry both being checked.
- Out of scope (from the ranked research list, deliberately not implemented here): the type-boost item family (Charcoal/Magnet/etc.), type-immunity abilities (Levitate/Water Absorb/etc.), Protosynthesis/Quark Drive + Booster Energy, Intimidate/Intrepid Sword/Dauntless Shield (a switch-in mechanic, doesn't belong in a per-hit `calculate_damage` call), Technician, Air Balloon/Iron Ball, move-flag-dependent abilities (Iron Fist/Strong Jaw/etc. — blocked on confirming `vgc_moves.json` carries the needed flags), Guts (needs status-condition state the combatant dict doesn't have), Covert Cloak/Loaded Dice (need infrastructure the calculator doesn't have). None of these are touched by any task below.

---

## File structure

- Modify `damage_calc/calc.py` — add `CHOICE_SCARF` to `_ITEM_STAT_BOOST` (Task 1); add `ABILITY_ATTACK_DOUBLE_MULTIPLIER`, `_ABILITY_STAT_BOOST`, `ADAPTABILITY_STAB_MULTIPLIER`, `MULTISCALE_NUM`, `_MULTISCALE_ABILITIES`, `FILTER_NUM`, `_FILTER_ABILITIES`, `THICK_FAT_NUM`, `_THICK_FAT_TYPES`, `TINTED_LENS_NUM` constants and wire all six ability checks into `_effective_stat` and `calculate_damage` (Task 3).
- Modify `tests/test_calc.py` — tests for Choice Scarf (Task 1) and each of the six abilities (Task 3).
- Modify `bot/team_store.py` — `resolve_calc_overrides` gains `explicit_ability` param and returns a 5-tuple (Task 2).
- Modify `tests/test_team_store.py` — update the three existing `resolve_calc_overrides` calls/unpacks for the new 5-tuple, add one new ability-specific test.
- Modify `bot/commands/calc.py` — `_build_combatant` gains an `ability` param; `calc_response` gains `attacker_ability`/`defender_ability` params (Task 2).
- Modify `tests/test_bot_calc.py` — new tests proving `calc_response` accepts and applies an ability.
- Modify `bot/main.py` — `/calc` command gains `attacker_ability`/`defender_ability` slash parameters, threaded through `resolve_calc_overrides` and into `calc_response` (Task 2).
- Modify `tests/test_bot_main.py` — new test proving `/calc`'s handler resolves and forwards ability the same way it already does for item.

---

### Task 1: Choice Scarf

**Files:**
- Modify: `damage_calc/calc.py`
- Test: `tests/test_calc.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: nothing consumed by a later task — this task is fully independent of Tasks 2 and 3.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_calc.py`:

```python
def test_choice_scarf_boosts_speed_but_not_damage():
    move = {"name": "Tackle", "type": "Normal", "category": "Physical", "power": 40, "accuracy": 100, "pp": 35, "effect": None}
    attacker_no_item = _make_combatant(_NEUTRAL_STATS, types=["Normal"])
    attacker_choice_scarf = _make_combatant(_NEUTRAL_STATS, types=["Normal"], item="Choice Scarf")
    defender = _make_combatant(_NEUTRAL_STATS, types=["Water"])

    no_item = calculate_damage(move, attacker_no_item, defender, _BASE_CONTEXT)
    choice_scarf = calculate_damage(move, attacker_choice_scarf, defender, _BASE_CONTEXT)

    # Choice Scarf boosts Speed, which calculate_damage never reads -- so unlike
    # Choice Band it must NOT change the damage roll at all.
    assert choice_scarf.max_damage == no_item.max_damage


def test_choice_scarf_boosts_the_speed_stat_directly():
    from damage_calc.calc import _effective_stat

    combatant_no_item = _make_combatant(_NEUTRAL_STATS)
    combatant_choice_scarf = _make_combatant(_NEUTRAL_STATS, item="Choice Scarf")

    boosted = _effective_stat(combatant_choice_scarf, "speed")
    baseline = _effective_stat(combatant_no_item, "speed")

    assert boosted == math.floor(baseline * 1.5)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_calc.py -v -k choice_scarf`
Expected: `test_choice_scarf_boosts_the_speed_stat_directly` FAILs (`1.5x` not applied, `boosted == baseline`); `test_choice_scarf_boosts_damage_but_not... ` (the "does not affect damage" test) already PASSes trivially since Choice Scarf currently does nothing at all — that's expected and fine, it's locking in the correct behavior for after Step 3 too.

- [ ] **Step 3: Implement**

In `damage_calc/calc.py`, change:

```python
_ITEM_STAT_BOOST = {
    "Choice Band": ("attack", CHOICE_ITEM_STAT_MULTIPLIER),
    "Choice Specs": ("sp_attack", CHOICE_ITEM_STAT_MULTIPLIER),
    "Assault Vest": ("sp_defense", ASSAULT_VEST_MULTIPLIER),
}
```

to:

```python
_ITEM_STAT_BOOST = {
    "Choice Band": ("attack", CHOICE_ITEM_STAT_MULTIPLIER),
    "Choice Specs": ("sp_attack", CHOICE_ITEM_STAT_MULTIPLIER),
    "Choice Scarf": ("speed", CHOICE_ITEM_STAT_MULTIPLIER),
    "Assault Vest": ("sp_defense", ASSAULT_VEST_MULTIPLIER),
}
```

`_effective_stat` already applies `_ITEM_STAT_BOOST` generically to whichever `stat_name` it's called with (see its existing `item_stat, item_multiplier = _ITEM_STAT_BOOST.get(combatant.get("item"), (None, None))` block) — no other code change is needed for this to take effect on the Speed stat.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_calc.py -v -k choice_scarf`
Expected: both PASS.

- [ ] **Step 5: Run the entire test suite as a final check**

Run: `pytest -q`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add damage_calc/calc.py tests/test_calc.py
git commit -m "feat: add missing Choice Scarf item to the damage calculator"
```

---

### Task 2: Ability field plumbing through `/calc`

**Files:**
- Modify: `bot/team_store.py`
- Modify: `tests/test_team_store.py`
- Modify: `bot/commands/calc.py`
- Modify: `tests/test_bot_calc.py`
- Modify: `bot/main.py`
- Modify: `tests/test_bot_main.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `resolve_calc_overrides(user_id, name, explicit_evs, explicit_nature, explicit_item, explicit_tera, explicit_ability) -> (evs, nature, item, tera, ability)` (5-tuple, was 4); `calc_response(..., attacker_ability=None, defender_ability=None)`; combatant dicts built by `_build_combatant` now always have an `"ability"` key. Task 3's ability checks in `damage_calc/calc.py` read `combatant.get("ability")` from the dicts this task produces.

- [ ] **Step 1: Write the failing tests**

In `tests/test_team_store.py`, change the three existing `resolve_calc_overrides` calls from 4-tuple to 5-tuple unpacking:

```python
def test_resolve_calc_overrides_uses_neutral_defaults_when_nothing_stored_or_explicit():
    evs, nature, item, tera, ability = resolve_calc_overrides(401, "Nonexistent", None, None, None, None, None)

    assert evs == "0/0/0/0/0/0"
    assert nature == "Hardy"
    assert item is None
    assert tera is None
    assert ability is None


def test_resolve_calc_overrides_falls_back_to_stored_team_member():
    store_team(402, "mine", [_GARCHOMP])

    evs, nature, item, tera, ability = resolve_calc_overrides(402, "Garchomp", None, None, None, None, None)

    assert evs == "4/252/0/0/0/252"
    assert nature == "Jolly"
    assert item == "Life Orb"
    assert tera == "Dragon"
    assert ability == "Rough Skin"


def test_resolve_calc_overrides_explicit_value_wins_over_stored_team_member():
    store_team(403, "mine", [_GARCHOMP])

    _, _, item, _, ability = resolve_calc_overrides(403, "Garchomp", None, None, "Choice Band", None, "Sand Veil")

    assert item == "Choice Band"
    assert ability == "Sand Veil"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_team_store.py -v -k resolve_calc_overrides`
Expected: all 3 FAIL with `TypeError: resolve_calc_overrides() takes 6 positional arguments but 7 were given`.

- [ ] **Step 3: Implement the `bot/team_store.py` change**

Change:

```python
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

to:

```python
def resolve_calc_overrides(
    user_id: int,
    name: str,
    explicit_evs: Optional[str],
    explicit_nature: Optional[str],
    explicit_item: Optional[str],
    explicit_tera: Optional[str],
    explicit_ability: Optional[str],
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

    ability = explicit_ability
    if ability is None and member is not None:
        ability = member["ability"]

    return evs, nature, item, tera, ability
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_team_store.py -v`
Expected: all PASS.

- [ ] **Step 5: Write the failing tests for `bot/commands/calc.py`**

Append to `tests/test_bot_calc.py`:

```python
def test_calc_response_accepts_an_attacker_ability():
    response = calc_response(
        _RECORDS, _MOVES, "Abomasnow", "Gyarados", "Ice Beam", attacker_ability="Snow Warning"
    )

    assert not is_error_response(response)


def test_calc_response_accepts_a_defender_ability():
    response = calc_response(
        _RECORDS, _MOVES, "Abomasnow", "Gyarados", "Ice Beam", defender_ability="Intimidate"
    )

    assert not is_error_response(response)
```

- [ ] **Step 6: Run the tests to verify they fail**

Run: `pytest tests/test_bot_calc.py -v -k ability`
Expected: both FAIL with `TypeError: calc_response() got an unexpected keyword argument 'attacker_ability'`.

- [ ] **Step 7: Implement the `bot/commands/calc.py` change**

Change `_build_combatant`:

```python
def _build_combatant(record: dict, evs: dict, nature: str, item: Optional[str], tera_type: Optional[str]) -> dict:
    return {
        "record": record,
        "level": _VGC_LEVEL,
        "evs": evs,
        "ivs": _MAX_IVS,
        "nature": nature,
        "stat_stages": _NO_STAT_STAGES,
        "tera_type": tera_type,
        "item": item,
    }
```

to:

```python
def _build_combatant(
    record: dict, evs: dict, nature: str, item: Optional[str], ability: Optional[str], tera_type: Optional[str]
) -> dict:
    return {
        "record": record,
        "level": _VGC_LEVEL,
        "evs": evs,
        "ivs": _MAX_IVS,
        "nature": nature,
        "stat_stages": _NO_STAT_STAGES,
        "tera_type": tera_type,
        "item": item,
        "ability": ability,
    }
```

Change `calc_response`'s signature: add `attacker_ability: Optional[str] = None,` right after the `attacker_item: Optional[str] = None,` line, and `defender_ability: Optional[str] = None,` right after the `defender_item: Optional[str] = None,` line.

Change the two `_build_combatant` call sites:

```python
    attacker = _build_combatant(attacker_record, parsed_attacker_evs, attacker_nature, attacker_item, attacker_tera)
    defender = _build_combatant(defender_record, parsed_defender_evs, defender_nature, defender_item, defender_tera)
```

to:

```python
    attacker = _build_combatant(
        attacker_record, parsed_attacker_evs, attacker_nature, attacker_item, attacker_ability, attacker_tera
    )
    defender = _build_combatant(
        defender_record, parsed_defender_evs, defender_nature, defender_item, defender_ability, defender_tera
    )
```

- [ ] **Step 8: Run the tests to verify they pass**

Run: `pytest tests/test_bot_calc.py -v`
Expected: all PASS.

- [ ] **Step 9: Write the failing test for `bot/main.py`**

Add to `tests/test_bot_main.py`:

```python
def test_calc_command_resolves_a_stored_team_members_ability():
    from bot.team_store import store_team

    store_team(9101, "mine", [{
        "species": "Garchomp", "nickname": None, "gender": None, "item": None,
        "ability": "Rough Skin", "level": 50, "tera_type": None,
        "evs": {"hp": 0, "attack": 0, "defense": 0, "sp_attack": 0, "sp_defense": 0, "speed": 0},
        "ivs": {"hp": 31, "attack": 31, "defense": 31, "sp_attack": 31, "sp_defense": 31, "speed": 31},
        "nature": "Hardy", "moves": ["Earthquake"],
    }])
    _client, tree = build_client(records=_CALC_TEST_RECORDS, moves=_CALC_TEST_MOVES)
    calc_command = tree.get_command("calc")
    interaction = MagicMock()
    interaction.user.id = 9101
    interaction.response.send_message = AsyncMock()

    asyncio.run(calc_command.callback(interaction, attacker="Garchomp", defender="Garchomp", move="Earthquake"))

    # No assertion on damage output here (Rough Skin isn't one of Task 3's
    # implemented abilities) -- this test only proves the handler resolves
    # and forwards the stored ability without crashing.
    interaction.response.send_message.assert_awaited_once()
```

(This reuses `_CALC_TEST_RECORDS`/`_CALC_TEST_MOVES`, already defined earlier in `tests/test_bot_main.py` for the existing stored-team `/calc` tests — `_CALC_TEST_RECORDS`'s `Garchomp` entry already has `"abilities": ["Rough Skin"]`.)

- [ ] **Step 10: Run the test to verify it fails**

Run: `pytest tests/test_bot_main.py -v -k resolves_a_stored_team_members_ability`
Expected: FAIL — `resolve_calc_overrides()` inside the `/calc` handler is still called with 6 positional args, raising `TypeError` once Task 2 Step 3's signature change has landed (it has, by this point in the task).

- [ ] **Step 11: Implement the `bot/main.py` change**

Change the `/calc` command's signature: add `attacker_ability: Optional[str] = None,` right after `attacker_item: Optional[str] = None,`, and `defender_ability: Optional[str] = None,` right after `defender_item: Optional[str] = None,`.

Change:

```python
        resolved_attacker_evs, resolved_attacker_nature, resolved_attacker_item, resolved_attacker_tera = (
            resolve_calc_overrides(user_id, attacker, attacker_evs, attacker_nature, attacker_item, attacker_tera)
        )
        resolved_defender_evs, resolved_defender_nature, resolved_defender_item, resolved_defender_tera = (
            resolve_calc_overrides(user_id, defender, defender_evs, defender_nature, defender_item, defender_tera)
        )
```

to:

```python
        (
            resolved_attacker_evs, resolved_attacker_nature,
            resolved_attacker_item, resolved_attacker_tera, resolved_attacker_ability,
        ) = resolve_calc_overrides(
            user_id, attacker, attacker_evs, attacker_nature, attacker_item, attacker_tera, attacker_ability
        )
        (
            resolved_defender_evs, resolved_defender_nature,
            resolved_defender_item, resolved_defender_tera, resolved_defender_ability,
        ) = resolve_calc_overrides(
            user_id, defender, defender_evs, defender_nature, defender_item, defender_tera, defender_ability
        )
```

Then find the `calc_response(...)` call immediately below and add `attacker_ability=resolved_attacker_ability,` and `defender_ability=resolved_defender_ability,` alongside the existing `attacker_item=resolved_attacker_item,` / `defender_item=resolved_defender_item,` lines (same positions, item and ability travel together).

- [ ] **Step 12: Run the tests to verify they pass**

Run: `pytest tests/test_bot_main.py -v -k calc`
Expected: all PASS.

- [ ] **Step 13: Run the entire test suite as a final check**

Run: `pytest -q`
Expected: all PASS.

- [ ] **Step 14: Commit**

```bash
git add bot/team_store.py tests/test_team_store.py bot/commands/calc.py tests/test_bot_calc.py bot/main.py tests/test_bot_main.py
git commit -m "feat: thread ability through /calc end-to-end"
```

---

### Task 3: Six ability modifiers in `damage_calc/calc.py`

**Files:**
- Modify: `damage_calc/calc.py`
- Modify: `tests/test_calc.py`

**Interfaces:**
- Consumes: `combatant.get("ability")` on the dicts Task 2 (production) and `_make_combatant` (tests, already exists) build.
- Produces: nothing consumed by a later task — this is the final task in this plan.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_calc.py`:

```python
def test_adaptability_boosts_stab_beyond_the_normal_1_5x():
    move = {"name": "Tackle", "type": "Normal", "category": "Physical", "power": 40, "accuracy": 100, "pp": 35, "effect": None}
    attacker_normal_stab = _make_combatant(_NEUTRAL_STATS, types=["Normal"])
    attacker_adaptability = _make_combatant(_NEUTRAL_STATS, types=["Normal"], ability="Adaptability")
    defender = _make_combatant(_NEUTRAL_STATS, types=["Water"])

    normal_stab = calculate_damage(move, attacker_normal_stab, defender, _BASE_CONTEXT)
    adaptability = calculate_damage(move, attacker_adaptability, defender, _BASE_CONTEXT)

    assert adaptability.max_damage > normal_stab.max_damage


def test_adaptability_does_nothing_without_stab():
    move = {"name": "Tackle", "type": "Normal", "category": "Physical", "power": 40, "accuracy": 100, "pp": 35, "effect": None}
    attacker_no_stab = _make_combatant(_NEUTRAL_STATS, types=["Water"])
    attacker_adaptability_no_stab = _make_combatant(_NEUTRAL_STATS, types=["Water"], ability="Adaptability")
    defender = _make_combatant(_NEUTRAL_STATS, types=["Grass"])

    no_stab = calculate_damage(move, attacker_no_stab, defender, _BASE_CONTEXT)
    adaptability = calculate_damage(move, attacker_adaptability_no_stab, defender, _BASE_CONTEXT)

    assert adaptability.max_damage == no_stab.max_damage


def test_huge_power_doubles_the_attack_stat():
    from damage_calc.calc import _effective_stat

    baseline = _effective_stat(_make_combatant(_NEUTRAL_STATS), "attack")
    boosted = _effective_stat(_make_combatant(_NEUTRAL_STATS, ability="Huge Power"), "attack")

    assert boosted == baseline * 2


def test_pure_power_doubles_the_attack_stat():
    from damage_calc.calc import _effective_stat

    baseline = _effective_stat(_make_combatant(_NEUTRAL_STATS), "attack")
    boosted = _effective_stat(_make_combatant(_NEUTRAL_STATS, ability="Pure Power"), "attack")

    assert boosted == baseline * 2


def test_huge_power_does_not_affect_the_defense_stat():
    from damage_calc.calc import _effective_stat

    baseline = _effective_stat(_make_combatant(_NEUTRAL_STATS), "defense")
    with_huge_power = _effective_stat(_make_combatant(_NEUTRAL_STATS, ability="Huge Power"), "defense")

    assert with_huge_power == baseline


def test_multiscale_halves_damage_taken_at_full_hp():
    move = {"name": "Tackle", "type": "Normal", "category": "Physical", "power": 40, "accuracy": 100, "pp": 35, "effect": None}
    attacker = _make_combatant(_NEUTRAL_STATS, types=["Normal"])
    defender_no_ability = _make_combatant(_NEUTRAL_STATS, types=["Water"])
    defender_multiscale = _make_combatant(_NEUTRAL_STATS, types=["Water"], ability="Multiscale")

    baseline = calculate_damage(move, attacker, defender_no_ability, _BASE_CONTEXT)
    multiscale = calculate_damage(move, attacker, defender_multiscale, _BASE_CONTEXT)

    assert multiscale.max_damage < baseline.max_damage


def test_multiscale_does_not_apply_below_full_hp():
    move = {"name": "Tackle", "type": "Normal", "category": "Physical", "power": 40, "accuracy": 100, "pp": 35, "effect": None}
    attacker = _make_combatant(_NEUTRAL_STATS, types=["Normal"])
    defender_no_ability = _make_combatant(_NEUTRAL_STATS, types=["Water"])
    defender_no_ability["current_hp_fraction"] = 0.5
    defender_multiscale = _make_combatant(_NEUTRAL_STATS, types=["Water"], ability="Multiscale")
    defender_multiscale["current_hp_fraction"] = 0.5

    baseline = calculate_damage(move, attacker, defender_no_ability, _BASE_CONTEXT)
    multiscale = calculate_damage(move, attacker, defender_multiscale, _BASE_CONTEXT)

    assert multiscale.max_damage == baseline.max_damage


def test_shadow_shield_behaves_the_same_as_multiscale():
    move = {"name": "Tackle", "type": "Normal", "category": "Physical", "power": 40, "accuracy": 100, "pp": 35, "effect": None}
    attacker = _make_combatant(_NEUTRAL_STATS, types=["Normal"])
    defender_no_ability = _make_combatant(_NEUTRAL_STATS, types=["Water"])
    defender_shadow_shield = _make_combatant(_NEUTRAL_STATS, types=["Water"], ability="Shadow Shield")

    baseline = calculate_damage(move, attacker, defender_no_ability, _BASE_CONTEXT)
    shadow_shield = calculate_damage(move, attacker, defender_shadow_shield, _BASE_CONTEXT)

    assert shadow_shield.max_damage < baseline.max_damage


def test_filter_reduces_super_effective_damage():
    move = {"name": "Ice Beam", "type": "Ice", "category": "Special", "power": 90, "accuracy": 100, "pp": 10, "effect": None}
    attacker = _make_combatant(_NEUTRAL_STATS, types=["Ice"])
    defender_no_ability = _make_combatant(_NEUTRAL_STATS, types=["Grass"])
    defender_filter = _make_combatant(_NEUTRAL_STATS, types=["Grass"], ability="Filter")

    baseline = calculate_damage(move, attacker, defender_no_ability, _BASE_CONTEXT)
    filtered = calculate_damage(move, attacker, defender_filter, _BASE_CONTEXT)

    assert filtered.max_damage < baseline.max_damage


def test_filter_does_not_apply_on_neutral_damage():
    move = {"name": "Tackle", "type": "Normal", "category": "Physical", "power": 40, "accuracy": 100, "pp": 35, "effect": None}
    attacker = _make_combatant(_NEUTRAL_STATS, types=["Normal"])
    defender_no_ability = _make_combatant(_NEUTRAL_STATS, types=["Water"])
    defender_filter = _make_combatant(_NEUTRAL_STATS, types=["Water"], ability="Filter")

    baseline = calculate_damage(move, attacker, defender_no_ability, _BASE_CONTEXT)
    filtered = calculate_damage(move, attacker, defender_filter, _BASE_CONTEXT)

    assert filtered.max_damage == baseline.max_damage


def test_solid_rock_and_prism_armor_behave_the_same_as_filter():
    move = {"name": "Ice Beam", "type": "Ice", "category": "Special", "power": 90, "accuracy": 100, "pp": 10, "effect": None}
    attacker = _make_combatant(_NEUTRAL_STATS, types=["Ice"])
    defender_no_ability = _make_combatant(_NEUTRAL_STATS, types=["Grass"])

    baseline = calculate_damage(move, attacker, defender_no_ability, _BASE_CONTEXT)
    for ability in ("Solid Rock", "Prism Armor"):
        defender = _make_combatant(_NEUTRAL_STATS, types=["Grass"], ability=ability)
        result = calculate_damage(move, attacker, defender, _BASE_CONTEXT)
        assert result.max_damage < baseline.max_damage


def test_thick_fat_halves_fire_and_ice_damage_taken():
    fire_move = {"name": "Ember", "type": "Fire", "category": "Special", "power": 40, "accuracy": 100, "pp": 25, "effect": None}
    attacker = _make_combatant(_NEUTRAL_STATS, types=["Fire"])
    defender_no_ability = _make_combatant(_NEUTRAL_STATS, types=["Normal"])
    defender_thick_fat = _make_combatant(_NEUTRAL_STATS, types=["Normal"], ability="Thick Fat")

    baseline = calculate_damage(fire_move, attacker, defender_no_ability, _BASE_CONTEXT)
    thick_fat = calculate_damage(fire_move, attacker, defender_thick_fat, _BASE_CONTEXT)

    assert thick_fat.max_damage < baseline.max_damage


def test_thick_fat_does_not_apply_to_other_types():
    move = {"name": "Tackle", "type": "Normal", "category": "Physical", "power": 40, "accuracy": 100, "pp": 35, "effect": None}
    attacker = _make_combatant(_NEUTRAL_STATS, types=["Normal"])
    defender_no_ability = _make_combatant(_NEUTRAL_STATS, types=["Water"])
    defender_thick_fat = _make_combatant(_NEUTRAL_STATS, types=["Water"], ability="Thick Fat")

    baseline = calculate_damage(move, attacker, defender_no_ability, _BASE_CONTEXT)
    thick_fat = calculate_damage(move, attacker, defender_thick_fat, _BASE_CONTEXT)

    assert thick_fat.max_damage == baseline.max_damage


def test_tinted_lens_doubles_not_very_effective_damage():
    move = {"name": "Tackle", "type": "Normal", "category": "Physical", "power": 40, "accuracy": 100, "pp": 35, "effect": None}
    attacker_no_ability = _make_combatant(_NEUTRAL_STATS, types=["Normal"])
    attacker_tinted_lens = _make_combatant(_NEUTRAL_STATS, types=["Normal"], ability="Tinted Lens")
    defender = _make_combatant(_NEUTRAL_STATS, types=["Rock"])  # Normal resisted by Rock (0.5x)

    baseline = calculate_damage(move, attacker_no_ability, defender, _BASE_CONTEXT)
    tinted_lens = calculate_damage(move, attacker_tinted_lens, defender, _BASE_CONTEXT)

    assert tinted_lens.max_damage > baseline.max_damage


def test_tinted_lens_does_not_apply_on_neutral_or_super_effective_damage():
    move = {"name": "Tackle", "type": "Normal", "category": "Physical", "power": 40, "accuracy": 100, "pp": 35, "effect": None}
    attacker_no_ability = _make_combatant(_NEUTRAL_STATS, types=["Normal"])
    attacker_tinted_lens = _make_combatant(_NEUTRAL_STATS, types=["Normal"], ability="Tinted Lens")
    defender = _make_combatant(_NEUTRAL_STATS, types=["Water"])  # neutral

    baseline = calculate_damage(move, attacker_no_ability, defender, _BASE_CONTEXT)
    tinted_lens = calculate_damage(move, attacker_tinted_lens, defender, _BASE_CONTEXT)

    assert tinted_lens.max_damage == baseline.max_damage
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_calc.py -v -k "adaptability or huge_power or pure_power or multiscale or shadow_shield or filter or solid_rock or thick_fat or tinted_lens"`
Expected: all FAIL (each assertion comparing "with ability" vs. baseline currently finds them equal, since no ability is read anywhere yet).

- [ ] **Step 3: Implement**

In `damage_calc/calc.py`, add these constants right after the existing `_RESIST_BERRY_TYPE` dict (before `def calculate_stat`):

```python
# Ability (attacker) -> Attack-stat multiplier, applied in _effective_stat the
# same way _ITEM_STAT_BOOST already is -- Huge Power and Pure Power are
# mechanically identical (2x Attack), just different Pokemon-specific names.
ABILITY_ATTACK_DOUBLE_MULTIPLIER = 2.0
_ABILITY_STAT_BOOST = {
    "Huge Power": ("attack", ABILITY_ATTACK_DOUBLE_MULTIPLIER),
    "Pure Power": ("attack", ABILITY_ATTACK_DOUBLE_MULTIPLIER),
}

# Ability (attacker) -> replaces the normal 1.5x STAB multiplier when the
# move's type matches the attacker's own type(s).
ADAPTABILITY_STAB_MULTIPLIER = 2.0

# Ability (defender) -> halves damage taken while at full HP. Final Modifier
# group, same numerator-chain stage as screens/items/berries.
MULTISCALE_NUM = 2048  # 0.5x
_MULTISCALE_ABILITIES = {"Multiscale", "Shadow Shield"}

# Ability (defender) -> 0.75x damage taken on a super-effective hit.
FILTER_NUM = 3072  # 0.75x
_FILTER_ABILITIES = {"Filter", "Solid Rock", "Prism Armor"}

# Ability (defender) -> halves Fire/Ice damage taken.
THICK_FAT_NUM = 2048  # 0.5x
_THICK_FAT_TYPES = {"Fire", "Ice"}

# Ability (attacker) -> doubles damage on a not-very-effective hit.
TINTED_LENS_NUM = 8192  # 2.0x
```

Change `_effective_stat` from:

```python
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
        item_stat, item_multiplier = _ITEM_STAT_BOOST.get(combatant.get("item"), (None, None))
        if item_stat == stat_name:
            stat = math.floor(stat * item_multiplier)
    return stat
```

to:

```python
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
        item_stat, item_multiplier = _ITEM_STAT_BOOST.get(combatant.get("item"), (None, None))
        if item_stat == stat_name:
            stat = math.floor(stat * item_multiplier)
        ability_stat, ability_multiplier = _ABILITY_STAT_BOOST.get(combatant.get("ability"), (None, None))
        if ability_stat == stat_name:
            stat = math.floor(stat * ability_multiplier)
    return stat
```

In `calculate_damage`, change the STAB line from:

```python
    attacker_types = [attacker["tera_type"]] if attacker["tera_type"] else attacker["record"]["types"]
    stab = STAB_MULTIPLIER if move["type"] in attacker_types else NO_STAB_MULTIPLIER
```

to:

```python
    attacker_types = [attacker["tera_type"]] if attacker["tera_type"] else attacker["record"]["types"]
    if move["type"] in attacker_types:
        stab = ADAPTABILITY_STAB_MULTIPLIER if attacker.get("ability") == "Adaptability" else STAB_MULTIPLIER
    else:
        stab = NO_STAB_MULTIPLIER
```

Finally, in the "Final Modifiers" block, change:

```python
    resist_berry_type = _RESIST_BERRY_TYPE.get(defender.get("item"))
    if resist_berry_type == move["type"] and (type_effectiveness > 1 or resist_berry_type == "Normal"):
        final_numerators.append(RESIST_BERRY_NUM)

    final_modifier_numerator = _chain_numerators(final_numerators)
```

to:

```python
    resist_berry_type = _RESIST_BERRY_TYPE.get(defender.get("item"))
    if resist_berry_type == move["type"] and (type_effectiveness > 1 or resist_berry_type == "Normal"):
        final_numerators.append(RESIST_BERRY_NUM)

    if defender.get("ability") in _MULTISCALE_ABILITIES and defender.get("current_hp_fraction") == 1.0:
        final_numerators.append(MULTISCALE_NUM)
    if defender.get("ability") in _FILTER_ABILITIES and type_effectiveness > 1:
        final_numerators.append(FILTER_NUM)
    if defender.get("ability") == "Thick Fat" and move["type"] in _THICK_FAT_TYPES:
        final_numerators.append(THICK_FAT_NUM)
    if attacker.get("ability") == "Tinted Lens" and 0 < type_effectiveness < 1:
        final_numerators.append(TINTED_LENS_NUM)

    final_modifier_numerator = _chain_numerators(final_numerators)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_calc.py -v`
Expected: all PASS (new and pre-existing).

- [ ] **Step 5: Run the entire test suite as a final check**

Run: `pytest -q`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add damage_calc/calc.py tests/test_calc.py
git commit -m "feat: add Adaptability, Huge/Pure Power, Multiscale, Filter, Thick Fat, Tinted Lens"
```

---

## Self-review notes

- **Spec coverage** (against this session's research list, top 8 items): Choice Scarf (Task 1); ability field plumbing end-to-end, `/calc` slash command through to the combatant dict (Task 2); Adaptability, Huge Power, Pure Power, Multiscale, Shadow Shield, Filter, Solid Rock, Prism Armor, Thick Fat, Tinted Lens (Task 3, 6 distinct mechanics covering 10 named abilities) — all covered. Items 9-17 from the research list are explicitly out of scope (see Global Constraints) and untouched by any task.
- **Placeholder scan:** no TBD/TODO; every step has runnable, complete code.
- **Type/name consistency checked:** `_build_combatant`'s new `ability` parameter (Task 2) lands in position 5, matching every call site updated in the same task; `resolve_calc_overrides`'s new 5-tuple order (`evs, nature, item, tera, ability`) matches every unpacking call site updated in the same task, including the new `bot/main.py` multi-line unpack. `combatant.get("ability")` (Task 3) reads the exact key `_build_combatant` (Task 2, production) and `_make_combatant` (tests, pre-existing) both already write.
- **Backward-compatibility note:** `resolve_calc_overrides` and `_build_combatant` both change their positional signatures (not additive/optional), which is a deliberate choice matching this codebase's stated preference against back-compat shims for internal call sites — both have exactly two call sites each (production + tests), all updated within the same task that changes the signature, so there is no lingering caller on the old shape.
