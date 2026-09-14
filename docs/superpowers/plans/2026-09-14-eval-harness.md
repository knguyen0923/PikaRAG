# Evaluation Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give PikaRAG a measurable quality baseline — an auto-generated golden Q&A set, a `recall@5` retrieval-quality check gated in CI, and an on-demand answer-quality script that exercises the real Ollama model — so future retrieval/prompt/model changes can be checked for regressions instead of eyeballed.

**Architecture:** `eval/` holds three small, independently-testable modules (`matchers.py` for string-comparison logic, `metrics.py` for the recall@k computation, `generate_golden_set.py` for building the golden set from the project's own processed data) plus the generated `data/eval/golden_set.json` artifact itself, committed to the repo. `tests/test_eval_retrieval.py` runs `recall_at_k` against a real `ChromaIndex` + `SentenceTransformerEmbedder` in CI (the suite's first test with a real model-download network dependency, mitigated with `actions/cache`). `scripts/run_eval.py` is a separate on-demand CLI that reuses `bot.main`'s existing `_build_real_index`/`_build_answerer` helpers to run the full `/ask` path against a live Ollama server — never gated in CI, since CI has no Tailscale access to the laptop.

**Tech Stack:** Python 3.9, `chromadb`/`sentence-transformers` (already dependencies, no new ones added), stdlib `json`/`argparse`. Reuses `rag/store.py`, `rag/embed.py`, `rag/answer.py`, `bot/commands/ask.py`, and `bot/main.py`'s existing `_build_real_index`/`_build_answerer` helpers — no changes to any of those files.

**Spec:** `docs/superpowers/specs/2026-09-13-eval-harness-design.md`

## Global Constraints

- No new dependency: only `chromadb`, `sentence-transformers`, `requests`, stdlib — all already in `requirements.txt`.
- Golden-set generation fails loudly (raises) on a missing source file or a record lacking an expected field — never silently skips a malformed record.
- `data/eval/golden_set.json` is committed to the repo, not gitignored — regenerating it is a deliberate, reviewable step (Task 4), not automatic.
- `recall@5` threshold starts at `0.9` (a module-level constant, easy to retune later once real usage informs a better number).
- The answer-quality script (`scripts/run_eval.py`) is never wired into `.github/workflows/test.yml` — it requires live Tailscale access to the Ollama laptop, which CI doesn't have.
- `OllamaAnswerer`'s `OFFLINE_MESSAGE` response is reported as its own distinct category in `run_eval.py`'s output, never conflated with a wrong-but-present answer.
- Golden set targets ~30-50 total entries (per the spec) via deterministic sampling — see Task 3's Interfaces for the exact sample sizes and why they land in that range. No randomness (no `random.seed` needed): sampling uses fixed-stride slicing so regenerating the golden set from the same source data always produces the same output, keeping the diff reviewable.

---

### Task 1: `eval/matchers.py` — answer-text matching logic

**Files:**
- Create: `eval/__init__.py` (empty — makes `eval/` an importable package)
- Create: `eval/matchers.py`
- Test: `tests/test_eval_matchers.py`

