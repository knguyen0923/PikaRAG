# Pika-RAG: Observability — Design

Status: Approved
Date: 2026-09-13

## Purpose

A bad `/ask` answer is undebuggable today — nothing records what was
retrieved, what the model said, or how long it took. This matters more
post-[[local-llm-migration]]: CPU inference latency on the laptop is a new
variable worth watching over time, and `rag/spend_tracker.py`'s removal
leaves no record of `/ask` activity at all. This adds structured, local
logging of every `/ask` call.

## Scope

In scope:
- A SQLite log of every `/ask` call: question, retrieved chunk IDs +
  distances, answer, sources, latency, whether the confidence gate fired
  or the answerer degraded to "offline."
- An admin-only Discord command to inspect the most recent call's full
  detail.

Out of scope (see "Out of scope" section for detail):
- Cost tracking (nothing left to track — no paid path).
- Metrics dashboards / external monitoring services.
- Logging for non-`/ask` commands.

### Dependencies

This spec's `sources`, `best_distance`, and `gate_fired` log fields (see
"Data model" below) do not correspond to anything that exists in the
codebase today: `build_context_block` (`rag/retrieve.py`) discards chunk
identity/distance and returns a bare string, and there is no confidence
gate or "sources" concept anywhere in the current code. Those fields are
proposed by the sibling spec
`docs/superpowers/specs/2026-09-13-grounding-trust-design.md`, which is
itself only a design spec, not yet implemented. **This spec's `log_ask()`
integration cannot be built as designed until grounding-trust is
implemented first** — an implementation plan covering both specs must
sequence grounding-trust before this one.

## Data model

`rag/observability.py`, a small module using Python's stdlib `sqlite3` —
no new dependency, consistent with this project's default toward
zero-cost, zero-new-infrastructure choices. Database at
`data/observability.db`. Implementation must add `data/observability.db`
to `.gitignore` — currently it only lists `data/chroma/` and
`data/state/`, so this is a required step, not an existing fact.

```sql
CREATE TABLE ask_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,        -- ISO 8601, passed in by the caller (see note)
    question TEXT NOT NULL,
    retrieved_chunks TEXT NOT NULL, -- JSON list of {id, distance}
    sources TEXT,                   -- JSON, from [[grounding-trust]]'s sources list
    best_distance REAL,
    gate_fired INTEGER NOT NULL,    -- 0/1, confidence gate from [[grounding-trust]]
    answer TEXT,
    degraded INTEGER NOT NULL,      -- 0/1, OllamaAnswerer offline fallback fired
    latency_ms INTEGER NOT NULL
);
```

`log_ask(...)` takes `timestamp` as a parameter rather than calling
`datetime.now()` internally, keeping the function pure/injectable for
tests (mirrors this project's existing pattern of injected clients over
hidden globals, e.g. `SentenceTransformerEmbedder`'s injected `model`).

## Integration

`ask_response`/`ask_response_async` are both defined entirely in
`bot/commands/ask.py` (lines 7-25); `rag/answer.py` contains only the
`OllamaAnswerer` class and has no `ask_response` functions or callers.
The actual caller of `ask_response_async` is `bot/main.py`'s `ask`
slash-command handler (around lines 63-72, inside `build_client`). That
call site calls `log_ask(...)` once per invocation, after the answer is
produced, wrapped so a logging failure **never** breaks the user-facing
response:

```python
try:
    log_ask(question=question, retrieved_chunks=..., ..., latency_ms=elapsed_ms)
except Exception:
    pass  # observability is best-effort; never blocks the answer
```

**Deriving `degraded`.** `OllamaAnswerer.answer()` (`rag/answer.py`) only
ever returns a plain string and never raises — on failure it returns the
fixed sentinel string `OFFLINE_MESSAGE` ("The knowledge assistant is
offline right now -- try again later."). `degraded` is derived via string
equality against the imported constant: `answer_text ==
OFFLINE_MESSAGE` (`from rag.answer import OFFLINE_MESSAGE`). This is a
deliberate string-sentinel choice, not a fragile one in practice — a real
model response coinciding with that exact fixed string is not a realistic
concern — and it requires no change to `OllamaAnswerer`'s already-shipped
interface.

**Deriving `latency_ms`.** Nothing in `ask_response`/`ask_response_async`
today measures elapsed time. `latency_ms` is measured by wrapping the
*entire* `ask_response_async` call — retrieval plus the LLM call
combined — with a timer at the call site in `bot/main.py`'s `ask` handler,
not just the Ollama call in isolation. This captures the end-to-end
latency an operator actually cares about, matching the Purpose section's
point that CPU-bound retrieval is also worth watching, not just the LLM
call.

## Admin command

`/debug-last` (or similar) is restricted to the bot owner. This bot does
not use `discord.ext.commands.Bot`/`AutoShardedBot` — `bot/main.py`
constructs a bare `discord.Client(intents=intents)` with a separate
`app_commands.CommandTree` — so `is_owner()`, which only exists on
`commands.Bot`, is not available. Instead, a new `BOT_OWNER_ID`
environment variable holds the owner's Discord user ID, documented in
`.env.example` following the same pattern as `DISCORD_TOKEN`/`LLM_HOST`.
The command is gated by an `app_commands.check` (or equivalent decorator)
that compares `interaction.user.id == int(os.environ["BOT_OWNER_ID"])`
and rejects the interaction otherwise. On success it queries the most
recent `ask_log` row and posts its full detail — question, chunks +
distances, gate/degraded flags, latency, full answer text — for live
debugging without needing shell access to the Oracle Cloud instance.

## Error handling

- Logging failures (disk full, DB locked, etc.) are swallowed, not
  surfaced to the Discord user — observability is a debugging aid, not a
  feature the bot depends on to function.
- `/debug-last` with an empty log table reports that plainly rather than
  erroring.

## Testing plan

- `log_ask`: writes a row with correct fields, given fixed inputs;
  round-trip read confirms JSON fields serialize/deserialize correctly.
- `ask` handler (`bot/main.py`): confirms `log_ask` is called with
  expected arguments (using a fake/spy) after `ask_response_async`
  returns, and that a raising `log_ask` doesn't propagate — the answer is
  still sent to the user normally.
- `degraded` derivation: given an `answer_text` equal to
  `rag.answer.OFFLINE_MESSAGE`, `degraded` is logged as `1`/`True`; given
  any other answer text (including one that merely resembles the offline
  message), `degraded` is logged as `0`/`False`.
- `latency_ms` derivation: the timer wraps the full
  `ask_response_async` call (a fake index/answerer with a known
  artificial delay confirms the measured duration reflects both the
  retrieval and answerer stages, not just one of them).
- `/debug-last`: formats a known row correctly; empty-table case handled;
  a non-owner `interaction.user.id` (i.e. one not equal to the configured
  `BOT_OWNER_ID`) is rejected by the `app_commands.check`, and an owner
  `interaction.user.id` is allowed through to the command's own logic —
  e.g. what it does with a found/missing row.

## Out of scope

- **Cost tracking** — `rag/spend_tracker.py` is deleted per
  [[local-llm-migration]]; there's no paid usage left to track. If a
  manual paid fallback is ever reintroduced, cost tracking would need to
  come back too, but that's explicitly not the current design.
- **Dashboards / external monitoring** (Grafana, etc.) — disproportionate
  infrastructure for a single-server hobby bot; a queryable local SQLite
  file plus an admin Discord command is the right scale.
- **Logging other commands** (`/calc`, `/stats`, `/team`, ...) — these are
  deterministic and don't touch retrieval or an LLM, so there's nothing
  probabilistic to debug; add logging for them only if a real need shows
  up.
