import asyncio

from bot.agentic import TOOLS, analyze_response_async, build_tool_dispatch
from rag.answer import MALFORMED_TOOL_CALL_MESSAGE

_RECORDS = [
    {
        "name": "Garchomp",
        "types": ["Dragon", "Ground"],
        "base_stats": {"hp": 108, "attack": 130, "defense": 95, "sp_attack": 80, "sp_defense": 85, "speed": 102},
        "abilities": ["Sand Veil", "Rough Skin"],
        "learnset": ["Earthquake", "Dragon Claw"],
    },
    {
        "name": "Incineroar",
        "types": ["Fire", "Dark"],
        "base_stats": {"hp": 95, "attack": 115, "defense": 90, "sp_attack": 80, "sp_defense": 90, "speed": 60},
        "abilities": ["Blaze", "Intimidate"],
        "learnset": ["Flare Blitz", "Knock Off"],
    },
]
_MOVES = [{"name": "Earthquake", "type": "Ground", "category": "Physical", "power": 100, "accuracy": 100, "pp": 10, "effect": None}]
_ITEMS = []
_USAGE = {"Garchomp": {"moves": [{"name": "Earthquake", "usage_pct": 90.0}], "items": [], "abilities": []}}


def test_tools_lists_exactly_the_three_specced_tools_with_valid_schema_shape():
    names = {tool["function"]["name"] for tool in TOOLS}

    assert names == {"run_damage_calc", "get_stored_team", "get_usage_stats"}
    for tool in TOOLS:
        assert tool["type"] == "function"
        assert "description" in tool["function"]
        assert "parameters" in tool["function"]


def test_run_damage_calc_dispatch_reaches_calc_response_with_the_right_arguments():
    dispatch = build_tool_dispatch(_RECORDS, _MOVES, _ITEMS, _USAGE, user_id=1)

    result = dispatch["run_damage_calc"]({
        "attacker_name": "Garchomp", "defender_name": "Incineroar", "move_name": "Earthquake",
    })

    assert "Garchomp" in result
    assert "Incineroar" in result


def test_get_stored_team_ignores_model_supplied_arguments_and_uses_the_bound_user_id(monkeypatch):
    calls = []
    monkeypatch.setattr("bot.agentic.get_team", lambda user_id, side: calls.append((user_id, side)) or [])

    dispatch = build_tool_dispatch(_RECORDS, _MOVES, _ITEMS, _USAGE, user_id=42)
    # A malicious/confused model tool call trying to name a different user --
    # must be ignored entirely, since get_stored_team's schema takes no args.
    dispatch["get_stored_team"]({"user_id": 999, "side": "opponent"})

    assert calls == [(42, "mine"), (42, "opponent")]


def test_get_stored_team_formats_both_sides_when_present(monkeypatch):
    def _fake_get_team(user_id, side):
        if side == "mine":
            return [{"species": "Garchomp", "item": None, "ability": None, "tera_type": None, "moves": [], "nature": "Hardy"}]
        return []

    monkeypatch.setattr("bot.agentic.get_team", _fake_get_team)
    dispatch = build_tool_dispatch(_RECORDS, _MOVES, _ITEMS, _USAGE, user_id=1)

    result = dispatch["get_stored_team"]({})

    assert "Garchomp" in result


def test_get_stored_team_reports_plainly_when_nothing_is_stored(monkeypatch):
    monkeypatch.setattr("bot.agentic.get_team", lambda user_id, side: [])
    dispatch = build_tool_dispatch(_RECORDS, _MOVES, _ITEMS, _USAGE, user_id=1)

    result = dispatch["get_stored_team"]({})

    assert "No stored team" in result


def test_get_usage_stats_dispatch_looks_up_the_named_pokemon():
    dispatch = build_tool_dispatch(_RECORDS, _MOVES, _ITEMS, _USAGE, user_id=1)

    result = dispatch["get_usage_stats"]({"name": "Garchomp"})

    assert "Earthquake" in result


def test_get_usage_stats_dispatch_reports_plainly_for_an_unknown_pokemon():
    dispatch = build_tool_dispatch(_RECORDS, _MOVES, _ITEMS, _USAGE, user_id=1)

    result = dispatch["get_usage_stats"]({"name": "NotAPokemon"})

    assert "No Pokemon named" in result


class _FakeAnswerer:
    def __init__(self, tool_result):
        self._tool_result = tool_result

    def answer_with_tools(self, question, tools, tool_dispatch, max_rounds=4, history=None):
        self.last_history = history
        return self._tool_result

    def answer(self, question, context_block):
        return "plain RAG fallback answer"


class _FakeIndex:
    def query(self, question, n_results=5, where=None):
        return [
            {
                "id": "Garchomp-stats",
                "text": "Some context chunk.",
                "metadata": {"pokemon": "Garchomp", "chunk_type": "stats"},
                "distance": 0.3,
            }
        ]


def test_analyze_response_async_returns_the_tool_answer_when_not_malformed():
    answerer = _FakeAnswerer("Incineroar resists Earthquake.")

    result = asyncio.run(analyze_response_async(
        answerer, "Is Incineroar a good check?", _RECORDS, _MOVES, _ITEMS, _USAGE, user_id=1,
        index=_FakeIndex(), bm25_index=None,
    ))

    assert result == "Incineroar resists Earthquake."


def test_analyze_response_async_falls_back_to_plain_rag_on_a_malformed_tool_call():
    answerer = _FakeAnswerer(MALFORMED_TOOL_CALL_MESSAGE)

    result = asyncio.run(analyze_response_async(
        answerer, "Is Incineroar a good check?", _RECORDS, _MOVES, _ITEMS, _USAGE, user_id=1,
        index=_FakeIndex(), bm25_index=None,
    ))

    assert result == "plain RAG fallback answer"


def test_analyze_response_async_threads_history_through_to_answer_with_tools():
    answerer = _FakeAnswerer("an answer")
    history = [{"role": "user", "content": "earlier question"}]

    asyncio.run(analyze_response_async(
        answerer, "new question", _RECORDS, _MOVES, _ITEMS, _USAGE, user_id=1,
        index=_FakeIndex(), bm25_index=None, history=history,
    ))

    assert answerer.last_history == history


def test_analyze_response_async_defaults_history_to_none_when_omitted():
    answerer = _FakeAnswerer("an answer")

    asyncio.run(analyze_response_async(
        answerer, "new question", _RECORDS, _MOVES, _ITEMS, _USAGE, user_id=1,
        index=_FakeIndex(), bm25_index=None,
    ))

    assert answerer.last_history is None
