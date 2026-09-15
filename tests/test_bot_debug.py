from bot.commands.debug import format_debug_last


def test_format_debug_last_reports_plainly_when_nothing_logged():
    formatted = format_debug_last(None)

    assert formatted == "No /ask calls logged yet."


def test_format_debug_last_renders_a_full_row():
    row = {
        "timestamp": "2026-09-14T12:00:00+00:00",
        "question": "How bulky is Gyarados?",
        "answer": "Gyarados has 95 base HP.",
        "sources": [{"name": "Gyarados", "chunk_type": "stats"}],
        "retrieved_chunks": [{"id": "Gyarados-stats", "distance": 0.4}],
        "best_distance": 0.4,
        "gate_fired": False,
        "degraded": False,
        "latency_ms": 900,
    }

    formatted = format_debug_last(row)

    assert "How bulky is Gyarados?" in formatted
    assert "Gyarados has 95 base HP." in formatted
    assert "Gyarados (stats)" in formatted
    assert "Gyarados-stats (distance 0.4000)" in formatted
    assert "0.4000" in formatted
    assert "False" in formatted
    assert "900" in formatted


def test_format_debug_last_shows_none_for_empty_sources_and_chunks():
    row = {
        "timestamp": "2026-09-14T12:00:00+00:00",
        "question": "What is the capital of France?",
        "answer": "I don't have solid information on that.",
        "sources": [],
        "retrieved_chunks": [],
        "best_distance": None,
        "gate_fired": True,
        "degraded": False,
        "latency_ms": 50,
    }

    formatted = format_debug_last(row)

    assert "**Sources:** none" in formatted
    assert "**Retrieved chunks:** none" in formatted
    assert "**Best distance:** none" in formatted
    assert "**Gate fired:** True" in formatted


def test_format_debug_last_truncates_a_very_long_question_and_answer():
    row = {
        "timestamp": "2026-09-14T12:00:00+00:00",
        "question": "Q" * 5000,
        "answer": "A" * 5000,
        "sources": [{"name": "Gyarados", "chunk_type": "stats"}],
        "retrieved_chunks": [{"id": "Gyarados-stats", "distance": 0.4}],
        "best_distance": 0.4,
        "gate_fired": False,
        "degraded": False,
        "latency_ms": 900,
    }

    formatted = format_debug_last(row)

    assert "Q" * 5000 not in formatted
    assert "A" * 5000 not in formatted
    assert "…[truncated]" in formatted
    # Truncation marker should appear twice: once for the question, once
    # for the answer.
    assert formatted.count("…[truncated]") == 2


def test_format_debug_last_stays_under_discord_embed_description_limit_worst_case():
    # Worst case: a long question, a long answer (the answerer can produce
    # up to ~1024 tokens, which can exceed 4096 characters on its own), and
    # several retrieved chunks/sources.
    row = {
        "timestamp": "2026-09-14T12:00:00+00:00",
        "question": "Q" * 6000,
        "answer": "A" * 6000,
        "sources": [{"name": f"Pokemon{i}", "chunk_type": "stats"} for i in range(10)],
        "retrieved_chunks": [{"id": f"Pokemon{i}-stats", "distance": 0.1 * i} for i in range(10)],
        "best_distance": 0.1,
        "gate_fired": False,
        "degraded": False,
        "latency_ms": 900,
    }

    formatted = format_debug_last(row)

    assert len(formatted) <= 4096
