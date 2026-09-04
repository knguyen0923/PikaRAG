import json
import sys
from pathlib import Path

from pipeline.fetch_pokeapi import fetch_all
from pipeline.build_records import (
    build_records,
    find_legal_pokemon_file,
    write_processed_records,
)


def run_refresh(source_dir, raw_dir, output_path, session=None) -> dict:
    source_dir = Path(source_dir)
    raw_dir = Path(raw_dir)
    output_path = Path(output_path)

    with open(find_legal_pokemon_file(source_dir)) as f:
        legal_data = json.load(f)
    legal_names = legal_data["legal_pokemon"]
    # The source file declares its own count; trust that as the expected total
    # so a truncated or partially-parsed legal_pokemon list is caught too.
    expected_count = legal_data.get("count", len(legal_names))

    summary = fetch_all(legal_names, cache_dir=raw_dir, session=session)

    records = build_records(source_dir, raw_dir)
    write_processed_records(records, output_path)
    summary["records_written"] = len(records)
    summary["expected_count"] = expected_count
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

    print(
        f"fetched={result['fetched']} cached={result['cached']} "
        f"failed={len(failed)} records_written={written} expected_count={expected}"
    )
    if failed:
        print(f"\nFAILED to fetch {len(failed)} Pokemon:")
        for name in failed:
            print(f"  - {name}")
    if written != expected:
        print(
            f"\nERROR: wrote {written} records but the source file declares "
            f"{expected} legal Pokemon ({expected - written} missing)."
        )
        sys.exit(1)
    print("\nOK: all legal Pokemon resolved and written.")
