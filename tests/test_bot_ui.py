import asyncio

import pytest
from unittest.mock import AsyncMock, MagicMock

import discord

from bot.ui import NameSuggestionView


def test_name_suggestion_view_has_one_option_per_suggestion():
    view = NameSuggestionView(user_id=1, suggestions=["Abomasnow", "Absol"], on_select=AsyncMock())

    select = view.children[0]
    assert [opt.label for opt in select.options] == ["Abomasnow", "Absol"]


def test_name_suggestion_view_caps_options_at_twenty_five():
    suggestions = [f"Species{i}" for i in range(30)]
    view = NameSuggestionView(user_id=1, suggestions=suggestions, on_select=AsyncMock())

    select = view.children[0]
    assert len(select.options) == 25


def test_picking_a_suggestion_calls_on_select_with_the_chosen_name():
    on_select = AsyncMock()
    view = NameSuggestionView(user_id=1, suggestions=["Abomasnow", "Absol"], on_select=on_select)
    select = view.children[0]
    select._values = ["Absol"]  # simulates Discord populating .values on submit
    interaction = MagicMock()
    interaction.user.id = 1

    asyncio.run(select.callback(interaction))

    on_select.assert_awaited_once_with(interaction, "Absol")


def test_name_suggestion_view_interaction_check_rejects_a_different_user():
    view = NameSuggestionView(user_id=1, suggestions=["Abomasnow"], on_select=AsyncMock())
    interaction = MagicMock()
    interaction.user.id = 999
    interaction.response.send_message = AsyncMock()

    allowed = asyncio.run(view.interaction_check(interaction))

    assert allowed is False
    _args, kwargs = interaction.response.send_message.call_args
    assert kwargs["ephemeral"] is True


def test_name_suggestion_view_interaction_check_allows_the_original_invoker():
    view = NameSuggestionView(user_id=1, suggestions=["Abomasnow"], on_select=AsyncMock())
    interaction = MagicMock()
    interaction.user.id = 1
    interaction.response.send_message = AsyncMock()

    allowed = asyncio.run(view.interaction_check(interaction))

    assert allowed is True
    interaction.response.send_message.assert_not_awaited()


def test_name_suggestion_view_rejects_an_empty_suggestions_list():
    with pytest.raises(ValueError):
        NameSuggestionView(user_id=1, suggestions=[], on_select=AsyncMock())


def test_name_suggestion_view_on_error_sends_an_ephemeral_message_when_not_yet_responded():
    async def on_select(_interaction, _chosen_name):
        raise RuntimeError("boom")

    view = NameSuggestionView(user_id=1, suggestions=["Abomasnow"], on_select=on_select)
    select = view.children[0]
    select._values = ["Abomasnow"]
    interaction = MagicMock()
    interaction.user.id = 1
    interaction.response.is_done.return_value = False
    interaction.response.send_message = AsyncMock()
    interaction.followup.send = AsyncMock()

    async def run():
        try:
            await select.callback(interaction)
        except RuntimeError as error:
            await view.on_error(interaction, error, select)

    asyncio.run(run())

    interaction.response.send_message.assert_awaited_once()
    interaction.followup.send.assert_not_awaited()
    _args, kwargs = interaction.response.send_message.call_args
    assert kwargs["ephemeral"] is True
    assert isinstance(kwargs["embed"], discord.Embed)
    assert "something went wrong" in kwargs["embed"].description.lower()


def test_name_suggestion_view_on_error_uses_followup_when_already_responded():
    view = NameSuggestionView(user_id=1, suggestions=["Abomasnow"], on_select=AsyncMock())
    select = view.children[0]
    interaction = MagicMock()
    interaction.user.id = 1
    interaction.response.is_done.return_value = True
    interaction.response.send_message = AsyncMock()
    interaction.followup.send = AsyncMock()

    asyncio.run(view.on_error(interaction, RuntimeError("boom"), select))

    interaction.followup.send.assert_awaited_once()
    interaction.response.send_message.assert_not_awaited()
    _args, kwargs = interaction.followup.send.call_args
    assert kwargs["ephemeral"] is True
    assert isinstance(kwargs["embed"], discord.Embed)
