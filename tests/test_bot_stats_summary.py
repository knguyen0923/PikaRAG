from bot.commands.stats_summary import format_stats_summary


def test_format_stats_summary_reports_plainly_when_nothing_logged():
    summary = {"total_asks": 0, "gate_fired_count": 0, "degraded_count": 0, "avg_latency_ms": 0.0}

    formatted = format_stats_summary(summary)

    assert formatted == "No /ask calls logged yet."


def test_format_stats_summary_reports_counts_rates_and_average_latency():
    summary = {"total_asks": 4, "gate_fired_count": 1, "degraded_count": 2, "avg_latency_ms": 725.5}

    formatted = format_stats_summary(summary)

    assert "**Total /ask calls:** 4" in formatted
    assert "1 (25.0%)" in formatted
    assert "2 (50.0%)" in formatted
    assert "726ms" in formatted
