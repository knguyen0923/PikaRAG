import pytest
import requests
from unittest.mock import MagicMock
from bot.pokepaste_fetch import resolve_pokepaste_text, PokepasteFetchError


def test_raw_text_passes_through_unchanged():
    result = resolve_pokepaste_text("Garchomp @ Life Orb\n- Earthquake\n")

    assert result == "Garchomp @ Life Orb\n- Earthquake\n"


def test_url_is_fetched_from_the_raw_endpoint():
    session = MagicMock()
    response = MagicMock(status_code=200, text="Garchomp @ Life Orb\n- Earthquake\n")
    session.get.return_value = response

    result = resolve_pokepaste_text("https://pokepast.es/abc123", session=session)

    assert result == "Garchomp @ Life Orb\n- Earthquake\n"
    session.get.assert_called_once_with("https://pokepast.es/abc123/raw", timeout=(5, 10))


def test_trailing_slash_url_still_resolves_to_raw_endpoint():
    session = MagicMock()
    session.get.return_value = MagicMock(status_code=200, text="Garchomp\n- Earthquake\n")

    resolve_pokepaste_text("https://pokepast.es/abc123/", session=session)

    session.get.assert_called_once_with("https://pokepast.es/abc123/raw", timeout=(5, 10))


def test_http_error_raises_pokepaste_fetch_error():
    session = MagicMock()
    session.get.return_value = MagicMock(status_code=404)

    with pytest.raises(PokepasteFetchError, match="404"):
        resolve_pokepaste_text("https://pokepast.es/nonexistent", session=session)


def test_network_error_raises_pokepaste_fetch_error():
    session = MagicMock()
    session.get.side_effect = requests.exceptions.ConnectionError("refused")

    with pytest.raises(PokepasteFetchError, match="Network error"):
        resolve_pokepaste_text("https://pokepast.es/abc123", session=session)


def test_non_pokepaste_host_is_rejected():
    with pytest.raises(PokepasteFetchError, match="pokepast.es"):
        resolve_pokepaste_text("https://evil.example.com/abc123")
