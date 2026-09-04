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
            {"text": "Gyarados is a Water/Flying-type Pokemon.", "metadata": {}},
            {"text": "Gyarados's legal moveset includes: Waterfall.", "metadata": {}},
        ]
    )

    context_block = build_context_block(index, "How bulky is Gyarados?")

    assert "Gyarados is a Water/Flying-type Pokemon." in context_block
    assert "Gyarados's legal moveset includes: Waterfall." in context_block


def test_build_context_block_returns_empty_string_for_no_matches():
    index = _FakeIndex(matches=[])

    context_block = build_context_block(index, "Unknown question")

    assert context_block == ""
