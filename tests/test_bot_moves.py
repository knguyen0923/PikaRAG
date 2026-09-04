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
