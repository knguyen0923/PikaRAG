def format_stats_summary(summary: dict) -> str:
    """Render rag.observability.get_log_summary()'s result for the
    /stats-summary admin command."""
    total = summary["total_asks"]
    if total == 0:
        return "No /ask calls logged yet."

    gate_fired = summary["gate_fired_count"]
    degraded = summary["degraded_count"]
    gate_rate = gate_fired / total
    degraded_rate = degraded / total

    return (
        f"**Total /ask calls:** {total}\n"
        f"**Gate fired:** {gate_fired} ({gate_rate:.1%})\n"
        f"**Degraded (offline):** {degraded} ({degraded_rate:.1%})\n"
        f"**Average latency:** {summary['avg_latency_ms']:.0f}ms"
    )
