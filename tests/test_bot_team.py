from bot.commands.team import (
    import_team_response, scout_response, view_team_response, format_team_block,
)
from bot.team_store import get_team

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
