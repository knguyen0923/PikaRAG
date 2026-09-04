from bot.commands.calc import calc_response

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

_ICE_BEAM = {"name": "Ice Beam", "type": "Ice", "category": "Special", "power": 90, "accuracy": 100, "pp": 12, "effect": None}
_TACKLE = {"name": "Tackle", "type": "Normal", "category": "Physical", "power": 40, "accuracy": 100, "pp": 35, "effect": None}
_MOVES = [_ICE_BEAM, _TACKLE]


def test_calc_response_reports_a_damage_range_and_percent():
    response = calc_response(_RECORDS, _MOVES, "Abomasnow", "Gyarados", "Ice Beam")

    assert "Abomasnow" in response
    assert "Ice Beam" in response
    assert "Gyarados" in response
    assert "-" in response
    assert "%" in response


def test_calc_response_unknown_attacker_suggests_close_matches():
    response = calc_response(_RECORDS, _MOVES, "Abomasno", "Gyarados", "Ice Beam")

    assert "no pokemon" in response.lower()
    assert "Abomasnow" in response


def test_calc_response_unknown_defender_suggests_close_matches():
    response = calc_response(_RECORDS, _MOVES, "Abomasnow", "Gyarado", "Ice Beam")

    assert "no pokemon" in response.lower()
    assert "Gyarados" in response


def test_calc_response_unknown_move_suggests_close_matches():
    response = calc_response(_RECORDS, _MOVES, "Abomasnow", "Gyarados", "Ice Beem")

    assert "no move" in response.lower()
    assert "Ice Beam" in response


def test_calc_response_rejects_malformed_evs():
    response = calc_response(_RECORDS, _MOVES, "Abomasnow", "Gyarados", "Ice Beam", attacker_evs="not-evs")

    assert "invalid" in response.lower()
    assert "evs" in response.lower()


def test_calc_response_higher_attacker_evs_increase_damage():
    baseline = calc_response(_RECORDS, _MOVES, "Abomasnow", "Gyarados", "Ice Beam")
    boosted = calc_response(
        _RECORDS, _MOVES, "Abomasnow", "Gyarados", "Ice Beam",
        attacker_evs="0/0/0/252/0/0", attacker_nature="Modest",
    )

    def _max_damage(response: str) -> int:
        return int(response.split(": ")[1].split("-")[1].split(" ")[0])

    assert _max_damage(boosted) > _max_damage(baseline)


def test_calc_response_flags_a_ko_chance_against_low_defender_hp():
    response = calc_response(
        _RECORDS, _MOVES, "Abomasnow", "Gyarados", "Ice Beam", defender_hp_percent=1
    )

    assert "ko chance" in response.lower()
