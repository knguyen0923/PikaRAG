def recall_at_k(index, golden_entries: list[dict], n_results: int = 5) -> float:
    if not golden_entries:
        raise ValueError("recall_at_k requires at least one golden entry")

    hits = 0
    for entry in golden_entries:
        results = index.query(entry["question"], n_results=n_results)
        found_ids = {result["id"] for result in results}
        if entry["source_chunk_id"] in found_ids:
            hits += 1

    return hits / len(golden_entries)
