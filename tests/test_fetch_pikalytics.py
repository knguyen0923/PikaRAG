import json
import pytest
import requests
from unittest.mock import MagicMock

from pipeline.cache_utils import simple_cache_filename
from pipeline.fetch_pikalytics import (
    resolve_pikalytics_slug,
    parse_usage_markdown,
    fetch_pikalytics_usage,
    fetch_all_usage,
    PikalyticsFetchError,
)


def test_resolve_plain_name():
    assert resolve_pikalytics_slug("Garchomp") == "Garchomp"


def test_resolve_prefix_form_species():
    assert resolve_pikalytics_slug("Wash Rotom") == "Rotom-Wash"


def test_resolve_bracket_regional_form():
    assert resolve_pikalytics_slug("Ninetales [Alolan Form]") == "Ninetales-Alola"


def test_resolve_mega():
    assert resolve_pikalytics_slug("Mega Abomasnow") == "Abomasnow-Mega"


def test_resolve_mega_x_y():
    assert resolve_pikalytics_slug("Mega Charizard X") == "Charizard-Mega-X"


_SAMPLE_MARKDOWN = """\
# Garchomp - Best Builds, Moves and Teams in Pokemon Champions VGC 2026 Reg M-B S3 Ranked Battle Data

> Find the best Garchomp builds...

## Best Garchomp Quick Info

| Property | Value |
|----------|-------|
| **Format** | Pokemon Champions VGC 2026 Reg M-B S3 |

## Common Moves
- **Dragon Claw**: 89.4%
- **Rock Slide**: 82.0%
- **Earthquake**: 80.7%
- **Protect**: 70.2%
- **Stomping Tantrum**: 40.3%
- **Poison Jab**: 18.3%
- **Rock Tomb**: 8.0%
- **Scale Shot**: 3.1%
- **Swords Dance**: 2.5%
- **Dragon Tail**: 2.0%

## Common Abilities
- **Rough Skin**: 98.5%
- **Sand Veil**: 1.5%

## Common Items
- **Life Orb**: 51.5%
- **Sitrus Berry**: 13.6%
- **Choice Scarf**: 12.7%
- **Roseli Berry**: 10.8%
- **Soft Sand**: 3.6%
- **White Herb**: 1.3%
- **Focus Sash**: 1.1%
- **Haban Berry**: 1.1%
- **Expert Belt**: 0.9%
- **Lum Berry**: 0.9%

## Common Teammates
- **Whimsicott**: undefined%
- **Charizard**: undefined%

## Featured Teams with Garchomp

### Team 1 by shaikhvgc786
*Record: 13-2*

**Pokemon**: Raichu-Mega-Y, Farigiraf, Mawile-Mega, Garchomp, Vivillon, Torkoal
"""


def test_parses_top_6_moves_sorted_by_usage():
    result = parse_usage_markdown(_SAMPLE_MARKDOWN)

    assert result["moves"] == [
        {"name": "Dragon Claw", "usage_pct": 89.4},
        {"name": "Rock Slide", "usage_pct": 82.0},
        {"name": "Earthquake", "usage_pct": 80.7},
        {"name": "Protect", "usage_pct": 70.2},
        {"name": "Stomping Tantrum", "usage_pct": 40.3},
        {"name": "Poison Jab", "usage_pct": 18.3},
    ]


def test_parses_top_6_items_sorted_by_usage():
    result = parse_usage_markdown(_SAMPLE_MARKDOWN)

    assert result["items"][0] == {"name": "Life Orb", "usage_pct": 51.5}
    assert len(result["items"]) == 6


def test_parses_all_abilities_uncapped():
    result = parse_usage_markdown(_SAMPLE_MARKDOWN)

    assert result["abilities"] == [
        {"name": "Rough Skin", "usage_pct": 98.5},
        {"name": "Sand Veil", "usage_pct": 1.5},
    ]


def test_ignores_teammates_section_and_undefined_percentages():
    result = parse_usage_markdown(_SAMPLE_MARKDOWN)

    all_names = [e["name"] for e in result["moves"] + result["items"] + result["abilities"]]
    assert "Whimsicott" not in all_names
    assert "evs" not in result
    assert "teammates" not in result


