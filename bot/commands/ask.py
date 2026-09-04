import asyncio

from rag.retrieve import build_context_block


def ask_response(index, answerer, question: str, n_results: int = 5) -> str:
    context_block = build_context_block(index, question, n_results=n_results)
    return answerer.answer(question, context_block)


async def ask_response_async(index, answerer, question: str, n_results: int = 5) -> str:
    """Run ask_response in a worker thread so the caller's event loop stays free.

    Both index.query (CPU-bound sentence-transformer encode) and
    answerer.answer (blocking network call) are synchronous; offloading the
    whole call keeps discord.py's event loop responsive during either one.
    """
    return await asyncio.to_thread(ask_response, index, answerer, question, n_results)
