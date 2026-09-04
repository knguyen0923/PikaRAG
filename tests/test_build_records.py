import json
from pipeline.build_records import build_records, write_processed_records

def _write_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f)

def _make_fixture_source(tmp_path):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    _write_json(source_dir / "legal_pokemon_m-b.json", {
        "regulation": "M-B",
        "count": 1,
        "legal_pokemon": ["Abomasnow"],
    })
    _write_json(source_dir / "vgc_moves.json", {
        "meta": {"regulation": "M-B"},
        "pokemon": [{"name": "Abomasnow", "types": ["Grass", "Ice"]}],
        "moves": [
            {"name": "Ice Punch", "type": "Ice", "category": "Physical", "power": 75, "accuracy": 100, "pp": 15, "effect": None},
            {"name": "Wood Hammer", "type": "Grass", "category": "Physical", "power": 120, "accuracy": 100, "pp": 15, "effect": None},
        ],
    })
    _write_json(source_dir / "vgc_abilities.json", [
        {"name": "Snow Warning", "description": "Summons hail/snow."},
        {"name": "Soundproof", "description": "Immune to sound moves."},
    ])
    _write_json(source_dir / "vgc_items.json", [])
    return source_dir

def _make_fixture_raw(tmp_path):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    _write_json(raw_dir / "abomasnow.json", {
        "base_stats": {"hp": 90, "attack": 92, "defense": 75, "sp_attack": 92, "sp_defense": 85, "speed": 60},
        "learnset": ["ice-punch", "wood-hammer", "solar-beam"],
        "abilities": ["snow-warning", "soundproof"],
    })
    return raw_dir

def test_build_records_merges_all_sources(tmp_path):
    source_dir = _make_fixture_source(tmp_path)
    raw_dir = _make_fixture_raw(tmp_path)

    records = build_records(source_dir, raw_dir)

    assert len(records) == 1
    record = records[0]
    assert record["name"] == "Abomasnow"
    assert record["types"] == ["Grass", "Ice"]
    assert record["base_stats"]["hp"] == 90
    assert record["legal_in"] == ["M-B"]
    assert set(record["learnset"]) == {"Ice Punch", "Wood Hammer"}
    assert set(record["abilities"]) == {"Snow Warning", "Soundproof"}

def test_build_records_skips_pokemon_missing_raw_cache(tmp_path):
    source_dir = _make_fixture_source(tmp_path)
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    records = build_records(source_dir, raw_dir)
    assert records == []

def test_write_processed_records_creates_valid_json(tmp_path):
    records = [{"name": "Abomasnow", "types": ["Grass", "Ice"]}]
    out_path = tmp_path / "processed" / "pokemon_records.json"
    write_processed_records(records, out_path)
    with open(out_path) as f:
        loaded = json.load(f)
    assert loaded == records

def test_build_records_filters_abilities_against_vgc_abilities(tmp_path):
    """Regression test: abilities not in vgc_abilities.json should be dropped."""
    source_dir = _make_fixture_source(tmp_path)
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    # Include an unlisted ability alongside the legal ones
    _write_json(raw_dir / "abomasnow.json", {
        "base_stats": {"hp": 90, "attack": 92, "defense": 75, "sp_attack": 92, "sp_defense": 85, "speed": 60},
        "learnset": ["ice-punch", "wood-hammer", "solar-beam"],
        "abilities": ["snow-warning", "soundproof", "some-unlisted-ability"],
    })

    records = build_records(source_dir, raw_dir)

    assert len(records) == 1
    record = records[0]
    # Only the two listed abilities should be included; some-unlisted-ability must be dropped
    assert set(record["abilities"]) == {"Snow Warning", "Soundproof"}
    assert "some-unlisted-ability" not in record["abilities"]
