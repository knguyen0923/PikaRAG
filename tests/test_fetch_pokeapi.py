from pipeline.fetch_pokeapi import resolve_pokeapi_name
from unittest.mock import MagicMock
import pytest
from pipeline.fetch_pokeapi import fetch_pokemon_data, PokeApiFetchError
import json
import requests.exceptions

def test_resolve_plain_name():
    assert resolve_pokeapi_name("Abomasnow") == "abomasnow"

def test_resolve_mega_name():
    assert resolve_pokeapi_name("Mega Absol") == "absol-mega"

def test_resolve_mega_x_y_name():
    assert resolve_pokeapi_name("Mega Charizard X") == "charizard-mega-x"
    assert resolve_pokeapi_name("Mega Charizard Y") == "charizard-mega-y"

def test_resolve_bracket_forme_name():
    assert resolve_pokeapi_name("Aegislash [Blade Forme]") == "aegislash-blade"

def test_resolve_hisuian_form_name():
    # PokeAPI uses the bare region stem "hisui", never the adjective "hisuian".
    assert resolve_pokeapi_name("Arcanine [Hisuian Form]") == "arcanine-hisui"

def test_resolve_female_form_name():
    assert resolve_pokeapi_name("Basculegion [Female]") == "basculegion-female"


# --- Regression tests for categories verified against the live PokeAPI ---
# Every expected slug below was confirmed to return HTTP 200 from
# https://pokeapi.co/api/v2/pokemon/<slug> before being written down here.

def test_resolve_name_with_period():
    # "mr.-rime" (the old naive space->dash) is an invalid PokeAPI slug.
    assert resolve_pokeapi_name("Mr. Rime") == "mr-rime"
    assert resolve_pokeapi_name("Mr. Mime") == "mr-mime"
    assert resolve_pokeapi_name("Mime Jr.") == "mime-jr"

def test_resolve_apostrophe_name():
    assert resolve_pokeapi_name("Farfetch'd") == "farfetchd"
    assert resolve_pokeapi_name("Sirfetch’d") == "sirfetchd"

def test_resolve_prefix_form_rotom():
    # Form word comes BEFORE the species in the legal list; PokeAPI puts it after.
    assert resolve_pokeapi_name("Heat Rotom") == "rotom-heat"
    assert resolve_pokeapi_name("Wash Rotom") == "rotom-wash"
    assert resolve_pokeapi_name("Frost Rotom") == "rotom-frost"
    assert resolve_pokeapi_name("Fan Rotom") == "rotom-fan"
    assert resolve_pokeapi_name("Mow Rotom") == "rotom-mow"

def test_resolve_bracket_form_words_drop_the_form_noun():
    assert resolve_pokeapi_name("Lycanroc [Dusk Form]") == "lycanroc-dusk"
    assert resolve_pokeapi_name("Lycanroc [Midnight Form]") == "lycanroc-midnight"
    assert resolve_pokeapi_name("Palafin [Hero Form]") == "palafin-hero"
    assert resolve_pokeapi_name("Castform [Rainy Form]") == "castform-rainy"

def test_resolve_regional_forms():
    assert resolve_pokeapi_name("Ninetales [Alolan Form]") == "ninetales-alola"
    assert resolve_pokeapi_name("Slowbro [Galarian Form]") == "slowbro-galar"
    assert resolve_pokeapi_name("Typhlosion [Hisuian Form]") == "typhlosion-hisui"

def test_resolve_nested_parenthetical_breed():
    # Outer form goes through form-noun stripping ("Paldean Form" -> "paldea");
    # the inner parenthetical keeps its noun ("Aqua Breed" -> "aqua-breed").
    assert resolve_pokeapi_name("Tauros [Paldean Form (Aqua Breed)]") == "tauros-paldea-aqua-breed"
    assert resolve_pokeapi_name("Tauros [Paldean Form (Blaze Breed)]") == "tauros-paldea-blaze-breed"
    assert resolve_pokeapi_name("Tauros [Paldean Form (Combat Breed)]") == "tauros-paldea-combat-breed"

