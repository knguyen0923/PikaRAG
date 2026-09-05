import json
from pathlib import Path

from pipeline.build_records import find_legal_pokemon_file
from pipeline.fetch_pikalytics import fetch_all_usage


def run_pikalytics_refresh(source_dir, cache_dir, output_path, session=None) -> dict:
    source_dir = Path(source_dir)
    output_path = Path(output_path)

    with open(find_legal_pokemon_file(source_dir)) as f:
        legal_data = json.load(f)
    legal_names = legal_data["legal_pokemon"]

    result = fetch_all_usage(legal_names, cache_dir=cache_dir, session=session)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(result["usage_by_species"], f, indent=2)

    result["species_with_data"] = len(result["usage_by_species"])
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
