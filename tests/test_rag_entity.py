from rag.entity import detect_entity

_RECORDS = [
    {"name": "Abomasnow"},
    {"name": "Mega Abomasnow"},
    {"name": "Absol"},
    {"name": "Mega Absol"},
    {"name": "Mega Absol Z"},
    {"name": "Arcanine"},
    {"name": "Arcanine [Hisuian Form]"},
    {"name": "Gyarados"},
    {"name": "Garchomp"},
    {"name": "Kommo-o"},
    {"name": "Kleavor"},
]

_ITEMS = [
    {"name": "Life Orb"},
    {"name": "Abomasite"},
]


def test_detect_entity_resolves_an_exact_pokemon_name():
    entity = detect_entity("Does Gyarados learn Waterfall?", _RECORDS, _ITEMS)

    assert entity == {"field": "pokemon", "name": "Gyarados"}


def test_detect_entity_resolves_a_fuzzy_typo_name():
    entity = detect_entity("Does Abomasno learn Attract?", _RECORDS, _ITEMS)

    assert entity == {"field": "pokemon", "name": "Abomasnow"}


def test_detect_entity_returns_none_when_nothing_is_recognized():
    entity = detect_entity("What is the weather like today?", _RECORDS, _ITEMS)

    assert entity is None


def test_detect_entity_resolves_an_item_name():
    entity = detect_entity("What does Life Orb do?", _RECORDS, _ITEMS)

    assert entity == {"field": "item", "name": "Life Orb"}


def test_detect_entity_resolves_plain_species_to_the_base_form():
    entity = detect_entity("Does Abomasnow learn Attract?", _RECORDS, _ITEMS)

    assert entity == {"field": "pokemon", "name": "Abomasnow"}


def test_detect_entity_resolves_a_form_qualifier_to_the_variant():
    entity = detect_entity("Does Mega Abomasnow learn Attract?", _RECORDS, _ITEMS)

    assert entity == {"field": "pokemon", "name": "Mega Abomasnow"}


def test_detect_entity_resolves_a_bracketed_form_qualifier_to_the_variant():
    entity = detect_entity("Does Hisuian Arcanine learn Extreme Speed?", _RECORDS, _ITEMS)

    assert entity == {"field": "pokemon", "name": "Arcanine [Hisuian Form]"}


def test_detect_entity_falls_back_to_unfiltered_on_genuine_variant_ambiguity():
    entity = detect_entity("What is Mega Absol's Speed stat?", _RECORDS, _ITEMS)

    assert entity is None


def test_detect_entity_rejects_generic_words_that_score_below_ratio_threshold():
    """Regression test: generic word "learn" should not fuzzy-match to Kleavor.
    The word "learn" appears in Pokemon questions like "Does Kommo-o learn Close Combat?"
    but should not be accepted as a fuzzy match candidate."""
    entity = detect_entity("Does Kommo-o learn Close Combat?", _RECORDS, _ITEMS)

    assert entity == {"field": "pokemon", "name": "Kommo-o"}


def test_detect_entity_fuzzy_matching_is_deterministic():
    """Regression test: fuzzy matching must be deterministic.
    Running the same question multiple times should always return the same entity,
    not vary between runs due to set iteration order randomization."""
    question = "Does Kommo-o learn Close Combat?"

    # Run multiple times to ensure deterministic behavior
    results = [detect_entity(question, _RECORDS, _ITEMS) for _ in range(5)]

    # All results should be identical and correct
    expected = {"field": "pokemon", "name": "Kommo-o"}
    for result in results:
        assert result == expected
