import pytest
from bot.pokepaste import parse_pokepaste, PokepasteParseError

_FULL_SPEC = """\
Iron Hands @ Assault Vest
Ability: Quark Drive
Level: 50
Tera Type: Water
EVs: 236 HP / 4 Atk / 4 Def / 116 SpD / 148 Spe
Adamant Nature
- Fake Out
- Wild Charge
- Drain Punch
- Heavy Slam
"""


def test_parses_species_item_and_moves():
    members = parse_pokepaste(_FULL_SPEC)

    assert len(members) == 1
    member = members[0]
    assert member["species"] == "Iron Hands"
    assert member["item"] == "Assault Vest"
    assert member["moves"] == ["Fake Out", "Wild Charge", "Drain Punch", "Heavy Slam"]


def test_parses_ability_level_tera_and_nature():
    member = parse_pokepaste(_FULL_SPEC)[0]

    assert member["ability"] == "Quark Drive"
    assert member["level"] == 50
    assert member["tera_type"] == "Water"
    assert member["nature"] == "Adamant"


def test_parses_evs_and_defaults_ivs_to_31():
    member = parse_pokepaste(_FULL_SPEC)[0]

    assert member["evs"] == {
        "hp": 236, "attack": 4, "defense": 4,
        "sp_attack": 0, "sp_defense": 116, "speed": 148,
    }
    assert member["ivs"] == {
        "hp": 31, "attack": 31, "defense": 31,
        "sp_attack": 31, "sp_defense": 31, "speed": 31,
    }


def test_parses_nickname_and_gender():
    member = parse_pokepaste("Bob (Flutter Mane) (F) @ Focus Sash\n- Moonblast\n")[0]

    assert member["nickname"] == "Bob"
    assert member["species"] == "Flutter Mane"
    assert member["gender"] == "F"


def test_no_nickname_when_no_parenthetical():
    member = parse_pokepaste("Garchomp @ Life Orb\n- Earthquake\n")[0]

    assert member["nickname"] is None
    assert member["species"] == "Garchomp"


def test_omitted_optional_fields_use_neutral_defaults():
    member = parse_pokepaste("Garchomp\n- Earthquake\n")[0]

    assert member["item"] is None
    assert member["ability"] is None
    assert member["tera_type"] is None
    assert member["nature"] == "Hardy"
    assert member["evs"] == {"hp": 0, "attack": 0, "defense": 0, "sp_attack": 0, "sp_defense": 0, "speed": 0}
    assert member["level"] == 50


_TWO_MON_TEAM = """\
Garchomp @ Life Orb
- Earthquake

Flutter Mane @ Focus Sash
- Moonblast
"""


def test_parses_multiple_blank_line_separated_blocks():
    members = parse_pokepaste(_TWO_MON_TEAM)

    assert [m["species"] for m in members] == ["Garchomp", "Flutter Mane"]


def test_more_than_six_blocks_raises():
    seven_mon_text = "\n\n".join(f"Pokemon{i}\n- Tackle" for i in range(7))

    with pytest.raises(PokepasteParseError, match="at most 6"):
        parse_pokepaste(seven_mon_text)


def test_unrecognized_line_raises_with_block_number():
    with pytest.raises(PokepasteParseError, match="Block 1"):
        parse_pokepaste("Foo @ Life Orb\n@#$%\n- Earthquake\n")


def test_empty_text_raises():
    with pytest.raises(PokepasteParseError, match="No Pokemon found"):
        parse_pokepaste("")
