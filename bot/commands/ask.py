import asyncio
from typing import Optional

from rag.answer import OFFLINE_MESSAGE
from rag.retrieve import build_context_block

GATE_MESSAGE = "I don't have solid information on that."

# Empirically tuned against the real embedding index (all-MiniLM-L6-v2) and
# the eval harness's 48-question golden set: every golden question's best
# match distance measured <= 1.3565 -- this is the hard, reproducible
# ceiling (re-derive it by running the golden set through
# build_context_block if the embedding model or Chroma's distance metric
# ever changes; see tests/test_eval_retrieval.py's
# test_golden_set_best_distances_stay_under_the_confidence_gate_threshold,
# which guards this automatically). A sample of out-of-domain questions
# ("What is the capital of France?", etc.) measured as low as ~1.42 in one
# sample, so the margin above 1.4 is thin, not a wide gap -- 1.4 was chosen
# to sit just above the golden set's ceiling, favoring never gating a real
# answerable question over catching every possible out-of-domain one.
DISTANCE_THRESHOLD = 1.4


def _format_sources(sources: list) -> str:
    return ", ".join(f"{s['name']} ({s['chunk_type']})" for s in sources)


def format_ask_response(result: dict) -> str:
    """Render an ask_response()/ask_response_async() result dict as the
    final display text, with a trailing "Sources: ..." line when sources
    are present."""
    if not result["sources"]:
        return result["answer"]
    return f"{result['answer']}\n\nSources: {_format_sources(result['sources'])}"


def ask_response(
    index,
    answerer,
    question: str,
    records: Optional[list] = None,
    items: Optional[list] = None,
    n_results: int = 5,
    extra_context: Optional[str] = None,
) -> dict:
    context = build_context_block(index, question, records=records, items=items, n_results=n_results)

    if not extra_context and (context["best_distance"] is None or context["best_distance"] > DISTANCE_THRESHOLD):
        return {
            "answer": GATE_MESSAGE,
            "sources": [],
            "retrieved_chunks": context["retrieved_chunks"],
            "best_distance": context["best_distance"],
        }

    context_text = context["text"]
    if extra_context:
        context_text = f"{extra_context}\n\n{context_text}"

    answer = answerer.answer(question, context_text)
    if answer == OFFLINE_MESSAGE:
        return {
            "answer": answer,
            "sources": [],
            "retrieved_chunks": context["retrieved_chunks"],
            "best_distance": context["best_distance"],
        }

    return {
        "answer": answer,
        "sources": context["sources"],
        "retrieved_chunks": context["retrieved_chunks"],
        "best_distance": context["best_distance"],
    }


async def ask_response_async(
    index,
    answerer,
    question: str,
    records: Optional[list] = None,
    items: Optional[list] = None,
    n_results: int = 5,
    extra_context: Optional[str] = None,
) -> dict:
    """Run ask_response in a worker thread so the caller's event loop stays free.

    Both index.query (CPU-bound sentence-transformer encode) and
    answerer.answer (blocking network call) are synchronous; offloading the
    whole call keeps discord.py's event loop responsive during either one.
    """
    return await asyncio.to_thread(
        ask_response, index, answerer, question, records, items, n_results, extra_context
    )
