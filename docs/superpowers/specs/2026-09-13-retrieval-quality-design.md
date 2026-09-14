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

This isn't hypothetical — the eval harness ([[eval-harness]]) measured it
directly. Two of the 48 golden questions miss their target chunk entirely:
`Does Abomasnow learn Attract?` and `Does Dragalge learn Accelerock?` both
fail to retrieve the Pokemon's own `-moveset` chunk in the top 5, even
though the moveset chunk literally contains the answer. Root-caused by
querying the real index directly: for every sampled Pokemon that also has
a Mega Stone item (Abomasnow, Dragalge, Kangaskhan, Medicham — 4 of the
golden set's 12), the top two results are *always* `item-<Name>ite`
("A held item that allows `<Name>` to Mega Evolve.") and `<Name>-stats`,
in that order, regardless of the question — `all-MiniLM-L6-v2`'s
mean-pooled embedding favors a short, clean sentence repeating the exact
Pokemon name over the long, diluted move-list text in the moveset chunk.
Kangaskhan and Medicham still happened to squeak into the top 5 (rank 4-5);
Abomasnow and Dragalge didn't (rank 6+). This is exactly the failure mode
entity-aware filtering below eliminates: a `where={"pokemon": "Abomasnow"}`
query only has Abomasnow's own 2 chunks to rank between — the Mega Stone's
`item-Abomasite` chunk carries `metadata={"item": ...}`, not `"pokemon"`,
so it's excluded from the filtered query entirely, not just outranked.

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
`/import`/`/scout` typo tolerance. Both functions require an
already-isolated candidate name string: `find_record(records, name)`
(bot/pokemon_lookup.py:4-16) does case-insensitive exact-string equality
against `name`, and `suggest_names` does fuzzy nearest-match against the
same kind of already-isolated string. Neither has any logic to scan an
arbitrary free-text sentence for an embedded candidate name — that
extraction step doesn't exist yet.

So `detect_entity` needs two steps, only the second of which is reuse:

1. **Scan** the question's tokens/substrings for a match against the known
   Pokemon/item name vocabulary. This is genuinely new code — there's
   nothing in `bot/pokemon_lookup.py` to lean on here.
2. **Resolve** a candidate substring found in step 1 against the
   known-names list, confirming/normalizing it to the record's canonical
   name. This step can reuse `find_record`/`suggest_names` as-is, since by
   this point the candidate is already isolated — exactly the precondition
   those functions expect.

Framed this way, retrieval doesn't introduce a second matching mechanism
(e.g. `rank_bm25`) for a fixed, already-known, small vocabulary — the new
part is only the scanning step, not the name-matching itself. This keeps
the "hand-rolled, understand every piece" approach the project has used
throughout ([[TAKEAWAYS]] retrospective) and adds no new dependency.

`rag/retrieve.py`'s `build_context_block` gains an entity-detection step
before querying. It needs the known-names vocabulary to detect against, so
its signature grows to accept `records: list[dict]` and `items: list[dict]`
— the same lists `bot/main.py`'s `main()` already loads via `_load_records()`
and `_load_items()` (around line 243-244) and already passes to other
command handlers like `/stats`/`/moves`. Rather than have `rag/entity.py`
independently re-load/duplicate those data files, the loaded lists are
threaded through the existing call chain: `bot/main.py`'s `ask` command
handler (around line 63-72) passes `records`/`items` to `ask_response`/
`ask_response_async` (`bot/commands/ask.py`), which pass them on to
`build_context_block`:

```python
def build_context_block(
    index, question: str, records: list[dict], items: list[dict], n_results: int = 5
) -> str:
    entity = detect_entity(question, records, items)  # new: rag/entity.py
    if entity:
        matches = index.query(question, n_results=n_results, where={entity["field"]: entity["name"]})
    else:
        matches = index.query(question, n_results=n_results)
    return "\n".join(match["text"] for match in matches)
```

`detect_entity(question, records, items)` scans the question's
tokens/substrings for a known Pokemon or item name (new logic — see
"Approach" above), then resolves a found candidate against `records`/
`items` (reusing `find_record`'s matching logic, factored out so both call
sites share it), returning `{"field": "pokemon", "name": "Kommo-o"}` or the
`item` equivalent, or `None` if nothing recognized. `ChromaIndex.query`
gains an optional `where` parameter, passed straight through to Chroma's
own metadata-filter support (already storing `pokemon`/`item` in each
chunk's metadata per `rag/embed.py`) — no schema change needed, the
filterable fields already exist.

When an entity is detected but yields zero results (e.g. filtered chunks
don't actually contain the answer — shouldn't happen given chunking, but
defensively), fall back to the unfiltered query rather than returning
nothing.

## Error handling

- **Form-variant tie-breaking.** A plain substring scan would be
  ambiguous far more often than "two unrelated names collide" suggests:
  `data/processed/pokemon_records.json` has roughly a third of its 345
  records as a compound form-variant name that contains its base species
  name as a substring (e.g. `"Abomasnow"` / `"Mega Abomasnow"`,
  `"Arcanine"` / `"Arcanine [Hisuian Form]"`). A question mentioning plain
  "Abomasnow" would otherwise ambiguously match both records. `detect_entity`
  resolves this with explicit tie-breaking before falling back to
  unfiltered search:
  - Prefer an exact full-token match over a substring match.
  - Only match a form-variant (Mega/regional/other bracketed form) if the
    question's text also contains that form's qualifying word
    (case-insensitive) — e.g. "mega", "hisuian", "alolan", "galarian", or
    the bracketed form text itself.
  - Otherwise, when a plain species name is mentioned with no form
    qualifier, prefer the base form.
- **Remaining ambiguity.** This tie-breaking doesn't resolve every case —
  the roster has a confirmed instance where two form-variants collide with
  each other: `"Mega Absol"` and `"Mega Absol Z"` both contain "mega absol"
  and both satisfy the "mega" qualifier check, so a question saying "mega
  absol" without further qualification is genuinely ambiguous between them
  (similarly, "mega charizard" alone doesn't distinguish `"Mega Charizard
  X"` from `"Mega Charizard Y"`). Only in cases like this — genuine
  ambiguity that survives the tie-breaking above — does detection fall
  through to unfiltered vector search, same as "no entity detected."
  Precision beyond this isn't worth further complexity for an assistant
  answering casual Discord questions.
- `where`-filtered query returning nothing falls back to unfiltered, as
  above — never returns an empty context block when a broader search might
  have found something.

## Testing plan

- `rag/entity.py` (`detect_entity`): unit tests — exact name, fuzzy/typo
  name (reusing existing `suggest_names` fixtures), no match, item vs
  Pokemon disambiguation, question with no recognizable entity at all.
- Form-variant tie-breaking: a question naming a plain species that also
  has a Mega/regional-form record (e.g. "Abomasnow") resolves to the base
  form, not the variant; a question naming the species with a form
  qualifier (e.g. "Mega Abomasnow") resolves to the variant; a question
  hitting genuine remaining ambiguity (e.g. "Mega Absol" vs "Mega Absol Z")
  falls through to unfiltered search.
- `ChromaIndex.query`'s new `where` parameter: unit test confirming it's
  passed to the underlying Chroma call and narrows results against a small
  fixture collection.
- `build_context_block`: test that, given `records`/`items` fixtures, a
  detected entity narrows the query, and that detection failure/
  empty-filtered-result falls back to unfiltered search.
- Regression check via the eval harness ([[eval-harness]]): recall@k on
  the subset of golden questions that name a specific Pokemon/item should
  visibly improve versus the pre-change baseline (measured 0.9583, 46/48,
  at implementation time) — worth running once both specs are implemented.
  `Abomasnow-moveset-learned-question` and
  `Dragalge-moveset-not-learned-question` (`data/eval/golden_set.json`) are
  the two known current misses this spec exists to fix — confirm both flip
  to hits, not just that the aggregate score goes up.

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
