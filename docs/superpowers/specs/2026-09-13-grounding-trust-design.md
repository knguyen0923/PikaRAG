# Pika-RAG: Grounding & Trust — Design

Status: Approved
Date: 2026-09-13

## Purpose

Today's `/ask` gives no way to tell *why* it said something — no visible
source, no signal of low confidence beyond the model's own (now weaker,
[[local-llm-migration]]) judgment about when to say "I don't know." This
makes a wrong answer indistinguishable from a right one until a user
happens to know better. This spec adds source attribution and a
retrieval-based confidence gate so bad answers are visible and, in the
clearest cases, prevented from reaching the LLM at all.

## Scope

In scope:
- Source attribution: every `/ask` response names which chunks (Pokemon/
  item + chunk type) fed the answer.
- A confidence gate based on retrieval distance: when the best match is
  clearly too far, skip the LLM call and say so directly.

Out of scope (see "Out of scope" section for detail):
- Per-sentence/fine-grained citation (which chunk supports which claim).
- A learned/calibrated confidence model.
- Surfacing raw distance scores to end users.

## Source attribution

`build_context_block` (`rag/retrieve.py`) already discards each match's
identity once it concatenates `match["text"]`. It changes to return
structured data instead of a bare string:

```python
def build_context_block(index, question: str, n_results: int = 5) -> dict:
    matches = index.query(question, n_results=n_results)  # entity-aware if [[retrieval-quality]] lands first
    return {
        "text": "\n".join(m["text"] for m in matches),
        "sources": [{"name": m["metadata"].get("pokemon") or m["metadata"].get("item"),
                     "chunk_type": m["metadata"]["chunk_type"]} for m in matches],
        "best_distance": min((m["distance"] for m in matches), default=None),
    }
```

`ask_response` threads `sources` through to the caller instead of just the
answer text; `bot/commands/ask.py` formats them as a compact trailing line:

```
Landorus-Therian has base 91 Speed...

Sources: Landorus-Therian (stats)
```

This is an additive, visible change to `ask_response`'s return shape —
callers that only cared about the answer text need a one-line update to
read `.answer` instead of treating the return as a bare string. This is
**not** automatically caught by the existing test suite: the only test
exercising `/ask` end-to-end, `test_ask_command_includes_stored_team_context`
(`tests/test_bot_main.py`), never inspects the sent embed's text content,
and `discord.Embed(description=<a dict>, ...)` does not raise — it silently
stringifies the dict via `str()`, producing garbage like
`"{'answer': 'hi', 'sources': []}"` shown directly to real Discord users.
`bot/main.py`'s `ask` command handler (around line 63-72) is the actual
integration point that must be explicitly updated: it currently does
`answer = await ask_response_async(...)` then
`await interaction.followup.send(embed=_embed("ask", answer))`, passing
whatever `ask_response_async` returns straight into embed construction.
This spec touches `bot/main.py` in addition to `bot/commands/ask.py`
(which formats the sources line) — `bot/main.py`'s embed-construction call
must change to read the new `.answer`/`.sources` shape rather than
assuming a bare string, and a new test must be added asserting the sent
embed's content reflects the sources line correctly, since no existing
test does this.

## Return shape contract

`ask_response`'s return type is consistently a dict/small structure of the
shape `{"answer": str, "sources": list[str]}` (or equivalent) across all
three possible outcomes, never a bare string:

1. **Normal**: answer text plus a non-empty `sources` list, built from
   `build_context_block`'s `sources` as described above.
2. **Gate-fired**: confidence too low, including the empty-matches
   (`best_distance is None`) case from the Confidence gate section below.
   No LLM call happens; `answer` is the fixed low-confidence message and
   `sources` is an empty list.
3. **Offline-degraded**: `OllamaAnswerer.answer()` itself returned its
   `OFFLINE_MESSAGE` constant (`rag/answer.py`) because the Ollama call
   failed. This is orthogonal to the confidence gate — the gate passed and
   the LLM was called, but the call itself failed. `answer` is
   `OllamaAnswerer`'s `OFFLINE_MESSAGE` string and `sources` is an empty
   list — wrapped in the same dict shape as the other two cases, not
   returned as a bare string.

Keeping all three cases in one consistent shape means `bot/main.py`'s
embed construction (see "Source attribution" above) only ever has to
handle one shape, with no bare-string special case to remember.

## Confidence gate

