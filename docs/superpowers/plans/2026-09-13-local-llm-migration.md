# Local LLM Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `/ask`'s paid Claude Haiku call with a free, locally-run Ollama model on a dedicated laptop, reached over Tailscale from the always-on Oracle Cloud bot host — eliminating the last paid dependency in PikaRAG.

**Architecture:** `OllamaAnswerer` (new, in `rag/answer.py`) implements the same `.answer(question, context_block) -> str` interface `HaikuAnswerer` already exposed, so `ask_response`/`ask_response_async` (`rag/answer.py` callers) need no changes at all. It POSTs to Ollama's `/api/chat` HTTP endpoint via the already-installed `requests` library, over a private Tailscale network link between the Oracle Cloud instance and the laptop — no new public exposure, no port-forwarding. `HaikuAnswerer` and `rag/spend_tracker.py` are deleted outright once the swap lands; there is no paid fallback path.

**Tech Stack:** Python 3.11, `requests` (already a dependency), Ollama (laptop-side, new), Tailscale (both machines, new). No new Python package dependencies.

**Spec:** `docs/superpowers/specs/2026-09-13-local-llm-migration-design.md`

## Global Constraints

- Model choice is a ~3B-parameter instruct model (`llama3.2:3b` default) — the laptop is 8GB RAM, CPU-only; nothing larger fits safely.
- No automatic fallback to a paid API under any circumstance — an unreachable laptop must produce a friendly "offline" message, never a silent reroute to Anthropic.
- `LLM_HOST`/`LLM_MODEL` are environment variables (matching the existing `DISCORD_TOKEN` pattern), not hardcoded — the model/host must be swappable without a code change.
- `requests` is the only HTTP client used — no new dependency added for this migration.
- `HaikuAnswerer`, `rag/spend_tracker.py`, and the `anthropic` package are removed entirely once `OllamaAnswerer` is wired in — not kept dormant.

---

### Task 1: Implement `OllamaAnswerer`

**Files:**
- Modify: `rag/answer.py` — add `OllamaAnswerer`, `OFFLINE_MESSAGE` alongside the still-present `HaikuAnswerer` (removed in Task 3). **Note:** `rag/answer.py` already defines a module-level `DEFAULT_MODEL = "claude-haiku-4-5"` for `HaikuAnswerer` — do not add a second `DEFAULT_MODEL` constant; `OllamaAnswerer`'s default model is a literal on its own `__init__` signature (see Step 3) to avoid any name collision between the two answerers' defaults.
- Modify: `tests/test_rag_answer.py` — add `OllamaAnswerer` tests alongside the still-present `HaikuAnswerer` tests (removed in Task 3)

**Interfaces:**
- Produces: `OllamaAnswerer(host: str, model: str = "llama3.2:3b", client=None, timeout: float = 30.0)` with `.answer(question: str, context_block: str) -> str`, matching `HaikuAnswerer`'s existing shape so `ask_response`/`ask_response_async` (`rag/answer.py` callers) need zero changes. `client` defaults to the real `requests` module; tests inject a fake with a `.post(url, json=..., timeout=...)` method returning an object with `.raise_for_status()` and `.json()`, mirroring how `requests.Response` behaves.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_rag_answer.py` (append; do not touch the existing `HaikuAnswerer` tests above):

