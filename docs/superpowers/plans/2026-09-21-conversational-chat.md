# Conversational Chat Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let people talk to the bot in plain messages (no slash command) in admin-designated Discord channels, reusing `/analyze`'s existing tool-calling loop, extended with a short rolling per-channel conversation history so natural follow-ups work.

**Architecture:** A new `bot/conversation.py` module holds a pure, in-memory `ConversationHistory` (per-channel rolling buffer, capped, not persisted) and a `should_respond(message, conversation_channel_ids)` routing guard. `OllamaAnswerer.answer_with_tools` (`rag/answer.py`) and `analyze_response_async` (`bot/agentic.py`) each gain an optional `history` parameter, threaded straight through — fully backward-compatible, default `None` reproduces today's exact behavior. `bot/main.py` gets a new `on_message` listener (requires `intents.message_content = True`) that, in channels listed in a new `CONVERSATION_CHANNEL_IDS` env var, shows a typing indicator, calls the extended `analyze_response_async` with that channel's history, replies in-channel, and updates the history — guarded by a simple one-response-in-flight-per-channel lock.

**Tech Stack:** `discord.py`'s `on_message` event + privileged Message Content Intent (already enabled in the Discord Developer Portal), stdlib `collections.deque` for the history buffer. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-09-21-conversational-chat-design.md`

## Global Constraints

- Slash commands are untouched — `/analyze`, `/ask`, `/calc`, etc. keep working exactly as today, everywhere. Conversational mode is additive, opt-in via `CONVERSATION_CHANNEL_IDS`.
- Trigger: every message in a designated channel, not @mention/reply/DM. Feature is entirely off (listener is a no-op) if `CONVERSATION_CHANNEL_IDS` is unset.
- No new tools — reuse the exact three `/analyze` already has (damage calc, stored team, usage stats) via the existing tool-calling-with-RAG-fallback path.
- History: per-channel, in-memory only, capped at the last 3 exchanges (6 messages: 3 user + 3 assistant). Not persisted across a bot restart. Shared across whoever's talking in that channel — no per-user isolation (accepted limitation, see spec).
- A degraded (`OFFLINE_MESSAGE`) or malformed-tool-call (`MALFORMED_TOOL_CALL_MESSAGE`) answer is replied to the user but never appended to history.
- One response in flight per channel at a time — a message arriving while a response is still generating for that channel is silently dropped, not queued or erred.
- Author is a bot (including this bot itself): ignored before any other check, to prevent response loops.
- Reply style: plain `message.reply(answer)`, no embed — conversational messages should read like chat, not a command-result card.

---

## File Structure

