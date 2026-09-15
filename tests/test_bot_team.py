import asyncio
from unittest.mock import AsyncMock, MagicMock

from bot.commands.team import (
    import_team_response, scout_response, view_team_response, format_team_block, TeamView,
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

_FOCUS_SASH = {"name": "Focus Sash", "description": "Endures a hit that would KO from full HP, once."}
_ITEMS = [_FOCUS_SASH]

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
    assert "Snow Warning" in block
    assert "Wood Hammer" in block


def test_format_team_block_omits_ability_when_unknown():
    member = dict(_ABOMASNOW_TEAM_MEMBER, ability=None)

    block = format_team_block([member], "Opponent's team")

    assert "None" not in block


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


def test_import_team_response_normalizes_unrecognized_nature():
    response = import_team_response(_RECORDS, _MOVES, 605, "mine", "Abomasnow\nadamant Nature\n- Wood Hammer\n")

    assert "not recognized" in response.lower()
    assert get_team(605, "mine")[0]["nature"] == "Hardy"


def test_import_team_response_normalizes_unrecognized_tera_type():
    response = import_team_response(_RECORDS, _MOVES, 606, "mine", "Abomasnow\nTera Type: Banana\n- Wood Hammer\n")

    assert "not recognized" in response.lower()
    assert get_team(606, "mine")[0]["tera_type"] is None


def test_scout_response_normalizes_unrecognized_tera_type():
    response = scout_response(_RECORDS, _MOVES, 705, "Abomasnow", tera_type="Banana", side="opponent")

    assert "not recognized" in response.lower()
    assert get_team(705, "opponent")[0]["tera_type"] is None


def test_import_team_response_flags_unmatched_item_when_items_given():
    response = import_team_response(
        _RECORDS, _MOVES, 801, "mine", "Abomasnow @ Focus Sesh\n- Wood Hammer\n", items=_ITEMS
    )

    assert "not recognized" in response.lower()
    assert "Focus Sesh" in response


def test_import_team_response_canonicalizes_item_casing_when_items_given():
    response = import_team_response(
        _RECORDS, _MOVES, 802, "mine", "Abomasnow @ focus sash\n- Wood Hammer\n", items=_ITEMS
    )

    assert "not recognized" not in response.lower()
    assert get_team(802, "mine")[0]["item"] == "Focus Sash"


def test_import_team_response_skips_item_validation_when_no_items_list_given():
    response = import_team_response(_RECORDS, _MOVES, 803, "mine", "Abomasnow @ Anything Goes\n- Wood Hammer\n")

    assert "not recognized" not in response.lower()
    assert get_team(803, "mine")[0]["item"] == "Anything Goes"


def test_scout_response_flags_unmatched_item_when_items_given():
    response = scout_response(_RECORDS, _MOVES, 804, "Abomasnow", item="Focus Sesh", items=_ITEMS, side="opponent")

    assert "not recognized" in response.lower()


def test_scout_response_reports_team_full_without_crashing():
    for i in range(6):
        scout_response(_RECORDS, _MOVES, 706, f"Species{i}", side="opponent")

    response = scout_response(_RECORDS, _MOVES, 706, "Species6", side="opponent")

    assert "6" in response


def test_team_view_has_your_team_and_opponents_team_buttons_in_order():
    view = TeamView(user_id=9400, side="mine")

    labels = [child.label for child in view.children]

    assert labels == ["Your team", "Opponent's team"]


def test_team_view_mine_button_edits_message_with_mine_side_and_a_fresh_view():
    view = TeamView(user_id=9400, side="opponent")
    mine_button = view.children[0]
    interaction = MagicMock()
    interaction.user.id = 9400
    interaction.response.edit_message = AsyncMock()

    asyncio.run(mine_button.callback(interaction))

    _args, kwargs = interaction.response.edit_message.call_args
    assert "no team" in kwargs["embed"].description.lower()
    assert isinstance(kwargs["view"], TeamView)
    assert kwargs["view"].side == "mine"
    assert kwargs["view"].user_id == 9400


def test_team_view_opponent_button_edits_message_with_opponent_side():
    view = TeamView(user_id=9400, side="mine")
    opponent_button = view.children[1]
    interaction = MagicMock()
    interaction.user.id = 9400
    interaction.response.edit_message = AsyncMock()

    asyncio.run(opponent_button.callback(interaction))

    _args, kwargs = interaction.response.edit_message.call_args
    assert isinstance(kwargs["view"], TeamView)
    assert kwargs["view"].side == "opponent"


def test_team_view_interaction_check_rejects_a_different_user_with_an_ephemeral_message():
    view = TeamView(user_id=9400, side="mine")
    interaction = MagicMock()
    interaction.user.id = 424242
    interaction.response.send_message = AsyncMock()

    allowed = asyncio.run(view.interaction_check(interaction))

    assert allowed is False
    interaction.response.send_message.assert_awaited_once()
    _args, kwargs = interaction.response.send_message.call_args
    assert kwargs["ephemeral"] is True


def test_team_view_interaction_check_allows_the_original_invoker():
    view = TeamView(user_id=9400, side="mine")
    interaction = MagicMock()
    interaction.user.id = 9400
    interaction.response.send_message = AsyncMock()

    allowed = asyncio.run(view.interaction_check(interaction))

    assert allowed is True
    interaction.response.send_message.assert_not_awaited()
