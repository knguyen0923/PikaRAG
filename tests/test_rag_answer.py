from rag.answer import HaikuAnswerer


class _FakeContentBlock:
    def __init__(self, text):
        self.text = text


class _FakeUsage:
    def __init__(self, input_tokens=10, output_tokens=10):
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


class _FakeMessage:
    def __init__(self, text, usage=None):
        self.content = [_FakeContentBlock(text)]
        self.usage = usage or _FakeUsage()


class _FakeMessages:
    def __init__(self, response_text, usage=None):
        self._response_text = response_text
        self._usage = usage
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return _FakeMessage(self._response_text, usage=self._usage)


class _FakeClient:
    def __init__(self, response_text="Gyarados has 95 base HP.", usage=None):
        self.messages = _FakeMessages(response_text, usage=usage)


def test_answer_returns_the_clients_response_text(tmp_path):
    client = _FakeClient(response_text="Gyarados has 95 base HP.")
    answerer = HaikuAnswerer(client=client, spend_state_path=tmp_path / "spend.json")

    result = answerer.answer("How bulky is Gyarados?", "Gyarados base HP: 95.")

    assert result == "Gyarados has 95 base HP."


def test_answer_sends_the_question_and_context_to_the_client(tmp_path):
    client = _FakeClient()
    answerer = HaikuAnswerer(client=client, spend_state_path=tmp_path / "spend.json")

    answerer.answer("How bulky is Gyarados?", "Gyarados base HP: 95.")

    sent = client.messages.calls[0]
    user_message = sent["messages"][0]["content"]
    assert "How bulky is Gyarados?" in user_message
    assert "Gyarados base HP: 95." in user_message


def test_answer_uses_the_grounding_system_prompt(tmp_path):
    client = _FakeClient()
    answerer = HaikuAnswerer(client=client, spend_state_path=tmp_path / "spend.json")

    answerer.answer("How bulky is Gyarados?", "Gyarados base HP: 95.")

    sent = client.messages.calls[0]
    assert "only" in sent["system"].lower()
    assert "context" in sent["system"].lower()


def test_answer_appends_warning_once_spend_crosses_threshold(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_SPEND_CAP_USD", "5.0")
    # 4M input tokens at Haiku's $1/MTok pricing = $4.00, exactly the
    # (cap - $1) threshold, so this single call crosses it outright.
    big_usage = _FakeUsage(input_tokens=4_000_000, output_tokens=0)
    client = _FakeClient(usage=big_usage)
    answerer = HaikuAnswerer(client=client, spend_state_path=tmp_path / "spend.json")

    result = answerer.answer("How bulky is Gyarados?", "Gyarados base HP: 95.")

    assert "Approaching the Anthropic spend cap" in result
