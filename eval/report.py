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
