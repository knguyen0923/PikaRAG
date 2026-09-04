import asyncio
from unittest.mock import AsyncMock, MagicMock

from bot.commands.ping import ping_response
from bot.main import build_client


def test_ping_response_is_pong():
    assert ping_response() == "Pong!"


def test_ping_command_is_registered_on_the_tree():
    _client, tree = build_client()
    commands = {command.name: command for command in tree.get_commands()}

    assert "ping" in commands
    assert commands["ping"].description == "Check that the bot is responsive."


def test_ask_command_is_registered_on_the_tree():
    _client, tree = build_client()
    commands = {command.name: command for command in tree.get_commands()}

    assert "ask" in commands
    assert "question" in commands["ask"].description.lower()


def test_stats_command_is_registered_on_the_tree():
    _client, tree = build_client()
    commands = {command.name: command for command in tree.get_commands()}

    assert "stats" in commands
    assert "stats" in commands["stats"].description.lower()


def test_moves_command_is_registered_on_the_tree():
    _client, tree = build_client()
    commands = {command.name: command for command in tree.get_commands()}

    assert "moves" in commands
    assert "moveset" in commands["moves"].description.lower()


def test_calc_command_is_registered_on_the_tree():
    _client, tree = build_client()
    commands = {command.name: command for command in tree.get_commands()}

    assert "calc" in commands
    assert "damage" in commands["calc"].description.lower()


def test_calc_command_actually_uses_the_moves_data_not_the_moves_command():
    # Regression test: the /moves command handler used to be named `moves`,
    # which rebound the `moves` closure variable to that Command object --
    # any command defined after it (like /calc) that reads `moves` from the
    # enclosing scope got the Command object instead of the move data list.
    records = [{
        "name": "Garchomp", "types": ["Dragon", "Ground"],
        "base_stats": {"hp": 108, "attack": 130, "defense": 95, "sp_attack": 80, "sp_defense": 85, "speed": 102},
        "abilities": ["Rough Skin"], "learnset": ["Earthquake"], "legal_in": ["M-B"],
    }]
    moves = [{"name": "Earthquake", "type": "Ground", "category": "Physical", "power": 100, "accuracy": 100, "pp": 10, "effect": None}]

    _client, tree = build_client(records=records, moves=moves)
    calc_cmd = tree.get_command("calc")
    interaction = MagicMock()
    interaction.user.id = 1
    interaction.response.send_message = AsyncMock()

    asyncio.run(calc_cmd.callback(interaction, attacker="Garchomp", defender="Garchomp", move="Earthquake"))

    sent_text = interaction.response.send_message.call_args[0][0]
    assert "Earthquake" in sent_text
    assert "damage" in sent_text.lower()
