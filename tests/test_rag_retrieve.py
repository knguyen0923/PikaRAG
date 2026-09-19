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
            {
                "id": "Gyarados-stats",
                "text": "Gyarados is a Water/Flying-type Pokemon.",
                "metadata": {"pokemon": "Gyarados", "chunk_type": "stats"},
                "distance": 0.4,
            },
            {
                "id": "Gyarados-moveset",
                "text": "Gyarados's legal moveset includes: Waterfall.",
                "metadata": {"pokemon": "Gyarados", "chunk_type": "moveset"},
                "distance": 0.5,
            },
        ]
    )

    result = build_context_block(index, "How bulky is Gyarados?")

    assert "Gyarados is a Water/Flying-type Pokemon." in result["text"]
    assert "Gyarados's legal moveset includes: Waterfall." in result["text"]


def test_build_context_block_returns_empty_text_sources_and_distance_for_no_matches():
    index = _FakeIndex(matches=[])

    result = build_context_block(index, "Unknown question")

    assert result["text"] == ""
    assert result["sources"] == []
    assert result["best_distance"] is None
    assert result["retrieved_chunks"] == []


def test_build_context_block_returns_sources_from_matched_chunk_metadata():
    index = _FakeIndex(
        matches=[
            {
                "id": "Gyarados-stats",
                "text": "Gyarados is a Water/Flying-type Pokemon.",
                "metadata": {"pokemon": "Gyarados", "chunk_type": "stats"},
                "distance": 0.4,
            },
            {
                "id": "item-Life Orb",
                "text": "Life Orb: Boosts move power.",
                "metadata": {"item": "Life Orb", "chunk_type": "item"},
                "distance": 0.6,
            },
        ]
    )

    result = build_context_block(index, "How bulky is Gyarados?")

    assert result["sources"] == [
        {"name": "Gyarados", "chunk_type": "stats"},
        {"name": "Life Orb", "chunk_type": "item"},
    ]


def test_build_context_block_returns_retrieved_chunks_with_ids_and_distances():
    index = _FakeIndex(
        matches=[
            {
                "id": "Gyarados-stats",
                "text": "Gyarados is a Water/Flying-type Pokemon.",
                "metadata": {"pokemon": "Gyarados", "chunk_type": "stats"},
                "distance": 0.4,
            },
            {
                "id": "item-Life Orb",
                "text": "Life Orb: Boosts move power.",
                "metadata": {"item": "Life Orb", "chunk_type": "item"},
                "distance": 0.6,
            },
        ]
    )

    result = build_context_block(index, "How bulky is Gyarados?")

    assert result["retrieved_chunks"] == [
        {"id": "Gyarados-stats", "distance": 0.4},
        {"id": "item-Life Orb", "distance": 0.6},
    ]


def test_build_context_block_returns_the_smallest_distance_as_best_distance():
    index = _FakeIndex(
        matches=[
            {"id": "a-stats", "text": "a", "metadata": {"pokemon": "A", "chunk_type": "stats"}, "distance": 0.9},
            {"id": "b-stats", "text": "b", "metadata": {"pokemon": "B", "chunk_type": "stats"}, "distance": 0.3},
            {"id": "c-stats", "text": "c", "metadata": {"pokemon": "C", "chunk_type": "stats"}, "distance": 0.7},
        ]
    )

    result = build_context_block(index, "Some question")

    assert result["best_distance"] == 0.3


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
        {
            "id": "Abomasnow-stats",
            "text": "Abomasnow stats chunk",
            "metadata": {"pokemon": "Abomasnow", "chunk_type": "stats"},
            "distance": 0.4,
        },
        {
            "id": "Gyarados-stats",
            "text": "Unrelated Gyarados chunk",
            "metadata": {"pokemon": "Gyarados", "chunk_type": "stats"},
            "distance": 0.5,
        },
    ])

    build_context_block(index, "Does Abomasnow learn Attract?", records=_RECORDS, items=_ITEMS)

    assert index.queries[0]["where"] == {"pokemon": "Abomasnow"}


def test_build_context_block_falls_back_to_unfiltered_when_no_entity_detected():
    index = _FakeIndexWithWhere(matches=[
        {
            "id": "Whatever-stats",
            "text": "Some chunk",
            "metadata": {"pokemon": "Whatever", "chunk_type": "stats"},
            "distance": 0.5,
        },
    ])

    build_context_block(index, "What is the weather like?", records=_RECORDS, items=_ITEMS)

    assert index.queries[0]["where"] is None


def test_build_context_block_falls_back_to_unfiltered_when_filtered_query_returns_nothing():
    index = _FakeIndexWithWhere(matches=[
        {
            "id": "item-Some Item",
            "text": "Unrelated chunk with no pokemon metadata",
            "metadata": {"item": "Some Item", "chunk_type": "item"},
            "distance": 0.6,
        },
    ])

    result = build_context_block(
        index, "Does Abomasnow learn Attract?", records=_RECORDS, items=_ITEMS
    )

    assert len(index.queries) == 2
    assert index.queries[0]["where"] == {"pokemon": "Abomasnow"}
    assert index.queries[1]["where"] is None
    assert "Unrelated chunk with no pokemon metadata" in result["text"]




