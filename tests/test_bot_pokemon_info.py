import asyncio
from unittest.mock import AsyncMock, MagicMock

from bot.commands.pokemon_info import PokemonInfoView, usage_response

_ABOMASNOW = {
    "name": "Abomasnow", "types": ["Grass", "Ice"],
    "base_stats": {"hp": 90, "attack": 92, "defense": 75, "sp_attack": 92, "sp_defense": 85, "speed": 60},
    "abilities": ["Snow Warning", "Soundproof"], "learnset": ["Blizzard", "Wood Hammer"], "legal_in": ["M-B"],
}
_RECORDS = [_ABOMASNOW]


def test_usage_response_not_found_suggests_close_matches():
    response = usage_response(_RECORDS, "Abomasno")

    assert "not found" in response.lower() or "no pokemon" in response.lower()


def test_usage_response_reports_no_usage_data_when_none_exists():
    response = usage_response(_RECORDS, "Abomasnow", usage={})

    assert "no usage data" in response.lower()


def test_usage_response_shows_items_abilities_and_moves():
    usage = {"Abomasnow": {
        "items": [{"name": "Focus Sash", "usage_pct": 40.0}],
        "abilities": [{"name": "Snow Warning", "usage_pct": 98.5}],
        "moves": [{"name": "Blizzard", "usage_pct": 91.2}, {"name": "Wood Hammer", "usage_pct": 84.0}],
    }}

    response = usage_response(_RECORDS, "Abomasnow", usage=usage)

    assert "Focus Sash 40.0%" in response
    assert "Snow Warning 98.5%" in response
    assert "Blizzard 91.2%" in response
    assert "Wood Hammer 84.0%" in response


def test_usage_response_omits_empty_sections():
    usage = {"Abomasnow": {"items": [], "abilities": [{"name": "Snow Warning", "usage_pct": 98.5}], "moves": []}}

    response = usage_response(_RECORDS, "Abomasnow", usage=usage)

    assert "Items:" not in response
    assert "Abilities: Snow Warning 98.5%" in response
    assert "Moves:" not in response


def test_pokemon_info_view_has_three_tabs_in_order():
    view = PokemonInfoView(_RECORDS, {}, "Abomasnow", user_id=1, active_tab="Stats")

    labels = [child.label for child in view.children]

    assert labels == ["Stats", "Moves", "Usage"]


def test_pokemon_info_view_styles_the_active_tab_as_primary():
    import discord

    view = PokemonInfoView(_RECORDS, {}, "Abomasnow", user_id=1, active_tab="Moves")

    styles = {child.label: child.style for child in view.children}

    assert styles["Moves"] == discord.ButtonStyle.primary
    assert styles["Stats"] == discord.ButtonStyle.secondary
    assert styles["Usage"] == discord.ButtonStyle.secondary


def test_pokemon_info_view_moves_tab_edits_in_the_moveset():
    view = PokemonInfoView(_RECORDS, {}, "Abomasnow", user_id=1, active_tab="Stats")
    moves_button = view.children[1]
    interaction = MagicMock()
    interaction.user.id = 1
    interaction.response.edit_message = AsyncMock()

    asyncio.run(moves_button.callback(interaction))

    _args, kwargs = interaction.response.edit_message.call_args
    assert "Blizzard" in kwargs["embed"].description
    assert isinstance(kwargs["view"], PokemonInfoView)
    assert kwargs["view"].active_tab == "Moves"


def test_pokemon_info_view_usage_tab_edits_in_the_usage_breakdown():
    usage = {"Abomasnow": {"items": [], "abilities": [], "moves": [{"name": "Blizzard", "usage_pct": 91.2}]}}
    view = PokemonInfoView(_RECORDS, usage, "Abomasnow", user_id=1, active_tab="Stats")
    usage_button = view.children[2]
    interaction = MagicMock()
    interaction.user.id = 1
    interaction.response.edit_message = AsyncMock()

    asyncio.run(usage_button.callback(interaction))

    _args, kwargs = interaction.response.edit_message.call_args
    assert "Blizzard 91.2%" in kwargs["embed"].description
    assert kwargs["view"].active_tab == "Usage"


def test_pokemon_info_view_interaction_check_rejects_a_different_user():
    view = PokemonInfoView(_RECORDS, {}, "Abomasnow", user_id=1, active_tab="Stats")
    interaction = MagicMock()
    interaction.user.id = 999
    interaction.response.send_message = AsyncMock()

    allowed = asyncio.run(view.interaction_check(interaction))

    assert allowed is False
    _args, kwargs = interaction.response.send_message.call_args
    assert kwargs["ephemeral"] is True
