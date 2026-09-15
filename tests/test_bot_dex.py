from bot.commands.dex import dex_page_response

_ABOMASNOW = {
    "name": "Abomasnow", "types": ["Grass", "Ice"],
    "base_stats": {"hp": 90, "attack": 92, "defense": 75, "sp_attack": 92, "sp_defense": 85, "speed": 60},
    "abilities": ["Snow Warning", "Soundproof"], "learnset": ["Blizzard", "Wood Hammer"], "legal_in": ["M-B"],
}
_GYARADOS = {
    "name": "Gyarados", "types": ["Water", "Flying"],
    "base_stats": {"hp": 95, "attack": 125, "defense": 79, "sp_attack": 60, "sp_defense": 100, "speed": 81},
    "abilities": ["Intimidate"], "learnset": ["Waterfall", "Dragon Dance"], "legal_in": ["M-B"],
}
_RECORDS = [_ABOMASNOW, _GYARADOS]


def test_dex_page_response_shows_the_record_at_the_given_index():
    response = dex_page_response(_RECORDS, 0)

    assert "Abomasnow" in response
    assert "HP 90" in response


def test_dex_page_response_shows_the_second_record():
    response = dex_page_response(_RECORDS, 1)

    assert "Gyarados" in response


def test_dex_page_response_includes_a_position_marker():
    response = dex_page_response(_RECORDS, 0)

    assert "(1/2)" in response

    response = dex_page_response(_RECORDS, 1)

    assert "(2/2)" in response