def test_missing_section_returns_empty_list():
    markdown_without_items = "## Common Moves\n- **Tackle**: 100.0%\n\n## Common Abilities\n- **Levitate**: 100.0%\n"

    result = parse_usage_markdown(markdown_without_items)

    assert result["items"] == []
    assert result["moves"] == [{"name": "Tackle", "usage_pct": 100.0}]


def _mock_session(status_code, text=None):
    session = MagicMock()
    response = MagicMock(status_code=status_code, text=text)
    session.get.return_value = response
    return session


def test_fetch_pikalytics_usage_parses_a_successful_response():
    session = _mock_session(200, text=_SAMPLE_MARKDOWN)

    result = fetch_pikalytics_usage("Garchomp", session=session)

    assert result["moves"][0]["name"] == "Dragon Claw"
    session.get.assert_called_once_with(
        "https://www.pikalytics.com/ai/pokedex/battledataregmbs3/Garchomp"
    )


def test_fetch_pikalytics_usage_returns_none_on_404():
    session = _mock_session(404, text="Pokemon not found")

    result = fetch_pikalytics_usage("Nonexistamon", session=session)

    assert result is None


def test_fetch_pikalytics_usage_raises_on_other_error_status():
    session = _mock_session(500)

    with pytest.raises(PikalyticsFetchError):
        fetch_pikalytics_usage("Garchomp", session=session)


def test_fetch_pikalytics_usage_wraps_network_exception():
    session = MagicMock()
    session.get.side_effect = requests.exceptions.ConnectionError("refused")

    with pytest.raises(PikalyticsFetchError):
        fetch_pikalytics_usage("Garchomp", session=session)


def test_fetch_all_usage_writes_cache_and_builds_usage_dict(tmp_path):
    session = _mock_session(200, text=_SAMPLE_MARKDOWN)

    result = fetch_all_usage(["Garchomp"], cache_dir=tmp_path, session=session, delay_seconds=0)

    assert result["fetched"] == 1
    assert result["cached"] == 0
    assert result["failed"] == []
    assert result["usage_by_species"]["Garchomp"]["moves"][0]["name"] == "Dragon Claw"
    assert (tmp_path / simple_cache_filename("Garchomp")).exists()


def test_fetch_all_usage_skips_already_cached_files(tmp_path):
    cache_file = tmp_path / simple_cache_filename("Garchomp")
    cache_file.write_text(json.dumps({"moves": [], "items": [], "abilities": []}))
    session = _mock_session(200, text=_SAMPLE_MARKDOWN)

    result = fetch_all_usage(["Garchomp"], cache_dir=tmp_path, session=session, delay_seconds=0)

    assert result["cached"] == 1
    assert result["fetched"] == 0
    session.get.assert_not_called()
    assert result["usage_by_species"]["Garchomp"] == {"moves": [], "items": [], "abilities": []}


def test_fetch_all_usage_caches_none_for_a_species_with_no_data(tmp_path):
    session = _mock_session(404, text="Pokemon not found")

    result = fetch_all_usage(["Nonexistamon"], cache_dir=tmp_path, session=session, delay_seconds=0)

    assert result["fetched"] == 1
    assert "Nonexistamon" not in result["usage_by_species"]
    cache_file = tmp_path / simple_cache_filename("Nonexistamon")
    assert cache_file.exists()
    assert json.loads(cache_file.read_text()) is None


def test_fetch_all_usage_does_not_refetch_a_cached_none(tmp_path):
    cache_file = tmp_path / simple_cache_filename("Nonexistamon")
    cache_file.write_text("null")
    session = _mock_session(200, text=_SAMPLE_MARKDOWN)

    result = fetch_all_usage(["Nonexistamon"], cache_dir=tmp_path, session=session, delay_seconds=0)

    assert result["cached"] == 1
    assert "Nonexistamon" not in result["usage_by_species"]
    session.get.assert_not_called()


def test_fetch_all_usage_continues_after_one_failure(tmp_path):
    session = MagicMock()
    ok_response = MagicMock(status_code=200, text=_SAMPLE_MARKDOWN)
    session.get.side_effect = [requests.exceptions.ConnectionError("refused"), ok_response]

    result = fetch_all_usage(["Broken", "Garchomp"], cache_dir=tmp_path, session=session, delay_seconds=0)

    assert result["failed"] == ["Broken"]
    assert "Garchomp" in result["usage_by_species"]