class _FakeBM25Index:
    def __init__(self, results):
        self._results = results
        self.searches = []

    def search(self, question, n_results=10):
        self.searches.append((question, n_results))
        return self._results[:n_results]


class _FakeIndexNoWhere:
    """Same as _FakeIndex above but records every call for pool-size assertions."""

    def __init__(self, matches):
        self._matches = matches
        self.queries = []

    def query(self, text, n_results=5):
        self.queries.append({"text": text, "n_results": n_results})
        return self._matches[:n_results]


def test_build_context_block_ignores_bm25_index_by_default_unchanged_behavior():
    index = _FakeIndexNoWhere(matches=[
        {"id": "a-stats", "text": "a", "metadata": {"pokemon": "A", "chunk_type": "stats"}, "distance": 0.4},
    ])

    build_context_block(index, "Some question", n_results=3)

    assert index.queries == [{"text": "Some question", "n_results": 3}]


def test_build_context_block_fuses_a_bm25_only_hit_into_the_results():
    # Vector search returns nothing relevant; BM25 finds the exact-keyword chunk.
    index = _FakeIndexNoWhere(matches=[
        {"id": "unrelated-stats", "text": "Unrelated chunk", "metadata": {"pokemon": "Unrelated", "chunk_type": "stats"}, "distance": 1.2},
    ])
    bm25_index = _FakeBM25Index(results=[
        {"id": "Aegislash-stats", "text": "Aegislash is a Steel/Ghost-type Pokemon. Abilities: Stance Change.", "pokemon": "Aegislash", "chunk_type": "stats"},
    ])

    result = build_context_block(index, "Which Pokemon has Stance Change?", n_results=2, bm25_index=bm25_index)

    ids = {chunk["id"] for chunk in result["retrieved_chunks"]}
    assert "Aegislash-stats" in ids
    assert "Aegislash is a Steel/Ghost-type Pokemon. Abilities: Stance Change." in result["text"]


def test_build_context_block_bm25_only_hit_never_lowers_best_distance_below_the_real_vector_minimum():
    index = _FakeIndexNoWhere(matches=[
        {"id": "unrelated-stats", "text": "Unrelated chunk", "metadata": {"pokemon": "Unrelated", "chunk_type": "stats"}, "distance": 1.2},
    ])
    bm25_index = _FakeBM25Index(results=[
        {"id": "Aegislash-stats", "text": "Aegislash text", "pokemon": "Aegislash", "chunk_type": "stats"},
    ])

    result = build_context_block(index, "Which Pokemon has Stance Change?", n_results=2, bm25_index=bm25_index)

    assert result["best_distance"] == 1.2


def test_build_context_block_ranks_a_chunk_found_by_both_retrievers_above_a_single_retriever_hit():
    index = _FakeIndexNoWhere(matches=[
        {"id": "both-stats", "text": "Found by both", "metadata": {"pokemon": "Both", "chunk_type": "stats"}, "distance": 0.5},
        {"id": "vector-only-stats", "text": "Vector only", "metadata": {"pokemon": "VectorOnly", "chunk_type": "stats"}, "distance": 0.6},
    ])
    bm25_index = _FakeBM25Index(results=[
        {"id": "both-stats", "text": "Found by both", "pokemon": "Both", "chunk_type": "stats"},
        {"id": "bm25-only-stats", "text": "BM25 only", "pokemon": "BM25Only", "chunk_type": "stats"},
    ])

    result = build_context_block(index, "A question", n_results=1, bm25_index=bm25_index)

    assert result["retrieved_chunks"] == [{"id": "both-stats", "distance": 0.5}]


def test_build_context_block_expands_the_vector_candidate_pool_when_bm25_index_is_given():
    index = _FakeIndexNoWhere(matches=[])
    bm25_index = _FakeBM25Index(results=[])

    build_context_block(index, "A question", n_results=3, bm25_index=bm25_index)

    # Candidate pool must be at least n_results, and wider than a bare n_results=3
    # so fusion has real breadth to work with.
    assert index.queries[0]["n_results"] > 3


def test_build_context_block_breaks_rrf_score_ties_deterministically_by_chunk_id():
    # Both chunks sit at rank 1 in their own retriever, so their RRF scores
    # are exactly equal -- a genuine tie that would otherwise fall back to
    # unordered-set iteration order (hash-seed dependent, non-deterministic
    # across processes/runs).
    index = _FakeIndexNoWhere(matches=[
        {"id": "z-vector-only", "text": "Vector only", "metadata": {"pokemon": "Z", "chunk_type": "stats"}, "distance": 0.5},
    ])
    bm25_index = _FakeBM25Index(results=[
        {"id": "a-bm25-only", "text": "BM25 only", "pokemon": "A", "chunk_type": "stats"},
    ])

    result_1 = build_context_block(index, "A question", n_results=1, bm25_index=bm25_index)
    result_2 = build_context_block(index, "A question", n_results=1, bm25_index=bm25_index)

    # Deterministic: repeated calls with the same tied input always agree,
    # and the winner is the lexicographically smaller chunk id.
    assert result_1 == result_2
    assert result_1["retrieved_chunks"] == [{"id": "a-bm25-only", "distance": 0.5}]