```python
import requests

from rag.answer import OFFLINE_MESSAGE, OllamaAnswerer


class _FakeOllamaResponse:
    def __init__(self, json_data, status_code=200):
        self._json_data = json_data
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error")

    def json(self):
        return self._json_data


class _FakeOllamaClient:
    def __init__(self, response_json=None, exception=None):
        self._response_json = response_json
        self._exception = exception
        self.calls = []

    def post(self, url, json=None, timeout=None):
        self.calls.append({"url": url, "json": json, "timeout": timeout})
        if self._exception:
            raise self._exception
        return _FakeOllamaResponse(self._response_json)


def test_ollama_answer_returns_the_models_response_text():
    client = _FakeOllamaClient(response_json={"message": {"content": "Gyarados has 95 base HP."}})
    answerer = OllamaAnswerer(host="100.1.2.3:11434", client=client)

    result = answerer.answer("How bulky is Gyarados?", "Gyarados base HP: 95.")

    assert result == "Gyarados has 95 base HP."


def test_ollama_answer_sends_the_question_and_context_to_the_client():
    client = _FakeOllamaClient(response_json={"message": {"content": "anything"}})
    answerer = OllamaAnswerer(host="100.1.2.3:11434", client=client)

    answerer.answer("How bulky is Gyarados?", "Gyarados base HP: 95.")

    sent = client.calls[0]["json"]
    user_message = sent["messages"][-1]["content"]
    assert "How bulky is Gyarados?" in user_message
    assert "Gyarados base HP: 95." in user_message


def test_ollama_answer_uses_the_grounding_system_prompt():
    client = _FakeOllamaClient(response_json={"message": {"content": "anything"}})
    answerer = OllamaAnswerer(host="100.1.2.3:11434", client=client)

    answerer.answer("How bulky is Gyarados?", "Gyarados base HP: 95.")

    sent = client.calls[0]["json"]
    system_message = sent["messages"][0]["content"]
    assert "only" in system_message.lower()
    assert "context" in system_message.lower()


def test_ollama_answer_posts_to_the_configured_host_and_model():
    client = _FakeOllamaClient(response_json={"message": {"content": "anything"}})
    answerer = OllamaAnswerer(host="100.1.2.3:11434", model="phi3:mini", client=client)

    answerer.answer("question", "context")

    call = client.calls[0]
    assert call["url"] == "http://100.1.2.3:11434/api/chat"
    assert call["json"]["model"] == "phi3:mini"


def test_ollama_answer_returns_offline_message_on_connection_error():
    client = _FakeOllamaClient(exception=requests.exceptions.ConnectionError("refused"))
    answerer = OllamaAnswerer(host="100.1.2.3:11434", client=client)

    result = answerer.answer("question", "context")

    assert result == OFFLINE_MESSAGE


def test_ollama_answer_returns_offline_message_on_timeout():
    client = _FakeOllamaClient(exception=requests.exceptions.Timeout("slow"))
    answerer = OllamaAnswerer(host="100.1.2.3:11434", client=client)

    result = answerer.answer("question", "context")

    assert result == OFFLINE_MESSAGE


def test_ollama_answer_returns_offline_message_on_http_error_status():
    client = _FakeOllamaClient(response_json={}, status_code=500)
    answerer = OllamaAnswerer(host="100.1.2.3:11434", client=client)

    result = answerer.answer("question", "context")

    assert result == OFFLINE_MESSAGE


def test_ollama_answer_returns_offline_message_on_malformed_response():
    client = _FakeOllamaClient(response_json={"unexpected": "shape"})
    answerer = OllamaAnswerer(host="100.1.2.3:11434", client=client)

    result = answerer.answer("question", "context")

    assert result == OFFLINE_MESSAGE
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_rag_answer.py -v`
Expected: the 8 new `test_ollama_*` tests FAIL with `ImportError: cannot import name 'OllamaAnswerer' from 'rag.answer'` (or `OFFLINE_MESSAGE`). The existing `HaikuAnswerer` tests above them still PASS untouched.

- [ ] **Step 3: Implement `OllamaAnswerer`**

Add to `rag/answer.py`, above or below the existing `HaikuAnswerer` class (leave `HaikuAnswerer` and its imports untouched in this task):

```python
import requests

OFFLINE_MESSAGE = "The knowledge assistant is offline right now -- try again later."


class OllamaAnswerer:
    """Generates grounded answers via a local Ollama server, reached over
    a private Tailscale network link.

    Accepts an injected `client` (anything with a `.post(url, json=..., timeout=...)`
    method matching `requests`' interface) so callers can swap in a fake for
    testing without a live Ollama server.
    """

    def __init__(self, host: str, model: str = "llama3.2:3b", client=None, timeout: float = 30.0):
        self._client = client if client is not None else requests
        self._host = host
        self._model = model
        self._timeout = timeout

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
                },
                timeout=self._timeout,
            )
            response.raise_for_status()
            return response.json()["message"]["content"]
        except (requests.RequestException, KeyError, TypeError):
            return OFFLINE_MESSAGE
```

Note: `SYSTEM_PROMPT` is the module-level constant `HaikuAnswerer` already defines at the top of `rag/answer.py` — reuse it as-is, do not redefine it.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_rag_answer.py -v`
Expected: all tests PASS (existing `HaikuAnswerer` tests + the 8 new `OllamaAnswerer` tests).

- [ ] **Step 5: Commit**

```bash
git add rag/answer.py tests/test_rag_answer.py
git commit -m "feat: add OllamaAnswerer for local LLM inference over Tailscale"
```

---

### Task 2: Wire `OllamaAnswerer` into the bot

**Files:**
- Modify: `bot/main.py:23` (import), `bot/main.py:238` (construction in `main()`) — add a `_build_answerer()` helper and use it in place of `HaikuAnswerer()`
- Modify: `tests/test_bot_main.py` — add one test for `_build_answerer()`

**Interfaces:**
- Consumes: `OllamaAnswerer(host: str, model: str = "llama3.2:3b")` from Task 1.
- Produces: `_build_answerer() -> OllamaAnswerer` in `bot/main.py`, reading `LLM_HOST` (required) and `LLM_MODEL` (optional, defaults to `"llama3.2:3b"`) from `os.environ` — mirrors the existing `_build_real_index(records, items)` helper's role as a small, testable construction function called from `main()`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_bot_main.py`. This tests `_build_answerer()`'s env-reading
through the public `.answer()` interface (matching how `tests/test_rag_answer.py`
already tests `OllamaAnswerer` — via a fake client's captured calls, never by
reaching into private attributes):

