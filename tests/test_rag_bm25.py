from rag.bm25 import BM25Index

_ABOMASNOW = {
    "name": "Abomasnow",
    "types": ["Grass", "Ice"],
    "base_stats": {"hp": 90, "attack": 92, "defense": 75, "sp_attack": 92, "sp_defense": 85, "speed": 60},
    "abilities": ["Snow Warning", "Soundproof"],
    "learnset": ["Blizzard", "Wood Hammer"],
}
_GYARADOS = {
    "name": "Gyarados",
    "types": ["Water", "Flying"],
    "base_stats": {"hp": 95, "attack": 125, "defense": 79, "sp_attack": 60, "sp_defense": 100, "speed": 81},
    "abilities": ["Intimidate"],
    "learnset": ["Waterfall", "Dragon Dance"],
}
_LIFE_ORB = {"name": "Life Orb", "description": "Boosts the power of moves, but the holder loses HP with each hit."}


def test_search_finds_the_chunk_containing_the_exact_keyword_phrase():
    index = BM25Index([_ABOMASNOW, _GYARADOS])

    results = index.search("Which Pokemon has the Snow Warning ability?", n_results=5)

    assert any(r["id"] == "Abomasnow-stats" for r in results)


def test_search_ranks_the_exact_keyword_match_first():
    index = BM25Index([_ABOMASNOW, _GYARADOS])

    results = index.search("Snow Warning ability", n_results=5)

    assert results[0]["id"] == "Abomasnow-stats"


def test_search_includes_item_chunks_when_items_are_given():
    index = BM25Index([_ABOMASNOW], items=[_LIFE_ORB])

    results = index.search("Life Orb power boost", n_results=5)

    assert any(r["id"] == "item-Life Orb" for r in results)


def test_search_excludes_zero_score_chunks():
    index = BM25Index([_ABOMASNOW, _GYARADOS])

    results = index.search("completely unrelated words nowhere in the corpus", n_results=5)

    assert results == []


def test_search_returns_chunk_dicts_with_text_and_metadata():
    index = BM25Index([_ABOMASNOW])

    results = index.search("Snow Warning", n_results=5)

    assert results[0]["text"].startswith("Abomasnow is a Grass/Ice-type Pokemon")
    assert results[0]["pokemon"] == "Abomasnow"
    assert results[0]["chunk_type"] == "stats"


def test_search_respects_n_results():
    index = BM25Index([_ABOMASNOW, _GYARADOS])

    results = index.search("Pokemon", n_results=1)

    assert len(results) <= 1


def test_empty_records_and_items_produces_an_empty_index():
    index = BM25Index([], items=[])

    assert index.search("anything", n_results=5) == []
