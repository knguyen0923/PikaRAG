# Retrieval Quality Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `/ask` retrieval entity-aware — when a question names a known Pokemon or item, constrain the vector search to that entity's own chunks instead of searching the whole corpus, fixing two confirmed retrieval misses (`Abomasnow`/`Dragalge` moveset questions losing to their own Mega Stone + stats chunks).

**Architecture:** A new `rag/entity.py` module scans a free-text question for a known Pokemon/item name (new logic) and resolves it to a canonical record, reusing `bot/pokemon_lookup.py`'s existing `find_record`/`suggest_names` for the actual name matching. `rag/store.py`'s `ChromaIndex.query` gains an optional `where` parameter (Chroma already supports metadata filtering; chunks already carry `pokemon`/`item` metadata). `rag/retrieve.py`'s `build_context_block` ties them together: detect an entity, query filtered, and fall back to today's unfiltered search whenever no entity is detected, detection is ambiguous, or the filtered query comes back empty. `records`/`items` (already loaded once in `bot/main.py`) are threaded through the existing `ask` call chain (`bot/main.py` -> `bot/commands/ask.py` -> `rag/retrieve.py`) rather than reloaded.

**Tech Stack:** Python 3.9, `chromadb`, `difflib` (stdlib, already used by `bot/pokemon_lookup.py`), `pytest`. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-09-13-retrieval-quality-design.md`

## Global Constraints

- No new dependencies — reuse `re`/`difflib` (stdlib) and the existing `find_record`/`suggest_names` helpers. No BM25/hybrid-search library (explicitly out of scope per spec).
- No Chroma schema change — chunks already carry `pokemon`/`item` metadata keys (`rag/embed.py`), `where={"pokemon": name}` / `where={"item": name}` filters against those directly.
- Every signature change (`ChromaIndex.query`, `build_context_block`, `ask_response`, `ask_response_async`) must keep new parameters optional with backward-compatible defaults (`where=None`, `records=None`, `items=None`) so existing callers/tests that don't pass them keep working unchanged — several existing tests in `tests/test_bot_main.py` and `tests/test_bot_ask.py` call these with fake index doubles that don't accept a `where` kwarg, and must not need to change.
- A `where`-filtered query that returns zero results must fall back to an unfiltered query rather than ever returning an empty context block when a broader search might have found something.
- Genuine remaining ambiguity between two form-variants (e.g. "Mega Absol" vs "Mega Absol Z") is accepted, not solved — falls through to unfiltered search, same as "no entity detected." Do not add extra precision for this beyond what's specified (see spec's "Remaining ambiguity" note).

---

## File structure

- Modify `rag/store.py` — `ChromaIndex.query` gains an optional `where` parameter, passed straight through to Chroma.
- Create `rag/entity.py` — `detect_entity(question, records, items)`, the new free-text scanning logic plus reuse of `find_record`/`suggest_names` for resolution, plus the form-variant tie-breaking rules.
- Create `tests/test_rag_entity.py` — unit tests for `detect_entity`.
- Modify `tests/test_rag_store.py` — add a `where`-filter test.
- Modify `rag/retrieve.py` — `build_context_block` gains `records`/`items` params, calls `detect_entity`, queries filtered with unfiltered fallback.
- Modify `tests/test_rag_retrieve.py` — add entity-narrowing and fallback tests.
- Modify `bot/commands/ask.py` — `ask_response`/`ask_response_async` gain `records`/`items` params, threaded through to `build_context_block`.
- Modify `tests/test_bot_ask.py` — add a records/items passthrough test.
- Modify `bot/main.py` — the `ask` command handler (already has `records`/`items` in scope via `build_client`'s parameters) passes them to `ask_response_async`.
- Modify `tests/test_bot_main.py` — add an end-to-end test confirming a named Pokemon narrows the query the bot actually issues.
- Modify `tests/test_eval_retrieval.py` — add a regression test confirming the two known golden-set misses (`Abomasnow-moveset-learned-question`, `Dragalge-moveset-not-learned-question`) now retrieve their target chunk via entity-aware filtering.

---

### Task 1: `ChromaIndex.query` gains an optional `where` filter

**Files:**
- Modify: `rag/store.py:43-54`
- Test: `tests/test_rag_store.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `ChromaIndex.query(text, n_results=5, where=None)` — later tasks call this with `where={"pokemon": name}` or `where={"item": name}`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_rag_store.py` (after `test_build_also_indexes_item_chunks`):

```python
def test_query_with_where_filter_narrows_to_matching_metadata():
    index = _build_test_index()

    matches = index.query("Pokemon", n_results=10, where={"pokemon": "Abomasnow"})

    assert len(matches) == 2
    assert all(m["metadata"]["pokemon"] == "Abomasnow" for m in matches)


