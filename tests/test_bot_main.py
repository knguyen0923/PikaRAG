import asyncio
from unittest.mock import AsyncMock, MagicMock

import discord

import rag.answer
from bot.commands.ping import ping_response
from bot.main import _build_answerer, build_client


def _extract_text(mock_send) -> str:
    """The description of the discord.Embed a send_message/followup.send call was given."""
    _args, kwargs = mock_send.call_args
    return kwargs["embed"].description


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

    sent_text = _extract_text(interaction.response.send_message)
    assert "Earthquake" in sent_text
    assert "damage" in sent_text.lower()


def test_calc_command_sends_an_embed_with_the_calc_color():
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

    _args, kwargs = interaction.response.send_message.call_args
    embed = kwargs["embed"]
    assert isinstance(embed, discord.Embed)
    assert embed.color == discord.Color.red()


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
    sent_text = _extract_text(interaction.followup.send)
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
        return _extract_text(interaction.response.send_message)

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

    sent_text = _extract_text(interaction.response.send_message)
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

    sent_text = _extract_text(interaction.response.send_message)
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

    sent_text = _extract_text(interaction.response.send_message)
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
        def query(self, question, n_results=5, where=None):
            return [
                {
                    "id": "Whatever-stats",
                    "text": "Some chunk",
                    "metadata": {"pokemon": "Whatever", "chunk_type": "stats"},
                    "distance": 1.6,
                }
            ]

    _client, tree = build_client(index=_FakeIndex(), answerer=_FakeAnswerer())
    ask_command = tree.get_command("ask")
    interaction = MagicMock()
    interaction.user.id = user_id
    interaction.response.defer = AsyncMock()
    interaction.followup.send = AsyncMock()

    asyncio.run(ask_command.callback(interaction, question="What's a good lead?"))

    interaction.response.defer.assert_awaited_once()
    assert "Garchomp" in captured["context_block"]


def test_ask_command_narrows_retrieval_when_a_known_pokemon_is_named():
    class _FakeIndex:
        def __init__(self):
            self.queries = []

        def query(self, question, n_results=5, where=None):
            self.queries.append(where)
            return [
                {
                    "id": "Abomasnow-stats",
                    "text": "context from narrowed query",
                    "metadata": {"chunk_type": "stats"},
                    "distance": 0.3,
                }
            ]

    class _FakeAnswerer:
        def answer(self, question, context_block):
            return "an answer"

    fake_index = _FakeIndex()
    records = [{"name": "Abomasnow"}]
    _client, tree = build_client(index=fake_index, answerer=_FakeAnswerer(), records=records, items=[])
    ask_command = tree.get_command("ask")
    interaction = MagicMock()
    interaction.user.id = 9099
    interaction.response.defer = AsyncMock()
    interaction.followup.send = AsyncMock()

    asyncio.run(ask_command.callback(interaction, question="Does Abomasnow learn Attract?"))

    assert fake_index.queries == [{"pokemon": "Abomasnow"}]


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
            return _extract_text(interaction.followup.send)
        return _extract_text(interaction.response.send_message)

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
    sent_text = _extract_text(interaction.response.send_message)
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


def test_stats_command_uses_usage_data_when_provided():
    records = [{
        "name": "Abomasnow", "types": ["Grass", "Ice"],
        "base_stats": {"hp": 90, "attack": 92, "defense": 75, "sp_attack": 92, "sp_defense": 85, "speed": 60},
        "abilities": ["Snow Warning"], "learnset": ["Blizzard"], "legal_in": ["M-B"],
    }]
    usage = {"Abomasnow": {
        "moves": [], "abilities": [{"name": "Snow Warning", "usage_pct": 98.5}],
        "items": [{"name": "Focus Sash", "usage_pct": 40.0}],
    }}

    _client, tree = build_client(records=records, usage=usage)
    stats_cmd = tree.get_command("stats")
    interaction = MagicMock()
    interaction.user.id = 1
    interaction.response.send_message = AsyncMock()

    asyncio.run(stats_cmd.callback(interaction, name="Abomasnow"))

    sent_text = _extract_text(interaction.response.send_message)
    assert "Common build" in sent_text