def test_resolve_gourgeist_size_varieties():
    # Three separate legal-list entries. PokeAPI names the largest size
    # "super", not "jumbo"; large/small match verbatim.
    assert resolve_pokeapi_name("Gourgeist [Jumbo Variety]") == "gourgeist-super"
    assert resolve_pokeapi_name("Gourgeist [Large Variety]") == "gourgeist-large"
    assert resolve_pokeapi_name("Gourgeist [Small Variety]") == "gourgeist-small"

def _mock_session(pokemon_json):
    session = MagicMock()
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = pokemon_json
    session.get.return_value = response
    return session

_SAMPLE_POKEAPI_RESPONSE = {
    "stats": [
        {"base_stat": 90, "stat": {"name": "hp"}},
        {"base_stat": 92, "stat": {"name": "attack"}},
        {"base_stat": 75, "stat": {"name": "defense"}},
        {"base_stat": 92, "stat": {"name": "special-attack"}},
        {"base_stat": 85, "stat": {"name": "special-defense"}},
        {"base_stat": 60, "stat": {"name": "speed"}},
    ],
    "moves": [
        {"move": {"name": "ice-punch"}},
        {"move": {"name": "wood-hammer"}},
    ],
    "abilities": [
        {"ability": {"name": "snow-warning"}},
        {"ability": {"name": "soundproof"}},
    ],
}

def test_fetch_pokemon_data_parses_stats_and_learnset():
    session = _mock_session(_SAMPLE_POKEAPI_RESPONSE)
    result = fetch_pokemon_data("Abomasnow", session=session)
    assert result["base_stats"] == {
        "hp": 90, "attack": 92, "defense": 75,
        "sp_attack": 92, "sp_defense": 85, "speed": 60,
    }
    assert result["learnset"] == ["ice-punch", "wood-hammer"]
    assert result["abilities"] == ["snow-warning", "soundproof"]

def test_fetch_pokemon_data_raises_on_http_error():
    session = MagicMock()
    response = MagicMock()
    response.status_code = 404
    session.get.return_value = response
    with pytest.raises(PokeApiFetchError):
        fetch_pokemon_data("Nonexistent", session=session)

from pipeline.fetch_pokeapi import fetch_all

def test_fetch_all_writes_cache_and_reports_summary(tmp_path):
    session = _mock_session(_SAMPLE_POKEAPI_RESPONSE)
    summary = fetch_all(["Abomasnow", "Absol"], cache_dir=tmp_path, session=session)
    assert summary["fetched"] == 2
    assert summary["cached"] == 0
    assert summary["failed"] == []
    assert (tmp_path / "abomasnow.json").exists()
    assert (tmp_path / "absol.json").exists()
    with open(tmp_path / "abomasnow.json") as f:
        cached = json.load(f)
    assert cached["base_stats"]["hp"] == 90

def test_fetch_all_skips_already_cached_files(tmp_path):
    (tmp_path / "abomasnow.json").write_text(json.dumps({"base_stats": {}, "learnset": []}))
    session = _mock_session(_SAMPLE_POKEAPI_RESPONSE)
    summary = fetch_all(["Abomasnow"], cache_dir=tmp_path, session=session)
    assert summary["fetched"] == 0
    assert summary["cached"] == 1
    session.get.assert_not_called()

def test_fetch_all_continues_after_one_failure(tmp_path):
    session = MagicMock()
    ok_response = MagicMock(status_code=200)
    ok_response.json.return_value = _SAMPLE_POKEAPI_RESPONSE
    fail_response = MagicMock(status_code=404)
    # 404 on the pokemon slug, then 404 on the species fallback lookup.
    session.get.side_effect = [fail_response, fail_response, ok_response]
    summary = fetch_all(["Broken Name", "Absol"], cache_dir=tmp_path, session=session)
    assert summary["fetched"] == 1
    assert summary["failed"] == ["Broken Name"]
    assert (tmp_path / "absol.json").exists()

def test_fetch_pokemon_data_wraps_request_exception():
    session = MagicMock()
    session.get.side_effect = requests.exceptions.ConnectionError("Connection refused")
    with pytest.raises(PokeApiFetchError) as exc_info:
        fetch_pokemon_data("Abomasnow", session=session)
    assert "Network error fetching" in str(exc_info.value)
    assert isinstance(exc_info.value.__cause__, requests.exceptions.ConnectionError)

