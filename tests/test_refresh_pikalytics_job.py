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

    result = run_pikalytics_refresh(
        source_dir, cache_dir, output_path, session=session,
        timestamp_path=tmp_path / "last_refresh_pikalytics.json",
    )

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

    result = run_pikalytics_refresh(
        source_dir, cache_dir, output_path, session=session,
        timestamp_path=tmp_path / "last_refresh_pikalytics.json",
    )

    assert result["species_with_data"] == 0
    written = json.loads(output_path.read_text())
    assert written == {}


def test_run_pikalytics_refresh_leaves_the_live_file_unchanged_on_an_unknown_species(tmp_path, monkeypatch):
    # The legal-Pokemon list only names Garchomp, but the fetched usage
    # data references a species outside that list -- a referential
    # integrity problem that should block the swap, same as a schema
    # problem on the PokeAPI side does. fetch_all_usage is driven by
    # legal_names, so to exercise the referential check we monkeypatch its
    # result directly rather than trying to make the real fetch return an
    # out-of-list species.
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "legal_pokemon_m-b.json").write_text(json.dumps({
        "regulation": "M-B", "count": 1, "legal_pokemon": ["Garchomp"],
    }))
    cache_dir = tmp_path / "raw_pikalytics"
    output_path = tmp_path / "processed" / "pikalytics_usage.json"
    output_path.parent.mkdir(parents=True)
    output_path.write_text('{"pre-existing": "data"}')

    session = MagicMock()
    monkeypatch.setattr(
        "pipeline.refresh_pikalytics_job.fetch_all_usage",
        lambda *a, **k: {
            "fetched": 1, "cached": 0, "failed": [],
            "usage_by_species": {"NotInLegalList": {"moves": [], "items": [], "abilities": []}},
        },
    )

    result = run_pikalytics_refresh(source_dir, cache_dir, output_path, session=session)

    assert result["swapped"] is False
    assert result["validation_problems"] != []
    assert output_path.read_text() == '{"pre-existing": "data"}'


def test_run_pikalytics_refresh_swaps_and_records_a_timestamp_on_a_clean_run(tmp_path):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "legal_pokemon_m-b.json").write_text(json.dumps({
        "regulation": "M-B", "count": 1, "legal_pokemon": ["Garchomp"],
    }))
    cache_dir = tmp_path / "raw_pikalytics"
    output_path = tmp_path / "processed" / "pikalytics_usage.json"
    timestamp_path = tmp_path / "last_refresh_pikalytics.json"

    session = MagicMock()
    session.get.return_value = MagicMock(status_code=200, text=_SAMPLE_MARKDOWN)

    result = run_pikalytics_refresh(
        source_dir, cache_dir, output_path, session=session,
        timestamp_path=timestamp_path, now_func=lambda: 54321.0,
    )

    assert result["swapped"] is True
    assert result["validation_problems"] == []
    recorded = json.loads(timestamp_path.read_text())
    assert recorded == {"last_refresh": 54321.0}
