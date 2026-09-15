import asyncio
from unittest.mock import AsyncMock, MagicMock

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
    select.values = ["Absol"]  # simulates Discord populating .values on submit
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
