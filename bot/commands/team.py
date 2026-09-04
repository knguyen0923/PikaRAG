from bot.pokemon_lookup import find_record, suggest_names
from bot.pokepaste import parse_pokepaste, PokepasteParseError
from bot.team_store import get_team, merge_scout, store_team
from damage_calc.data.natures import get_nature_modifiers
from damage_calc.data.type_chart import ALL_TYPES

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
    if member["nature"] is not None:
        try:
            get_nature_modifiers(member["nature"])
        except KeyError:
            warnings.append(f"Nature '{member['nature']}' not recognized -- using Hardy instead.")
            member["nature"] = "Hardy"
    if member["tera_type"] is not None and member["tera_type"] not in ALL_TYPES:
        warnings.append(f"Tera type '{member['tera_type']}' not recognized -- ignoring it.")
        member["tera_type"] = None
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