```python
import rag.answer
from bot.main import _build_answerer


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_bot_main.py -v -k build_answerer`
Expected: FAIL with `ImportError: cannot import name '_build_answerer' from 'bot.main'`.

- [ ] **Step 3: Implement `_build_answerer` and wire it into `main()`**

In `bot/main.py`, change the import at line 23:

```python
from rag.answer import HaikuAnswerer
```

to:

```python
from rag.answer import OllamaAnswerer
```

Add a new helper function near `_build_real_index` (both are small construction helpers called from `main()`):

```python
def _build_answerer() -> OllamaAnswerer:
    return OllamaAnswerer(
        host=os.environ["LLM_HOST"],
        model=os.environ.get("LLM_MODEL", "llama3.2:3b"),
    )
```

In `main()`, change:

```python
        answerer=HaikuAnswerer(),
```

to:

```python
        answerer=_build_answerer(),
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_bot_main.py -v`
Expected: all tests PASS, including the 2 new `_build_answerer` tests.

- [ ] **Step 5: Commit**

```bash
git add bot/main.py tests/test_bot_main.py
git commit -m "feat: wire OllamaAnswerer into the bot via LLM_HOST/LLM_MODEL env config"
```

---

### Task 3: Remove the Haiku path entirely

**Files:**
- Modify: `rag/answer.py` — remove `HaikuAnswerer` and its `from rag import spend_tracker` import
- Modify: `tests/test_rag_answer.py` — remove the `HaikuAnswerer` tests (the `test_answer_*` tests that predate this plan, all four of them)
- Delete: `rag/spend_tracker.py`
- Delete: `tests/test_spend_tracker.py`
- Modify: `requirements.txt` — remove the `anthropic==0.125.0` line (and its preceding comment block, if any lines are anthropic-specific — check before deleting; the `torch`/`sentence-transformers` pinning comment above it is unrelated and must stay)

**Interfaces:**
- Consumes: nothing new.
- Produces: nothing new — this task only removes now-dead code. `OllamaAnswerer` (Task 1) is unaffected; it doesn't import anything from `spend_tracker` or `HaikuAnswerer`.

- [ ] **Step 1: Confirm nothing else references what's being removed**