Using `best_distance` from above: if it exceeds a fixed threshold, **or if
`best_distance` is `None`** (matches was empty — an empty/newly-created
collection, or Chroma returning fewer than `n_results`), skip the Ollama
call entirely and return a fixed "I don't have solid information on that"
response with no sources line. The `None` case is treated the same as
exceeding the threshold: no sources, insufficient confidence, gate fires.
Gate logic must check for `None` explicitly before any numeric comparison
(e.g. `best_distance is None or best_distance > threshold`) — comparing
`None > threshold` directly raises `TypeError`.

The threshold itself should start at a value tuned empirically against the
eval harness's golden set ([[eval-harness]]), since "too far" only means
something relative to this project's actual embedding space. However,
neither `eval/generate_golden_set.py` nor `data/eval/golden_set.json`
exist yet — [[eval-harness]] is itself only a design spec, not an
implemented one. Threshold tuning against the golden set should therefore
happen only after [[eval-harness]] is implemented and a real golden set
exists. In the meantime, ship with a conservative placeholder threshold,
chosen to err toward gating (fewer, more-confident answers) rather than
under-gating, and revisit once real tuning data is available.

This is deliberately a hard-coded numeric threshold, not a learned
classifier — the corpus is small and static enough that empirical tuning
against the golden set is sufficient, and a second model call to "judge
confidence" would cost CPU time on the same constrained laptop for
marginal benefit.

Rationale for gating before the LLM rather than trusting the system
prompt's existing "say you don't know" instruction alone: a 3B model
follows that instruction less reliably than Haiku did, so a mechanical
check independent of the model's own judgment is worth having as a
backstop.

## Error handling

- No sources to report — `matches` can legitimately be empty (an empty or
  newly-created collection, or Chroma returning fewer than `n_results`);
  this is not a rare edge case but an already-tested one (`_FakeIndex.query`
  returning `[]` exists in `tests/test_bot_main.py`). It is handled by an
  empty `sources` list, and `best_distance is None` explicitly routes
  through the confidence gate's "gate fires" path (see "Confidence gate"
  above) rather than crashing on a `None > threshold` comparison. Once
  routed there, formatting code omits the "Sources:" line entirely rather
  than printing it empty.
- The confidence gate firing (for either reason: over-threshold or
  `best_distance is None`) is not treated as an error — it's a normal,
  logged (see [[observability]]) response path, distinct from the
  `OllamaAnswerer` "offline" degradation message.

## Testing plan

- `build_context_block`: returns correct `text`/`sources`/`best_distance`
  structure against a fake index with known distances/metadata, including
  a case where the fake index's `query` returns an empty list (mirroring
  `_FakeIndex.query` in `tests/test_bot_main.py`), asserting
  `best_distance` comes back `None` rather than raising.
- `ask_response`: sources pass through unchanged to the caller; existing
  tests updated for the new return shape (one-line change per call site);
  a test for each of the three outcomes in "Return shape contract" above
  (normal, gate-fired, offline-degraded) asserting the returned dict has
  the expected `answer`/`sources` shape in every case.
- Confidence gate: unit tests for below-threshold (normal path, LLM
  called), above-threshold (gate fires, LLM never called — assert the
  fake answerer's `.answer` was not invoked), and `best_distance is None`
  from empty matches (gate fires the same way, LLM never called, no
  `TypeError` raised).
- `bot/commands/ask.py` formatting: sources line present/absent as
  expected, gate-triggered response formatted without a sources line.
- `bot/main.py`'s `ask` command handler: a new test asserting the embed
  sent via `interaction.followup.send` reads the `.answer`/`.sources`
  shape correctly and reflects the sources line as expected, rather than
  stringifying the whole returned structure — guarding against the
  silent-embed-stringification failure mode described in "Source
  attribution" above.

## Out of scope

- **Per-sentence citation** — attributing individual claims within a
  multi-sentence answer to specific chunks would need the LLM to emit
  structured citations itself (much larger prompt-engineering lift for a
  3B model that already struggles with simpler instructions); chunk-level
  attribution is the right granularity for this corpus's chunk sizes
  (roughly one chunk = one fact).
- **A learned confidence model** — a fixed, empirically-tuned distance
  threshold is proportionate to a static, small corpus; revisit only if
  the golden set shows the simple threshold isn't discriminating well.
- **Raw distance scores in the user-facing response** — meaningless to a
  Discord user without embedding-space context; the chunk names/types are
  the useful signal, the number itself belongs in the observability log
  ([[observability]]), not the reply.
