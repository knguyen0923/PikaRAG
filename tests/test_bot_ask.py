import asyncio
import time

from bot.commands.ask import ask_response, ask_response_async, format_ask_response
from rag.answer import OFFLINE_MESSAGE


class _FakeIndex:
    def __init__(self, context_matches):
        self._matches = context_matches

    def query(self, text, n_results=5, where=None):
        return self._matches[:n_results]


class _FakeAnswerer:
    def __init__(self, response_text):
        self._response_text = response_text
        self.calls = []

    def answer(self, question, context_block):
        self.calls.append((question, context_block))
        return self._response_text


_CLOSE_MATCH = {
    "id": "Gyarados-stats",
    "text": "Gyarados base HP: 95.",
    "metadata": {"pokemon": "Gyarados", "chunk_type": "stats"},
    "distance": 0.4,
}


def test_ask_response_returns_the_answerers_response():
    index = _FakeIndex(context_matches=[_CLOSE_MATCH])
    answerer = _FakeAnswerer(response_text="Gyarados has 95 base HP.")

    result = ask_response(index, answerer, "How bulky is Gyarados?")

    assert result["answer"] == "Gyarados has 95 base HP."


def test_ask_response_returns_sources_from_the_matched_chunks():
    index = _FakeIndex(context_matches=[_CLOSE_MATCH])
    answerer = _FakeAnswerer(response_text="Gyarados has 95 base HP.")

    result = ask_response(index, answerer, "How bulky is Gyarados?")

    assert result["sources"] == [{"name": "Gyarados", "chunk_type": "stats"}]


def test_ask_response_returns_retrieved_chunks_and_best_distance_from_the_matched_chunks():
    index = _FakeIndex(context_matches=[_CLOSE_MATCH])
    answerer = _FakeAnswerer(response_text="Gyarados has 95 base HP.")

    result = ask_response(index, answerer, "How bulky is Gyarados?")

    assert result["retrieved_chunks"] == [{"id": "Gyarados-stats", "distance": 0.4}]
    assert result["best_distance"] == 0.4


def test_ask_response_passes_retrieved_context_to_the_answerer():
    index = _FakeIndex(context_matches=[_CLOSE_MATCH])
    answerer = _FakeAnswerer(response_text="anything")

    ask_response(index, answerer, "How bulky is Gyarados?")

    question, context_text = answerer.calls[0]
    assert question == "How bulky is Gyarados?"
    assert "Gyarados base HP: 95." in context_text


def test_ask_response_async_returns_the_same_result_as_the_sync_version():
    index = _FakeIndex(context_matches=[_CLOSE_MATCH])
    answerer = _FakeAnswerer(response_text="Gyarados has 95 base HP.")

    result = asyncio.run(ask_response_async(index, answerer, "How bulky is Gyarados?"))

    assert result["answer"] == "Gyarados has 95 base HP."


def test_ask_response_async_does_not_block_the_event_loop():
    # A "slow" sync answerer standing in for a real blocking network call.
    # If ask_response_async ran it directly on the event loop instead of
    # offloading to a thread, the ticker below would be starved for the
    # whole 0.2s and record close to zero ticks.
    class _SlowAnswerer:
        def answer(self, question, context_block):
            time.sleep(0.2)
            return "answer"

    index = _FakeIndex(context_matches=[_CLOSE_MATCH])
    answerer = _SlowAnswerer()

    async def run():
        ticks = 0

        async def ticker():
            nonlocal ticks
            while True:
                await asyncio.sleep(0.01)
                ticks += 1

        ticker_task = asyncio.create_task(ticker())
        result = await ask_response_async(index, answerer, "Q")
        ticker_task.cancel()
        return result, ticks

    result, ticks = asyncio.run(run())

    assert result["answer"] == "answer"
    assert ticks >= 8


def test_ask_response_prepends_extra_context_when_given():
    index = _FakeIndex(context_matches=[_CLOSE_MATCH])
    answerer = _FakeAnswerer(response_text="answer")

    ask_response(index, answerer, "How bulky is Gyarados?", extra_context="Your team: Gyarados")

    question, context_text = answerer.calls[0]
    assert context_text.startswith("Your team: Gyarados")
    assert "Gyarados base HP: 95." in context_text


def test_ask_response_gate_fires_when_best_distance_exceeds_the_threshold():
    far_match = {
        "id": "Whatever-stats",
        "text": "Some barely related chunk.",
        "metadata": {"pokemon": "Whatever", "chunk_type": "stats"},
        "distance": 1.6,
    }
    index = _FakeIndex(context_matches=[far_match])
    answerer = _FakeAnswerer(response_text="should never be returned")

    result = ask_response(index, answerer, "What is the capital of France?")

    assert result == {
        "answer": "I don't have solid information on that.",
        "sources": [],
        "retrieved_chunks": [{"id": "Whatever-stats", "distance": 1.6}],
        "best_distance": 1.6,
    }
    assert answerer.calls == []


