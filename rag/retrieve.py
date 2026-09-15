from typing import Optional

from rag.entity import detect_entity


def build_context_block(
    index,
    question: str,
    records: Optional[list] = None,
    items: Optional[list] = None,
    n_results: int = 5,
) -> dict:
    entity = detect_entity(question, records or [], items or [])
    if entity:
        matches = index.query(question, n_results=n_results, where={entity["field"]: entity["name"]})
        if not matches:
            matches = index.query(question, n_results=n_results)
    else:
        matches = index.query(question, n_results=n_results)
    return {
        "text": "\n".join(match["text"] for match in matches),
        "sources": [
            {
                "name": match["metadata"].get("pokemon") or match["metadata"].get("item"),
                "chunk_type": match["metadata"]["chunk_type"],
            }
            for match in matches
        ],
        "retrieved_chunks": [
            {"id": match["id"], "distance": match["distance"]} for match in matches
        ],
        "best_distance": min((match["distance"] for match in matches), default=None),
    }
