from typing import Optional

# Discord embed descriptions are capped at 4096 characters. A long /ask
# question or a long LLM answer (the answerer can produce up to ~1024
# tokens) can push the combined description past that limit, causing
# /debug-last to hard-fail with a generic error. Cap each of the two
# unbounded free-text fields well under the total budget.
_FIELD_CHAR_LIMIT = 1500
_TRUNCATION_MARKER = "…[truncated]"


def _truncate(text: str, limit: int = _FIELD_CHAR_LIMIT) -> str:
    if text is None or len(text) <= limit:
        return text
    return text[:limit] + _TRUNCATION_MARKER


def format_debug_last(row: Optional[dict]) -> str:
    """Render the most recent ask_log row (from
    rag.observability.get_last_ask_log) for the /debug-last admin command."""
    if row is None:
        return "No /ask calls logged yet."

    question = _truncate(row["question"])
    answer = _truncate(row["answer"])

    if row["sources"]:
        sources_text = _truncate(", ".join(f"{s['name']} ({s['chunk_type']})" for s in row["sources"]))
    else:
        sources_text = "none"

    if row["retrieved_chunks"]:
        chunks_text = _truncate(
            ", ".join(f"{c['id']} (distance {c['distance']:.4f})" for c in row["retrieved_chunks"])
        )
    else:
        chunks_text = "none"

    best_distance_text = f"{row['best_distance']:.4f}" if row["best_distance"] is not None else "none"

    return (
        f"**Timestamp:** {row['timestamp']}\n"
        f"**Question:** {question}\n"
        f"**Answer:** {answer}\n"
        f"**Sources:** {sources_text}\n"
        f"**Retrieved chunks:** {chunks_text}\n"
        f"**Best distance:** {best_distance_text}\n"
        f"**Gate fired:** {row['gate_fired']}\n"
        f"**Degraded (offline):** {row['degraded']}\n"
        f"**Latency:** {row['latency_ms']}ms"
    )
