import re

# Generic noun words that the legal list appends to a form name but that PokeAPI
# omits from its variety slugs: "Lycanroc [Dusk Form]" -> "lycanroc-dusk",
# "Aegislash [Blade Forme]" -> "aegislash-blade",
# "Gourgeist [Large Variety]" -> "gourgeist-large".
_FORM_NOUNS = {"form", "forme", "variety", "size", "style", "mode", "cloak"}

# Regional adjectives as written in the legal list -> PokeAPI's region stem.
# PokeAPI uses the bare region name ("hisui", "galar", "alola", "paldea"),
# never the adjective form ("hisuian", "galarian", ...).
_REGION_FORM_MAP = {
    "hisuian": "hisui",
    "galarian": "galar",
    "alolan": "alola",
    "paldean": "paldea",
    "kantonian": "kanto",
    "johtonian": "johto",
}

# Form words the legal list spells differently from PokeAPI. Gourgeist's
# largest size is "Jumbo" in-game but "super" in PokeAPI ("gourgeist-super");
# its other sizes (average/small/large) match verbatim.
_FORM_WORD_ALIASES = {
    "jumbo": "super",
}

# Species whose form names are written BEFORE the species name in the legal
# list ("Heat Rotom") while PokeAPI slugs them after it ("rotom-heat").
# This is a species set, not a name-to-slug table: any "<Form> Rotom" resolves.
_PREFIX_FORM_SPECIES = {"rotom"}

# Characters that appear in display names but never in a PokeAPI slug:
# periods ("Mr. Rime" -> "mr-rime", "Mime Jr." -> "mime-jr"), apostrophes in
# either ASCII or curly form ("Farfetch'd" -> "farfetchd"), and colons.
_SLUG_STRIP_CHARS = ".':’"


def _slugify(text: str) -> str:
    """Lowercase a display name into PokeAPI's slug shape."""
    slug = text.strip().lower()
    for char in _SLUG_STRIP_CHARS:
        slug = slug.replace(char, "")
    return re.sub(r"\s+", "-", slug.strip())


def _normalize_form_words(text: str) -> list:
    """Turn form text like 'Paldean Form' into slug words like ['paldea']."""
    words = []
    for word in _slugify(text).split("-"):
        if not word or word in _FORM_NOUNS:
            continue
        word = _REGION_FORM_MAP.get(word, word)
        word = _FORM_WORD_ALIASES.get(word, word)
        words.append(word)
    return words


def resolve_pokeapi_name(display_name: str) -> str:
    name = display_name.strip()

    bracket_match = re.search(r"\[([^\]]+)\]", name)
    bracket_words = []
    if bracket_match:
        bracket_text = bracket_match.group(1).strip()
        name = name[: bracket_match.start()].strip()

        # A nested parenthetical narrows the outer form, and PokeAPI keeps both
        # parts in order: "[Paldean Form (Aqua Breed)]" -> "paldea-aqua-breed".
        # The inner words keep their nouns ("breed" is part of the real slug),
        # so only the outer form text goes through the form-noun stripping.
        paren_match = re.search(r"\(([^)]*)\)", bracket_text)
        paren_text = None
        if paren_match:
            paren_text = paren_match.group(1).strip()
            bracket_text = bracket_text[: paren_match.start()].strip()

        bracket_words = _normalize_form_words(bracket_text)
        if paren_text:
            bracket_words += [w for w in _slugify(paren_text).split("-") if w]

    mega_match = re.match(r"^Mega (.+?)( X| Y)?$", name)
    if mega_match:
        base = mega_match.group(1)
        suffix = mega_match.group(2)
        slug = _slugify(base)
        if suffix:
            slug += f"-mega-{suffix.strip().lower()}"
        else:
            slug += "-mega"
        return slug

    # Prefix-form pattern: "<Form> <Species>" -> "<species>-<form>".
    words = name.split()
    if len(words) > 1 and words[-1].lower() in _PREFIX_FORM_SPECIES:
        species = _slugify(words[-1])
        form_words = [_slugify(w) for w in words[:-1]]
        slug = "-".join([species] + form_words)
        return "-".join([slug] + bracket_words) if bracket_words else slug

    slug = _slugify(name)
    if bracket_words:
        slug += "-" + "-".join(bracket_words)
    return slug


import requests

POKEAPI_BASE_URL = "https://pokeapi.co/api/v2/pokemon"
POKEAPI_SPECIES_URL = "https://pokeapi.co/api/v2/pokemon-species"

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


def _get(session, url, display_name, slug):
    try:
        return session.get(url)
    except requests.exceptions.RequestException as e:
        raise PokeApiFetchError(
            f"Network error fetching '{display_name}' (slug '{slug}'): {e}"
        ) from e


def _default_variety_slug(session, slug: str, display_name: str):
    """Resolve a bare species slug to its default variety slug, or None.

    Some species have no bare-species Pokemon record: PokeAPI stores even the
    default form under a suffixed slug ("lycanroc" -> "lycanroc-midday",
    "palafin" -> "palafin-zero", "maushold" -> "maushold-family-of-four").
    This is safe to apply generally because it only fires when `slug` is itself
    a valid *species* name -- so we can only ever be asking for that species'
    default form. A form-specific slug that 404s (e.g. "meowstic-mega") is not
    a species name, so the species lookup 404s too and nothing is substituted.
    """
    response = _get(session, f"{POKEAPI_SPECIES_URL}/{slug}", display_name, slug)
    if response.status_code != 200:
        return None
    for variety in response.json().get("varieties", []):
        if variety.get("is_default"):
            name = variety.get("pokemon", {}).get("name")
            if name and name != slug:
                return name
    return None


def fetch_pokemon_data(display_name: str, session=None) -> dict:
    session = session or requests.Session()
    slug = resolve_pokeapi_name(display_name)
    response = _get(session, f"{POKEAPI_BASE_URL}/{slug}", display_name, slug)
    if response.status_code != 200:
        fallback_slug = _default_variety_slug(session, slug, display_name)
        if fallback_slug:
            slug = fallback_slug
            response = _get(session, f"{POKEAPI_BASE_URL}/{slug}", display_name, slug)
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
    abilities = [a["ability"]["name"] for a in payload["abilities"]]
    return {"base_stats": base_stats, "learnset": learnset, "abilities": abilities}


import json
from pathlib import Path

from pipeline.cache_utils import simple_cache_filename


def fetch_all(legal_names: list, cache_dir, session=None) -> dict:
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    session = session or requests.Session()

    fetched, cached, failed = 0, 0, []
    for name in legal_names:
        cache_file = cache_dir / simple_cache_filename(name)
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
