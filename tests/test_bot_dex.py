import asyncio
from unittest.mock import AsyncMock, MagicMock

from bot.commands.dex import DexBrowseView, dex_page_response

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


def test_dex_page_response_shows_the_record_at_the_given_index():
    response = dex_page_response(_RECORDS, 0)

    assert "Abomasnow" in response
    assert "HP 90" in response


def test_dex_page_response_shows_the_second_record():
    response = dex_page_response(_RECORDS, 1)

    assert "Gyarados" in response


def test_dex_page_response_includes_a_position_marker():
    response = dex_page_response(_RECORDS, 0)

    assert "(1/2)" in response

    response = dex_page_response(_RECORDS, 1)

    assert "(2/2)" in response


def test_dex_browse_view_disables_prev_at_the_first_page():
    view = DexBrowseView(_RECORDS, index=0, user_id=1)

    prev_button, next_button = view.children

    assert prev_button.disabled is True
    assert next_button.disabled is False


def test_dex_browse_view_disables_next_at_the_last_page():
    view = DexBrowseView(_RECORDS, index=1, user_id=1)

    prev_button, next_button = view.children

    assert prev_button.disabled is False
    assert next_button.disabled is True


def test_dex_browse_view_next_button_advances_the_page():
    view = DexBrowseView(_RECORDS, index=0, user_id=1)
    _prev_button, next_button = view.children
    interaction = MagicMock()
    interaction.user.id = 1
    interaction.response.edit_message = AsyncMock()

    asyncio.run(next_button.callback(interaction))

    _args, kwargs = interaction.response.edit_message.call_args
    assert "Gyarados" in kwargs["embed"].description
    assert isinstance(kwargs["view"], DexBrowseView)
    assert kwargs["view"].index == 1


def test_dex_browse_view_prev_button_goes_back_a_page():
    view = DexBrowseView(_RECORDS, index=1, user_id=1)
    prev_button, _next_button = view.children
    interaction = MagicMock()
    interaction.user.id = 1
    interaction.response.edit_message = AsyncMock()

    asyncio.run(prev_button.callback(interaction))

    _args, kwargs = interaction.response.edit_message.call_args
    assert kwargs["view"].index == 0


def test_dex_browse_view_interaction_check_rejects_a_different_user():
    view = DexBrowseView(_RECORDS, index=0, user_id=1)
    interaction = MagicMock()
    interaction.user.id = 999
    interaction.response.send_message = AsyncMock()

    allowed = asyncio.run(view.interaction_check(interaction))

    assert allowed is False
