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


def _max_damage(response: str) -> int:
    return int(response.split(": ")[1].split("-")[1].split(" ")[0])


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


def test_calc_response_accepts_an_attacker_ability():
    response = calc_response(
        _RECORDS, _MOVES, "Abomasnow", "Gyarados", "Ice Beam", attacker_ability="Snow Warning"
    )

    assert not is_error_response(response)


def test_calc_response_accepts_a_defender_ability():
    response = calc_response(
        _RECORDS, _MOVES, "Abomasnow", "Gyarados", "Ice Beam", defender_ability="Intimidate"
    )

    assert not is_error_response(response)


def test_calc_response_discloses_an_unmodeled_defender_ability():
    # Sturdy isn't one of the abilities this calculator models, so the
    # damage figure silently ignores it -- the response must say so.
    response = calc_response(
        _RECORDS, _MOVES, "Abomasnow", "Gyarados", "Ice Beam", defender_ability="Sturdy"
    )

    assert "(ability 'Sturdy' is not modeled)" in response


def test_calc_response_discloses_an_unmodeled_attacker_ability():
    response = calc_response(
        _RECORDS, _MOVES, "Abomasnow", "Gyarados", "Ice Beam", attacker_ability="Sturdy"
    )

    assert "(ability 'Sturdy' is not modeled)" in response


def test_calc_response_discloses_both_unmodeled_abilities_when_both_are_set():
    response = calc_response(
        _RECORDS, _MOVES, "Abomasnow", "Gyarados", "Ice Beam",
        attacker_ability="Sturdy", defender_ability="Regenerator",
    )

    assert "(ability 'Sturdy' is not modeled)" in response
    assert "(ability 'Regenerator' is not modeled)" in response


def test_calc_response_does_not_disclose_an_implemented_ability():
    response = calc_response(
        _RECORDS, _MOVES, "Abomasnow", "Gyarados", "Ice Beam", defender_ability="Multiscale"
    )

    assert "is not modeled" not in response


def test_calc_response_does_not_disclose_anything_when_no_ability_given():
    response = calc_response(_RECORDS, _MOVES, "Abomasnow", "Gyarados", "Ice Beam")

    assert "is not modeled" not in response


def test_calc_response_auto_derives_sun_weather_from_droughts_attacker():
    move = {"name": "Ember", "type": "Fire", "category": "Special", "power": 40, "accuracy": 100, "pp": 25, "effect": None}
    moves_with_ember = _MOVES + [move]

    baseline = calc_response(_RECORDS, moves_with_ember, "Abomasnow", "Gyarados", "Ember")
    with_sun = calc_response(
        _RECORDS, moves_with_ember, "Abomasnow", "Gyarados", "Ember", attacker_ability="Drought"
    )

    assert _max_damage(with_sun) > _max_damage(baseline)


def test_calc_response_auto_derives_snow_weather_from_defenders_snow_warning():
    # Snow Warning is Abomasnow's real ability in this fixture. It doesn't
    # boost/reduce any move TYPE's damage the way Rain/Sun do -- this
    # calculator also doesn't model Gen 9 Snow's separate Ice-type Defense
    # stat boost, so it correctly stays flagged as not modeled even though
    # the weather value is still auto-derived into context.
    response = calc_response(
        _RECORDS, _MOVES, "Abomasnow", "Gyarados", "Ice Beam", attacker_ability="Snow Warning"
    )

    assert not is_error_response(response)
    assert "(ability 'Snow Warning' is not modeled)" in response


def test_calc_response_discloses_sand_stream_as_unmodeled():
    # Sand Stream auto-derives "Sand" into context, but damage_calc.calc's
    # weather_modifier only branches on Rain/Sun -- Sand changes nothing,
    # so it must still be flagged not modeled.
    response = calc_response(
        _RECORDS, _MOVES, "Abomasnow", "Gyarados", "Ice Beam", attacker_ability="Sand Stream"
    )

    assert not is_error_response(response)
    assert "(ability 'Sand Stream' is not modeled)" in response


def test_calc_response_discloses_misty_surge_as_unmodeled():
    # Misty Surge auto-derives "Misty" into context, but _TERRAIN_TYPE_MAP
    # has no "Misty" entry -- it changes nothing, so it must still be
    # flagged not modeled.
    response = calc_response(
        _RECORDS, _MOVES, "Abomasnow", "Gyarados", "Ice Beam", attacker_ability="Misty Surge"
    )

    assert not is_error_response(response)
    assert "(ability 'Misty Surge' is not modeled)" in response


