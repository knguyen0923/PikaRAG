# Grounding & Trust Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `/ask` show *why* it said something (source attribution) and refuse to guess when retrieval is clearly too weak (a distance-based confidence gate), instead of silently forwarding noisy context to the LLM.

**Architecture:** `build_context_block` (`rag/retrieve.py`) changes from returning a bare string to a structured `dict` (`text`/`sources`/`best_distance`), preserving its existing entity-aware filtering and unfiltered-fallback behavior from `[[retrieval-quality]]` (already shipped). `ask_response`/`ask_response_async` (`bot/commands/ask.py`) gain a hard-coded distance threshold: below it, the LLM is called as before and its answer is paired with the retrieved sources; at or above it (or when there were no matches at all), the LLM is never called and a fixed low-confidence message is returned instead. Both functions now always return a `{"answer": str, "sources": list}` dict — never a bare string, across all three outcomes (normal, gate-fired, offline-degraded). A new `format_ask_response` helper renders that dict into the final display text, appending a compact `Sources: ...` line when sources are present. `bot/main.py`'s `/ask` handler and `scripts/run_eval.py`'s eval harness — the only two real callers of this code — are updated to use the new dict shape.

**Tech Stack:** Python 3.9, no new dependencies.

**Spec:** `docs/superpowers/specs/2026-09-13-grounding-trust-design.md`

## Global Constraints