def test_query_without_where_filter_is_unaffected():
    index = _build_test_index()

    matches = index.query("Pokemon", n_results=10)

    assert len(matches) == 4
```

- [ ] **Step 2: Run tests to verify the new one fails**

Run: `pytest tests/test_rag_store.py -v`
Expected: `test_query_with_where_filter_narrows_to_matching_metadata` FAILs with `TypeError: query() got an unexpected keyword argument 'where'`; `test_query_without_where_filter_is_unaffected` passes already (no change needed for it, it's a safety-net regression check).

- [ ] **Step 3: Add the `where` parameter**

In `rag/store.py`, replace the `query` method:

```python
    def query(self, text: str, n_results: int = 5, where: Optional[dict] = None) -> list[dict]:
        embedding = self._embedder.embed([text])[0]
        result = self._collection.query(query_embeddings=[embedding], n_results=n_results, where=where)
        return [
            {
                "id": result["ids"][0][i],
                "text": result["documents"][0][i],
                "metadata": result["metadatas"][0][i],
                "distance": result["distances"][0][i],
            }
            for i in range(len(result["ids"][0]))
        ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_rag_store.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add rag/store.py tests/test_rag_store.py
git commit -m "feat: add optional where filter to ChromaIndex.query"
```

---

### Task 2: `rag/entity.py` — detect a known Pokemon/item name in a question

**Files:**
- Create: `rag/entity.py`
- Test: `tests/test_rag_entity.py`

**Interfaces:**
- Consumes: `bot.pokemon_lookup.find_record(records, name)`, `bot.pokemon_lookup.suggest_names(records, name, n=3)` (both exist already, unmodified).
- Produces: `detect_entity(question: str, records: list, items: list) -> Optional[dict]`, returning `{"field": "pokemon", "name": <name>}`, `{"field": "item", "name": <name>}`, or `None`. Task 3 calls this directly.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_rag_entity.py`:

```python
from rag.entity import detect_entity

_RECORDS = [
    {"name": "Abomasnow"},
    {"name": "Mega Abomasnow"},
    {"name": "Absol"},
    {"name": "Mega Absol"},
    {"name": "Mega Absol Z"},
    {"name": "Arcanine"},
    {"name": "Arcanine [Hisuian Form]"},
    {"name": "Gyarados"},
    {"name": "Garchomp"},
]

_ITEMS = [
    {"name": "Life Orb"},
    {"name": "Abomasite"},
]


def test_detect_entity_resolves_an_exact_pokemon_name():
    entity = detect_entity("Does Gyarados learn Waterfall?", _RECORDS, _ITEMS)

    assert entity == {"field": "pokemon", "name": "Gyarados"}


def test_detect_entity_resolves_a_fuzzy_typo_name():
    entity = detect_entity("Does Abomasno learn Attract?", _RECORDS, _ITEMS)

    assert entity == {"field": "pokemon", "name": "Abomasnow"}


def test_detect_entity_returns_none_when_nothing_is_recognized():
    entity = detect_entity("What is the weather like today?", _RECORDS, _ITEMS)

    assert entity is None


def test_detect_entity_resolves_an_item_name():
    entity = detect_entity("What does Life Orb do?", _RECORDS, _ITEMS)

    assert entity == {"field": "item", "name": "Life Orb"}


def test_detect_entity_resolves_plain_species_to_the_base_form():
    entity = detect_entity("Does Abomasnow learn Attract?", _RECORDS, _ITEMS)

    assert entity == {"field": "pokemon", "name": "Abomasnow"}


def test_detect_entity_resolves_a_form_qualifier_to_the_variant():
    entity = detect_entity("Does Mega Abomasnow learn Attract?", _RECORDS, _ITEMS)

    assert entity == {"field": "pokemon", "name": "Mega Abomasnow"}


def test_detect_entity_resolves_a_bracketed_form_qualifier_to_the_variant():
    entity = detect_entity("Does Hisuian Arcanine learn Extreme Speed?", _RECORDS, _ITEMS)

    assert entity == {"field": "pokemon", "name": "Arcanine [Hisuian Form]"}


def test_detect_entity_falls_back_to_unfiltered_on_genuine_variant_ambiguity():
    entity = detect_entity("What is Mega Absol's Speed stat?", _RECORDS, _ITEMS)

    assert entity is None
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_rag_entity.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'rag.entity'`.

- [ ] **Step 3: Implement `rag/entity.py`**

```python
import re
from typing import Optional

from bot.pokemon_lookup import find_record, suggest_names

_BRACKET_SUFFIX = re.compile(r"\s*\[([^\]]+)\]$")
_MEGA_PREFIX = "Mega "
_MAX_BASE_NGRAM_WORDS = 2
_MIN_FUZZY_WORD_LEN = 4


def _species_key(name: str) -> str:
    """Canonical species/item name a form-variant's full record name
    reduces to, so e.g. "Abomasnow" and "Mega Abomasnow" group together."""
    stripped = _BRACKET_SUFFIX.sub("", name).strip()
    if stripped.startswith(_MEGA_PREFIX):
        stripped = stripped[len(_MEGA_PREFIX):]
    # Trailing Mega-form letter, e.g. "Charizard X" -> "Charizard".
    stripped = re.sub(r"\s+[A-Z]$", "", stripped)
    return stripped.strip().lower()


def _qualifier_word(name: str) -> Optional[str]:
    """The word a question must contain to pick this variant over its base
    form; None for a plain/unqualified record name."""
    bracket_match = _BRACKET_SUFFIX.search(name)
    if bracket_match:
        first_word = re.match(r"[A-Za-z]+", bracket_match.group(1))
        return first_word.group(0).lower() if first_word else None
    if name.startswith(_MEGA_PREFIX):
        return "mega"
    return None


def _word_present(question_lower: str, word: str) -> bool:
    return re.search(r"\b" + re.escape(word.lower()) + r"\b", question_lower) is not None


def _question_ngrams(question: str, max_words: int) -> list:
    words = re.findall(r"[A-Za-z0-9]+", question)
    ngrams = []
    for size in range(min(max_words, len(words)), 0, -1):
        for start in range(len(words) - size + 1):
            ngrams.append(" ".join(words[start : start + size]))
    return ngrams


def _base_records(candidates: list) -> list:
    """One representative record per species/item family: the plain,
    unqualified record (no Mega prefix, no bracketed form suffix)."""
    return [c for c in candidates if _qualifier_word(c["name"]) is None]


def _find_species(question: str, bases: list) -> Optional[dict]:
    """Resolve which known species/item family the question is about.
    Exact match first (reusing find_record as-is), falling back to
    fuzzy/typo matching (reusing suggest_names as-is) when nothing matches
    exactly."""
    for ngram in _question_ngrams(question, _MAX_BASE_NGRAM_WORDS):
        record = find_record(bases, ngram)
        if record:
            return record
    words = sorted(set(re.findall(r"[A-Za-z0-9]+", question)), key=len, reverse=True)
    for word in words:
        if len(word) < _MIN_FUZZY_WORD_LEN:
            continue
        suggestions = suggest_names(bases, word, n=1)
        if suggestions:
            return find_record(bases, suggestions[0])
    return None


def _resolve_variant(question_lower: str, base: dict, candidates: list) -> Optional[dict]:
    """Given the recognized base species/item, pick the specific
    Mega/regional-form variant the question means, fall back to the base
    when no variant is specifically named, or signal genuine ambiguity
    (None) when more than one variant's qualifying word is present."""
    key = _species_key(base["name"])
    variants = [c for c in candidates if c is not base and _species_key(c["name"]) == key]
    if not variants:
        return base
    qualified = [v for v in variants if _word_present(question_lower, _qualifier_word(v["name"]))]
    if not qualified:
        return base
    if len(qualified) == 1:
        return qualified[0]
    return None


def _resolve(question: str, candidates: list) -> Optional[dict]:
    if not candidates:
        return None
    bases = _base_records(candidates)
    base = _find_species(question, bases)
    if base is None:
        return None
    return _resolve_variant(question.lower(), base, candidates)


def detect_entity(question: str, records: list, items: list) -> Optional[dict]:
    """Detect a known Pokemon or item name mentioned in a free-text question.

    Returns {"field": "pokemon", "name": <canonical name>} or
    {"field": "item", "name": <canonical name>}, or None when nothing is
    recognized, or recognition is genuinely ambiguous between two
    form-variants (see the retrieval-quality design's tie-breaking rules).
    """
    pokemon_match = _resolve(question, records or [])
    if pokemon_match:
        return {"field": "pokemon", "name": pokemon_match["name"]}
    item_match = _resolve(question, items or [])
    if item_match:
        return {"field": "item", "name": item_match["name"]}
    return None
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_rag_entity.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add rag/entity.py tests/test_rag_entity.py
git commit -m "feat: add detect_entity for entity-aware retrieval"
```

---

### Task 3: `build_context_block` uses entity detection with unfiltered fallback

**Files:**
- Modify: `rag/retrieve.py:1-3`
- Test: `tests/test_rag_retrieve.py`

**Interfaces:**
- Consumes: `rag.entity.detect_entity(question, records, items)` (Task 2), `ChromaIndex.query(text, n_results, where=None)` (Task 1).
- Produces: `build_context_block(index, question, records=None, items=None, n_results=5) -> str`. Task 4 calls this with `records`/`items` threaded from `ask_response`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_rag_retrieve.py` (the existing `_FakeIndex` and its 3 tests stay as-is — they cover the no-records/no-items backward-compatible path already):

```python
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
        {"text": "Abomasnow stats chunk", "metadata": {"pokemon": "Abomasnow"}},
        {"text": "Unrelated Gyarados chunk", "metadata": {"pokemon": "Gyarados"}},
    ])

    build_context_block(index, "Does Abomasnow learn Attract?", records=_RECORDS, items=_ITEMS)

    assert index.queries[0]["where"] == {"pokemon": "Abomasnow"}


