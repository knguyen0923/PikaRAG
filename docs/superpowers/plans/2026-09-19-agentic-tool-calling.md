# Agentic /ask + /calc Tool-Calling Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a new `/analyze` Discord command that lets the LLM orchestrate the existing damage calculator, stored-team lookup, and usage-stats lookup across multiple tool-call round-trips to answer open-ended questions (e.g. "is Landorus a good check to this team?") — without ever letting the model compute damage itself, and without touching `/ask` or `/calc`'s existing behavior.

**Architecture:** `OllamaAnswerer` (`rag/answer.py`) gains a new method, `answer_with_tools(question, tools, tool_dispatch, max_rounds=4)`, alongside its existing `answer()`/`answer_bare()`. It drives Ollama's native `/api/chat` tool-calling loop: send the question + tool schemas, dispatch any tool call the model emits, append the result as a `tool`-role message, repeat up to `max_rounds`; on hitting the cap, force one final non-tool call for a best-effort answer. A new `bot/agentic.py` module defines the three tool JSON schemas and `build_tool_dispatch(...)`, which binds each tool's implementation to real request context (`records`/`moves`/`items`/`usage` from the loaded data, `user_id` from the Discord interaction) so the model's tool-call arguments can never carry anything security-sensitive. `bot/main.py` wires a new `/analyze` command that calls `raw_answerer.answer_with_tools(...)` (via `bot/agentic.py`'s orchestration helper) and falls back to a plain RAG answer through the existing `ask_response_async` path if the model's tool call was malformed or hallucinated.

**Tech Stack:** Existing `requests`-based `OllamaAnswerer` client, Ollama's native `/api/chat` `tools` parameter (no new dependency), `discord.py`'s existing command/defer pattern.

**Spec:** `docs/superpowers/specs/2026-09-17-agentic-tool-calling-design.md`

## Global Constraints

