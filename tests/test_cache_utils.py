from pipeline.cache_utils import simple_cache_filename


def test_plain_name():
    assert simple_cache_filename("Abomasnow") == "abomasnow.json"


def test_spaces_become_underscores():
    assert simple_cache_filename("Mega Charizard X") == "mega_charizard_x.json"


def test_brackets_are_stripped():
    assert simple_cache_filename("Aegislash [Blade Forme]") == "aegislash_blade_forme.json"


def test_nested_parenthetical_name():
    assert (
        simple_cache_filename("Tauros [Paldean Form (Aqua Breed)]")
        == "tauros_paldean_form_(aqua_breed).json"
    )


def test_fetch_and_build_agree_on_filename():
    # The whole point of the shared module: both sides of the raw-cache
    # contract must call the same function, not two copies of it.
    from pipeline import fetch_pokeapi, build_records

    assert fetch_pokeapi.simple_cache_filename is simple_cache_filename
    assert build_records.simple_cache_filename is simple_cache_filename
