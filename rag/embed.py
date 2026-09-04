DEFAULT_MODEL_NAME = "all-MiniLM-L6-v2"


def build_chunks(record: dict) -> list[dict]:
    """Turn one processed Pokemon record into retrievable text chunks.

    Separate stats/moveset chunks so retrieval can be precise depending on
    question type, per the chunking strategy in the project plan.
    """
    name = record["name"]
    types = "/".join(record["types"])
    stats = record["base_stats"]
    stats_text = (
        f"{name} is a {types}-type Pokemon with base stats "
        f"HP {stats['hp']}, Attack {stats['attack']}, Defense {stats['defense']}, "
        f"Sp. Atk {stats['sp_attack']}, Sp. Def {stats['sp_defense']}, Speed {stats['speed']}. "
        f"Abilities: {', '.join(record['abilities'])}."
    )
    moveset_text = f"{name}'s legal moveset includes: {', '.join(record['learnset'])}."

    return [
        {"id": f"{name}-stats", "pokemon": name, "chunk_type": "stats", "text": stats_text},
        {"id": f"{name}-moveset", "pokemon": name, "chunk_type": "moveset", "text": moveset_text},
    ]


class SentenceTransformerEmbedder:
    """Local embedding via sentence-transformers.

    Accepts an injected `model` (anything with `.encode(texts)`) so callers
    can swap in a lightweight stand-in for testing without downloading a
    real model.
    """

    def __init__(self, model=None, model_name: str = DEFAULT_MODEL_NAME):
        if model is None:
            from sentence_transformers import SentenceTransformer

            model = SentenceTransformer(model_name)
        self._model = model

    def embed(self, texts: list[str]) -> list[list[float]]:
        # Cast every element to a plain Python float: sentence-transformers
        # returns numpy.float32 rows, and list(row) alone leaves numpy
        # scalars behind -- Chroma's upsert rejects those.
        return [[float(value) for value in vector] for vector in self._model.encode(texts)]