**Interfaces:**
- Produces: `matches(actual: str, expected, match_type: str) -> bool`. `match_type` is one of `"exact"`, `"set"`, `"substring"`. For `"exact"`, `expected` is a single string checked as a whole-word, case-insensitive match inside `actual` (word-boundary regex, not a bare substring check — see Step 3's rationale). For `"set"`, `expected` is a `list[str]`, every item must appear in `actual` case-insensitively. For `"substring"`, `expected` is a single string checked as a plain case-insensitive substring of `actual`. Raises `ValueError` for any other `match_type`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_eval_matchers.py`:

```python
import pytest

from eval.matchers import matches


def test_exact_match_is_case_insensitive():
    assert matches("Yes, Kommo-o learns Close Combat.", "yes", "exact") is True


def test_exact_match_requires_a_whole_word_not_a_bare_substring():
    # "no" is a substring of "known" -- a naive `in` check would false-positive.
    # word-boundary matching must not.
    assert matches("Kommo-o's known moves include Close Combat.", "no", "exact") is False


def test_exact_match_finds_the_word_when_genuinely_present():
    assert matches("No, Kommo-o cannot learn Tackle.", "no", "exact") is True


def test_set_match_requires_every_item_present():
    answer = "Kommo-o's base stats: HP 75, Attack 110, Defense 125."
    assert matches(answer, ["HP 75", "Attack 110", "Defense 125"], "set") is True


def test_set_match_fails_when_one_item_missing():
    answer = "Kommo-o's base stats: HP 75, Attack 110."
    assert matches(answer, ["HP 75", "Attack 110", "Defense 125"], "set") is False


def test_set_match_is_case_insensitive():
    answer = "abilities: bulletproof, overcoat"
    assert matches(answer, ["Bulletproof", "Overcoat"], "set") is True


def test_substring_match_finds_a_paraphrased_key_phrase():
    answer = "Life Orb boosts move power by 30 percent but you take recoil damage."
    assert matches(answer, "Boosts move power by 30%", "substring") is False  # exact text not present
    assert matches(answer, "boosts move power by 30", "substring") is True


def test_substring_match_is_case_insensitive():
    assert matches("LIFE ORB DESCRIPTION", "life orb description", "substring") is True


def test_unknown_match_type_raises():
    with pytest.raises(ValueError):
        matches("anything", "anything", "not-a-real-type")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_eval_matchers.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'eval'` (or `eval.matchers`).

- [ ] **Step 3: Implement `eval/matchers.py`**

Create `eval/__init__.py` (empty file).

Create `eval/matchers.py`:

```python
import re


def matches(actual: str, expected, match_type: str) -> bool:
    """Checks whether `actual` (an LLM's free-text answer) satisfies `expected`.

    A full free-text answer will essentially never equal a bare expected
    value like "91" or "Yes" verbatim, so "exact" means a whole-word,
    case-insensitive match within the answer -- not string equality. This
    also avoids a plain substring check's false positive on short words
    (e.g. "no" matching inside "known").
    """
    actual_lower = actual.lower()
    if match_type == "exact":
        pattern = r"\b" + re.escape(expected.lower()) + r"\b"
        return re.search(pattern, actual_lower) is not None
    if match_type == "set":
        return all(item.lower() in actual_lower for item in expected)
    if match_type == "substring":
        return expected.lower() in actual_lower
    raise ValueError(f"unknown match_type: {match_type!r}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_eval_matchers.py -v`
Expected: all 9 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add eval/__init__.py eval/matchers.py tests/test_eval_matchers.py
git commit -m "feat: add eval.matchers for golden-set answer comparison"
```

---

### Task 2: `eval/metrics.py` — recall@k computation

**Files:**
- Create: `eval/metrics.py`
- Test: `tests/test_eval_metrics.py`

**Interfaces:**
- Consumes: an `index` object with `.query(text: str, n_results: int) -> list[dict]` where each result dict has an `"id"` key (matches `rag.store.ChromaIndex`'s shape, and the `_FakeIndex` test double already used in `tests/test_rag_retrieve.py`).
- Produces: `recall_at_k(index, golden_entries: list[dict], n_results: int = 5) -> float`. Each entry in `golden_entries` must have `"question"` and `"source_chunk_id"` keys. Returns the fraction of entries whose `source_chunk_id` appears among the `id`s returned by `index.query(entry["question"], n_results=n_results)`. Raises `ValueError` if `golden_entries` is empty (recall is undefined for zero entries — this project's convention is to fail loudly on degenerate input rather than return a misleading `1.0` or `0.0`).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_eval_metrics.py`:

```python
import pytest

from eval.metrics import recall_at_k


class _FakeIndex:
    def __init__(self, results_by_question):
        self._results_by_question = results_by_question

    def query(self, text, n_results=5):
        return self._results_by_question.get(text, [])[:n_results]


def test_recall_is_1_when_every_entrys_chunk_is_found():
    index = _FakeIndex({
        "q1": [{"id": "chunk-a"}, {"id": "chunk-b"}],
        "q2": [{"id": "chunk-c"}],
    })
    golden = [
        {"question": "q1", "source_chunk_id": "chunk-a"},
        {"question": "q2", "source_chunk_id": "chunk-c"},
    ]

    assert recall_at_k(index, golden, n_results=5) == 1.0


def test_recall_is_0_when_no_entrys_chunk_is_found():
    index = _FakeIndex({"q1": [{"id": "wrong-chunk"}]})
    golden = [{"question": "q1", "source_chunk_id": "chunk-a"}]

    assert recall_at_k(index, golden, n_results=5) == 0.0


def test_recall_is_the_fraction_of_hits():
    index = _FakeIndex({
        "q1": [{"id": "chunk-a"}],
        "q2": [{"id": "wrong-chunk"}],
    })
    golden = [
        {"question": "q1", "source_chunk_id": "chunk-a"},
        {"question": "q2", "source_chunk_id": "chunk-b"},
    ]

    assert recall_at_k(index, golden, n_results=5) == 0.5


def test_n_results_is_passed_through_to_the_index_query():
    class _RecordingIndex:
        def __init__(self):
            self.calls = []

        def query(self, text, n_results=5):
            self.calls.append(n_results)
            return []

    index = _RecordingIndex()
    golden = [{"question": "q1", "source_chunk_id": "chunk-a"}]

    recall_at_k(index, golden, n_results=3)

    assert index.calls == [3]


def test_empty_golden_set_raises():
    index = _FakeIndex({})

    with pytest.raises(ValueError):
        recall_at_k(index, [], n_results=5)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_eval_metrics.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'eval.metrics'`.

- [ ] **Step 3: Implement `eval/metrics.py`**

```python
def recall_at_k(index, golden_entries: list[dict], n_results: int = 5) -> float:
    if not golden_entries:
        raise ValueError("recall_at_k requires at least one golden entry")

    hits = 0
    for entry in golden_entries:
        results = index.query(entry["question"], n_results=n_results)
        found_ids = {result["id"] for result in results}
        if entry["source_chunk_id"] in found_ids:
            hits += 1

    return hits / len(golden_entries)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_eval_metrics.py -v`
Expected: all 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add eval/metrics.py tests/test_eval_metrics.py
git commit -m "feat: add eval.metrics.recall_at_k for retrieval-quality scoring"
```

---

### Task 3: `eval/generate_golden_set.py` — golden set generation

**Files:**
- Create: `eval/generate_golden_set.py`
- Test: `tests/test_eval_generate_golden_set.py`

**Interfaces:**
- Consumes: nothing from Tasks 1-2 (independent module).
- Produces: `generate_golden_set(records: list[dict], items: list[dict], moves: list[dict]) -> list[dict]`, plus `build_stats_entry`, `build_abilities_entry`, `build_moveset_entry`, `build_item_entry` (each `(record_or_item, ...) -> dict`, used directly by Task 3's own tests and available for reuse), and a `main()` CLI entry point invoked via `python -m eval.generate_golden_set` that reads the three real source files and writes `data/eval/golden_set.json`. Every produced entry dict has exactly the keys `id`, `question`, `match_type`, `expected`, `source_chunk_id` — this is the shape Task 2's `recall_at_k` and Task 7's `run_eval.py` both consume.

**Design decisions this task locks in** (the spec left the exact sampling strategy and per-category question count unstated beyond "~30-50 total entries" and "one question per Pokemon" per category — these are concrete, disclosed choices, not spec violations):
- Sample ~12 of the 345 Pokemon records and ~8 of the 197 items, via fixed-stride slicing (`records[::len(records)//12]`) — deterministic, no RNG, and regenerating from the same source data always produces the same output.
- Each sampled Pokemon gets exactly 3 questions (base-stats, abilities, moveset-membership) — matching "one \<category\> question per Pokemon" read literally. 12 records × 3 + 8 items × 1 = ~44 entries, comfortably inside the spec's 30-50 target.
- The base-stats question is the spec's "combined" option (one question covering all six stats via `match_type: "set"`), not one question per stat — the per-stat option would produce 12×6=72 base-stat questions alone, blowing well past the 30-50 budget.
- The moveset-membership question alternates between a learned-move ("Yes") and a not-learned-move ("No") check across sampled records (even index → learned, odd index → not-learned), so the golden set as a whole covers both directions while staying at exactly one question per Pokemon for this category, matching the spec's literal "One moveset-membership question per Pokemon" wording.
- Abilities text lives inside `rag/embed.py`'s `"stats"` chunk (`build_chunks`' `stats_text` includes `"Abilities: ..."` — there's no separate abilities chunk), so the abilities question's `source_chunk_id` is `f"{name}-stats"`, not a separate `-abilities` id.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_eval_generate_golden_set.py`:

```python
from eval.generate_golden_set import (
    build_abilities_entry,
    build_item_entry,
    build_moveset_entry,
    build_stats_entry,
    generate_golden_set,
)

_KOMMOO = {
    "name": "Kommo-o",
    "types": ["Dragon", "Fighting"],
    "base_stats": {"hp": 75, "attack": 110, "defense": 125, "sp_attack": 100, "sp_defense": 105, "speed": 85},
    "abilities": ["Bulletproof", "Overcoat", "Soundproof"],
    "learnset": ["Close Combat", "Dragon Claw"],
    "legal_in": ["M-C"],
}

_LIFE_ORB = {"name": "Life Orb", "description": "Boosts move power by 30% at the cost of recoil HP."}

_MOVES_POOL = [
    {"name": "Close Combat", "type": "Fighting"},
    {"name": "Dragon Claw", "type": "Dragon"},
    {"name": "Tackle", "type": "Normal"},
]


def test_build_stats_entry_covers_every_stat_via_set_match():
    entry = build_stats_entry(_KOMMOO)

    assert entry["match_type"] == "set"
    assert entry["source_chunk_id"] == "Kommo-o-stats"
    assert "HP 75" in entry["expected"]
    assert "Attack 110" in entry["expected"]
    assert "Defense 125" in entry["expected"]
    assert "Sp. Atk 100" in entry["expected"]
    assert "Sp. Def 105" in entry["expected"]
    assert "Speed 85" in entry["expected"]


def test_build_abilities_entry_targets_the_stats_chunk():
    entry = build_abilities_entry(_KOMMOO)

    assert entry["match_type"] == "set"
    assert entry["expected"] == ["Bulletproof", "Overcoat", "Soundproof"]
    assert entry["source_chunk_id"] == "Kommo-o-stats"


def test_build_moveset_entry_for_a_learned_move_expects_yes():
    entry = build_moveset_entry(_KOMMOO, _MOVES_POOL, want_learned=True)

    assert entry["match_type"] == "exact"
    assert entry["expected"] == "Yes"
    assert "Close Combat" in entry["question"]
    assert entry["source_chunk_id"] == "Kommo-o-moveset"


def test_build_moveset_entry_for_a_not_learned_move_expects_no():
    entry = build_moveset_entry(_KOMMOO, _MOVES_POOL, want_learned=False)

    assert entry["match_type"] == "exact"
    assert entry["expected"] == "No"
    assert "Tackle" in entry["question"]  # first move in the pool not in Kommo-o's learnset


def test_build_item_entry_uses_substring_match_against_the_raw_description():
    entry = build_item_entry(_LIFE_ORB)

    assert entry["match_type"] == "substring"
    assert entry["expected"] == "Boosts move power by 30% at the cost of recoil HP."
    assert entry["source_chunk_id"] == "item-Life Orb"


def test_generate_golden_set_has_unique_ids():
    records = [dict(_KOMMOO, name=f"Mon{i}") for i in range(30)]
    items = [dict(_LIFE_ORB, name=f"Item{i}") for i in range(20)]

    golden_set = generate_golden_set(records, items, _MOVES_POOL)

    ids = [entry["id"] for entry in golden_set]
    assert len(ids) == len(set(ids))


def test_generate_golden_set_stays_within_the_target_size_range():
    records = [dict(_KOMMOO, name=f"Mon{i}") for i in range(345)]
    items = [dict(_LIFE_ORB, name=f"Item{i}") for i in range(197)]

    golden_set = generate_golden_set(records, items, _MOVES_POOL)

    assert 30 <= len(golden_set) <= 50


def test_generate_golden_set_alternates_learned_and_not_learned_across_records():
    records = [dict(_KOMMOO, name=f"Mon{i}") for i in range(4)]
    items = []

    golden_set = generate_golden_set(records, items, _MOVES_POOL)

    moveset_entries = [e for e in golden_set if "moveset" in e["id"]]
    expecteds = [e["expected"] for e in moveset_entries]
    assert expecteds == ["Yes", "No", "Yes", "No"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_eval_generate_golden_set.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'eval.generate_golden_set'`.

- [ ] **Step 3: Implement `eval/generate_golden_set.py`**

```python
import json
from pathlib import Path

RECORDS_PATH = Path("data/processed/pokemon_records.json")
ITEMS_PATH = Path("data/source/vgc_items.json")
MOVES_PATH = Path("data/source/vgc_moves.json")
GOLDEN_SET_PATH = Path("data/eval/golden_set.json")

_RECORD_SAMPLE_SIZE = 12
_ITEM_SAMPLE_SIZE = 8


def _sample(pool: list, target_count: int) -> list:
    if not pool:
        return []
    step = max(1, len(pool) // target_count)
    return pool[::step]


def build_stats_entry(record: dict) -> dict:
    name = record["name"]
    stats = record["base_stats"]
    return {
        "id": f"{name}-stats-question",
        "question": f"What are {name}'s base stats?",
        "match_type": "set",
        "expected": [
            f"HP {stats['hp']}",
            f"Attack {stats['attack']}",
            f"Defense {stats['defense']}",
            f"Sp. Atk {stats['sp_attack']}",
            f"Sp. Def {stats['sp_defense']}",
            f"Speed {stats['speed']}",
        ],
        "source_chunk_id": f"{name}-stats",
    }


def build_abilities_entry(record: dict) -> dict:
    name = record["name"]
    return {
        "id": f"{name}-abilities-question",
        "question": f"What are {name}'s abilities?",
        "match_type": "set",
        "expected": list(record["abilities"]),
        "source_chunk_id": f"{name}-stats",
    }


def build_moveset_entry(record: dict, moves_pool: list[dict], want_learned: bool) -> dict:
    name = record["name"]
    learnset = record["learnset"]
    if want_learned:
        move = learnset[0]
        expected = "Yes"
        suffix = "moveset-learned"
    else:
        learnset_set = set(learnset)
        move = next(m["name"] for m in moves_pool if m["name"] not in learnset_set)
        expected = "No"
        suffix = "moveset-not-learned"
    return {
        "id": f"{name}-{suffix}-question",
        "question": f"Does {name} learn {move}?",
        "match_type": "exact",
        "expected": expected,
        "source_chunk_id": f"{name}-moveset",
    }


def build_item_entry(item: dict) -> dict:
    name = item["name"]
    return {
        "id": f"item-{name}-question",
        "question": f"What does {name} do?",
        "match_type": "substring",
        "expected": item["description"],
        "source_chunk_id": f"item-{name}",
    }


def generate_golden_set(records: list[dict], items: list[dict], moves: list[dict]) -> list[dict]:
    sampled_records = _sample(records, _RECORD_SAMPLE_SIZE)
    sampled_items = _sample(items, _ITEM_SAMPLE_SIZE)

    entries = []
    for i, record in enumerate(sampled_records):
        entries.append(build_stats_entry(record))
        entries.append(build_abilities_entry(record))
        entries.append(build_moveset_entry(record, moves, want_learned=(i % 2 == 0)))
    for item in sampled_items:
        entries.append(build_item_entry(item))

    ids = [entry["id"] for entry in entries]
    if len(ids) != len(set(ids)):
        raise ValueError("generated golden set has duplicate ids -- sampled records/items must have unique names")
    return entries


def main() -> None:
    records = json.loads(RECORDS_PATH.read_text())
    items = json.loads(ITEMS_PATH.read_text())
    moves = json.loads(MOVES_PATH.read_text())["moves"]

    golden_set = generate_golden_set(records, items, moves)

    GOLDEN_SET_PATH.parent.mkdir(parents=True, exist_ok=True)
    GOLDEN_SET_PATH.write_text(json.dumps(golden_set, indent=2) + "\n")
    print(f"Wrote {len(golden_set)} golden entries to {GOLDEN_SET_PATH}")


if __name__ == "__main__":
    main()
```

Note on "fails loudly": `record["name"]`, `record["base_stats"]`, `item["description"]`, etc. are all direct dict-key access (no `.get()` with a silent default anywhere) — a record or item missing an expected field raises `KeyError` naturally, and `RECORDS_PATH.read_text()` on a missing file raises `FileNotFoundError` naturally. This satisfies the spec's "fails loudly... if a source data file is missing or a record lacks an expected field" without extra validation code.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_eval_generate_golden_set.py -v`
Expected: all 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add eval/generate_golden_set.py tests/test_eval_generate_golden_set.py
git commit -m "feat: add eval.generate_golden_set to build the golden Q&A set"
```

---

### Task 4: Generate and commit the real golden set

This task runs the tool built in Task 3 against the project's actual data and commits the result — the spec's "deliberate, reviewable step," not an automatic side effect. No new code.

**Files:**
- Create: `data/eval/golden_set.json` (generated, then committed)

**Interfaces:**
- Consumes: `eval.generate_golden_set.main()` (Task 3), the real `data/processed/pokemon_records.json`, `data/source/vgc_items.json`, `data/source/vgc_moves.json`.
- Produces: `data/eval/golden_set.json`, consumed by Task 6 (`tests/test_eval_retrieval.py`) and Task 7 (`scripts/run_eval.py`).

- [ ] **Step 1: Run the generator**

```bash
.venv/bin/python -m eval.generate_golden_set
```

Expected output: `Wrote 48 golden entries to data/eval/golden_set.json` — Task 3's `_sample` step is `345 // 12 = 28`, giving 13 sampled records (not 12 — integer-division stride over-samples slightly when the pool doesn't divide evenly), and `197 // 8 = 24`, giving 9 sampled items. 13×3 + 9×1 = 48, still comfortably inside the spec's 30-50 target. If the underlying data file has changed since this plan was written (a data refresh changes `pokemon_records.json`'s count), the exact number may differ slightly — that's expected, don't force it back to 48; just confirm it's still in the 30-50 range per Step 2.

- [ ] **Step 2: Spot-check the output**

```bash
.venv/bin/python -c "
import json
golden = json.loads(open('data/eval/golden_set.json').read())
print(f'{len(golden)} entries')
print(json.dumps(golden[0], indent=2))
print(json.dumps(golden[-1], indent=2))
"
```

Confirm: the count is in the 30-50 range, the first and last entries have the expected shape (`id`/`question`/`match_type`/`expected`/`source_chunk_id`), and a couple of `question`/`expected` pairs read sensibly against real Pokemon/item names (e.g. open `data/eval/golden_set.json` and skim a handful of entries — this is the human-reviewable moment the spec calls for).

- [ ] **Step 3: Commit**

```bash
git add data/eval/golden_set.json
git commit -m "data: generate the eval harness's golden Q&A set"
```

---

### Task 5: CI — cache the sentence-transformers model download

**Files:**
- Modify: `.github/workflows/test.yml`

**Interfaces:** none — CI configuration only, no code.

- [ ] **Step 1: Add the cache step**

Current `.github/workflows/test.yml`:

```yaml
name: Tests

on:
  push:
    branches: [main]
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.9"
          cache: pip
      - run: pip install -r requirements.txt
      - run: python -m pytest -q
```

Change to:

```yaml
name: Tests

on:
  push:
    branches: [main]
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.9"
          cache: pip
      - uses: actions/cache@v4
        with:
          path: ~/.cache/huggingface
          key: ${{ runner.os }}-hf-${{ hashFiles('requirements.txt') }}
          restore-keys: |
            ${{ runner.os }}-hf-
      - run: pip install -r requirements.txt
      - run: python -m pytest -q
```

(The cache key is tied to `requirements.txt` since a `sentence-transformers`/`torch` version bump could change what gets cached under that path — `restore-keys` still lets a version-bump run fall back to the old cache rather than a fully cold download, since the model itself won't have changed.)

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/test.yml
git commit -m "ci: cache the sentence-transformers model download"
```

---

### Task 6: `tests/test_eval_retrieval.py` — recall@k CI test

**Files:**
- Create: `tests/test_eval_retrieval.py`

**Interfaces:**
- Consumes: `eval.metrics.recall_at_k` (Task 2), `data/eval/golden_set.json` (Task 4), `rag.embed.SentenceTransformerEmbedder`, `rag.store.ChromaIndex` (both unchanged, existing).

- [ ] **Step 1: Write the test**

This test has no "fail first" step in the usual TDD sense — `recall_at_k` and the golden set already exist and work (Tasks 2 and 4), so this task is wiring them into a real-index integration test rather than driving new implementation. Still run it once written to confirm the threshold actually holds against real data, per Step 2.

Create `tests/test_eval_retrieval.py`:

```python
import json
from pathlib import Path

import chromadb

from eval.metrics import recall_at_k
from rag.embed import SentenceTransformerEmbedder
from rag.store import ChromaIndex

RECORDS_PATH = Path("data/processed/pokemon_records.json")
ITEMS_PATH = Path("data/source/vgc_items.json")
GOLDEN_SET_PATH = Path("data/eval/golden_set.json")

_RECALL_THRESHOLD = 0.9


def test_recall_at_5_meets_the_threshold_against_the_real_index():
    records = json.loads(RECORDS_PATH.read_text())
    items = json.loads(ITEMS_PATH.read_text())
    golden_set = json.loads(GOLDEN_SET_PATH.read_text())

    index = ChromaIndex(embedder=SentenceTransformerEmbedder(), client=chromadb.Client())
    index.build(records, items=items)

    score = recall_at_k(index, golden_set, n_results=5)

    assert score >= _RECALL_THRESHOLD, f"recall@5 dropped to {score:.2f} (threshold {_RECALL_THRESHOLD})"
```

Note: `client=chromadb.Client()` (in-memory, ephemeral) matches `tests/test_rag_store.py`'s existing convention — this test never touches the persistent `data/chroma/` directory the live bot uses.

- [ ] **Step 2: Run the test**

Run: `.venv/bin/python -m pytest tests/test_eval_retrieval.py -v`

Expected: PASS, reporting the real recall@5 score. This run downloads `all-MiniLM-L6-v2` from Hugging Face Hub on a cache miss (a few seconds on a normal connection) and embeds ~890 chunk texts (345 records × 2 chunks + 197 items) plus 44 golden questions — expect this test alone to take noticeably longer than the rest of the suite (single-digit seconds to roughly a minute depending on CPU), which is expected and acceptable for the one real-model test in the suite.

If the score comes in below `0.9`: this is real signal, not a bug to paper over. Read which golden entries failed (temporarily add a print of missed entries, or drop into a debugger) and decide whether the threshold was too optimistic for a real 12-record/8-item sample, or whether there's a genuine retrieval-quality issue worth its own investigation — don't lower the threshold just to make the test pass without understanding why it's failing.

- [ ] **Step 3: Commit**

```bash
git add tests/test_eval_retrieval.py
git commit -m "test: gate recall@5 in CI against the real Chroma index"
```

---

### Task 7: `scripts/run_eval.py` — on-demand answer-quality script

**Files:**
- Create: `scripts/__init__.py` (empty — makes `scripts/` importable so tests can `from scripts.run_eval import ...`)
- Create: `scripts/run_eval.py`
- Test: `tests/test_run_eval.py`
- Modify: `README.md` — add a short "Evaluation" section

**Interfaces:**
- Consumes: `eval.matchers.matches` (Task 1), `data/eval/golden_set.json` (Task 4), `bot.main._build_real_index`, `bot.main._build_answerer` (both already exist, unchanged), `bot.commands.ask.ask_response`, `rag.answer.OFFLINE_MESSAGE` (all already exist, unchanged).
- Produces: `run_answer_quality(index, answerer, golden_set: list[dict]) -> list[dict]` (each result dict has `id`, `question`, `expected`, `actual`, `passed`, `offline`), `print_report(results: list[dict]) -> None`, and a `main()` CLI requiring `--with-answers` to run at all (an accidental bare invocation does nothing rather than silently calling the live LLM).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_run_eval.py`:

```python
from scripts.run_eval import print_report, run_answer_quality
from rag.answer import OFFLINE_MESSAGE


class _FakeIndex:
    def query(self, text, n_results=5):
        return []


class _FakeAnswerer:
    def __init__(self, answers_by_question):
        self._answers_by_question = answers_by_question

    def answer(self, question, context_block):
        return self._answers_by_question[question]


def test_run_answer_quality_marks_a_matching_answer_as_passed():
    golden_set = [{"id": "q1", "question": "Does Kommo-o learn Close Combat?", "match_type": "exact", "expected": "Yes"}]
    answerer = _FakeAnswerer({"Does Kommo-o learn Close Combat?": "Yes, it does."})

    results = run_answer_quality(_FakeIndex(), answerer, golden_set)

    assert results[0]["passed"] is True
    assert results[0]["offline"] is False


def test_run_answer_quality_marks_a_wrong_answer_as_failed():
    golden_set = [{"id": "q1", "question": "Does Kommo-o learn Close Combat?", "match_type": "exact", "expected": "Yes"}]
    answerer = _FakeAnswerer({"Does Kommo-o learn Close Combat?": "No, it does not."})

    results = run_answer_quality(_FakeIndex(), answerer, golden_set)

    assert results[0]["passed"] is False
    assert results[0]["offline"] is False


def test_run_answer_quality_flags_the_offline_message_as_its_own_category_not_a_wrong_answer():
    golden_set = [{"id": "q1", "question": "Does Kommo-o learn Close Combat?", "match_type": "exact", "expected": "Yes"}]
    answerer = _FakeAnswerer({"Does Kommo-o learn Close Combat?": OFFLINE_MESSAGE})

    results = run_answer_quality(_FakeIndex(), answerer, golden_set)

    assert results[0]["offline"] is True
    assert results[0]["passed"] is False


def test_run_answer_quality_handles_set_and_substring_match_types_too():
    golden_set = [
        {"id": "q1", "question": "abilities?", "match_type": "set", "expected": ["Bulletproof", "Overcoat"]},
        {"id": "q2", "question": "item?", "match_type": "substring", "expected": "boosts move power"},
    ]
    answerer = _FakeAnswerer({
        "abilities?": "Bulletproof and Overcoat.",
        "item?": "This item boosts move power significantly.",
    })

    results = run_answer_quality(_FakeIndex(), answerer, golden_set)

    assert results[0]["passed"] is True
    assert results[1]["passed"] is True


def test_print_report_runs_without_error_on_a_mixed_result_set(capsys):
    results = [
        {"id": "q1", "question": "q1?", "expected": "Yes", "actual": "Yes indeed.", "passed": True, "offline": False},
        {"id": "q2", "question": "q2?", "expected": "No", "actual": "Yes.", "passed": False, "offline": False},
        {"id": "q3", "question": "q3?", "expected": "Yes", "actual": OFFLINE_MESSAGE, "passed": False, "offline": True},
    ]

    print_report(results)

    output = capsys.readouterr().out
    assert "q2" in output  # the failure is named
    assert "q3" in output  # the offline case is named
    assert "1/3 passed" in output
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_run_eval.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts'` (or `scripts.run_eval`).

- [ ] **Step 3: Implement `scripts/run_eval.py`**

Create `scripts/__init__.py` (empty file).

Create `scripts/run_eval.py`:

```python
import argparse
import json
import sys
from pathlib import Path

from bot.commands.ask import ask_response
from bot.main import _build_answerer, _build_real_index
from eval.matchers import matches
from rag.answer import OFFLINE_MESSAGE

GOLDEN_SET_PATH = Path("data/eval/golden_set.json")
RECORDS_PATH = Path("data/processed/pokemon_records.json")
ITEMS_PATH = Path("data/source/vgc_items.json")


def run_answer_quality(index, answerer, golden_set: list[dict]) -> list[dict]:
    results = []
    for entry in golden_set:
        actual = ask_response(index, answerer, entry["question"])
        offline = actual == OFFLINE_MESSAGE
        passed = (not offline) and matches(actual, entry["expected"], entry["match_type"])
        results.append({
            "id": entry["id"],
            "question": entry["question"],
            "expected": entry["expected"],
            "actual": actual,
            "passed": passed,
            "offline": offline,
        })
    return results


def print_report(results: list[dict]) -> None:
    passed = [r for r in results if r["passed"]]
    offline = [r for r in results if r["offline"]]
    failed = [r for r in results if not r["passed"] and not r["offline"]]

    for r in failed:
        print(f"FAIL {r['id']}: question={r['question']!r} expected={r['expected']!r} actual={r['actual']!r}")
    for r in offline:
        print(f"OFFLINE {r['id']}: question={r['question']!r} (Ollama unreachable, not a quality failure)")

    print(f"\n{len(passed)}/{len(results)} passed, {len(failed)} failed, {len(offline)} offline")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the answer-quality eval against the live Ollama model. "
        "Requires network access to the Ollama server (LLM_HOST) -- not run in CI."
    )
    parser.add_argument(
        "--with-answers",
        action="store_true",
        required=True,
        help="Required: confirms you want to call the live Ollama model once per golden entry.",
    )
    parser.parse_args()

    golden_set = json.loads(GOLDEN_SET_PATH.read_text())
    records = json.loads(RECORDS_PATH.read_text())
    items = json.loads(ITEMS_PATH.read_text())

    index = _build_real_index(records, items)
    answerer = _build_answerer()

    results = run_answer_quality(index, answerer, golden_set)
    print_report(results)

    failed_count = sum(1 for r in results if not r["passed"])
    sys.exit(1 if failed_count else 0)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_run_eval.py -v`
Expected: all 5 tests PASS.

- [ ] **Step 5: Update `README.md`**

Add a new `## Evaluation` section, after `## Testing` (the last section in the current file):

```markdown

## Evaluation

`data/eval/golden_set.json` is an auto-generated golden Q&A set (see
`eval/generate_golden_set.py`), used two ways:

- **Retrieval quality (`recall@5`)** runs as a normal test in CI
  (`tests/test_eval_retrieval.py`) — no live LLM involved, just the
  embedding model and Chroma.
- **Answer quality** exercises the full `/ask` path against a live Ollama
  model, on demand (not run in CI, since CI has no Tailscale access to the
  laptop):
  ```bash
  .venv/bin/python -m scripts.run_eval --with-answers
  ```
  Run this after a retrieval/prompt change or a model swap, from a machine
  with tailnet access (the Oracle Cloud instance or a dev machine joined to
  the same tailnet).

Regenerate the golden set after a data refresh with:
```bash
.venv/bin/python -m eval.generate_golden_set
```
Review the diff before committing — this is a deliberate step, not
automatic.
```

Run `git diff README.md` after editing to confirm only this section was added (no accidental changes elsewhere in the file).

- [ ] **Step 6: Commit**

```bash
git add scripts/__init__.py scripts/run_eval.py tests/test_run_eval.py README.md
git commit -m "feat: add scripts.run_eval, the on-demand answer-quality check"
```

---

### Task 8: Full suite sanity check

No new code — confirms nothing in the previous 7 tasks broke anything else, and that the full suite (including the new, slower `test_eval_retrieval.py`) is still healthy end to end.

**Files:** none.

- [ ] **Step 1: Run the full suite**

Run: `.venv/bin/python -m pytest -q`

Expected: all tests pass, including the new `test_eval_matchers.py`, `test_eval_metrics.py`, `test_eval_generate_golden_set.py`, `test_eval_retrieval.py`, and `test_run_eval.py` files. No warnings beyond the pre-existing `NotOpenSSLWarning` (present before this plan, unrelated to this work).

- [ ] **Step 2: Confirm `scripts/run_eval.py` fails cleanly without `--with-answers`**

Run: `.venv/bin/python -m scripts.run_eval`

Expected: argparse errors with something like `the following arguments are required: --with-answers` and a non-zero exit code — confirms the script can't accidentally call the live LLM with a bare invocation.

No commit for this task — it's verification of already-committed work (Tasks 1-7).
