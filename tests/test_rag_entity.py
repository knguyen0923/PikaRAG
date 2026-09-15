import os
import subprocess
import sys

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


def test_detect_entity_fuzzy_matching_is_deterministic_across_hash_seeds():
    """Regression test: fuzzy matching must be deterministic regardless of
    Python's hash randomization. A same-process repeat loop doesn't prove
    this (hash seed is fixed within one process) -- this runs the same
    call in fresh subprocesses under different explicit PYTHONHASHSEED
    values and confirms the result never changes."""
    script = (
        "from rag.entity import detect_entity\n"
        "records = [{'name': 'Kommo-o'}, {'name': 'Kleavor'}]\n"
        "print(detect_entity('Does Kommo-o learn Close Combat?', records, []))\n"
    )
    outputs = set()
    for seed in ("0", "1", "42"):
        env = dict(os.environ, PYTHONHASHSEED=seed)
        result = subprocess.run(
            [sys.executable, "-c", script], capture_output=True, text=True, env=env, check=True
        )
        outputs.add(result.stdout.strip())
    assert outputs == {"{'field': 'pokemon', 'name': 'Kommo-o'}"}, (
        f"detect_entity result varies across PYTHONHASHSEED values: {outputs}"
    )


def test_detect_entity_ambiguous_pokemon_does_not_leak_to_item_vocabulary():
    """Regression test for a real bug: an ambiguous Pokemon match (Mega Absol
    vs Mega Absol Z) must return None, not fall through and get bound to an
    unrelated item just because the item vocabulary happens to have
    something fuzzy-close to "Absol" (its own Mega Stone, "Absolite")."""
    items_with_mega_stone = _ITEMS + [{"name": "Absolite"}]

    entity = detect_entity("What is Mega Absol's Speed stat?", _RECORDS, items_with_mega_stone)

    assert entity is None


def test_detect_entity_does_not_crash_on_a_same_key_sibling_with_no_qualifier():
    """Regression test for a real crash: two item names that collide on
    _species_key (e.g. both end in a lone capital letter) but are NOT
    actually Mega/bracket variants of each other must not raise -- they're
    genuinely ambiguous, not a crash."""
    records_with_charizard_family = _RECORDS + [
        {"name": "Charizard"},
        {"name": "Mega Charizard X"},
        {"name": "Mega Charizard Y"},
    ]
    items_with_charizardite_family = _ITEMS + [
        {"name": "Charizardite X"},
        {"name": "Charizardite Y"},
    ]

    entity = detect_entity(
        "What are Mega Charizard's base stats?",
        records_with_charizard_family,
        items_with_charizardite_family,
    )

    assert entity is None


def test_detect_entity_exact_item_match_is_not_shadowed_by_fuzzy_pokemon_match():
    """Regression test for a real recall regression: an exact item match
    (e.g. "Chandelurite") must not be shadowed by a looser fuzzy Pokemon
    match (e.g. "Chandelure") found by iterating the Pokemon vocabulary's
    fuzzy stage before the item vocabulary is ever tried."""
    records_with_chandelure = _RECORDS + [{"name": "Chandelure"}]
    items_with_chandelurite = _ITEMS + [{"name": "Chandelurite"}]

    entity = detect_entity("What does Chandelurite do?", records_with_chandelure, items_with_chandelurite)

    assert entity == {"field": "item", "name": "Chandelurite"}
