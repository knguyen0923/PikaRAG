# Ability/Held-Item Interactions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close three specific gaps in `/calc`'s ability modeling: type-immunity/absorb abilities that currently produce a silently-wrong non-zero damage number, weather/terrain that currently must be typed manually even when an ability already sets it, and Intimidate (currently flagged "not modeled" despite the calculator already supporting the exact stat-stage math it needs).

**Architecture:** Type-immunity abilities are modeled inside `damage_calc/calc.py`'s `calculate_damage` (same layer as the existing Multiscale/Filter/Thick Fat/Tinted Lens ability checks) since they change the core damage number. Weather/terrain auto-derivation and Intimidate are modeled one layer up, in `bot/commands/calc.py`'s `calc_response`, since both are really about *deriving inputs* (`context["weather"]`, a combatant's `stat_stages`) that `calculate_damage` already knows how to consume unchanged — no new concept needs to enter the core formula for either.

**Tech Stack:** Pure Python, no new dependencies. Builds entirely on existing `damage_calc/calc.py` ability infrastructure (`_canonicalize_ability`, `_IMPLEMENTED_ABILITIES`) and `bot/commands/calc.py`'s existing `_unmodeled_abilities` warning mechanism.

**Spec:** No separate spec file — bounded design approved in chat 2026-09-17, recorded in `IMPROVEMENTS.md`'s "Ability/held-item interactions" bullet: *"type-immunity/absorb abilities (Levitate, Water Absorb, Flash Fire, Volt Absorb, Lightning Rod, Storm Drain — force 0 damage instead of a wrong non-zero number), weather/terrain auto-derivation from Drought/Drizzle/Sand Stream/Snow Warning + the 4 terrain-setters (explicit `--weather`/`--terrain` params still always win), and Intimidate (folds into existing stat-stage math). Focus Sash explicitly dropped from scope — it's a survival/KO-guarantee concept, not a damage number, so it doesn't fit this calculator's output shape."*

## Global Constraints

- Focus Sash is explicitly out of scope — do not add it anywhere in this plan.
- An explicit `weather`/`terrain` param passed to `calc_response` must always win over an ability-derived one (design's stated requirement).
- Every currently-passing test must keep passing. Two existing tests in `tests/test_bot_calc.py` (`test_calc_response_discloses_an_unmodeled_defender_ability`, `test_calc_response_discloses_an_unmodeled_attacker_ability`) assert that `Levitate`/`Intimidate` are flagged "not modeled" — this is the exact behavior this plan intentionally changes, so Task 1 updates those two tests to use a still-genuinely-unmodeled ability instead (e.g. `Sturdy`), preserving what they're actually testing (the "not modeled" disclosure mechanism itself).
- VGC/Gen 9 ability names, spelled exactly: `Levitate`, `Water Absorb`, `Flash Fire`, `Volt Absorb`, `Lightning Rod`, `Storm Drain`, `Drought`, `Drizzle`, `Sand Stream`, `Snow Warning`, `Electric Surge`, `Grassy Surge`, `Psychic Surge`, `Misty Surge`, `Intimidate`.

---

## File Structure

- Modify: `damage_calc/calc.py` — add `_ABILITY_IMMUNITY_TYPE` mapping and the immunity check in `calculate_damage`; extend `_IMPLEMENTED_ABILITIES`.
- Modify: `tests/test_calc.py` — add tests for the 6 immunity abilities.
- Modify: `bot/commands/calc.py` — add `_WEATHER_SETTER_ABILITY`/`_TERRAIN_SETTER_ABILITY` maps, `_ability_lookup`/`_has_ability` helpers, weather/terrain auto-derivation, Intimidate stat-stage derivation, and extend `_unmodeled_abilities`'s known-set; `_build_combatant` gains a `stat_stages` parameter.
- Modify: `tests/test_bot_calc.py` — update the two "not modeled" tests noted above; add tests for weather/terrain auto-derivation, explicit-param precedence, and Intimidate.

---

### Task 1: Type-immunity/absorb abilities force 0 damage

**Files:**
- Modify: `damage_calc/calc.py`
- Test: `tests/test_calc.py`

**Interfaces:**
- Consumes: existing `_canonicalize_ability`, `defender_ability` (already computed in `calculate_damage`), `move["type"]` (existing).
- Produces: `_ABILITY_IMMUNITY_TYPE: dict[str, str]` (ability name -> the move type it grants immunity to) and `_IMPLEMENTED_ABILITIES` extended to include all 6 — both consumed by Task 3's `_unmodeled_abilities` update in `bot/commands/calc.py`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_calc.py` (reuse the file's existing `_make_combatant`/`_BASE_CONTEXT` helpers already defined near the top):

```python
def test_levitate_grants_immunity_to_ground_type_moves():
    move = {"name": "Earthquake", "type": "Ground", "category": "Physical", "power": 100, "accuracy": 100, "pp": 10, "effect": None}
    stats = {"hp": 100, "attack": 100, "defense": 100, "sp_attack": 100, "sp_defense": 100, "speed": 100}
    attacker = _make_combatant(stats, types=["Ground"])
    defender_levitate = _make_combatant(stats, types=["Water"], ability="Levitate")

    result = calculate_damage(move, attacker, defender_levitate, _BASE_CONTEXT)

    assert result.min_damage == 0
    assert result.max_damage == 0
    assert result.is_ko_chance is False


def test_levitate_does_not_grant_immunity_to_non_ground_moves():
    move = {"name": "Surf", "type": "Water", "category": "Special", "power": 90, "accuracy": 100, "pp": 15, "effect": None}
    stats = {"hp": 100, "attack": 100, "defense": 100, "sp_attack": 100, "sp_defense": 100, "speed": 100}
    attacker = _make_combatant(stats, types=["Water"])
    defender_levitate = _make_combatant(stats, types=["Water"], ability="Levitate")

    result = calculate_damage(move, attacker, defender_levitate, _BASE_CONTEXT)

    assert result.max_damage > 0


def test_water_absorb_grants_immunity_to_water_type_moves():
    move = {"name": "Surf", "type": "Water", "category": "Special", "power": 90, "accuracy": 100, "pp": 15, "effect": None}
    stats = {"hp": 100, "attack": 100, "defense": 100, "sp_attack": 100, "sp_defense": 100, "speed": 100}
    attacker = _make_combatant(stats, types=["Water"])
    defender = _make_combatant(stats, types=["Fire"], ability="Water Absorb")

    result = calculate_damage(move, attacker, defender, _BASE_CONTEXT)

    assert result.min_damage == 0
    assert result.max_damage == 0


def test_flash_fire_grants_immunity_to_fire_type_moves():
    move = {"name": "Flamethrower", "type": "Fire", "category": "Special", "power": 90, "accuracy": 100, "pp": 15, "effect": None}
    stats = {"hp": 100, "attack": 100, "defense": 100, "sp_attack": 100, "sp_defense": 100, "speed": 100}
    attacker = _make_combatant(stats, types=["Fire"])
    defender = _make_combatant(stats, types=["Grass"], ability="Flash Fire")

    result = calculate_damage(move, attacker, defender, _BASE_CONTEXT)

    assert result.min_damage == 0
    assert result.max_damage == 0


def test_volt_absorb_grants_immunity_to_electric_type_moves():
    move = {"name": "Thunderbolt", "type": "Electric", "category": "Special", "power": 90, "accuracy": 100, "pp": 15, "effect": None}
    stats = {"hp": 100, "attack": 100, "defense": 100, "sp_attack": 100, "sp_defense": 100, "speed": 100}
    attacker = _make_combatant(stats, types=["Electric"])
    defender = _make_combatant(stats, types=["Water"], ability="Volt Absorb")

    result = calculate_damage(move, attacker, defender, _BASE_CONTEXT)

    assert result.min_damage == 0
    assert result.max_damage == 0


def test_lightning_rod_grants_immunity_to_electric_type_moves():
    move = {"name": "Thunderbolt", "type": "Electric", "category": "Special", "power": 90, "accuracy": 100, "pp": 15, "effect": None}
    stats = {"hp": 100, "attack": 100, "defense": 100, "sp_attack": 100, "sp_defense": 100, "speed": 100}
    attacker = _make_combatant(stats, types=["Electric"])
    defender = _make_combatant(stats, types=["Water"], ability="Lightning Rod")

    result = calculate_damage(move, attacker, defender, _BASE_CONTEXT)

    assert result.min_damage == 0
    assert result.max_damage == 0


def test_storm_drain_grants_immunity_to_water_type_moves():
    move = {"name": "Surf", "type": "Water", "category": "Special", "power": 90, "accuracy": 100, "pp": 15, "effect": None}
    stats = {"hp": 100, "attack": 100, "defense": 100, "sp_attack": 100, "sp_defense": 100, "speed": 100}
    attacker = _make_combatant(stats, types=["Water"])
    defender = _make_combatant(stats, types=["Fire"], ability="Storm Drain")

    result = calculate_damage(move, attacker, defender, _BASE_CONTEXT)

    assert result.min_damage == 0
    assert result.max_damage == 0


def test_ability_matching_is_case_insensitive_for_type_immunity():
    move = {"name": "Earthquake", "type": "Ground", "category": "Physical", "power": 100, "accuracy": 100, "pp": 10, "effect": None}
    stats = {"hp": 100, "attack": 100, "defense": 100, "sp_attack": 100, "sp_defense": 100, "speed": 100}
    attacker = _make_combatant(stats, types=["Ground"])
    defender = _make_combatant(stats, types=["Water"], ability="levitate")

    result = calculate_damage(move, attacker, defender, _BASE_CONTEXT)

    assert result.min_damage == 0
    assert result.max_damage == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_calc.py -v -k "immunity or levitate or water_absorb or flash_fire or volt_absorb or lightning_rod or storm_drain"`
Expected: FAIL — all 8 new tests fail (damage comes back non-zero for the immunity ones; the non-Ground Levitate test currently passes already, that's fine, it's a regression guard for later).

- [ ] **Step 3: Implement**

In `damage_calc/calc.py`, add near the other ability maps (after `_THICK_FAT_TYPES`):

```python
# Ability (defender) -> move type it grants full immunity to, forcing 0
# damage instead of the wrong non-zero number the base type chart alone
# would otherwise produce (e.g. a Ground-type move vs. a Water-type
# defender with Levitate is normally neutral/super-effective).
_ABILITY_IMMUNITY_TYPE = {
    "Levitate": "Ground",
    "Water Absorb": "Water",
    "Flash Fire": "Fire",
    "Volt Absorb": "Electric",
    "Lightning Rod": "Electric",
    "Storm Drain": "Water",
}
```

Update `_IMPLEMENTED_ABILITIES` to include them:

```python
_IMPLEMENTED_ABILITIES = frozenset(
    set(_ABILITY_STAT_BOOST)
    | {"Adaptability"}
    | _MULTISCALE_ABILITIES
    | _FILTER_ABILITIES
    | {"Thick Fat"}
    | {"Tinted Lens"}
    | set(_ABILITY_IMMUNITY_TYPE)
)
```

In `calculate_damage`, find the block:

```python
    # A fully immune matchup deals exactly zero; everything else deals at least 1.
    if type_effectiveness == 0:
        min_damage = max_damage = 0
    else:
        min_damage = max(1, min_damage)
        max_damage = max(1, max_damage)
```

Replace it with:

```python
    ability_grants_immunity = _ABILITY_IMMUNITY_TYPE.get(defender_ability) == move["type"]

    # A fully immune matchup deals exactly zero; everything else deals at least 1.
    if type_effectiveness == 0 or ability_grants_immunity:
        min_damage = max_damage = 0
    else:
        min_damage = max(1, min_damage)
        max_damage = max(1, max_damage)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_calc.py -v`
Expected: all pass (existing + 8 new)

- [ ] **Step 5: Commit**

```bash
git add damage_calc/calc.py tests/test_calc.py
git commit -m "feat: model type-immunity/absorb abilities as forced 0 damage" -m "$(printf 'Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>')"
```

---

### Task 2: Update the two `bot/commands/calc.py` "not modeled" tests that this plan intentionally invalidates

**Files:**
- Modify: `tests/test_bot_calc.py`

**Interfaces:**
- Consumes: `damage_calc.calc._IMPLEMENTED_ABILITIES` (now includes `Levitate` after Task 1).

**Why this task exists, and why it's first:** `tests/test_bot_calc.py` currently has `test_calc_response_discloses_an_unmodeled_defender_ability` (asserts `Levitate` -> "not modeled") and `test_calc_response_discloses_an_unmodeled_attacker_ability` (asserts `Intimidate` -> "not modeled"). Task 1 already made `Levitate` modeled, so the first test is failing right now. Task 3 will make `Intimidate` modeled too. Fix both tests now (swap to a still-genuinely-unmodeled ability) so the suite is green before Task 3 starts, and re-use the same swap for the "both unmodeled" test.

- [ ] **Step 1: Confirm the current failure**

Run: `python -m pytest tests/test_bot_calc.py -v -k unmodeled`
Expected: `test_calc_response_discloses_an_unmodeled_defender_ability` FAILS (Levitate is now modeled per Task 1); `test_calc_response_discloses_an_unmodeled_attacker_ability` and `test_calc_response_discloses_both_unmodeled_abilities_when_both_are_set` still PASS for now (Intimidate isn't modeled until Task 3).

- [ ] **Step 2: Update the tests**

In `tests/test_bot_calc.py`, replace these three tests (they currently use `Levitate` as the defender ability and `Intimidate` as the attacker ability to prove the "not modeled" disclosure mechanism — swap both for `Sturdy`, a real ability this calculator has never modeled and this plan does not add):

```python
def test_calc_response_discloses_an_unmodeled_defender_ability():
    # Sturdy isn't one of the abilities this calculator models, so the
    # damage figure silently ignores it -- the response must say so.
    response = calc_response(
        _RECORDS, _MOVES, "Abomasnow", "Gyarados", "Ice Beam", defender_ability="Sturdy"
    )

    assert "(ability 'Sturdy' is not modeled)" in response


def test_calc_response_discloses_an_unmodeled_attacker_ability():
    response = calc_response(
        _RECORDS, _MOVES, "Abomasnow", "Gyarados", "Ice Beam", attacker_ability="Sturdy"
    )

    assert "(ability 'Sturdy' is not modeled)" in response


def test_calc_response_discloses_both_unmodeled_abilities_when_both_are_set():
    response = calc_response(
        _RECORDS, _MOVES, "Abomasnow", "Gyarados", "Ice Beam",
        attacker_ability="Sturdy", defender_ability="Regenerator",
    )

    assert "(ability 'Sturdy' is not modeled)" in response
    assert "(ability 'Regenerator' is not modeled)" in response
```

- [ ] **Step 3: Run tests to verify they pass**

Run: `python -m pytest tests/test_bot_calc.py -v -k unmodeled`
Expected: all 3 pass.

- [ ] **Step 4: Commit**

```bash
git add tests/test_bot_calc.py
git commit -m "test: stop asserting Levitate is unmodeled ahead of the ability/item interactions work" -m "$(printf 'Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>')"
```

---

### Task 3: Weather/terrain auto-derivation and Intimidate stat-stage math

**Files:**
- Modify: `bot/commands/calc.py`
- Test: `tests/test_bot_calc.py`

**Interfaces:**
- Consumes: `damage_calc.calc._IMPLEMENTED_ABILITIES` (already imported in this file); the existing `_build_combatant`/`calc_response`/`_unmodeled_abilities` in this same file.
- Produces: `_build_combatant(record, evs, nature, item, ability, tera_type, stat_stages)` (signature change — new required 7th positional-or-keyword param); `_ability_lookup(ability, table) -> Optional[str]`; `_has_ability(ability, name) -> bool`. Nothing outside this file consumes any of these — self-contained.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_bot_calc.py`. This reuses the existing `_ABOMASNOW` fixture (real ability `"Snow Warning"`) and `_GYARADOS` fixture (real ability `"Intimidate"`) already defined at the top of the file, plus its existing `_max_damage` helper (used elsewhere in the file for comparisons — reuse it, don't redefine it):

```python
def test_calc_response_auto_derives_sun_weather_from_droughts_attacker():
    move = {"name": "Ember", "type": "Fire", "category": "Special", "power": 40, "accuracy": 100, "pp": 25, "effect": None}
    moves_with_ember = _MOVES + [move]

    baseline = calc_response(_RECORDS, moves_with_ember, "Abomasnow", "Gyarados", "Ember")
    with_sun = calc_response(
        _RECORDS, moves_with_ember, "Abomasnow", "Gyarados", "Ember", attacker_ability="Drought"
    )

    assert _max_damage(with_sun) > _max_damage(baseline)


def test_calc_response_auto_derives_snow_weather_from_defenders_snow_warning():
    # Snow Warning is Abomasnow's real ability in this fixture -- it doesn't
    # boost/reduce any move type in this calculator (matching the real
    # games, where Snow doesn't modify move damage), but passing it through
    # to context must not error and must not be flagged "not modeled".
    response = calc_response(
        _RECORDS, _MOVES, "Abomasnow", "Gyarados", "Ice Beam", attacker_ability="Snow Warning"
    )

    assert not is_error_response(response)
    assert "is not modeled" not in response


def test_calc_response_explicit_weather_param_wins_over_ability_derived_weather():
    move = {"name": "Ember", "type": "Fire", "category": "Special", "power": 40, "accuracy": 100, "pp": 25, "effect": None}
    moves_with_ember = _MOVES + [move]

    # Drought would auto-derive Sun (which boosts Fire); explicit Rain (which
    # weakens Fire) must win instead.
    response = calc_response(
        _RECORDS, moves_with_ember, "Abomasnow", "Gyarados", "Ember",
        attacker_ability="Drought", weather="Rain",
    )
    rain_damage = _max_damage(response)

    neutral = calc_response(_RECORDS, moves_with_ember, "Abomasnow", "Gyarados", "Ember")
    assert rain_damage < _max_damage(neutral)


def test_calc_response_auto_derives_electric_terrain_from_electric_surge():
    move = {"name": "Thunderbolt", "type": "Electric", "category": "Special", "power": 90, "accuracy": 100, "pp": 15, "effect": None}
    moves_with_tbolt = _MOVES + [move]

    baseline = calc_response(_RECORDS, moves_with_tbolt, "Abomasnow", "Gyarados", "Thunderbolt")
    with_terrain = calc_response(
        _RECORDS, moves_with_tbolt, "Abomasnow", "Gyarados", "Thunderbolt", attacker_ability="Electric Surge"
    )

    assert _max_damage(with_terrain) > _max_damage(baseline)


def test_calc_response_explicit_terrain_param_wins_over_ability_derived_terrain():
    move = {"name": "Thunderbolt", "type": "Electric", "category": "Special", "power": 90, "accuracy": 100, "pp": 15, "effect": None}
    moves_with_tbolt = _MOVES + [move]

    with_electric_surge = calc_response(
        _RECORDS, moves_with_tbolt, "Abomasnow", "Gyarados", "Thunderbolt", attacker_ability="Electric Surge"
    )
    with_explicit_override = calc_response(
        _RECORDS, moves_with_tbolt, "Abomasnow", "Gyarados", "Thunderbolt",
        attacker_ability="Electric Surge", terrain="Psychic",
    )

    assert _max_damage(with_explicit_override) < _max_damage(with_electric_surge)


def test_calc_response_defenders_intimidate_lowers_the_attackers_physical_damage():
    baseline = calc_response(_RECORDS, _MOVES, "Gyarados", "Abomasnow", "Tackle")
    with_intimidate = calc_response(
        _RECORDS, _MOVES, "Gyarados", "Abomasnow", "Tackle", defender_ability="Intimidate"
    )

    assert _max_damage(with_intimidate) < _max_damage(baseline)


def test_calc_response_attackers_intimidate_lowers_the_defenders_physical_damage_output_not_the_attackers_own():
    # Intimidate lowers the OPPONENT's Attack, not the holder's own -- so as
    # the attacker here, Gyarados's own outgoing damage must be unaffected.
    baseline = calc_response(_RECORDS, _MOVES, "Gyarados", "Abomasnow", "Tackle")
    with_own_intimidate = calc_response(
        _RECORDS, _MOVES, "Gyarados", "Abomasnow", "Tackle", attacker_ability="Intimidate"
    )

    assert _max_damage(with_own_intimidate) == _max_damage(baseline)


def test_calc_response_does_not_disclose_intimidate_as_unmodeled():
    response = calc_response(
        _RECORDS, _MOVES, "Abomasnow", "Gyarados", "Ice Beam", attacker_ability="Intimidate"
    )

    assert "is not modeled" not in response


def test_calc_response_does_not_disclose_a_weather_setter_ability_as_unmodeled():
    response = calc_response(
        _RECORDS, _MOVES, "Abomasnow", "Gyarados", "Ice Beam", attacker_ability="Drought"
    )

    assert "is not modeled" not in response


def test_calc_response_does_not_disclose_a_terrain_setter_ability_as_unmodeled():
    response = calc_response(
        _RECORDS, _MOVES, "Abomasnow", "Gyarados", "Ice Beam", attacker_ability="Electric Surge"
    )

    assert "is not modeled" not in response
```

Check near the top of `tests/test_bot_calc.py` for the existing `_max_damage` helper's exact name/signature (it's already used by tests like `test_choice_band_boosts_physical_damage`/`test_assault_vest_reduces_special_damage_taken` earlier in this file) and reuse it verbatim rather than redefining it.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_bot_calc.py -v -k "auto_derives or explicit_weather_param or explicit_terrain_param or intimidate or weather_setter or terrain_setter"`
Expected: FAIL — weather/terrain tests fail because nothing derives them yet (damage unchanged from baseline); Intimidate tests fail because stat_stages are hardcoded to neutral and "Intimidate" is still flagged "not modeled".

- [ ] **Step 3: Implement**

In `bot/commands/calc.py`, add near the top (after the existing module-level constants like `_NO_STAT_STAGES`):

```python
# Ability (either side) -> the weather/terrain it auto-sets, so a caller
# doesn't have to type --weather/--terrain manually when they've already
# told /calc which ability is in play. An explicit weather/terrain param
# always wins -- see calc_response's `weather = weather or ...` below.
_WEATHER_SETTER_ABILITY = {
    "Drought": "Sun",
    "Drizzle": "Rain",
    "Sand Stream": "Sand",
    "Snow Warning": "Snow",
}
_TERRAIN_SETTER_ABILITY = {
    "Electric Surge": "Electric",
    "Grassy Surge": "Grassy",
    "Psychic Surge": "Psychic",
    "Misty Surge": "Misty",
}
_INTIMIDATE = "Intimidate"

# Abilities realized at THIS layer (not inside damage_calc.calc, which only
# knows about abilities that change the core damage formula itself) -- used
# by _unmodeled_abilities below so these don't get spuriously flagged
# "not modeled" even though damage_calc.calc never sees their names.
_BOT_LEVEL_MODELED_ABILITIES = frozenset(
    {_INTIMIDATE} | set(_WEATHER_SETTER_ABILITY) | set(_TERRAIN_SETTER_ABILITY)
)


def _ability_lookup(ability: Optional[str], table: dict) -> Optional[str]:
    """Case-insensitive lookup of `ability` in `table` (an ability-name-keyed
    dict), mirroring damage_calc.calc._canonicalize_ability's case-fold
    matching style. Returns None if `ability` is falsy or not in `table`."""
    if not ability:
        return None
    for known, value in table.items():
        if ability.casefold() == known.casefold():
            return value
    return None


def _has_ability(ability: Optional[str], name: str) -> bool:
    return bool(ability) and ability.casefold() == name.casefold()
```

Update `_build_combatant` to accept `stat_stages`:

```python
def _build_combatant(
    record: dict, evs: dict, nature: str, item: Optional[str], ability: Optional[str], tera_type: Optional[str],
    stat_stages: dict,
) -> dict:
    return {
        "record": record,
        "level": _VGC_LEVEL,
        "evs": evs,
        "ivs": _MAX_IVS,
        "nature": nature,
        "stat_stages": stat_stages,
        "tera_type": tera_type,
        "item": item,
        "ability": ability,
    }
```

In `calc_response`, find where `attacker`/`defender` combatants are built:

```python
    attacker = _build_combatant(
        attacker_record, parsed_attacker_evs, attacker_nature, attacker_item, attacker_ability, attacker_tera
    )
    defender = _build_combatant(
        defender_record, parsed_defender_evs, defender_nature, defender_item, defender_ability, defender_tera
    )
    defender["current_hp_fraction"] = defender_hp_percent / 100

    context = {
        "is_doubles": spread,
        "is_spread_target": spread,
        "weather": weather,
        "terrain": terrain,
        "screen": screen,
    }
```

Replace with:

```python
    attacker_stat_stages = dict(_NO_STAT_STAGES)
    if _has_ability(defender_ability, _INTIMIDATE):
        attacker_stat_stages["attack"] = -1
    defender_stat_stages = dict(_NO_STAT_STAGES)
    if _has_ability(attacker_ability, _INTIMIDATE):
        defender_stat_stages["attack"] = -1

    attacker = _build_combatant(
        attacker_record, parsed_attacker_evs, attacker_nature, attacker_item, attacker_ability, attacker_tera,
        attacker_stat_stages,
    )
    defender = _build_combatant(
        defender_record, parsed_defender_evs, defender_nature, defender_item, defender_ability, defender_tera,
        defender_stat_stages,
    )
    defender["current_hp_fraction"] = defender_hp_percent / 100

    derived_weather = (
        _ability_lookup(attacker_ability, _WEATHER_SETTER_ABILITY)
        or _ability_lookup(defender_ability, _WEATHER_SETTER_ABILITY)
    )
    derived_terrain = (
        _ability_lookup(attacker_ability, _TERRAIN_SETTER_ABILITY)
        or _ability_lookup(defender_ability, _TERRAIN_SETTER_ABILITY)
    )

    context = {
        "is_doubles": spread,
        "is_spread_target": spread,
        "weather": weather or derived_weather,
        "terrain": terrain or derived_terrain,
        "screen": screen,
    }
```

Update `_unmodeled_abilities`:

```python
def _unmodeled_abilities(*abilities: Optional[str]) -> list:
    """Abilities from `abilities` that are set but not in _IMPLEMENTED_ABILITIES
    (modeled inside damage_calc.calc) or _BOT_LEVEL_MODELED_ABILITIES (modeled
    one layer up, in this file -- weather/terrain auto-derivation and
    Intimidate's stat-stage math)."""
    known = {name.casefold() for name in _IMPLEMENTED_ABILITIES | _BOT_LEVEL_MODELED_ABILITIES}
    return [ability for ability in abilities if ability and ability.casefold() not in known]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_bot_calc.py -v`
Expected: all pass (existing + Task 2's updates + Task 3's new tests)

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest -q`
Expected: all tests pass, no regressions anywhere else in the suite.

- [ ] **Step 6: Commit**

```bash
git add bot/commands/calc.py tests/test_bot_calc.py
git commit -m "feat: auto-derive weather/terrain from setter abilities and model Intimidate via stat stages" -m "$(printf 'Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>')"
```

---

### Task 4: Update `IMPROVEMENTS.md` and `README.md`

**Files:**
- Modify: `IMPROVEMENTS.md`
- Modify: `README.md` (only if it documents `/calc`'s currently-modeled ability list — check first)

- [ ] **Step 1: Check whether README.md lists modeled abilities**

Run: `grep -n -i "levitate\|multiscale\|modeled abilit\|ability" README.md`

If it lists specific modeled abilities (e.g. the existing Multiscale/Filter/Thick Fat/Tinted Lens set), add the 6 new immunity abilities plus a note that weather/terrain auto-derive from setter abilities and Intimidate is modeled via stat stages. If it doesn't mention abilities at all, skip this file.

- [ ] **Step 2: Mark the item done in IMPROVEMENTS.md**

In `IMPROVEMENTS.md`'s "Ability/held-item interactions" bullet (both the top summary section and "Priority 4"), replace "bounded design approved in chat (2026-09-17), not yet implemented" with an "implemented and merged" note in the style of the neighboring "Pinned-deps CI check — done." bullet: the 6 immunity abilities, the 4 weather-setters + 4 terrain-setters, Intimidate, and the final test count from `python -m pytest -q`.

- [ ] **Step 3: Commit**

```bash
git add IMPROVEMENTS.md README.md
git commit -m "docs: mark ability/held-item interactions done in the improvement backlog" -m "$(printf 'Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>')"
```