def test_moves_command_uses_usage_data_when_provided():
    records = [{
        "name": "Abomasnow", "types": ["Grass", "Ice"],
        "base_stats": {"hp": 90, "attack": 92, "defense": 75, "sp_attack": 92, "sp_defense": 85, "speed": 60},
        "abilities": ["Snow Warning"], "learnset": ["Blizzard"], "legal_in": ["M-B"],
    }]
    usage = {"Abomasnow": {
        "moves": [{"name": "Blizzard", "usage_pct": 91.2}], "abilities": [], "items": [],
    }}

    _client, tree = build_client(records=records, usage=usage)
    moves_cmd = tree.get_command("moves")
    interaction = MagicMock()
    interaction.user.id = 1
    interaction.response.send_message = AsyncMock()

    asyncio.run(moves_cmd.callback(interaction, name="Abomasnow"))

    sent_text = _extract_text(interaction.response.send_message)
    assert "top moves" in sent_text.lower()


def test_tree_error_handler_gives_an_ephemeral_permission_message_on_check_failure():
    from discord import app_commands

    _client, tree = build_client()
    interaction = MagicMock()
    interaction.response.is_done.return_value = False
    interaction.response.send_message = AsyncMock()

    error = app_commands.CheckFailure("owner only")
    asyncio.run(tree.on_error(interaction, error))

    _args, kwargs = interaction.response.send_message.call_args
    assert kwargs["ephemeral"] is True
    assert "permission" in kwargs["embed"].description.lower()


def test_tree_error_handler_gives_a_friendly_message_on_cooldown():
    from discord import app_commands
    from discord.app_commands.checks import Cooldown

    _client, tree = build_client()
    interaction = MagicMock()
    interaction.response.is_done.return_value = False
    interaction.response.send_message = AsyncMock()

    error = app_commands.CommandOnCooldown(Cooldown(1, 3.0), retry_after=2.5)
    asyncio.run(tree.on_error(interaction, error))

    sent_text = _extract_text(interaction.response.send_message)
    assert "2.5" in sent_text
    assert "wait" in sent_text.lower() or "slow down" in sent_text.lower()


class _FakeResponse:
    def json(self):
        return {"message": {"content": "ok"}}

    def raise_for_status(self):
        pass


def test_build_answerer_reads_llm_host_and_model_from_env(monkeypatch):
    monkeypatch.setenv("LLM_HOST", "100.1.2.3:11434")
    monkeypatch.setenv("LLM_MODEL", "phi3:mini")
    calls = []
    monkeypatch.setattr(
        rag.answer.requests, "post",
        lambda url, json=None, timeout=None: calls.append({"url": url, "json": json}) or _FakeResponse(),
    )

    _build_answerer().answer("question", "context")

    assert calls[0]["url"] == "http://100.1.2.3:11434/api/chat"
    assert calls[0]["json"]["model"] == "phi3:mini"


def test_build_answerer_defaults_model_when_unset(monkeypatch):
    monkeypatch.setenv("LLM_HOST", "100.1.2.3:11434")
    monkeypatch.delenv("LLM_MODEL", raising=False)
    calls = []
    monkeypatch.setattr(
        rag.answer.requests, "post",
        lambda url, json=None, timeout=None: calls.append({"url": url, "json": json}) or _FakeResponse(),
    )

    _build_answerer().answer("question", "context")

    assert calls[0]["json"]["model"] == "llama3.2:3b"


def test_build_answerer_reads_llm_timeout_from_env(monkeypatch):
    monkeypatch.setenv("LLM_HOST", "100.1.2.3:11434")
    monkeypatch.setenv("LLM_TIMEOUT", "60")
    calls = []
    monkeypatch.setattr(
        rag.answer.requests, "post",
        lambda url, json=None, timeout=None: calls.append({"timeout": timeout}) or _FakeResponse(),
    )

    _build_answerer().answer("question", "context")

    assert calls[0]["timeout"] == 60.0


def test_build_answerer_defaults_timeout_when_unset(monkeypatch):
    monkeypatch.setenv("LLM_HOST", "100.1.2.3:11434")
    monkeypatch.delenv("LLM_TIMEOUT", raising=False)
    calls = []
    monkeypatch.setattr(
        rag.answer.requests, "post",
        lambda url, json=None, timeout=None: calls.append({"timeout": timeout}) or _FakeResponse(),
    )

    _build_answerer().answer("question", "context")

    assert calls[0]["timeout"] == 30.0


