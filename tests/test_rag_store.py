import re

import chromadb

import rag.store
from rag.store import ChromaIndex

_ABOMASNOW = {
    "name": "Abomasnow",
    "types": ["Grass", "Ice"],
    "base_stats": {"hp": 90, "attack": 92, "defense": 75, "sp_attack": 92, "sp_defense": 85, "speed": 60},
    "abilities": ["Snow Warning", "Soundproof"],
    "learnset": ["Blizzard", "Wood Hammer"],
    "legal_in": ["M-B"],
}

_GYARADOS = {
    "name": "Gyarados",
    "types": ["Water", "Flying"],
    "base_stats": {"hp": 95, "attack": 125, "defense": 79, "sp_attack": 60, "sp_defense": 100, "speed": 81},
    "abilities": ["Intimidate"],
    "learnset": ["Waterfall", "Dragon Dance"],
    "legal_in": ["M-B"],
}


class _BagOfWordsEmbedder:
    """Deterministic, dependency-free stand-in for a real embedding model.

    Assigns each distinct word its own vector slot (built up as words are
    seen) so texts sharing vocabulary land near each other with zero hash
    collisions -- enough to exercise real Chroma similarity search without
    downloading a transformer model in the test suite.
    """

    DIM = 512

    def __init__(self):
        self._vocab_index: dict[str, int] = {}

    def _index_for(self, word: str) -> int:
        if word not in self._vocab_index:
            self._vocab_index[word] = len(self._vocab_index) % self.DIM
        return self._vocab_index[word]

    def embed(self, texts):
        vectors = []
        for text in texts:
            vector = [0.0] * self.DIM
            for word in re.findall(r"[a-z0-9]+", text.lower()):
                vector[self._index_for(word)] += 1.0
            # Unit-normalize so plain L2 distance behaves like cosine distance --
            # otherwise longer documents look "farther" purely from extra
            # unmatched words, regardless of how well they match the query.
            norm = sum(v * v for v in vector) ** 0.5
            vectors.append([v / norm for v in vector] if norm else vector)
        return vectors


def _build_test_index():
    index = ChromaIndex(embedder=_BagOfWordsEmbedder(), client=chromadb.Client())
    index.build([_ABOMASNOW, _GYARADOS])
    return index


def test_query_returns_the_matching_pokemons_stats_chunk():
    index = _build_test_index()

    matches = index.query("Abomasnow base stats and abilities", n_results=1)

    assert matches[0]["metadata"]["pokemon"] == "Abomasnow"
    assert matches[0]["metadata"]["chunk_type"] == "stats"


def test_query_returns_the_matching_pokemons_moveset_chunk():
    index = _build_test_index()

    matches = index.query("Gyarados legal moveset moves", n_results=1)

    assert matches[0]["metadata"]["pokemon"] == "Gyarados"
    assert matches[0]["metadata"]["chunk_type"] == "moveset"


def test_build_indexes_one_chunk_per_record_per_chunk_type():
    index = _build_test_index()

    matches = index.query("Pokemon", n_results=10)

    assert len(matches) == 4


def test_default_client_persists_data_across_instances_at_same_path(tmp_path):
    persist_dir = tmp_path / "chroma"
    embedder = _BagOfWordsEmbedder()

    first = ChromaIndex(embedder=embedder, collection_name="pokemon", persist_directory=str(persist_dir))
    first.build([_ABOMASNOW])

    # A second instance, no client passed, pointed at the same directory --
    # must see the first instance's data without rebuilding.
    second = ChromaIndex(embedder=embedder, collection_name="pokemon", persist_directory=str(persist_dir))
    matches = second.query("Abomasnow base stats", n_results=1)

    assert matches[0]["metadata"]["pokemon"] == "Abomasnow"


def test_default_persist_directory_used_when_none_given(monkeypatch):
    captured = {}

    class _StubPersistentClient:
        def __init__(self, path):
            captured["path"] = path

        def get_or_create_collection(self, name):
            return None

    monkeypatch.setattr(rag.store.chromadb, "PersistentClient", _StubPersistentClient)

    ChromaIndex(embedder=_BagOfWordsEmbedder())

    assert captured["path"] == rag.store.DEFAULT_PERSIST_DIR
