import re

import requests

_URL_PATTERN = re.compile(r"^https?://", re.IGNORECASE)


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

    session = session or requests.Session()
    url = pokepaste.rstrip("/") + "/raw"
    try:
        response = session.get(url)
    except requests.exceptions.RequestException as e:
        raise PokepasteFetchError(f"Network error fetching '{pokepaste_original}': {e}") from e
    if response.status_code != 200:
        raise PokepasteFetchError(f"Could not fetch '{pokepaste_original}' (got HTTP {response.status_code}).")
    return response.text
