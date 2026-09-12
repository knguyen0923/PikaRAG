"""Estimated cumulative Anthropic spend tracking for /ask.

This is an early-warning estimate computed from token usage, not a
substitute for Anthropic Console's own billing ledger and spend-limit
notifications -- use both.
"""

import json
import os
import threading
from pathlib import Path

HAIKU_INPUT_PRICE_PER_MTOK = 1.00
HAIKU_OUTPUT_PRICE_PER_MTOK = 5.00

DEFAULT_STATE_PATH = Path(__file__).resolve().parent.parent / "data" / "state" / "spend_tracker.json"
DEFAULT_SPEND_CAP_USD = 5.0

_lock = threading.Lock()


def _load_state(state_path: Path) -> dict:
    if not state_path.exists():
        return {"total_usd": 0.0, "warned": False}
    with open(state_path) as f:
        return json.load(f)


def _save_state(state_path: Path, state: dict) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    with open(state_path, "w") as f:
        json.dump(state, f)


def record_usage(
    input_tokens: int,
    output_tokens: int,
    state_path: Path = DEFAULT_STATE_PATH,
    spend_cap_usd: float = None,
) -> bool:
    """Record one API call's token usage against the running total.

    Returns True the first time cumulative estimated spend crosses
    (spend_cap_usd - 1.0); False otherwise, including on every call after
    the first crossing. spend_cap_usd defaults to the ANTHROPIC_SPEND_CAP_USD
    env var (falling back to DEFAULT_SPEND_CAP_USD) when not passed.
    """
    if spend_cap_usd is None:
        spend_cap_usd = float(os.environ.get("ANTHROPIC_SPEND_CAP_USD", DEFAULT_SPEND_CAP_USD))
    threshold = spend_cap_usd - 1.0

    cost = (
        input_tokens * HAIKU_INPUT_PRICE_PER_MTOK + output_tokens * HAIKU_OUTPUT_PRICE_PER_MTOK
    ) / 1_000_000

    with _lock:
        state = _load_state(state_path)
        state["total_usd"] = state.get("total_usd", 0.0) + cost
        just_crossed = False
        if not state.get("warned", False) and state["total_usd"] >= threshold:
            state["warned"] = True
            just_crossed = True
        _save_state(state_path, state)

    return just_crossed
