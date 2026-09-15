# Observability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Log every `/ask` call to a local SQLite database (question, retrieved chunks + distances, sources, gate/degraded flags, latency) and add an owner-only `/debug-last` command to inspect the most recent call, so a bad answer is debuggable instead of leaving no trace.

**Architecture:** A new `rag/observability.py` module wraps stdlib `sqlite3` with two pure, injectable functions: `log_ask(...)` (write) and `get_last_ask_log(...)` (read the most recent row). `build_context_block`/`ask_response`/`ask_response_async` (already returning a dict shape from `[[grounding-trust]]`, already shipped) gain one more field each — `retrieved_chunks`, a list of `{"id", "distance"}` per retrieved chunk — since that's the one piece of data `log_ask` needs that the current return shape doesn't carry (it has `sources`/`best_distance` already, but not per-chunk IDs). `bot/main.py`'s `/ask` handler times the whole `ask_response_async` call, derives `gate_fired`/`degraded` via string-sentinel comparison (same pattern the codebase already uses for `OFFLINE_MESSAGE`), and calls `log_ask` wrapped in a bare `try/except` so a logging failure never blocks the user's answer. A new `bot/commands/debug.py` holds the pure formatting logic for `/debug-last`, gated by a new `BOT_OWNER_ID`-checking predicate in `bot/main.py`.

**Tech Stack:** Python 3.9, stdlib `sqlite3` and `json`. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-09-13-observability-design.md`

## Global Constraints

- No new dependencies — stdlib `sqlite3`/`json` only, consistent with this project's zero-cost, zero-new-infrastructure default.
- `log_ask(...)` takes `timestamp` as a parameter, never calling `datetime.now()` internally — keeps it pure/injectable for tests (mirrors this project's existing pattern of injected clients over hidden globals, e.g. `SentenceTransformerEmbedder`'s injected `model`).
- Logging failures must never propagate to the user — wrapped in `try: ... except Exception: pass` at the call site, not inside `log_ask` itself.
- `degraded` is derived via string equality against `rag.answer.OFFLINE_MESSAGE`, not any other mechanism (spec's explicit "Deriving `degraded`" section) — this plan derives `gate_fired` the identical way, against `bot.commands.ask.GATE_MESSAGE`, for consistency (spec doesn't specify a different mechanism for `gate_fired`, and no other signal is available at the call site).
- `latency_ms` wraps the *entire* `ask_response_async` call (retrieval + LLM combined), not just the Ollama call in isolation (spec's explicit "Deriving `latency_ms`" section).
- `/debug-last` is gated by comparing `interaction.user.id` against a `BOT_OWNER_ID` environment variable, via an `app_commands.check`-style predicate — not `commands.Bot.is_owner()`, which isn't available (`bot/main.py` uses a bare `discord.Client` + separate `CommandTree`, not `commands.Bot`/`AutoShardedBot`).
- `data/observability.db` must be added to `.gitignore` (currently only lists `data/chroma/` and `data/state/`).

---

## File structure

- Create `rag/observability.py` — `log_ask(...)` (write one row) and `get_last_ask_log(...)` (read the most recent row), both taking an injectable `db_path` parameter defaulting to `data/observability.db`.
- Modify `.gitignore` — add `data/observability.db`.
- Modify `rag/retrieve.py` — `build_context_block` gains a `"retrieved_chunks"` key in its returned dict.
- Modify `bot/commands/ask.py` — `ask_response`/`ask_response_async` gain two new keys in their returned dict: `retrieved_chunks` and `best_distance` (currently only `answer`/`sources` are returned; `best_distance` is computed internally by `build_context_block` today but discarded once `ask_response` builds its own return value — `log_ask` needs both, and neither is derivable externally).
- Modify `tests/test_rag_retrieve.py`, `tests/test_bot_ask.py` (full rewrites), `tests/test_bot_main.py`, `tests/test_run_eval.py` (targeted edits) — every existing fake index fixture that returns a match dict needs an `"id"` key added, since `build_context_block` now reads `match["id"]` for every match (previously unused).
- Create `bot/commands/debug.py` — `format_debug_last(row: Optional[dict]) -> str`, the pure formatting logic for `/debug-last`, following this project's established pattern (`bot/commands/ping.py`, `bot/commands/stats.py`, etc. hold pure response-building functions; `bot/main.py` wires them into `tree.command` handlers).
- Create `tests/test_bot_debug.py` — tests for `format_debug_last` (matches the naming convention of `tests/test_bot_stats.py` for `bot/commands/stats.py`, etc.).
- Modify `bot/main.py` — imports `time`, `datetime`/`timezone`, `GATE_MESSAGE` (from `bot.commands.ask`), `OFFLINE_MESSAGE` (from `rag.answer`), `log_ask`/`get_last_ask_log` (from `rag.observability`), `format_debug_last` (from `bot.commands.debug`); the `ask` handler times the call and logs it; a new `_owner_only` predicate function and a new `/debug-last` command are added.
- Modify `.env.example` — document the new `BOT_OWNER_ID` variable.
- Modify `tests/test_bot_main.py` — new tests for the logging call, the failure-swallowing behavior, the owner-only predicate, and the `/debug-last` command body.
- Create `tests/test_rag_observability.py` — tests for `log_ask`/`get_last_ask_log`.

---

### Task 1: `rag/observability.py` — SQLite logging module

**Files:**
- Create: `rag/observability.py`
- Modify: `.gitignore`
- Test: `tests/test_rag_observability.py`

**Interfaces:**
- Consumes: nothing new (stdlib `sqlite3`/`json` only).
- Produces: `log_ask(timestamp, question, retrieved_chunks, sources, best_distance, gate_fired, answer, degraded, latency_ms, db_path=DEFAULT_DB_PATH) -> None` and `get_last_ask_log(db_path=DEFAULT_DB_PATH) -> Optional[dict]`, returning a dict with keys `timestamp`/`question`/`retrieved_chunks`/`sources`/`best_distance`/`gate_fired`/`answer`/`degraded`/`latency_ms` (with `retrieved_chunks`/`sources` deserialized back to Python lists, `gate_fired`/`degraded` as real `bool`s). Task 3 calls both; Task 4 calls `get_last_ask_log`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_rag_observability.py`:

