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


def run_refresh(
    source_dir, raw_dir, output_path, session=None,
    timestamp_path=POKEAPI_TIMESTAMP_PATH, now_func=time.time,
) -> dict:
    source_dir = Path(source_dir)
    raw_dir = Path(raw_dir)
    output_path = Path(output_path)

    with open(find_legal_pokemon_file(source_dir)) as f:
        legal_data = json.load(f)
    legal_names = legal_data["legal_pokemon"]
    regulation = legal_data["regulation"]
    # The source file declares its own count; trust that as the expected total
    # so a truncated or partially-parsed legal_pokemon list is caught too.
    expected_count = legal_data.get("count", len(legal_names))

    summary = fetch_all(legal_names, cache_dir=raw_dir, session=session)

    records = build_records(source_dir, raw_dir)
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
    os.replace(temp_path, output_path)
    summary["swapped"] = True
    record_successful_refresh(timestamp_path, now_func())
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

    if problems:
        print("\nERROR: validation failed, live data left unchanged:")
        for problem in problems:
            print(f"  - {problem}")
        sys.exit(1)
    print("\nOK: all legal Pokemon resolved, validated, and written.")