def test_build_context_block_falls_back_to_unfiltered_when_no_entity_detected():
    index = _FakeIndexWithWhere(matches=[{"text": "Some chunk", "metadata": {}}])

    build_context_block(index, "What is the weather like?", records=_RECORDS, items=_ITEMS)

    assert index.queries[0]["where"] is None


def test_build_context_block_falls_back_to_unfiltered_when_filtered_query_returns_nothing():
    index = _FakeIndexWithWhere(matches=[
        {"text": "Unrelated chunk with no pokemon metadata", "metadata": {}},
    ])

    context_block = build_context_block(
        index, "Does Abomasnow learn Attract?", records=_RECORDS, items=_ITEMS
    )

    assert len(index.queries) == 2
    assert index.queries[0]["where"] == {"pokemon": "Abomasnow"}
    assert index.queries[1]["where"] is None
    assert "Unrelated chunk with no pokemon metadata" in context_block
```

- [ ] **Step 2: Run the tests to verify the new ones fail**

Run: `pytest tests/test_rag_retrieve.py -v`
Expected: the 3 new tests FAIL with `TypeError: build_context_block() got an unexpected keyword argument 'records'`.

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
) -> str:
    entity = detect_entity(question, records or [], items or [])
    if entity:
        matches = index.query(question, n_results=n_results, where={entity["field"]: entity["name"]})
        if not matches:
            matches = index.query(question, n_results=n_results)
    else:
        matches = index.query(question, n_results=n_results)
    return "\n".join(match["text"] for match in matches)
```

