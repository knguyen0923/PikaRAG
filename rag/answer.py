from rag import spend_tracker

DEFAULT_MODEL = "claude-haiku-4-5"

SYSTEM_PROMPT = (
    "You are a Pokemon VGC doubles assistant. Answer the user's question "
    "using only the information in the provided context. If the context "
    "does not contain the answer, say you don't know rather than guessing."
)


class HaikuAnswerer:
    """Generates grounded answers via Claude Haiku.

    Accepts an injected `client` (anything with `.messages.create(...)`,
    matching the anthropic SDK's interface) so callers can swap in a fake
    for testing without a live API key.
    """

    def __init__(self, client=None, model: str = DEFAULT_MODEL, spend_state_path=None):
        if client is None:
            import anthropic

            client = anthropic.Anthropic()
        self._client = client
        self._model = model
        self._spend_state_path = spend_state_path or spend_tracker.DEFAULT_STATE_PATH

    def answer(self, question: str, context_block: str) -> str:
        message = self._client.messages.create(
            model=self._model,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": f"Context:\n{context_block}\n\nQuestion: {question}",
                }
            ],
        )
        text = message.content[0].text
        crossed = spend_tracker.record_usage(
            message.usage.input_tokens, message.usage.output_tokens, state_path=self._spend_state_path
        )
        if crossed:
            text += "\n\n⚠️ Approaching the Anthropic spend cap (~$1 left)."
        return text
