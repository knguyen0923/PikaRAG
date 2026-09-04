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
        try:
            amount_str, abbrev = part.split(" ", 1)
            amount = int(amount_str.strip())
            stat_name = _STAT_ABBREV[abbrev.strip().lower()]
        except (ValueError, KeyError) as e:
            raise PokepasteParseError(f"Could not parse stat entry '{part}': {e}") from e
        stats[stat_name] = amount
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
            try:
                member["level"] = int(line.split(":", 1)[1].strip())
            except ValueError as e:
                raise PokepasteParseError(f"Invalid Level value in '{line}': {e}") from e
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


def parse_pokepaste(text: str) -> list[dict]:
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
