from collections import deque
from typing import Iterable

# 3 exchanges (user + assistant pairs) -- bounds both memory and the
# tool-calling prompt size. See docs/superpowers/specs/2026-09-21-conversational-chat-design.md.
HISTORY_CAP_MESSAGES = 6


class ConversationHistory:
    """Short-lived, in-memory rolling chat history per Discord channel.
    Not persisted -- a bot restart clears all context, which is
    acceptable for chat-style back-and-forth."""

    def __init__(self, cap: int = HISTORY_CAP_MESSAGES):
        self._cap = cap
        self._history: dict[int, deque] = {}

    def append(self, channel_id: int, role: str, content: str) -> None:
        buffer = self._history.setdefault(channel_id, deque(maxlen=self._cap))
        buffer.append({"role": role, "content": content})

    def get(self, channel_id: int) -> list[dict]:
        return list(self._history.get(channel_id, []))


def should_respond(message, conversation_channel_ids: Iterable[int]) -> bool:
    """True only if the message's channel is in the configured allowlist
    and the author isn't a bot (covers this bot's own messages and any
    other bot in the channel, preventing response loops)."""
    if message.author.bot:
        return False
    return message.channel.id in conversation_channel_ids