def test_calc_response_explicit_weather_param_wins_over_ability_derived_weather():
    move = {"name": "Ember", "type": "Fire", "category": "Special", "power": 40, "accuracy": 100, "pp": 25, "effect": None}
    moves_with_ember = _MOVES + [move]

    # Drought would auto-derive Sun (which boosts Fire); explicit Rain (which
    # weakens Fire) must win instead.
    response = calc_response(
        _RECORDS, moves_with_ember, "Abomasnow", "Gyarados", "Ember",
        attacker_ability="Drought", weather="Rain",
    )
    rain_damage = _max_damage(response)

    neutral = calc_response(_RECORDS, moves_with_ember, "Abomasnow", "Gyarados", "Ember")
    assert rain_damage < _max_damage(neutral)


def test_calc_response_auto_derives_electric_terrain_from_electric_surge():
    move = {"name": "Thunderbolt", "type": "Electric", "category": "Special", "power": 90, "accuracy": 100, "pp": 15, "effect": None}
    moves_with_tbolt = _MOVES + [move]

    baseline = calc_response(_RECORDS, moves_with_tbolt, "Abomasnow", "Gyarados", "Thunderbolt")
    with_terrain = calc_response(
        _RECORDS, moves_with_tbolt, "Abomasnow", "Gyarados", "Thunderbolt", attacker_ability="Electric Surge"
    )

    assert _max_damage(with_terrain) > _max_damage(baseline)


def test_calc_response_explicit_terrain_param_wins_over_ability_derived_terrain():
    move = {"name": "Thunderbolt", "type": "Electric", "category": "Special", "power": 90, "accuracy": 100, "pp": 15, "effect": None}
    moves_with_tbolt = _MOVES + [move]

    with_electric_surge = calc_response(
        _RECORDS, moves_with_tbolt, "Abomasnow", "Gyarados", "Thunderbolt", attacker_ability="Electric Surge"
    )
    with_explicit_override = calc_response(
        _RECORDS, moves_with_tbolt, "Abomasnow", "Gyarados", "Thunderbolt",
        attacker_ability="Electric Surge", terrain="Psychic",
    )

    assert _max_damage(with_explicit_override) < _max_damage(with_electric_surge)


def test_calc_response_defenders_intimidate_lowers_the_attackers_physical_damage():
    baseline = calc_response(_RECORDS, _MOVES, "Gyarados", "Abomasnow", "Tackle")
    with_intimidate = calc_response(
        _RECORDS, _MOVES, "Gyarados", "Abomasnow", "Tackle", defender_ability="Intimidate"
    )

    assert _max_damage(with_intimidate) < _max_damage(baseline)


def test_calc_response_attackers_intimidate_lowers_the_defenders_physical_damage_output_not_the_attackers_own():
    # Intimidate lowers the OPPONENT's Attack, not the holder's own -- so as
    # the attacker here, Gyarados's own outgoing damage must be unaffected.
    baseline = calc_response(_RECORDS, _MOVES, "Gyarados", "Abomasnow", "Tackle")
    with_own_intimidate = calc_response(
        _RECORDS, _MOVES, "Gyarados", "Abomasnow", "Tackle", attacker_ability="Intimidate"
    )

    assert _max_damage(with_own_intimidate) == _max_damage(baseline)


def test_calc_response_does_not_disclose_intimidate_as_unmodeled():
    response = calc_response(
        _RECORDS, _MOVES, "Abomasnow", "Gyarados", "Ice Beam", attacker_ability="Intimidate"
    )

    assert "is not modeled" not in response


def test_calc_response_does_not_disclose_a_weather_setter_ability_as_unmodeled():
    response = calc_response(
        _RECORDS, _MOVES, "Abomasnow", "Gyarados", "Ice Beam", attacker_ability="Drought"
    )

    assert "is not modeled" not in response


def test_calc_response_does_not_disclose_a_terrain_setter_ability_as_unmodeled():
    response = calc_response(
        _RECORDS, _MOVES, "Abomasnow", "Gyarados", "Ice Beam", attacker_ability="Electric Surge"
    )

    assert "is not modeled" not in response


def test_calc_response_discloses_auto_derived_weather_source():
    response = calc_response(
        _RECORDS, _MOVES, "Abomasnow", "Gyarados", "Ice Beam", attacker_ability="Drought"
    )

    assert "(Sun weather auto-derived from Drought)" in response


def test_calc_response_does_not_disclose_auto_derivation_when_weather_is_explicit():
    response = calc_response(
        _RECORDS, _MOVES, "Abomasnow", "Gyarados", "Ice Beam", attacker_ability="Drought", weather="Rain"
    )

    assert "auto-derived" not in response


def test_calc_response_discloses_auto_derived_terrain_source():
    response = calc_response(
        _RECORDS, _MOVES, "Abomasnow", "Gyarados", "Ice Beam", attacker_ability="Electric Surge"
    )

    assert "(Electric terrain auto-derived from Electric Surge)" in response


def test_calc_response_does_not_disclose_auto_derivation_when_terrain_is_explicit():
    response = calc_response(
        _RECORDS, _MOVES, "Abomasnow", "Gyarados", "Ice Beam",
        attacker_ability="Electric Surge", terrain="Psychic",
    )

    assert "auto-derived" not in response
