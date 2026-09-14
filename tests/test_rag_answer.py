import requests

from rag.answer import OFFLINE_MESSAGE, OllamaAnswerer


class _FakeOllamaResponse:
    def __init__(self, json_data, status_code=200):
        self._json_data = json_data
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error")

    def json(self):
        return self._json_data


class _FakeOllamaClient:
    def __init__(self, response_json=None, exception=None, status_code=200):
        self._response_json = response_json
        self._exception = exception
        self._status_code = status_code
        self.calls = []

    def post(self, url, json=None, timeout=None):
        self.calls.append({"url": url, "json": json, "timeout": timeout})
        if self._exception:
            raise self._exception
        return _FakeOllamaResponse(self._response_json, status_code=self._status_code)


def test_ollama_answer_returns_the_models_response_text():
    client = _FakeOllamaClient(response_json={"message": {"content": "Gyarados has 95 base HP."}})
    answerer = OllamaAnswerer(host="100.1.2.3:11434", client=client)

    result = answerer.answer("How bulky is Gyarados?", "Gyarados base HP: 95.")

    assert result == "Gyarados has 95 base HP."


def test_ollama_answer_sends_the_question_and_context_to_the_client():
    client = _FakeOllamaClient(response_json={"message": {"content": "anything"}})
    answerer = OllamaAnswerer(host="100.1.2.3:11434", client=client)

    answerer.answer("How bulky is Gyarados?", "Gyarados base HP: 95.")

    sent = client.calls[0]["json"]
    user_message = sent["messages"][-1]["content"]
    assert "How bulky is Gyarados?" in user_message
    assert "Gyarados base HP: 95." in user_message


def test_ollama_answer_uses_the_grounding_system_prompt():
    client = _FakeOllamaClient(response_json={"message": {"content": "anything"}})
    answerer = OllamaAnswerer(host="100.1.2.3:11434", client=client)

    answerer.answer("How bulky is Gyarados?", "Gyarados base HP: 95.")

    sent = client.calls[0]["json"]
    system_message = sent["messages"][0]["content"]
    assert "only" in system_message.lower()
    assert "context" in system_message.lower()


def test_ollama_answer_posts_to_the_configured_host_and_model():
    client = _FakeOllamaClient(response_json={"message": {"content": "anything"}})
    answerer = OllamaAnswerer(host="100.1.2.3:11434", model="phi3:mini", client=client)

    answerer.answer("question", "context")

    call = client.calls[0]
    assert call["url"] == "http://100.1.2.3:11434/api/chat"
    assert call["json"]["model"] == "phi3:mini"


def test_ollama_answer_returns_offline_message_on_connection_error():
    client = _FakeOllamaClient(exception=requests.exceptions.ConnectionError("refused"))
    answerer = OllamaAnswerer(host="100.1.2.3:11434", client=client)

    result = answerer.answer("question", "context")

    assert result == OFFLINE_MESSAGE


def test_ollama_answer_returns_offline_message_on_timeout():
    client = _FakeOllamaClient(exception=requests.exceptions.Timeout("slow"))
    answerer = OllamaAnswerer(host="100.1.2.3:11434", client=client)

    result = answerer.answer("question", "context")

    assert result == OFFLINE_MESSAGE


def test_ollama_answer_returns_offline_message_on_http_error_status():
    client = _FakeOllamaClient(response_json={}, status_code=500)
    answerer = OllamaAnswerer(host="100.1.2.3:11434", client=client)

    result = answerer.answer("question", "context")

    assert result == OFFLINE_MESSAGE


def test_ollama_answer_returns_offline_message_on_malformed_response():
    client = _FakeOllamaClient(response_json={"unexpected": "shape"})
    answerer = OllamaAnswerer(host="100.1.2.3:11434", client=client)

    result = answerer.answer("question", "context")

    assert result == OFFLINE_MESSAGE
