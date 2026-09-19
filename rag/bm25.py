import re
from typing import Optional

from rank_bm25 import BM25Okapi

from rag.embed import build_chunks, build_item_chunks


def _tokenize(text: str) -> list:
    return re.findall(r"[a-z0-9]+", text.lower())


class BM25Index:
    """In-memory keyword (BM25) index over the same chunk texts embedded
    into the vector index, built once from the raw records/items (same
    build_chunks/build_item_chunks used by rag/store.py's ChromaIndex.build)
    -- used by rag/retrieve.py's hybrid fallback path so an exact keyword
    match (e.g. an ability name present verbatim in a chunk) isn't lost to
    semantic drift in the embedding space.
    """

    def __init__(self, records: list, items: Optional[list] = None):
        chunks = [chunk for record in records for chunk in build_chunks(record)]
        if items:
            chunks += [chunk for item in items for chunk in build_item_chunks(item)]
        self._chunks = chunks
        self._bm25 = BM25Okapi([_tokenize(chunk["text"]) for chunk in chunks]) if chunks else None

    def search(self, question: str, n_results: int = 10) -> list:
        if self._bm25 is None:
            return []
        scores = self._bm25.get_scores(_tokenize(question))
        ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        return [self._chunks[i] for i in ranked[:n_results] if scores[i] > 0]
