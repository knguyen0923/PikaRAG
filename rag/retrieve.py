from typing import Optional

from rag.entity import detect_entity


def build_context_block(
    index,
    question: str,
    records: Optional[list] = None,
    items: Optional[list] = None,
    n_results: int = 5,
) -> str:
    entity = detect_entity(question, records or [], items or [])
    if entity:
        matches = index.query(question, n_results=n_results, where={entity["field"]: entity["name"]})
        if not matches:
            matches = index.query(question, n_results=n_results)
    else:
        matches = index.query(question, n_results=n_results)
    return "\n".join(match["text"] for match in matches)