```python
from rag.observability import get_last_ask_log, log_ask


def test_log_ask_writes_a_row_and_get_last_ask_log_reads_it_back(tmp_path):
    db_path = str(tmp_path / "observability.db")

    log_ask(
        timestamp="2026-09-14T12:00:00+00:00",
        question="Does Gyarados learn Waterfall?",
        retrieved_chunks=[{"id": "Gyarados-moveset", "distance": 0.4}],
        sources=[{"name": "Gyarados", "chunk_type": "moveset"}],
        best_distance=0.4,
        gate_fired=False,
        answer="Yes, Gyarados learns Waterfall.",
        degraded=False,
        latency_ms=1234,
        db_path=db_path,
    )

    row = get_last_ask_log(db_path=db_path)

    assert row["timestamp"] == "2026-09-14T12:00:00+00:00"
    assert row["question"] == "Does Gyarados learn Waterfall?"
    assert row["retrieved_chunks"] == [{"id": "Gyarados-moveset", "distance": 0.4}]
    assert row["sources"] == [{"name": "Gyarados", "chunk_type": "moveset"}]
    assert row["best_distance"] == 0.4
    assert row["gate_fired"] is False
    assert row["answer"] == "Yes, Gyarados learns Waterfall."
    assert row["degraded"] is False
    assert row["latency_ms"] == 1234


def test_get_last_ask_log_returns_none_when_the_table_is_empty(tmp_path):
    db_path = str(tmp_path / "observability.db")

    row = get_last_ask_log(db_path=db_path)

    assert row is None


def test_get_last_ask_log_returns_the_most_recently_logged_row(tmp_path):
    db_path = str(tmp_path / "observability.db")

    log_ask(
        timestamp="2026-09-14T12:00:00+00:00", question="First question?",
        retrieved_chunks=[], sources=[], best_distance=None, gate_fired=True,
        answer="I don't have solid information on that.", degraded=False, latency_ms=50,
        db_path=db_path,
    )
    log_ask(
        timestamp="2026-09-14T12:05:00+00:00", question="Second question?",
        retrieved_chunks=[{"id": "Absol-stats", "distance": 0.3}],
        sources=[{"name": "Absol", "chunk_type": "stats"}], best_distance=0.3, gate_fired=False,
        answer="Second answer.", degraded=False, latency_ms=900,
        db_path=db_path,
    )

    row = get_last_ask_log(db_path=db_path)

    assert row["question"] == "Second question?"


def test_log_ask_creates_the_table_if_it_does_not_exist_yet(tmp_path):
    db_path = str(tmp_path / "brand_new.db")

    log_ask(
        timestamp="2026-09-14T12:00:00+00:00", question="Q?", retrieved_chunks=[], sources=[],
        best_distance=None, gate_fired=True, answer="A", degraded=False, latency_ms=10,
        db_path=db_path,
    )

    row = get_last_ask_log(db_path=db_path)
    assert row is not None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_rag_observability.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'rag.observability'`.

- [ ] **Step 3: Implement `rag/observability.py`**

```python
import json
import sqlite3
from typing import Optional

DEFAULT_DB_PATH = "data/observability.db"

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS ask_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    question TEXT NOT NULL,
    retrieved_chunks TEXT NOT NULL,
    sources TEXT,
    best_distance REAL,
    gate_fired INTEGER NOT NULL,
    answer TEXT,
    degraded INTEGER NOT NULL,
    latency_ms INTEGER NOT NULL
)
"""


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute(_CREATE_TABLE_SQL)
    return conn


def log_ask(
    timestamp: str,
    question: str,
    retrieved_chunks: list,
    sources: list,
    best_distance: Optional[float],
    gate_fired: bool,
    answer: str,
    degraded: bool,
    latency_ms: int,
    db_path: str = DEFAULT_DB_PATH,
) -> None:
    conn = _connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO ask_log
                (timestamp, question, retrieved_chunks, sources, best_distance, gate_fired, answer, degraded, latency_ms)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                timestamp,
                question,
                json.dumps(retrieved_chunks),
                json.dumps(sources),
                best_distance,
                int(gate_fired),
                answer,
                int(degraded),
                latency_ms,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def get_last_ask_log(db_path: str = DEFAULT_DB_PATH) -> Optional[dict]:
    conn = _connect(db_path)
    try:
        cursor = conn.execute(
            "SELECT timestamp, question, retrieved_chunks, sources, best_distance, "
            "gate_fired, answer, degraded, latency_ms FROM ask_log ORDER BY id DESC LIMIT 1"
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return {
            "timestamp": row[0],
            "question": row[1],
            "retrieved_chunks": json.loads(row[2]),
            "sources": json.loads(row[3]) if row[3] is not None else [],
            "best_distance": row[4],
            "gate_fired": bool(row[5]),
            "answer": row[6],
            "degraded": bool(row[7]),
            "latency_ms": row[8],
        }
    finally:
        conn.close()
```

