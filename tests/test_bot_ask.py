from bot.commands.ask import ask_response


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
