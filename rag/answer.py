import json
from typing import Optional

import requests

SYSTEM_PROMPT = (
    "You are a Pokemon VGC doubles assistant. Answer the user's question "
    "using only the information in the provided context. If the context "
    "does not contain the answer, say you don't know rather than guessing."
)

OFFLINE_MESSAGE = "The knowledge assistant is offline right now -- try again later."

BARE_SYSTEM_PROMPT = (
    "You are a Pokemon VGC doubles assistant. Answer the user's question "
    "directly and concisely, using what you know."
)

TOOLS_SYSTEM_PROMPT = (
    "You are a Pokemon VGC doubles assistant with access to tools: a "
    "deterministic damage calculator, stored-team lookup, and usage-rate "
    "stats. Use tools to gather facts before answering. Never compute "
    "damage yourself -- always call run_damage_calc for any damage "
    "question. Give a concise final answer once you have what you need."
)

# Returned by answer_with_tools when the model's tool call is malformed or
# hallucinated (unknown tool name, non-object arguments, or a dispatch
# failure from missing/invalid required fields) -- signals the caller
# (bot/agentic.py) to drop tool-calling and retry as a plain RAG answer.
# A fixed sentinel string, same pattern as OFFLINE_MESSAGE.
MALFORMED_TOOL_CALL_MESSAGE = "The assistant's tool call could not be understood -- falling back to a plain answer."

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

    def __init__(self, host: str, model: str = "qwen3.5:9b", client=None, timeout: float = 30.0):
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

    def answer_bare(self, question: str) -> str:
        """Like answer(), but sends only the question -- no context block,
        no grounding caveat in the system prompt. Used to benchmark a
        fine-tuned model's learned knowledge directly, without RAG
        retrieval layered on top (see
        docs/superpowers/specs/2026-09-17-finetune-vs-rag-design.md)."""
        try:
            response = self._client.post(
                f"http://{self._host}/api/chat",
                json={
                    "model": self._model,
                    "messages": [
                        {"role": "system", "content": BARE_SYSTEM_PROMPT},
                        {"role": "user", "content": question},
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

    def answer_with_tools(
        self, question: str, tools: list, tool_dispatch: dict, max_rounds: int = 4,
        history: Optional[list] = None,
    ) -> str:
        """Drives Ollama's native tool-calling loop: send the question +
        tool schemas, dispatch any tool call the model emits, append the
        result as a tool-role message, repeat up to max_rounds. On hitting
        the cap, forces one final non-tool call for a best-effort answer.

        history, if given, is a list of prior {"role", "content"} turns
        inserted between the system prompt and the new question -- used by
        conversational chat to carry short-term context across messages in
        the same channel.

        Returns MALFORMED_TOOL_CALL_MESSAGE (not an exception) if the model
        emits an unknown tool name, non-object arguments, or a tool call
        that fails to dispatch due to missing/invalid required fields --
        the caller is expected to check for this sentinel and degrade to a
        plain RAG answer. Returns OFFLINE_MESSAGE on any network/parsing
        failure talking to Ollama itself, same as answer()/answer_bare()."""
        messages = [{"role": "system", "content": TOOLS_SYSTEM_PROMPT}]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": question})

        for _ in range(max_rounds):
            try:
                response = self._client.post(
                    f"http://{self._host}/api/chat",
                    json={
                        "model": self._model,
                        "messages": messages,
                        "tools": tools,
                        "stream": False,
                        "options": {"num_predict": 1024},
                    },
                    timeout=self._timeout,
                )
                response.raise_for_status()
                message = response.json()["message"]
            except (requests.RequestException, KeyError, TypeError) as e:
                print(f"OllamaAnswerer call failed: {e!r}")
                return OFFLINE_MESSAGE

            tool_calls = message.get("tool_calls")
            if not tool_calls:
                return message.get("content", "")

            messages.append(message)
            for call in tool_calls:
                function = call.get("function") if isinstance(call, dict) else None
                if not isinstance(function, dict):
                    return MALFORMED_TOOL_CALL_MESSAGE

                name = function.get("name")
                arguments = function.get("arguments")
                if isinstance(arguments, str):
                    try:
                        arguments = json.loads(arguments)
                    except json.JSONDecodeError:
                        return MALFORMED_TOOL_CALL_MESSAGE

                if name not in tool_dispatch or not isinstance(arguments, dict):
                    return MALFORMED_TOOL_CALL_MESSAGE

                try:
                    result = tool_dispatch[name](arguments)
                except (KeyError, TypeError, ValueError):
                    return MALFORMED_TOOL_CALL_MESSAGE

                messages.append({"role": "tool", "content": str(result)})

        messages.append({
            "role": "user",
            "content": "Give your best final answer now, using the tool results above.",
        })
        try:
            response = self._client.post(
                f"http://{self._host}/api/chat",
                json={
                    "model": self._model,
                    "messages": messages,
                    "stream": False,
                    "options": {"num_predict": 1024},
                },
                timeout=self._timeout,
            )
            response.raise_for_status()
            return response.json()["message"].get("content", "")
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