- [ ] **Step 4: Run all retrieve tests to verify they pass**

Run: `pytest tests/test_rag_retrieve.py -v`
Expected: all PASS (the 3 new ones and the 3 pre-existing backward-compatible ones).

- [ ] **Step 5: Commit**

```bash
git add rag/retrieve.py tests/test_rag_retrieve.py
git commit -m "feat: narrow build_context_block's query to a detected entity"
```

---

### Task 4: Thread `records`/`items` through `ask_response`/`ask_response_async`

**Files:**
- Modify: `bot/commands/ask.py`
- Test: `tests/test_bot_ask.py`

**Interfaces:**
- Consumes: `build_context_block(index, question, records=None, items=None, n_results=5)` (Task 3).
- Produces: `ask_response(index, answerer, question, records=None, items=None, n_results=5, extra_context=None)` and the equivalent async version. Task 5 calls `ask_response_async` with `records`/`items`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_bot_ask.py` (reuses the existing `_FakeAnswerer` already defined in that file):

```python
class _FakeIndexWithWhere:
    def __init__(self):
        self.queries = []

    def query(self, text, n_results=5, where=None):
        self.queries.append(where)
        return []


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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_bot_ask.py -v`
Expected: the 2 new tests FAIL with `TypeError: ask_response() got an unexpected keyword argument 'records'`.

- [ ] **Step 3: Implement the change**

Replace the full contents of `bot/commands/ask.py`:

```python
import asyncio
from typing import Optional

