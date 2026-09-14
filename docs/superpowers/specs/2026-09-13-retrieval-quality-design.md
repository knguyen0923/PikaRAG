# Pika-RAG: Retrieval Quality — Design

Status: Approved
Date: 2026-09-13

## Purpose

Pure vector search (the entire retrieval mechanism today, `rag/store.py`'s
`ChromaIndex.query`) is unreliable for the most common real question shape:
"tell me about `<exact Pokemon/item name>`." Embedding similarity is a poor
tool for exact-entity lookup — a misretrieved neighbor silently degrades
answer quality, and matters more now that a small local model
([[local-llm-migration]]) can't compensate for noisy context as well as
Haiku could.

## Scope

In scope:
- Entity-aware retrieval: detect a known Pokemon/item name in the question
  and constrain/boost Chroma results to that entity's chunks.
- Fallback to today's pure vector search when no entity is detected or
  recognized.

Out of scope (see "Out of scope" section for detail):
- BM25/hybrid search as a general mechanism.
- Chunking-granularity changes.
- Query rewriting/expansion for multi-turn follow-ups.

## Approach

The project already has fuzzy name matching for exactly this vocabulary —
`bot/pokemon_lookup.py`'s `find_record`/`suggest_names`, built for
`/import`/`/scout` typo tolerance. Retrieval reuses the same matching
against both Pokemon names (`pokemon_records`) and item names
(`vgc_items`), rather than introducing a second matching mechanism (e.g.
`rank_bm25`) for a fixed, already-known, small vocabulary. This keeps the
"hand-rolled, understand every piece" approach the project has used
throughout ([[TAKEAWAYS]] retrospective) and adds no new dependency.

`rag/retrieve.py`'s `build_context_block` gains an entity-detection step
before querying:

```python
def build_context_block(index, question: str, n_results: int = 5) -> str:
    entity = detect_entity(question)  # new: rag/entity.py
    if entity:
        matches = index.query(question, n_results=n_results, where={entity["field"]: entity["name"]})
    else:
        matches = index.query(question, n_results=n_results)
    return "\n".join(match["text"] for match in matches)
```

`detect_entity(question)` scans the question's tokens/substrings against
known Pokemon and item names (reusing `find_record`'s matching logic,
factored out so both call sites share it), returning
`{"field": "pokemon", "name": "Landorus-Therian"}` or the `item` equivalent,
or `None` if nothing recognized. `ChromaIndex.query` gains an optional
`where` parameter, passed straight through to Chroma's own metadata-filter
support (already storing `pokemon`/`item` in each chunk's metadata per
`rag/embed.py`) — no schema change needed, the filterable fields already
exist.

When an entity is detected but yields zero results (e.g. filtered chunks
don't actually contain the answer — shouldn't happen given chunking, but
defensively), fall back to the unfiltered query rather than returning
nothing.

## Error handling

- Ambiguous detection (question plausibly matches two different known
  names) is not specially handled — falls through to unfiltered vector
  search, same as "no entity detected." Precision here isn't worth the
  complexity of a disambiguation step for a assistant answering casual
  Discord questions.
- `where`-filtered query returning nothing falls back to unfiltered, as
  above — never returns an empty context block when a broader search might
  have found something.

## Testing plan

- `rag/entity.py` (`detect_entity`): unit tests — exact name, fuzzy/typo
  name (reusing existing `suggest_names` fixtures), no match, item vs
  Pokemon disambiguation, question with no recognizable entity at all.
- `ChromaIndex.query`'s new `where` parameter: unit test confirming it's
  passed to the underlying Chroma call and narrows results against a small
  fixture collection.
- `build_context_block`: test that a detected entity narrows the query,
  and that detection failure/empty-filtered-result falls back to
  unfiltered search.
- Regression check via the eval harness ([[eval-harness]]): recall@k on
  the subset of golden questions that name a specific Pokemon/item should
  visibly improve versus the pre-change baseline — worth running once both
  specs are implemented.

## Out of scope

- **BM25/hybrid search** — the corpus is small and the vocabulary (Pokemon
  and item names) is fixed and already has fuzzy matching built for it
  elsewhere in the project; a general lexical-search layer would solve a
  problem the existing name matcher already covers more simply. Revisit
  only if free-text (non-entity) retrieval quality turns out to be the
  actual bottleneck once the eval harness has real numbers.
- **Chunking-granularity changes** — entity filtering already narrows
  results to the right species/item; the existing stats/moveset/item split
  isn't the bottleneck this spec addresses.
- **Query rewriting for follow-ups** ("what about its Speed?" referring to
  the previous message's Pokemon) — a real gap, but a separate,
  conversation-state-dependent feature, not a retrieval-mechanism change.
