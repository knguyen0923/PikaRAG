# Pika-RAG: Local LLM Migration — Design

Status: Approved
Date: 2026-09-13

**Superseded 2026-09-20:** this design's central hardware assumption (an
8GB RAM, CPU-only Windows laptop, ruling out 7B+ models) never actually
got built — the Windows laptop was dropped in favor of a MacBook already
set up for local dev, which runs a 9.7B model (`qwen3.5:9b`) fine. The
mechanism this doc designed (Tailscale networking, `OllamaAnswerer`,
graceful degradation, no paid fallback) is exactly what's live today,
unchanged — only the "worst-case hardware" framing and model-size math
below are stale. See `docs/DEPLOYMENT.md` section 3 for the current setup.

## Purpose

Eliminate the one remaining paid dependency in PikaRAG. Hosting (Oracle Cloud
free tier) and embeddings (local `sentence-transformers`) already cost $0;
the only paid component is the Claude Haiku call in `/ask` (~$0.003-0.007 per
query, hard-capped at $5 via `rag/spend_tracker.py`). This replaces that call
with a locally-run LLM on a dedicated Windows laptop (8GB RAM, CPU-only —
worst-case hardware, so the design must work without a GPU), reached over a
private Tailscale network from the always-on Oracle Cloud instance. Result:
`/ask` costs nothing to run, ever, at the cost of slower responses and an
"offline" state when the laptop isn't reachable.

## Scope

In scope:
- A Tailscale-based private network between the Oracle Cloud instance and the
  laptop (no port-forwarding, no public exposure of the laptop).
- Ollama running on the laptop, serving a small (~3B parameter) instruct model
  sized for 8GB RAM / CPU-only inference.
- A new `OllamaAnswerer` in `rag/answer.py` implementing the same interface as
  the removed `HaikuAnswerer` (`.answer(question, context_block) -> str`), so
  `ask_response`/`ask_response_async` and their tests are unaffected.
- Graceful degradation: a request timeout when the laptop is unreachable
  produces a friendly "offline" reply instead of an exception surfacing to
  the user.
- Removal of the Anthropic-backed path entirely: `HaikuAnswerer`,
  `rag/spend_tracker.py`, the `anthropic` dependency, and their tests.

Out of scope (see "Out of scope" section for detail):
- The evaluation harness for measuring answer-quality regression from this
  model swap — a real need this migration creates, but a separate, already-
  planned piece of work.
- Retrieval-quality changes (hybrid search, reranking, citations) — unrelated
  to which LLM generates the final answer.
- Any automatic fallback to a paid API when the laptop is offline.
- Running the Discord bot process itself on the laptop (an alternative
  topology considered and rejected — see "Alternatives considered").

## Architecture

```
Discord
   │
   ▼
discord.py bot (Oracle Cloud, systemd, always-on) — UNCHANGED
   │
   ├─ Chroma + sentence-transformers (local to Oracle Cloud) — UNCHANGED
   │
   └─ /ask: OllamaAnswerer.answer(question, context_block)
             │
             │  HTTP POST, over Tailscale private network
             ▼
      Ollama server (Windows laptop, 8GB RAM, CPU-only)
        model: llama3.2:3b (or phi3:mini) — configurable
```

The laptop is a passive inference server: Ollama sits idle until a request
arrives, and never talks to Discord. The Oracle Cloud bot is the only thing
with a Discord connection; it makes one outbound HTTP call per `/ask`
invocation to whichever host `LLM_HOST` names.

## Networking — Tailscale

Both machines join the same private tailnet:

- **Oracle Cloud instance:** install the Tailscale client, `tailscale up`.
- **Laptop:** install Tailscale for Windows, `tailscale up`. Ollama's default
  bind (`localhost:11434`) is reachable from the Oracle Cloud box at the
  laptop's stable Tailscale IP (e.g. `100.x.y.z:11434`) without any router
  configuration, port-forwarding, or public IP exposure.

Verified 2026-09-13: Tailscale's **Personal** plan is free forever (not a
trial), with unlimited devices under a 6-user cap — well within a 2-device
personal setup. Paid-tier gates (log streaming, just-in-time access, >50
tagged resources) don't apply here.

