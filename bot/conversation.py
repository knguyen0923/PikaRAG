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
    """True only if the message's channel is in the configured allowlist,
    the author isn't a bot (covers this bot's own messages and any other
    bot in the channel, preventing response loops), and the message has
    actual text (an attachment/sticker-only message has nothing to answer)."""
    if message.author.bot:
        return False
    if not message.content.strip():
        return False
    return message.channel.id in conversation_channel_ids


def strip_bot_mention(content: str, bot_user_id: int) -> str:
    """Remove the bot's own mention token (with or without the nickname
    '!' variant Discord sometimes sends) so the remainder is just the
    asked question."""
    for token in (f"<@{bot_user_id}>", f"<@!{bot_user_id}>"):
        content = content.replace(token, "")
    return content.strip()


def should_respond_to_mention(message, mention_channel_ids: Iterable[int], bot_user) -> bool:
    """True only if the channel opted into mention-triggered answers, the
    author isn't a bot, the bot was actually @mentioned (not just named in
    text), and there's a question left over once the mention is stripped."""
    if message.author.bot:
        return False
    if message.channel.id not in mention_channel_ids:
        return False
    if bot_user not in message.mentions:
        return False
    return bool(strip_bot_mention(message.content, bot_user.id))
