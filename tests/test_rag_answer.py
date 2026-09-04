from rag.answer import HaikuAnswerer


class _FakeContentBlock:
    def __init__(self, text):
        self.text = text


class _FakeMessage:
    def __init__(self, text):
        self.content = [_FakeContentBlock(text)]


class _FakeMessages:
    def __init__(self, response_text):
        self._response_text = response_text
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return _FakeMessage(self._response_text)


class _FakeClient:
    def __init__(self, response_text="Gyarados has 95 base HP."):
        self.messages = _FakeMessages(response_text)


def test_answer_returns_the_clients_response_text():
    client = _FakeClient(response_text="Gyarados has 95 base HP.")
    answerer = HaikuAnswerer(client=client)

    result = answerer.answer("How bulky is Gyarados?", "Gyarados base HP: 95.")

    assert result == "Gyarados has 95 base HP."


def test_answer_sends_the_question_and_context_to_the_client():
    client = _FakeClient()
    answerer = HaikuAnswerer(client=client)

    answerer.answer("How bulky is Gyarados?", "Gyarados base HP: 95.")

    sent = client.messages.calls[0]
    user_message = sent["messages"][0]["content"]
    assert "How bulky is Gyarados?" in user_message
    assert "Gyarados base HP: 95." in user_message


def test_answer_uses_the_grounding_system_prompt():
    client = _FakeClient()
    answerer = HaikuAnswerer(client=client)

    answerer.answer("How bulky is Gyarados?", "Gyarados base HP: 95.")

    sent = client.messages.calls[0]
    assert "only" in sent["system"].lower()
    assert "context" in sent["system"].lower()
