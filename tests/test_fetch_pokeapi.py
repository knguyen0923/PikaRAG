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
    assert resolve_pokeapi_name("Arcanine [Hisuian Form]") == "arcanine-hisuian"

def test_resolve_female_form_name():
    assert resolve_pokeapi_name("Basculegion [Female]") == "basculegion-female"

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
}

def test_fetch_pokemon_data_parses_stats_and_learnset():
    session = _mock_session(_SAMPLE_POKEAPI_RESPONSE)
    result = fetch_pokemon_data("Abomasnow", session=session)
    assert result["base_stats"] == {
        "hp": 90, "attack": 92, "defense": 75,
        "sp_attack": 92, "sp_defense": 85, "speed": 60,
    }
    assert result["learnset"] == ["ice-punch", "wood-hammer"]

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
    session.get.side_effect = [fail_response, ok_response]
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
