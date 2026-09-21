from bot.conversation import (
    ConversationHistory,
    should_respond,
    should_respond_to_mention,
    strip_bot_mention,
)


def test_conversation_history_returns_empty_list_for_an_unseen_channel():
    history = ConversationHistory()

    assert history.get(12345) == []


def test_conversation_history_returns_appended_turns_in_order():
    history = ConversationHistory()

    history.append(1, "user", "hello")
    history.append(1, "assistant", "hi there")

    assert history.get(1) == [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi there"},
    ]


def test_conversation_history_trims_to_the_cap():
    history = ConversationHistory(cap=4)

    for i in range(6):
        history.append(1, "user", f"message {i}")

    result = history.get(1)
    assert len(result) == 4
    # oldest entries dropped, newest kept
    assert result[0]["content"] == "message 2"
    assert result[-1]["content"] == "message 5"


def test_conversation_history_isolates_channels():
    history = ConversationHistory()

    history.append(1, "user", "channel one message")
    history.append(2, "user", "channel two message")

    assert history.get(1) == [{"role": "user", "content": "channel one message"}]
    assert history.get(2) == [{"role": "user", "content": "channel two message"}]


class _FakeAuthor:
    def __init__(self, bot: bool):
        self.bot = bot


class _FakeChannel:
    def __init__(self, channel_id: int):
        self.id = channel_id


class _FakeMessage:
    def __init__(self, channel_id: int, is_bot: bool, content: str = "hello there", mentions=None):
        self.channel = _FakeChannel(channel_id)
        self.author = _FakeAuthor(bot=is_bot)
        self.content = content
        self.mentions = mentions or []


class _FakeUser:
    def __init__(self, user_id: int):
        self.id = user_id


def test_should_respond_true_for_a_human_author_in_a_designated_channel():
    message = _FakeMessage(channel_id=100, is_bot=False)

    assert should_respond(message, conversation_channel_ids={100, 200}) is True


def test_should_respond_false_for_a_channel_not_in_the_allowlist():
    message = _FakeMessage(channel_id=999, is_bot=False)

    assert should_respond(message, conversation_channel_ids={100, 200}) is False


def test_should_respond_false_for_a_bot_author_even_in_a_designated_channel():
    message = _FakeMessage(channel_id=100, is_bot=True)

    assert should_respond(message, conversation_channel_ids={100, 200}) is False


def test_should_respond_false_when_the_allowlist_is_empty():
    message = _FakeMessage(channel_id=100, is_bot=False)

    assert should_respond(message, conversation_channel_ids=set()) is False


def test_should_respond_false_for_a_message_with_no_text_content():
    message = _FakeMessage(channel_id=100, is_bot=False, content="   ")

    assert should_respond(message, conversation_channel_ids={100, 200}) is False


def test_strip_bot_mention_removes_plain_and_nickname_tokens():
    assert strip_bot_mention("<@42> what's the best tera type?", 42) == "what's the best tera type?"
    assert strip_bot_mention("<@!42> what's the best tera type?", 42) == "what's the best tera type?"


def test_should_respond_to_mention_true_when_mentioned_in_a_designated_channel():
    bot_user = _FakeUser(42)
    message = _FakeMessage(channel_id=100, is_bot=False, content="<@42> hello", mentions=[bot_user])

    assert should_respond_to_mention(message, mention_channel_ids={100}, bot_user=bot_user) is True


def test_should_respond_to_mention_false_for_a_channel_not_in_the_allowlist():
    bot_user = _FakeUser(42)
    message = _FakeMessage(channel_id=999, is_bot=False, content="<@42> hello", mentions=[bot_user])

    assert should_respond_to_mention(message, mention_channel_ids={100}, bot_user=bot_user) is False


def test_should_respond_to_mention_false_when_the_bot_is_not_actually_mentioned():
    bot_user = _FakeUser(42)
    message = _FakeMessage(channel_id=100, is_bot=False, content="hello", mentions=[])

    assert should_respond_to_mention(message, mention_channel_ids={100}, bot_user=bot_user) is False


def test_should_respond_to_mention_false_for_a_bot_author():
    bot_user = _FakeUser(42)
    message = _FakeMessage(channel_id=100, is_bot=True, content="<@42> hello", mentions=[bot_user])

    assert should_respond_to_mention(message, mention_channel_ids={100}, bot_user=bot_user) is False


def test_should_respond_to_mention_false_when_nothing_is_left_after_stripping_the_mention():
    bot_user = _FakeUser(42)
    message = _FakeMessage(channel_id=100, is_bot=False, content="<@42>", mentions=[bot_user])

    assert should_respond_to_mention(message, mention_channel_ids={100}, bot_user=bot_user) is False