from rag.retrieve import build_context_block


def ask_response(
    index,
    answerer,
    question: str,
    records: Optional[list] = None,
    items: Optional[list] = None,
    n_results: int = 5,
    extra_context: Optional[str] = None,
) -> str:
    context_block = build_context_block(index, question, records=records, items=items, n_results=n_results)
    if extra_context:
        context_block = f"{extra_context}\n\n{context_block}"
    return answerer.answer(question, context_block)


async def ask_response_async(
    index,
    answerer,
    question: str,
    records: Optional[list] = None,
    items: Optional[list] = None,
    n_results: int = 5,
    extra_context: Optional[str] = None,
) -> str:
    """Run ask_response in a worker thread so the caller's event loop stays free.

    Both index.query (CPU-bound sentence-transformer encode) and
    answerer.answer (blocking network call) are synchronous; offloading the
    whole call keeps discord.py's event loop responsive during either one.
    """
    return await asyncio.to_thread(
        ask_response, index, answerer, question, records, items, n_results, extra_context
    )
```

- [ ] **Step 4: Run all ask tests to verify they pass**

Run: `pytest tests/test_bot_ask.py -v`
Expected: all PASS (the 2 new ones and the 5 pre-existing ones).

- [ ] **Step 5: Commit**

```bash
git add bot/commands/ask.py tests/test_bot_ask.py
git commit -m "feat: thread records/items through ask_response for entity detection"
```

---

### Task 5: Wire `records`/`items` into the `/ask` command handler

**Files:**
- Modify: `bot/main.py:63-72`
- Test: `tests/test_bot_main.py`

**Interfaces:**
- Consumes: `ask_response_async(index, answerer, question, records=None, items=None, extra_context=None)` (Task 4). `records`/`items` are already parameters of `build_client` (`bot/main.py:50`) and already in scope inside the `ask` closure — this task only changes the call inside `ask`, nothing else.
- Produces: nothing new consumed by later tasks — this is the last code task; Task 6 is verification only.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_bot_main.py` (reuses the `asyncio`, `AsyncMock`, `MagicMock` imports already at the top of that file):

```python
def test_ask_command_narrows_retrieval_when_a_known_pokemon_is_named():
    class _FakeIndex:
        def __init__(self):
            self.queries = []

        def query(self, question, n_results=5, where=None):
            self.queries.append(where)
            return []

    class _FakeAnswerer:
        def answer(self, question, context_block):
            return "an answer"

    fake_index = _FakeIndex()
    records = [{"name": "Abomasnow"}]
    _client, tree = build_client(index=fake_index, answerer=_FakeAnswerer(), records=records, items=[])
    ask_command = tree.get_command("ask")
    interaction = MagicMock()
    interaction.user.id = 9099
    interaction.response.defer = AsyncMock()
    interaction.followup.send = AsyncMock()

    asyncio.run(ask_command.callback(interaction, question="Does Abomasnow learn Attract?"))

    assert fake_index.queries == [{"pokemon": "Abomasnow"}]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_bot_main.py -v -k narrows_retrieval`
