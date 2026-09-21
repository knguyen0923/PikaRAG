from bot.conversation import ConversationHistory, should_respond


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
    def __init__(self, channel_id: int, is_bot: bool):
        self.channel = _FakeChannel(channel_id)
        self.author = _FakeAuthor(bot=is_bot)


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
