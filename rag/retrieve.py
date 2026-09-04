def build_context_block(index, question: str, n_results: int = 5) -> str:
    matches = index.query(question, n_results=n_results)
    return "\n".join(match["text"] for match in matches)
