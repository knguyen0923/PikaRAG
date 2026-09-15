from scripts.run_eval import print_report, run_answer_quality
from rag.answer import OFFLINE_MESSAGE


class _FakeIndex:
    def query(self, text, n_results=5, where=None):
        return [
            {
                "text": "Some context chunk.",
                "metadata": {"pokemon": "Whatever", "chunk_type": "stats"},
                "distance": 0.3,
            }
        ]


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
