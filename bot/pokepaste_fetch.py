import re
from urllib.parse import urlparse

import requests

_URL_PATTERN = re.compile(r"^https?://", re.IGNORECASE)
_ALLOWED_HOSTS = {"pokepast.es", "www.pokepast.es"}
_REQUEST_TIMEOUT = (5, 10)  # (connect, read) seconds


class PokepasteFetchError(Exception):
    pass


def resolve_pokepaste_text(pokepaste: str, session=None) -> str:
    """Return raw Showdown-format team text.

    If `pokepaste` is a pokepast.es URL, fetches its plain-text export from
    the `/raw` route. Otherwise returns it unchanged (already raw text).
    """
    pokepaste_original = pokepaste
    pokepaste = pokepaste.strip()
    if not _URL_PATTERN.match(pokepaste):
        return pokepaste_original

    hostname = (urlparse(pokepaste).hostname or "").lower()
    if hostname not in _ALLOWED_HOSTS:
        raise PokepasteFetchError(
            f"'{pokepaste_original}' is not a pokepast.es URL -- only pokepast.es links can be fetched."
        )

    session = session or requests.Session()
    url = pokepaste.rstrip("/") + "/raw"
    try:
        response = session.get(url, timeout=_REQUEST_TIMEOUT)
    except requests.exceptions.RequestException as e:
        raise PokepasteFetchError(f"Network error fetching '{pokepaste_original}': {e}") from e
    if response.status_code != 200:
        raise PokepasteFetchError(f"Could not fetch '{pokepaste_original}' (got HTTP {response.status_code}).")
    return response.text