- [ ] **Step 4: Add `data/observability.db` to `.gitignore`**

The current file reads:
```
.venv/
__pycache__/
*.pyc
.pytest_cache/
.env
data/chroma/
data/state/
.vscode/

.worktrees/
```

Add one line, `data/observability.db`, alongside the other `data/` entries:
```
.venv/
__pycache__/
*.pyc
.pytest_cache/
.env
data/chroma/
data/state/
data/observability.db
.vscode/

.worktrees/
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pytest tests/test_rag_observability.py -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add rag/observability.py tests/test_rag_observability.py .gitignore
git commit -m "feat: add SQLite logging for /ask calls"
```

---

### Task 2: Thread `retrieved_chunks` (and `best_distance`) through `build_context_block`/`ask_response`

**Files:**
- Modify: `rag/retrieve.py` (full file)
- Modify: `bot/commands/ask.py` (full file)
- Modify: `tests/test_rag_retrieve.py` (full rewrite)
- Modify: `tests/test_bot_ask.py` (full rewrite)
- Modify: `tests/test_bot_main.py` (3 targeted edits, given below)
- Modify: `tests/test_run_eval.py` (1 targeted edit, given below)

**Interfaces:**
- Consumes: nothing new.
- Produces: `build_context_block(...)`'s returned dict gains `"retrieved_chunks"` (list of `{"id": str, "distance": float}`, one per retrieved chunk, in the same order as `"sources"`). `ask_response`/`ask_response_async`'s returned dict gains `"retrieved_chunks"` and `"best_distance"` in ALL THREE outcomes (normal, gate-fired, offline-degraded) — so the full returned dict shape is now `{"answer": str, "sources": list, "retrieved_chunks": list, "best_distance": float|None}`. Task 3 reads `result["retrieved_chunks"]` and `result["best_distance"]` from `ask_response_async`'s return.

**Why this task exists:** `log_ask` (Task 1) needs a per-chunk `{"id", "distance"}` list and the overall `best_distance` — `build_context_block` already computes `best_distance` internally but discards it once `ask_response` builds its return dict, and neither function currently exposes per-chunk IDs at all (`"sources"` only has `name`/`chunk_type`, no `"id"`). Since `ChromaIndex.query`'s real match dicts always include an `"id"` key (`rag/store.py`), this task's code accesses `match["id"]` directly (no `.get()`) — consistent with how `match["metadata"]["chunk_type"]` is already accessed directly elsewhere in this same function. That means every existing test fixture across the whole test suite that constructs a fake match dict needs an `"id"` key added, or this code will raise `KeyError` when exercised through those fixtures. This task fixes every one of them.

