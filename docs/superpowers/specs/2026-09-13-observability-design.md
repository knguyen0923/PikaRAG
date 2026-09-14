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

## Data model

`rag/observability.py`, a small module using Python's stdlib `sqlite3` —
no new dependency, consistent with this project's default toward
zero-cost, zero-new-infrastructure choices. Database at
`data/observability.db` (gitignored, like `data/chroma/`).

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

`ask_response`/`ask_response_async` (`rag/answer.py` / `bot/commands/ask.py`
callers) call `log_ask(...)` once per invocation, after the answer is
produced, wrapped so a logging failure **never** breaks the user-facing
response:

```python
try:
    log_ask(question=question, retrieved_chunks=..., ..., latency_ms=elapsed_ms)
except Exception:
    pass  # observability is best-effort; never blocks the answer
```

## Admin command

`/debug-last` (or similar), restricted to the bot owner (Discord's
`is_owner()` check, matching how other admin-only concerns would
typically be gated in `discord.py`), queries the most recent `ask_log` row
and posts its full detail — question, chunks + distances, gate/degraded
flags, latency, full answer text — for live debugging without needing
shell access to the Oracle Cloud instance.

## Error handling

- Logging failures (disk full, DB locked, etc.) are swallowed, not
  surfaced to the Discord user — observability is a debugging aid, not a
  feature the bot depends on to function.
- `/debug-last` with an empty log table reports that plainly rather than
  erroring.

## Testing plan

- `log_ask`: writes a row with correct fields, given fixed inputs;
  round-trip read confirms JSON fields serialize/deserialize correctly.
- `ask_response`/`ask_response_async`: confirms `log_ask` is called with
  expected arguments (using a fake/spy), and that a raising `log_ask`
  doesn't propagate — the answer still returns normally.
- `/debug-last`: formats a known row correctly; empty-table case handled;
  non-owner invocation is rejected (if using `discord.py`'s built-in owner
  check, this is largely covered by the framework, but the command's own
  logic — e.g. what it does with a found/missing row — still needs direct
  tests).

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
