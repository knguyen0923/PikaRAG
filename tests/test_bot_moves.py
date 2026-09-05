from bot.commands.moves import moves_response

_ABOMASNOW = {
    "name": "Abomasnow",
    "types": ["Grass", "Ice"],
    "base_stats": {"hp": 90, "attack": 92, "defense": 75, "sp_attack": 92, "sp_defense": 85, "speed": 60},
    "abilities": ["Snow Warning", "Soundproof"],
    "learnset": ["Blizzard", "Wood Hammer"],
    "legal_in": ["M-B"],
}

_RECORDS = [_ABOMASNOW]


def test_moves_response_lists_the_full_learnset():
    response = moves_response(_RECORDS, "Abomasnow")

    assert "Abomasnow" in response
    assert "Blizzard" in response
    assert "Wood Hammer" in response


def test_moves_response_is_case_insensitive():
    response = moves_response(_RECORDS, "abomasnow")

    assert "Abomasnow" in response


def test_moves_response_not_found_suggests_close_matches():
    response = moves_response(_RECORDS, "Abomasno")

    assert "not found" in response.lower() or "no pokemon" in response.lower()
    assert "Abomasnow" in response


def test_moves_response_shows_top_moves_when_usage_data_exists():
    usage = {"Abomasnow": {
        "moves": [{"name": "Blizzard", "usage_pct": 91.2}, {"name": "Wood Hammer", "usage_pct": 84.0}],
        "abilities": [], "items": [],
    }}

    response = moves_response(_RECORDS, "Abomasnow", usage=usage)

    assert "top moves" in response.lower()
    assert "Blizzard 91.2%" in response
    assert "Wood Hammer 84.0%" in response


def test_moves_response_falls_back_to_full_learnset_when_no_usage_data():
    response = moves_response(_RECORDS, "Abomasnow", usage={})

    assert "legal moveset" in response.lower()


def test_moves_response_falls_back_when_usage_entry_has_no_moves():
    usage = {"Abomasnow": {"moves": [], "abilities": [], "items": []}}

    response = moves_response(_RECORDS, "Abomasnow", usage=usage)

    assert "legal moveset" in response.lower()


def test_moves_response_usage_defaults_to_none_and_behaves_like_before():
    with_default = moves_response(_RECORDS, "Abomasnow")
    with_explicit_none = moves_response(_RECORDS, "Abomasnow", usage=None)

    assert with_default == with_explicit_none
    assert "legal moveset" in with_default.lower()
