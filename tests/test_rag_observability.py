from rag.observability import get_last_ask_log, log_ask


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
