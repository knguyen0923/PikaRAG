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
callers (and their existing tests) that only cared about the answer text
need a one-line update to read `.answer` instead of treating the return as
a bare string; not a silent breaking change since it's caught immediately
by the existing test suite.

## Confidence gate

Using `best_distance` from above: if it exceeds a fixed threshold (start at
a value tuned empirically against the eval harness's golden set —
[[eval-harness]] — since "too far" only means something relative to this
project's actual embedding space), skip the Ollama call entirely and
return a fixed "I don't have solid information on that" response with no
sources line. This is deliberately a hard-coded numeric threshold, not a
learned classifier — the corpus is small and static enough that empirical
tuning against the golden set is sufficient, and a second model call to
"judge confidence" would cost CPU time on the same constrained laptop for
marginal benefit.

Rationale for gating before the LLM rather than trusting the system
prompt's existing "say you don't know" instruction alone: a 3B model
follows that instruction less reliably than Haiku did, so a mechanical
check independent of the model's own judgment is worth having as a
backstop.

## Error handling

- No sources to report (shouldn't happen — `n_results` is always >0 when
  the collection is non-empty) is handled by an empty `sources` list;
  formatting code omits the "Sources:" line entirely rather than printing
  it empty.
- The confidence gate firing is not treated as an error — it's a normal,
  logged (see [[observability]]) response path, distinct from the
  `OllamaAnswerer` "offline" degradation message.

## Testing plan

- `build_context_block`: returns correct `text`/`sources`/`best_distance`
  structure against a fake index with known distances/metadata.
- `ask_response`: sources pass through unchanged to the caller; existing
  tests updated for the new return shape (one-line change per call site).
- Confidence gate: unit tests for below-threshold (normal path, LLM
  called) and above-threshold (gate fires, LLM never called — assert the
  fake answerer's `.answer` was not invoked).
- `bot/commands/ask.py` formatting: sources line present/absent as
  expected, gate-triggered response formatted without a sources line.

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
