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
