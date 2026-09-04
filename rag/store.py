import uuid
from typing import Optional

import chromadb

from rag.embed import build_chunks


class ChromaIndex:
    """Chroma-backed vector index over Pokemon record chunks."""

    def __init__(self, embedder, client=None, collection_name: Optional[str] = None):
        self._embedder = embedder
        self._client = client or chromadb.Client()
        # Default to a fresh collection per instance so unrelated indexes
        # (e.g. across tests) never share state through Chroma's process-wide
        # default backend.
        name = collection_name or f"pokemon-{uuid.uuid4().hex}"
        self._collection = self._client.get_or_create_collection(name)

    def build(self, records: list[dict]) -> None:
        chunks = [chunk for record in records for chunk in build_chunks(record)]
        embeddings = self._embedder.embed([chunk["text"] for chunk in chunks])
        self._collection.upsert(
            ids=[chunk["id"] for chunk in chunks],
            embeddings=embeddings,
            documents=[chunk["text"] for chunk in chunks],
            metadatas=[
                {"pokemon": chunk["pokemon"], "chunk_type": chunk["chunk_type"]} for chunk in chunks
            ],
        )

    def query(self, text: str, n_results: int = 5) -> list[dict]:
        embedding = self._embedder.embed([text])[0]
        result = self._collection.query(query_embeddings=[embedding], n_results=n_results)
        return [
            {
                "id": result["ids"][0][i],
                "text": result["documents"][0][i],
                "metadata": result["metadatas"][0][i],
                "distance": result["distances"][0][i],
            }
            for i in range(len(result["ids"][0]))
        ]
