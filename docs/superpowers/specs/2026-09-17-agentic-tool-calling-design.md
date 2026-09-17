# Agentic /ask + /calc tool-calling loop — design

Source: `IMPROVEMENTS.md` Priority 3. Portfolio-review backlog item — let the
model decide when to call the deterministic damage calculator or pull
stored-team/usage data mid-conversation, while math itself still always
routes through the deterministic calculator, never through the LLM.

## Purpose

Today `/ask` (RAG Q&A) and `/calc` (deterministic damage calculator) are
cleanly separate commands — a good call for correctness, since math should
never go through the LLM. This design adds a third command that lets the
model orchestrate both existing tools plus stored-team lookup, for questions
like "is Landorus a good check to this team?" that need the model to look up
a stored team, run the calculator against each member, and reason over the
results — without the user manually invoking `/calc` per team member.

## Constraints established during brainstorming

- **New command (`/analyze`), not an extension of `/ask`.** `/ask` stays
  exactly as it is — untouched, low-risk, already shipped and tested. The
  agentic loop is opt-in for questions that actually need reasoning over
  team+calc+usage together.
- **Ollama's native tool-calling is used as-is** (`/api/chat`'s `tools`
  param), confirmed supported for `llama3.2:3b` (the model already serving
  `/ask`) — this does not need to be hand-rolled via ReAct-style prompting.
  However, tool-selection reliability on a 3B model is noticeably weaker
  than larger models (higher rate of malformed/hallucinated calls), so
  defensive handling is a first-class part of this design, not an
  afterthought.
- **On a malformed/hallucinated tool call, degrade to a plain RAG answer**
  (retry once via the existing `/ask` context-block path), mirroring the
  already-established `OFFLINE_MESSAGE` degradation pattern, rather than
  surfacing a raw error to the user.
- **Tool set:** damage calculator, stored-team lookup, and usage stats (all
  three) — usage stats wasn't required by the motivating example but was
  approved as a low-cost addition since the wrapper is thin and the data
  already has a clean accessor (`usage_for_record`).
- **Round-trip cap: 4.** Bounds latency/cost on CPU-bound local inference and
  avoids runaway loops on a weaker 3B model. On hitting the cap, force a
  final answer from whatever tool results have been gathered so far, rather
  than erroring.

## Architecture

### New module — `bot/agentic.py`

- `OllamaAnswerer` (in `rag/answer.py`) gains a new method, e.g.
  `answer_with_tools(question, tools, tool_dispatch, max_rounds=4)`,
  alongside its existing single-shot `answer(question, context_block)`. The
  existing method and its callers (`ask_response`/`ask_response_async`) are
  untouched.
- Three tools, each a thin JSON-schema wrapper around an existing pure
  function — no reimplementation of any underlying logic:
  1. **`run_damage_calc`** → `bot/commands/calc.py:calc_response(...)`
     (already a clean, Discord-independent pure function; reused as-is).
  2. **`get_stored_team`** → `bot/team_store.py:get_team(user_id, side)`.
  3. **`get_usage_stats`** → `bot/pokemon_lookup.py:usage_for_record(usage,
     record)`.
- **Loop:** send the question + tool schemas to Ollama via `/api/chat`. If
  the model emits a tool call, dispatch it — `user_id`/`side` are supplied
  by the command handler from the real Discord interaction context, **never
  taken from the model's tool-call arguments**, so a confused or adversarial
  prompt can't spoof whose stored team gets read. Append the tool result as
  a `tool`-role message and repeat, capped at 4 round-trips. On hitting the
  cap, force a final answer from whatever's been gathered (same "answer with
  what you have" shape as a normal RAG context block).

### Failure handling

If the model emits a malformed tool call (bad JSON, unknown tool name, wrong
args) at any point: drop tool-calling for that invocation entirely and retry
once as a plain RAG-style answer through `/ask`'s existing
`build_context_block`/`ask_response` path. This mirrors the existing
`OFFLINE_MESSAGE` degradation pattern (compare failure by structural check,
not by catching exceptions from Ollama, matching `rag/circuit_breaker.py`'s
existing convention) rather than surfacing a raw error.

### Discord integration

`/analyze` defers immediately (`interaction.response.defer()` +
`followup.send()`), the same pattern already used by `/ask` and
`/llmstatus` — multiple tool round-trips make Discord's 3-second ack window
even more certain to be missed than a single Ollama call already is.

### Correctness boundary (preserved from `/calc`)

The model never computes damage itself. It only ever sees
`run_damage_calc`'s deterministic string output and reasons over that text —
matching the existing "math should never go through the LLM" principle
`/calc` already established. This is the one invariant this design must not
weaken under any failure path.

## Testing

- Unit tests per tool wrapper: schema shape is well-formed, dispatch reaches
  the correct underlying pure function with the right arguments.
- A test for the round-trip cap: confirm a final answer is forced (not an
  infinite loop or an error) once 4 rounds are reached.
- A test for the malformed-tool-call fallback: confirm it degrades to a
  plain RAG answer rather than raising or timing out.
- Mock Ollama's `/api/chat` responses, the same way existing
  `OllamaAnswerer` tests already do — no live-model dependency in the test
  suite.

## Out of scope

- Persisting conversation state across multiple `/analyze` invocations —
  each call is single-turn from the user's side, even though it may involve
  multiple tool round-trips internally.
- Adding tools beyond the three listed above.
- Any change to `/ask`'s or `/calc`'s existing behavior.
