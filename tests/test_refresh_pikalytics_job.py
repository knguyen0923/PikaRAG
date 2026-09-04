import json
from unittest.mock import MagicMock

from pipeline.refresh_pikalytics_job import run_pikalytics_refresh

_SAMPLE_MARKDOWN = """\
## Common Moves
- **Dragon Claw**: 89.4%
- **Earthquake**: 80.7%

## Common Abilities
- **Rough Skin**: 98.5%

## Common Items
- **Life Orb**: 51.5%
"""


def test_run_pikalytics_refresh_finds_legal_file_and_writes_output(tmp_path):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "legal_pokemon_m-b.json").write_text(json.dumps({
        "regulation": "M-B", "count": 1, "legal_pokemon": ["Garchomp"],
    }))
    cache_dir = tmp_path / "raw_pikalytics"
    output_path = tmp_path / "processed" / "pikalytics_usage.json"

    session = MagicMock()
    session.get.return_value = MagicMock(status_code=200, text=_SAMPLE_MARKDOWN)

    result = run_pikalytics_refresh(source_dir, cache_dir, output_path, session=session)

    assert result["fetched"] == 1
    assert result["species_with_data"] == 1
    written = json.loads(output_path.read_text())
    assert written["Garchomp"]["moves"][0]["name"] == "Dragon Claw"


def test_run_pikalytics_refresh_counts_species_with_no_data(tmp_path):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "legal_pokemon_m-b.json").write_text(json.dumps({
        "regulation": "M-B", "count": 1, "legal_pokemon": ["Nonexistamon"],
    }))
    cache_dir = tmp_path / "raw_pikalytics"
    output_path = tmp_path / "processed" / "pikalytics_usage.json"

    session = MagicMock()
    session.get.return_value = MagicMock(status_code=404, text="Pokemon not found")

    result = run_pikalytics_refresh(source_dir, cache_dir, output_path, session=session)

    assert result["species_with_data"] == 0
    written = json.loads(output_path.read_text())
    assert written == {}
