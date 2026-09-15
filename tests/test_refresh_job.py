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

def _fixture_source(tmp_path, legal_pokemon=None, count=None, filename="legal_pokemon_m-b.json"):
    legal_pokemon = legal_pokemon or ["Abomasnow"]
    count = len(legal_pokemon) if count is None else count
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    with open(source_dir / filename, "w") as f:
        json.dump({"regulation": "M-B", "count": count, "legal_pokemon": legal_pokemon}, f)
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
    assert summary["expected_count"] == 1


def test_run_refresh_leaves_the_live_file_unchanged_when_a_fetch_fails(tmp_path):
    # Two legal Pokemon, the second one 404s (and its species fallback 404s
    # too), so only one record can be built. Under validate-before-swap,
    # this shortfall is a hard failure -- the live file must not be
    # touched, not silently written with partial data.
    source_dir = _fixture_source(tmp_path, legal_pokemon=["Abomasnow", "Bogusmon"])
    raw_dir = tmp_path / "raw"
    output_path = tmp_path / "processed" / "pokemon_records.json"

    session = MagicMock()
    ok = MagicMock(status_code=200)
    ok.json.return_value = _SAMPLE_RESPONSE
    miss = MagicMock(status_code=404)
    session.get.side_effect = [ok, miss, miss]

    summary = run_refresh(source_dir, raw_dir, output_path, session=session)

    assert summary["failed"] == ["Bogusmon"]
    assert summary["expected_count"] == 2
    assert summary["records_written"] == 1
    assert summary["swapped"] is False
    assert summary["validation_problems"] != []
    assert not output_path.exists()


def test_run_refresh_finds_legal_file_by_glob_not_hardcoded_name(tmp_path):
    # A future regulation drops in a differently-named file; nothing else changes.
    source_dir = _fixture_source(tmp_path, filename="legal_pokemon_m-c.json")
    raw_dir = tmp_path / "raw"
    output_path = tmp_path / "processed" / "pokemon_records.json"

    session = MagicMock()
    response = MagicMock(status_code=200)
    response.json.return_value = _SAMPLE_RESPONSE
    session.get.return_value = response

    summary = run_refresh(source_dir, raw_dir, output_path, session=session)

    assert summary["records_written"] == 1
    assert summary["expected_count"] == 1


def test_run_refresh_swaps_and_records_a_timestamp_on_a_clean_run(tmp_path):
    source_dir = _fixture_source(tmp_path)
    raw_dir = tmp_path / "raw"
    output_path = tmp_path / "processed" / "pokemon_records.json"
    timestamp_path = tmp_path / "last_refresh_pokeapi.json"

    session = MagicMock()
    response = MagicMock(status_code=200)
    response.json.return_value = _SAMPLE_RESPONSE
    session.get.return_value = response

    summary = run_refresh(
        source_dir, raw_dir, output_path, session=session,
        timestamp_path=timestamp_path, now_func=lambda: 12345.0,
    )

    assert summary["swapped"] is True
    assert summary["validation_problems"] == []
    assert output_path.exists()
    recorded = json.loads(timestamp_path.read_text())
    assert recorded == {"last_refresh": 12345.0}
