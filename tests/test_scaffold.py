import json
from pathlib import Path

SOURCE_DIR = Path(__file__).resolve().parent.parent / "data" / "source"

def test_all_four_source_files_present_and_valid_json():
    expected = {
        "legal_pokemon_m-b.json",
        "vgc_abilities.json",
        "vgc_items.json",
        "vgc_moves.json",
    }
    actual = {p.name for p in SOURCE_DIR.glob("*.json")}
    assert expected == actual

    for name in expected:
        with open(SOURCE_DIR / name) as f:
            data = json.load(f)
        assert data

def test_legal_pokemon_file_has_regulation_tag():
    with open(SOURCE_DIR / "legal_pokemon_m-b.json") as f:
        data = json.load(f)
    assert data["regulation"] == "M-B"
    assert len(data["legal_pokemon"]) == data["count"]
