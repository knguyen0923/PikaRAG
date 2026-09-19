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

    def get(self, url, timeout=None):
        self.calls.append({"url": url, "timeout": timeout})
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


def test_ollama_check_health_reports_up_and_lists_loaded_models():
    client = _FakeOllamaClient(
        response_json={"models": [{"name": "llama3.2:3b"}, {"name": "nomic-embed-text"}]}
    )
    answerer = OllamaAnswerer(host="100.1.2.3:11434", client=client)

    result = answerer.check_health()

    assert result == {"up": True, "models": ["llama3.2:3b", "nomic-embed-text"]}


def test_ollama_check_health_hits_the_tags_endpoint_with_a_short_timeout():
    client = _FakeOllamaClient(response_json={"models": []})
    answerer = OllamaAnswerer(host="100.1.2.3:11434", client=client)

    answerer.check_health()

    call = client.calls[0]
    assert call["url"] == "http://100.1.2.3:11434/api/tags"
    assert call["timeout"] == 3.0


def test_ollama_check_health_reports_down_on_connection_error():
    client = _FakeOllamaClient(exception=requests.exceptions.ConnectionError("refused"))
    answerer = OllamaAnswerer(host="100.1.2.3:11434", client=client)

    result = answerer.check_health()

    assert result == {"up": False, "models": []}


def test_ollama_check_health_reports_down_on_timeout():
    client = _FakeOllamaClient(exception=requests.exceptions.Timeout("slow"))
    answerer = OllamaAnswerer(host="100.1.2.3:11434", client=client)

    result = answerer.check_health()

    assert result == {"up": False, "models": []}


def test_ollama_check_health_reports_down_on_malformed_response():
    client = _FakeOllamaClient(response_json={"unexpected": "shape"})
    answerer = OllamaAnswerer(host="100.1.2.3:11434", client=client)

    result = answerer.check_health()

    assert result == {"up": False, "models": []}


def test_ollama_answerer_exposes_its_configured_model():
    answerer = OllamaAnswerer(host="100.1.2.3:11434", model="phi3:mini")

    assert answerer.model == "phi3:mini"


def test_answer_bare_returns_the_models_response_text():
    client = _FakeOllamaClient(response_json={"message": {"content": "Gyarados has 95 base HP."}})
    answerer = OllamaAnswerer(host="100.1.2.3:11434", client=client)

    result = answerer.answer_bare("How bulky is Gyarados?")

    assert result == "Gyarados has 95 base HP."


def test_answer_bare_sends_only_the_question_no_context():
    client = _FakeOllamaClient(response_json={"message": {"content": "anything"}})
    answerer = OllamaAnswerer(host="100.1.2.3:11434", client=client)

    answerer.answer_bare("How bulky is Gyarados?")

    sent = client.calls[0]["json"]
    user_message = sent["messages"][-1]["content"]
    assert user_message == "How bulky is Gyarados?"


def test_answer_bare_does_not_use_the_grounding_caveat_system_prompt():
    client = _FakeOllamaClient(response_json={"message": {"content": "anything"}})
    answerer = OllamaAnswerer(host="100.1.2.3:11434", client=client)

    answerer.answer_bare("How bulky is Gyarados?")

    sent = client.calls[0]["json"]
    system_message = sent["messages"][0]["content"]
    # answer()'s grounding prompt tells the model to say "I don't know" when
    # context doesn't have the answer -- answer_bare has no context block at
    # all, so that caveat would make a fine-tuned model refuse to answer from
    # its own learned knowledge. Confirm it's a different, caveat-free prompt.
    assert "only the information in the provided context" not in system_message.lower()


def test_answer_bare_posts_to_the_configured_host_and_model():
    client = _FakeOllamaClient(response_json={"message": {"content": "anything"}})
    answerer = OllamaAnswerer(host="100.1.2.3:11434", model="pikarag-finetuned", client=client)

    answerer.answer_bare("question")

    call = client.calls[0]
    assert call["url"] == "http://100.1.2.3:11434/api/chat"
    assert call["json"]["model"] == "pikarag-finetuned"


def test_answer_bare_returns_offline_message_on_connection_error():
    client = _FakeOllamaClient(exception=requests.exceptions.ConnectionError("refused"))
    answerer = OllamaAnswerer(host="100.1.2.3:11434", client=client)

    result = answerer.answer_bare("question")

    assert result == OFFLINE_MESSAGE
