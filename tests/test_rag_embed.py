import numpy as np

from rag.embed import SentenceTransformerEmbedder, build_chunks

_RECORD = {
    "name": "Abomasnow",
    "types": ["Grass", "Ice"],
    "base_stats": {"hp": 90, "attack": 92, "defense": 75, "sp_attack": 92, "sp_defense": 85, "speed": 60},
    "abilities": ["Snow Warning", "Soundproof"],
    "learnset": ["Blizzard", "Wood Hammer", "Earthquake"],
    "legal_in": ["M-B"],
}


def test_build_chunks_returns_one_stats_chunk_and_one_moveset_chunk():
    chunks = build_chunks(_RECORD)

    chunk_types = {chunk["chunk_type"] for chunk in chunks}
    assert chunk_types == {"stats", "moveset"}
    assert all(chunk["pokemon"] == "Abomasnow" for chunk in chunks)
    assert all(chunk["id"].startswith("Abomasnow-") for chunk in chunks)


def test_stats_chunk_text_contains_types_and_base_stats():
    chunks = build_chunks(_RECORD)
    stats_chunk = next(c for c in chunks if c["chunk_type"] == "stats")

    assert "Grass" in stats_chunk["text"]
    assert "Ice" in stats_chunk["text"]
    assert "92" in stats_chunk["text"]
    assert "Snow Warning" in stats_chunk["text"]


def test_moveset_chunk_text_contains_learnset_moves():
    chunks = build_chunks(_RECORD)
    moveset_chunk = next(c for c in chunks if c["chunk_type"] == "moveset")

    assert "Blizzard" in moveset_chunk["text"]
    assert "Wood Hammer" in moveset_chunk["text"]


class _FakeModel:
    def encode(self, texts):
        return [[float(len(text))] for text in texts]


def test_sentence_transformer_embedder_delegates_to_injected_model():
    embedder = SentenceTransformerEmbedder(model=_FakeModel())

    vectors = embedder.embed(["abc", "de"])

    assert vectors == [[3.0], [2.0]]


class _NumpyFakeModel:
    """Mimics the real SentenceTransformer.encode return shape: a numpy
    array of numpy.float32 rows, not plain Python floats."""

    def encode(self, texts):
        return np.array([[len(text), 0.0] for text in texts], dtype="float32")


def test_sentence_transformer_embedder_returns_plain_python_floats():
    # Chroma's upsert rejects lists containing numpy scalar types even
    # though it accepts numpy arrays wholesale -- list(numpy_row) alone
    # would leave numpy.float32 elements behind, so this must be caught.
    embedder = SentenceTransformerEmbedder(model=_NumpyFakeModel())

    vectors = embedder.embed(["abc"])

    assert all(isinstance(value, float) for value in vectors[0])
