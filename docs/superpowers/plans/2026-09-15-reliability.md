# Reliability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a circuit breaker around `OllamaAnswerer` calls so concurrent `/ask` requests stop paying a full 30-second timeout once the laptop is known to be down, and add an owner-only `/llmstatus` command that reports LLM reachability, the loaded model, and the breaker's current state without waiting on a real question.

**Architecture:** A new `rag/circuit_breaker.py` module holds `CircuitBreaker`, a small state machine (closed/open/half-open) that wraps any object exposing `.answer(question, context_block) -> str` and detects failure by comparing the return value against `rag.answer.OFFLINE_MESSAGE` (the wrapped `OllamaAnswerer` already never raises for a network failure — it catches everything internally and returns that fixed string). `rag/answer.py`'s `OllamaAnswerer` gains a `check_health()` method (a short-timeout `GET /api/tags` liveness probe, separate from the real inference call) and a `model` read-only property. `bot/commands/llmstatus.py` holds a pure `format_llmstatus(...)` formatter, following this project's established pattern (`bot/commands/debug.py`, `bot/commands/ping.py`, etc. hold pure response-building functions; `bot/main.py` wires them into `tree.command` handlers). `bot/main.py`'s `main()` wraps the real `OllamaAnswerer` in a `CircuitBreaker` at construction time (decorator/composition — `OllamaAnswerer` itself doesn't change) and passes both the breaker (as `answerer`, used unchanged by `/ask`) and the raw answerer (as a new `raw_answerer` parameter, used only by `/llmstatus` for its health check and configured-model name) into `build_client`.

**Tech Stack:** Python 3.9, stdlib `time`, existing `requests`-compatible client pattern (no new dependencies).

**Spec:** `docs/superpowers/specs/2026-09-13-reliability-design.md`

## Global Constraints

