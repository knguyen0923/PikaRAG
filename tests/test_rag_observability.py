from rag.observability import get_last_ask_log, get_log_summary, log_ask, prune_old_logs


def test_log_ask_writes_a_row_and_get_last_ask_log_reads_it_back(tmp_path):
    db_path = str(tmp_path / "observability.db")

    log_ask(
        timestamp="2026-09-14T12:00:00+00:00",
        question="Does Gyarados learn Waterfall?",
        retrieved_chunks=[{"id": "Gyarados-moveset", "distance": 0.4}],
        sources=[{"name": "Gyarados", "chunk_type": "moveset"}],
        best_distance=0.4,
        gate_fired=False,
        answer="Yes, Gyarados learns Waterfall.",
        degraded=False,
        latency_ms=1234,
        db_path=db_path,
    )

    row = get_last_ask_log(db_path=db_path)

    assert row["timestamp"] == "2026-09-14T12:00:00+00:00"
    assert row["question"] == "Does Gyarados learn Waterfall?"
    assert row["retrieved_chunks"] == [{"id": "Gyarados-moveset", "distance": 0.4}]
    assert row["sources"] == [{"name": "Gyarados", "chunk_type": "moveset"}]
    assert row["best_distance"] == 0.4
    assert row["gate_fired"] is False
    assert row["answer"] == "Yes, Gyarados learns Waterfall."
    assert row["degraded"] is False
    assert row["latency_ms"] == 1234


def test_get_last_ask_log_returns_none_when_the_table_is_empty(tmp_path):
    db_path = str(tmp_path / "observability.db")

    row = get_last_ask_log(db_path=db_path)

    assert row is None


def test_get_last_ask_log_returns_the_most_recently_logged_row(tmp_path):
    db_path = str(tmp_path / "observability.db")

    log_ask(
        timestamp="2026-09-14T12:00:00+00:00", question="First question?",
        retrieved_chunks=[], sources=[], best_distance=None, gate_fired=True,
        answer="I don't have solid information on that.", degraded=False, latency_ms=50,
        db_path=db_path,
    )
    log_ask(
        timestamp="2026-09-14T12:05:00+00:00", question="Second question?",
        retrieved_chunks=[{"id": "Absol-stats", "distance": 0.3}],
        sources=[{"name": "Absol", "chunk_type": "stats"}], best_distance=0.3, gate_fired=False,
        answer="Second answer.", degraded=False, latency_ms=900,
        db_path=db_path,
    )

    row = get_last_ask_log(db_path=db_path)

    assert row["question"] == "Second question?"


def test_log_ask_creates_the_table_if_it_does_not_exist_yet(tmp_path):
    db_path = str(tmp_path / "brand_new.db")

    log_ask(
        timestamp="2026-09-14T12:00:00+00:00", question="Q?", retrieved_chunks=[], sources=[],
        best_distance=None, gate_fired=True, answer="A", degraded=False, latency_ms=10,
        db_path=db_path,
    )

    row = get_last_ask_log(db_path=db_path)
    assert row is not None


def _log(db_path, timestamp, question="Q?", **overrides):
    kwargs = dict(
        timestamp=timestamp, question=question, retrieved_chunks=[], sources=[],
        best_distance=None, gate_fired=False, answer="A", degraded=False, latency_ms=10,
        db_path=db_path,
    )
    kwargs.update(overrides)
    log_ask(**kwargs)


def test_prune_old_logs_deletes_rows_older_than_the_cutoff_and_keeps_the_rest(tmp_path):
    db_path = str(tmp_path / "observability.db")
    _log(db_path, "2026-01-01T00:00:00+00:00", question="Old")
    _log(db_path, "2026-09-01T00:00:00+00:00", question="Recent")

    deleted = prune_old_logs(cutoff_timestamp="2026-06-01T00:00:00+00:00", db_path=db_path)

    assert deleted == 1
    row = get_last_ask_log(db_path=db_path)
    assert row["question"] == "Recent"


def test_prune_old_logs_returns_zero_when_nothing_is_old_enough(tmp_path):
    db_path = str(tmp_path / "observability.db")
    _log(db_path, "2026-09-01T00:00:00+00:00")

    deleted = prune_old_logs(cutoff_timestamp="2026-01-01T00:00:00+00:00", db_path=db_path)

    assert deleted == 0
    assert get_last_ask_log(db_path=db_path) is not None


def test_get_log_summary_returns_zeros_when_the_table_is_empty(tmp_path):
    db_path = str(tmp_path / "observability.db")

    summary = get_log_summary(db_path=db_path)

    assert summary == {
        "total_asks": 0,
        "gate_fired_count": 0,
        "degraded_count": 0,
        "avg_latency_ms": 0.0,
    }


def test_get_log_summary_aggregates_counts_and_average_latency(tmp_path):
    db_path = str(tmp_path / "observability.db")
    _log(db_path, "2026-09-01T00:00:00+00:00", gate_fired=True, degraded=False, latency_ms=100)
    _log(db_path, "2026-09-01T00:01:00+00:00", gate_fired=False, degraded=True, latency_ms=300)
    _log(db_path, "2026-09-01T00:02:00+00:00", gate_fired=False, degraded=False, latency_ms=200)

    summary = get_log_summary(db_path=db_path)

    assert summary["total_asks"] == 3
    assert summary["gate_fired_count"] == 1
    assert summary["degraded_count"] == 1
    assert summary["avg_latency_ms"] == 200.0
