# Hybrid BM25+Vector Retrieval Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add keyword (BM25) search alongside the existing vector search for `/ask`'s unfiltered/fallback retrieval path, fusing the two via Reciprocal Rank Fusion (RRF) so exact keyword matches (e.g. an ability name that appears verbatim in a chunk) aren't lost to semantic drift in the embedding space.

**Architecture:** A new `rag/bm25.py` module builds an in-memory `BM25Okapi` index once, over the same chunk texts (`rag/embed.py`'s `build_chunks`/`build_item_chunks`) that seed the Chroma vector index. `rag/retrieve.py`'s `build_context_block` gains an optional `bm25_index` parameter; when given, the two currently-unfiltered code paths (no entity detected; entity-filtered query came back empty) fetch a wider candidate pool from both the vector index and the BM25 index and fuse them by rank via RRF instead of calling `index.query` alone. When `bm25_index` is omitted (the default, and what every existing test does), behavior is byte-identical to today — this is purely additive. The real bot wires a real `BM25Index` through `bot/main.py` → `bot/commands/ask.py` → `rag/retrieve.py`.

**Tech Stack:** `rank_bm25` (new pinned dependency), existing `rag/embed.py`/`rag/store.py`/`rag/entity.py`.

**Spec:** No separate spec file — bounded design approved in chat 2026-09-17, recorded in `IMPROVEMENTS.md`'s "Hybrid BM25+vector retrieval" bullet: *"replace the unfiltered fallback path in `rag/retrieve.py`'s `build_context_block` with Reciprocal Rank Fusion over BM25 (`rank_bm25`, in-memory, 887 chunks) + the existing vector query; add 3-5 new golden-set entries targeting the no-entity-detected gap the golden set doesn't currently cover (current recall@5 is already 1.0, so new eval cases are needed to actually demonstrate the benefit)."*

## Global Constraints

- New dependency `rank_bm25` must be pinned in `requirements.txt` with a preceding explanatory comment (enforced by `scripts/check_pinned_deps.py` in CI) — confirmed installable version: `0.2.2`.
- Every existing test in `tests/test_rag_retrieve.py`, `tests/test_bot_ask.py`, `tests/test_bot_main.py`, and `tests/test_eval_retrieval.py` must keep passing unchanged — the hybrid path only activates when a `bm25_index` is explicitly passed in, which none of today's call sites/tests do until this plan wires them.
- `best_distance` (drives `bot/commands/ask.py`'s `DISTANCE_THRESHOLD` confidence gate) must never become artificially *better* (lower) because of a BM25-only hit that has no real vector distance — a BM25-only chunk gets a pessimistic filler distance (the worst real vector distance observed in that query's candidate pool, or `float("inf")` if the vector pool was empty), never a fabricated good one.
- Do not touch the entity-filtered query path (`where={...}`) — this plan only changes the two branches that currently call `index.query` with no `where` filter.

---

## File Structure

- Create: `rag/bm25.py` — `BM25Index` class (builds the in-memory keyword index from records/items, exposes `.search(question, n_results)`).
- Create: `tests/test_rag_bm25.py` — unit tests for `BM25Index`.
- Modify: `rag/retrieve.py` — add `_hybrid_matches` helper (RRF fusion) and thread an optional `bm25_index` param through `build_context_block`.
- Modify: `tests/test_rag_retrieve.py` — add new tests for the hybrid path (existing tests untouched).
- Modify: `bot/commands/ask.py` — thread `bm25_index` through `ask_response`/`ask_response_async`.
- Modify: `tests/test_bot_ask.py` — add tests proving `bm25_index` is passed through to `build_context_block`.
- Modify: `bot/main.py` — `build_client` gains a `bm25_index` param passed into the `/ask` handler's `ask_response_async` call; `main()` constructs a real `BM25Index` from the loaded records/items and passes it to `build_client`.
- Modify: `tests/test_bot_main.py` — add a test proving the `/ask` handler forwards `bm25_index` to `ask_response_async`.
- Modify: `data/eval/golden_set.json` — add 4 new entries whose questions deliberately don't name a known Pokemon/item, so `detect_entity` returns `None` and they exercise the (previously untested) unfiltered/hybrid path.
- Modify: `tests/test_eval_retrieval.py` — add a regression test proving hybrid retrieval recovers a real, currently-failing golden entry (`Aegislash-stats`) that pure vector search misses at k=5.
- Modify: `requirements.txt` — pin `rank_bm25==0.2.2`.

---

### Task 1: Pin the `rank_bm25` dependency

**Files:**
- Modify: `requirements.txt`
- Test: `tests/test_check_pinned_deps.py` (existing test, run only — no new test needed, it already validates every pinned line generically)

**Interfaces:**
- Produces: `rank_bm25` importable as `from rank_bm25 import BM25Okapi`, used by Task 2.

- [ ] **Step 1: Add the pin**

Append to `requirements.txt`:

```
# Added for hybrid BM25+vector retrieval (rag/bm25.py) -- confirmed
# importable and installable at this exact version.
rank_bm25==0.2.2
```

- [ ] **Step 2: Install it**

Run: `pip install rank_bm25==0.2.2`
Expected: installs cleanly (pure-Python package, no compiled extensions).

- [ ] **Step 3: Run the pinned-deps CI check**

Run: `python -m pytest tests/test_check_pinned_deps.py -v`
Expected: PASS (the new pin has a preceding comment, satisfying the check).

- [ ] **Step 4: Commit**

```bash
git add requirements.txt
git commit -m "build: pin rank_bm25 for hybrid retrieval" -m "$(printf 'Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>')"
```

---

### Task 2: `BM25Index` — in-memory keyword index

**Files:**
- Create: `rag/bm25.py`
- Test: `tests/test_rag_bm25.py`

**Interfaces:**
- Consumes: `rag.embed.build_chunks(record: dict) -> list[dict]`, `rag.embed.build_item_chunks(item: dict) -> list[dict]` (each chunk dict has `id`, `text`, plus metadata keys like `pokemon`/`item`/`chunk_type`) — both already exist, unchanged.
- Produces: `BM25Index(records: list[dict], items: Optional[list[dict]] = None)` with `.search(question: str, n_results: int = 10) -> list[dict]`, where each returned item is a chunk dict (`id`, `text`, plus metadata keys) ranked by BM25 score descending, score-zero results excluded. Used by Task 3's `_hybrid_matches`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_rag_bm25.py`:

```python
from rag.bm25 import BM25Index

_ABOMASNOW = {
    "name": "Abomasnow",
    "types": ["Grass", "Ice"],
    "base_stats": {"hp": 90, "attack": 92, "defense": 75, "sp_attack": 92, "sp_defense": 85, "speed": 60},
    "abilities": ["Snow Warning", "Soundproof"],
    "learnset": ["Blizzard", "Wood Hammer"],
}
_GYARADOS = {
    "name": "Gyarados",
    "types": ["Water", "Flying"],
    "base_stats": {"hp": 95, "attack": 125, "defense": 79, "sp_attack": 60, "sp_defense": 100, "speed": 81},
    "abilities": ["Intimidate"],
    "learnset": ["Waterfall", "Dragon Dance"],
}
_LIFE_ORB = {"name": "Life Orb", "description": "Boosts the power of moves, but the holder loses HP with each hit."}


def test_search_finds_the_chunk_containing_the_exact_keyword_phrase():
    index = BM25Index([_ABOMASNOW, _GYARADOS])

    results = index.search("Which Pokemon has the Snow Warning ability?", n_results=5)

    assert any(r["id"] == "Abomasnow-stats" for r in results)


def test_search_ranks_the_exact_keyword_match_first():
    index = BM25Index([_ABOMASNOW, _GYARADOS])

    results = index.search("Snow Warning ability", n_results=5)

    assert results[0]["id"] == "Abomasnow-stats"


def test_search_includes_item_chunks_when_items_are_given():
    index = BM25Index([_ABOMASNOW], items=[_LIFE_ORB])

    results = index.search("Life Orb power boost", n_results=5)

    assert any(r["id"] == "item-Life Orb" for r in results)


def test_search_excludes_zero_score_chunks():
    index = BM25Index([_ABOMASNOW, _GYARADOS])

    results = index.search("completely unrelated words nowhere in the corpus", n_results=5)

    assert results == []


def test_search_returns_chunk_dicts_with_text_and_metadata():
    index = BM25Index([_ABOMASNOW])

    results = index.search("Snow Warning", n_results=5)

    assert results[0]["text"].startswith("Abomasnow is a Grass/Ice-type Pokemon")
    assert results[0]["pokemon"] == "Abomasnow"
    assert results[0]["chunk_type"] == "stats"


def test_search_respects_n_results():
    index = BM25Index([_ABOMASNOW, _GYARADOS])

    results = index.search("Pokemon", n_results=1)

    assert len(results) <= 1


def test_empty_records_and_items_produces_an_empty_index():
    index = BM25Index([], items=[])

    assert index.search("anything", n_results=5) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_rag_bm25.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'rag.bm25'`

- [ ] **Step 3: Write the implementation**

Create `rag/bm25.py`:

```python
import re
from typing import Optional

from rank_bm25 import BM25Okapi

from rag.embed import build_chunks, build_item_chunks


def _tokenize(text: str) -> list:
    return re.findall(r"[a-z0-9]+", text.lower())


class BM25Index:
    """In-memory keyword (BM25) index over the same chunk texts embedded
    into the vector index, built once from the raw records/items (same
    build_chunks/build_item_chunks used by rag/store.py's ChromaIndex.build)
    -- used by rag/retrieve.py's hybrid fallback path so an exact keyword
    match (e.g. an ability name present verbatim in a chunk) isn't lost to
    semantic drift in the embedding space.
    """

    def __init__(self, records: list, items: Optional[list] = None):
        chunks = [chunk for record in records for chunk in build_chunks(record)]
        if items:
            chunks += [chunk for item in items for chunk in build_item_chunks(item)]
        self._chunks = chunks
        self._bm25 = BM25Okapi([_tokenize(chunk["text"]) for chunk in chunks]) if chunks else None

    def search(self, question: str, n_results: int = 10) -> list:
        if self._bm25 is None:
            return []
        scores = self._bm25.get_scores(_tokenize(question))
        ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        return [self._chunks[i] for i in ranked[:n_results] if scores[i] > 0]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_rag_bm25.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add rag/bm25.py tests/test_rag_bm25.py
git commit -m "feat: add in-memory BM25 keyword index for hybrid retrieval" -m "$(printf 'Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>')"
```

---

### Task 3: Fuse BM25 + vector results via RRF in `build_context_block`

**Files:**
- Modify: `rag/retrieve.py`
- Test: `tests/test_rag_retrieve.py` (append new tests; do not change existing ones)

**Interfaces:**
- Consumes: `BM25Index.search(question, n_results) -> list[dict]` from Task 2; `index.query(text, n_results, where=None) -> list[dict]` (existing `ChromaIndex`/fake-index contract, each match dict has `id`, `text`, `metadata`, `distance`).
- Produces: `build_context_block(index, question, records=None, items=None, n_results=5, bm25_index=None) -> dict` — same return shape as today (`text`, `sources`, `retrieved_chunks`, `best_distance`). Used by Task 4's `ask_response`/`ask_response_async`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_rag_retrieve.py`:

```python
from rag.retrieve import build_context_block


class _FakeBM25Index:
    def __init__(self, results):
        self._results = results
        self.searches = []

    def search(self, question, n_results=10):
        self.searches.append((question, n_results))
        return self._results[:n_results]


class _FakeIndexNoWhere:
    """Same as _FakeIndex above but records every call for pool-size assertions."""

    def __init__(self, matches):
        self._matches = matches
        self.queries = []

    def query(self, text, n_results=5):
        self.queries.append({"text": text, "n_results": n_results})
        return self._matches[:n_results]


def test_build_context_block_ignores_bm25_index_by_default_unchanged_behavior():
    index = _FakeIndexNoWhere(matches=[
        {"id": "a-stats", "text": "a", "metadata": {"pokemon": "A", "chunk_type": "stats"}, "distance": 0.4},
    ])

    build_context_block(index, "Some question", n_results=3)

    assert index.queries == [{"text": "Some question", "n_results": 3}]


def test_build_context_block_fuses_a_bm25_only_hit_into_the_results():
    # Vector search returns nothing relevant; BM25 finds the exact-keyword chunk.
    index = _FakeIndexNoWhere(matches=[
        {"id": "unrelated-stats", "text": "Unrelated chunk", "metadata": {"pokemon": "Unrelated", "chunk_type": "stats"}, "distance": 1.2},
    ])
    bm25_index = _FakeBM25Index(results=[
        {"id": "Aegislash-stats", "text": "Aegislash is a Steel/Ghost-type Pokemon. Abilities: Stance Change.", "pokemon": "Aegislash", "chunk_type": "stats"},
    ])

    result = build_context_block(index, "Which Pokemon has Stance Change?", n_results=2, bm25_index=bm25_index)

    ids = {chunk["id"] for chunk in result["retrieved_chunks"]}
    assert "Aegislash-stats" in ids
    assert "Aegislash is a Steel/Ghost-type Pokemon. Abilities: Stance Change." in result["text"]


def test_build_context_block_bm25_only_hit_never_lowers_best_distance_below_the_real_vector_minimum():
    index = _FakeIndexNoWhere(matches=[
        {"id": "unrelated-stats", "text": "Unrelated chunk", "metadata": {"pokemon": "Unrelated", "chunk_type": "stats"}, "distance": 1.2},
    ])
    bm25_index = _FakeBM25Index(results=[
        {"id": "Aegislash-stats", "text": "Aegislash text", "pokemon": "Aegislash", "chunk_type": "stats"},
    ])

    result = build_context_block(index, "Which Pokemon has Stance Change?", n_results=2, bm25_index=bm25_index)

    assert result["best_distance"] == 1.2


def test_build_context_block_ranks_a_chunk_found_by_both_retrievers_above_a_single_retriever_hit():
    index = _FakeIndexNoWhere(matches=[
        {"id": "both-stats", "text": "Found by both", "metadata": {"pokemon": "Both", "chunk_type": "stats"}, "distance": 0.5},
        {"id": "vector-only-stats", "text": "Vector only", "metadata": {"pokemon": "VectorOnly", "chunk_type": "stats"}, "distance": 0.6},
    ])
    bm25_index = _FakeBM25Index(results=[
        {"id": "both-stats", "text": "Found by both", "pokemon": "Both", "chunk_type": "stats"},
        {"id": "bm25-only-stats", "text": "BM25 only", "pokemon": "BM25Only", "chunk_type": "stats"},
    ])

    result = build_context_block(index, "A question", n_results=1, bm25_index=bm25_index)

    assert result["retrieved_chunks"] == [{"id": "both-stats", "distance": 0.5}]


def test_build_context_block_expands_the_vector_candidate_pool_when_bm25_index_is_given():
    index = _FakeIndexNoWhere(matches=[])
    bm25_index = _FakeBM25Index(results=[])

    build_context_block(index, "A question", n_results=3, bm25_index=bm25_index)

    # Candidate pool must be at least n_results, and wider than a bare n_results=3
    # so fusion has real breadth to work with.
    assert index.queries[0]["n_results"] > 3
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_rag_retrieve.py -v`
Expected: FAIL — `build_context_block() got an unexpected keyword argument 'bm25_index'`

- [ ] **Step 3: Implement the hybrid fusion**

Replace the full contents of `rag/retrieve.py`:

```python
from typing import Optional

from rag.entity import detect_entity

_RRF_K = 60
_CANDIDATE_POOL_SIZE = 10


def _hybrid_matches(index, question: str, n_results: int, bm25_index) -> list:
    """The two currently-unfiltered code paths in build_context_block route
    through here. With no bm25_index (the default, and every pre-hybrid
    caller), this is byte-identical to the old `index.query(question,
    n_results=n_results)` call. With a bm25_index, both retrievers are
    queried over a wider candidate pool and fused by rank via Reciprocal
    Rank Fusion (RRF) -- rank position only, not raw scores, since BM25 and
    cosine-distance scores aren't on comparable scales.
    """
    if bm25_index is None:
        return index.query(question, n_results=n_results)

    candidate_pool = max(n_results, _CANDIDATE_POOL_SIZE)
    vector_matches = index.query(question, n_results=candidate_pool)
    bm25_chunks = bm25_index.search(question, n_results=candidate_pool)

    vector_by_id = {match["id"]: match for match in vector_matches}
    bm25_by_id = {chunk["id"]: chunk for chunk in bm25_chunks}
    vector_rank = {match["id"]: i + 1 for i, match in enumerate(vector_matches)}
    bm25_rank = {chunk["id"]: i + 1 for i, chunk in enumerate(bm25_chunks)}

    # A BM25-only hit (no real vector distance) is never allowed to look
    # more confident than anything the vector query actually found -- give
    # it the worst distance observed in the vector candidate pool, or
    # infinity if the vector pool was empty.
    fallback_distance = max((match["distance"] for match in vector_matches), default=float("inf"))

    def rrf_score(chunk_id: str) -> float:
        score = 0.0
        if chunk_id in vector_rank:
            score += 1.0 / (_RRF_K + vector_rank[chunk_id])
        if chunk_id in bm25_rank:
            score += 1.0 / (_RRF_K + bm25_rank[chunk_id])
        return score

    all_ids = set(vector_rank) | set(bm25_rank)
    fused_ids = sorted(all_ids, key=rrf_score, reverse=True)[:n_results]

    fused_matches = []
    for chunk_id in fused_ids:
        if chunk_id in vector_by_id:
            fused_matches.append(vector_by_id[chunk_id])
        else:
            chunk = bm25_by_id[chunk_id]
            fused_matches.append({
                "id": chunk["id"],
                "text": chunk["text"],
                "metadata": {k: v for k, v in chunk.items() if k not in ("id", "text")},
                "distance": fallback_distance,
            })
    return fused_matches


def build_context_block(
    index,
    question: str,
    records: Optional[list] = None,
    items: Optional[list] = None,
    n_results: int = 5,
    bm25_index=None,
) -> dict:
    entity = detect_entity(question, records or [], items or [])
    if entity:
        matches = index.query(question, n_results=n_results, where={entity["field"]: entity["name"]})
        if not matches:
            matches = _hybrid_matches(index, question, n_results, bm25_index)
    else:
        matches = _hybrid_matches(index, question, n_results, bm25_index)
    return {
        "text": "\n".join(match["text"] for match in matches),
        "sources": [
            {
                "name": match["metadata"].get("pokemon") or match["metadata"].get("item"),
                "chunk_type": match["metadata"]["chunk_type"],
            }
            for match in matches
        ],
        "retrieved_chunks": [
            {"id": match["id"], "distance": match["distance"]} for match in matches
        ],
        "best_distance": min((match["distance"] for match in matches), default=None),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_rag_retrieve.py -v`
Expected: all tests pass (existing + new)

- [ ] **Step 5: Run the full suite to confirm no regressions**

Run: `python -m pytest tests/test_rag_retrieve.py tests/test_bot_ask.py tests/test_eval_retrieval.py -v`
Expected: all pass unchanged (bm25_index defaults to None everywhere else so far)

- [ ] **Step 6: Commit**

```bash
git add rag/retrieve.py tests/test_rag_retrieve.py
git commit -m "feat: fuse BM25 keyword search into the unfiltered retrieval path via RRF" -m "$(printf 'Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>')"
```

---

### Task 4: Wire `bm25_index` through `ask_response`/`ask_response_async`

**Files:**
- Modify: `bot/commands/ask.py`
- Test: `tests/test_bot_ask.py` (append new tests)

**Interfaces:**
- Consumes: `build_context_block(..., bm25_index=None)` from Task 3.
- Produces: `ask_response(index, answerer, question, records=None, items=None, n_results=5, extra_context=None, bm25_index=None) -> dict`; `ask_response_async(...)` same signature, both unchanged in every other respect. Used by Task 5's `bot/main.py` wiring.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_bot_ask.py`:

```python
class _RecordingBM25Index:
    def __init__(self):
        self.received_questions = []

    def search(self, question, n_results=10):
        self.received_questions.append(question)
        return []


def test_ask_response_forwards_bm25_index_to_build_context_block():
    index = _FakeIndex(matches=[])
    answerer = _FakeAnswerer(response="An answer.")
    bm25_index = _RecordingBM25Index()

    ask_response(index, answerer, "A question", bm25_index=bm25_index)

    assert bm25_index.received_questions == ["A question"]


async def test_ask_response_async_forwards_bm25_index_to_build_context_block():
    index = _FakeIndex(matches=[])
    answerer = _FakeAnswerer(response="An answer.")
    bm25_index = _RecordingBM25Index()

    await ask_response_async(index, answerer, "A question", bm25_index=bm25_index)

    assert bm25_index.received_questions == ["A question"]
```

Check the top of `tests/test_bot_ask.py` for how `ask_response_async` is already imported and how existing `async def test_...` functions are run (pytest-asyncio marker or similar) — match that exact pattern so the new async test actually executes instead of being silently skipped.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_bot_ask.py -v -k bm25`
Expected: FAIL — `ask_response() got an unexpected keyword argument 'bm25_index'`

- [ ] **Step 3: Implement**

In `bot/commands/ask.py`, update `ask_response`:

```python
def ask_response(
    index,
    answerer,
    question: str,
    records: Optional[list] = None,
    items: Optional[list] = None,
    n_results: int = 5,
    extra_context: Optional[str] = None,
    bm25_index=None,
) -> dict:
    context = build_context_block(
        index, question, records=records, items=items, n_results=n_results, bm25_index=bm25_index
    )
    ...  # rest unchanged
```

And `ask_response_async`'s signature + the `asyncio.to_thread(...)` call it wraps — add the same `bm25_index=None` parameter and pass it through positionally/by-keyword to the wrapped `ask_response` call (match whatever calling convention `asyncio.to_thread` already uses there — likely `asyncio.to_thread(ask_response, index, answerer, question, records, items, n_results, extra_context, bm25_index)` if positional, or add it as a keyword — read the existing line first and extend it consistently).

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_bot_ask.py -v`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add bot/commands/ask.py tests/test_bot_ask.py
git commit -m "feat: thread bm25_index through ask_response/ask_response_async" -m "$(printf 'Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>')"
```

---

### Task 5: Build and wire a real `BM25Index` in the bot

**Files:**
- Modify: `bot/main.py`
- Test: `tests/test_bot_main.py` (append new test)

**Interfaces:**
- Consumes: `BM25Index(records, items)` from Task 2; `ask_response_async(..., bm25_index=None)` from Task 4.
- Produces: `build_client(..., bm25_index=None)` — the `/ask` handler forwards `bm25_index` into its `ask_response_async` call. `main()` builds a real `BM25Index` from the same `records`/`items` it already loads and passes it to `build_client`.

- [ ] **Step 1: Write the failing test**

Read `tests/test_bot_main.py` around the existing `/ask`-handler tests (search for `ask_response_async` usage or the test that exercises the `ask` tree command with a fake index/answerer, e.g. near `build_client(index=_FakeIndex(), answerer=_FakeAnswerer())`) to match its exact fixture/invocation style, then append a test structured the same way:

```python
def test_build_client_forwards_bm25_index_to_the_ask_handler(monkeypatch):
    captured = {}

    async def fake_ask_response_async(index, answerer, question, records=None, items=None, n_results=5, extra_context=None, bm25_index=None):
        captured["bm25_index"] = bm25_index
        return {"answer": "An answer.", "sources": [], "retrieved_chunks": [], "best_distance": 0.1}

    monkeypatch.setattr("bot.main.ask_response_async", fake_ask_response_async)
    sentinel_bm25_index = object()

    _client, tree = build_client(
        index=_FakeIndex(), answerer=_FakeAnswerer(), bm25_index=sentinel_bm25_index
    )
    # Invoke the /ask command the same way the existing ask-handler test in
    # this file does (reuse its exact interaction-mocking helper/pattern).

    assert captured["bm25_index"] is sentinel_bm25_index
```

Adjust the fake-interaction invocation to match whatever helper this test file already uses elsewhere to call a `tree` command directly (there is exactly one existing `/ask`-exercising test in this file — copy its interaction setup verbatim rather than inventing a new one).

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_bot_main.py -v -k bm25`
Expected: FAIL — `build_client() got an unexpected keyword argument 'bm25_index'`

- [ ] **Step 3: Implement**

In `bot/main.py`:

1. Add the import: `from rag.bm25 import BM25Index`
2. Update `build_client`'s signature to add `bm25_index=None`.
3. In the `/ask` handler (`async def ask(...)`), add `bm25_index=bm25_index` to the existing `ask_response_async(...)` call.
4. Update `main()`:

```python
def main() -> None:
    token = os.environ["DISCORD_TOKEN"]
    records = _load_records()
    items = _load_items()
    raw_answerer = _build_answerer()
    client, _tree = build_client(
        index=_build_real_index(records, items),
        answerer=CircuitBreaker(raw_answerer),
        raw_answerer=raw_answerer,
        records=records,
        moves=_load_moves(),
        usage=_load_usage(),
        items=items,
        bm25_index=BM25Index(records, items),
    )
    client.run(token)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_bot_main.py -v`
Expected: all pass

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest -q`
Expected: all tests pass (previous count + new tests from Tasks 1-5, no regressions)

- [ ] **Step 6: Commit**

```bash
git add bot/main.py tests/test_bot_main.py
git commit -m "feat: wire a real BM25Index into the live bot's /ask path" -m "$(printf 'Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>')"
```

---

### Task 6: Add golden-set entries targeting the no-entity-detected gap and prove the recall fix

**Files:**
- Modify: `data/eval/golden_set.json`
- Modify: `tests/test_eval_retrieval.py`

**Interfaces:**
- Consumes: `rag.bm25.BM25Index`, `rag.retrieve.build_context_block(..., bm25_index=...)`, `bot.main._build_real_index`, `rag.entity.detect_entity` — all from prior tasks / already-existing code.

**Background (already verified against the real data before writing this plan):** every existing golden-set entry names a Pokemon or item directly in its question, so `detect_entity` always fires and the unfiltered/hybrid path is never exercised by the golden set today. These 4 new entries deliberately avoid naming the target Pokemon/item (verified live against `rag.entity.detect_entity` — each returns `None`). One of them (`Aegislash-stats`) is a **real, currently-failing** case at k=5 with pure vector search (confirmed: `index.query(...)` top-5 returns unrelated `Pikachu-moveset`/`Lucario-moveset`/etc., not `Aegislash-stats`) — BM25 alone ranks it #1 for this question (confirmed: BM25 score 33.2, next-highest chunk scores 32.5), so RRF fusion recovers it. The other 3 already pass with pure vector search but still add real no-entity-detected coverage.

- [ ] **Step 1: Add the 4 new entries**

Open `data/eval/golden_set.json` and append these 4 objects to the JSON array (keep it valid JSON — add a comma after the current last entry):

```json
  {
    "id": "no-entity-stance-change-question",
    "question": "Which Pokemon changes from a defensive stance to an offensive stance via the Stance Change ability?",
    "match_type": "substring",
    "expected": "Stance Change",
    "source_chunk_id": "Aegislash-stats"
  },
  {
    "id": "no-entity-air-balloon-question",
    "question": "What held item keeps its holder floating so it is immune to attacks from below, until it is hit once and pops?",
    "match_type": "substring",
    "expected": "immunity to Ground-type moves",
    "source_chunk_id": "item-Air Balloon"
  },
  {
    "id": "no-entity-levitate-attack-question",
    "question": "Which Pokemon has the Levitate ability, 115 base Attack, and only 50 base Speed?",
    "match_type": "set",
    "expected": ["Attack 115", "Speed 50"],
    "source_chunk_id": "Eelektross-stats"
  },
  {
    "id": "no-entity-burn-cure-question",
    "question": "What held item cures a burn and disappears after a single use?",
    "match_type": "substring",
    "expected": "Cures being burned",
    "source_chunk_id": "item-Rawst Berry"
  }
```

- [ ] **Step 2: Verify the JSON is valid and the entries' ids are unique**

Run: `python -c "import json; d = json.loads(open('data/eval/golden_set.json').read()); print(len(d)); assert len({e['id'] for e in d}) == len(d)"`
Expected: prints `52` (48 existing + 4 new), no assertion error.

- [ ] **Step 3: Write the failing regression test**

Append to `tests/test_eval_retrieval.py`:

```python
from rag.bm25 import BM25Index
from rag.retrieve import build_context_block


def test_hybrid_retrieval_recovers_a_no_entity_detected_miss_that_pure_vector_search_misses():
    """Aegislash-stats is a REAL miss for pure vector search at k=5 on this
    question (confirmed directly against the live index while writing this
    plan) -- BM25 ranks it #1 on the same question, so RRF fusion should
    recover it. This is the concrete, demonstrated benefit of hybrid
    retrieval, not just a smoke test."""
    records = json.loads(RECORDS_PATH.read_text())
    items = json.loads(ITEMS_PATH.read_text())
    golden_by_id = {entry["id"]: entry for entry in json.loads(GOLDEN_SET_PATH.read_text())}
    entry = golden_by_id["no-entity-stance-change-question"]

    index = _build_real_index(records, items, client=chromadb.Client())
    bm25_index = BM25Index(records, items)

    # Confirm the premise: pure vector search at k=5 misses it.
    vector_only_ids = {m["id"] for m in index.query(entry["question"], n_results=5)}
    assert entry["source_chunk_id"] not in vector_only_ids, (
        "premise check failed -- pure vector search no longer misses this question; "
        "pick a different no-entity-detected golden entry that's still a real miss"
    )

    # Hybrid retrieval (through the actual build_context_block path) recovers it.
    result = build_context_block(index, entry["question"], records=records, items=items, n_results=5, bm25_index=bm25_index)
    hybrid_ids = {chunk["id"] for chunk in result["retrieved_chunks"]}
    assert entry["source_chunk_id"] in hybrid_ids


def test_new_no_entity_golden_entries_detect_no_entity():
    """Confirms the premise these 4 entries were added for: none of them
    should trigger entity-aware filtering, so they actually exercise the
    unfiltered/hybrid retrieval path build_context_block falls back to."""
    records = json.loads(RECORDS_PATH.read_text())
    items = json.loads(ITEMS_PATH.read_text())
    golden_by_id = {entry["id"]: entry for entry in json.loads(GOLDEN_SET_PATH.read_text())}

    no_entity_ids = [
        "no-entity-stance-change-question",
        "no-entity-air-balloon-question",
        "no-entity-levitate-attack-question",
        "no-entity-burn-cure-question",
    ]
    for golden_id in no_entity_ids:
        entity = detect_entity(golden_by_id[golden_id]["question"], records, items)
        assert entity is None, f"{golden_id}: expected no entity detected, got {entity}"
```

- [ ] **Step 4: Run the new tests to verify they fail first, then implementation makes them pass**

Run: `python -m pytest tests/test_eval_retrieval.py -v -k "no_entity or hybrid_retrieval_recovers"`
Expected: with Tasks 2-3 already implemented, `test_new_no_entity_golden_entries_detect_no_entity` should already PASS (pure data check), and `test_hybrid_retrieval_recovers_a_no_entity_detected_miss` should also PASS since `BM25Index`/`build_context_block(bm25_index=...)` already exist from Tasks 2-3. If either fails, debug before proceeding — do not weaken the assertions.

- [ ] **Step 5: Run the complete eval-retrieval test file and the full suite**

Run: `python -m pytest tests/test_eval_retrieval.py -v`
Expected: all pass, including the pre-existing `test_recall_at_5_meets_the_threshold_against_the_real_index` (unaffected — it calls `index.query` directly, not `build_context_block`) and `test_recall_at_5_through_entity_aware_retrieval_does_not_regress` (unaffected for the same reason — it doesn't pass `bm25_index` either).

Run: `python -m pytest -q`
Expected: full suite passes.

- [ ] **Step 6: Commit**

```bash
git add data/eval/golden_set.json tests/test_eval_retrieval.py
git commit -m "test: add no-entity-detected golden entries and prove hybrid retrieval recovers a real miss" -m "$(printf 'Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>')"
```

---

### Task 7: Update `IMPROVEMENTS.md`

**Files:**
- Modify: `IMPROVEMENTS.md`

- [ ] **Step 1: Mark the item done**

In `IMPROVEMENTS.md`'s "Hybrid BM25+vector retrieval" bullet (top summary section and the "Priority 3" section), replace "bounded design approved in chat (2026-09-17), not yet implemented" with a short "implemented and merged" note mirroring the style of the neighboring "Pinned-deps CI check — done." bullet: what shipped, the final test count, and the one concrete recall fix demonstrated (`Aegislash-stats`, previously missed by pure vector search at k=5, now recovered via BM25+RRF).

- [ ] **Step 2: Commit**

```bash
git add IMPROVEMENTS.md
git commit -m "docs: mark hybrid BM25+vector retrieval done in the improvement backlog" -m "$(printf 'Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>')"
```