- Create: `bot/conversation.py` — `ConversationHistory`, `HISTORY_CAP_MESSAGES`, `should_respond(...)`.
- Create: `tests/test_bot_conversation.py` — unit tests for both.
- Modify: `rag/answer.py` — `OllamaAnswerer.answer_with_tools` gains `history: Optional[list] = None`.
- Modify: `tests/test_rag_answer.py` — tests for the new `history` param.
- Modify: `bot/agentic.py` — `analyze_response_async` gains a matching `history` param, threaded through.
- Modify: `tests/test_bot_agentic.py` — tests for the new param, plus update `_FakeAnswerer.answer_with_tools`'s signature so existing tests keep passing.
- Modify: `bot/main.py` — `intents.message_content = True`, new `on_message` listener inside `build_client`, `CONVERSATION_CHANNEL_IDS` env var parsed once.
- Modify: `tests/test_bot_main.py` — handler-level tests for `on_message`.
- Modify: `.env.example` — document `CONVERSATION_CHANNEL_IDS`.
- Modify: `docs/DEPLOYMENT.md` — brief pointer to the new env var and the Message Content Intent prerequisite (already enabled manually; document it so a future redeploy doesn't miss it).
- Modify: `STATUS.md` / `IMPROVEMENTS.md` — mark the feature done once merged.

---

### Task 1: `bot/conversation.py` — history buffer and routing guard

**Files:**
- Create: `bot/conversation.py`
- Test: `tests/test_bot_conversation.py`

**Interfaces:**
- Consumes: nothing — pure Python, stdlib only.
- Produces: `ConversationHistory` class with `.append(channel_id: int, role: str, content: str) -> None` and `.get(channel_id: int) -> list[dict]` (each dict shaped `{"role": str, "content": str}`); module constant `HISTORY_CAP_MESSAGES = 6`; `should_respond(message, conversation_channel_ids: set[int]) -> bool`. Both are consumed by Task 4's `bot/main.py`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_bot_conversation.py`:

```python
from bot.conversation import ConversationHistory, should_respond


def test_conversation_history_returns_empty_list_for_an_unseen_channel():
    history = ConversationHistory()

    assert history.get(12345) == []


def test_conversation_history_returns_appended_turns_in_order():
    history = ConversationHistory()

    history.append(1, "user", "hello")
    history.append(1, "assistant", "hi there")

    assert history.get(1) == [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi there"},
    ]


def test_conversation_history_trims_to_the_cap():
    history = ConversationHistory(cap=4)

    for i in range(6):
        history.append(1, "user", f"message {i}")

    result = history.get(1)
    assert len(result) == 4
    # oldest entries dropped, newest kept
    assert result[0]["content"] == "message 2"
    assert result[-1]["content"] == "message 5"


def test_conversation_history_isolates_channels():
    history = ConversationHistory()

    history.append(1, "user", "channel one message")
    history.append(2, "user", "channel two message")

    assert history.get(1) == [{"role": "user", "content": "channel one message"}]
    assert history.get(2) == [{"role": "user", "content": "channel two message"}]


class _FakeAuthor:
    def __init__(self, bot: bool):
        self.bot = bot


class _FakeChannel:
    def __init__(self, channel_id: int):
        self.id = channel_id


class _FakeMessage:
    def __init__(self, channel_id: int, is_bot: bool):
        self.channel = _FakeChannel(channel_id)
        self.author = _FakeAuthor(bot=is_bot)


def test_should_respond_true_for_a_human_author_in_a_designated_channel():
    message = _FakeMessage(channel_id=100, is_bot=False)

    assert should_respond(message, conversation_channel_ids={100, 200}) is True


def test_should_respond_false_for_a_channel_not_in_the_allowlist():
    message = _FakeMessage(channel_id=999, is_bot=False)

    assert should_respond(message, conversation_channel_ids={100, 200}) is False


def test_should_respond_false_for_a_bot_author_even_in_a_designated_channel():
    message = _FakeMessage(channel_id=100, is_bot=True)

    assert should_respond(message, conversation_channel_ids={100, 200}) is False


def test_should_respond_false_when_the_allowlist_is_empty():
    message = _FakeMessage(channel_id=100, is_bot=False)

    assert should_respond(message, conversation_channel_ids=set()) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_bot_conversation.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bot.conversation'`

- [ ] **Step 3: Write the implementation**

Create `bot/conversation.py`:

```python
from collections import deque
from typing import Iterable

# 3 exchanges (user + assistant pairs) -- bounds both memory and the
# tool-calling prompt size. See docs/superpowers/specs/2026-09-21-conversational-chat-design.md.
HISTORY_CAP_MESSAGES = 6


class ConversationHistory:
    """Short-lived, in-memory rolling chat history per Discord channel.
    Not persisted -- a bot restart clears all context, which is
    acceptable for chat-style back-and-forth."""

    def __init__(self, cap: int = HISTORY_CAP_MESSAGES):
        self._cap = cap
        self._history: dict[int, deque] = {}

    def append(self, channel_id: int, role: str, content: str) -> None:
        buffer = self._history.setdefault(channel_id, deque(maxlen=self._cap))
        buffer.append({"role": role, "content": content})

    def get(self, channel_id: int) -> list[dict]:
        return list(self._history.get(channel_id, []))


def should_respond(message, conversation_channel_ids: Iterable[int]) -> bool:
    """True only if the message's channel is in the configured allowlist
    and the author isn't a bot (covers this bot's own messages and any
    other bot in the channel, preventing response loops)."""
    if message.author.bot:
        return False
    return message.channel.id in conversation_channel_ids
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_bot_conversation.py -v`
Expected: PASS (9 tests)

- [ ] **Step 5: Commit**

```bash
git add bot/conversation.py tests/test_bot_conversation.py
git commit -m "feat: add ConversationHistory and should_respond for conversational chat"
```

---

### Task 2: `OllamaAnswerer.answer_with_tools` gains an optional `history` param

**Files:**
- Modify: `rag/answer.py`
- Test: `tests/test_rag_answer.py`

**Interfaces:**
- Consumes: nothing new from other tasks.
- Produces: `OllamaAnswerer.answer_with_tools(question: str, tools: list, tool_dispatch: dict, max_rounds: int = 4, history: Optional[list[dict]] = None) -> str`. Consumed by Task 3's `analyze_response_async`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_rag_answer.py` (reuses `_FakeSequentialOllamaClient`/`_final_response` already defined there from the existing `answer_with_tools` tests):

```python
def test_answer_with_tools_inserts_history_between_the_system_prompt_and_the_new_question():
    client = _FakeSequentialOllamaClient([_final_response("answer")])
    answerer = OllamaAnswerer(host="100.1.2.3:11434", client=client)
    history = [
        {"role": "user", "content": "earlier question"},
        {"role": "assistant", "content": "earlier answer"},
    ]

    answerer.answer_with_tools("new question", tools=[], tool_dispatch={}, history=history)

    sent_messages = client.calls[0]["json"]["messages"]
    assert sent_messages[0]["role"] == "system"
    assert sent_messages[1] == {"role": "user", "content": "earlier question"}
    assert sent_messages[2] == {"role": "assistant", "content": "earlier answer"}
    assert sent_messages[3] == {"role": "user", "content": "new question"}


def test_answer_with_tools_omitting_history_reproduces_todays_exact_message_shape():
    client = _FakeSequentialOllamaClient([_final_response("answer")])
    answerer = OllamaAnswerer(host="100.1.2.3:11434", client=client)

    answerer.answer_with_tools("new question", tools=[], tool_dispatch={})

    sent_messages = client.calls[0]["json"]["messages"]
    assert len(sent_messages) == 2
    assert sent_messages[1] == {"role": "user", "content": "new question"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_rag_answer.py -k history -v`
Expected: FAIL — `test_answer_with_tools_inserts_history...` fails because history is never inserted (only 2 messages sent, not 4); the second test should already pass (documents current behavior as a regression guard) but run both together to confirm the first genuinely fails first.

- [ ] **Step 3: Write the implementation**

In `rag/answer.py`, add `Optional` to the existing `typing` usage (the file currently has no `typing` import at all — add `from typing import Optional` near the top with `import json`/`import requests`), then modify `answer_with_tools`'s signature and message construction:

```python
    def answer_with_tools(
        self, question: str, tools: list, tool_dispatch: dict, max_rounds: int = 4,
        history: Optional[list] = None,
    ) -> str:
```

and replace the existing:

```python
        messages = [
            {"role": "system", "content": TOOLS_SYSTEM_PROMPT},
            {"role": "user", "content": question},
        ]
```

with:

```python
        messages = [{"role": "system", "content": TOOLS_SYSTEM_PROMPT}]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": question})
```

Also update the docstring to mention the new parameter: add a line like `history, if given, is a list of prior {"role", "content"} turns inserted between the system prompt and the new question -- used by conversational chat to carry short-term context across messages in the same channel.`

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_rag_answer.py -v`
Expected: PASS (all existing `answer_with_tools` tests plus the 2 new ones — confirms no regression to the existing tool-calling tests)

- [ ] **Step 5: Commit**

```bash
git add rag/answer.py tests/test_rag_answer.py
git commit -m "feat: add optional history param to OllamaAnswerer.answer_with_tools"
```

---

### Task 3: `analyze_response_async` gains a matching `history` param

**Files:**
- Modify: `bot/agentic.py`
- Test: `tests/test_bot_agentic.py`

**Interfaces:**
- Consumes: Task 2's `answer_with_tools(..., history=...)`.
- Produces: `analyze_response_async(answerer, question, records, moves, items, usage, user_id, index=None, bm25_index=None, history: Optional[list] = None) -> str`. Consumed by Task 4's `bot/main.py` `on_message` listener (and unchanged by the existing `/analyze` slash command, which continues to call it with no `history` argument).

- [ ] **Step 1: Update the existing fake and write the failing test**

`tests/test_bot_agentic.py`'s existing `_FakeAnswerer.answer_with_tools(self, question, tools, tool_dispatch, max_rounds=4)` (around line 103) does not accept a `history` kwarg. Once Task 3's implementation passes `history=history` through to it, every existing test using `_FakeAnswerer` would break with `TypeError: answer_with_tools() got an unexpected keyword argument 'history'` unless this fake is updated first. Update it:

```python
class _FakeAnswerer:
    def __init__(self, tool_result):
        self._tool_result = tool_result

    def answer_with_tools(self, question, tools, tool_dispatch, max_rounds=4, history=None):
        self.last_history = history
        return self._tool_result

    def answer(self, question, context_block):
        return "plain RAG fallback answer"
```

(adding `self.last_history = history` so the new test below can assert on it.)

Then add a new test:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_bot_agentic.py -v`
Expected: the two new tests FAIL with `AttributeError: 'analyze_response_async' object has no attribute...` or simply wrong assertion (since `analyze_response_async` doesn't accept/forward `history` yet) — all pre-existing tests in this file should still PASS at this point (the fake update alone is backward-compatible).

- [ ] **Step 3: Write the implementation**

In `bot/agentic.py`, modify `analyze_response_async`'s signature and its call to `answer_with_tools`:

```python
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
    history: Optional[list] = None,
) -> str:
    """Runs the agentic tool-calling loop, then falls back to a plain RAG
    /ask-style answer if the model's tool call was malformed or
    hallucinated. `answerer` must support answer_with_tools (pass
    raw_answerer, not a CircuitBreaker-wrapped one -- CircuitBreaker only
    implements .answer()). `history`, if given, is a list of prior
    {"role", "content"} turns from the same conversation (used by
    conversational chat; the /analyze slash command omits it -- each call
    is single-turn)."""
    tool_dispatch = build_tool_dispatch(records, moves, items, usage, user_id)
    answer = answerer.answer_with_tools(question, TOOLS, tool_dispatch, history=history)

    if answer == MALFORMED_TOOL_CALL_MESSAGE:
        result = await ask_response_async(
            index, answerer, question, records=records, items=items, bm25_index=bm25_index
        )
        return result["answer"]

    return answer
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_bot_agentic.py -v`
Expected: PASS (all tests, including the two new ones)

- [ ] **Step 5: Run the full suite to confirm no regression in `/analyze`'s own tests**

Run: `.venv/bin/python -m pytest tests/test_bot_main.py -k analyze -v`
Expected: PASS (the `/analyze` slash-command tests in `tests/test_bot_main.py` don't pass `history` at all, exercising the default-`None` path end to end)

- [ ] **Step 6: Commit**

```bash
git add bot/agentic.py tests/test_bot_agentic.py
git commit -m "feat: thread optional history through analyze_response_async"
```

---

### Task 4: Wire the `on_message` listener into `bot/main.py`

**Files:**
- Modify: `bot/main.py`
- Modify: `tests/test_bot_main.py`
- Modify: `.env.example`
- Modify: `docs/DEPLOYMENT.md`

**Interfaces:**
- Consumes: Task 1's `ConversationHistory`/`should_respond`, Task 3's `analyze_response_async(..., history=...)`.
- Produces: a working `on_message` event handler registered on the `client` returned by `build_client(...)`, reachable in tests as `client.on_message` (an `@client.event`-decorated coroutine, same mechanism `on_ready`/`on_tree_error` already use — callable directly as `asyncio.run(client.on_message(fake_message))`).

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_bot_main.py`:

```python
class _FakeAuthor:
    def __init__(self, user_id: int, is_bot: bool = False):
        self.id = user_id
        self.bot = is_bot


class _FakeTypingContext:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False


class _FakeChannel:
    def __init__(self, channel_id: int):
        self.id = channel_id

    def typing(self):
        return _FakeTypingContext()


class _FakeConversationMessage:
    def __init__(self, channel_id: int, content: str, user_id: int = 1, is_bot: bool = False):
        self.channel = _FakeChannel(channel_id)
        self.author = _FakeAuthor(user_id, is_bot=is_bot)
        self.content = content
        self.reply = AsyncMock()


def test_on_message_ignores_channels_outside_the_conversation_allowlist(monkeypatch):
    monkeypatch.delenv("CONVERSATION_CHANNEL_IDS", raising=False)
    _client, _tree = build_client()
    # No CONVERSATION_CHANNEL_IDS set -- allowlist is empty, listener is a no-op.
    message = _FakeConversationMessage(channel_id=100, content="hello")

    asyncio.run(_client.on_message(message))

    message.reply.assert_not_called()


def test_on_message_ignores_messages_from_bots(monkeypatch):
    monkeypatch.setenv("CONVERSATION_CHANNEL_IDS", "100")
    _client, _tree = build_client()
    message = _FakeConversationMessage(channel_id=100, content="hello", is_bot=True)

    asyncio.run(_client.on_message(message))

    message.reply.assert_not_called()


def test_on_message_replies_in_a_designated_channel(monkeypatch):
    monkeypatch.setenv("CONVERSATION_CHANNEL_IDS", "100")

    async def _fake_analyze_response_async(*args, **kwargs):
        return "a conversational answer"

    monkeypatch.setattr("bot.main.analyze_response_async", _fake_analyze_response_async)
    _client, _tree = build_client()
    message = _FakeConversationMessage(channel_id=100, content="hello")

    asyncio.run(_client.on_message(message))

    message.reply.assert_awaited_once_with("a conversational answer")


def test_on_message_passes_and_updates_channel_history(monkeypatch):
    monkeypatch.setenv("CONVERSATION_CHANNEL_IDS", "100")
    captured = {}

    async def _fake_analyze_response_async(answerer, question, records, moves, items, usage, user_id, index=None, bm25_index=None, history=None):
        captured["history_seen"] = history
        return "second answer"

    monkeypatch.setattr("bot.main.analyze_response_async", _fake_analyze_response_async)
    _client, _tree = build_client()

    first_message = _FakeConversationMessage(channel_id=100, content="first question")
    asyncio.run(_client.on_message(first_message))
    second_message = _FakeConversationMessage(channel_id=100, content="second question")
    asyncio.run(_client.on_message(second_message))

    # The first call had no prior history; the second call should have
    # seen the first exchange.
    assert captured["history_seen"] == [
        {"role": "user", "content": "first question"},
        {"role": "assistant", "content": "second answer"},
    ]


def test_on_message_does_not_record_offline_message_into_history(monkeypatch):
    monkeypatch.setenv("CONVERSATION_CHANNEL_IDS", "100")

    async def _fake_analyze_response_async(*args, **kwargs):
        return rag.answer.OFFLINE_MESSAGE

    monkeypatch.setattr("bot.main.analyze_response_async", _fake_analyze_response_async)
    _client, _tree = build_client()

    asyncio.run(_client.on_message(_FakeConversationMessage(channel_id=100, content="q")))

    # A second message should see no history from the degraded first turn.
    captured = {}

    async def _capture_history(answerer, question, records, moves, items, usage, user_id, index=None, bm25_index=None, history=None):
        captured["history_seen"] = history
        return "a real answer"

    monkeypatch.setattr("bot.main.analyze_response_async", _capture_history)
    asyncio.run(_client.on_message(_FakeConversationMessage(channel_id=100, content="q2")))

    assert captured["history_seen"] == []


def test_on_message_drops_a_second_message_while_one_is_in_flight(monkeypatch):
    monkeypatch.setenv("CONVERSATION_CHANNEL_IDS", "100")
    started = asyncio.Event()
    finish = asyncio.Event()

    async def _slow_analyze_response_async(*args, **kwargs):
        started.set()
        await finish.wait()
        return "slow answer"

    monkeypatch.setattr("bot.main.analyze_response_async", _slow_analyze_response_async)
    _client, _tree = build_client()

    async def _scenario():
        first_message = _FakeConversationMessage(channel_id=100, content="first")
        first_task = asyncio.ensure_future(_client.on_message(first_message))
        await started.wait()

        second_message = _FakeConversationMessage(channel_id=100, content="second, while first is in flight")
        await _client.on_message(second_message)
        second_message.reply.assert_not_called()

        finish.set()
        await first_task
        first_message.reply.assert_awaited_once_with("slow answer")

    asyncio.run(_scenario())
```

Add `import rag.answer` near the top of `tests/test_bot_main.py` if not already imported (check first — `rag.answer` is already imported per line 6 of the existing file, so this may already be available).

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_bot_main.py -k on_message -v`
Expected: FAIL with `AttributeError: 'Client' object has no attribute 'on_message'` (no listener registered yet)

- [ ] **Step 3: Write the implementation**

In `bot/main.py`:

1. Add `MALFORMED_TOOL_CALL_MESSAGE` to the existing `rag.answer` import (currently `from rag.answer import OFFLINE_MESSAGE, OllamaAnswerer`):

```python
from rag.answer import MALFORMED_TOOL_CALL_MESSAGE, OFFLINE_MESSAGE, OllamaAnswerer
```

2. Add the import for the new module, alongside the other `bot.*` imports:

```python
from bot.conversation import ConversationHistory, should_respond
```

3. In `build_client`, change the intents line:

```python
    intents = discord.Intents.default()
    intents.message_content = True
```

4. Still in `build_client`, after `tree = app_commands.CommandTree(client)` (or anywhere before the `on_message` handler below — placement relative to the `@tree.command(...)` definitions doesn't matter), add:

```python
    conversation_channel_ids = {
        int(channel_id) for channel_id in os.environ.get("CONVERSATION_CHANNEL_IDS", "").split(",")
        if channel_id.strip()
    }
    conversation_history = ConversationHistory()
    conversation_locks: dict[int, bool] = {}
```

5. Add the listener itself. Place it right after the existing `on_ready` handler (around where `@client.event async def on_ready(...)` is defined):

```python
    @client.event
    async def on_message(message: discord.Message) -> None:
        if not should_respond(message, conversation_channel_ids):
            return
        if conversation_locks.get(message.channel.id):
            return
        conversation_locks[message.channel.id] = True
        try:
            async with message.channel.typing():
                history = conversation_history.get(message.channel.id)
                answer = await analyze_response_async(
                    raw_answerer, message.content, records, moves, items, usage,
                    message.author.id, index=index, bm25_index=bm25_index,
                    history=history,
                )
            await message.reply(answer)
            if answer not in (OFFLINE_MESSAGE, MALFORMED_TOOL_CALL_MESSAGE):
                conversation_history.append(message.channel.id, "user", message.content)
                conversation_history.append(message.channel.id, "assistant", answer)
        finally:
            conversation_locks[message.channel.id] = False
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_bot_main.py -k on_message -v`
Expected: PASS (all 6 new tests)

- [ ] **Step 5: Run the full test suite**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS, all tests (confirms nothing else broke — in particular that enabling `intents.message_content` doesn't change any existing slash-command test, since those don't go through `on_message` at all)

- [ ] **Step 6: Document the new env var**

Append to `.env.example`, after the existing `BOT_OWNER_ID=` block:

```bash

# Comma-separated Discord channel IDs where plain messages (no slash
# command) are treated as directed at the bot -- answered via the same
# tool-calling loop /analyze uses, with a short rolling per-channel
# memory for natural follow-ups. Find a channel's ID: Discord Settings ->
# Advanced -> enable Developer Mode, then right-click the channel ->
# Copy Channel ID. Requires the "Message Content Intent" privileged
# intent to be enabled for this bot in the Discord Developer Portal
# (Bot -> Privileged Gateway Intents) -- without it, this feature
# silently receives no message content regardless of this setting.
# Optional -- if unset, this feature is entirely off.
CONVERSATION_CHANNEL_IDS=
```

- [ ] **Step 7: Add a deployment note**

In `docs/DEPLOYMENT.md`, add a short paragraph near the end of section 2 (`.env` setup) or as its own numbered note referencing `CONVERSATION_CHANNEL_IDS` and the Message Content Intent prerequisite, pointing to `docs/superpowers/specs/2026-09-21-conversational-chat-design.md` for the full design. Keep it to 3-4 sentences — this is a pointer, not a re-explanation.

- [ ] **Step 8: Commit**

```bash
git add bot/main.py tests/test_bot_main.py .env.example docs/DEPLOYMENT.md
git commit -m "feat: add conversational chat via on_message in designated channels"
```

---

### Task 5: Update tracking docs

**Files:**
- Modify: `STATUS.md`
- Modify: `IMPROVEMENTS.md`

**Interfaces:**
- Consumes: nothing (documentation only).
- Produces: nothing consumed by other tasks — this is the final task.

- [ ] **Step 1: Update `STATUS.md`**

Replace the "In progress: conversational chat..." paragraph in the "What's left" section with a one-line mention under "Shipped features" instead (matching the style of every other shipped-feature bullet in that file), pointing to `docs/superpowers/plans/2026-09-21-conversational-chat.md`. Update the `STATUS_COMMIT` marker to match `git rev-parse --short HEAD` after committing this task, per `CLAUDE.md`'s convention (this may take a follow-up STATUS.md-only commit if the marker bump commit itself needs to trail the content commit — see the pattern already established in this repo's recent commit history if unsure).

- [ ] **Step 2: Update `IMPROVEMENTS.md`**

Add a one-line entry under its "Done" section: conversational chat, pointing to the plan file, mirroring the existing one-line-per-item style already used there.

- [ ] **Step 3: Run the full suite one more time**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS (docs-only changes in this task, but confirm nothing drifted)

- [ ] **Step 4: Commit**

```bash
git add STATUS.md IMPROVEMENTS.md
git commit -m "docs: mark conversational chat done in STATUS.md/IMPROVEMENTS.md"
```

---

## Manual verification (not automated, do after all tasks land)

1. Deploy to the machine running the live bot (`git pull`, restart the service).
2. Set `CONVERSATION_CHANNEL_IDS` in that machine's `.env` to a real test channel's ID, restart again.
3. In that Discord channel, type a plain question (e.g. "What are Aegislash's base stats?") with no slash command. Confirm a reply arrives, unprompted by any command.
4. Ask a natural follow-up in the same channel (e.g. "what about its speed?"). Confirm the reply shows the history actually helped (references the same Pokemon without it being restated).
5. Have a second person (or a second account) send a message in the same channel while the first response is still generating. Confirm it's silently dropped (no reply, no error) rather than erroring or queuing strangely.
6. Turn the local LLM off (`scripts/llm_toggle.sh off`) and send a message in the designated channel. Confirm the existing offline-degradation message appears, same as `/ask` already does when the host is down.
7. Confirm `/analyze`, `/ask`, and all other slash commands still work normally in every channel, designated or not.
