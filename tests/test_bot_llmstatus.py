from bot.commands.llmstatus import format_llmstatus


def test_format_llmstatus_reports_online_with_loaded_models():
    formatted = format_llmstatus(
        up=True,
        models=["llama3.2:3b", "nomic-embed-text"],
        configured_model="llama3.2:3b",
        breaker_state="closed",
    )

    assert "Online" in formatted
    assert "llama3.2:3b (loaded)" in formatted
    assert "nomic-embed-text" in formatted
    assert "closed" in formatted


def test_format_llmstatus_flags_when_the_configured_model_is_not_in_the_loaded_list():
    formatted = format_llmstatus(
        up=True, models=["some-other-model"], configured_model="llama3.2:3b", breaker_state="closed"
    )

    assert "NOT in the loaded models list" in formatted


def test_format_llmstatus_reports_offline():
    formatted = format_llmstatus(up=False, models=[], configured_model="llama3.2:3b", breaker_state="open")

    assert "Offline" in formatted
    assert "llama3.2:3b" in formatted
    assert "open" in formatted


def test_format_llmstatus_reports_the_breaker_state_for_all_three_states():
    for state in ("closed", "open", "half_open"):
        formatted = format_llmstatus(
            up=True, models=["llama3.2:3b"], configured_model="llama3.2:3b", breaker_state=state
        )
        assert state in formatted
