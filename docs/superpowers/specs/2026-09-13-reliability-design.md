# Pika-RAG: Reliability — Design

Status: Approved
Date: 2026-09-13

## Purpose

[[local-llm-migration]]'s error handling already turns a laptop-unreachable
`/ask` into a friendly "offline" message instead of a crash — that's the
floor. This spec builds on it: avoid every concurrent `/ask` paying a full
30-second timeout when the laptop is *known* to be down, and give the bot
owner a fast way to check laptop health without waiting on a real question.

## Scope

In scope:
- A circuit breaker around `OllamaAnswerer` calls: after repeated failures,
  short-circuit immediately instead of retrying the network call.
- A lightweight admin health-check command independent of `/ask`.

Out of scope (see "Out of scope" section for detail):
- Automatic retries with backoff on transient (non-consecutive) failures.
- Any reliability work for `/calc`, `/stats`, `/moves`, `/team` — these
  don't call the network at all and have no equivalent failure mode.

## Circuit breaker

A small state machine wrapping `OllamaAnswerer.answer`, in
`rag/circuit_breaker.py`:

- **Closed** (normal): calls pass through. Each failure increments a
  counter; each success resets it to zero.
- **Open** (tripped): after 3 consecutive failures, the breaker opens —
  further calls skip the network entirely and return the "offline" message
  immediately, for a 60-second cooldown. This is the actual payoff: instead
  of N concurrent users each waiting out a 30s timeout against a laptop
  that's plainly down, only the first 3 pay that cost.
- **Half-open** (probing): once the cooldown elapses, the next call is
  allowed through for real. Success closes the breaker (back to normal);
  failure reopens it for another cooldown period.

Thresholds (3 failures, 60s cooldown) are reasonable starting defaults, not
load-tested values — this bot serves a single small Discord server at low
query volume, so precision here matters less than having the mechanism at
all. Adjust if real usage shows the numbers wrong.

`OllamaAnswerer.answer` (`rag/answer.py:27-46`) already catches every
network/parsing failure internally (`requests.RequestException`, `KeyError`,
`TypeError`) and returns the fixed string `OFFLINE_MESSAGE` — it never
raises for the "laptop unreachable" case the breaker exists to protect
against, so a breaker watching for exceptions would see nothing during a
real outage. The breaker therefore detects failure by value, not by
exception: it calls the wrapped `.answer(question, context_block)`
normally, then compares the returned string against `OFFLINE_MESSAGE`
(imported from `rag.answer`) — that equality check *is* the failure
signal.

`OllamaAnswerer` itself doesn't change — its interface and internal
exception handling stay exactly as they are; the breaker wraps it at
construction time in `bot/main.py` (decorator/composition, matching the
project's existing preference for small composable pieces over modifying
an existing class's internals) and layers its own return-value check on
top.

## Health-check command

`/llmstatus` is admin-only via a hardcoded Discord user ID: a `BOT_OWNER_ID`
environment variable (documented in `.env.example`, following the same
pattern as `DISCORD_TOKEN` and `LLM_HOST`), checked with
`interaction.user.id == int(os.environ["BOT_OWNER_ID"])` inside an
`app_commands.check` (or equivalent) gating the command. This bot uses a
plain `discord.Client` (see `bot/main.py`), not `commands.Bot`, so there is
no built-in `is_owner()` helper available — the env-var comparison is the
whole mechanism. It also carries the same
`@app_commands.checks.cooldown(1, _COOLDOWN_SECONDS)` decorator (the
constant already defined in `bot/main.py`) as every other command in the
file, for consistency.

The command sends a short-timeout (e.g. 3s) request to Ollama's own
`/api/tags` endpoint (lists loaded models — a cheap liveness probe that
doesn't run inference) and reports up/down plus which model is currently
loaded. Also reports the circuit breaker's current state
(closed/open/half-open) so "is it actually down, or just tripped and
cooling down" is answerable at a glance.

## Error handling

- The circuit breaker's own state transitions are the error-handling
  mechanism here; nothing new to add on top beyond what
  [[local-llm-migration]] already specified for the underlying call
  failing.
- `/llmstatus`'s own health-check request failing (laptop down) is not an
  error state for the command itself — it's the expected "down" result,
  reported plainly.

## Testing plan

- Circuit breaker state machine: unit tests for closed→open (3 failures),
  open short-circuits without calling the wrapped function, open→half-open
  after cooldown elapses (inject a fake clock rather than sleeping in
  tests), half-open→closed on success, half-open→open on failure. "Failure"
  in these tests means the wrapped fake returns `OFFLINE_MESSAGE`, not that
  it raises — a case that returns any other string must be treated as
  success even if the fake's setup looks failure-like, confirming the
  breaker keys off the sentinel string rather than exceptions.
- `/llmstatus`: up case, down case, and breaker-state reporting, all with
  a fake HTTP client — no real network calls in tests. Also cover the
  `BOT_OWNER_ID` gate itself: an interaction from the owner's user ID is
  allowed through, and one from any other user ID is rejected before the
  health-check request is made.

## Out of scope

- **Retries with backoff on transient failures** — a single dropped
  request isn't distinguished from a real outage in this design; the
  circuit breaker's consecutive-failure count already absorbs occasional
  one-off blips without needing a separate retry layer, and adding one
  would mean two separate policies effectively doing similar jobs.
- **Reliability work for other commands** — `/calc`, `/stats`, `/moves`,
  `/team` are pure-Python/deterministic, no network dependency, nothing
  for a circuit breaker or health check to protect.
