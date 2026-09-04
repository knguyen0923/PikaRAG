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


def test_import_command_is_registered_on_the_tree():
    _client, tree = build_client()
    commands = {command.name: command for command in tree.get_commands()}

    assert "import" in commands
    assert "team" in commands["import"].description.lower()


def test_scout_command_is_registered_on_the_tree():
    _client, tree = build_client()
    commands = {command.name: command for command in tree.get_commands()}

    assert "scout" in commands
    assert "pokemon" in commands["scout"].description.lower()


def test_team_view_command_is_registered_on_the_tree():
    _client, tree = build_client()
    commands = {command.name: command for command in tree.get_commands()}

    assert "team" in commands
    assert "opponent" in commands["team"].description.lower() or "team" in commands["team"].description.lower()


_CALC_TEST_RECORDS = [{
    "name": "Garchomp", "types": ["Dragon", "Ground"],
    "base_stats": {"hp": 108, "attack": 130, "defense": 95, "sp_attack": 80, "sp_defense": 85, "speed": 102},
    "abilities": ["Rough Skin"], "learnset": ["Earthquake"], "legal_in": ["M-B"],
}]
_CALC_TEST_MOVES = [
    {"name": "Earthquake", "type": "Ground", "category": "Physical", "power": 100, "accuracy": 100, "pp": 10, "effect": None},
]


def _max_damage_from_calc_response(text: str) -> int:
    return int(text.split(": ")[1].split("-")[1].split(" ")[0])


def test_calc_command_uses_a_stored_team_members_evs_and_item():
    # Exercises build_client's calc callback directly via the underlying
    # discord.app_commands.Command's `.callback`, bypassing real Discord I/O.
    from bot.team_store import store_team

    boosted_user_id, plain_user_id = 9001, 9002
    store_team(boosted_user_id, "mine", [{
        "species": "Garchomp", "nickname": None, "gender": None, "item": "Life Orb",
        "ability": "Rough Skin", "level": 50, "tera_type": None,
        "evs": {"hp": 0, "attack": 252, "defense": 0, "sp_attack": 0, "sp_defense": 0, "speed": 0},
        "ivs": {"hp": 31, "attack": 31, "defense": 31, "sp_attack": 31, "sp_defense": 31, "speed": 31},
        "nature": "Adamant", "moves": ["Earthquake"],
    }])

    _client, tree = build_client(records=_CALC_TEST_RECORDS, moves=_CALC_TEST_MOVES)
    calc_command = tree.get_command("calc")

    def _run(user_id):
        interaction = MagicMock()
        interaction.user.id = user_id
        interaction.response.send_message = AsyncMock()
        asyncio.run(calc_command.callback(
            interaction, attacker="Garchomp", defender="Garchomp", move="Earthquake",
        ))
        return interaction.response.send_message.call_args[0][0]

    boosted_text = _run(boosted_user_id)
    plain_text = _run(plain_user_id)  # no team stored for this user -> neutral defaults

    assert _max_damage_from_calc_response(boosted_text) > _max_damage_from_calc_response(plain_text)


def test_ask_command_includes_stored_team_context():
    from unittest.mock import AsyncMock, MagicMock
    from bot.team_store import store_team

    user_id = 9003
    store_team(user_id, "mine", [{
        "species": "Garchomp", "nickname": None, "gender": None, "item": "Life Orb",
        "ability": "Rough Skin", "level": 50, "tera_type": "Dragon",
        "evs": {"hp": 0, "attack": 0, "defense": 0, "sp_attack": 0, "sp_defense": 0, "speed": 0},
        "ivs": {"hp": 31, "attack": 31, "defense": 31, "sp_attack": 31, "sp_defense": 31, "speed": 31},
        "nature": "Hardy", "moves": [],
    }])

    captured = {}

    class _FakeAnswerer:
        def answer(self, question, context_block):
            captured["context_block"] = context_block
            return "an answer"

    class _FakeIndex:
        def query(self, question, n_results=5):
            return []

    _client, tree = build_client(index=_FakeIndex(), answerer=_FakeAnswerer())
    ask_command = tree.get_command("ask")
    interaction = MagicMock()
    interaction.user.id = user_id
    interaction.response.send_message = AsyncMock()

    import asyncio
    asyncio.run(ask_command.callback(interaction, question="What's a good lead?"))

    assert "Garchomp" in captured["context_block"]
