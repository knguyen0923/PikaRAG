from bot.commands.pokemon_info import usage_response

_ABOMASNOW = {
    "name": "Abomasnow", "types": ["Grass", "Ice"],
    "base_stats": {"hp": 90, "attack": 92, "defense": 75, "sp_attack": 92, "sp_defense": 85, "speed": 60},
    "abilities": ["Snow Warning", "Soundproof"], "learnset": ["Blizzard", "Wood Hammer"], "legal_in": ["M-B"],
}
_RECORDS = [_ABOMASNOW]


def test_usage_response_not_found_suggests_close_matches():
    response = usage_response(_RECORDS, "Abomasno")

    assert "not found" in response.lower() or "no pokemon" in response.lower()


def test_usage_response_reports_no_usage_data_when_none_exists():
    response = usage_response(_RECORDS, "Abomasnow", usage={})

    assert "no usage data" in response.lower()


def test_usage_response_shows_items_abilities_and_moves():
    usage = {"Abomasnow": {
        "items": [{"name": "Focus Sash", "usage_pct": 40.0}],
        "abilities": [{"name": "Snow Warning", "usage_pct": 98.5}],
        "moves": [{"name": "Blizzard", "usage_pct": 91.2}, {"name": "Wood Hammer", "usage_pct": 84.0}],
    }}

    response = usage_response(_RECORDS, "Abomasnow", usage=usage)

    assert "Focus Sash 40.0%" in response
    assert "Snow Warning 98.5%" in response
    assert "Blizzard 91.2%" in response
    assert "Wood Hammer 84.0%" in response


def test_usage_response_omits_empty_sections():
    usage = {"Abomasnow": {"items": [], "abilities": [{"name": "Snow Warning", "usage_pct": 98.5}], "moves": []}}

    response = usage_response(_RECORDS, "Abomasnow", usage=usage)

    assert "Items:" not in response
    assert "Abilities: Snow Warning 98.5%" in response
    assert "Moves:" not in response
