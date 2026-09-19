import argparse
import json
import os
import sys
from pathlib import Path
from typing import Optional

import chromadb

from bot.commands.ask import ask_response
from bot.main import _build_answerer, _build_real_index
from eval.matchers import matches
from rag.answer import OFFLINE_MESSAGE, OllamaAnswerer
from rag.bm25 import BM25Index

GOLDEN_SET_PATH = Path("data/eval/golden_set.json")
RECORDS_PATH = Path("data/processed/pokemon_records.json")
ITEMS_PATH = Path("data/source/vgc_items.json")
FINETUNED_MODEL_NAME = "pikarag-finetuned"


def run_answer_quality(
    index,
    answerer,
    golden_set: list[dict],
    records: Optional[list] = None,
    items: Optional[list] = None,
    bm25_index: Optional[BM25Index] = None,
) -> list[dict]:
    results = []
    for entry in golden_set:
        actual = ask_response(
            index, answerer, entry["question"], records=records, items=items, bm25_index=bm25_index
        )["answer"]
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


if __name__ == "__main__":
    main()
