import requests

SYSTEM_PROMPT = (
    "You are a Pokemon VGC doubles assistant. Answer the user's question "
    "using only the information in the provided context. If the context "
    "does not contain the answer, say you don't know rather than guessing."
)

OFFLINE_MESSAGE = "The knowledge assistant is offline right now -- try again later."

# Timeout for the /llmstatus health-check request (OllamaAnswerer.check_health).
# Deliberately much shorter than the 30s default used for a real answer --
# this is a liveness probe, not an inference call, so a slow response IS
# the "down" signal, not something worth waiting out.
HEALTH_CHECK_TIMEOUT = 3.0


class OllamaAnswerer:
    """Generates grounded answers via a local Ollama server, reached over
    a private Tailscale network link.

    Accepts an injected `client` (anything with `.post(url, json=..., timeout=...)`
    and `.get(url, timeout=...)` methods matching `requests`' interface) so
    callers can swap in a fake for testing without a live Ollama server.
    """

    def __init__(self, host: str, model: str = "llama3.2:3b", client=None, timeout: float = 30.0):
        self._client = client if client is not None else requests
        self._host = host
        self._model = model
        self._timeout = timeout

    @property
    def model(self) -> str:
        return self._model

    def answer(self, question: str, context_block: str) -> str:
        try:
            response = self._client.post(
                f"http://{self._host}/api/chat",
                json={
                    "model": self._model,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": f"Context:\n{context_block}\n\nQuestion: {question}"},
                    ],
                    "stream": False,
                    "options": {"num_predict": 1024},
                },
                timeout=self._timeout,
            )
            response.raise_for_status()
            return response.json()["message"]["content"]
        except (requests.RequestException, KeyError, TypeError) as e:
            print(f"OllamaAnswerer call failed: {e!r}")
            return OFFLINE_MESSAGE

    def check_health(self) -> dict:
        """Cheap liveness probe for /llmstatus: hits Ollama's own /api/tags
        endpoint (lists locally-available models) instead of running real
        inference, on a short timeout. Returns {"up": bool, "models": list}
        -- models is empty when down, since there's nothing to report."""
        try:
            response = self._client.get(f"http://{self._host}/api/tags", timeout=HEALTH_CHECK_TIMEOUT)
            response.raise_for_status()
            models = [entry["name"] for entry in response.json()["models"]]
            return {"up": True, "models": models}
        except (requests.RequestException, KeyError, TypeError) as e:
            print(f"OllamaAnswerer health check failed: {e!r}")
            return {"up": False, "models": []}
