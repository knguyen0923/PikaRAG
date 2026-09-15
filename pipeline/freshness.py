import json
import time
from pathlib import Path
from typing import Optional

POKEAPI_TIMESTAMP_PATH = "data/processed/.last_refresh_pokeapi.json"
PIKALYTICS_TIMESTAMP_PATH = "data/processed/.last_refresh_pikalytics.json"

# Loosely double each job's own cadence (deploy/systemd/*.timer: weekly for
# PokeAPI, monthly for Pikalytics) -- using the shorter threshold for both
# jobs would false-positive "stale" on the Pikalytics job every single
# month even when it's running exactly on schedule.
POKEAPI_FRESHNESS_THRESHOLD_SECONDS = 14 * 24 * 60 * 60
PIKALYTICS_FRESHNESS_THRESHOLD_SECONDS = 60 * 24 * 60 * 60


def record_successful_refresh(timestamp_path, now: float) -> None:
    timestamp_path = Path(timestamp_path)
    timestamp_path.parent.mkdir(parents=True, exist_ok=True)
    with open(timestamp_path, "w") as f:
        json.dump({"last_refresh": now}, f)


def check_freshness(timestamp_path, now: float, max_age_seconds: float) -> Optional[str]:
    """Returns a warning string if the last recorded refresh is older than
    max_age_seconds, or None if fresh. A missing timestamp file (no refresh
    has ever succeeded, or a fresh setup) is treated as "unknown," not
    "stale" -- returns None rather than false-positiving."""
    timestamp_path = Path(timestamp_path)
    if not timestamp_path.exists():
        return None
    with open(timestamp_path) as f:
        data = json.load(f)
    age_seconds = now - data["last_refresh"]
    if age_seconds > max_age_seconds:
        age_days = age_seconds / 86400
        threshold_days = max_age_seconds / 86400
        return (
            f"last successful refresh at {timestamp_path} was {age_days:.1f} days "
            f"ago (threshold: {threshold_days:.0f} days)"
        )
    return None


def check_all_freshness(now_func=time.time) -> list:
    """Checks both refresh jobs' own timestamp files against their own
    thresholds. Returns a list of warning strings (empty if both are fresh
    or unknown)."""
    now = now_func()
    warnings = [
        check_freshness(POKEAPI_TIMESTAMP_PATH, now, POKEAPI_FRESHNESS_THRESHOLD_SECONDS),
        check_freshness(PIKALYTICS_TIMESTAMP_PATH, now, PIKALYTICS_FRESHNESS_THRESHOLD_SECONDS),
    ]
    return [w for w in warnings if w is not None]