Expected: FAIL — `fake_index.queries == [None]` (the entity is detected correctly by `rag/entity.py`, since that's already implemented, but `bot/main.py`'s `ask` handler doesn't pass `records`/`items` through yet, so `build_context_block` never sees them and always queries unfiltered).

- [ ] **Step 3: Implement the change**

In `bot/main.py`, replace the `ask` function body (currently lines 63-72):

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
        answer = await ask_response_async(
            index, answerer, question, records=records, items=items, extra_context=extra_context
        )
        await interaction.followup.send(embed=_embed("ask", answer))
```

- [ ] **Step 4: Run the full test_bot_main.py suite to verify nothing broke**

Run: `pytest tests/test_bot_main.py -v`
Expected: all PASS, including the pre-existing `test_ask_command_includes_stored_team_context` (which calls `build_client` without `records`/`items`, so both are `None`, `detect_entity` sees empty lists, and the fake index there — which doesn't accept a `where` kwarg — is called exactly as before).

- [ ] **Step 5: Commit**

```bash
git add bot/main.py tests/test_bot_main.py
git commit -m "feat: wire records/items into the /ask command handler"
```

---

### Task 6: Regression check — confirm the two known golden-set misses now hit

**Files:**
- Modify: `tests/test_eval_retrieval.py`

**Interfaces:**
- Consumes: `rag.entity.detect_entity` (Task 2), `ChromaIndex.query(..., where=...)` (Task 1), `bot.main._build_real_index` (already exists, unmodified).
- Produces: nothing consumed by later tasks — this is the plan's final verification task.

- [ ] **Step 1: Write the new regression test**

Add to `tests/test_eval_retrieval.py` (reuses the `RECORDS_PATH`/`ITEMS_PATH`/`GOLDEN_SET_PATH` constants and `chromadb`/`_build_real_index` imports already at the top of that file):

```python
from rag.entity import detect_entity

_KNOWN_MISSES = ["Abomasnow-moveset-learned-question", "Dragalge-moveset-not-learned-question"]


def test_entity_aware_filtering_fixes_the_known_abomasnow_and_dragalge_misses():
    records = json.loads(RECORDS_PATH.read_text())
    items = json.loads(ITEMS_PATH.read_text())
    golden_by_id = {entry["id"]: entry for entry in json.loads(GOLDEN_SET_PATH.read_text())}

    index = _build_real_index(records, items, client=chromadb.Client())

    for golden_id in _KNOWN_MISSES:
        entry = golden_by_id[golden_id]
        entity = detect_entity(entry["question"], records, items)
        assert entity is not None, f"{golden_id}: expected an entity to be detected"

        results = index.query(entry["question"], n_results=5, where={entity["field"]: entity["name"]})
        found_ids = {result["id"] for result in results}
        assert entry["source_chunk_id"] in found_ids, (
            f"{golden_id}: target chunk {entry['source_chunk_id']!r} still missing after entity filtering"
        )
```

- [ ] **Step 2: Run the test to verify it fails before this plan's changes would have applied**

Run: `pytest tests/test_eval_retrieval.py -v -k known_abomasnow_and_dragalge`
Expected: PASS. (By this point in the plan, Tasks 1-2 are already implemented and committed, so this test should already pass — it's here as a permanent regression guard, not a red-then-green step. If it fails, something in Tasks 1-2 doesn't match the real data the way the unit tests assumed; re-check `rag/entity.py` against the real `data/processed/pokemon_records.json`/`data/source/vgc_items.json` shapes before proceeding.)

- [ ] **Step 3: Run the full existing eval regression suite too**

Run: `pytest tests/test_eval_retrieval.py -v`
Expected: all PASS, including the pre-existing `test_recall_at_5_meets_the_threshold_against_the_real_index` (recall@5 measured via raw `index.query`, unaffected by this plan since that test doesn't go through `build_context_block`/entity detection — it's testing the underlying embedder/index, not the new filtering layer, so it should be unaffected either way).

- [ ] **Step 4: Run the entire test suite as a final check**

Run: `pytest -q`
Expected: all tests PASS (292 pre-existing + this plan's new tests).

- [ ] **Step 5: Commit**

```bash
git add tests/test_eval_retrieval.py
git commit -m "test: confirm entity-aware filtering fixes the two known retrieval misses"
```

---

## Self-review notes

- **Spec coverage:** entity-aware retrieval (Task 2-3), fallback to unfiltered search (Task 3), `where` on `ChromaIndex.query` (Task 1), `records`/`items` threaded through the real call chain rather than reloaded (Tasks 4-5), form-variant tie-breaking including the bracket-form case and the accepted remaining ambiguity (Task 2), regression check against the two named golden-set misses (Task 6) — all covered.
- **Out-of-scope items** (BM25, chunking changes, query rewriting) are correctly not touched by any task.
- **Type/name consistency checked:** `detect_entity` returns `{"field": ..., "name": ...}` consistently from Task 2 through Task 6; `ChromaIndex.query`'s `where` parameter name and shape (`dict` or `None`) is identical across Tasks 1, 3, 4, 5, 6; `build_context_block`'s `records`/`items` parameter names match what Task 4 passes and what Task 5's already-existing `build_client` parameters are named.
