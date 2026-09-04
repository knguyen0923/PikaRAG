import json
from pathlib import Path


def _load_json(path: Path):
    with open(path) as f:
        return json.load(f)


def _simple_cache_filename(display_name: str) -> str:
    slug = display_name.lower()
    slug = slug.replace("[", "").replace("]", "")
    slug = slug.replace(" ", "_")
    return f"{slug}.json"


def build_records(source_dir: Path, raw_dir: Path) -> list:
    source_dir = Path(source_dir)
    raw_dir = Path(raw_dir)

    legal_data = _load_json(source_dir / "legal_pokemon_m-b.json")
    moves_data = _load_json(source_dir / "vgc_moves.json")
    abilities_data = _load_json(source_dir / "vgc_abilities.json")

    regulation = legal_data["regulation"]
    types_by_name = {p["name"]: p["types"] for p in moves_data["pokemon"]}
    move_names_by_slug = {}
    for move in moves_data["moves"]:
        slug = move["name"].lower().replace(" ", "-").replace("'", "")
        move_names_by_slug[slug] = move["name"]
    ability_names_by_slug = {}
    for ability in abilities_data:
        slug = ability["name"].lower().replace(" ", "-").replace("'", "")
        ability_names_by_slug[slug] = ability["name"]

    records = []
    for name in legal_data["legal_pokemon"]:
        raw_path = raw_dir / _simple_cache_filename(name)
        if not raw_path.exists():
            continue
        raw = _load_json(raw_path)

        learnset = sorted({
            move_names_by_slug[slug]
            for slug in raw.get("learnset", [])
            if slug in move_names_by_slug
        })
        abilities = sorted({
            ability_names_by_slug[slug]
            for slug in raw.get("abilities", [])
            if slug in ability_names_by_slug
        })

        records.append({
            "name": name,
            "types": types_by_name.get(name, []),
            "base_stats": raw.get("base_stats", {}),
            "abilities": abilities,
            "learnset": learnset,
            "legal_in": [regulation],
        })

    return records


def write_processed_records(records: list, output_path: Path) -> None:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(records, f, indent=2)
