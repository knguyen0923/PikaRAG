import argparse
import json
import sys
from pathlib import Path
from typing import Optional

import chromadb

from bot.commands.ask import ask_response
from bot.main import _build_answerer, _build_real_index
from eval.matchers import matches
from rag.answer import OFFLINE_MESSAGE
from rag.bm25 import BM25Index

GOLDEN_SET_PATH = Path("data/eval/golden_set.json")
RECORDS_PATH = Path("data/processed/pokemon_records.json")
ITEMS_PATH = Path("data/source/vgc_items.json")


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

    answerer = _build_answerer()
    index = _build_real_index(records, items, client=chromadb.Client())
    bm25_index = BM25Index(records, items)

    results = run_answer_quality(index, answerer, golden_set, records, items, bm25_index)
    print_report(results)

    failed_count = sum(1 for r in results if not r["passed"])
    sys.exit(1 if failed_count else 0)


if __name__ == "__main__":
    main()
