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


def test_import_command_reports_a_fetch_error_without_crashing(monkeypatch):
    import bot.main as main_module
    from bot.pokepaste_fetch import PokepasteFetchError

    def _raise(*args, **kwargs):
        raise PokepasteFetchError("Could not fetch 'https://pokepast.es/bad' (got HTTP 404).")

    monkeypatch.setattr(main_module, "resolve_pokepaste_text", _raise)

    _client, tree = build_client()
    import_command = tree.get_command("import")
    interaction = MagicMock()
    interaction.user.id = 1
    interaction.response.defer = AsyncMock()
    interaction.followup.send = AsyncMock()

    asyncio.run(import_command.callback(interaction, side="mine", pokepaste="https://pokepast.es/bad"))

    interaction.response.defer.assert_awaited_once()
    sent_text = interaction.followup.send.call_args[0][0]
    assert "404" in sent_text


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


def test_calc_command_notes_when_a_stored_team_member_was_used():
    from bot.team_store import store_team

    user_id = 9004
    store_team(user_id, "mine", [{
        "species": "Garchomp", "nickname": None, "gender": None, "item": "Life Orb",
        "ability": "Rough Skin", "level": 50, "tera_type": None,
        "evs": {"hp": 0, "attack": 252, "defense": 0, "sp_attack": 0, "sp_defense": 0, "speed": 0},
        "ivs": {"hp": 31, "attack": 31, "defense": 31, "sp_attack": 31, "sp_defense": 31, "speed": 31},
        "nature": "Adamant", "moves": ["Earthquake"],
    }])

    _client, tree = build_client(records=_CALC_TEST_RECORDS, moves=_CALC_TEST_MOVES)
    calc_command = tree.get_command("calc")
    interaction = MagicMock()
    interaction.user.id = user_id
    interaction.response.send_message = AsyncMock()

    asyncio.run(calc_command.callback(
        interaction, attacker="Garchomp", defender="Garchomp", move="Earthquake",
    ))

    sent_text = interaction.response.send_message.call_args[0][0]
    assert "using stored data" in sent_text.lower()
    assert "Garchomp" in sent_text.split("using stored data")[1]


def test_calc_command_omits_the_note_when_nothing_is_stored():
    _client, tree = build_client(records=_CALC_TEST_RECORDS, moves=_CALC_TEST_MOVES)
    calc_command = tree.get_command("calc")
    interaction = MagicMock()
    interaction.user.id = 9005
    interaction.response.send_message = AsyncMock()

    asyncio.run(calc_command.callback(
        interaction, attacker="Garchomp", defender="Garchomp", move="Earthquake",
    ))

    sent_text = interaction.response.send_message.call_args[0][0]
    assert "using stored data" not in sent_text.lower()


def test_calc_command_omits_the_note_on_an_error_response():
    _client, tree = build_client(records=_CALC_TEST_RECORDS, moves=_CALC_TEST_MOVES)
    calc_command = tree.get_command("calc")
    interaction = MagicMock()
    interaction.user.id = 9006
    interaction.response.send_message = AsyncMock()

    asyncio.run(calc_command.callback(
        interaction, attacker="Nonexistamon", defender="Garchomp", move="Earthquake",
    ))

    sent_text = interaction.response.send_message.call_args[0][0]
    assert "using stored data" not in sent_text.lower()


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


def test_import_then_calc_uses_the_real_parsed_team_data():
    records = [{
        "name": "Garchomp", "types": ["Dragon", "Ground"],
        "base_stats": {"hp": 108, "attack": 130, "defense": 95, "sp_attack": 80, "sp_defense": 85, "speed": 102},
        "abilities": ["Rough Skin"], "learnset": ["Earthquake"], "legal_in": ["M-B"],
    }]
    moves_data = [
        {"name": "Earthquake", "type": "Ground", "category": "Physical", "power": 100, "accuracy": 100, "pp": 10, "effect": None},
    ]
    _client, tree = build_client(records=records, moves=moves_data)
    import_command = tree.get_command("import")
    calc_command = tree.get_command("calc")

    user_id = 20001
    fresh_user_id = 20002

    def _run(cmd, uid, **kwargs):
        interaction = MagicMock()
        interaction.user.id = uid
        interaction.response.send_message = AsyncMock()
        interaction.response.defer = AsyncMock()
        interaction.followup.send = AsyncMock()
        asyncio.run(cmd.callback(interaction, **kwargs))
        if interaction.followup.send.called:
            return interaction.followup.send.call_args[0][0]
        return interaction.response.send_message.call_args[0][0]

    _run(import_command, user_id, side="mine", pokepaste="""Garchomp @ Life Orb
Ability: Rough Skin
EVs: 0 HP / 252 Atk / 0 Def / 0 SpA / 0 SpD / 0 Spe
Adamant Nature
- Earthquake
""")

    boosted_text = _run(calc_command, user_id, attacker="Garchomp", defender="Garchomp", move="Earthquake")
    plain_text = _run(calc_command, fresh_user_id, attacker="Garchomp", defender="Garchomp", move="Earthquake")

    def _max_damage(text):
        return int(text.split(": ")[1].split("-")[1].split(" ")[0])

    assert _max_damage(boosted_text) > _max_damage(plain_text)


def test_tree_error_handler_sends_a_friendly_message_when_not_yet_responded():
    from discord import app_commands

    _client, tree = build_client()
    interaction = MagicMock()
    interaction.response.is_done.return_value = False
    interaction.response.send_message = AsyncMock()
    interaction.followup.send = AsyncMock()

    asyncio.run(tree.on_error(interaction, app_commands.AppCommandError("boom")))

    interaction.response.send_message.assert_awaited_once()
    interaction.followup.send.assert_not_called()
    sent_text = interaction.response.send_message.call_args[0][0]
    assert "boom" not in sent_text
    assert "went wrong" in sent_text.lower()


def test_tree_error_handler_uses_followup_when_already_responded():
    from discord import app_commands

    _client, tree = build_client()
    interaction = MagicMock()
    interaction.response.is_done.return_value = True
    interaction.response.send_message = AsyncMock()
    interaction.followup.send = AsyncMock()

    asyncio.run(tree.on_error(interaction, app_commands.AppCommandError("boom")))

    interaction.followup.send.assert_awaited_once()
    interaction.response.send_message.assert_not_called()


def test_every_command_has_a_cooldown_check():
    _client, tree = build_client()

    for name in ("ping", "ask", "stats", "moves", "import", "scout", "team", "calc"):
        command = tree.get_command(name)
        assert len(command.checks) >= 1, f"/{name} has no cooldown check attached"


def test_tree_error_handler_gives_a_friendly_message_on_cooldown():
    from discord import app_commands
    from discord.app_commands.checks import Cooldown

    _client, tree = build_client()
    interaction = MagicMock()
    interaction.response.is_done.return_value = False
    interaction.response.send_message = AsyncMock()

    error = app_commands.CommandOnCooldown(Cooldown(1, 3.0), retry_after=2.5)
    asyncio.run(tree.on_error(interaction, error))

    sent_text = interaction.response.send_message.call_args[0][0]
    assert "2.5" in sent_text
    assert "wait" in sent_text.lower() or "slow down" in sent_text.lower()
