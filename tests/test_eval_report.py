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