- No new dependencies.
- The circuit breaker detects failure by return-value comparison against `rag.answer.OFFLINE_MESSAGE`, never by catching an exception — `OllamaAnswerer.answer` never raises for a network/parsing failure, it always returns that fixed string, so an exception-based breaker would see nothing during a real outage.
- Circuit breaker thresholds: 3 consecutive failures to open, 60-second cooldown before a half-open probe — reasonable starting defaults per the spec, not load-tested values.
- The breaker's clock is injectable (`time_func`, defaulting to `time.monotonic`) — tests use a fake clock, never real `sleep()`.
- `/llmstatus` is gated by the same `BOT_OWNER_ID`-checking `_owner_only` predicate already used by `/debug-last` (`bot/main.py`), via `app_commands.check` — this bot uses a bare `discord.Client` + separate `CommandTree`, not `commands.Bot`, so `is_owner()` isn't available.
- `/llmstatus` also carries the same `@app_commands.checks.cooldown(1, _COOLDOWN_SECONDS)` decorator every other command in `bot/main.py` has, for consistency (unlike `/debug-last`, which the spec doesn't require to have one and doesn't currently have one — don't add it there, out of scope for this plan).
- The health-check request uses a short timeout (3 seconds) — deliberately much shorter than `OllamaAnswerer.answer`'s 30-second default, since a slow health-check response IS the "down" signal, not something worth waiting out.
- `OllamaAnswerer` itself keeps its existing interface and internal exception handling exactly as-is; the breaker wraps it from the outside, it does not modify the class.

---

## File structure

- Create `rag/circuit_breaker.py` — `CircuitBreaker` class (states `CLOSED`/`OPEN`/`HALF_OPEN`, a `.answer(question, context_block)` method matching `OllamaAnswerer`'s interface so `/ask`'s code never needs to know it's wrapped, and a `.state` property for `/llmstatus` to read).
- Create `tests/test_rag_circuit_breaker.py` — full state-machine test coverage.
- Modify `rag/answer.py` — add `HEALTH_CHECK_TIMEOUT = 3.0` constant, `OllamaAnswerer.check_health()` method, `OllamaAnswerer.model` read-only property.
- Modify `tests/test_rag_answer.py` — extend `_FakeOllamaClient` with a `.get()` method (mirroring its existing `.post()`), add tests for `check_health()` and the `model` property.
- Create `bot/commands/llmstatus.py` — `format_llmstatus(up, models, configured_model, breaker_state) -> str`, pure formatting logic.
- Create `tests/test_bot_llmstatus.py` — tests for `format_llmstatus`.
- Modify `bot/main.py` — imports `CircuitBreaker` and `format_llmstatus`; `build_client` gains a `raw_answerer=None` parameter; a new `/llmstatus` command is registered; `_COMMAND_COLORS` gains an `"llmstatus"` entry; `main()` wraps `_build_answerer()`'s result in a `CircuitBreaker` and passes both the breaker and the raw answerer into `build_client`.
- Modify `tests/test_bot_main.py` — new tests for `/llmstatus`'s registration (both checks attached), its up/down/breaker-state reporting, and its ephemeral reply.
- Modify `.env.example` — update `BOT_OWNER_ID`'s comment to mention it now also gates `/llmstatus`.

---

### Task 1: `rag/circuit_breaker.py` — circuit breaker state machine

**Files:**
- Create: `rag/circuit_breaker.py`
- Test: `tests/test_rag_circuit_breaker.py`

**Interfaces:**
- Consumes: `rag.answer.OFFLINE_MESSAGE` (already exists).
- Produces: `CircuitBreaker(wrapped, failure_threshold=3, cooldown_seconds=60.0, time_func=time.monotonic)` with `.answer(question: str, context_block: str) -> str` and a read-only `.state` property returning one of the string constants `CLOSED`/`OPEN`/`HALF_OPEN` (also exported from this module). Task 4 constructs `CircuitBreaker(raw_answerer)` in `bot/main.py`'s `main()` and reads `.state` from it inside the `/llmstatus` handler.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_rag_circuit_breaker.py`:

```python
from rag.answer import OFFLINE_MESSAGE
from rag.circuit_breaker import CLOSED, HALF_OPEN, OPEN, CircuitBreaker


class _FakeAnswerer:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = 0

    def answer(self, question, context_block):
        self.calls += 1
        return self._responses.pop(0)


class _FakeClock:
    def __init__(self, start=0.0):
        self._now = start

    def __call__(self):
        return self._now

    def advance(self, seconds):
        self._now += seconds


def test_breaker_starts_closed():
    breaker = CircuitBreaker(_FakeAnswerer(["anything"]))

    assert breaker.state == CLOSED


def test_breaker_opens_after_three_consecutive_failures():
    wrapped = _FakeAnswerer([OFFLINE_MESSAGE, OFFLINE_MESSAGE, OFFLINE_MESSAGE])
    breaker = CircuitBreaker(wrapped, failure_threshold=3)

    breaker.answer("q", "c")
    breaker.answer("q", "c")
    assert breaker.state == CLOSED
    breaker.answer("q", "c")

    assert breaker.state == OPEN


def test_breaker_open_short_circuits_without_calling_the_wrapped_function():
    wrapped = _FakeAnswerer([OFFLINE_MESSAGE, OFFLINE_MESSAGE, OFFLINE_MESSAGE])
    breaker = CircuitBreaker(wrapped, failure_threshold=3)
    for _ in range(3):
        breaker.answer("q", "c")
    assert breaker.state == OPEN

    result = breaker.answer("q", "c")

    assert result == OFFLINE_MESSAGE
    assert wrapped.calls == 3  # the short-circuited call never reached the wrapped function


def test_breaker_a_success_before_the_threshold_resets_the_failure_count():
    wrapped = _FakeAnswerer(
        [OFFLINE_MESSAGE, OFFLINE_MESSAGE, "a real answer", OFFLINE_MESSAGE, OFFLINE_MESSAGE]
    )
    breaker = CircuitBreaker(wrapped, failure_threshold=3)

    breaker.answer("q", "c")
    breaker.answer("q", "c")
    breaker.answer("q", "c")  # success resets the counter
    breaker.answer("q", "c")
    breaker.answer("q", "c")

    assert breaker.state == CLOSED  # only 2 consecutive failures since the reset


def test_breaker_treats_any_non_offline_string_as_success_even_if_it_looks_failure_like():
    wrapped = _FakeAnswerer(["error: something failed", OFFLINE_MESSAGE, OFFLINE_MESSAGE])
    breaker = CircuitBreaker(wrapped, failure_threshold=2)

    breaker.answer("q", "c")  # looks like a failure string, but isn't OFFLINE_MESSAGE -- success
    breaker.answer("q", "c")
    breaker.answer("q", "c")

    assert breaker.state == OPEN  # opened by the 2 real OFFLINE_MESSAGE failures, not 3


def test_breaker_transitions_to_half_open_after_the_cooldown_elapses():
    clock = _FakeClock()
    wrapped = _FakeAnswerer([OFFLINE_MESSAGE, OFFLINE_MESSAGE, OFFLINE_MESSAGE])
    breaker = CircuitBreaker(wrapped, failure_threshold=3, cooldown_seconds=60.0, time_func=clock)
    for _ in range(3):
        breaker.answer("q", "c")
    assert breaker.state == OPEN

    clock.advance(59.0)
    assert breaker.state == OPEN

    clock.advance(1.0)
    assert breaker.state == HALF_OPEN


def test_breaker_half_open_success_closes_the_breaker():
    clock = _FakeClock()
    wrapped = _FakeAnswerer([OFFLINE_MESSAGE, OFFLINE_MESSAGE, OFFLINE_MESSAGE, "back online"])
    breaker = CircuitBreaker(wrapped, failure_threshold=3, cooldown_seconds=60.0, time_func=clock)
    for _ in range(3):
        breaker.answer("q", "c")
    clock.advance(60.0)
    assert breaker.state == HALF_OPEN

    result = breaker.answer("q", "c")

    assert result == "back online"
    assert breaker.state == CLOSED
    assert wrapped.calls == 4  # the half-open probe actually called through to the wrapped function


def test_breaker_half_open_failure_reopens_the_breaker_for_another_cooldown():
    clock = _FakeClock()
    wrapped = _FakeAnswerer([OFFLINE_MESSAGE, OFFLINE_MESSAGE, OFFLINE_MESSAGE, OFFLINE_MESSAGE])
    breaker = CircuitBreaker(wrapped, failure_threshold=3, cooldown_seconds=60.0, time_func=clock)
    for _ in range(3):
        breaker.answer("q", "c")
    clock.advance(60.0)
    assert breaker.state == HALF_OPEN

    result = breaker.answer("q", "c")

    assert result == OFFLINE_MESSAGE
    assert breaker.state == OPEN  # reopened, not stuck at half-open
    assert wrapped.calls == 4  # the probe call did go through

    # The new cooldown restarts from this reopen, not the original one.
    clock.advance(59.0)
    assert breaker.state == OPEN
    clock.advance(1.0)
    assert breaker.state == HALF_OPEN
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_rag_circuit_breaker.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'rag.circuit_breaker'`.

- [ ] **Step 3: Implement `rag/circuit_breaker.py`**

```python
import time
from typing import Callable

from rag.answer import OFFLINE_MESSAGE

CLOSED = "closed"
OPEN = "open"
HALF_OPEN = "half_open"


class CircuitBreaker:
    """Wraps an answerer-like object (anything with .answer(question,
    context_block) -> str) and short-circuits calls after repeated
    failures, so concurrent /ask requests stop each paying a full network
    timeout once the LLM host is known to be down.

    Detects failure by return value, not exception: OllamaAnswerer.answer
    already catches every network/parsing failure internally and returns
    the fixed OFFLINE_MESSAGE string rather than raising, so this breaker
    treats "result == OFFLINE_MESSAGE" as the failure signal.
    """

    def __init__(
        self,
        wrapped,
        failure_threshold: int = 3,
        cooldown_seconds: float = 60.0,
        time_func: Callable[[], float] = time.monotonic,
    ):
        self._wrapped = wrapped
        self._failure_threshold = failure_threshold
        self._cooldown_seconds = cooldown_seconds
        self._time_func = time_func
        self._state = CLOSED
        self._failure_count = 0
        self._opened_at = None

    @property
    def state(self) -> str:
        if self._state == OPEN and self._time_func() - self._opened_at >= self._cooldown_seconds:
            return HALF_OPEN
        return self._state

    def answer(self, question: str, context_block: str) -> str:
        effective_state = self.state
        if effective_state == OPEN:
            return OFFLINE_MESSAGE

        result = self._wrapped.answer(question, context_block)

        if result == OFFLINE_MESSAGE:
            if effective_state == HALF_OPEN:
                self._state = OPEN
                self._opened_at = self._time_func()
            else:
                self._failure_count += 1
                if self._failure_count >= self._failure_threshold:
                    self._state = OPEN
                    self._opened_at = self._time_func()
        else:
            self._state = CLOSED
            self._failure_count = 0

        return result
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_rag_circuit_breaker.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add rag/circuit_breaker.py tests/test_rag_circuit_breaker.py
git commit -m "feat: add circuit breaker for OllamaAnswerer calls"
```

---

### Task 2: `rag/answer.py` — health-check method and model property

**Files:**
- Modify: `rag/answer.py` (full file)
- Modify: `tests/test_rag_answer.py` (extend `_FakeOllamaClient`, add new tests)

**Interfaces:**
- Consumes: nothing new.
- Produces: `OllamaAnswerer.check_health() -> dict` returning `{"up": bool, "models": list[str]}` (empty list when down), and a read-only `OllamaAnswerer.model -> str` property. Task 4's `/llmstatus` handler calls both on the raw (non-breaker-wrapped) `OllamaAnswerer` instance.

- [ ] **Step 1: Write the failing tests**

In `tests/test_rag_answer.py`, find the `_FakeOllamaClient` class:

```python
class _FakeOllamaClient:
    def __init__(self, response_json=None, exception=None, status_code=200):
        self._response_json = response_json
        self._exception = exception
        self._status_code = status_code
        self.calls = []

    def post(self, url, json=None, timeout=None):
        self.calls.append({"url": url, "json": json, "timeout": timeout})
        if self._exception:
            raise self._exception
        return _FakeOllamaResponse(self._response_json, status_code=self._status_code)
```

Replace it with (adds a `.get()` method for the health-check request, mirroring `.post()`):

```python
class _FakeOllamaClient:
    def __init__(self, response_json=None, exception=None, status_code=200):
        self._response_json = response_json
        self._exception = exception
        self._status_code = status_code
        self.calls = []

    def post(self, url, json=None, timeout=None):
        self.calls.append({"url": url, "json": json, "timeout": timeout})
        if self._exception:
            raise self._exception
        return _FakeOllamaResponse(self._response_json, status_code=self._status_code)

    def get(self, url, timeout=None):
        self.calls.append({"url": url, "timeout": timeout})
        if self._exception:
            raise self._exception
        return _FakeOllamaResponse(self._response_json, status_code=self._status_code)
```

Then append these tests to the end of the file:

```python
def test_ollama_check_health_reports_up_and_lists_loaded_models():
    client = _FakeOllamaClient(
        response_json={"models": [{"name": "llama3.2:3b"}, {"name": "nomic-embed-text"}]}
    )
    answerer = OllamaAnswerer(host="100.1.2.3:11434", client=client)

    result = answerer.check_health()

    assert result == {"up": True, "models": ["llama3.2:3b", "nomic-embed-text"]}


def test_ollama_check_health_hits_the_tags_endpoint_with_a_short_timeout():
    client = _FakeOllamaClient(response_json={"models": []})
    answerer = OllamaAnswerer(host="100.1.2.3:11434", client=client)

    answerer.check_health()

    call = client.calls[0]
    assert call["url"] == "http://100.1.2.3:11434/api/tags"
    assert call["timeout"] == 3.0


def test_ollama_check_health_reports_down_on_connection_error():
    client = _FakeOllamaClient(exception=requests.exceptions.ConnectionError("refused"))
    answerer = OllamaAnswerer(host="100.1.2.3:11434", client=client)

    result = answerer.check_health()

    assert result == {"up": False, "models": []}


def test_ollama_check_health_reports_down_on_timeout():
    client = _FakeOllamaClient(exception=requests.exceptions.Timeout("slow"))
    answerer = OllamaAnswerer(host="100.1.2.3:11434", client=client)

    result = answerer.check_health()

    assert result == {"up": False, "models": []}


def test_ollama_check_health_reports_down_on_malformed_response():
    client = _FakeOllamaClient(response_json={"unexpected": "shape"})
    answerer = OllamaAnswerer(host="100.1.2.3:11434", client=client)

    result = answerer.check_health()

    assert result == {"up": False, "models": []}


def test_ollama_answerer_exposes_its_configured_model():
    answerer = OllamaAnswerer(host="100.1.2.3:11434", model="phi3:mini")

    assert answerer.model == "phi3:mini"
```

- [ ] **Step 2: Run the tests to verify the new ones fail**

Run: `pytest tests/test_rag_answer.py -v`
Expected: the 6 new tests FAIL — `check_health`/`model` tests with `AttributeError: 'OllamaAnswerer' object has no attribute 'check_health'` (and similarly for `model`); all pre-existing tests still PASS (the `_FakeOllamaClient` edit only adds a method, it doesn't change `.post()`'s behavior).

- [ ] **Step 3: Implement the changes to `rag/answer.py`**

Replace the full contents of `rag/answer.py`:

```python
import requests

SYSTEM_PROMPT = (
    "You are a Pokemon VGC doubles assistant. Answer the user's question "
    "using only the information in the provided context. If the context "
    "does not contain the answer, say you don't know rather than guessing."
)

OFFLINE_MESSAGE = "The knowledge assistant is offline right now -- try again later."

# Timeout for the /llmstatus health-check request (OllamaAnswerer.check_health).
# Deliberately much shorter than the 30s default used for a real answer --
# this is a liveness probe, not an inference call, so a slow response IS
# the "down" signal, not something worth waiting out.
HEALTH_CHECK_TIMEOUT = 3.0


class OllamaAnswerer:
    """Generates grounded answers via a local Ollama server, reached over
    a private Tailscale network link.

    Accepts an injected `client` (anything with `.post(url, json=..., timeout=...)`
    and `.get(url, timeout=...)` methods matching `requests`' interface) so
    callers can swap in a fake for testing without a live Ollama server.
    """

    def __init__(self, host: str, model: str = "llama3.2:3b", client=None, timeout: float = 30.0):
        self._client = client if client is not None else requests
        self._host = host
        self._model = model
        self._timeout = timeout

    @property
    def model(self) -> str:
        return self._model

    def answer(self, question: str, context_block: str) -> str:
        try:
            response = self._client.post(
                f"http://{self._host}/api/chat",
                json={
                    "model": self._model,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": f"Context:\n{context_block}\n\nQuestion: {question}"},
                    ],
                    "stream": False,
                    "options": {"num_predict": 1024},
                },
                timeout=self._timeout,
            )
            response.raise_for_status()
            return response.json()["message"]["content"]
        except (requests.RequestException, KeyError, TypeError) as e:
            print(f"OllamaAnswerer call failed: {e!r}")
            return OFFLINE_MESSAGE

    def check_health(self) -> dict:
        """Cheap liveness probe for /llmstatus: hits Ollama's own /api/tags
        endpoint (lists locally-available models) instead of running real
        inference, on a short timeout. Returns {"up": bool, "models": list}
        -- models is empty when down, since there's nothing to report."""
        try:
            response = self._client.get(f"http://{self._host}/api/tags", timeout=HEALTH_CHECK_TIMEOUT)
            response.raise_for_status()
            models = [entry["name"] for entry in response.json()["models"]]
            return {"up": True, "models": models}
        except (requests.RequestException, KeyError, TypeError) as e:
            print(f"OllamaAnswerer health check failed: {e!r}")
            return {"up": False, "models": []}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_rag_answer.py -v`
Expected: all PASS.

- [ ] **Step 5: Run the entire test suite to verify nothing else broke**

Run: `pytest -q`
Expected: all PASS. (`rag.answer.OllamaAnswerer` is imported by `bot/main.py` and used throughout the existing test suite; this task only adds new members, so no other file should need changes.)

- [ ] **Step 6: Commit**

```bash
git add rag/answer.py tests/test_rag_answer.py
git commit -m "feat: add OllamaAnswerer.check_health and .model for /llmstatus"
```

---

### Task 3: `bot/commands/llmstatus.py` — pure formatter

**Files:**
- Create: `bot/commands/llmstatus.py`
- Test: `tests/test_bot_llmstatus.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `format_llmstatus(up: bool, models: list, configured_model: str, breaker_state: str) -> str`. Task 4's `/llmstatus` command handler calls this with the result of `OllamaAnswerer.check_health()` (Task 2) and a `CircuitBreaker.state` (Task 1).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_bot_llmstatus.py`:

```python
from bot.commands.llmstatus import format_llmstatus


def test_format_llmstatus_reports_online_with_loaded_models():
    formatted = format_llmstatus(
        up=True,
        models=["llama3.2:3b", "nomic-embed-text"],
        configured_model="llama3.2:3b",
        breaker_state="closed",
    )

    assert "Online" in formatted
    assert "llama3.2:3b (loaded)" in formatted
    assert "nomic-embed-text" in formatted
    assert "closed" in formatted


def test_format_llmstatus_flags_when_the_configured_model_is_not_in_the_loaded_list():
    formatted = format_llmstatus(
        up=True, models=["some-other-model"], configured_model="llama3.2:3b", breaker_state="closed"
    )

    assert "NOT in the loaded models list" in formatted


def test_format_llmstatus_reports_offline():
    formatted = format_llmstatus(up=False, models=[], configured_model="llama3.2:3b", breaker_state="open")

    assert "Offline" in formatted
    assert "llama3.2:3b" in formatted
    assert "open" in formatted


def test_format_llmstatus_reports_the_breaker_state_for_all_three_states():
    for state in ("closed", "open", "half_open"):
        formatted = format_llmstatus(
            up=True, models=["llama3.2:3b"], configured_model="llama3.2:3b", breaker_state=state
        )
        assert state in formatted
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_bot_llmstatus.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bot.commands.llmstatus'`.

- [ ] **Step 3: Implement `bot/commands/llmstatus.py`**

```python
def format_llmstatus(up: bool, models: list, configured_model: str, breaker_state: str) -> str:
    """Pure formatter for the /llmstatus admin command's embed body.

    up/models come from rag.answer.OllamaAnswerer.check_health();
    breaker_state comes from a rag.circuit_breaker.CircuitBreaker's .state.
    """
    if up:
        status_line = "\U0001F7E2 Online"
        if models:
            loaded_note = "loaded" if configured_model in models else "NOT in the loaded models list"
            models_text = ", ".join(models)
        else:
            loaded_note = "no models reported"
            models_text = "none"
        model_line = f"**Configured model:** {configured_model} ({loaded_note})\n**Loaded models:** {models_text}\n"
    else:
        status_line = "\U0001F534 Offline"
        model_line = f"**Configured model:** {configured_model}\n"

    return f"**LLM status:** {status_line}\n{model_line}**Circuit breaker:** {breaker_state}"
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_bot_llmstatus.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add bot/commands/llmstatus.py tests/test_bot_llmstatus.py
git commit -m "feat: add pure formatter for /llmstatus"
```

---

### Task 4: Wire the circuit breaker and `/llmstatus` into `bot/main.py`

**Files:**
- Modify: `bot/main.py` (imports, `_COMMAND_COLORS`, `build_client`'s signature, a new `/llmstatus` command, `main()`)
- Modify: `tests/test_bot_main.py`
- Modify: `.env.example`

**Interfaces:**
- Consumes: `CircuitBreaker` (Task 1), `OllamaAnswerer.check_health()`/`.model` (Task 2), `format_llmstatus(...)` (Task 3), `_owner_only` (already exists, added by the observability plan).
- Produces: nothing new consumed by a later task — this is the final task in this plan.

- [ ] **Step 1: Write the failing tests**

Add these tests to `tests/test_bot_main.py` (reuses the `asyncio`, `AsyncMock`, `MagicMock`, `_extract_text` helpers already at the top of that file):

```python
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
    interaction.response.send_message = AsyncMock()

    asyncio.run(command.callback(interaction))

    sent_text = _extract_text(interaction.response.send_message)
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
    interaction.response.send_message = AsyncMock()

    asyncio.run(command.callback(interaction))

    sent_text = _extract_text(interaction.response.send_message)
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
    interaction.response.send_message = AsyncMock()

    asyncio.run(command.callback(interaction))

    _args, kwargs = interaction.response.send_message.call_args
    assert kwargs["ephemeral"] is True
```

Note: the `BOT_OWNER_ID` gate itself (owner allowed through, non-owner rejected before any health-check request is made) is already fully covered by the existing `_owner_only` unit tests in `tests/test_bot_main.py` (`test_owner_only_rejects_a_non_owner`, `test_owner_only_allows_the_owner`, `test_owner_only_rejects_everyone_when_bot_owner_id_is_unset`, `test_owner_only_rejects_everyone_when_bot_owner_id_is_malformed`, added by the observability plan) — `/llmstatus` reuses that same predicate function, so no new gate-specific test is needed here beyond confirming the check is attached (the first test above).

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_bot_main.py -v -k llmstatus`
Expected: all 4 FAIL — `AssertionError: None is not None` (no `llmstatus` command registered yet) for the first, and `AttributeError`/`TypeError` for the rest since `build_client` doesn't accept `raw_answerer` yet.

- [ ] **Step 3: Implement the changes to `bot/main.py`**

Update the imports at the top of the file. Change:

```python
from rag.answer import OFFLINE_MESSAGE, OllamaAnswerer
```

to:

```python
from bot.commands.llmstatus import format_llmstatus
from rag.answer import OFFLINE_MESSAGE, OllamaAnswerer
from rag.circuit_breaker import CircuitBreaker
```

(Add the `bot.commands.llmstatus` import alphabetically alongside the other `bot.commands.*` imports, and `rag.circuit_breaker` alphabetically alongside the other `rag.*` imports — matching this file's existing import ordering.)

Add `"llmstatus": discord.Color.orange(),` to the `_COMMAND_COLORS` dict (alongside the other command-name-to-color entries; `orange` isn't used by any existing command).

Change `build_client`'s signature from:

```python
def build_client(
    index=None, answerer=None, records=None, moves=None, usage=None, items=None
) -> tuple[discord.Client, app_commands.CommandTree]:
```

to:

```python
def build_client(
    index=None, answerer=None, raw_answerer=None, records=None, moves=None, usage=None, items=None
) -> tuple[discord.Client, app_commands.CommandTree]:
```

Inside `build_client`, add this new command (place it after the `debug_last` command, before `stats`):

```python
    @tree.command(name="llmstatus", description="Check the local LLM's health and circuit breaker state (bot owner only).")
    @app_commands.checks.cooldown(1, _COOLDOWN_SECONDS)
    @app_commands.check(_owner_only)
    async def llmstatus(interaction: discord.Interaction) -> None:
        health = await asyncio.to_thread(raw_answerer.check_health)
        formatted = format_llmstatus(
            up=health["up"],
            models=health["models"],
            configured_model=raw_answerer.model,
            breaker_state=answerer.state,
        )
        await interaction.response.send_message(embed=_embed("llmstatus", formatted), ephemeral=True)
```

Finally, in `main()`, change:

```python
    client, _tree = build_client(
        index=_build_real_index(records, items),
        answerer=_build_answerer(),
        records=records,
        moves=_load_moves(),
        usage=_load_usage(),
        items=items,
    )
```

to:

```python
    raw_answerer = _build_answerer()
    client, _tree = build_client(
        index=_build_real_index(records, items),
        answerer=CircuitBreaker(raw_answerer),
        raw_answerer=raw_answerer,
        records=records,
        moves=_load_moves(),
        usage=_load_usage(),
        items=items,
    )
```

`_build_answerer()` itself is unchanged — it still returns a plain `OllamaAnswerer`. `main()` is not unit-tested elsewhere in this codebase (it ends in a blocking `client.run(token)` call), so this wiring change has no test of its own here, consistent with that existing convention; the breaker's own behavior is fully covered by Task 1's tests, and `/ask`'s handler code is unchanged (it still just calls `answerer.answer(...)`, which now happens to be a `CircuitBreaker` instance satisfying the same interface).

- [ ] **Step 4: Update `.env.example`**

Change the `BOT_OWNER_ID` comment block from:

```
# Discord user ID of the bot owner, used to gate the admin-only /debug-last
# command (shows the most recent /ask call's full retrieval/answer detail).
# Find your own ID: Discord Settings -> Advanced -> enable Developer Mode,
# then right-click your name -> Copy User ID. Optional -- if unset,
# /debug-last is rejected for everyone.
BOT_OWNER_ID=
```

to:

```
# Discord user ID of the bot owner, used to gate the admin-only /debug-last
# and /llmstatus commands (the former shows the most recent /ask call's
# full retrieval/answer detail; the latter shows LLM health and circuit
# breaker state). Find your own ID: Discord Settings -> Advanced -> enable
# Developer Mode, then right-click your name -> Copy User ID. Optional --
# if unset, both commands are rejected for everyone.
BOT_OWNER_ID=
```

- [ ] **Step 5: Run the full `test_bot_main.py` suite to verify everything passes**

Run: `pytest tests/test_bot_main.py -v`
Expected: all PASS.

- [ ] **Step 6: Run the entire test suite as a final check**

Run: `pytest -q`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add bot/main.py tests/test_bot_main.py .env.example
git commit -m "feat: wire circuit breaker and add /llmstatus command"
```

---

## Self-review notes

- **Spec coverage:** the circuit breaker's closed/open/half-open state machine with the exact spec'd thresholds (3 failures, 60s cooldown) and value-based (not exception-based) failure detection (Task 1); `OllamaAnswerer` unchanged internally, wrapped from the outside at construction time in `bot/main.py` (Task 1 + Task 4); the `/llmstatus` health check hitting `/api/tags` on a short timeout and reporting up/down, the currently-configured model, and the breaker's state (Task 2 + Task 3 + Task 4); the `BOT_OWNER_ID` gate plus the same cooldown decorator every other command has (Task 4) — all covered. The spec's requirement to test "an interaction from the owner's user ID is allowed through, and one from any other user ID is rejected before the health-check request is made" is satisfied by the already-existing, command-agnostic `_owner_only` tests from the observability plan, since `/llmstatus` reuses that exact predicate — Task 4 calls this out explicitly rather than duplicating that coverage.
- **Out-of-scope items** (retries with backoff on transient failures, reliability work for `/calc`/`/stats`/`/moves`/`/team`) are correctly not touched by any task.
- **Type/name consistency checked:** `CircuitBreaker.answer`'s signature (`question`, `context_block`) matches `OllamaAnswerer.answer`'s exactly, so `bot/commands/ask.py`'s existing `ask_response`/`ask_response_async` code needs zero changes despite `answerer` now being a `CircuitBreaker` instance in production. `OllamaAnswerer.check_health()`'s returned dict keys (`up`, `models`) match exactly what `format_llmstatus` (Task 3) and the `/llmstatus` handler (Task 4) read. `CircuitBreaker.state`'s three string values (`CLOSED`/`OPEN`/`HALF_OPEN`, lowercase `"closed"`/`"open"`/`"half_open"`) are read directly by `format_llmstatus` with no translation needed.
- **Breaking-change fallout audited:** `build_client`'s new `raw_answerer=None` parameter is additive and defaults to `None`, so every existing test that constructs `build_client(...)` without it continues to work unchanged, as long as no existing test invokes the new `/llmstatus` command's callback (none does — it's a new command). `_build_answerer()`'s existing tests (`test_build_answerer_reads_llm_host_and_model_from_env` and friends) are untouched since that function's signature and behavior don't change; only `main()`, which has no existing unit tests, wraps its result in a `CircuitBreaker` before passing it on.