Run: `grep -rn "HaikuAnswerer\|spend_tracker" --include="*.py" .`
Expected output: only matches inside `rag/answer.py` (the class/import itself) and `tests/test_rag_answer.py`/`tests/test_spend_tracker.py` (the tests being removed in this task). If anything else matches (it shouldn't, per the codebase survey done while writing this plan), stop and investigate before proceeding — that would mean something outside this migration still depends on the Haiku path.

- [ ] **Step 2: Remove `HaikuAnswerer` from `rag/answer.py`**

Delete the `from rag import spend_tracker` import line, the `DEFAULT_MODEL = "claude-haiku-4-5"` constant (it belongs to `HaikuAnswerer` alone — `OllamaAnswerer` never used it, per Task 1's note), and the entire `HaikuAnswerer` class definition (everything from `class HaikuAnswerer:` through the end of its `answer` method). Leave `SYSTEM_PROMPT`, `OFFLINE_MESSAGE`, the `requests` import, and `OllamaAnswerer` untouched.

- [ ] **Step 3: Remove the `HaikuAnswerer` tests from `tests/test_rag_answer.py`**

Delete the four `test_answer_*` tests (`test_answer_returns_the_clients_response_text`, `test_answer_sends_the_question_and_context_to_the_client`, `test_answer_uses_the_grounding_system_prompt`, `test_answer_appends_warning_once_spend_crosses_threshold`) and their supporting fixture classes (`_FakeContentBlock`, `_FakeUsage`, `_FakeMessage`, `_FakeMessages`, `_FakeClient`) and the `from rag.answer import HaikuAnswerer` import line. Leave the `test_ollama_*` tests and their fixtures (added in Task 1) untouched.

- [ ] **Step 4: Delete the spend tracker module and its tests**

```bash
git rm rag/spend_tracker.py tests/test_spend_tracker.py
```

- [ ] **Step 5: Remove the `anthropic` dependency**

In `requirements.txt`, delete the line `anthropic==0.125.0`. Leave every other line (including the `torch`/`sentence-transformers` pinning comment) unchanged.

- [ ] **Step 6: Run the full test suite**

Run: `pytest -q`
Expected: all tests PASS, no `HaikuAnswerer`/`spend_tracker` references remain, count is `(previous total) - 4 (Haiku tests) - 6 (spend_tracker tests)`.

- [ ] **Step 7: Commit**

```bash
git add rag/answer.py tests/test_rag_answer.py requirements.txt
git rm rag/spend_tracker.py tests/test_spend_tracker.py
git commit -m "refactor: remove HaikuAnswerer and spend_tracker, no paid path remains"
```

---

### Task 4: Update docs and `.env.example` for the new setup

**Files:**
- Modify: `.env.example` — replace the `ANTHROPIC_*` block with `LLM_HOST`/`LLM_MODEL`
- Modify: `docs/DEPLOYMENT.md` — replace the Anthropic API key/budget-cap steps with a new "Local LLM (Ollama + Tailscale)" section; update the `.env` fill-in instruction
- Modify: `README.md` — update the `rag/` architecture line and the `Setup` section's `.env` fill-in comment

**Interfaces:** none — documentation only, no code.

- [ ] **Step 1: Update `.env.example`**

Replace the current file's Anthropic block:

```
# Anthropic API key: console.anthropic.com -> Settings -> API Keys.
# Set a prepaid budget cap under Settings -> Billing before generating this --
# see docs/DEPLOYMENT.md for why.
ANTHROPIC_API_KEY=

# Must match the spend cap you set in Anthropic Console above -- /ask appends
# a one-time in-Discord warning once estimated cumulative spend crosses
# (this value - $1). This is a secondary, estimate-based warning; Console's
# own spend-limit notifications are the authoritative one.
ANTHROPIC_SPEND_CAP_USD=5.0
```

with:

```
# Local LLM server (Ollama) that /ask sends grounded-answer requests to,
# reached over a private Tailscale network -- see docs/DEPLOYMENT.md's
# "Local LLM (Ollama + Tailscale)" section for setup on both machines.
# <laptop's Tailscale IP>:11434, e.g. 100.64.1.2:11434 -- find it by running
# `tailscale ip` on the laptop.
LLM_HOST=

# Ollama model tag to request. Must already be pulled on the LLM_HOST
# machine (`ollama pull llama3.2:3b`). Optional -- defaults to llama3.2:3b
# if unset.
LLM_MODEL=llama3.2:3b
```

- [ ] **Step 2: Update `docs/DEPLOYMENT.md`'s accounts/secrets section**

In section "## 1. Accounts and secrets (needs you -- can't be automated)", remove items 2 and 3:

```
2. **Anthropic API key**: https://console.anthropic.com -> Settings ->
   API Keys -> Create Key.
3. **Anthropic prepaid budget cap**: console.anthropic.com -> Settings ->
   Billing -> set a spend limit *before* the bot goes live and starts
   burning real `/ask` requests against it. This is an account setting with
   no API/CLI equivalent -- it has to be clicked, by you, once.
```

Renumber the remaining "Oracle Cloud instance" item from 4 to 2, and add a new item 3:

```
3. **A dedicated laptop for local LLM inference** (8GB+ RAM; CPU-only is
   fine, just slower) that stays powered on and connected whenever `/ask`
   should work -- see the new "Local LLM (Ollama + Tailscale)" section
   below for setup.
```

- [ ] **Step 3: Add the "Local LLM (Ollama + Tailscale)" section**

Insert as a new section, after section 2 ("Server setup") and before the renumbered "Install the systemd units" section:

```markdown
## 3. Local LLM (Ollama + Tailscale)

Sets up the laptop that runs `/ask`'s language model, and connects it
privately to the Oracle Cloud instance -- no public IP, no port-forwarding.

**On the laptop (Windows):**

1. Install Tailscale: https://tailscale.com/download/windows, sign in,
   `tailscale up` (or use the tray app's "Connect" button).
2. Install Ollama: https://ollama.com/download/windows.
3. Pull the model: `ollama pull llama3.2:3b` (roughly 2GB download; Ollama
   runs as a background service afterward, listening on `localhost:11434`).
4. Find the laptop's Tailscale IP: `tailscale ip` (prints something like
   `100.64.1.2`). This is the value `LLM_HOST` needs, as `<that-ip>:11434`.
5. Keep the laptop powered on, plugged in, and connected whenever `/ask`
   should work -- Ollama does nothing until a request arrives, but it can't
   answer one if the machine is asleep or off.

**On the Oracle Cloud instance:**

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```

Both steps are outbound-only (Tailscale's coordination happens over HTTPS
out, same as the bot's existing Discord/PokeAPI/Pikalytics traffic) --
consistent with this instance's "no inbound ports needed" setup from
section 1.

Set `LLM_HOST` in `.env` (section 4 below) to the laptop's Tailscale IP
and port, e.g. `LLM_HOST=100.64.1.2:11434`.
```

Renumber the old sections 3, 4, 5 ("Install the systemd units", "Regulation bumps", "Updating the deployed code") to 4, 5, 6.

- [ ] **Step 4: Update the `.env` fill-in instruction in "Server setup"**

Change:

```
sudo -u pikarag $EDITOR .env   # fill in DISCORD_TOKEN and ANTHROPIC_API_KEY
```

to:

```
sudo -u pikarag $EDITOR .env   # fill in DISCORD_TOKEN and LLM_HOST
```

- [ ] **Step 5: Update `README.md`**

Change:

```
- **`rag/`** — embeds and retrieves Pokemon data, answers `/ask` via Claude
  (Haiku)
```

to:

```
- **`rag/`** — embeds and retrieves Pokemon data, answers `/ask` via a
  locally-run LLM (Ollama, reached over Tailscale)
```

Change:

```
cp .env.example .env   # fill in DISCORD_TOKEN, ANTHROPIC_API_KEY, ANTHROPIC_SPEND_CAP_USD
```

to:

```
cp .env.example .env   # fill in DISCORD_TOKEN, LLM_HOST (see docs/DEPLOYMENT.md)
```

- [ ] **Step 6: Commit**

```bash
git add .env.example docs/DEPLOYMENT.md README.md
git commit -m "docs: document Ollama + Tailscale setup, replace Anthropic instructions"
```

---

### Task 5: Set up both machines and verify end to end

This task is manual/hands-on-hardware — there is no code change, and it can't be run from this session since it requires physical access to the laptop and the live Oracle Cloud instance. Follow it once ready to actually cut over.

**Files:** none (operational verification only)

- [ ] **Step 1: Set up the laptop**

Follow `docs/DEPLOYMENT.md`'s "Local LLM (Ollama + Tailscale)" section, laptop half: install Tailscale, sign in, install Ollama, `ollama pull llama3.2:3b`, note the `tailscale ip` output.

- [ ] **Step 2: Set up the Oracle Cloud instance**

SSH in, install Tailscale (`curl -fsSL https://tailscale.com/install.sh | sh && sudo tailscale up`), confirm it can reach the laptop:

```bash
ping <laptop-tailscale-ip>
curl http://<laptop-tailscale-ip>:11434/api/tags
```

Expected: the `curl` returns a JSON list of installed models including `llama3.2:3b`. If it times out, check that Ollama is actually running on the laptop (it should auto-start as a Windows service after install) and that Windows Firewall isn't blocking the Tailscale interface.

- [ ] **Step 3: Update the deployed `.env` and pull the new code**

```bash
cd /opt/pikarag
sudo -u pikarag git pull
sudo -u pikarag .venv/bin/pip install -r requirements.txt
sudo -u pikarag $EDITOR .env   # set LLM_HOST=<laptop-tailscale-ip>:11434, remove old ANTHROPIC_* lines
sudo systemctl restart pikarag-bot.service
```

- [ ] **Step 4: Verify `/ask` works end to end**

In Discord, run `/ask what's a good EV spread for Landorus-Therian`. Expected: a grounded answer arrives (slower than Haiku was — CPU inference on a 3B model, expect several seconds). Check logs if it doesn't respond:

```bash
sudo journalctl -u pikarag-bot.service -f
```

- [ ] **Step 5: Verify the offline degradation path**

Turn off Tailscale on the laptop (or shut it down), then run `/ask` again in Discord. Expected: the bot replies with `OFFLINE_MESSAGE` ("The knowledge assistant is offline right now -- try again later.") within `timeout` seconds (30s default), not a crash or a hung interaction. Turn the laptop's Tailscale back on afterward and confirm a follow-up `/ask` works normally again.

No commit for this task — it's verification of already-committed work (Tasks 1-4).
