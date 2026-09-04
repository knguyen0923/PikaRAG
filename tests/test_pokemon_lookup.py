from bot.pokemon_lookup import find_record, not_found_message, suggest_names

_RECORDS = [
    {"name": "Abomasnow", "types": ["Grass", "Ice"]},
    {"name": "Gyarados", "types": ["Water", "Flying"]},
    {"name": "Garchomp", "types": ["Dragon", "Ground"]},
]


def test_find_record_exact_match():
    record = find_record(_RECORDS, "Gyarados")

    assert record["name"] == "Gyarados"


def test_find_record_is_case_insensitive():
    record = find_record(_RECORDS, "gyarados")

    assert record["name"] == "Gyarados"


def test_find_record_returns_none_when_not_found():
    assert find_record(_RECORDS, "Pikachu") is None


def test_suggest_names_returns_close_matches():
    suggestions = suggest_names(_RECORDS, "Garchomp", n=2)

    assert suggestions == ["Garchomp"]


def test_suggest_names_returns_empty_list_when_nothing_close():
    suggestions = suggest_names(_RECORDS, "Zzzzzzzzzzzzzzz", n=2)

    assert suggestions == []
