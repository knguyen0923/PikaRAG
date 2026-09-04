from pathlib import Path

from pipeline.fetch_pokeapi import fetch_all
from pipeline.build_records import build_records, write_processed_records


def run_refresh(source_dir, raw_dir, output_path, session=None) -> dict:
    source_dir = Path(source_dir)
    raw_dir = Path(raw_dir)
    output_path = Path(output_path)

    import json
    with open(source_dir / "legal_pokemon_m-b.json") as f:
        legal_names = json.load(f)["legal_pokemon"]

    summary = fetch_all(legal_names, cache_dir=raw_dir, session=session)

    records = build_records(source_dir, raw_dir)
    write_processed_records(records, output_path)
    summary["records_written"] = len(records)
    return summary


if __name__ == "__main__":
    result = run_refresh(
        source_dir=Path("data/source"),
        raw_dir=Path("data/raw"),
        output_path=Path("data/processed/pokemon_records.json"),
    )
    print(result)
