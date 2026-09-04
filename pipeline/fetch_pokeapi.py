import re

_FORM_WORD_MAP = {
    "blade forme": "blade",
    "hisuian form": "hisuian",
    "galarian form": "galar",
    "alolan form": "alola",
    "paldean form": "paldea",
    "female": "female",
    "rainy form": "rainy",
    "snowy form": "snowy",
    "sunny form": "sunny",
}


def resolve_pokeapi_name(display_name: str) -> str:
    name = display_name.strip()

    bracket_match = re.search(r"\[([^\]]+)\]", name)
    bracket_suffix = None
    if bracket_match:
        bracket_text = bracket_match.group(1).strip().lower()
        bracket_suffix = _FORM_WORD_MAP.get(bracket_text, bracket_text.replace(" ", "-"))
        name = name[: bracket_match.start()].strip()

    mega_match = re.match(r"^Mega (.+?)( X| Y)?$", name)
    if mega_match:
        base = mega_match.group(1)
        suffix = mega_match.group(2)
        slug = base.lower().replace(" ", "-").replace("'", "")
        if suffix:
            slug += f"-mega-{suffix.strip().lower()}"
        else:
            slug += "-mega"
        return slug

    slug = name.lower().replace(" ", "-").replace("'", "")
    if bracket_suffix:
        slug += f"-{bracket_suffix}"
    return slug


import requests

POKEAPI_BASE_URL = "https://pokeapi.co/api/v2/pokemon"

_STAT_NAME_MAP = {
    "hp": "hp",
    "attack": "attack",
    "defense": "defense",
    "special-attack": "sp_attack",
    "special-defense": "sp_defense",
    "speed": "speed",
}


class PokeApiFetchError(Exception):
    pass


def fetch_pokemon_data(display_name: str, session=None) -> dict:
    session = session or requests.Session()
    slug = resolve_pokeapi_name(display_name)
    try:
        response = session.get(f"{POKEAPI_BASE_URL}/{slug}")
    except requests.exceptions.RequestException as e:
        raise PokeApiFetchError(
            f"Network error fetching '{display_name}' (slug '{slug}'): {e}"
        ) from e
    if response.status_code != 200:
        raise PokeApiFetchError(
            f"PokeAPI returned {response.status_code} for '{display_name}' (slug '{slug}')"
        )
    payload = response.json()
    base_stats = {
        _STAT_NAME_MAP[s["stat"]["name"]]: s["base_stat"]
        for s in payload["stats"]
        if s["stat"]["name"] in _STAT_NAME_MAP
    }
    learnset = [m["move"]["name"] for m in payload["moves"]]
    return {"base_stats": base_stats, "learnset": learnset}


import json
from pathlib import Path


def _simple_cache_filename(display_name: str) -> str:
    slug = display_name.lower()
    slug = slug.replace("[", "").replace("]", "")
    slug = slug.replace(" ", "_")
    return f"{slug}.json"


def fetch_all(legal_names: list, cache_dir, session=None) -> dict:
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    session = session or requests.Session()

    fetched, cached, failed = 0, 0, []
    for name in legal_names:
        cache_file = cache_dir / _simple_cache_filename(name)
        if cache_file.exists():
            cached += 1
            continue
        try:
            data = fetch_pokemon_data(name, session=session)
        except PokeApiFetchError:
            failed.append(name)
            continue
        with open(cache_file, "w") as f:
            json.dump(data, f, indent=2)
        fetched += 1

    return {"fetched": fetched, "cached": cached, "failed": failed}
