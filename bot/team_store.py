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


def find_team_member(user_id: int, name: str) -> Optional[dict]:
    target = name.strip().lower()
    for side in ("mine", "opponent"):
        for member in _store.get(user_id, {}).get(side, []):
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
