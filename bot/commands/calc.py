from typing import Optional

from bot.pokemon_lookup import find_record, not_found_message
from damage_calc.calc import _IMPLEMENTED_ABILITIES, calculate_damage
from damage_calc.data.natures import get_nature_modifiers
from damage_calc.data.type_chart import ALL_TYPES

_STAT_ORDER = ["hp", "attack", "defense", "sp_attack", "sp_defense", "speed"]
_VGC_LEVEL = 50
_MAX_IVS = {stat: 31 for stat in _STAT_ORDER}
_NO_STAT_STAGES = {"attack": 0, "defense": 0, "sp_attack": 0, "sp_defense": 0, "speed": 0}
_MAX_EV_PER_STAT = 252
_MAX_EV_TOTAL = 508
_ERROR_PREFIXES = ("No ", "Invalid ")

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


def is_error_response(response: str) -> bool:
    """True if `response` is one of calc_response's error messages rather
    than a successful damage-range result. Centralized here, next to the
    messages themselves, so callers don't have to re-derive or guess at
    which prefixes mean "this calc failed" -- see bot/main.py's /calc
    handler for why that distinction matters to a caller.
    """
    return response.startswith(_ERROR_PREFIXES)


def _parse_evs(evs: str) -> Optional[dict]:
    parts = [part.strip() for part in evs.split("/")]
    if len(parts) != 6 or not all(part.isdigit() for part in parts):
        return None
    values = [int(part) for part in parts]
    if any(v > _MAX_EV_PER_STAT for v in values) or sum(values) > _MAX_EV_TOTAL:
        return None
    return dict(zip(_STAT_ORDER, values))


def _is_valid_nature(nature: str) -> bool:
    try:
        get_nature_modifiers(nature)
        return True
    except KeyError:
        return False


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


def _canonicalize_item(items: Optional[list], item: Optional[str]) -> tuple:
    """Resolve `item` against `items` (vgc_items.json entries), if a list was given.

    Returns (canonical_item_or_original, error_message_or_None). When `items`
    is not provided, the item passes through unvalidated (backward-compatible
    with callers that don't have an items list handy).
    """
    if not items or not item:
        return item, None
    record = find_record(items, item)
    if record is None:
        return item, not_found_message(items, item, kind="item")
    return record["name"], None


def calc_response(
    records: list,
    moves: list,
    attacker_name: str,
    defender_name: str,
    move_name: str,
    items: Optional[list] = None,
    attacker_evs: str = "0/0/0/0/0/0",
    attacker_nature: str = "Hardy",
    attacker_item: Optional[str] = None,
    attacker_ability: Optional[str] = None,
    attacker_tera: Optional[str] = None,
    defender_evs: str = "0/0/0/0/0/0",
    defender_nature: str = "Hardy",
    defender_item: Optional[str] = None,
    defender_ability: Optional[str] = None,
    defender_tera: Optional[str] = None,
    defender_hp_percent: int = 100,
    weather: Optional[str] = None,
    terrain: Optional[str] = None,
    screen: Optional[str] = None,
    spread: bool = False,
) -> str:
    """Format a damage-range response, assuming level 50 / 31 IVs / neutral stat stages (VGC standard)."""
    attacker_record = find_record(records, attacker_name)
    if attacker_record is None:
        return not_found_message(records, attacker_name)

    defender_record = find_record(records, defender_name)
    if defender_record is None:
        return not_found_message(records, defender_name)

    move = find_record(moves, move_name)
    if move is None:
        return not_found_message(moves, move_name, kind="move")

    attacker_item, error = _canonicalize_item(items, attacker_item)
    if error:
        return error
    defender_item, error = _canonicalize_item(items, defender_item)
    if error:
        return error

    parsed_attacker_evs = _parse_evs(attacker_evs)
    if parsed_attacker_evs is None:
        return (
            "Invalid attacker EVs. Expected format: hp/atk/def/spa/spd/spe, e.g. 4/252/0/0/0/252 "
            f"(each stat 0-{_MAX_EV_PER_STAT}, total up to {_MAX_EV_TOTAL})."
        )

    parsed_defender_evs = _parse_evs(defender_evs)
    if parsed_defender_evs is None:
        return (
            "Invalid defender EVs. Expected format: hp/atk/def/spa/spd/spe, e.g. 252/0/252/0/4/0 "
            f"(each stat 0-{_MAX_EV_PER_STAT}, total up to {_MAX_EV_TOTAL})."
        )

    if not _is_valid_nature(attacker_nature):
        return f"Invalid attacker nature '{attacker_nature}'."
    if not _is_valid_nature(defender_nature):
        return f"Invalid defender nature '{defender_nature}'."

    if attacker_tera is not None and attacker_tera not in ALL_TYPES:
        return f"Invalid attacker Tera type '{attacker_tera}'."
    if defender_tera is not None and defender_tera not in ALL_TYPES:
        return f"Invalid defender Tera type '{defender_tera}'."

    if not 1 <= defender_hp_percent <= 100:
        return "Invalid defender HP percent. Must be between 1 and 100."

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

    result = calculate_damage(move, attacker, defender, context)

    ko_note = " (KO chance)" if result.is_ko_chance else ""
    response = (
        f"{attacker_record['name']}'s {move['name']} vs {defender_record['name']}: "
        f"{result.min_damage}-{result.max_damage} damage "
        f"({result.min_percent}%-{result.max_percent}%){ko_note}."
    )

    # Flag when a real, correctly-spelled ability was passed in but isn't one
    # of the ~10 abilities this calculator actually models -- otherwise the
    # damage above silently ignores it (e.g. Levitate vs. Ground moves) with
    # no indication that happened. Case-insensitive, matching the case-fold
    # damage_calc itself applies to recognized abilities.
    for unmodeled_ability in _unmodeled_abilities(attacker_ability, defender_ability):
        response += f" (ability '{unmodeled_ability}' is not modeled)"

    return response


def _unmodeled_abilities(*abilities: Optional[str]) -> list:
    """Abilities from `abilities` that are set but not in _IMPLEMENTED_ABILITIES
    (modeled inside damage_calc.calc) or _BOT_LEVEL_MODELED_ABILITIES (modeled
    one layer up, in this file -- weather/terrain auto-derivation and
    Intimidate's stat-stage math)."""
    known = {name.casefold() for name in _IMPLEMENTED_ABILITIES | _BOT_LEVEL_MODELED_ABILITIES}
    return [ability for ability in abilities if ability and ability.casefold() not in known]
