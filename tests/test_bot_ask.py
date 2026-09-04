import asyncio
import time

from bot.commands.ask import ask_response, ask_response_async


class _FakeIndex:
    def __init__(self, context_matches):
        self._matches = context_matches

    def query(self, text, n_results=5):
        return self._matches[:n_results]


class _FakeAnswerer:
    def __init__(self, response_text):
        self._response_text = response_text
        self.calls = []

    def answer(self, question, context_block):
        self.calls.append((question, context_block))
        return self._response_text


def test_ask_response_returns_the_answerers_response():
    index = _FakeIndex(context_matches=[{"text": "Gyarados base HP: 95.", "metadata": {}}])
    answerer = _FakeAnswerer(response_text="Gyarados has 95 base HP.")

    result = ask_response(index, answerer, "How bulky is Gyarados?")

    assert result == "Gyarados has 95 base HP."


def test_ask_response_passes_retrieved_context_to_the_answerer():
    index = _FakeIndex(context_matches=[{"text": "Gyarados base HP: 95.", "metadata": {}}])
    answerer = _FakeAnswerer(response_text="anything")

    ask_response(index, answerer, "How bulky is Gyarados?")

    question, context_block = answerer.calls[0]
    assert question == "How bulky is Gyarados?"
    assert "Gyarados base HP: 95." in context_block


def test_ask_response_async_returns_the_same_result_as_the_sync_version():
    index = _FakeIndex(context_matches=[{"text": "Gyarados base HP: 95.", "metadata": {}}])
    answerer = _FakeAnswerer(response_text="Gyarados has 95 base HP.")

    result = asyncio.run(ask_response_async(index, answerer, "How bulky is Gyarados?"))

    assert result == "Gyarados has 95 base HP."


def test_ask_response_async_does_not_block_the_event_loop():
    # A "slow" sync answerer standing in for a real blocking network call.
    # If ask_response_async ran it directly on the event loop instead of
    # offloading to a thread, the ticker below would be starved for the
    # whole 0.2s and record close to zero ticks.
    class _SlowAnswerer:
        def answer(self, question, context_block):
            time.sleep(0.2)
            return "answer"

    index = _FakeIndex(context_matches=[{"text": "x", "metadata": {}}])
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

    assert result == "answer"
    assert ticks >= 8


def test_ask_response_prepends_extra_context_when_given():
    index = _FakeIndex(context_matches=[{"text": "Gyarados base HP: 95.", "metadata": {}}])
    answerer = _FakeAnswerer(response_text="answer")

    ask_response(index, answerer, "How bulky is Gyarados?", extra_context="Your team: Gyarados")

    question, context_block = answerer.calls[0]
    assert context_block.startswith("Your team: Gyarados")
    assert "Gyarados base HP: 95." in context_block
