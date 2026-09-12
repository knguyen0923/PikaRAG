import json

from rag import spend_tracker


def _read_state(path):
    with open(path) as f:
        return json.load(f)


def test_record_usage_persists_cost_across_calls(tmp_path):
    state_path = tmp_path / "spend.json"

    spend_tracker.record_usage(1_000_000, 0, state_path=state_path, spend_cap_usd=100.0)
    spend_tracker.record_usage(1_000_000, 0, state_path=state_path, spend_cap_usd=100.0)

    assert _read_state(state_path)["total_usd"] == 2.0


def test_record_usage_prices_input_and_output_tokens_separately(tmp_path):
    state_path = tmp_path / "spend.json"

    # 1M input tokens ($1.00) + 1M output tokens ($5.00) = $6.00
    spend_tracker.record_usage(1_000_000, 1_000_000, state_path=state_path, spend_cap_usd=100.0)

    assert _read_state(state_path)["total_usd"] == 6.0


def test_record_usage_returns_false_below_threshold(tmp_path):
    state_path = tmp_path / "spend.json"

    crossed = spend_tracker.record_usage(100, 100, state_path=state_path, spend_cap_usd=5.0)

    assert crossed is False


def test_record_usage_returns_true_once_crossing_threshold(tmp_path):
    state_path = tmp_path / "spend.json"
    # cap 5.0 -> threshold 4.0. 4_000_000 input tokens = $4.00 exactly.
    spend_tracker.record_usage(3_000_000, 0, state_path=state_path, spend_cap_usd=5.0)

    crossed = spend_tracker.record_usage(1_000_000, 0, state_path=state_path, spend_cap_usd=5.0)

    assert crossed is True


def test_record_usage_does_not_refire_after_first_warning(tmp_path):
    state_path = tmp_path / "spend.json"
    spend_tracker.record_usage(4_000_000, 0, state_path=state_path, spend_cap_usd=5.0)

    crossed_again = spend_tracker.record_usage(1_000_000, 0, state_path=state_path, spend_cap_usd=5.0)

    assert crossed_again is False


def test_record_usage_reads_spend_cap_from_env_when_not_passed(tmp_path, monkeypatch):
    state_path = tmp_path / "spend.json"
    monkeypatch.setenv("ANTHROPIC_SPEND_CAP_USD", "2.0")

    # threshold = 2.0 - 1.0 = 1.0. 1_000_000 input tokens = $1.00 exactly.
    crossed = spend_tracker.record_usage(1_000_000, 0, state_path=state_path)

    assert crossed is True
