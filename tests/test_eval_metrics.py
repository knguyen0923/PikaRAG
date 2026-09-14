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