def test_fetch_falls_back_to_species_default_variety():
    # PokeAPI has no bare "lycanroc" Pokemon record; its default form lives at
    # "lycanroc-midday". A 404 on a bare species slug retries via the species
    # endpoint and follows the is_default variety.
    session = MagicMock()
    miss = MagicMock(status_code=404)
    species = MagicMock(status_code=200)
    species.json.return_value = {
        "varieties": [
            {"is_default": True, "pokemon": {"name": "lycanroc-midday"}},
            {"is_default": False, "pokemon": {"name": "lycanroc-dusk"}},
        ]
    }
    hit = MagicMock(status_code=200)
    hit.json.return_value = _SAMPLE_POKEAPI_RESPONSE
    session.get.side_effect = [miss, species, hit]

    result = fetch_pokemon_data("Lycanroc", session=session)

    assert result["base_stats"]["hp"] == 90
    urls = [c.args[0] for c in session.get.call_args_list]
    assert urls[0].endswith("/pokemon/lycanroc")
    assert urls[1].endswith("/pokemon-species/lycanroc")
    assert urls[2].endswith("/pokemon/lycanroc-midday")


def test_fetch_does_not_substitute_a_wrong_form_on_404():
    # "mega-nonexistent" 404s, its bare species lookup 404s too (existing
    # substitution fallback), and its base-species lookup 404s as well (the
    # gendered-mega fallback) -- every avenue exhausted, so it must fail loudly.
    session = MagicMock()
    session.get.side_effect = [
        MagicMock(status_code=404), MagicMock(status_code=404), MagicMock(status_code=404),
    ]
    with pytest.raises(PokeApiFetchError) as exc_info:
        fetch_pokemon_data("Mega Nonexistent", session=session)
    assert "nonexistent-mega" in str(exc_info.value)


def test_fetch_resolves_a_mega_form_pokeapi_splits_by_gender():
    # PokeAPI has no genderless "meowstic-mega" -- only "meowstic-male-mega" /
    # "meowstic-female-mega". A 404 on the direct mega slug, and on the
    # (fruitless) species lookup for that same slug, falls back to the BASE
    # species' own default variety ("meowstic-male") to pick a gender, mirroring
    # how the bare (non-Mega) form already defaults to that same variety.
    session = MagicMock()
    mega_miss = MagicMock(status_code=404)
    mega_species_miss = MagicMock(status_code=404)
    base_species = MagicMock(status_code=200)
    base_species.json.return_value = {
        "varieties": [
            {"is_default": True, "pokemon": {"name": "meowstic-male"}},
            {"is_default": False, "pokemon": {"name": "meowstic-female"}},
        ]
    }
    hit = MagicMock(status_code=200)
    hit.json.return_value = _SAMPLE_POKEAPI_RESPONSE
    session.get.side_effect = [mega_miss, mega_species_miss, base_species, hit]

    result = fetch_pokemon_data("Mega Meowstic", session=session)

    assert result["base_stats"]["hp"] == 90
    urls = [c.args[0] for c in session.get.call_args_list]
    assert urls[0].endswith("/pokemon/meowstic-mega")
    assert urls[1].endswith("/pokemon-species/meowstic-mega")
    assert urls[2].endswith("/pokemon-species/meowstic")
    assert urls[3].endswith("/pokemon/meowstic-male-mega")


def test_fetch_all_continues_after_request_exception(tmp_path):
    session = MagicMock()
    ok_response = MagicMock(status_code=200)
    ok_response.json.return_value = _SAMPLE_POKEAPI_RESPONSE
    session.get.side_effect = [
        requests.exceptions.Timeout("Request timed out"),
        ok_response,
    ]
    summary = fetch_all(["Timeout Name", "Absol"], cache_dir=tmp_path, session=session)
    assert summary["fetched"] == 1
    assert summary["failed"] == ["Timeout Name"]
    assert (tmp_path / "absol.json").exists()