- New command (`/analyze`), not an extension of `/ask` — `/ask`'s command handler, `ask_response`/`ask_response_async`, and `OllamaAnswerer.answer`/`answer_bare` are untouched.
- The model never computes damage itself — it only ever sees `run_damage_calc`'s deterministic string output (from the existing `calc_response` pure function, reused as-is) and reasons over that text. This is the one invariant that must not weaken under any failure path.
- `user_id` is supplied by the command handler from the real Discord interaction (`interaction.user.id`), never taken from the model's tool-call arguments. `get_stored_team`'s tool schema takes **no arguments at all** and always returns both the calling user's "mine" and "opponent" stored teams together — the model never gets to pick whose team or which side, so a confused or adversarial prompt can't spoof whose stored team gets read.
- Round-trip cap: 4. On hitting the cap, force a final answer from whatever tool results have been gathered so far — never an infinite loop, never a raw error.
- On a malformed/hallucinated tool call (unknown tool name, arguments that aren't a JSON object, or a tool call that raises when dispatched due to missing/invalid required fields), drop tool-calling entirely and retry once as a plain RAG-style answer through the existing `ask_response_async` path — mirroring the existing `OFFLINE_MESSAGE` degradation pattern (structural check on the return value, not catching exceptions from Ollama itself, matching `rag/circuit_breaker.py`'s convention).
- `/analyze` defers immediately (`interaction.response.defer()` + `followup.send()`), same pattern as `/ask` and `/llmstatus`.
- `CircuitBreaker` (`rag/circuit_breaker.py`) only implements `.answer(question, context_block)`, not `.answer_with_tools(...)` — extending it is out of scope (spec: "Any change to `/ask`'s or `/calc`'s existing behavior" is out of scope, and `CircuitBreaker` exists for `/ask`'s protection). `/analyze` therefore calls `raw_answerer.answer_with_tools(...)` directly, the same way `/llmstatus` already calls `raw_answerer.check_health()` directly — no circuit-breaker protection on this path. Document this in the command's docstring/description, don't silently paper over it.
- No new tools beyond the three listed (damage calculator, stored-team lookup, usage stats). No persisting conversation state across multiple `/analyze` invocations — each call is single-turn from the user's side, even though it may involve multiple tool round-trips internally.

---

## File Structure

- Modify: `rag/answer.py` — add `TOOLS_SYSTEM_PROMPT`, `MALFORMED_TOOL_CALL_MESSAGE` constants and `OllamaAnswerer.answer_with_tools(...)`.
- Modify: `tests/test_rag_answer.py` — tests for `answer_with_tools`.
- Create: `bot/agentic.py` — `RUN_DAMAGE_CALC_TOOL`/`GET_STORED_TEAM_TOOL`/`GET_USAGE_STATS_TOOL`/`TOOLS`, `build_tool_dispatch(...)`, `analyze_response_async(...)`.
- Create: `tests/test_bot_agentic.py` — unit tests for the tool schemas, dispatch functions, and the orchestration/fallback logic.
- Modify: `bot/main.py` — import `analyze_response_async`, add `"analyze"` to `_COMMAND_COLORS`, wire the `/analyze` command.
- Modify: `tests/test_bot_main.py` — tests proving `/analyze` is registered, defers, calls through to `analyze_response_async` with the right context, and sends the result.
- Modify: `IMPROVEMENTS.md` — mark the item done.

---

### Task 1: `OllamaAnswerer.answer_with_tools`

**Files:**
- Modify: `rag/answer.py`
- Test: `tests/test_rag_answer.py`

**Interfaces:**
- Consumes: nothing new from other tasks — same `self._client`/`self._host`/`self._model`/`self._timeout` `OllamaAnswerer` already has.
- Produces: `OllamaAnswerer.answer_with_tools(question: str, tools: list, tool_dispatch: dict, max_rounds: int = 4) -> str`, `MALFORMED_TOOL_CALL_MESSAGE` (module constant, a fixed sentinel string), both consumed by Task 3's `bot/agentic.py`. `tool_dispatch` is `dict[str, Callable[[dict], str]]` — each value takes the tool call's parsed `arguments` dict and returns a string result.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_rag_answer.py` (reusing `_FakeOllamaClient`/`_FakeOllamaResponse` already defined there):

```python
from rag.answer import MALFORMED_TOOL_CALL_MESSAGE


def _tool_call_response(name, arguments, content=""):
    return {"message": {"role": "assistant", "content": content, "tool_calls": [{"function": {"name": name, "arguments": arguments}}]}}


def _final_response(content):
    return {"message": {"role": "assistant", "content": content}}


class _FakeSequentialOllamaClient:
    """Returns one canned response per call, in order -- for testing
    multi-round tool-calling loops where each round needs a different
    response."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def post(self, url, json=None, timeout=None):
        self.calls.append({"url": url, "json": json, "timeout": timeout})
        return _FakeOllamaResponse(self._responses.pop(0))


def test_answer_with_tools_returns_the_final_answer_when_no_tool_call_is_made():
    client = _FakeSequentialOllamaClient([_final_response("42 base HP.")])
    answerer = OllamaAnswerer(host="100.1.2.3:11434", client=client)

    result = answerer.answer_with_tools("How bulky is Gyarados?", tools=[], tool_dispatch={})

    assert result == "42 base HP."


def test_answer_with_tools_dispatches_a_single_tool_call_then_returns_the_final_answer():
    client = _FakeSequentialOllamaClient([
        _tool_call_response("run_damage_calc", {"attacker_name": "Garchomp"}),
        _final_response("It does a lot of damage."),
    ])
    dispatch_calls = []
    tool_dispatch = {"run_damage_calc": lambda args: dispatch_calls.append(args) or "42-50% damage"}
    answerer = OllamaAnswerer(host="100.1.2.3:11434", client=client)

    result = answerer.answer_with_tools("q?", tools=[{"some": "schema"}], tool_dispatch=tool_dispatch)

    assert result == "It does a lot of damage."
    assert dispatch_calls == [{"attacker_name": "Garchomp"}]
    # The tool result was appended as a tool-role message for the second call.
    second_call_messages = client.calls[1]["json"]["messages"]
    assert any(m.get("role") == "tool" and "42-50% damage" in m.get("content", "") for m in second_call_messages)


def test_answer_with_tools_sends_the_tools_schema_on_every_call():
    client = _FakeSequentialOllamaClient([_final_response("answer")])
    tools = [{"type": "function", "function": {"name": "run_damage_calc"}}]
    answerer = OllamaAnswerer(host="100.1.2.3:11434", client=client)

    answerer.answer_with_tools("q?", tools=tools, tool_dispatch={})

    assert client.calls[0]["json"]["tools"] == tools


def test_answer_with_tools_forces_a_final_answer_after_hitting_the_round_cap():
    # 4 rounds of "still calling a tool", then one final forced call with no
    # more tools offered.
    responses = [_tool_call_response("run_damage_calc", {"attacker_name": "Garchomp"}) for _ in range(4)]
    responses.append(_final_response("Best guess given what I found."))
    client = _FakeSequentialOllamaClient(responses)
    tool_dispatch = {"run_damage_calc": lambda args: "some result"}
    answerer = OllamaAnswerer(host="100.1.2.3:11434", client=client)

    result = answerer.answer_with_tools("q?", tools=[{"x": 1}], tool_dispatch=tool_dispatch, max_rounds=4)

    assert result == "Best guess given what I found."
    assert len(client.calls) == 5  # 4 tool-calling rounds + 1 forced final call
    # The forced final call must not offer tools again (no more calls allowed).
    assert "tools" not in client.calls[4]["json"]


def test_answer_with_tools_degrades_on_an_unknown_tool_name():
    client = _FakeSequentialOllamaClient([_tool_call_response("not_a_real_tool", {})])
    answerer = OllamaAnswerer(host="100.1.2.3:11434", client=client)

    result = answerer.answer_with_tools("q?", tools=[], tool_dispatch={"run_damage_calc": lambda args: "x"})

    assert result == MALFORMED_TOOL_CALL_MESSAGE


def test_answer_with_tools_degrades_on_arguments_that_are_not_an_object():
    client = _FakeSequentialOllamaClient([_tool_call_response("run_damage_calc", "not valid json{")])
    answerer = OllamaAnswerer(host="100.1.2.3:11434", client=client)

    result = answerer.answer_with_tools("q?", tools=[], tool_dispatch={"run_damage_calc": lambda args: "x"})

    assert result == MALFORMED_TOOL_CALL_MESSAGE


def test_answer_with_tools_degrades_when_the_dispatched_tool_raises_on_bad_arguments():
    def _raises(args):
        raise KeyError("attacker_name")

    client = _FakeSequentialOllamaClient([_tool_call_response("run_damage_calc", {})])
    answerer = OllamaAnswerer(host="100.1.2.3:11434", client=client)

    result = answerer.answer_with_tools("q?", tools=[], tool_dispatch={"run_damage_calc": _raises})

    assert result == MALFORMED_TOOL_CALL_MESSAGE


def test_answer_with_tools_returns_offline_message_on_connection_error():
    client = _FakeOllamaClient(exception=requests.exceptions.ConnectionError("refused"))
    answerer = OllamaAnswerer(host="100.1.2.3:11434", client=client)

    result = answerer.answer_with_tools("q?", tools=[], tool_dispatch={})

    assert result == OFFLINE_MESSAGE
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_rag_answer.py -v -k answer_with_tools`
Expected: FAIL with `AttributeError: 'OllamaAnswerer' object has no attribute 'answer_with_tools'` (and an `ImportError` on `MALFORMED_TOOL_CALL_MESSAGE` for the tests that import it directly).

- [ ] **Step 3: Implement `answer_with_tools`**

In `rag/answer.py`, add `import json` to the top-level imports, and add these constants near `BARE_SYSTEM_PROMPT`:

```python
TOOLS_SYSTEM_PROMPT = (
    "You are a Pokemon VGC doubles assistant with access to tools: a "
    "deterministic damage calculator, stored-team lookup, and usage-rate "
    "stats. Use tools to gather facts before answering. Never compute "
    "damage yourself -- always call run_damage_calc for any damage "
    "question. Give a concise final answer once you have what you need."
)

# Returned by answer_with_tools when the model's tool call is malformed or
# hallucinated (unknown tool name, non-object arguments, or a dispatch
# failure from missing/invalid required fields) -- signals the caller
# (bot/agentic.py) to drop tool-calling and retry as a plain RAG answer.
# A fixed sentinel string, same pattern as OFFLINE_MESSAGE.
MALFORMED_TOOL_CALL_MESSAGE = "The assistant's tool call could not be understood -- falling back to a plain answer."
```

Add the method to `OllamaAnswerer` (after `answer_bare`):

```python
    def answer_with_tools(
        self, question: str, tools: list, tool_dispatch: dict, max_rounds: int = 4
    ) -> str:
        """Drives Ollama's native tool-calling loop: send the question +
        tool schemas, dispatch any tool call the model emits, append the
        result as a tool-role message, repeat up to max_rounds. On hitting
        the cap, forces one final non-tool call for a best-effort answer.

        Returns MALFORMED_TOOL_CALL_MESSAGE (not an exception) if the model
        emits an unknown tool name, non-object arguments, or a tool call
        that fails to dispatch due to missing/invalid required fields --
        the caller is expected to check for this sentinel and degrade to a
        plain RAG answer. Returns OFFLINE_MESSAGE on any network/parsing
        failure talking to Ollama itself, same as answer()/answer_bare()."""
        messages = [
            {"role": "system", "content": TOOLS_SYSTEM_PROMPT},
            {"role": "user", "content": question},
        ]

        for _ in range(max_rounds):
            try:
                response = self._client.post(
                    f"http://{self._host}/api/chat",
                    json={
                        "model": self._model,
                        "messages": messages,
                        "tools": tools,
                        "stream": False,
                        "options": {"num_predict": 1024},
                    },
                    timeout=self._timeout,
                )
                response.raise_for_status()
                message = response.json()["message"]
            except (requests.RequestException, KeyError, TypeError) as e:
                print(f"OllamaAnswerer call failed: {e!r}")
                return OFFLINE_MESSAGE

            tool_calls = message.get("tool_calls")
            if not tool_calls:
                return message.get("content", "")

            messages.append(message)
            for call in tool_calls:
                function = call.get("function") if isinstance(call, dict) else None
                if not isinstance(function, dict):
                    return MALFORMED_TOOL_CALL_MESSAGE

                name = function.get("name")
                arguments = function.get("arguments")
                if isinstance(arguments, str):
                    try:
                        arguments = json.loads(arguments)
                    except json.JSONDecodeError:
                        return MALFORMED_TOOL_CALL_MESSAGE

                if name not in tool_dispatch or not isinstance(arguments, dict):
                    return MALFORMED_TOOL_CALL_MESSAGE

                try:
                    result = tool_dispatch[name](arguments)
                except (KeyError, TypeError, ValueError):
                    return MALFORMED_TOOL_CALL_MESSAGE

                messages.append({"role": "tool", "content": str(result)})

        messages.append({
            "role": "user",
            "content": "Give your best final answer now, using the tool results above.",
        })
        try:
            response = self._client.post(
                f"http://{self._host}/api/chat",
                json={
                    "model": self._model,
                    "messages": messages,
                    "stream": False,
                    "options": {"num_predict": 1024},
                },
                timeout=self._timeout,
            )
            response.raise_for_status()
            return response.json()["message"].get("content", "")
        except (requests.RequestException, KeyError, TypeError) as e:
            print(f"OllamaAnswerer call failed: {e!r}")
            return OFFLINE_MESSAGE
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_rag_answer.py -v`
Expected: all pass (existing `answer()`/`answer_bare()` tests + new `answer_with_tools` tests)

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest -q`
Expected: all tests pass, no regressions.

- [ ] **Step 6: Commit**

```bash
git add rag/answer.py tests/test_rag_answer.py
git commit -m "feat: add OllamaAnswerer.answer_with_tools for agentic tool-calling" -m "$(printf 'Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>')"
```

---

### Task 2: `bot/agentic.py` — tool schemas, dispatch, orchestration

**Files:**
- Create: `bot/agentic.py`
- Test: `tests/test_bot_agentic.py`

**Interfaces:**
- Consumes: Task 1's `OllamaAnswerer.answer_with_tools`, `MALFORMED_TOOL_CALL_MESSAGE`; existing `bot.commands.calc.calc_response`, `bot.commands.team.format_team_block`, `bot.pokemon_lookup.find_record`, `bot.pokemon_lookup.usage_for_record`, `bot.team_store.get_team`, `bot.commands.ask.ask_response_async`.
- Produces: `TOOLS: list` (the 3 tool schemas), `build_tool_dispatch(records, moves, items, usage, user_id) -> dict[str, Callable[[dict], str]]`, `analyze_response_async(answerer, question, records, moves, items, usage, user_id, index=None, bm25_index=None) -> str`. Task 3's `bot/main.py` calls `analyze_response_async` directly; nothing else calls `build_tool_dispatch` or `TOOLS` outside this module and its tests.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_bot_agentic.py`:

```python
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

    def answer_with_tools(self, question, tools, tool_dispatch, max_rounds=4):
        return self._tool_result

    def answer(self, question, context_block):
        return "plain RAG fallback answer"


class _FakeIndex:
    def query(self, question, n_results=5, where=None):
        return []


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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_bot_agentic.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bot.agentic'`

- [ ] **Step 3: Implement `bot/agentic.py`**

```python
import json
from typing import Callable, Optional

from bot.commands.ask import ask_response_async
from bot.commands.calc import calc_response
from bot.commands.team import format_team_block
from bot.pokemon_lookup import find_record, usage_for_record
from bot.team_store import get_team
from rag.answer import MALFORMED_TOOL_CALL_MESSAGE

RUN_DAMAGE_CALC_TOOL = {
    "type": "function",
    "function": {
        "name": "run_damage_calc",
        "description": (
            "Calculate a deterministic damage range for one attacker's move "
            "against one defender, VGC-standard (level 50, 31 IVs, neutral "
            "stat stages unless overridden). Always use this tool for any "
            "damage question -- never compute damage yourself."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "attacker_name": {"type": "string", "description": "The attacking Pokemon's name."},
                "defender_name": {"type": "string", "description": "The defending Pokemon's name."},
                "move_name": {"type": "string", "description": "The move being used."},
                "attacker_item": {"type": "string", "description": "The attacker's held item, if any."},
                "attacker_ability": {"type": "string", "description": "The attacker's ability, if any."},
                "attacker_tera": {"type": "string", "description": "The attacker's Tera type, if Terastallized."},
                "defender_item": {"type": "string", "description": "The defender's held item, if any."},
                "defender_ability": {"type": "string", "description": "The defender's ability, if any."},
                "defender_tera": {"type": "string", "description": "The defender's Tera type, if Terastallized."},
                "weather": {"type": "string", "description": "Active weather, if any (e.g. 'Sun', 'Rain')."},
                "terrain": {"type": "string", "description": "Active terrain, if any (e.g. 'Electric', 'Grassy')."},
            },
            "required": ["attacker_name", "defender_name", "move_name"],
        },
    },
}

GET_STORED_TEAM_TOOL = {
    "type": "function",
    "function": {
        "name": "get_stored_team",
        "description": (
            "Look up the current user's stored team and the stored opponent "
            "team, if any have been saved via /scout or /import. Takes no "
            "arguments -- always returns the calling user's own stored teams."
        ),
        "parameters": {"type": "object", "properties": {}},
    },
}

GET_USAGE_STATS_TOOL = {
    "type": "function",
    "function": {
        "name": "get_usage_stats",
        "description": "Look up a Pokemon's competitive usage-rate statistics, if available.",
        "parameters": {
            "type": "object",
            "properties": {"name": {"type": "string", "description": "The Pokemon's name."}},
            "required": ["name"],
        },
    },
}

TOOLS = [RUN_DAMAGE_CALC_TOOL, GET_STORED_TEAM_TOOL, GET_USAGE_STATS_TOOL]


def _run_damage_calc(records: list, moves: list, items: list, arguments: dict) -> str:
    return calc_response(
        records, moves,
        attacker_name=arguments["attacker_name"],
        defender_name=arguments["defender_name"],
        move_name=arguments["move_name"],
        items=items,
        attacker_item=arguments.get("attacker_item"),
        attacker_ability=arguments.get("attacker_ability"),
        attacker_tera=arguments.get("attacker_tera"),
        defender_item=arguments.get("defender_item"),
        defender_ability=arguments.get("defender_ability"),
        defender_tera=arguments.get("defender_tera"),
        weather=arguments.get("weather"),
        terrain=arguments.get("terrain"),
    )


def _get_stored_team(user_id: int, _arguments: dict) -> str:
    # user_id comes from the real Discord interaction (bound by
    # build_tool_dispatch), never from the model's tool-call arguments --
    # the schema takes no parameters at all, so there's nothing for a
    # confused or adversarial prompt to spoof.
    mine = format_team_block(get_team(user_id, "mine"), "Your team")
    opponent = format_team_block(get_team(user_id, "opponent"), "Opponent's team")
    blocks = [block for block in (mine, opponent) if block]
    return "\n\n".join(blocks) if blocks else "No stored team found for this user."


def _get_usage_stats(records: list, usage: Optional[dict], arguments: dict) -> str:
    record = find_record(records, arguments["name"])
    if record is None:
        return f"No Pokemon named '{arguments['name']}' found."
    stats = usage_for_record(usage, record)
    if stats is None:
        return f"No usage data available for {record['name']}."
    return json.dumps(stats)


def build_tool_dispatch(
    records: list, moves: list, items: list, usage: Optional[dict], user_id: int
) -> dict[str, Callable[[dict], str]]:
    """Binds each tool's implementation to the real request context so the
    model's tool-call arguments never carry anything security-sensitive --
    only Pokemon/move names and calc overrides, all safe to take from the
    model."""
    return {
        "run_damage_calc": lambda arguments: _run_damage_calc(records, moves, items, arguments),
        "get_stored_team": lambda arguments: _get_stored_team(user_id, arguments),
        "get_usage_stats": lambda arguments: _get_usage_stats(records, usage, arguments),
    }


async def analyze_response_async(
    answerer,
    question: str,
    records: list,
    moves: list,
    items: list,
    usage: Optional[dict],
    user_id: int,
    index=None,
    bm25_index=None,
) -> str:
    """Runs the agentic tool-calling loop, then falls back to a plain RAG
    /ask-style answer if the model's tool call was malformed or
    hallucinated. `answerer` must support answer_with_tools (pass
    raw_answerer, not a CircuitBreaker-wrapped one -- CircuitBreaker only
    implements .answer())."""
    tool_dispatch = build_tool_dispatch(records, moves, items, usage, user_id)
    answer = answerer.answer_with_tools(question, TOOLS, tool_dispatch)

    if answer == MALFORMED_TOOL_CALL_MESSAGE:
        result = await ask_response_async(
            index, answerer, question, records=records, items=items, bm25_index=bm25_index
        )
        return result["answer"]

    return answer
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_bot_agentic.py -v`
Expected: all pass

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest -q`
Expected: all tests pass, no regressions.

- [ ] **Step 6: Commit**

```bash
git add bot/agentic.py tests/test_bot_agentic.py
git commit -m "feat: add bot/agentic.py with tool schemas, dispatch, and orchestration" -m "$(printf 'Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>')"
```

---

### Task 3: Wire `/analyze` into `bot/main.py`

**Files:**
- Modify: `bot/main.py`
- Test: `tests/test_bot_main.py`

**Interfaces:**
- Consumes: Task 2's `bot.agentic.analyze_response_async`.
- Produces: the `/analyze` Discord command, registered on the tree returned by `build_client`. No other task depends on this.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_bot_main.py`, near the other `/ask`-adjacent tests, reusing the `_extract_text` helper already defined at the top of the file:

```python
def test_analyze_command_is_registered_on_the_tree():
    _client, tree = build_client()
    commands = {command.name: command for command in tree.get_commands()}

    assert "analyze" in commands
    assert "question" in commands["analyze"].description.lower()


def test_analyze_command_defers_and_sends_the_result(monkeypatch):
    captured = {}

    async def _fake_analyze_response_async(answerer, question, records, moves, items, usage, user_id, index=None, bm25_index=None):
        captured["question"] = question
        captured["user_id"] = user_id
        return "the analysis result"

    monkeypatch.setattr("bot.main.analyze_response_async", _fake_analyze_response_async)

    _client, tree = build_client()
    analyze_command = tree.get_command("analyze")
    interaction = MagicMock()
    interaction.user.id = 777
    interaction.response.defer = AsyncMock()
    interaction.followup.send = AsyncMock()

    asyncio.run(analyze_command.callback(interaction, question="Is Incineroar a good check to this team?"))

    interaction.response.defer.assert_awaited_once()
    assert captured["question"] == "Is Incineroar a good check to this team?"
    assert captured["user_id"] == 777
    sent_text = _extract_text(interaction.followup.send)
    assert sent_text == "the analysis result"


def test_analyze_command_uses_raw_answerer_not_the_circuit_breaker(monkeypatch):
    # CircuitBreaker only implements .answer(), not .answer_with_tools() --
    # /analyze must be wired to raw_answerer, same as /llmstatus already is.
    class _FakeBreaker:
        def answer(self, question, context_block):
            raise AssertionError("CircuitBreaker.answer() should never be called by /analyze")

    class _FakeRawAnswerer:
        def answer_with_tools(self, question, tools, tool_dispatch, max_rounds=4):
            return "raw answerer was used correctly"

        def answer(self, question, context_block):
            return "raw answerer was used correctly"

    _client, tree = build_client(answerer=_FakeBreaker(), raw_answerer=_FakeRawAnswerer())
    analyze_command = tree.get_command("analyze")
    interaction = MagicMock()
    interaction.user.id = 1
    interaction.response.defer = AsyncMock()
    interaction.followup.send = AsyncMock()

    asyncio.run(analyze_command.callback(interaction, question="q?"))

    sent_text = _extract_text(interaction.followup.send)
    assert sent_text == "raw answerer was used correctly"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_bot_main.py -v -k analyze`
Expected: FAIL — `test_analyze_command_is_registered_on_the_tree` fails because there's no `/analyze` command yet; the other two fail with `AttributeError`/`KeyError` for the same reason.

- [ ] **Step 3: Wire the command**

In `bot/main.py`, add the import near the other `bot.commands.*` imports:

```python
from bot.agentic import analyze_response_async
```

Add `"analyze"` to `_COMMAND_COLORS` (any unused `discord.Color`, e.g. `discord.Color.dark_teal()`):

```python
_COMMAND_COLORS = {
    ...
    "stats-summary": discord.Color.dark_grey(),
    "analyze": discord.Color.dark_teal(),
}
```

Add the command after the existing `/calc` command's registration (`build_client`'s function body, before `@client.event async def on_ready`):

```python
    @tree.command(
        name="analyze",
        description="Ask an open-ended VGC question that may need the damage calculator, stored teams, or usage stats.",
    )
    @app_commands.checks.cooldown(1, _COOLDOWN_SECONDS)
    async def analyze(interaction: discord.Interaction, question: str) -> None:
        await interaction.response.defer()
        answer = await analyze_response_async(
            raw_answerer, question, records, moves, items, usage, interaction.user.id,
            index=index, bm25_index=bm25_index,
        )
        await interaction.followup.send(embed=_embed("analyze", answer))
```

`records`, `moves`, `items`, `usage`, `index`, `bm25_index`, and `raw_answerer` are all already parameters/closures of `build_client` (used by `/ask`, `/calc`, `/stats`, etc.) — no new plumbing needed.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_bot_main.py -v -k analyze`
Expected: all pass

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest -q`
Expected: all tests pass, no regressions anywhere else in the suite.

- [ ] **Step 6: Commit**

```bash
git add bot/main.py tests/test_bot_main.py
git commit -m "feat: wire /analyze command into the bot" -m "$(printf 'Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>')"
```

---

### Task 4: Update `IMPROVEMENTS.md`

**Files:**
- Modify: `IMPROVEMENTS.md`

- [ ] **Step 1: Mark the item done**

In `IMPROVEMENTS.md`'s "Agentic `/ask`+`/calc` tool-calling loop" bullet (currently reading "architectural spec written and committed... Not yet implemented"), replace it with an "implemented" note in the style of the neighboring done items: what was built (`OllamaAnswerer.answer_with_tools`, `bot/agentic.py`'s three tool schemas + dispatch + orchestration, the `/analyze` command, the malformed-tool-call fallback to plain RAG, the round-trip cap), and the final test count from `python -m pytest -q`.

- [ ] **Step 2: Commit**

```bash
git add IMPROVEMENTS.md
git commit -m "docs: mark agentic tool-calling loop done in the improvement backlog" -m "$(printf 'Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>')"
```
