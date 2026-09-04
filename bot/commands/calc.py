from typing import Optional

from bot.pokemon_lookup import find_record, suggest_names
from damage_calc.calc import calculate_damage

_STAT_ORDER = ["hp", "attack", "defense", "sp_attack", "sp_defense", "speed"]
_VGC_LEVEL = 50
_MAX_IVS = {stat: 31 for stat in _STAT_ORDER}
_NO_STAT_STAGES = {"attack": 0, "defense": 0, "sp_attack": 0, "sp_defense": 0, "speed": 0}


def _parse_evs(evs: str) -> Optional[dict]:
    parts = [part.strip() for part in evs.split("/")]
    if len(parts) != 6 or not all(part.isdigit() for part in parts):
        return None
    return dict(zip(_STAT_ORDER, (int(part) for part in parts)))


def _not_found_message(kind: str, name: str, candidates: list) -> str:
    suggestions = suggest_names(candidates, name)
    if suggestions:
        return f"No {kind} found matching '{name}'. Did you mean: {', '.join(suggestions)}?"
    return f"No {kind} found matching '{name}'."


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


def calc_response(
    records: list,
    moves: list,
    attacker_name: str,
    defender_name: str,
    move_name: str,
    attacker_evs: str = "0/0/0/0/0/0",
    attacker_nature: str = "Hardy",
    attacker_item: Optional[str] = None,
    attacker_tera: Optional[str] = None,
    defender_evs: str = "0/0/0/0/0/0",
    defender_nature: str = "Hardy",
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
        return _not_found_message("Pokemon", attacker_name, records)

    defender_record = find_record(records, defender_name)
    if defender_record is None:
        return _not_found_message("Pokemon", defender_name, records)

    move = find_record(moves, move_name)
    if move is None:
        return _not_found_message("move", move_name, moves)

    parsed_attacker_evs = _parse_evs(attacker_evs)
    if parsed_attacker_evs is None:
        return "Invalid attacker EVs. Expected format: hp/atk/def/spa/spd/spe, e.g. 4/252/0/0/0/252."

    parsed_defender_evs = _parse_evs(defender_evs)
    if parsed_defender_evs is None:
        return "Invalid defender EVs. Expected format: hp/atk/def/spa/spd/spe, e.g. 252/0/252/0/4/0."

    attacker = _build_combatant(attacker_record, parsed_attacker_evs, attacker_nature, attacker_item, attacker_tera)
    defender = _build_combatant(defender_record, parsed_defender_evs, defender_nature, None, defender_tera)
    defender["current_hp_fraction"] = defender_hp_percent / 100

    context = {
        "is_doubles": spread,
        "is_spread_target": spread,
        "weather": weather,
        "terrain": terrain,
        "screen": screen,
    }

    result = calculate_damage(move, attacker, defender, context)

    ko_note = " (KO chance)" if result.is_ko_chance else ""
    return (
        f"{attacker_record['name']}'s {move['name']} vs {defender_record['name']}: "
        f"{result.min_damage}-{result.max_damage} damage "
        f"({result.min_percent}%-{result.max_percent}%){ko_note}."
    )