`LLM_HOST` (the laptop's Tailscale IP:port) is an environment variable read
by `bot/main.py` alongside the existing `.env` config, matching how
`ANTHROPIC_API_KEY` was configured today.

## Model choice

8GB RAM, CPU-only laptop rules out 7B+ models (quantized Q4 still risks
~5GB+ runtime footprint plus Windows overhead, likely swapping to disk).
Target a ~3B instruct model instead:

- **Llama 3.2 3B Instruct** or **Phi-3-mini**, Q4 quantization via Ollama
  (`ollama pull llama3.2:3b`). Both run in roughly 3-4GB, leaving headroom
  for the OS.
- Model name is a config value (env var), not hardcoded, so it can be
  swapped later (e.g. if the laptop is upgraded) without touching
  `rag/answer.py` or `bot/main.py` beyond the config read.

Tradeoff accepted explicitly: a 3B model has weaker instruction-following
than Haiku, particularly for the "answer only from context, say you don't
know" discipline the system prompt relies on. This is the reason the
evaluation-harness work (out of scope here, tracked separately) matters —
it's how a quality regression from this swap gets caught rather than
discovered by users.

## Integration (`rag/answer.py`)

`OllamaAnswerer` replaces `HaikuAnswerer` as the sole answerer, keeping the
exact interface `ask_response` already depends on:

```python
class OllamaAnswerer:
    def __init__(self, host: str, model: str, client=None, timeout: float = 30.0):
        self._host = host
        self._model = model
        self._client = client or requests  # injectable for tests, matches
                                            # the existing injected-client pattern
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
        except (requests.RequestException, KeyError):
            return "The knowledge assistant is offline right now — try again later."
```

`SYSTEM_PROMPT` (the "answer only from the provided context, say you don't
know otherwise" instruction) carries over unchanged from the current
`rag/answer.py`. `requests` is already a project dependency — no new library
needed. The `anthropic` package and its usage-tracking call are removed.

## Error handling

- **Laptop unreachable / Ollama not running / request times out:** caught in
  `OllamaAnswerer.answer` itself (network exception or malformed response),
  returns the fixed "offline" message rather than raising — `/ask` degrades
  gracefully, every other command (`/calc`, `/stats`, `/moves`, `/team`,
  `/import`, `/scout`) is entirely unaffected since none of them touch the
  LLM path.
- **Timeout value:** 30 seconds, generous for CPU inference on a small model
  while still bounding how long a Discord interaction can hang before
  Discord's own interaction-response window (3 seconds initial ack, up to
  15 minutes for a deferred followup) is at risk — `/ask`'s existing
  `ask_response_async` + `asyncio.to_thread` pattern (deferred response)
  already accommodates slower calls than Haiku's.
- **No automatic paid fallback.** If the laptop is down, the honest answer is
  "the assistant is offline," not a silent reversion to a paid API — that
  would reintroduce the cost this migration exists to remove. `HaikuAnswerer`
  and `rag/spend_tracker.py` are deleted outright rather than kept dormant.

## Operational notes

The laptop is a dedicated, always-on (when in use) inference box for this
project's testing and usage — not a shared daily-driver machine. The
"offline" degradation path is a safety net for reboots/network hiccups, not
an expected everyday state. This is an explicit user decision, not an
assumption baked into the design; if that changes, the offline path would
become the common case rather than the exception, which would be worth
revisiting.

## Testing plan

- `rag/answer.py` (`OllamaAnswerer`): unit tests with an injected fake HTTP
  client — success path (returns model's message content), timeout/
  connection-error path (returns the offline message), malformed-response
  path (missing `message.content` key, same offline fallback).
- `bot/main.py`: wiring test that `/ask` constructs `OllamaAnswerer` with
  `LLM_HOST`/model config from environment, replacing the existing
  Haiku-construction test.
- Remove `tests/test_spend_tracker.py` (or equivalent) and any
  `HaikuAnswerer`-specific tests along with the code they cover.
- `ask_response`/`ask_response_async` themselves need no test changes — they
  depend only on the answerer's `.answer()` interface, which is preserved.
- Manual end-to-end smoke test: laptop on, `/ask` a real question in Discord,
  confirm a grounded answer; then laptop off/unreachable, confirm the
  friendly offline message instead of an error.

## Alternatives considered

- **Laptop runs the whole bot, replacing Oracle Cloud entirely.** Rejected:
  Oracle Cloud hosting is already $0 and reliably always-on; moving the
  Discord connection itself to a laptop trades a stable host for one that
  goes offline whenever the laptop sleeps/reboots/loses power, with no cost
  benefit (hosting wasn't the paid part).
- **Cloudflare Tunnel instead of Tailscale.** Both are free for this use
  case; Tailscale was preferred because it never creates a public-facing
  endpoint at all (private mesh network only), while a tunnel exposes a
  public hostname even if authenticated.
- **Automatic fallback to Haiku when the laptop is offline.** Rejected as
  contrary to the goal — it would silently reintroduce the exact cost this
  migration removes, and defeats the point of deleting the paid path
  outright.

## Out of scope

- **Evaluation harness** for catching answer-quality regressions from the
  weaker local model — real and important follow-up, tracked as its own
  design (see project's broader "production-grade RAG" brainstorm).
- **Retrieval-quality improvements** (hybrid search, entity-aware retrieval,
  reranking, citations) — orthogonal to which model generates the answer.
- **Running the bot process on the laptop** — see "Alternatives considered."
- **A manual break-glass fallback to a paid API** — deliberately not built;
  revisit only if the user's cost-vs-availability priority changes.
