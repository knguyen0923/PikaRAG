from rag.retrieve import build_context_block


def ask_response(index, answerer, question: str, n_results: int = 5) -> str:
    context_block = build_context_block(index, question, n_results=n_results)
    return answerer.answer(question, context_block)
