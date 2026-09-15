import json

from pipeline.freshness import (
    PIKALYTICS_FRESHNESS_THRESHOLD_SECONDS,
    POKEAPI_FRESHNESS_THRESHOLD_SECONDS,
    check_all_freshness,
    check_freshness,
    record_successful_refresh,
)


def test_record_successful_refresh_writes_the_timestamp(tmp_path):
    timestamp_path = tmp_path / "last_refresh.json"

    record_successful_refresh(timestamp_path, now=1000.0)

    written = json.loads(timestamp_path.read_text())
    assert written == {"last_refresh": 1000.0}


def test_check_freshness_returns_none_when_the_file_is_missing(tmp_path):
    timestamp_path = tmp_path / "does_not_exist.json"

    result = check_freshness(timestamp_path, now=1000.0, max_age_seconds=100.0)

    assert result is None


def test_check_freshness_returns_none_when_within_the_threshold(tmp_path):
    timestamp_path = tmp_path / "last_refresh.json"
    record_successful_refresh(timestamp_path, now=1000.0)

    result = check_freshness(timestamp_path, now=1050.0, max_age_seconds=100.0)

    assert result is None


def test_check_freshness_returns_a_warning_when_past_the_threshold(tmp_path):
    timestamp_path = tmp_path / "last_refresh.json"
    record_successful_refresh(timestamp_path, now=1000.0)

    result = check_freshness(timestamp_path, now=1000.0 + 200.0, max_age_seconds=100.0)

    assert result is not None
    assert str(timestamp_path) in result


def test_check_freshness_uses_the_pokeapi_threshold_of_14_days(tmp_path):
    timestamp_path = tmp_path / "last_refresh_pokeapi.json"
    now = 10_000_000.0
    record_successful_refresh(timestamp_path, now=now)

    just_under = now + POKEAPI_FRESHNESS_THRESHOLD_SECONDS - 1
    just_over = now + POKEAPI_FRESHNESS_THRESHOLD_SECONDS + 1

    assert check_freshness(timestamp_path, just_under, POKEAPI_FRESHNESS_THRESHOLD_SECONDS) is None
    assert check_freshness(timestamp_path, just_over, POKEAPI_FRESHNESS_THRESHOLD_SECONDS) is not None


def test_check_freshness_uses_the_pikalytics_threshold_of_60_days(tmp_path):
    timestamp_path = tmp_path / "last_refresh_pikalytics.json"
    now = 10_000_000.0
    record_successful_refresh(timestamp_path, now=now)

    just_under = now + PIKALYTICS_FRESHNESS_THRESHOLD_SECONDS - 1
    just_over = now + PIKALYTICS_FRESHNESS_THRESHOLD_SECONDS + 1

    assert check_freshness(timestamp_path, just_under, PIKALYTICS_FRESHNESS_THRESHOLD_SECONDS) is None
    assert check_freshness(timestamp_path, just_over, PIKALYTICS_FRESHNESS_THRESHOLD_SECONDS) is not None


def test_check_all_freshness_returns_no_warnings_when_no_timestamps_exist_yet(monkeypatch, tmp_path):
    monkeypatch.setattr("pipeline.freshness.POKEAPI_TIMESTAMP_PATH", str(tmp_path / "pokeapi.json"))
    monkeypatch.setattr("pipeline.freshness.PIKALYTICS_TIMESTAMP_PATH", str(tmp_path / "pikalytics.json"))

    warnings = check_all_freshness(now_func=lambda: 1000.0)

    assert warnings == []


def test_check_all_freshness_reports_a_stale_job_by_name(monkeypatch, tmp_path):
    pokeapi_path = tmp_path / "pokeapi.json"
    pikalytics_path = tmp_path / "pikalytics.json"
    monkeypatch.setattr("pipeline.freshness.POKEAPI_TIMESTAMP_PATH", str(pokeapi_path))
    monkeypatch.setattr("pipeline.freshness.PIKALYTICS_TIMESTAMP_PATH", str(pikalytics_path))
    record_successful_refresh(pokeapi_path, now=0.0)
    record_successful_refresh(pikalytics_path, now=0.0)

    # Only the PokeAPI job's threshold (14 days) has elapsed, not the
    # Pikalytics job's (60 days) -- only one warning should appear.
    stale_for_pokeapi_only = POKEAPI_FRESHNESS_THRESHOLD_SECONDS + 1

    warnings = check_all_freshness(now_func=lambda: stale_for_pokeapi_only)

    assert len(warnings) == 1
    assert str(pokeapi_path) in warnings[0]
