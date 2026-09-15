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
