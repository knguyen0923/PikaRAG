import json
from unittest.mock import MagicMock
from pipeline.refresh_job import run_refresh

_SAMPLE_RESPONSE = {
    "stats": [
        {"base_stat": 90, "stat": {"name": "hp"}},
        {"base_stat": 92, "stat": {"name": "attack"}},
        {"base_stat": 75, "stat": {"name": "defense"}},
        {"base_stat": 92, "stat": {"name": "special-attack"}},
        {"base_stat": 85, "stat": {"name": "special-defense"}},
        {"base_stat": 60, "stat": {"name": "speed"}},
    ],
    "moves": [{"move": {"name": "ice-punch"}}],
    "abilities": [{"ability": {"name": "snow-warning"}}],
}

def _fixture_source(tmp_path):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    with open(source_dir / "legal_pokemon_m-b.json", "w") as f:
        json.dump({"regulation": "M-B", "count": 1, "legal_pokemon": ["Abomasnow"]}, f)
    with open(source_dir / "vgc_moves.json", "w") as f:
        json.dump({
            "meta": {"regulation": "M-B"},
            "pokemon": [{"name": "Abomasnow", "types": ["Grass", "Ice"]}],
            "moves": [{"name": "Ice Punch", "type": "Ice", "category": "Physical", "power": 75, "accuracy": 100, "pp": 15, "effect": None}],
        }, f)
    with open(source_dir / "vgc_abilities.json", "w") as f:
        json.dump([{"name": "Snow Warning", "description": "x"}], f)
    with open(source_dir / "vgc_items.json", "w") as f:
        json.dump([], f)
    return source_dir

def test_run_refresh_fetches_and_writes_records(tmp_path):
    source_dir = _fixture_source(tmp_path)
    raw_dir = tmp_path / "raw"
    output_path = tmp_path / "processed" / "pokemon_records.json"

    session = MagicMock()
    response = MagicMock(status_code=200)
    response.json.return_value = _SAMPLE_RESPONSE
    session.get.return_value = response

    summary = run_refresh(source_dir, raw_dir, output_path, session=session)

    assert summary["fetched"] == 1
    assert summary["failed"] == []
    assert summary["records_written"] == 1
    with open(output_path) as f:
        records = json.load(f)
    assert records[0]["name"] == "Abomasnow"
    assert records[0]["legal_in"] == ["M-B"]
