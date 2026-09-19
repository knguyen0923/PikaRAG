"""Deletes ask_log rows older than a retention window from data/observability.db.

Manual/cron script, not wired into the bot or CI -- run it periodically on
whichever machine hosts the live bot (same deployment pattern as
pipeline/refresh_job.py), so the observability DB doesn't grow unbounded.
"""
import argparse
from datetime import datetime, timedelta, timezone

from rag.observability import DEFAULT_DB_PATH, prune_old_logs

_DEFAULT_RETENTION_DAYS = 90


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--days",
        type=int,
        default=_DEFAULT_RETENTION_DAYS,
        help=f"Delete ask_log rows older than this many days (default: {_DEFAULT_RETENTION_DAYS}).",
    )
    args = parser.parse_args()

    cutoff = (datetime.now(timezone.utc) - timedelta(days=args.days)).isoformat()
    deleted = prune_old_logs(cutoff_timestamp=cutoff, db_path=DEFAULT_DB_PATH)
    print(f"Deleted {deleted} ask_log row(s) older than {args.days} days (before {cutoff}).")


if __name__ == "__main__":
    main()