- [ ] **Step 1: Write the failing tests — `tests/test_rag_retrieve.py`**

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
                "id": "Gyarados-stats",
                "text": "Gyarados is a Water/Flying-type Pokemon.",
                "metadata": {"pokemon": "Gyarados", "chunk_type": "stats"},
                "distance": 0.4,
            },
            {
                "id": "Gyarados-moveset",
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
    assert result["retrieved_chunks"] == []


def test_build_context_block_returns_sources_from_matched_chunk_metadata():
    index = _FakeIndex(
        matches=[
            {
                "id": "Gyarados-stats",
                "text": "Gyarados is a Water/Flying-type Pokemon.",
                "metadata": {"pokemon": "Gyarados", "chunk_type": "stats"},
                "distance": 0.4,
            },
            {
                "id": "item-Life Orb",
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


def test_build_context_block_returns_retrieved_chunks_with_ids_and_distances():
    index = _FakeIndex(
        matches=[
            {
                "id": "Gyarados-stats",
                "text": "Gyarados is a Water/Flying-type Pokemon.",
                "metadata": {"pokemon": "Gyarados", "chunk_type": "stats"},
                "distance": 0.4,
            },
            {
                "id": "item-Life Orb",
                "text": "Life Orb: Boosts move power.",
                "metadata": {"item": "Life Orb", "chunk_type": "item"},
                "distance": 0.6,
            },
        ]
    )

    result = build_context_block(index, "How bulky is Gyarados?")

    assert result["retrieved_chunks"] == [
        {"id": "Gyarados-stats", "distance": 0.4},
        {"id": "item-Life Orb", "distance": 0.6},
    ]


def test_build_context_block_returns_the_smallest_distance_as_best_distance():
    index = _FakeIndex(
        matches=[
            {"id": "a-stats", "text": "a", "metadata": {"pokemon": "A", "chunk_type": "stats"}, "distance": 0.9},
            {"id": "b-stats", "text": "b", "metadata": {"pokemon": "B", "chunk_type": "stats"}, "distance": 0.3},
            {"id": "c-stats", "text": "c", "metadata": {"pokemon": "C", "chunk_type": "stats"}, "distance": 0.7},
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
            "id": "Abomasnow-stats",
            "text": "Abomasnow stats chunk",
            "metadata": {"pokemon": "Abomasnow", "chunk_type": "stats"},
            "distance": 0.4,
        },
        {
            "id": "Gyarados-stats",
            "text": "Unrelated Gyarados chunk",
            "metadata": {"pokemon": "Gyarados", "chunk_type": "stats"},
            "distance": 0.5,
        },
    ])

    build_context_block(index, "Does Abomasnow learn Attract?", records=_RECORDS, items=_ITEMS)

    assert index.queries[0]["where"] == {"pokemon": "Abomasnow"}


def test_build_context_block_falls_back_to_unfiltered_when_no_entity_detected():
    index = _FakeIndexWithWhere(matches=[
        {
            "id": "Whatever-stats",
            "text": "Some chunk",
            "metadata": {"pokemon": "Whatever", "chunk_type": "stats"},
            "distance": 0.5,
        },
    ])

    build_context_block(index, "What is the weather like?", records=_RECORDS, items=_ITEMS)

    assert index.queries[0]["where"] is None


def test_build_context_block_falls_back_to_unfiltered_when_filtered_query_returns_nothing():
    index = _FakeIndexWithWhere(matches=[
        {
            "id": "item-Some Item",
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
Expected: `test_build_context_block_returns_empty_text_sources_and_distance_for_no_matches` and `test_build_context_block_returns_retrieved_chunks_with_ids_and_distances` FAIL — `KeyError: 'retrieved_chunks'` (the dict doesn't have that key yet).

- [ ] **Step 3: Implement `rag/retrieve.py`**

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
        "retrieved_chunks": [
            {"id": match["id"], "distance": match["distance"]} for match in matches
        ],
        "best_distance": min((match["distance"] for match in matches), default=None),
    }
```

- [ ] **Step 4: Write the failing tests — `tests/test_bot_ask.py`**

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
    "id": "Gyarados-stats",
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


def test_ask_response_returns_retrieved_chunks_and_best_distance_from_the_matched_chunks():
    index = _FakeIndex(context_matches=[_CLOSE_MATCH])
    answerer = _FakeAnswerer(response_text="Gyarados has 95 base HP.")

    result = ask_response(index, answerer, "How bulky is Gyarados?")

    assert result["retrieved_chunks"] == [{"id": "Gyarados-stats", "distance": 0.4}]
    assert result["best_distance"] == 0.4


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
        "id": "Whatever-stats",
        "text": "Some barely related chunk.",
        "metadata": {"pokemon": "Whatever", "chunk_type": "stats"},
        "distance": 1.6,
    }
    index = _FakeIndex(context_matches=[far_match])
    answerer = _FakeAnswerer(response_text="should never be returned")

    result = ask_response(index, answerer, "What is the capital of France?")

    assert result == {
        "answer": "I don't have solid information on that.",
        "sources": [],
        "retrieved_chunks": [{"id": "Whatever-stats", "distance": 1.6}],
        "best_distance": 1.6,
    }
    assert answerer.calls == []


def test_ask_response_gate_fires_when_there_are_no_matches_at_all():
    index = _FakeIndex(context_matches=[])
    answerer = _FakeAnswerer(response_text="should never be returned")

    result = ask_response(index, answerer, "Anything")

    assert result == {
        "answer": "I don't have solid information on that.",
        "sources": [],
        "retrieved_chunks": [],
        "best_distance": None,
    }
    assert answerer.calls == []


def test_ask_response_gate_is_bypassed_when_extra_context_is_provided():
    far_match = {
        "id": "Whatever-stats",
        "text": "Some barely related chunk.",
        "metadata": {"pokemon": "Whatever", "chunk_type": "stats"},
        "distance": 1.6,
    }
    index = _FakeIndex(context_matches=[far_match])
    answerer = _FakeAnswerer(response_text="Here's some strategy advice.")

    result = ask_response(
        index, answerer, "What should I lead with?", extra_context="Your team: Gyarados, Garchomp"
    )

    assert result["answer"] == "Here's some strategy advice."
    assert len(answerer.calls) == 1
    question, context_text = answerer.calls[0]
    assert context_text.startswith("Your team: Gyarados, Garchomp")


def test_ask_response_does_not_gate_when_best_distance_is_exactly_the_threshold():
    boundary_match = {
        "id": "Whatever-stats",
        "text": "Some chunk.",
        "metadata": {"pokemon": "Whatever", "chunk_type": "stats"},
        "distance": 1.4,
    }
    index = _FakeIndex(context_matches=[boundary_match])
    answerer = _FakeAnswerer(response_text="An answer.")

    result = ask_response(index, answerer, "A question")

    assert result["answer"] == "An answer."
    assert answerer.calls != []


def test_ask_response_returns_no_sources_when_the_answerer_reports_offline():
    index = _FakeIndex(context_matches=[_CLOSE_MATCH])
    answerer = _FakeAnswerer(response_text=OFFLINE_MESSAGE)

    result = ask_response(index, answerer, "How bulky is Gyarados?")

    assert result == {
        "answer": OFFLINE_MESSAGE,
        "sources": [],
        "retrieved_chunks": [{"id": "Gyarados-stats", "distance": 0.4}],
        "best_distance": 0.4,
    }
    assert answerer.calls != []  # confirms the LLM WAS called -- distinct from the gate-fired path, where it never is


class _FakeIndexWithWhere:
    def __init__(self):
        self.queries = []

    def query(self, text, n_results=5, where=None):
        self.queries.append(where)
        return [
            {
                "id": "Abomasnow-stats",
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

- [ ] **Step 5: Run tests to verify the changed ones fail**

Run: `pytest tests/test_bot_ask.py -v`
Expected: `test_ask_response_returns_retrieved_chunks_and_best_distance_from_the_matched_chunks`, `test_ask_response_gate_fires_when_best_distance_exceeds_the_threshold`, `test_ask_response_gate_fires_when_there_are_no_matches_at_all`, and `test_ask_response_returns_no_sources_when_the_answerer_reports_offline` FAIL (either `KeyError` or dict-equality mismatch, since the current code doesn't return `retrieved_chunks`/`best_distance` yet).

- [ ] **Step 6: Implement `bot/commands/ask.py`**

Replace the full contents of `bot/commands/ask.py`:

```python
import asyncio
from typing import Optional

from rag.answer import OFFLINE_MESSAGE
from rag.retrieve import build_context_block

GATE_MESSAGE = "I don't have solid information on that."

# Empirically tuned against the real embedding index (all-MiniLM-L6-v2) and
# the eval harness's 48-question golden set: every golden question's best
# match distance measured <= 1.3565 -- this is the hard, reproducible
# ceiling (re-derive it by running the golden set through
# build_context_block if the embedding model or Chroma's distance metric
# ever changes; see tests/test_eval_retrieval.py's
# test_golden_set_best_distances_stay_under_the_confidence_gate_threshold,
# which guards this automatically). A sample of out-of-domain questions
# ("What is the capital of France?", etc.) measured as low as ~1.42 in one
# sample, so the margin above 1.4 is thin, not a wide gap -- 1.4 was chosen
# to sit just above the golden set's ceiling, favoring never gating a real
# answerable question over catching every possible out-of-domain one.
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

    if not extra_context and (context["best_distance"] is None or context["best_distance"] > DISTANCE_THRESHOLD):
        return {
            "answer": GATE_MESSAGE,
            "sources": [],
            "retrieved_chunks": context["retrieved_chunks"],
            "best_distance": context["best_distance"],
        }

    context_text = context["text"]
    if extra_context:
        context_text = f"{extra_context}\n\n{context_text}"

    answer = answerer.answer(question, context_text)
    if answer == OFFLINE_MESSAGE:
        return {
            "answer": answer,
            "sources": [],
            "retrieved_chunks": context["retrieved_chunks"],
            "best_distance": context["best_distance"],
        }

    return {
        "answer": answer,
        "sources": context["sources"],
        "retrieved_chunks": context["retrieved_chunks"],
        "best_distance": context["best_distance"],
    }


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

- [ ] **Step 7: Run tests to verify they pass**

Run: `pytest tests/test_rag_retrieve.py tests/test_bot_ask.py -v`
Expected: all PASS.

- [ ] **Step 8: Fix the 3 remaining fixtures in `tests/test_bot_main.py`**

Find and apply these 3 exact edits (each adds an `"id"` key to a match dict that currently lacks one):

**Edit 1** — in `test_ask_command_includes_stored_team_context`, find:
```python
    class _FakeIndex:
        def query(self, question, n_results=5, where=None):
            return [
                {
                    "text": "Some chunk",
                    "metadata": {"pokemon": "Whatever", "chunk_type": "stats"},
                    "distance": 1.6,
                }
            ]
```
Replace with:
```python
    class _FakeIndex:
        def query(self, question, n_results=5, where=None):
            return [
                {
                    "id": "Whatever-stats",
                    "text": "Some chunk",
                    "metadata": {"pokemon": "Whatever", "chunk_type": "stats"},
                    "distance": 1.6,
                }
            ]
```

**Edit 2** — in `test_ask_command_narrows_retrieval_when_a_known_pokemon_is_named`, find:
```python
            return [{"text": "context from narrowed query", "metadata": {"chunk_type": "stats"}, "distance": 0.3}]
```
Replace with:
```python
            return [
                {
                    "id": "Abomasnow-stats",
                    "text": "context from narrowed query",
                    "metadata": {"chunk_type": "stats"},
                    "distance": 0.3,
                }
            ]
```

**Edit 3** — in `test_ask_command_embed_includes_a_sources_line`, find:
```python
    class _FakeIndex:
        def query(self, question, n_results=5, where=None):
            return [
                {
                    "text": "Landorus-Therian stats chunk",
                    "metadata": {"pokemon": "Landorus-Therian", "chunk_type": "stats"},
                    "distance": 0.3,
                }
            ]
```
Replace with:
```python
    class _FakeIndex:
        def query(self, question, n_results=5, where=None):
            return [
                {
                    "id": "Landorus-Therian-stats",
                    "text": "Landorus-Therian stats chunk",
                    "metadata": {"pokemon": "Landorus-Therian", "chunk_type": "stats"},
                    "distance": 0.3,
                }
            ]
```

- [ ] **Step 9: Fix the 1 remaining fixture in `tests/test_run_eval.py`**

Find:
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
Replace with:
```python
class _FakeIndex:
    def query(self, text, n_results=5, where=None):
        return [
            {
                "id": "Whatever-stats",
                "text": "Some context chunk.",
                "metadata": {"pokemon": "Whatever", "chunk_type": "stats"},
                "distance": 0.3,
            }
        ]
```

- [ ] **Step 10: Run the entire test suite to verify nothing else broke**

Run: `pytest -q`
Expected: all PASS.

- [ ] **Step 11: Commit**

```bash
git add rag/retrieve.py bot/commands/ask.py tests/test_rag_retrieve.py tests/test_bot_ask.py tests/test_bot_main.py tests/test_run_eval.py
git commit -m "feat: thread retrieved_chunks and best_distance through ask_response"
```

---

### Task 3: Wire `log_ask` into the `/ask` command handler

**Files:**
- Modify: `bot/main.py` (imports at the top, and the `ask` handler at `bot/main.py:63-72` per the pre-Task-2 line numbers — re-locate it by function name, since Task 2 didn't change this file)
- Test: `tests/test_bot_main.py`

**Interfaces:**
- Consumes: `log_ask(...)` (Task 1), `ask_response_async(...) -> dict` with `retrieved_chunks`/`sources`/`best_distance`/`answer` keys (Task 2), `bot.commands.ask.GATE_MESSAGE` (already exists), `rag.answer.OFFLINE_MESSAGE` (already exists, not yet imported into `bot/main.py`).
- Produces: nothing new consumed by later tasks.

- [ ] **Step 1: Write the failing tests**

Add these two tests to `tests/test_bot_main.py` (reuses the `asyncio`, `AsyncMock`, `MagicMock` imports already at the top of that file):

```python
def test_ask_command_logs_the_call_via_log_ask(monkeypatch):
    calls = []

    def _fake_log_ask(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr("bot.main.log_ask", _fake_log_ask)

    class _FakeIndex:
        def query(self, question, n_results=5, where=None):
            return [
                {
                    "id": "Gyarados-stats",
                    "text": "Gyarados stats chunk",
                    "metadata": {"pokemon": "Gyarados", "chunk_type": "stats"},
                    "distance": 0.3,
                }
            ]

    class _FakeAnswerer:
        def answer(self, question, context_block):
            return "Gyarados has 95 base HP."

    _client, tree = build_client(index=_FakeIndex(), answerer=_FakeAnswerer())
    ask_command = tree.get_command("ask")
    interaction = MagicMock()
    interaction.user.id = 9200
    interaction.response.defer = AsyncMock()
    interaction.followup.send = AsyncMock()

    asyncio.run(ask_command.callback(interaction, question="How bulky is Gyarados?"))

    assert len(calls) == 1
    logged = calls[0]
    assert logged["question"] == "How bulky is Gyarados?"
    assert logged["answer"] == "Gyarados has 95 base HP."
    assert logged["retrieved_chunks"] == [{"id": "Gyarados-stats", "distance": 0.3}]
    assert logged["sources"] == [{"name": "Gyarados", "chunk_type": "stats"}]
    assert logged["best_distance"] == 0.3
    assert logged["gate_fired"] is False
    assert logged["degraded"] is False
    assert isinstance(logged["latency_ms"], int)
    assert isinstance(logged["timestamp"], str)


def test_ask_command_still_sends_the_answer_when_log_ask_raises(monkeypatch):
    def _raising_log_ask(**kwargs):
        raise RuntimeError("disk full")

    monkeypatch.setattr("bot.main.log_ask", _raising_log_ask)

    class _FakeIndex:
        def query(self, question, n_results=5, where=None):
            return [
                {
                    "id": "Gyarados-stats",
                    "text": "Gyarados stats chunk",
                    "metadata": {"pokemon": "Gyarados", "chunk_type": "stats"},
                    "distance": 0.3,
                }
            ]

    class _FakeAnswerer:
        def answer(self, question, context_block):
            return "Gyarados has 95 base HP."

    _client, tree = build_client(index=_FakeIndex(), answerer=_FakeAnswerer())
    ask_command = tree.get_command("ask")
    interaction = MagicMock()
    interaction.user.id = 9201
    interaction.response.defer = AsyncMock()
    interaction.followup.send = AsyncMock()

    asyncio.run(ask_command.callback(interaction, question="How bulky is Gyarados?"))

    sent_text = _extract_text(interaction.followup.send)
    assert "Gyarados has 95 base HP." in sent_text
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_bot_main.py -v -k "logs_the_call or log_ask_raises"`
Expected: both FAIL — `AttributeError: <module 'bot.main'> does not have the attribute 'log_ask'` (not imported yet).

- [ ] **Step 3: Implement the change**

In `bot/main.py`, update the imports at the top of the file. Add these lines (alongside the existing imports, in the same style):

```python
import time
from datetime import datetime, timezone
```

Change the existing `from bot.commands.ask import ask_response_async, format_ask_response` line to:

```python
from bot.commands.ask import GATE_MESSAGE, ask_response_async, format_ask_response
```

Change the existing `from rag.answer import OllamaAnswerer` line to:

```python
from rag.answer import OFFLINE_MESSAGE, OllamaAnswerer
```

Add this new import line (with the other `rag.*` imports):

```python
from rag.observability import log_ask
```

Then replace the `ask` function body (find it by its `@tree.command(name="ask", ...)` decorator):

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
        start_time = time.monotonic()
        result = await ask_response_async(
            index, answerer, question, records=records, items=items, extra_context=extra_context
        )
        latency_ms = int((time.monotonic() - start_time) * 1000)
        try:
            log_ask(
                timestamp=datetime.now(timezone.utc).isoformat(),
                question=question,
                retrieved_chunks=result["retrieved_chunks"],
                sources=result["sources"],
                best_distance=result["best_distance"],
                gate_fired=result["answer"] == GATE_MESSAGE,
                answer=result["answer"],
                degraded=result["answer"] == OFFLINE_MESSAGE,
                latency_ms=latency_ms,
            )
        except Exception:
            pass  # observability is best-effort; never blocks the answer
        await interaction.followup.send(embed=_embed("ask", format_ask_response(result)))
```

- [ ] **Step 4: Run the full test_bot_main.py suite to verify nothing else broke**

Run: `pytest tests/test_bot_main.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add bot/main.py tests/test_bot_main.py
git commit -m "feat: log every /ask call via log_ask"
```

---

### Task 4: `/debug-last` admin command

**Files:**
- Create: `bot/commands/debug.py`
- Test: `tests/test_bot_debug.py`
- Modify: `bot/main.py` (imports, `_COMMAND_COLORS`, a new `_owner_only` function, a new `/debug-last` command registration)
- Modify: `.env.example`
- Test: `tests/test_bot_main.py`

**Interfaces:**
- Consumes: `get_last_ask_log(...)` (Task 1, already returns the exact dict shape `format_debug_last` expects).
- Produces: `format_debug_last(row: Optional[dict]) -> str`. Nothing later consumes this — final task in the plan.

- [ ] **Step 1: Write the failing tests — `bot/commands/debug.py`**

Create `tests/test_bot_debug.py`:

```python
from bot.commands.debug import format_debug_last


def test_format_debug_last_reports_plainly_when_nothing_logged():
    formatted = format_debug_last(None)

    assert formatted == "No /ask calls logged yet."


def test_format_debug_last_renders_a_full_row():
    row = {
        "timestamp": "2026-09-14T12:00:00+00:00",
        "question": "How bulky is Gyarados?",
        "answer": "Gyarados has 95 base HP.",
        "sources": [{"name": "Gyarados", "chunk_type": "stats"}],
        "retrieved_chunks": [{"id": "Gyarados-stats", "distance": 0.4}],
        "best_distance": 0.4,
        "gate_fired": False,
        "degraded": False,
        "latency_ms": 900,
    }

    formatted = format_debug_last(row)

    assert "How bulky is Gyarados?" in formatted
    assert "Gyarados has 95 base HP." in formatted
    assert "Gyarados (stats)" in formatted
    assert "Gyarados-stats (distance 0.4000)" in formatted
    assert "0.4000" in formatted
    assert "False" in formatted
    assert "900" in formatted


def test_format_debug_last_shows_none_for_empty_sources_and_chunks():
    row = {
        "timestamp": "2026-09-14T12:00:00+00:00",
        "question": "What is the capital of France?",
        "answer": "I don't have solid information on that.",
        "sources": [],
        "retrieved_chunks": [],
        "best_distance": None,
        "gate_fired": True,
        "degraded": False,
        "latency_ms": 50,
    }

    formatted = format_debug_last(row)

    assert "**Sources:** none" in formatted
    assert "**Retrieved chunks:** none" in formatted
    assert "**Best distance:** none" in formatted
    assert "**Gate fired:** True" in formatted
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_bot_debug.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bot.commands.debug'`.

- [ ] **Step 3: Implement `bot/commands/debug.py`**

```python
from typing import Optional


def format_debug_last(row: Optional[dict]) -> str:
    """Render the most recent ask_log row (from
    rag.observability.get_last_ask_log) for the /debug-last admin command."""
    if row is None:
        return "No /ask calls logged yet."

    if row["sources"]:
        sources_text = ", ".join(f"{s['name']} ({s['chunk_type']})" for s in row["sources"])
    else:
        sources_text = "none"

    if row["retrieved_chunks"]:
        chunks_text = ", ".join(
            f"{c['id']} (distance {c['distance']:.4f})" for c in row["retrieved_chunks"]
        )
    else:
        chunks_text = "none"

    best_distance_text = f"{row['best_distance']:.4f}" if row["best_distance"] is not None else "none"

    return (
        f"**Timestamp:** {row['timestamp']}\n"
        f"**Question:** {row['question']}\n"
        f"**Answer:** {row['answer']}\n"
        f"**Sources:** {sources_text}\n"
        f"**Retrieved chunks:** {chunks_text}\n"
        f"**Best distance:** {best_distance_text}\n"
        f"**Gate fired:** {row['gate_fired']}\n"
        f"**Degraded (offline):** {row['degraded']}\n"
        f"**Latency:** {row['latency_ms']}ms"
    )
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/test_bot_debug.py -v`
Expected: all PASS.

- [ ] **Step 5: Write the failing tests — `bot/main.py` wiring**

Add these tests to `tests/test_bot_main.py`:

```python
def test_owner_only_rejects_a_non_owner(monkeypatch):
    from bot.main import _owner_only

    monkeypatch.setenv("BOT_OWNER_ID", "12345")
    interaction = MagicMock()
    interaction.user.id = 99999

    assert _owner_only(interaction) is False


def test_owner_only_allows_the_owner(monkeypatch):
    from bot.main import _owner_only

    monkeypatch.setenv("BOT_OWNER_ID", "12345")
    interaction = MagicMock()
    interaction.user.id = 12345

    assert _owner_only(interaction) is True


def test_owner_only_rejects_everyone_when_bot_owner_id_is_unset(monkeypatch):
    from bot.main import _owner_only

    monkeypatch.delenv("BOT_OWNER_ID", raising=False)
    interaction = MagicMock()
    interaction.user.id = 12345

    assert _owner_only(interaction) is False


def test_debug_last_command_is_registered_with_an_owner_only_check():
    _client, tree = build_client()
    command = tree.get_command("debug-last")

    assert command is not None
    assert len(command.checks) >= 1


def test_debug_last_shows_the_most_recent_logged_call(monkeypatch):
    monkeypatch.setenv("BOT_OWNER_ID", "12345")
    monkeypatch.setattr(
        "bot.main.get_last_ask_log",
        lambda: {
            "timestamp": "2026-09-14T12:00:00+00:00",
            "question": "How bulky is Gyarados?",
            "answer": "Gyarados has 95 base HP.",
            "sources": [{"name": "Gyarados", "chunk_type": "stats"}],
            "retrieved_chunks": [{"id": "Gyarados-stats", "distance": 0.4}],
            "best_distance": 0.4,
            "gate_fired": False,
            "degraded": False,
            "latency_ms": 900,
        },
    )

    _client, tree = build_client()
    debug_command = tree.get_command("debug-last")
    interaction = MagicMock()
    interaction.user.id = 12345
    interaction.response.send_message = AsyncMock()

    asyncio.run(debug_command.callback(interaction))

    sent_text = _extract_text(interaction.response.send_message)
    assert "How bulky is Gyarados?" in sent_text
    assert "Gyarados has 95 base HP." in sent_text


def test_debug_last_reports_plainly_when_nothing_is_logged_yet(monkeypatch):
    monkeypatch.setenv("BOT_OWNER_ID", "12345")
    monkeypatch.setattr("bot.main.get_last_ask_log", lambda: None)

    _client, tree = build_client()
    debug_command = tree.get_command("debug-last")
    interaction = MagicMock()
    interaction.user.id = 12345
    interaction.response.send_message = AsyncMock()

    asyncio.run(debug_command.callback(interaction))

    sent_text = _extract_text(interaction.response.send_message)
    assert "No /ask calls logged yet." in sent_text
```

- [ ] **Step 6: Run the tests to verify they fail**

Run: `pytest tests/test_bot_main.py -v -k "owner_only or debug_last"`
Expected: FAIL — `ImportError: cannot import name '_owner_only' from 'bot.main'` and `AssertionError: None is not None` (no `debug-last` command registered yet).

- [ ] **Step 7: Implement the `bot/main.py` changes**

Add this import (with the other `bot.commands.*` imports):

```python
from bot.commands.debug import format_debug_last
```

Change the `rag.observability` import line added in Task 3 from:
```python
from rag.observability import log_ask
```
to:
```python
from rag.observability import get_last_ask_log, log_ask
```

Add `"debug": discord.Color.dark_grey(),` to the `_COMMAND_COLORS` dict (alongside the other command-name-to-color entries).

Add this new module-level function, near `_embed` (both are simple, standalone helpers, not closures over `build_client`'s state):

```python
def _owner_only(interaction: discord.Interaction) -> bool:
    owner_id = os.environ.get("BOT_OWNER_ID")
    return owner_id is not None and interaction.user.id == int(owner_id)
```

Inside `build_client`, add this new command (place it after the `ask` command, before `stats`):

```python
    @tree.command(name="debug-last", description="Show the most recent /ask call's full detail (bot owner only).")
    @app_commands.check(_owner_only)
    async def debug_last(interaction: discord.Interaction) -> None:
        row = get_last_ask_log()
        await interaction.response.send_message(embed=_embed("debug", format_debug_last(row)))
```

- [ ] **Step 8: Add `BOT_OWNER_ID` to `.env.example`**

Append this to the end of `.env.example`:

```
# Discord user ID of the bot owner, used to gate the admin-only /debug-last
# command (shows the most recent /ask call's full retrieval/answer detail).
# Find your own ID: Discord Settings -> Advanced -> enable Developer Mode,
# then right-click your name -> Copy User ID. Optional -- if unset,
# /debug-last is rejected for everyone.
BOT_OWNER_ID=
```

- [ ] **Step 9: Run the full test_bot_main.py suite to verify everything passes**

Run: `pytest tests/test_bot_main.py -v`
Expected: all PASS.

- [ ] **Step 10: Run the entire test suite as a final check**

Run: `pytest -q`
Expected: all tests PASS.

- [ ] **Step 11: Commit**

```bash
git add bot/commands/debug.py tests/test_bot_debug.py bot/main.py tests/test_bot_main.py .env.example
git commit -m "feat: add owner-only /debug-last command"
```

---

## Self-review notes

- **Spec coverage:** the SQLite `ask_log` table with all 9 spec'd columns (Task 1), `log_ask`'s injectable `timestamp` parameter (Task 1), the required `.gitignore` addition (Task 1), threading `retrieved_chunks`/`best_distance` since the spec's data model needs per-chunk id+distance that no existing return shape carried (Task 2), the exact `degraded`/`gate_fired` string-sentinel derivation the spec specifies, wrapping the *entire* `ask_response_async` call for `latency_ms`, and the best-effort `try/except` around `log_ask` (Task 3), the `BOT_OWNER_ID`-gated `/debug-last` command with the `app_commands.check` predicate (not `is_owner()`, unavailable on this bot's bare `discord.Client`) and the empty-table case (Task 4) — all covered.
- **Out-of-scope items** (cost tracking, dashboards/external monitoring, logging non-`/ask` commands) are correctly not touched by any task.
- **Type/name consistency checked:** `log_ask`'s parameter names match exactly what Task 3's `bot/main.py` call site passes as keyword arguments; `get_last_ask_log`'s returned dict keys match exactly what `format_debug_last` (Task 4) reads; `build_context_block`'s `"retrieved_chunks"` key name matches what `ask_response` (Task 2) reads and what `log_ask` (Task 3's call site) is keyed by.
- **Breaking-change fallout audited:** every existing fake-index fixture across the whole test suite that constructs a match dict was checked for a missing `"id"` key (required once `build_context_block` starts reading `match["id"]`) — `tests/test_rag_retrieve.py` and `tests/test_bot_ask.py` needed full rewrites since nearly every test in each file is affected; `tests/test_bot_main.py` and `tests/test_run_eval.py` needed one/three surgical edits respectively. All four are covered by Task 2's steps.
