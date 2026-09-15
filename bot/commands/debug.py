from typing import Optional


def format_debug_last(row: Optional[dict]) -> str:
    """Render the most recent ask_log row (from
    rag.observability.get_last_ask_log) for the /debug-last admin command."""
    if row is None:
        return "No /ask calls logged yet."

    if row["sources"]:
        sources_text = ", ".join(f"{s['name']} ({s['chunk_type']})" for s in row["sources"])
    else:
        sources_text = "none"

    if row["retrieved_chunks"]:
        chunks_text = ", ".join(
            f"{c['id']} (distance {c['distance']:.4f})" for c in row["retrieved_chunks"]
        )
    else:
        chunks_text = "none"

    best_distance_text = f"{row['best_distance']:.4f}" if row["best_distance"] is not None else "none"

    return (
        f"**Timestamp:** {row['timestamp']}\n"
        f"**Question:** {row['question']}\n"
        f"**Answer:** {row['answer']}\n"
        f"**Sources:** {sources_text}\n"
        f"**Retrieved chunks:** {chunks_text}\n"
        f"**Best distance:** {best_distance_text}\n"
        f"**Gate fired:** {row['gate_fired']}\n"
        f"**Degraded (offline):** {row['degraded']}\n"
        f"**Latency:** {row['latency_ms']}ms"
    )
