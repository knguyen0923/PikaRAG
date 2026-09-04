from bot.team_store import store_team, get_team, merge_scout, find_team_member, resolve_calc_overrides

_GARCHOMP = {
    "species": "Garchomp", "nickname": None, "gender": None, "item": "Life Orb",
    "ability": "Rough Skin", "level": 50, "tera_type": "Dragon",
    "evs": {"hp": 4, "attack": 252, "defense": 0, "sp_attack": 0, "sp_defense": 0, "speed": 252},
    "ivs": {"hp": 31, "attack": 31, "defense": 31, "sp_attack": 31, "sp_defense": 31, "speed": 31},
    "nature": "Jolly", "moves": ["Earthquake", "Dragon Claw"],
}


def test_get_team_is_empty_for_a_user_with_nothing_stored():
    assert get_team(101, "mine") == []


def test_store_team_then_get_team_round_trips():
    store_team(102, "mine", [_GARCHOMP])

    assert get_team(102, "mine") == [_GARCHOMP]


def test_store_team_replaces_the_previous_contents():
    store_team(103, "mine", [_GARCHOMP])
    store_team(103, "mine", [])

    assert get_team(103, "mine") == []


def test_store_team_rejects_more_than_six():
    seven = [dict(_GARCHOMP, species=f"Mon{i}") for i in range(7)]

    try:
        store_team(104, "mine", seven)
        assert False, "expected ValueError"
    except ValueError as e:
        assert "6" in str(e)


def test_merge_scout_adds_a_new_species():
    merge_scout(201, "opponent", dict(_GARCHOMP, moves=[]))

    assert get_team(201, "opponent") == [dict(_GARCHOMP, moves=[])]


def test_merge_scout_updates_item_on_an_existing_species_without_touching_other_fields():
    merge_scout(202, "opponent", dict(_GARCHOMP, item=None, moves=[]))

    merge_scout(202, "opponent", {
        "species": "Garchomp", "nickname": None, "gender": None,
        "item": "Focus Sash", "ability": None, "level": 50, "tera_type": None,
        "evs": {"hp": 0, "attack": 0, "defense": 0, "sp_attack": 0, "sp_defense": 0, "speed": 0},
        "ivs": {"hp": 31, "attack": 31, "defense": 31, "sp_attack": 31, "sp_defense": 31, "speed": 31},
        "nature": "Hardy", "moves": [],
    })

    stored = get_team(202, "opponent")[0]
    assert stored["item"] == "Focus Sash"
    assert stored["ability"] == "Rough Skin"  # untouched: the second call passed None


def test_merge_scout_adds_new_moves_without_dropping_known_ones():
    merge_scout(203, "opponent", dict(_GARCHOMP, moves=["Earthquake"]))

    merge_scout(203, "opponent", {
        "species": "Garchomp", "nickname": None, "gender": None,
        "item": None, "ability": None, "level": 50, "tera_type": None,
        "evs": {"hp": 0, "attack": 0, "defense": 0, "sp_attack": 0, "sp_defense": 0, "speed": 0},
        "ivs": {"hp": 31, "attack": 31, "defense": 31, "sp_attack": 31, "sp_defense": 31, "speed": 31},
        "nature": "Hardy", "moves": ["Dragon Claw"],
    })

    assert get_team(203, "opponent")[0]["moves"] == ["Earthquake", "Dragon Claw"]


def test_merge_scout_rejects_a_seventh_distinct_species():
    for i in range(6):
        merge_scout(204, "opponent", dict(_GARCHOMP, species=f"Mon{i}", moves=[]))

    try:
        merge_scout(204, "opponent", dict(_GARCHOMP, species="Mon6", moves=[]))
        assert False, "expected ValueError"
    except ValueError as e:
        assert "6" in str(e)


def test_find_team_member_matches_case_insensitively():
    store_team(301, "mine", [_GARCHOMP])

    assert find_team_member(301, "garchomp")["species"] == "Garchomp"


def test_find_team_member_checks_mine_before_opponent():
    store_team(302, "mine", [dict(_GARCHOMP, item="Life Orb")])
    store_team(302, "opponent", [dict(_GARCHOMP, item="Focus Sash")])

    assert find_team_member(302, "Garchomp")["item"] == "Life Orb"


def test_find_team_member_returns_none_when_not_found():
    assert find_team_member(303, "Nonexistent") is None


def test_find_team_member_does_not_grow_the_store_for_unseen_users():
    from bot.team_store import _store

    untouched_user_id = 888888
    find_team_member(untouched_user_id, "Nonexistent")

    assert untouched_user_id not in _store


def test_resolve_calc_overrides_uses_neutral_defaults_when_nothing_stored_or_explicit():
    evs, nature, item, tera = resolve_calc_overrides(401, "Nonexistent", None, None, None, None)

    assert evs == "0/0/0/0/0/0"
    assert nature == "Hardy"
    assert item is None
    assert tera is None


def test_resolve_calc_overrides_falls_back_to_stored_team_member():
    store_team(402, "mine", [_GARCHOMP])

    evs, nature, item, tera = resolve_calc_overrides(402, "Garchomp", None, None, None, None)

    assert evs == "4/252/0/0/0/252"
    assert nature == "Jolly"
    assert item == "Life Orb"
    assert tera == "Dragon"


def test_resolve_calc_overrides_explicit_value_wins_over_stored_team_member():
    store_team(403, "mine", [_GARCHOMP])

    _, _, item, _ = resolve_calc_overrides(403, "Garchomp", None, None, "Choice Band", None)

    assert item == "Choice Band"
