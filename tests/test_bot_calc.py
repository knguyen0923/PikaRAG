from bot.commands.calc import calc_response, is_error_response

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


def test_is_error_response_true_for_error_messages():
    assert is_error_response("No Pokemon found matching 'Abomasno'.") is True
    assert is_error_response("Invalid attacker EVs. Expected format: ...") is True


def test_is_error_response_false_for_a_successful_calc():
    assert is_error_response("Abomasnow's Ice Beam vs Gyarados: 10-12 damage (5.0%-6.0%).") is False


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


def test_calc_response_rejects_evs_over_the_per_stat_cap():
    response = calc_response(_RECORDS, _MOVES, "Abomasnow", "Gyarados", "Ice Beam", attacker_evs="0/999/0/0/0/0")

    assert "invalid" in response.lower()
    assert "evs" in response.lower()


def test_calc_response_rejects_evs_over_the_total_cap():
    # Each stat is individually <= 252, but the total (300*2 = 600) exceeds 508.
    response = calc_response(_RECORDS, _MOVES, "Abomasnow", "Gyarados", "Ice Beam", attacker_evs="0/252/252/0/0/96")

    assert "invalid" in response.lower()
    assert "evs" in response.lower()


def test_calc_response_rejects_unrecognized_attacker_nature():
    response = calc_response(_RECORDS, _MOVES, "Abomasnow", "Gyarados", "Ice Beam", attacker_nature="Adamnt")

    assert "invalid" in response.lower()
    assert "nature" in response.lower()


def test_calc_response_rejects_unrecognized_defender_nature():
    response = calc_response(_RECORDS, _MOVES, "Abomasnow", "Gyarados", "Ice Beam", defender_nature="Modeset")

    assert "invalid" in response.lower()
    assert "nature" in response.lower()


def test_calc_response_rejects_unrecognized_attacker_tera_type():
    response = calc_response(_RECORDS, _MOVES, "Abomasnow", "Gyarados", "Ice Beam", attacker_tera="Fir")

    assert "invalid" in response.lower()
    assert "tera" in response.lower()


def test_calc_response_rejects_out_of_range_defender_hp_percent():
    response = calc_response(_RECORDS, _MOVES, "Abomasnow", "Gyarados", "Ice Beam", defender_hp_percent=0)

    assert "invalid" in response.lower()
    assert "hp" in response.lower()

    response = calc_response(_RECORDS, _MOVES, "Abomasnow", "Gyarados", "Ice Beam", defender_hp_percent=101)

    assert "invalid" in response.lower()
    assert "hp" in response.lower()


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


_ASSAULT_VEST = {"name": "Assault Vest", "description": "Boosts Sp. Def by 50%; prevents status moves."}
_ITEMS = [_ASSAULT_VEST]


def test_calc_response_unknown_attacker_item_suggests_close_matches_when_items_given():
    response = calc_response(
        _RECORDS, _MOVES, "Abomasnow", "Gyarados", "Ice Beam",
        attacker_item="Assult Vest", items=_ITEMS,
    )

    assert "no item" in response.lower()
    assert "Assault Vest" in response


def test_calc_response_skips_item_validation_when_no_items_list_given():
    # Backward-compatible: callers that don't pass `items` (e.g. existing
    # tests below) get the old pass-through-unvalidated behavior.
    response = calc_response(
        _RECORDS, _MOVES, "Abomasnow", "Gyarados", "Ice Beam", attacker_item="Anything Goes"
    )

    assert "no item" not in response.lower()


def test_calc_response_canonicalizes_item_casing_before_applying_its_effect(monkeypatch):
    # Regression: a validated item must still reach damage_calc with its
    # canonical casing, since damage_calc's item dicts are case-sensitive
    # exact-match lookups against the raw string.
    def _max_damage(response: str) -> int:
        return int(response.split(": ")[1].split("-")[1].split(" ")[0])

    baseline = calc_response(_RECORDS, _MOVES, "Abomasnow", "Gyarados", "Ice Beam")
    with_vest = calc_response(
        _RECORDS, _MOVES, "Abomasnow", "Gyarados", "Ice Beam",
        defender_item="assault vest", items=_ITEMS,
    )

    assert _max_damage(with_vest) < _max_damage(baseline)


def test_calc_response_defender_item_reduces_damage():
    def _max_damage(response: str) -> int:
        return int(response.split(": ")[1].split("-")[1].split(" ")[0])

    baseline = calc_response(_RECORDS, _MOVES, "Abomasnow", "Gyarados", "Ice Beam")
    with_vest = calc_response(
        _RECORDS, _MOVES, "Abomasnow", "Gyarados", "Ice Beam", defender_item="Assault Vest"
    )

    assert _max_damage(with_vest) < _max_damage(baseline)