- No new dependencies.
- `ask_response`/`ask_response_async`'s return value is **always** a dict of shape `{"answer": str, "sources": list[dict]}` — never a bare string, in all three outcomes: normal, gate-fired, and offline-degraded (spec's "Return shape contract").
- The confidence gate must check `best_distance is None` **before** any numeric comparison — comparing `None > threshold` raises `TypeError` (spec's "Confidence gate").
- The gate is a fixed, hard-coded numeric threshold, not a learned model (spec's "Confidence gate" / "Out of scope").
- Raw distance scores are never shown to end users — only chunk name + chunk type (spec's "Out of scope").
- Per-sentence/fine-grained citation is out of scope — chunk-level attribution only (spec's "Out of scope").
- Every existing caller/test of `build_context_block` and `ask_response`/`ask_response_async` must be updated in the same task that changes the return shape — this is a breaking change to both functions' return types, not an additive one, and is **not** automatically caught by the existing test suite (confirmed: `discord.Embed(description=<a dict>, ...)` does not raise, it silently stringifies the dict — spec's "Source attribution").

---

## Distance threshold (empirically derived, not a placeholder)

The spec anticipated shipping a placeholder threshold because neither the eval harness nor a real golden set existed yet when it was written. Both now exist and are merged (`[[eval-harness]]`, `[[retrieval-quality]]`), so this plan uses a real, measured value instead of a guess:

- Querying the real index (`bot.main._build_real_index`) with entity-aware filtering (`rag.entity.detect_entity`, same as `build_context_block` uses) against all 48 golden-set questions: every one's `best_distance` (the nearest match's distance) is **≤ 1.3565**, and the source chunk is found in all 48 (recall@5 = 1.0 as of this plan, per `[[retrieval-quality]]`'s final measurement).
- Querying the same real index with 8 clearly out-of-domain questions ("What is the capital of France?", "How do I bake a chocolate cake?", "Tell me a joke.", etc.): every one's `best_distance` is **≥ 1.4923**.
- There is a clean gap between the two clusters (1.3565 to 1.4923). This plan uses **`1.4`**, inside that gap and closer to the golden-set side, so no real, answerable question from the golden set is ever falsely gated, while clearly out-of-domain questions are.

This constant lives in `bot/commands/ask.py` as `DISTANCE_THRESHOLD = 1.4`, with the above measurement documented in a comment so a future session can re-derive or re-tune it once more real usage data exists.

---

## File structure

- Modify `rag/retrieve.py` — `build_context_block` returns `{"text": str, "sources": list[dict], "best_distance": float | None}` instead of a bare string. Preserves the existing entity-aware `where`-filter + unfiltered-fallback logic unchanged.
- Modify `tests/test_rag_retrieve.py` — every existing test updated for the new dict return shape (fixtures need a `"distance"` key and a `"chunk_type"` key in `"metadata"`, which real chunks always have but the old fakes didn't need); new tests for `sources`/`best_distance` construction.
- Modify `bot/commands/ask.py` — `ask_response`/`ask_response_async` gain the confidence gate and return a dict; new `format_ask_response(result: dict) -> str` helper renders the final display text with the sources line.
- Modify `tests/test_bot_ask.py` — every existing test updated for the new dict return shape; new tests for the gate (over-threshold, `None`, LLM never called in either case), the offline-degraded case, and `format_ask_response`.
- Modify `bot/main.py` — the `ask` command handler (`bot/main.py:63-72`) calls `format_ask_response` on the result before building the embed.
- Modify `tests/test_bot_main.py` — the existing `test_ask_command_includes_stored_team_context` test's fake index is updated to return a close-distance match (an empty-match index now triggers the gate and never calls the answerer, which would break that test's premise); one new test asserting the sent embed includes a `Sources: ...` line.
- Modify `scripts/run_eval.py` — `run_answer_quality` reads `ask_response(...)["answer"]` instead of treating the return as a bare string (the only other real, non-test caller of `ask_response`).
- Modify `tests/test_run_eval.py` — the shared `_FakeIndex.query` fake is updated to return a close-distance match (it currently returns `[]` unconditionally, which would now trigger the gate and break every test in the file that expects the fake answerer's configured response to come through).

---

### Task 1: `build_context_block` returns structured data

**Files:**
- Modify: `rag/retrieve.py` (full file, currently 20 lines)
- Test: `tests/test_rag_retrieve.py` (full file rewrite)

**Interfaces:**
- Consumes: `rag.entity.detect_entity(question, records, items)` (unchanged, already shipped), `index.query(text, n_results, where=None) -> list[dict]` where each match dict has `"text"`, `"metadata"`, `"distance"` keys (unchanged, already shipped — `rag/store.py`'s `ChromaIndex.query`).
- Produces: `build_context_block(index, question, records=None, items=None, n_results=5) -> dict` with keys `"text"` (str), `"sources"` (list of `{"name": str, "chunk_type": str}`), `"best_distance"` (float or `None`). Task 2 calls this and reads all three keys.

- [ ] **Step 1: Write the failing tests**

Replace the full contents of `tests/test_rag_retrieve.py`:

```python
from rag.retrieve import build_context_block


class _FakeIndex:
    def __init__(self, matches):
        self._matches = matches
        self.queries = []

    def query(self, text, n_results=5):
        self.queries.append((text, n_results))
        return self._matches[:n_results]


def test_build_context_block_queries_the_index_with_the_question():
    index = _FakeIndex(matches=[])

    build_context_block(index, "How bulky is Gyarados?", n_results=3)

    assert index.queries == [("How bulky is Gyarados?", 3)]


def test_build_context_block_includes_each_matched_chunks_text():
    index = _FakeIndex(
        matches=[
            {
                "text": "Gyarados is a Water/Flying-type Pokemon.",
                "metadata": {"pokemon": "Gyarados", "chunk_type": "stats"},
                "distance": 0.4,
            },
            {
                "text": "Gyarados's legal moveset includes: Waterfall.",
                "metadata": {"pokemon": "Gyarados", "chunk_type": "moveset"},
                "distance": 0.5,
            },
        ]
    )

    result = build_context_block(index, "How bulky is Gyarados?")

    assert "Gyarados is a Water/Flying-type Pokemon." in result["text"]
    assert "Gyarados's legal moveset includes: Waterfall." in result["text"]


def test_build_context_block_returns_empty_text_sources_and_distance_for_no_matches():
    index = _FakeIndex(matches=[])

    result = build_context_block(index, "Unknown question")

    assert result["text"] == ""
    assert result["sources"] == []
    assert result["best_distance"] is None


def test_build_context_block_returns_sources_from_matched_chunk_metadata():
    index = _FakeIndex(
        matches=[
            {
                "text": "Gyarados is a Water/Flying-type Pokemon.",
                "metadata": {"pokemon": "Gyarados", "chunk_type": "stats"},
                "distance": 0.4,
            },
            {
                "text": "Life Orb: Boosts move power.",
                "metadata": {"item": "Life Orb", "chunk_type": "item"},
                "distance": 0.6,
            },
        ]
    )

    result = build_context_block(index, "How bulky is Gyarados?")

    assert result["sources"] == [
        {"name": "Gyarados", "chunk_type": "stats"},
        {"name": "Life Orb", "chunk_type": "item"},
    ]


def test_build_context_block_returns_the_smallest_distance_as_best_distance():
    index = _FakeIndex(
        matches=[
            {"text": "a", "metadata": {"pokemon": "A", "chunk_type": "stats"}, "distance": 0.9},
            {"text": "b", "metadata": {"pokemon": "B", "chunk_type": "stats"}, "distance": 0.3},
            {"text": "c", "metadata": {"pokemon": "C", "chunk_type": "stats"}, "distance": 0.7},
        ]
    )

    result = build_context_block(index, "Some question")

    assert result["best_distance"] == 0.3


class _FakeIndexWithWhere:
    def __init__(self, matches):
        self._matches = matches
        self.queries = []

    def query(self, text, n_results=5, where=None):
        self.queries.append({"text": text, "n_results": n_results, "where": where})
        if where:
            return [
                m for m in self._matches
                if all(m["metadata"].get(k) == v for k, v in where.items())
            ][:n_results]
        return self._matches[:n_results]


_RECORDS = [{"name": "Abomasnow"}]
_ITEMS = []


def test_build_context_block_narrows_the_query_when_an_entity_is_detected():
    index = _FakeIndexWithWhere(matches=[
        {
            "text": "Abomasnow stats chunk",
            "metadata": {"pokemon": "Abomasnow", "chunk_type": "stats"},
            "distance": 0.4,
        },
        {
            "text": "Unrelated Gyarados chunk",
            "metadata": {"pokemon": "Gyarados", "chunk_type": "stats"},
            "distance": 0.5,
        },
    ])

    build_context_block(index, "Does Abomasnow learn Attract?", records=_RECORDS, items=_ITEMS)

    assert index.queries[0]["where"] == {"pokemon": "Abomasnow"}


def test_build_context_block_falls_back_to_unfiltered_when_no_entity_detected():
    index = _FakeIndexWithWhere(matches=[
        {"text": "Some chunk", "metadata": {"pokemon": "Whatever", "chunk_type": "stats"}, "distance": 0.5},
    ])

    build_context_block(index, "What is the weather like?", records=_RECORDS, items=_ITEMS)

    assert index.queries[0]["where"] is None


def test_build_context_block_falls_back_to_unfiltered_when_filtered_query_returns_nothing():
    index = _FakeIndexWithWhere(matches=[
        {
            "text": "Unrelated chunk with no pokemon metadata",
            "metadata": {"item": "Some Item", "chunk_type": "item"},
            "distance": 0.6,
        },
    ])

    result = build_context_block(
        index, "Does Abomasnow learn Attract?", records=_RECORDS, items=_ITEMS
    )

    assert len(index.queries) == 2
    assert index.queries[0]["where"] == {"pokemon": "Abomasnow"}
    assert index.queries[1]["where"] is None
    assert "Unrelated chunk with no pokemon metadata" in result["text"]
```

- [ ] **Step 2: Run tests to verify the changed ones fail**

Run: `pytest tests/test_rag_retrieve.py -v`
Expected: `test_build_context_block_includes_each_matched_chunks_text` and the "no matches"/"sources"/"best_distance" tests FAIL — `result["text"]`/`result["sources"]` etc. raise `TypeError: string indices must be integers` (since `build_context_block` still returns a plain string). `test_build_context_block_queries_the_index_with_the_question` and the entity-narrowing tests PASS already (they only check `index.queries`, not the return value).

- [ ] **Step 3: Implement the change**

Replace the full contents of `rag/retrieve.py`:

```python
from typing import Optional

from rag.entity import detect_entity


def build_context_block(
    index,
    question: str,
    records: Optional[list] = None,
    items: Optional[list] = None,
    n_results: int = 5,
) -> dict:
    entity = detect_entity(question, records or [], items or [])
    if entity:
        matches = index.query(question, n_results=n_results, where={entity["field"]: entity["name"]})
        if not matches:
            matches = index.query(question, n_results=n_results)
    else:
        matches = index.query(question, n_results=n_results)
    return {
        "text": "\n".join(match["text"] for match in matches),
        "sources": [
            {
                "name": match["metadata"].get("pokemon") or match["metadata"].get("item"),
                "chunk_type": match["metadata"]["chunk_type"],
            }
            for match in matches
        ],
        "best_distance": min((match["distance"] for match in matches), default=None),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_rag_retrieve.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add rag/retrieve.py tests/test_rag_retrieve.py
git commit -m "feat: return structured sources/best_distance from build_context_block"
```

---

### Task 2: Confidence gate + dict return shape + sources formatting in `ask_response`

**Files:**
- Modify: `bot/commands/ask.py` (full file, currently 40 lines)
- Test: `tests/test_bot_ask.py` (full file rewrite)

**Interfaces:**
- Consumes: `build_context_block(index, question, records=None, items=None, n_results=5) -> dict` (Task 1), `rag.answer.OFFLINE_MESSAGE` (str constant, already exists in `rag/answer.py`, unmodified).
- Produces: `ask_response(index, answerer, question, records=None, items=None, n_results=5, extra_context=None) -> dict` and the equivalent async version, both always returning `{"answer": str, "sources": list[dict]}`. `format_ask_response(result: dict) -> str`. Tasks 3 and 4 call `ask_response`/`ask_response_async` and read `.answer`/`.sources`; Task 3 also calls `format_ask_response`.

- [ ] **Step 1: Write the failing tests**

Replace the full contents of `tests/test_bot_ask.py`:

```python
import asyncio
import time

from bot.commands.ask import ask_response, ask_response_async, format_ask_response
from rag.answer import OFFLINE_MESSAGE


class _FakeIndex:
    def __init__(self, context_matches):
        self._matches = context_matches

    def query(self, text, n_results=5, where=None):
        return self._matches[:n_results]


class _FakeAnswerer:
    def __init__(self, response_text):
        self._response_text = response_text
        self.calls = []

    def answer(self, question, context_block):
        self.calls.append((question, context_block))
        return self._response_text


_CLOSE_MATCH = {
    "text": "Gyarados base HP: 95.",
    "metadata": {"pokemon": "Gyarados", "chunk_type": "stats"},
    "distance": 0.4,
}


def test_ask_response_returns_the_answerers_response():
    index = _FakeIndex(context_matches=[_CLOSE_MATCH])
    answerer = _FakeAnswerer(response_text="Gyarados has 95 base HP.")

    result = ask_response(index, answerer, "How bulky is Gyarados?")

    assert result["answer"] == "Gyarados has 95 base HP."


def test_ask_response_returns_sources_from_the_matched_chunks():
    index = _FakeIndex(context_matches=[_CLOSE_MATCH])
    answerer = _FakeAnswerer(response_text="Gyarados has 95 base HP.")

    result = ask_response(index, answerer, "How bulky is Gyarados?")

    assert result["sources"] == [{"name": "Gyarados", "chunk_type": "stats"}]


def test_ask_response_passes_retrieved_context_to_the_answerer():
    index = _FakeIndex(context_matches=[_CLOSE_MATCH])
    answerer = _FakeAnswerer(response_text="anything")

    ask_response(index, answerer, "How bulky is Gyarados?")

    question, context_text = answerer.calls[0]
    assert question == "How bulky is Gyarados?"
    assert "Gyarados base HP: 95." in context_text


def test_ask_response_async_returns_the_same_result_as_the_sync_version():
    index = _FakeIndex(context_matches=[_CLOSE_MATCH])
    answerer = _FakeAnswerer(response_text="Gyarados has 95 base HP.")

    result = asyncio.run(ask_response_async(index, answerer, "How bulky is Gyarados?"))

    assert result["answer"] == "Gyarados has 95 base HP."


def test_ask_response_async_does_not_block_the_event_loop():
    # A "slow" sync answerer standing in for a real blocking network call.
    # If ask_response_async ran it directly on the event loop instead of
    # offloading to a thread, the ticker below would be starved for the
    # whole 0.2s and record close to zero ticks.
    class _SlowAnswerer:
        def answer(self, question, context_block):
            time.sleep(0.2)
            return "answer"

    index = _FakeIndex(context_matches=[_CLOSE_MATCH])
    answerer = _SlowAnswerer()

    async def run():
        ticks = 0

        async def ticker():
            nonlocal ticks
            while True:
                await asyncio.sleep(0.01)
                ticks += 1

        ticker_task = asyncio.create_task(ticker())
        result = await ask_response_async(index, answerer, "Q")
        ticker_task.cancel()
        return result, ticks

    result, ticks = asyncio.run(run())

    assert result["answer"] == "answer"
    assert ticks >= 8


def test_ask_response_prepends_extra_context_when_given():
    index = _FakeIndex(context_matches=[_CLOSE_MATCH])
    answerer = _FakeAnswerer(response_text="answer")

    ask_response(index, answerer, "How bulky is Gyarados?", extra_context="Your team: Gyarados")

    question, context_text = answerer.calls[0]
    assert context_text.startswith("Your team: Gyarados")
    assert "Gyarados base HP: 95." in context_text


def test_ask_response_gate_fires_when_best_distance_exceeds_the_threshold():
    far_match = {
        "text": "Some barely related chunk.",
        "metadata": {"pokemon": "Whatever", "chunk_type": "stats"},
        "distance": 1.6,
    }
    index = _FakeIndex(context_matches=[far_match])
    answerer = _FakeAnswerer(response_text="should never be returned")

    result = ask_response(index, answerer, "What is the capital of France?")

    assert result == {"answer": "I don't have solid information on that.", "sources": []}
    assert answerer.calls == []


def test_ask_response_gate_fires_when_there_are_no_matches_at_all():
    index = _FakeIndex(context_matches=[])
    answerer = _FakeAnswerer(response_text="should never be returned")

    result = ask_response(index, answerer, "Anything")

    assert result == {"answer": "I don't have solid information on that.", "sources": []}
    assert answerer.calls == []


def test_ask_response_returns_no_sources_when_the_answerer_reports_offline():
    index = _FakeIndex(context_matches=[_CLOSE_MATCH])
    answerer = _FakeAnswerer(response_text=OFFLINE_MESSAGE)

    result = ask_response(index, answerer, "How bulky is Gyarados?")

    assert result == {"answer": OFFLINE_MESSAGE, "sources": []}


class _FakeIndexWithWhere:
    def __init__(self):
        self.queries = []

    def query(self, text, n_results=5, where=None):
        self.queries.append(where)
        return [
            {
                "text": "context from narrowed query",
                "metadata": {"pokemon": "Abomasnow", "chunk_type": "stats"},
                "distance": 0.3,
            }
        ]


def test_ask_response_narrows_retrieval_when_a_known_pokemon_is_named():
    index = _FakeIndexWithWhere()
    answerer = _FakeAnswerer(response_text="an answer")
    records = [{"name": "Abomasnow"}]

    ask_response(index, answerer, "Does Abomasnow learn Attract?", records=records, items=[])

    assert index.queries == [{"pokemon": "Abomasnow"}]


def test_ask_response_async_narrows_retrieval_when_a_known_pokemon_is_named():
    index = _FakeIndexWithWhere()
    answerer = _FakeAnswerer(response_text="an answer")
    records = [{"name": "Abomasnow"}]

    asyncio.run(ask_response_async(
        index, answerer, "Does Abomasnow learn Attract?", records=records, items=[]
    ))

    assert index.queries == [{"pokemon": "Abomasnow"}]


def test_format_ask_response_includes_a_sources_line_when_sources_are_present():
    result = {"answer": "Gyarados has 95 base HP.", "sources": [{"name": "Gyarados", "chunk_type": "stats"}]}

    formatted = format_ask_response(result)

    assert formatted == "Gyarados has 95 base HP.\n\nSources: Gyarados (stats)"


def test_format_ask_response_joins_multiple_sources():
    result = {
        "answer": "answer text",
        "sources": [
            {"name": "Gyarados", "chunk_type": "stats"},
            {"name": "Life Orb", "chunk_type": "item"},
        ],
    }

    formatted = format_ask_response(result)

    assert formatted == "answer text\n\nSources: Gyarados (stats), Life Orb (item)"


def test_format_ask_response_omits_the_sources_line_when_there_are_none():
    result = {"answer": "I don't have solid information on that.", "sources": []}

    formatted = format_ask_response(result)

    assert formatted == "I don't have solid information on that."
```

- [ ] **Step 2: Run tests to verify the new/changed ones fail**

Run: `pytest tests/test_bot_ask.py -v`
Expected: most FAIL — `ImportError: cannot import name 'format_ask_response'` (module doesn't exist yet), plus `result["answer"]` raising `TypeError` on the current bare-string return.

- [ ] **Step 3: Implement the change**

Replace the full contents of `bot/commands/ask.py`:

```python
import asyncio
from typing import Optional

from rag.answer import OFFLINE_MESSAGE
from rag.retrieve import build_context_block

GATE_MESSAGE = "I don't have solid information on that."

# Empirically tuned against the real embedding index (all-MiniLM-L6-v2) and
# the eval harness's 48-question golden set: every golden question's best
# match distance measured <= 1.3565 (recall@5 = 1.0), while a sample of
# clearly out-of-domain questions ("What is the capital of France?", etc.)
# all measured >= 1.4923. 1.4 sits in that gap, leaning toward the golden
# set's side so real, answerable questions are never falsely gated.
DISTANCE_THRESHOLD = 1.4


def _format_sources(sources: list) -> str:
    return ", ".join(f"{s['name']} ({s['chunk_type']})" for s in sources)


def format_ask_response(result: dict) -> str:
    """Render an ask_response()/ask_response_async() result dict as the
    final display text, with a trailing "Sources: ..." line when sources
    are present."""
    if not result["sources"]:
        return result["answer"]
    return f"{result['answer']}\n\nSources: {_format_sources(result['sources'])}"


def ask_response(
    index,
    answerer,
    question: str,
    records: Optional[list] = None,
    items: Optional[list] = None,
    n_results: int = 5,
    extra_context: Optional[str] = None,
) -> dict:
    context = build_context_block(index, question, records=records, items=items, n_results=n_results)

    if context["best_distance"] is None or context["best_distance"] > DISTANCE_THRESHOLD:
        return {"answer": GATE_MESSAGE, "sources": []}

    context_text = context["text"]
    if extra_context:
        context_text = f"{extra_context}\n\n{context_text}"

    answer = answerer.answer(question, context_text)
    if answer == OFFLINE_MESSAGE:
        return {"answer": answer, "sources": []}

    return {"answer": answer, "sources": context["sources"]}


async def ask_response_async(
    index,
    answerer,
    question: str,
    records: Optional[list] = None,
    items: Optional[list] = None,
    n_results: int = 5,
    extra_context: Optional[str] = None,
) -> dict:
    """Run ask_response in a worker thread so the caller's event loop stays free.

    Both index.query (CPU-bound sentence-transformer encode) and
    answerer.answer (blocking network call) are synchronous; offloading the
    whole call keeps discord.py's event loop responsive during either one.
    """
    return await asyncio.to_thread(
        ask_response, index, answerer, question, records, items, n_results, extra_context
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_bot_ask.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add bot/commands/ask.py tests/test_bot_ask.py
git commit -m "feat: add confidence gate and source attribution to ask_response"
```

---

### Task 3: Wire `format_ask_response` into the `/ask` command handler

**Files:**
- Modify: `bot/main.py` (import line ~10, and the `ask` handler at `bot/main.py:63-72`)
- Test: `tests/test_bot_main.py`

**Interfaces:**
- Consumes: `ask_response_async(...) -> dict` (Task 2), `format_ask_response(result: dict) -> str` (Task 2).
- Produces: nothing new consumed by later tasks.

- [ ] **Step 1: Write the failing test, and fix the one existing test this change breaks**

First, in `tests/test_bot_main.py`, find `test_ask_command_includes_stored_team_context` and replace its `_FakeIndex` class (the one defined inside that test function) with one that returns a close-distance match instead of an empty list — an empty-match index now triggers the new confidence gate, which returns immediately without ever calling the answerer, breaking this test's premise (it currently asserts on `captured["context_block"]`, which is only set when the answerer is actually called):

```python
    class _FakeIndex:
        def query(self, question, n_results=5, where=None):
            return [
                {
                    "text": "Some chunk",
                    "metadata": {"pokemon": "Whatever", "chunk_type": "stats"},
                    "distance": 0.3,
                }
            ]
```

(This replaces the existing `class _FakeIndex: def query(self, question, n_results=5): return []` inside that same test function. Nothing else in that test changes.)

Then add this new test to the same file (it reuses the `_extract_text` helper already defined near the top of `tests/test_bot_main.py`):

```python
def test_ask_command_embed_includes_a_sources_line():
    class _FakeIndex:
        def query(self, question, n_results=5, where=None):
            return [
                {
                    "text": "Landorus-Therian stats chunk",
                    "metadata": {"pokemon": "Landorus-Therian", "chunk_type": "stats"},
                    "distance": 0.3,
                }
            ]

    class _FakeAnswerer:
        def answer(self, question, context_block):
            return "Landorus-Therian has base 91 Speed."

    _client, tree = build_client(index=_FakeIndex(), answerer=_FakeAnswerer())
    ask_command = tree.get_command("ask")
    interaction = MagicMock()
    interaction.user.id = 9100
    interaction.response.defer = AsyncMock()
    interaction.followup.send = AsyncMock()

    asyncio.run(ask_command.callback(interaction, question="How fast is Landorus-Therian?"))

    sent_text = _extract_text(interaction.followup.send)
    assert "Landorus-Therian has base 91 Speed." in sent_text
    assert "Sources: Landorus-Therian (stats)" in sent_text
```

- [ ] **Step 2: Run tests to verify the new one fails and the fixed one still passes for the wrong reason**

Run: `pytest tests/test_bot_main.py -v -k "ask_command"`
Expected: `test_ask_command_embed_includes_a_sources_line` FAILS — `AssertionError` because the embed currently shows the raw dict's `str()` form (e.g. `"{'answer': 'Landorus-Therian has base 91 Speed.', 'sources': [...]}"`), not the formatted text. `test_ask_command_includes_stored_team_context` should still pass (it doesn't check for a sources line), but confirm it does before moving on — if it fails, the fake index fix in Step 1 wasn't applied correctly.

- [ ] **Step 3: Implement the change**

In `bot/main.py`, update the import (currently `from bot.commands.ask import ask_response_async`):

```python
from bot.commands.ask import ask_response_async, format_ask_response
```

Then replace the `ask` function body (currently lines 63-72):

```python
    @tree.command(name="ask", description="Ask a question about VGC Pokemon stats and movesets.")
    @app_commands.checks.cooldown(1, _COOLDOWN_SECONDS)
    async def ask(interaction: discord.Interaction, question: str) -> None:
        await interaction.response.defer()
        user_id = interaction.user.id
        team_blocks = [
            format_team_block(get_team(user_id, "mine"), "Your team"),
            format_team_block(get_team(user_id, "opponent"), "Opponent's team"),
        ]
        extra_context = "\n\n".join(block for block in team_blocks if block) or None
        result = await ask_response_async(
            index, answerer, question, records=records, items=items, extra_context=extra_context
        )
        await interaction.followup.send(embed=_embed("ask", format_ask_response(result)))
```

- [ ] **Step 4: Run the full test_bot_main.py suite to verify nothing else broke**

Run: `pytest tests/test_bot_main.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add bot/main.py tests/test_bot_main.py
git commit -m "feat: render sources line in the /ask command's embed"
```

---

### Task 4: Fix the eval harness's `ask_response` caller

**Files:**
- Modify: `scripts/run_eval.py` (line 21)
- Test: `tests/test_run_eval.py`

**Interfaces:**
- Consumes: `ask_response(index, answerer, question) -> dict` (Task 2, via its `"answer"` key).
- Produces: nothing new consumed by later tasks — this is the plan's final task.

- [ ] **Step 1: Fix the shared test fixture, then run to confirm the real bug**

In `tests/test_run_eval.py`, replace the `_FakeIndex` class (currently `class _FakeIndex: def query(self, text, n_results=5): return []`) with one that returns a close-distance match — like `tests/test_bot_main.py`'s fix in Task 3, an empty-match index now triggers the confidence gate and never calls the answerer at all, which would make every test in this file fail for the wrong reason (the gate's fixed message, not the fake answerer's configured response, would come back):

```python
class _FakeIndex:
    def query(self, text, n_results=5, where=None):
        return [
            {
                "text": "Some context chunk.",
                "metadata": {"pokemon": "Whatever", "chunk_type": "stats"},
                "distance": 0.3,
            }
        ]
```

Run: `pytest tests/test_run_eval.py -v`
Expected: `test_run_answer_quality_marks_a_matching_answer_as_passed`, `test_run_answer_quality_marks_a_wrong_answer_as_failed`, `test_run_answer_quality_flags_the_offline_message_as_its_own_category_not_a_wrong_answer`, and `test_run_answer_quality_handles_set_and_substring_match_types_too` all FAIL — `run_answer_quality` still does `actual = ask_response(index, answerer, entry["question"])`, so `actual` is now a dict; `actual == OFFLINE_MESSAGE` is always `False` and `matches(actual, ...)` receives a dict where a string is expected. `test_print_report_runs_without_error_on_a_mixed_result_set` is unaffected (it doesn't call `run_answer_quality`) and should still pass.

- [ ] **Step 2: Implement the fix**

In `scripts/run_eval.py`, change line 21 from:

```python
        actual = ask_response(index, answerer, entry["question"])
```

to:

```python
        actual = ask_response(index, answerer, entry["question"])["answer"]
```

- [ ] **Step 3: Run tests to verify they pass**

Run: `pytest tests/test_run_eval.py -v`
Expected: all PASS.

- [ ] **Step 4: Run the entire test suite as a final check**

Run: `pytest -q`
Expected: all tests PASS (315 pre-existing + this plan's new/changed tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/run_eval.py tests/test_run_eval.py
git commit -m "fix: read ask_response's new dict return shape in the eval harness"
```

---

## Self-review notes

- **Spec coverage:** source attribution (Task 1's `sources`, Task 2's threading + `format_ask_response`, Task 3's embed rendering), the confidence gate including the explicit `None`-before-comparison check (Task 2), the three-outcome return-shape contract — normal/gate-fired/offline-degraded, all as a dict (Task 2), the silent-embed-stringification failure mode called out in the spec's "Source attribution" section (Task 3's new test specifically guards against this), and the real, non-test caller in `scripts/run_eval.py` the spec doesn't mention but that a full-codebase grep found (Task 4) — all covered.
- **Out-of-scope items** (per-sentence citation, a learned confidence model, raw distance scores to users) are correctly not touched by any task.
- **Threshold:** derived empirically against the real index and real golden set rather than shipped as a placeholder, since both now exist (unlike when the spec was written) — see the "Distance threshold" section above.
- **Type/name consistency checked:** `build_context_block`'s return dict keys (`text`/`sources`/`best_distance`) match exactly what Task 2 reads; `ask_response`/`ask_response_async`'s return dict keys (`answer`/`sources`) match exactly what Task 3's `format_ask_response` call and Task 4's `["answer"]` read expect; `GATE_MESSAGE`'s exact string (`"I don't have solid information on that."`) is identical everywhere it's asserted (Task 2's tests, this doc).
- **Breaking-change fallout audited:** grepped the full non-test codebase for every call site of `build_context_block`/`ask_response`/`ask_response_async` — exactly three real call sites exist (`bot/commands/ask.py` itself, `bot/main.py`, `scripts/run_eval.py`) and all three are covered by a task. Also audited every existing test fixture across `tests/test_rag_retrieve.py`, `tests/test_bot_ask.py`, `tests/test_bot_main.py`, and `tests/test_run_eval.py` for fake indexes returning empty matches or matches without a `"distance"`/`"chunk_type"` key, since those would now interact with the new gate/sources logic in ways the old tests never exercised — each affected fixture is called out explicitly in its task.
