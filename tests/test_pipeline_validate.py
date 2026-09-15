from pipeline.validate import (
    COUNT_TOLERANCE,
    EXPECTED_REGULATION_COUNTS,
    validate_items,
    validate_legal_count,
    validate_records,
    validate_usage,
    validate_write_count,
)


def _good_record(name="Abomasnow"):
    return {
        "name": name,
        "types": ["Grass", "Ice"],
        "base_stats": {
            "hp": 90, "attack": 92, "defense": 75,
            "sp_attack": 92, "sp_defense": 85, "speed": 60,
        },
        "abilities": ["Snow Warning"],
        "learnset": ["Blizzard"],
        "legal_in": ["M-C"],
    }


def test_validate_records_returns_no_problems_for_good_data():
    assert validate_records([_good_record()]) == []


def test_validate_records_flags_a_record_missing_a_name():
    record = _good_record()
    del record["name"]

    problems = validate_records([record])

    assert len(problems) == 1
    assert "missing name" in problems[0]


def test_validate_records_flags_an_empty_learnset():
    record = _good_record()
    record["learnset"] = []

    problems = validate_records([record])

    assert len(problems) == 1
    assert "empty learnset" in problems[0]
    assert "Abomasnow" in problems[0]


def test_validate_records_flags_missing_base_stat_fields():
    record = _good_record()
    del record["base_stats"]["speed"]

    problems = validate_records([record])

    assert len(problems) == 1
    assert "missing base stat fields" in problems[0]
    assert "Abomasnow" in problems[0]


def test_validate_records_reports_a_problem_per_broken_record():
    bad_1 = _good_record(name="Gyarados")
    bad_1["learnset"] = []
    bad_2 = _good_record(name="Garchomp")
    del bad_2["base_stats"]["hp"]

    problems = validate_records([bad_1, bad_2])

    assert len(problems) == 2


def test_validate_items_returns_no_problems_for_good_data():
    items = [{"name": "Life Orb", "description": "Boosts move power."}]

    assert validate_items(items) == []


def test_validate_items_flags_missing_name():
    items = [{"description": "Boosts move power."}]

    problems = validate_items(items)

    assert len(problems) == 1
    assert "missing name" in problems[0]


def test_validate_items_flags_missing_description():
    items = [{"name": "Life Orb"}]

    problems = validate_items(items)

    assert len(problems) == 1
    assert "Life Orb" in problems[0]
    assert "no description" in problems[0]


def test_validate_usage_returns_no_problems_when_all_species_are_known():
    usage = {"Abomasnow": {"moves": [], "items": [], "abilities": []}}
    known_species = {"Abomasnow", "Garchomp"}

    assert validate_usage(usage, known_species) == []


def test_validate_usage_flags_an_unknown_species():
    usage = {"Bogusmon": {"moves": [], "items": [], "abilities": []}}
    known_species = {"Abomasnow", "Garchomp"}

    problems = validate_usage(usage, known_species)

    assert len(problems) == 1
    assert "Bogusmon" in problems[0]


def test_validate_usage_returns_no_problems_for_an_empty_usage_dict():
    assert validate_usage({}, {"Abomasnow"}) == []


def test_validate_legal_count_returns_no_problems_when_count_matches_the_table():
    expected = EXPECTED_REGULATION_COUNTS["M-C"]

    assert validate_legal_count("M-C", expected) == []


def test_validate_legal_count_flags_a_count_far_below_the_expected_table_value():
    problems = validate_legal_count("M-C", 10)

    assert len(problems) == 1
    assert "M-C" in problems[0]
    assert "10" in problems[0]


def test_validate_legal_count_allows_small_variation_within_tolerance():
    expected = EXPECTED_REGULATION_COUNTS["M-C"]
    slightly_off = int(expected * (1 + COUNT_TOLERANCE / 2))

    assert validate_legal_count("M-C", slightly_off) == []


def test_validate_legal_count_skips_an_unrecognized_regulation():
    # Regulations not in the table (old/retired ones like M-B, and
    # synthetic test regulations) have nothing to compare against --
    # "unknown," not a failure.
    assert validate_legal_count("M-B", 1) == []
    assert validate_legal_count("Totally-Made-Up-Reg", 999999) == []


def test_validate_write_count_returns_no_problems_when_counts_match():
    assert validate_write_count(345, 345) == []


def test_validate_write_count_flags_any_shortfall():
    problems = validate_write_count(343, 345)

    assert len(problems) == 1
    assert "343" in problems[0]
    assert "345" in problems[0]
