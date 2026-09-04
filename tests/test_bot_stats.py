from bot.commands.stats import stats_response

_ABOMASNOW = {
    "name": "Abomasnow",
    "types": ["Grass", "Ice"],
    "base_stats": {"hp": 90, "attack": 92, "defense": 75, "sp_attack": 92, "sp_defense": 85, "speed": 60},
    "abilities": ["Snow Warning", "Soundproof"],
    "learnset": ["Blizzard", "Wood Hammer"],
    "legal_in": ["M-B"],
}

_GYARADOS = {
    "name": "Gyarados",
    "types": ["Water", "Flying"],
    "base_stats": {"hp": 95, "attack": 125, "defense": 79, "sp_attack": 60, "sp_defense": 100, "speed": 81},
    "abilities": ["Intimidate"],
    "learnset": ["Waterfall", "Dragon Dance"],
    "legal_in": ["M-B"],
}

_RECORDS = [_ABOMASNOW, _GYARADOS]


def test_stats_response_includes_name_types_and_all_six_stats():
    response = stats_response(_RECORDS, "Abomasnow")

    assert "Abomasnow" in response
    assert "Grass" in response and "Ice" in response
    assert "90" in response  # hp
    assert "92" in response  # attack (and sp_attack, same value here)
    assert "75" in response  # defense
    assert "85" in response  # sp_defense
    assert "60" in response  # speed


def test_stats_response_includes_abilities():
    response = stats_response(_RECORDS, "Gyarados")

    assert "Intimidate" in response


def test_stats_response_is_case_insensitive():
    response = stats_response(_RECORDS, "gyarados")

    assert "Gyarados" in response


def test_stats_response_not_found_suggests_close_matches():
    response = stats_response(_RECORDS, "Abomasno")

    assert "not found" in response.lower() or "no pokemon" in response.lower()
    assert "Abomasnow" in response
