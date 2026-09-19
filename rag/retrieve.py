from typing import Optional

from rag.entity import detect_entity

_RRF_K = 60
_CANDIDATE_POOL_SIZE = 10


def _hybrid_matches(index, question: str, n_results: int, bm25_index) -> list:
    """The two currently-unfiltered code paths in build_context_block route
    through here. With no bm25_index (the default, and every pre-hybrid
    caller), this is byte-identical to the old `index.query(question,
    n_results=n_results)` call. With a bm25_index, both retrievers are
    queried over a wider candidate pool and fused by rank via Reciprocal
    Rank Fusion (RRF) -- rank position only, not raw scores, since BM25 and
    cosine-distance scores aren't on comparable scales.
    """
    if bm25_index is None:
        return index.query(question, n_results=n_results)

    candidate_pool = max(n_results, _CANDIDATE_POOL_SIZE)
    vector_matches = index.query(question, n_results=candidate_pool)
    bm25_chunks = bm25_index.search(question, n_results=candidate_pool)

    vector_by_id = {match["id"]: match for match in vector_matches}
    bm25_by_id = {chunk["id"]: chunk for chunk in bm25_chunks}
    vector_rank = {match["id"]: i + 1 for i, match in enumerate(vector_matches)}
    bm25_rank = {chunk["id"]: i + 1 for i, chunk in enumerate(bm25_chunks)}

    # A BM25-only hit (no real vector distance) is never allowed to look
    # more confident than anything the vector query actually found -- give
    # it the worst distance observed in the vector candidate pool, or
    # infinity if the vector pool was empty.
    fallback_distance = max((match["distance"] for match in vector_matches), default=float("inf"))

    def rrf_score(chunk_id: str) -> float:
        score = 0.0
        if chunk_id in vector_rank:
            score += 1.0 / (_RRF_K + vector_rank[chunk_id])
        if chunk_id in bm25_rank:
            score += 1.0 / (_RRF_K + bm25_rank[chunk_id])
        return score

    all_ids = set(vector_rank) | set(bm25_rank)
    fused_ids = sorted(all_ids, key=lambda chunk_id: (-rrf_score(chunk_id), chunk_id))[:n_results]

    fused_matches = []
    for chunk_id in fused_ids:
        if chunk_id in vector_by_id:
            fused_matches.append(vector_by_id[chunk_id])
        else:
            chunk = bm25_by_id[chunk_id]
            fused_matches.append({
                "id": chunk["id"],
                "text": chunk["text"],
                "metadata": {k: v for k, v in chunk.items() if k not in ("id", "text")},
                "distance": fallback_distance,
            })
    return fused_matches


def build_context_block(
    index,
    question: str,
    records: Optional[list] = None,
    items: Optional[list] = None,
    n_results: int = 5,
    bm25_index=None,
) -> dict:
    entity = detect_entity(question, records or [], items or [])
    if entity:
        matches = index.query(question, n_results=n_results, where={entity["field"]: entity["name"]})
        if not matches:
            matches = _hybrid_matches(index, question, n_results, bm25_index)
    else:
        matches = _hybrid_matches(index, question, n_results, bm25_index)
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
