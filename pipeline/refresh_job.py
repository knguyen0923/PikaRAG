import json
import os
import sys
import time
from pathlib import Path

from pipeline.fetch_pokeapi import fetch_all
from pipeline.build_records import (
    build_records,
    find_legal_pokemon_file,
    write_processed_records,
)
from pipeline.freshness import (
    POKEAPI_TIMESTAMP_PATH,
    check_all_freshness,
    record_successful_refresh,
)
from pipeline.validate import validate_legal_count, validate_records, validate_write_count

_SOURCE_LOAD_ERRORS = (FileNotFoundError, json.JSONDecodeError, KeyError)


def _empty_summary(problem: str) -> dict:
    return {
        "fetched": 0, "cached": 0, "failed": [],
        "records_written": 0, "expected_count": 0,
        "validation_problems": [problem], "swapped": False,
    }


def run_refresh(
    source_dir, raw_dir, output_path, session=None,
    timestamp_path=POKEAPI_TIMESTAMP_PATH, now_func=time.time,
) -> dict:
    source_dir = Path(source_dir)
    raw_dir = Path(raw_dir)
    output_path = Path(output_path)

    try:
        with open(find_legal_pokemon_file(source_dir)) as f:
            legal_data = json.load(f)
        legal_names = legal_data["legal_pokemon"]
        regulation = legal_data["regulation"]
        # The source file declares its own count; trust that as the expected
        # total so a truncated or partially-parsed legal_pokemon list is
        # caught too.
        expected_count = legal_data.get("count", len(legal_names))
    except _SOURCE_LOAD_ERRORS as e:
        return _empty_summary(f"Could not load legal-Pokemon source data: {e}")

    summary = fetch_all(legal_names, cache_dir=raw_dir, session=session)

    try:
        records = build_records(source_dir, raw_dir)
    except _SOURCE_LOAD_ERRORS as e:
        summary["records_written"] = 0
        summary["expected_count"] = expected_count
        summary["validation_problems"] = [f"Could not build records from source data: {e}"]
        summary["swapped"] = False
        return summary

    summary["records_written"] = len(records)
    summary["expected_count"] = expected_count

    problems = (
        validate_records(records)
        + validate_legal_count(regulation, expected_count)
        + validate_write_count(len(records), expected_count)
    )
    summary["validation_problems"] = problems

    if problems:
        summary["swapped"] = False
        return summary

    temp_path = output_path.with_name(output_path.name + ".tmp")
    write_processed_records(records, temp_path)
    try:
        os.replace(temp_path, output_path)
    except OSError as e:
        summary["swapped"] = False
        summary["validation_problems"] = [f"Could not write live data (filesystem error): {e}"]
        return summary
    summary["swapped"] = True

    try:
        record_successful_refresh(timestamp_path, now_func())
    except OSError as e:
        summary["freshness_write_failed"] = str(e)
    return summary


if __name__ == "__main__":
    result = run_refresh(
        source_dir=Path("data/source"),
        raw_dir=Path("data/raw"),
        output_path=Path("data/processed/pokemon_records.json"),
    )

    written = result["records_written"]
    expected = result["expected_count"]
    failed = result["failed"]
    problems = result["validation_problems"]

    print(
        f"fetched={result['fetched']} cached={result['cached']} "
        f"failed={len(failed)} records_written={written} expected_count={expected}"
    )
    if failed:
        print(f"\nFAILED to fetch {len(failed)} Pokemon:")
        for name in failed:
            print(f"  - {name}")

    for warning in check_all_freshness():
        print(f"\nWARNING: {warning}")

    if result.get("freshness_write_failed"):
        print(f"\nWARNING: could not record successful-refresh timestamp: {result['freshness_write_failed']}")

    if problems:
        print("\nERROR: validation failed, live data left unchanged:")
        for problem in problems:
            print(f"  - {problem}")
        sys.exit(1)
    print("\nOK: all legal Pokemon resolved, validated, and written.")
