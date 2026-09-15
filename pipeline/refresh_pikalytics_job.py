import json
import os
import sys
import time
from pathlib import Path

from pipeline.build_records import find_legal_pokemon_file
from pipeline.fetch_pikalytics import fetch_all_usage
from pipeline.freshness import (
    PIKALYTICS_TIMESTAMP_PATH,
    check_all_freshness,
    record_successful_refresh,
)
from pipeline.validate import validate_usage


def run_pikalytics_refresh(
    source_dir, cache_dir, output_path, session=None,
    timestamp_path=PIKALYTICS_TIMESTAMP_PATH, now_func=time.time,
) -> dict:
    source_dir = Path(source_dir)
    output_path = Path(output_path)

    with open(find_legal_pokemon_file(source_dir)) as f:
        legal_data = json.load(f)
    legal_names = legal_data["legal_pokemon"]

    result = fetch_all_usage(legal_names, cache_dir=cache_dir, session=session)
    usage_by_species = result["usage_by_species"]
    result["species_with_data"] = len(usage_by_species)

    problems = validate_usage(usage_by_species, known_species=set(legal_names))
    result["validation_problems"] = problems

    if problems:
        result["swapped"] = False
        return result

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = output_path.with_name(output_path.name + ".tmp")
    with open(temp_path, "w") as f:
        json.dump(usage_by_species, f, indent=2)
    os.replace(temp_path, output_path)
    result["swapped"] = True
    record_successful_refresh(timestamp_path, now_func())
    return result


if __name__ == "__main__":
    summary = run_pikalytics_refresh(
        source_dir=Path("data/source"),
        cache_dir=Path("data/raw_pikalytics"),
        output_path=Path("data/processed/pikalytics_usage.json"),
    )
    print(
        f"fetched={summary['fetched']} cached={summary['cached']} "
        f"failed={len(summary['failed'])} species_with_data={summary['species_with_data']}"
    )
    if summary["failed"]:
        print(f"\nFAILED to fetch usage for {len(summary['failed'])} Pokemon:")
        for name in summary["failed"]:
            print(f"  - {name}")

    # Mirror refresh_job.py's coverage guard: a scheduled run that silently
    # writes a degenerate result is worse than one that fails loudly. Real
    # HTTP/network failures are an unambiguous problem. Zero species with
    # any usage data despite processing a full legal list is *also* a
    # failure signature (most likely a stale PIKALYTICS_FORMAT_CODE making
    # every page 404, which looks identical to "no usage data" per-species)
    # rather than a legitimate reg where nothing gets played.
    stale_format_code = summary["species_with_data"] == 0 and not summary["failed"]
    if stale_format_code:
        print(
            "\nERROR: every species came back with no usage data and nothing "
            "outright failed -- this looks like a stale PIKALYTICS_FORMAT_CODE "
            "rather than a real 0%-usage regulation."
        )

    for warning in check_all_freshness():
        print(f"\nWARNING: {warning}")

    if summary["validation_problems"]:
        print("\nERROR: validation failed, live data left unchanged:")
        for problem in summary["validation_problems"]:
            print(f"  - {problem}")

    if summary["failed"] or stale_format_code or summary["validation_problems"]:
        sys.exit(1)
