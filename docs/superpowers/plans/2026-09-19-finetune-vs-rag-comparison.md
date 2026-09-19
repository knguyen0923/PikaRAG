# Fine-tune vs. RAG Comparison Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Demonstrate LoRA fine-tuning as a second ML technique alongside the existing RAG pipeline, and produce a rigorous, explainable head-to-head comparison against `/ask`'s RAG answers, using the same 48-entry golden set the eval harness already gates CI on.

**Architecture:** A new `scripts/generate_finetune_data.py` (mirroring `eval/generate_golden_set.py`'s structure) generates `(question, answer)` training pairs from the same processed Pokemon records / `vgc_items.json` that `rag/embed.py` already chunks for RAG, committed to `data/finetune/train.jsonl`. Training itself happens off-repo, one time, on a free-tier Colab T4 GPU, documented as `notebooks/finetune_llama3.2.ipynb` (LoRA via `peft`/`transformers`/`bitsandbytes`, merge + GGUF convert + quantize, `ollama create pikarag-finetuned`). Back in this repo, `rag/answer.py`'s `OllamaAnswerer` gains an `answer_bare(question)` method (no context block, no grounding-caveat system prompt) for calling the fine-tuned model directly. `scripts/run_eval.py` gains a `--model rag|finetuned` flag reusing the existing golden set and `eval/matchers.matches` grading, plus an `--output` flag to dump raw per-question results as JSON. A new `eval/report.py` reads two such JSON files (one per `--model` run) and tabulates RAG-path vs. fine-tuned-path accuracy side by side, per question.

**Tech Stack:** Existing stdlib/`requests`/`chromadb` for everything in this repo; `peft`/`transformers`/`bitsandbytes` only inside the Colab notebook (installed there via `pip install` cells, not added to this repo's `requirements.txt` — they never run locally or in CI); `llama.cpp`'s `convert_hf_to_gguf.py` + `llama-quantize` + Ollama, run manually on whichever machine serves Ollama for the project.

**Spec:** `docs/superpowers/specs/2026-09-17-finetune-vs-rag-design.md`

## Global Constraints

- $0 cost, local-first is the standing priority ([[pikarag_cost_priority]] memory) — the only accepted exception is the one-time, off-repo Colab/Kaggle training run; inference/serving stays fully local via Ollama, $0, same as today.
- Base model: **Llama3.2-3B**, matching the model already serving the live RAG path (`OllamaAnswerer`'s default `llama3.2:3b`), for an apples-to-apples comparison.
- No `mlx-lm`, no `unsloth` — training toolchain is the portable, standard `peft` + `transformers` + `bitsandbytes` stack.
- Comparison re-uses the existing eval harness (`scripts/run_eval.py`, `data/eval/golden_set.json`, `eval/matchers.matches`) — extend, don't duplicate or build separate side-by-side tooling.
- RAG path keeps its existing recall@5 retrieval metric, unaffected by this work (nothing in this plan touches `eval/metrics.py` or `tests/test_eval_retrieval.py`'s recall@5 tests). The fine-tuned path is graded on answer-correctness against `golden_set.json`'s `expected` field via `eval/matchers.matches` (exact/set/substring) — no LLM-as-judge, deterministic, no new model dependency.
- Training data generation must be deterministic and template-based (no LLM-generation cost, no non-reproducible step) — same rationale as `eval/generate_golden_set.py`.
- Do not use the fine-tuned model in production `/ask` — it stays a benchmark artifact (see spec's "Out of scope"). Nothing in this plan wires `pikarag-finetuned` into `bot/main.py` or `bot/commands/ask.py`.
- The training notebook itself is not unit-tested (manual, one-time, off-repo run); only `scripts/generate_finetune_data.py` (its input) and the eval/report code (its output's consumer) get unit tests, per the spec's Testing section.

---

## File Structure

- Create: `scripts/generate_finetune_data.py` — generates `(question, answer)` training pairs from processed records/items/moves, mirroring `eval/generate_golden_set.py`'s function-per-field-type structure.
- Create: `tests/test_generate_finetune_data.py` — unit tests for the pair-builder functions, no network/model calls.
- Create: `data/finetune/train.jsonl` — committed output of running `scripts/generate_finetune_data.py` once (same precedent as committing `data/eval/golden_set.json`).
- Modify: `rag/answer.py` — add `OllamaAnswerer.answer_bare(question)` and a `BARE_SYSTEM_PROMPT` constant.
- Modify: `tests/test_rag_answer.py` — add tests for `answer_bare`.
- Modify: `scripts/run_eval.py` — add `--model rag|finetuned` and `--output <path>` flags; add `run_answer_quality_finetuned`; add `FINETUNED_MODEL_NAME` constant.
- Modify: `tests/test_run_eval.py` — add tests for `run_answer_quality_finetuned` and for the new flags' effect on `main()`'s wiring (via the existing test style — see Task 4).
- Create: `eval/report.py` — `build_comparison`, `summarize`, `format_report` functions plus a CLI entrypoint reading two `--output` JSON files.
- Create: `tests/test_eval_report.py` — unit tests for the three functions.
- Create: `notebooks/finetune_llama3.2.ipynb` — the training notebook (data load → LoRA fine-tune → merge → save adapter), run manually on Colab/Kaggle.
- Create: `docs/finetuned-model-serving.md` — the merge → GGUF convert → quantize → `ollama create` steps (run manually on whichever machine serves Ollama), referenced from the notebook's last cell.
- Modify: `IMPROVEMENTS.md` — mark the item done.

---

### Task 1: Training data generation — `scripts/generate_finetune_data.py`

**Files:**
- Create: `scripts/generate_finetune_data.py`
- Test: `tests/test_generate_finetune_data.py`

**Interfaces:**
- Consumes: nothing from other tasks — reads the same on-disk JSON shapes `eval/generate_golden_set.py` already reads (`data/processed/pokemon_records.json` records with `name`/`types`/`base_stats`/`abilities`/`learnset`; `data/source/vgc_items.json` entries with `name`/`description`; `data/source/vgc_moves.json`'s `moves` list of `{"name": ..., ...}`).
- Produces: `generate_finetune_data(records, items, moves) -> list[dict]`, each dict `{"question": str, "answer": str}`. Task 6 (train.jsonl generation) calls this via the script's `main()`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_generate_finetune_data.py`:

```python
from scripts.generate_finetune_data import (
    build_ability_pairs,
    build_item_pairs,
    build_moveset_pairs,
    build_stats_pairs,
    build_type_pairs,
    generate_finetune_data,
)

_KOMMOO = {
    "name": "Kommo-o",
    "types": ["Dragon", "Fighting"],
    "base_stats": {"hp": 75, "attack": 110, "defense": 125, "sp_attack": 100, "sp_defense": 105, "speed": 85},
    "abilities": ["Bulletproof", "Overcoat", "Soundproof"],
    "learnset": ["Close Combat", "Dragon Claw", "Flamethrower", "Poison Jab"],
}

_LIFE_ORB = {"name": "Life Orb", "description": "Boosts move power by 30% at the cost of recoil HP."}

_MOVES_POOL = [
    {"name": "Close Combat"},
    {"name": "Dragon Claw"},
    {"name": "Flamethrower"},
    {"name": "Poison Jab"},
    {"name": "Tackle"},
    {"name": "Splash"},
    {"name": "Rest"},
]


def test_build_stats_pairs_covers_full_stat_line_and_a_single_stat():
    pairs = build_stats_pairs(_KOMMOO)

    assert len(pairs) == 2
    full = next(p for p in pairs if "base stats" in p["question"])
    assert "HP 75" in full["answer"]
    assert "Attack 110" in full["answer"]
    assert "Defense 125" in full["answer"]
    assert "Sp. Atk 100" in full["answer"]
    assert "Sp. Def 105" in full["answer"]
    assert "Speed 85" in full["answer"]

    hp_only = next(p for p in pairs if "base HP" in p["question"])
    assert "75" in hp_only["answer"]


def test_build_type_pairs_names_both_types():
    pairs = build_type_pairs(_KOMMOO)

    assert len(pairs) == 1
    assert "Dragon" in pairs[0]["answer"]
    assert "Fighting" in pairs[0]["answer"]


def test_build_ability_pairs_lists_every_ability_in_both_templates():
    pairs = build_ability_pairs(_KOMMOO)

    assert len(pairs) == 2
    for pair in pairs:
        assert "Bulletproof" in pair["answer"]
        assert "Overcoat" in pair["answer"]
        assert "Soundproof" in pair["answer"]


def test_build_moveset_pairs_yields_learned_and_not_learned_pairs():
    pairs = build_moveset_pairs(_KOMMOO, _MOVES_POOL, n_learned=2, n_not_learned=2)

    learned = [p for p in pairs if p["answer"].startswith("Yes")]
    not_learned = [p for p in pairs if p["answer"].startswith("No")]
    assert len(learned) == 2
    assert len(not_learned) == 2
    assert "Close Combat" in learned[0]["question"]
    assert "Tackle" in not_learned[0]["question"]
    assert "Tackle" in not_learned[0]["answer"]


def test_build_item_pairs_uses_the_raw_description_in_both_templates():
    pairs = build_item_pairs(_LIFE_ORB)

    assert len(pairs) == 2
    assert all("Life Orb" in p["question"] or "Life Orb" in p["answer"] for p in pairs)
    assert any(p["answer"] == "Boosts move power by 30% at the cost of recoil HP." for p in pairs)


def test_generate_finetune_data_covers_every_record_and_item():
    records = [dict(_KOMMOO, name=f"Mon{i}") for i in range(5)]
    items = [dict(_LIFE_ORB, name=f"Item{i}") for i in range(3)]

    pairs = generate_finetune_data(records, items, _MOVES_POOL)

    questions = " ".join(p["question"] for p in pairs)
    for i in range(5):
        assert f"Mon{i}" in questions
    for i in range(3):
        assert f"Item{i}" in questions


def test_generate_finetune_data_produces_more_pairs_than_the_golden_set_needs():
    # The spec calls for "more template variety per field than the 48-question
    # golden set needs" -- one record alone should already clear a handful of
    # pairs across all field types (2 stats + 1 type + 2 ability + up to 6
    # moveset = 11 for a single record with a large enough learnset/pool).
    pairs = generate_finetune_data([_KOMMOO], [], _MOVES_POOL)

    assert len(pairs) >= 8
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_generate_finetune_data.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.generate_finetune_data'`

- [ ] **Step 3: Implement `scripts/generate_finetune_data.py`**

```python
import json
from pathlib import Path

RECORDS_PATH = Path("data/processed/pokemon_records.json")
ITEMS_PATH = Path("data/source/vgc_items.json")
MOVES_PATH = Path("data/source/vgc_moves.json")
TRAIN_DATA_PATH = Path("data/finetune/train.jsonl")

_MOVES_PER_RECORD = 3


def build_stats_pairs(record: dict) -> list[dict]:
    name = record["name"]
    stats = record["base_stats"]
    full_answer = (
        f"{name} has base stats: HP {stats['hp']}, Attack {stats['attack']}, "
        f"Defense {stats['defense']}, Sp. Atk {stats['sp_attack']}, "
        f"Sp. Def {stats['sp_defense']}, Speed {stats['speed']}."
    )
    return [
        {"question": f"What are {name}'s base stats?", "answer": full_answer},
        {"question": f"What is {name}'s base HP?", "answer": f"{name}'s base HP is {stats['hp']}."},
    ]


def build_type_pairs(record: dict) -> list[dict]:
    name = record["name"]
    types = "/".join(record["types"])
    return [
        {"question": f"What type is {name}?", "answer": f"{name} is a {types}-type Pokemon."},
    ]


def build_ability_pairs(record: dict) -> list[dict]:
    name = record["name"]
    abilities = ", ".join(record["abilities"])
    return [
        {"question": f"What are {name}'s abilities?", "answer": f"{name}'s abilities are: {abilities}."},
        {
            "question": f"What abilities can {name} have?",
            "answer": f"{name} can have the following abilities: {abilities}.",
        },
    ]


def build_moveset_pairs(
    record: dict,
    moves_pool: list[dict],
    n_learned: int = _MOVES_PER_RECORD,
    n_not_learned: int = _MOVES_PER_RECORD,
) -> list[dict]:
    name = record["name"]
    learnset = record["learnset"]
    learnset_set = set(learnset)

    pairs = []
    for move in learnset[:n_learned]:
        pairs.append({"question": f"Does {name} learn {move}?", "answer": f"Yes, {name} learns {move}."})

    not_learned = [m["name"] for m in moves_pool if m["name"] not in learnset_set][:n_not_learned]
    for move in not_learned:
        pairs.append({"question": f"Does {name} learn {move}?", "answer": f"No, {name} does not learn {move}."})

    return pairs


def build_item_pairs(item: dict) -> list[dict]:
    name = item["name"]
    description = item["description"]
    return [
        {"question": f"What does {name} do?", "answer": f"{name}: {description}"},
        {"question": f"What is {name} used for?", "answer": description},
    ]


def generate_finetune_data(records: list[dict], items: list[dict], moves: list[dict]) -> list[dict]:
    pairs = []
    for record in records:
        pairs.extend(build_stats_pairs(record))
        pairs.extend(build_type_pairs(record))
        pairs.extend(build_ability_pairs(record))
        pairs.extend(build_moveset_pairs(record, moves))
    for item in items:
        pairs.extend(build_item_pairs(item))
    return pairs


def main() -> None:
    records = json.loads(RECORDS_PATH.read_text())
    items = json.loads(ITEMS_PATH.read_text())
    moves = json.loads(MOVES_PATH.read_text())["moves"]

    pairs = generate_finetune_data(records, items, moves)

    TRAIN_DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    with TRAIN_DATA_PATH.open("w") as f:
        for pair in pairs:
            f.write(json.dumps(pair) + "\n")
    print(f"Wrote {len(pairs)} training pairs to {TRAIN_DATA_PATH}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_generate_finetune_data.py -v`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add scripts/generate_finetune_data.py tests/test_generate_finetune_data.py
git commit -m "feat: add template-based fine-tuning training data generator" -m "$(printf 'Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>')"
```

---

### Task 2: Generate and commit `data/finetune/train.jsonl`

**Files:**
- Create: `data/finetune/train.jsonl` (generated, not hand-written)

**Interfaces:**
- Consumes: Task 1's `scripts/generate_finetune_data.py` `main()`.
- Produces: `data/finetune/train.jsonl`, read by `notebooks/finetune_llama3.2.ipynb` (Task 5).

- [ ] **Step 1: Run the generator**

Run: `python -m scripts.generate_finetune_data`
Expected: prints `Wrote N training pairs to data/finetune/train.jsonl` and creates the file.

- [ ] **Step 2: Sanity-check the output**

Run: `wc -l data/finetune/train.jsonl && head -3 data/finetune/train.jsonl`
Expected: line count in the low thousands (345 records × ~11 pairs + 197 items × 2 pairs, roughly 4000-4500); each line is valid JSON with `question`/`answer` string keys.

- [ ] **Step 3: Commit**

```bash
git add data/finetune/train.jsonl
git commit -m "data: generate fine-tuning training set from processed records and items" -m "$(printf 'Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>')"
```

---

### Task 3: `OllamaAnswerer.answer_bare` — no-context inference path

**Files:**
- Modify: `rag/answer.py`
- Test: `tests/test_rag_answer.py`

**Interfaces:**
- Consumes: nothing new — same `self._client`/`self._host`/`self._model`/`self._timeout` `OllamaAnswerer` already has.
- Produces: `OllamaAnswerer.answer_bare(question: str) -> str`, used by Task 4's `run_answer_quality_finetuned`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_rag_answer.py` (after the existing `answer()` tests, reusing `_FakeOllamaClient`/`_FakeOllamaResponse` already defined in that file):

```python
def test_answer_bare_returns_the_models_response_text():
    client = _FakeOllamaClient(response_json={"message": {"content": "Gyarados has 95 base HP."}})
    answerer = OllamaAnswerer(host="100.1.2.3:11434", client=client)

    result = answerer.answer_bare("How bulky is Gyarados?")

    assert result == "Gyarados has 95 base HP."


def test_answer_bare_sends_only_the_question_no_context():
    client = _FakeOllamaClient(response_json={"message": {"content": "anything"}})
    answerer = OllamaAnswerer(host="100.1.2.3:11434", client=client)

    answerer.answer_bare("How bulky is Gyarados?")

    sent = client.calls[0]["json"]
    user_message = sent["messages"][-1]["content"]
    assert user_message == "How bulky is Gyarados?"


def test_answer_bare_does_not_use_the_grounding_caveat_system_prompt():
    client = _FakeOllamaClient(response_json={"message": {"content": "anything"}})
    answerer = OllamaAnswerer(host="100.1.2.3:11434", client=client)

    answerer.answer_bare("How bulky is Gyarados?")

    sent = client.calls[0]["json"]
    system_message = sent["messages"][0]["content"]
    # answer()'s grounding prompt tells the model to say "I don't know" when
    # context doesn't have the answer -- answer_bare has no context block at
    # all, so that caveat would make a fine-tuned model refuse to answer from
    # its own learned knowledge. Confirm it's a different, caveat-free prompt.
    assert "only the information in the provided context" not in system_message.lower()


def test_answer_bare_posts_to_the_configured_host_and_model():
    client = _FakeOllamaClient(response_json={"message": {"content": "anything"}})
    answerer = OllamaAnswerer(host="100.1.2.3:11434", model="pikarag-finetuned", client=client)

    answerer.answer_bare("question")

    call = client.calls[0]
    assert call["url"] == "http://100.1.2.3:11434/api/chat"
    assert call["json"]["model"] == "pikarag-finetuned"


def test_answer_bare_returns_offline_message_on_connection_error():
    client = _FakeOllamaClient(exception=requests.exceptions.ConnectionError("refused"))
    answerer = OllamaAnswerer(host="100.1.2.3:11434", client=client)

    result = answerer.answer_bare("question")

    assert result == OFFLINE_MESSAGE
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_rag_answer.py -v -k answer_bare`
Expected: FAIL with `AttributeError: 'OllamaAnswerer' object has no attribute 'answer_bare'`

- [ ] **Step 3: Implement `answer_bare`**

In `rag/answer.py`, add a module-level constant near `SYSTEM_PROMPT`:

```python
BARE_SYSTEM_PROMPT = (
    "You are a Pokemon VGC doubles assistant. Answer the user's question "
    "directly and concisely, using what you know."
)
```

Add the method to `OllamaAnswerer` (after `answer`):

```python
    def answer_bare(self, question: str) -> str:
        """Like answer(), but sends only the question -- no context block,
        no grounding caveat in the system prompt. Used to benchmark a
        fine-tuned model's learned knowledge directly, without RAG
        retrieval layered on top (see
        docs/superpowers/specs/2026-09-17-finetune-vs-rag-design.md)."""
        try:
            response = self._client.post(
                f"http://{self._host}/api/chat",
                json={
                    "model": self._model,
                    "messages": [
                        {"role": "system", "content": BARE_SYSTEM_PROMPT},
                        {"role": "user", "content": question},
                    ],
                    "stream": False,
                    "options": {"num_predict": 1024},
                },
                timeout=self._timeout,
            )
            response.raise_for_status()
            return response.json()["message"]["content"]
        except (requests.RequestException, KeyError, TypeError) as e:
            print(f"OllamaAnswerer call failed: {e!r}")
            return OFFLINE_MESSAGE
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_rag_answer.py -v`
Expected: all pass (existing `answer()` tests + new `answer_bare` tests)

- [ ] **Step 5: Commit**

```bash
git add rag/answer.py tests/test_rag_answer.py
git commit -m "feat: add OllamaAnswerer.answer_bare for context-free fine-tuned-model inference" -m "$(printf 'Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>')"
```

---

### Task 4: `scripts/run_eval.py` — `--model rag|finetuned` and `--output`

**Files:**
- Modify: `scripts/run_eval.py`
- Test: `tests/test_run_eval.py`

**Interfaces:**
- Consumes: Task 3's `OllamaAnswerer.answer_bare`; existing `eval.matchers.matches`, `rag.answer.OFFLINE_MESSAGE`.
- Produces: `run_answer_quality_finetuned(answerer, golden_set) -> list[dict]` (same result-dict shape as the existing `run_answer_quality`: `id`/`question`/`expected`/`actual`/`passed`/`offline`) and `FINETUNED_MODEL_NAME = "pikarag-finetuned"`, consumed by Task 6 (report generation is driven from `--output` files this task produces, not a direct function call).

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_run_eval.py`:

```python
from scripts.run_eval import print_report, run_answer_quality, run_answer_quality_finetuned


class _FakeBareAnswerer:
    def __init__(self, answers_by_question):
        self._answers_by_question = answers_by_question
        self.calls = []

    def answer_bare(self, question):
        self.calls.append(question)
        return self._answers_by_question[question]


def test_run_answer_quality_finetuned_marks_a_matching_answer_as_passed():
    golden_set = [{"id": "q1", "question": "Does Kommo-o learn Close Combat?", "match_type": "exact", "expected": "Yes"}]
    answerer = _FakeBareAnswerer({"Does Kommo-o learn Close Combat?": "Yes, it learns Close Combat."})

    results = run_answer_quality_finetuned(answerer, golden_set)

    assert results[0]["passed"] is True
    assert results[0]["offline"] is False


def test_run_answer_quality_finetuned_calls_answer_bare_not_answer():
    golden_set = [{"id": "q1", "question": "q?", "match_type": "substring", "expected": "x"}]
    answerer = _FakeBareAnswerer({"q?": "x"})

    run_answer_quality_finetuned(answerer, golden_set)

    # answer_bare takes only the question -- no context block was built or
    # passed, confirming this path skips retrieval entirely.
    assert answerer.calls == ["q?"]


def test_run_answer_quality_finetuned_flags_offline_message():
    golden_set = [{"id": "q1", "question": "q?", "match_type": "exact", "expected": "Yes"}]
    answerer = _FakeBareAnswerer({"q?": OFFLINE_MESSAGE})

    results = run_answer_quality_finetuned(answerer, golden_set)

    assert results[0]["offline"] is True
    assert results[0]["passed"] is False
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_run_eval.py -v -k finetuned`
Expected: FAIL with `ImportError: cannot import name 'run_answer_quality_finetuned'`

- [ ] **Step 3: Implement the new function, constant, and CLI flags**

In `scripts/run_eval.py`, add the import and constant near the top:

```python
import os
...
from rag.answer import OFFLINE_MESSAGE, OllamaAnswerer
...
FINETUNED_MODEL_NAME = "pikarag-finetuned"
```

Add the new function after `run_answer_quality`:

```python
def run_answer_quality_finetuned(answerer, golden_set: list[dict]) -> list[dict]:
    """Like run_answer_quality, but calls the bare fine-tuned model directly
    (no retrieval, no context block) and grades every entry on
    answer-correctness against `expected` -- there's no retrieval step to
    measure recall@5 on without a context block."""
    results = []
    for entry in golden_set:
        actual = answerer.answer_bare(entry["question"])
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
```

Replace `main()` with:

```python
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
    parser.add_argument(
        "--model",
        choices=["rag", "finetuned"],
        default="rag",
        help="'rag' (default): existing retrieval-grounded /ask path, graded on answer-correctness "
        "(recall@5 is measured separately, see tests/test_eval_retrieval.py). "
        "'finetuned': bare pikarag-finetuned Ollama model, no retrieval, graded on answer-correctness.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional path to write the raw per-question results as JSON -- feed two such files "
        "(one per --model) to eval/report.py to compare rag vs. finetuned side by side.",
    )
    args = parser.parse_args()

    golden_set = json.loads(GOLDEN_SET_PATH.read_text())

    if args.model == "finetuned":
        answerer = OllamaAnswerer(
            host=os.environ["LLM_HOST"],
            model=FINETUNED_MODEL_NAME,
            timeout=float(os.environ.get("LLM_TIMEOUT", "30")),
        )
        results = run_answer_quality_finetuned(answerer, golden_set)
    else:
        records = json.loads(RECORDS_PATH.read_text())
        items = json.loads(ITEMS_PATH.read_text())
        answerer = _build_answerer()
        index = _build_real_index(records, items, client=chromadb.Client())
        bm25_index = BM25Index(records, items)
        results = run_answer_quality(index, answerer, golden_set, records, items, bm25_index)

    print_report(results)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(results, indent=2) + "\n")
        print(f"Wrote raw results to {args.output}")

    failed_count = sum(1 for r in results if not r["passed"])
    sys.exit(1 if failed_count else 0)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_run_eval.py -v`
Expected: all pass (existing `run_answer_quality`/`print_report` tests + new `run_answer_quality_finetuned` tests)

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest -q`
Expected: all tests pass, no regressions elsewhere.

- [ ] **Step 6: Commit**

```bash
git add scripts/run_eval.py tests/test_run_eval.py
git commit -m "feat: add --model finetuned and --output flags to the eval harness" -m "$(printf 'Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>')"
```

---

### Task 5: `eval/report.py` — side-by-side comparison

**Files:**
- Create: `eval/report.py`
- Test: `tests/test_eval_report.py`

**Interfaces:**
- Consumes: two JSON files shaped like Task 4's `--output` (`list[dict]` with `id`/`question`/`expected`/`actual`/`passed`/`offline` keys).
- Produces: `build_comparison(rag_results, finetuned_results) -> list[dict]`, `summarize(results) -> dict`, `format_report(rag_results, finetuned_results) -> str`. No other task calls these directly -- this is the terminal reporting step run manually after two `scripts/run_eval.py --output ...` invocations.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_eval_report.py`:

```python
from eval.report import build_comparison, format_report, summarize

_RAG_RESULTS = [
    {"id": "q1", "question": "q1?", "expected": "Yes", "actual": "Yes.", "passed": True, "offline": False},
    {"id": "q2", "question": "q2?", "expected": "No", "actual": "Yes.", "passed": False, "offline": False},
]

_FINETUNED_RESULTS = [
    {"id": "q1", "question": "q1?", "expected": "Yes", "actual": "Yes indeed.", "passed": True, "offline": False},
    {"id": "q2", "question": "q2?", "expected": "No", "actual": "No.", "passed": True, "offline": False},
]


def test_build_comparison_pairs_up_matching_ids():
    comparison = build_comparison(_RAG_RESULTS, _FINETUNED_RESULTS)

    assert comparison == [
        {"id": "q1", "question": "q1?", "rag_passed": True, "finetuned_passed": True},
        {"id": "q2", "question": "q2?", "rag_passed": False, "finetuned_passed": True},
    ]


def test_build_comparison_handles_a_missing_finetuned_entry():
    comparison = build_comparison(_RAG_RESULTS, [_FINETUNED_RESULTS[0]])

    assert comparison[1]["finetuned_passed"] is None


def test_summarize_reports_pass_count_and_accuracy():
    summary = summarize(_RAG_RESULTS)

    assert summary == {"total": 2, "passed": 1, "accuracy": 0.5}


def test_format_report_names_every_question_and_both_summaries():
    report = format_report(_RAG_RESULTS, _FINETUNED_RESULTS)

    assert "q1" in report
    assert "q2" in report
    assert "RAG" in report
    assert "Fine-tuned" in report
    assert "1/2" in report  # rag summary
    assert "2/2" in report  # finetuned summary
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_eval_report.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'eval.report'`

- [ ] **Step 3: Implement `eval/report.py`**

```python
import argparse
import json
from pathlib import Path


def build_comparison(rag_results: list[dict], finetuned_results: list[dict]) -> list[dict]:
    finetuned_by_id = {r["id"]: r for r in finetuned_results}
    comparison = []
    for rag_r in rag_results:
        finetuned_r = finetuned_by_id.get(rag_r["id"])
        comparison.append({
            "id": rag_r["id"],
            "question": rag_r["question"],
            "rag_passed": rag_r["passed"],
            "finetuned_passed": finetuned_r["passed"] if finetuned_r is not None else None,
        })
    return comparison


def summarize(results: list[dict]) -> dict:
    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    return {"total": total, "passed": passed, "accuracy": passed / total if total else 0.0}


def format_report(rag_results: list[dict], finetuned_results: list[dict]) -> str:
    comparison = build_comparison(rag_results, finetuned_results)
    rag_summary = summarize(rag_results)
    finetuned_summary = summarize(finetuned_results)

    lines = ["Question | RAG | Fine-tuned", "--- | --- | ---"]
    for row in comparison:
        rag_mark = "PASS" if row["rag_passed"] else "FAIL"
        if row["finetuned_passed"] is None:
            finetuned_mark = "N/A"
        else:
            finetuned_mark = "PASS" if row["finetuned_passed"] else "FAIL"
        lines.append(f"{row['id']} | {rag_mark} | {finetuned_mark}")

    lines.append("")
    lines.append(
        f"RAG: {rag_summary['passed']}/{rag_summary['total']} ({rag_summary['accuracy']:.1%}) -- "
        f"Fine-tuned: {finetuned_summary['passed']}/{finetuned_summary['total']} "
        f"({finetuned_summary['accuracy']:.1%})"
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Tabulate RAG-path vs. fine-tuned-path answer accuracy side by side, from two "
        "scripts/run_eval.py --output result files."
    )
    parser.add_argument("--rag-results", type=Path, required=True)
    parser.add_argument("--finetuned-results", type=Path, required=True)
    args = parser.parse_args()

    rag_results = json.loads(args.rag_results.read_text())
    finetuned_results = json.loads(args.finetuned_results.read_text())

    print(format_report(rag_results, finetuned_results))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_eval_report.py -v`
Expected: all pass

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest -q`
Expected: all tests pass, no regressions elsewhere.

- [ ] **Step 6: Commit**

```bash
git add eval/report.py tests/test_eval_report.py
git commit -m "feat: add eval/report.py to tabulate rag vs finetuned accuracy side by side" -m "$(printf 'Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>')"
```

---

### Task 6: Training notebook and serving doc (manual, not unit-tested)

**Files:**
- Create: `notebooks/finetune_llama3.2.ipynb`
- Create: `docs/finetuned-model-serving.md`

**Interfaces:**
- Consumes: `data/finetune/train.jsonl` (Task 2).
- Produces: (outside this repo's automated tests) a LoRA adapter directory downloaded locally after running the notebook on Colab/Kaggle, then a `pikarag-finetuned` Ollama model after following `docs/finetuned-model-serving.md`. `scripts/run_eval.py --model finetuned` (Task 4) is what exercises the resulting Ollama model.

This task has no failing-test step -- per the spec's Testing section, the notebook is a manual, one-time, off-repo run with no unit tests of its own; its *output* is what Task 4's `--model finetuned` path exercises. Write both files directly.

- [ ] **Step 1: Create `notebooks/finetune_llama3.2.ipynb`**

A Jupyter notebook (plain JSON, `nbformat` 4) with these cells, in order. Each is its own cell; markdown cells are `"cell_type": "markdown"`, code cells `"cell_type": "code"` with `"outputs": []` and `"execution_count": null` (never-run template, filled in when actually executed on Colab):

1. Markdown: title + one-paragraph explanation — "LoRA fine-tune of Llama3.2-3B on PikaRAG's generated training pairs (`data/finetune/train.jsonl`), run once on a free-tier Colab T4 GPU. Training only -- serving stays local via Ollama, see `docs/finetuned-model-serving.md` for the merge/convert/quantize/deploy steps after this notebook produces an adapter." Note the base model choice mirrors the live RAG path's `llama3.2:3b` for an apples-to-apples comparison.
2. Code: `!pip install -q transformers peft bitsandbytes accelerate datasets`
3. Code: upload/mount `train.jsonl` (Colab-specific):
   ```python
   from google.colab import files
   uploaded = files.upload()  # select data/finetune/train.jsonl
   ```
4. Code: load and format the dataset as chat-formatted text:
   ```python
   import json
   from datasets import Dataset

   pairs = [json.loads(line) for line in open("train.jsonl")]

   def to_chat_text(pair):
       return (
           "<|start_header_id|>user<|end_header_id|>\n\n"
           f"{pair['question']}<|eot_id|>"
           "<|start_header_id|>assistant<|end_header_id|>\n\n"
           f"{pair['answer']}<|eot_id|>"
       )

   dataset = Dataset.from_list([{"text": to_chat_text(p)} for p in pairs])
   print(dataset)
   ```
5. Code: load the base model in 4-bit and attach a LoRA adapter:
   ```python
   import torch
   from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
   from peft import LoraConfig, get_peft_model

   MODEL_NAME = "meta-llama/Llama-3.2-3B-Instruct"

   bnb_config = BitsAndBytesConfig(
       load_in_4bit=True,
       bnb_4bit_quant_type="nf4",
       bnb_4bit_compute_dtype=torch.bfloat16,
   )

   tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
   tokenizer.pad_token = tokenizer.eos_token

   model = AutoModelForCausalLM.from_pretrained(
       MODEL_NAME, quantization_config=bnb_config, device_map="auto"
   )

   lora_config = LoraConfig(
       r=16,
       lora_alpha=32,
       target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
       lora_dropout=0.05,
       bias="none",
       task_type="CAUSAL_LM",
   )
   model = get_peft_model(model, lora_config)
   model.print_trainable_parameters()
   ```
6. Code: tokenize and train:
   ```python
   from transformers import TrainingArguments, Trainer, DataCollatorForLanguageModeling

   def tokenize(example):
       return tokenizer(example["text"], truncation=True, max_length=256, padding="max_length")

   tokenized = dataset.map(tokenize, remove_columns=["text"])

   training_args = TrainingArguments(
       output_dir="./pikarag-lora",
       per_device_train_batch_size=4,
       gradient_accumulation_steps=4,
       num_train_epochs=3,
       learning_rate=2e-4,
       fp16=False,
       bf16=True,
       logging_steps=20,
       save_strategy="epoch",
       report_to="none",
   )

   trainer = Trainer(
       model=model,
       args=training_args,
       train_dataset=tokenized,
       data_collator=DataCollatorForLanguageModeling(tokenizer, mlm=False),
   )
   trainer.train()
   ```
7. Code: merge the adapter into the base weights and save locally:
   ```python
   merged_model = model.merge_and_unload()
   merged_model.save_pretrained("./pikarag-finetuned-merged", safe_serialization=True)
   tokenizer.save_pretrained("./pikarag-finetuned-merged")
   ```
8. Code: zip and download the merged model directory:
   ```python
   import shutil
   shutil.make_archive("pikarag-finetuned-merged", "zip", "pikarag-finetuned-merged")
   files.download("pikarag-finetuned-merged.zip")
   ```
9. Markdown: "Next: follow `docs/finetuned-model-serving.md` on the machine serving Ollama for this project to convert the downloaded merged model to a quantized GGUF and register it as `pikarag-finetuned`."

Write this notebook's JSON directly with `Write` (a Python script to construct it via `nbformat` isn't worth the indirection for a one-time file) -- use `nbformat` 4, `nbformat_minor` 5, and a `metadata.kernelspec` naming Python 3, so it opens cleanly in Colab/Jupyter.

- [ ] **Step 2: Create `docs/finetuned-model-serving.md`**

```markdown
# Serving the fine-tuned model locally via Ollama

Run this on whichever machine currently serves Ollama for the project
(the Windows laptop, per `2026-09-13-local-llm-migration-design.md`; a
future M4 Pro Mac is a documented option, not built around). These are
manual, one-time steps per notebook run -- not automated, not run in CI.

## Prerequisites

- The merged model directory downloaded from
  `notebooks/finetune_llama3.2.ipynb` (Task 6, step 8's zip), unzipped
  locally.
- [llama.cpp](https://github.com/ggerganov/llama.cpp) cloned and built
  locally, for `convert_hf_to_gguf.py` and `llama-quantize`.
- Ollama already installed and running (it already is -- this is the same
  host serving the live `/ask` RAG path).

## Steps

1. Convert the merged FP16 HuggingFace model to GGUF:

   ```bash
   python /path/to/llama.cpp/convert_hf_to_gguf.py \
     ./pikarag-finetuned-merged \
     --outfile pikarag-finetuned-f16.gguf \
     --outtype f16
   ```

2. Quantize, matching the existing `llama3.2:latest` quantization already
   in use for the RAG path's model:

   ```bash
   /path/to/llama.cpp/llama-quantize \
     pikarag-finetuned-f16.gguf \
     pikarag-finetuned-q4.gguf \
     Q4_K_M
   ```

3. Write a `Modelfile` next to the quantized GGUF:

   ```
   FROM ./pikarag-finetuned-q4.gguf
   ```

4. Register the model with Ollama:

   ```bash
   ollama create pikarag-finetuned -f Modelfile
   ```

5. Confirm it's available:

   ```bash
   ollama list
   ```

   `pikarag-finetuned` should now appear alongside `llama3.2:latest`.

## Running the comparison

From the repo root, on a machine with `LLM_HOST` pointed at this Ollama
instance:

```bash
python -m scripts.run_eval --with-answers --model rag --output /tmp/rag_results.json
python -m scripts.run_eval --with-answers --model finetuned --output /tmp/finetuned_results.json
python -m eval.report --rag-results /tmp/rag_results.json --finetuned-results /tmp/finetuned_results.json
```
```

- [ ] **Step 3: Commit**

```bash
git add notebooks/finetune_llama3.2.ipynb docs/finetuned-model-serving.md
git commit -m "docs: add fine-tuning training notebook and local serving guide" -m "$(printf 'Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>')"
```

---

### Task 7: Update `IMPROVEMENTS.md`

**Files:**
- Modify: `IMPROVEMENTS.md`

- [ ] **Step 1: Mark the item done**

In `IMPROVEMENTS.md`'s "Fine-tune vs. RAG comparison" bullet (the one currently reading "architectural spec written and committed... Not yet implemented"), replace it with an "implemented" note in the style of the neighboring "Ability/held-item interactions — done." bullet: what was built (training data generator + committed `data/finetune/train.jsonl`, `answer_bare` on `OllamaAnswerer`, `--model rag|finetuned`/`--output` on `scripts/run_eval.py`, `eval/report.py`, the Colab notebook, the serving doc), the final test count from `python -m pytest -q`, and a note that the actual training run / model comparison numbers are a manual follow-up (this plan builds the infrastructure; running the notebook on Colab and filling in real accuracy numbers for the portfolio writeup happens outside CI, at the user's convenience).

- [ ] **Step 2: Commit**

```bash
git add IMPROVEMENTS.md
git commit -m "docs: mark fine-tune vs RAG comparison infrastructure done in the improvement backlog" -m "$(printf 'Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>')"
```