def test_ask_command_logs_the_call_via_log_ask(monkeypatch):
    calls = []

    def _fake_log_ask(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr("bot.main.log_ask", _fake_log_ask)

    class _FakeIndex:
        def query(self, question, n_results=5, where=None):
            return [
                {
                    "id": "Gyarados-stats",
                    "text": "Gyarados stats chunk",
                    "metadata": {"pokemon": "Gyarados", "chunk_type": "stats"},
                    "distance": 0.3,
                }
            ]

    class _FakeAnswerer:
        def answer(self, question, context_block):
            return "Gyarados has 95 base HP."

    _client, tree = build_client(index=_FakeIndex(), answerer=_FakeAnswerer())
    ask_command = tree.get_command("ask")
    interaction = MagicMock()
    interaction.user.id = 9200
    interaction.response.defer = AsyncMock()
    interaction.followup.send = AsyncMock()

    asyncio.run(ask_command.callback(interaction, question="How bulky is Gyarados?"))

    assert len(calls) == 1
    logged = calls[0]
    assert logged["question"] == "How bulky is Gyarados?"
    assert logged["answer"] == "Gyarados has 95 base HP."
    assert logged["retrieved_chunks"] == [{"id": "Gyarados-stats", "distance": 0.3}]
    assert logged["sources"] == [{"name": "Gyarados", "chunk_type": "stats"}]
    assert logged["best_distance"] == 0.3
    assert logged["gate_fired"] is False
    assert logged["degraded"] is False
    assert isinstance(logged["latency_ms"], int)
    assert isinstance(logged["timestamp"], str)


def test_ask_command_still_sends_the_answer_when_log_ask_raises(monkeypatch):
    def _raising_log_ask(**kwargs):
        raise RuntimeError("disk full")

    monkeypatch.setattr("bot.main.log_ask", _raising_log_ask)

    class _FakeIndex:
        def query(self, question, n_results=5, where=None):
            return [
                {
                    "id": "Gyarados-stats",
                    "text": "Gyarados stats chunk",
                    "metadata": {"pokemon": "Gyarados", "chunk_type": "stats"},
                    "distance": 0.3,
                }
            ]

    class _FakeAnswerer:
        def answer(self, question, context_block):
            return "Gyarados has 95 base HP."

    _client, tree = build_client(index=_FakeIndex(), answerer=_FakeAnswerer())
    ask_command = tree.get_command("ask")
    interaction = MagicMock()
    interaction.user.id = 9201
    interaction.response.defer = AsyncMock()
    interaction.followup.send = AsyncMock()

    asyncio.run(ask_command.callback(interaction, question="How bulky is Gyarados?"))

    sent_text = _extract_text(interaction.followup.send)
    assert "Gyarados has 95 base HP." in sent_text


def test_ask_command_embed_includes_a_sources_line():
    class _FakeIndex:
        def query(self, question, n_results=5, where=None):
            return [
                {
                    "id": "Landorus-Therian-stats",
                    "text": "Landorus-Therian stats chunk",
                    "metadata": {"pokemon": "Landorus-Therian", "chunk_type": "stats"},
                    "distance": 0.3,
                }
            ]

    class _FakeAnswerer:
        def answer(self, question, context_block):
            return "Landorus-Therian has base 91 Speed."

    _client, tree = build_client(index=_FakeIndex(), answerer=_FakeAnswerer())
    ask_command = tree.get_command("ask")
    interaction = MagicMock()
    interaction.user.id = 9100
    interaction.response.defer = AsyncMock()
    interaction.followup.send = AsyncMock()

    asyncio.run(ask_command.callback(interaction, question="How fast is Landorus-Therian?"))

    sent_text = _extract_text(interaction.followup.send)
    assert "Landorus-Therian has base 91 Speed." in sent_text
    assert "Sources: Landorus-Therian (stats)" in sent_text


def test_owner_only_rejects_a_non_owner(monkeypatch):
    from bot.main import _owner_only

    monkeypatch.setenv("BOT_OWNER_ID", "12345")
    interaction = MagicMock()
    interaction.user.id = 99999

    assert _owner_only(interaction) is False


def test_owner_only_allows_the_owner(monkeypatch):
    from bot.main import _owner_only

    monkeypatch.setenv("BOT_OWNER_ID", "12345")
    interaction = MagicMock()
    interaction.user.id = 12345

    assert _owner_only(interaction) is True


def test_owner_only_rejects_everyone_when_bot_owner_id_is_unset(monkeypatch):
    from bot.main import _owner_only

    monkeypatch.delenv("BOT_OWNER_ID", raising=False)
    interaction = MagicMock()
    interaction.user.id = 12345

    assert _owner_only(interaction) is False


def test_owner_only_rejects_everyone_when_bot_owner_id_is_malformed(monkeypatch):
    from bot.main import _owner_only

    monkeypatch.setenv("BOT_OWNER_ID", "not-a-number")
    interaction = MagicMock()
    interaction.user.id = 12345

    assert _owner_only(interaction) is False


def test_debug_last_command_is_registered_with_an_owner_only_check():
    _client, tree = build_client()
    command = tree.get_command("debug-last")

    assert command is not None
    assert len(command.checks) >= 1


def test_debug_last_shows_the_most_recent_logged_call(monkeypatch):
    monkeypatch.setenv("BOT_OWNER_ID", "12345")
    monkeypatch.setattr(
        "bot.main.get_last_ask_log",
        lambda: {
            "timestamp": "2026-09-14T12:00:00+00:00",
            "question": "How bulky is Gyarados?",
            "answer": "Gyarados has 95 base HP.",
            "sources": [{"name": "Gyarados", "chunk_type": "stats"}],
            "retrieved_chunks": [{"id": "Gyarados-stats", "distance": 0.4}],
            "best_distance": 0.4,
            "gate_fired": False,
            "degraded": False,
            "latency_ms": 900,
        },
    )

    _client, tree = build_client()
    debug_command = tree.get_command("debug-last")
    interaction = MagicMock()
    interaction.user.id = 12345
    interaction.response.send_message = AsyncMock()

    asyncio.run(debug_command.callback(interaction))

    sent_text = _extract_text(interaction.response.send_message)
    assert "How bulky is Gyarados?" in sent_text
    assert "Gyarados has 95 base HP." in sent_text


def test_debug_last_reports_plainly_when_nothing_is_logged_yet(monkeypatch):
    monkeypatch.setenv("BOT_OWNER_ID", "12345")
    monkeypatch.setattr("bot.main.get_last_ask_log", lambda: None)

    _client, tree = build_client()
    debug_command = tree.get_command("debug-last")
    interaction = MagicMock()
    interaction.user.id = 12345
    interaction.response.send_message = AsyncMock()

    asyncio.run(debug_command.callback(interaction))

    sent_text = _extract_text(interaction.response.send_message)
    assert "No /ask calls logged yet." in sent_text


def test_debug_last_replies_ephemerally_so_it_is_not_leaked_to_the_channel(monkeypatch):
    # /debug-last shows the MOST RECENT /ask call, which may belong to any
    # user in the server -- not the owner running the command. It must be
    # ephemeral so the question/answer/chunk IDs aren't republished publicly.
    monkeypatch.setenv("BOT_OWNER_ID", "12345")
    monkeypatch.setattr(
        "bot.main.get_last_ask_log",
        lambda: {
            "timestamp": "2026-09-14T12:00:00+00:00",
            "question": "How bulky is Gyarados?",
            "answer": "Gyarados has 95 base HP.",
            "sources": [{"name": "Gyarados", "chunk_type": "stats"}],
            "retrieved_chunks": [{"id": "Gyarados-stats", "distance": 0.4}],
            "best_distance": 0.4,
            "gate_fired": False,
            "degraded": False,
            "latency_ms": 900,
        },
    )

    _client, tree = build_client()
    debug_command = tree.get_command("debug-last")
    interaction = MagicMock()
    interaction.user.id = 12345
    interaction.response.send_message = AsyncMock()

    asyncio.run(debug_command.callback(interaction))

    _args, kwargs = interaction.response.send_message.call_args
    assert kwargs["ephemeral"] is True


def test_ask_command_logs_gate_fired_true_when_only_far_matches_are_retrieved(monkeypatch):
    # DISTANCE_THRESHOLD in bot/commands/ask.py is 1.4 -- a best match
    # farther than that (and no extra_context) should trip the confidence
    # gate. This proves `gate_fired=result["answer"] == GATE_MESSAGE` in
    # bot/main.py's ask handler actually evaluates True when it should,
    # at the handler-integration layer (not just inside ask_response()).
    calls = []

    def _fake_log_ask(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr("bot.main.log_ask", _fake_log_ask)

    class _FakeIndex:
        def query(self, question, n_results=5, where=None):
            return [
                {
                    "id": "Whatever-stats",
                    "text": "Some chunk",
                    "metadata": {"pokemon": "Whatever", "chunk_type": "stats"},
                    "distance": 1.6,
                }
            ]

    class _FakeAnswerer:
        def answer(self, question, context_block):
            raise AssertionError("answerer should not be called when the gate fires")

    _client, tree = build_client(index=_FakeIndex(), answerer=_FakeAnswerer())
    ask_command = tree.get_command("ask")
    interaction = MagicMock()
    interaction.user.id = 9300  # no stored team context for this user
    interaction.response.defer = AsyncMock()
    interaction.followup.send = AsyncMock()

    asyncio.run(ask_command.callback(interaction, question="What is the capital of France?"))

    assert len(calls) == 1
    assert calls[0]["gate_fired"] is True
    assert calls[0]["degraded"] is False


def test_ask_command_logs_degraded_true_when_the_answerer_is_offline(monkeypatch):
    # Proves `degraded=result["answer"] == OFFLINE_MESSAGE` actually
    # evaluates True at the handler-integration layer when the answerer
    # reports it's offline.
    from rag.answer import OFFLINE_MESSAGE

    calls = []

    def _fake_log_ask(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr("bot.main.log_ask", _fake_log_ask)

    class _FakeIndex:
        def query(self, question, n_results=5, where=None):
            return [
                {
                    "id": "Gyarados-stats",
                    "text": "Gyarados stats chunk",
                    "metadata": {"pokemon": "Gyarados", "chunk_type": "stats"},
                    "distance": 0.3,
                }
            ]

    class _FakeAnswerer:
        def answer(self, question, context_block):
            return OFFLINE_MESSAGE

    _client, tree = build_client(index=_FakeIndex(), answerer=_FakeAnswerer())
    ask_command = tree.get_command("ask")
    interaction = MagicMock()
    interaction.user.id = 9301
    interaction.response.defer = AsyncMock()
    interaction.followup.send = AsyncMock()

    asyncio.run(ask_command.callback(interaction, question="How bulky is Gyarados?"))

    assert len(calls) == 1
    assert calls[0]["degraded"] is True
    assert calls[0]["gate_fired"] is False


def test_llmstatus_command_is_registered_with_cooldown_and_owner_only_checks():
    _client, tree = build_client()
    command = tree.get_command("llmstatus")

    assert command is not None
    assert len(command.checks) >= 2


def test_llmstatus_command_reports_up_with_configured_model_and_breaker_state():
    class _FakeRawAnswerer:
        model = "llama3.2:3b"

        def check_health(self):
            return {"up": True, "models": ["llama3.2:3b"]}

    class _FakeBreaker:
        state = "closed"

        def answer(self, question, context_block):
            return "unused"

    _client, tree = build_client(answerer=_FakeBreaker(), raw_answerer=_FakeRawAnswerer())
    command = tree.get_command("llmstatus")
    interaction = MagicMock()
    interaction.user.id = 1
    interaction.response.defer = AsyncMock()
    interaction.followup.send = AsyncMock()

    asyncio.run(command.callback(interaction))

    interaction.response.defer.assert_awaited_once()
    sent_text = _extract_text(interaction.followup.send)
    assert "Online" in sent_text
    assert "llama3.2:3b" in sent_text
    assert "closed" in sent_text


def test_llmstatus_command_reports_down_with_the_breaker_state():
    class _FakeRawAnswerer:
        model = "llama3.2:3b"

        def check_health(self):
            return {"up": False, "models": []}

    class _FakeBreaker:
        state = "open"

        def answer(self, question, context_block):
            return "unused"

    _client, tree = build_client(answerer=_FakeBreaker(), raw_answerer=_FakeRawAnswerer())
    command = tree.get_command("llmstatus")
    interaction = MagicMock()
    interaction.user.id = 1
    interaction.response.defer = AsyncMock()
    interaction.followup.send = AsyncMock()

    asyncio.run(command.callback(interaction))

    interaction.response.defer.assert_awaited_once()
    sent_text = _extract_text(interaction.followup.send)
    assert "Offline" in sent_text
    assert "open" in sent_text


def test_llmstatus_replies_ephemerally():
    class _FakeRawAnswerer:
        model = "llama3.2:3b"

        def check_health(self):
            return {"up": False, "models": []}

    class _FakeBreaker:
        state = "open"

        def answer(self, question, context_block):
            return "unused"

    _client, tree = build_client(answerer=_FakeBreaker(), raw_answerer=_FakeRawAnswerer())
    command = tree.get_command("llmstatus")
    interaction = MagicMock()
    interaction.user.id = 1
    interaction.response.defer = AsyncMock()
    interaction.followup.send = AsyncMock()

    asyncio.run(command.callback(interaction))

    interaction.response.defer.assert_awaited_once()
    _args, kwargs = interaction.followup.send.call_args
    assert kwargs["ephemeral"] is True
