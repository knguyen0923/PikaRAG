import json
import sqlite3
from typing import Optional

DEFAULT_DB_PATH = "data/team_store.db"

_MAX_TEAM_SIZE = 6
_DEFAULT_EVS_STRING = "0/0/0/0/0/0"
_DEFAULT_NATURE = "Hardy"
_EVS_STAT_ORDER = ["hp", "attack", "defense", "sp_attack", "sp_defense", "speed"]

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS team (
    user_id INTEGER NOT NULL,
    side TEXT NOT NULL,
    members TEXT NOT NULL,
    PRIMARY KEY (user_id, side)
)
"""


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute(_CREATE_TABLE_SQL)
    return conn


def _load(user_id: int, side: str, db_path: str) -> list:
    conn = _connect(db_path)
    try:
        cursor = conn.execute("SELECT members FROM team WHERE user_id = ? AND side = ?", (user_id, side))
        row = cursor.fetchone()
        return json.loads(row[0]) if row is not None else []
    finally:
        conn.close()


def _save(user_id: int, side: str, members: list, db_path: str) -> None:
    conn = _connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO team (user_id, side, members) VALUES (?, ?, ?)
            ON CONFLICT(user_id, side) DO UPDATE SET members = excluded.members
            """,
            (user_id, side, json.dumps(members)),
        )
        conn.commit()
    finally:
        conn.close()


def store_team(user_id: int, side: str, members: list, db_path: Optional[str] = None) -> None:
    if len(members) > _MAX_TEAM_SIZE:
        raise ValueError(f"A team can have at most {_MAX_TEAM_SIZE} Pokemon, got {len(members)}.")
    _save(user_id, side, list(members), db_path or DEFAULT_DB_PATH)


def get_team(user_id: int, side: str, db_path: Optional[str] = None) -> list:
    return _load(user_id, side, db_path or DEFAULT_DB_PATH)


def merge_scout(user_id: int, side: str, member: dict, db_path: Optional[str] = None) -> dict:
    db_path = db_path or DEFAULT_DB_PATH
    team = _load(user_id, side, db_path)
    target = member["species"].strip().lower()
    for existing in team:
        if existing["species"].strip().lower() == target:
            for field in ("item", "ability", "tera_type"):
                if member.get(field) is not None:
                    existing[field] = member[field]
            for move in member.get("moves", []):
                if move not in existing["moves"] and len(existing["moves"]) < 4:
                    existing["moves"].append(move)
            _save(user_id, side, team, db_path)
            return existing

    if len(team) >= _MAX_TEAM_SIZE:
        raise ValueError(f"'{side}' already has {_MAX_TEAM_SIZE} Pokemon -- nothing more can be added.")
    team.append(member)
    _save(user_id, side, team, db_path)
    return member


def find_team_member(user_id: int, name: str, db_path: Optional[str] = None) -> Optional[dict]:
    db_path = db_path or DEFAULT_DB_PATH
    target = name.strip().lower()
    for side in ("mine", "opponent"):
        for member in _load(user_id, side, db_path):
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
    explicit_ability: Optional[str],
    db_path: Optional[str] = None,
) -> tuple:
    member = find_team_member(user_id, name, db_path or DEFAULT_DB_PATH)

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