def test_ask_response_gate_fires_when_there_are_no_matches_at_all():
    index = _FakeIndex(context_matches=[])
    answerer = _FakeAnswerer(response_text="should never be returned")

    result = ask_response(index, answerer, "Anything")

    assert result == {
        "answer": "I don't have solid information on that.",
        "sources": [],
        "retrieved_chunks": [],
        "best_distance": None,
    }
    assert answerer.calls == []


def test_ask_response_gate_is_bypassed_when_extra_context_is_provided():
    far_match = {
        "id": "Whatever-stats",
        "text": "Some barely related chunk.",
        "metadata": {"pokemon": "Whatever", "chunk_type": "stats"},
        "distance": 1.6,
    }
    index = _FakeIndex(context_matches=[far_match])
    answerer = _FakeAnswerer(response_text="Here's some strategy advice.")

    result = ask_response(
        index, answerer, "What should I lead with?", extra_context="Your team: Gyarados, Garchomp"
    )

    assert result["answer"] == "Here's some strategy advice."
    assert len(answerer.calls) == 1
    question, context_text = answerer.calls[0]
    assert context_text.startswith("Your team: Gyarados, Garchomp")


def test_ask_response_does_not_gate_when_best_distance_is_exactly_the_threshold():
    boundary_match = {
        "id": "Whatever-stats",
        "text": "Some chunk.",
        "metadata": {"pokemon": "Whatever", "chunk_type": "stats"},
        "distance": 1.4,
    }
    index = _FakeIndex(context_matches=[boundary_match])
    answerer = _FakeAnswerer(response_text="An answer.")

    result = ask_response(index, answerer, "A question")

    assert result["answer"] == "An answer."
    assert answerer.calls != []


def test_ask_response_returns_no_sources_when_the_answerer_reports_offline():
    index = _FakeIndex(context_matches=[_CLOSE_MATCH])
    answerer = _FakeAnswerer(response_text=OFFLINE_MESSAGE)

    result = ask_response(index, answerer, "How bulky is Gyarados?")

    assert result == {
        "answer": OFFLINE_MESSAGE,
        "sources": [],
        "retrieved_chunks": [{"id": "Gyarados-stats", "distance": 0.4}],
        "best_distance": 0.4,
    }
    assert answerer.calls != []  # confirms the LLM WAS called -- distinct from the gate-fired path, where it never is


class _FakeIndexWithWhere:
    def __init__(self):
        self.queries = []

    def query(self, text, n_results=5, where=None):
        self.queries.append(where)
        return [
            {
                "id": "Abomasnow-stats",
                "text": "context from narrowed query",
                "metadata": {"pokemon": "Abomasnow", "chunk_type": "stats"},
                "distance": 0.3,
            }
        ]


def test_ask_response_narrows_retrieval_when_a_known_pokemon_is_named():
    index = _FakeIndexWithWhere()
    answerer = _FakeAnswerer(response_text="an answer")
    records = [{"name": "Abomasnow"}]

    ask_response(index, answerer, "Does Abomasnow learn Attract?", records=records, items=[])

    assert index.queries == [{"pokemon": "Abomasnow"}]


def test_ask_response_async_narrows_retrieval_when_a_known_pokemon_is_named():
    index = _FakeIndexWithWhere()
    answerer = _FakeAnswerer(response_text="an answer")
    records = [{"name": "Abomasnow"}]

    asyncio.run(ask_response_async(
        index, answerer, "Does Abomasnow learn Attract?", records=records, items=[]
    ))

    assert index.queries == [{"pokemon": "Abomasnow"}]


def test_format_ask_response_includes_a_sources_line_when_sources_are_present():
    result = {"answer": "Gyarados has 95 base HP.", "sources": [{"name": "Gyarados", "chunk_type": "stats"}]}

    formatted = format_ask_response(result)

    assert formatted == "Gyarados has 95 base HP.\n\nSources: Gyarados (stats)"


def test_format_ask_response_joins_multiple_sources():
    result = {
        "answer": "answer text",
        "sources": [
            {"name": "Gyarados", "chunk_type": "stats"},
            {"name": "Life Orb", "chunk_type": "item"},
        ],
    }

    formatted = format_ask_response(result)

    assert formatted == "answer text\n\nSources: Gyarados (stats), Life Orb (item)"


def test_format_ask_response_omits_the_sources_line_when_there_are_none():
    result = {"answer": "I don't have solid information on that.", "sources": []}

    formatted = format_ask_response(result)

    assert formatted == "I don't have solid information on that."
