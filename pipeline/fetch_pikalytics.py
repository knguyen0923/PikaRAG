import json
import re
import time
from pathlib import Path
from typing import Optional

import requests

from pipeline.cache_utils import simple_cache_filename
from pipeline.fetch_pokeapi import resolve_pokeapi_name

PIKALYTICS_FORMAT_CODE = "battledataregmbs3"  # VGC 2026 Reg M-B S3 -- manually
# verified against Pikalytics' current format list; re-verify whenever a new
# regulation file is dropped in (see spec's "Format code" section -- this is
# NOT derivable from our own regulation label).
PIKALYTICS_AI_BASE_URL = "https://www.pikalytics.com/ai/pokedex"
_TOP_N = 6


class PikalyticsFetchError(Exception):
    pass


def resolve_pikalytics_slug(display_name: str) -> str:
    """Pikalytics' URL slug for a species: this project's existing PokeAPI
    slug (which already solves Mega/regional/prefix-form/bracket naming),
    title-cased word by word on '-'. Confirmed empirically against a plain
    name, a prefix-form species, a bracket regional form, a Mega, and
    Mega X/Y forms.

    Two further divergences from the plain PokeAPI slug, confirmed live
    against the real Pikalytics endpoint: Pikalytics drops PokeAPI's
    trailing '-breed' segment on Tauros' Paldean forms, and abbreviates a
    trailing '-female' to '-f' (no confirmed '-male'/'-m' case exists in
    the current legal roster, so that direction is left alone).
    """
    pokeapi_slug = resolve_pokeapi_name(display_name)
    slug = "-".join(word.capitalize() for word in pokeapi_slug.split("-"))
    if slug.endswith("-Breed"):
        slug = slug[: -len("-Breed")]
    if slug.endswith("-Female"):
        slug = slug[: -len("-Female")] + "-F"
    return slug


_ENTRY_PATTERN = re.compile(r"^-\s+\*\*(.+?)\*\*:\s+([\d.]+)%\s*$")


def _extract_section(markdown: str, heading: str) -> list:
    """Pull '- **Name**: XX.X%' entries out of a '## <heading>' section,
    stopping at the next '## ' heading or end of text. Lines that don't
    match the expected shape (e.g. Pikalytics' teammate rows, which are
    literally '- **Name**: undefined%') are silently skipped.
    """
    pattern = re.compile(
        rf"^## {re.escape(heading)}\s*$(.*?)(?=^## |\Z)",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(markdown)
    if not match:
        return []
    entries = []
    for line in match.group(1).splitlines():
        entry_match = _ENTRY_PATTERN.match(line.strip())
        if entry_match:
            entries.append({"name": entry_match.group(1), "usage_pct": float(entry_match.group(2))})
    return entries


def parse_usage_markdown(markdown: str) -> dict:
    moves = sorted(_extract_section(markdown, "Common Moves"), key=lambda e: -e["usage_pct"])
    items = sorted(_extract_section(markdown, "Common Items"), key=lambda e: -e["usage_pct"])
    abilities = sorted(_extract_section(markdown, "Common Abilities"), key=lambda e: -e["usage_pct"])
    return {"moves": moves[:_TOP_N], "items": items[:_TOP_N], "abilities": abilities}


def _new_session() -> requests.Session:
    session = requests.Session()
    session.headers["User-Agent"] = "PikaRAG-Bot/1.0"
    return session


def fetch_pikalytics_usage(display_name: str, session=None) -> Optional[dict]:
    """Fetch and parse one species' usage page.

    Returns the parsed usage dict, or None if Pikalytics has no page for
    this species (HTTP 404) or has a page with no real usage data (every
    section empty after parsing -- Pikalytics returns this as HTTP 200
    with every percentage literally "undefined%" for a zero-usage
    species) -- both are the single "no usage data" outcome this module
    exposes, not two different ones. Raises PikalyticsFetchError on a
    network error or any other non-200 status.
    """
    session = session or _new_session()
    slug = resolve_pikalytics_slug(display_name)
    url = f"{PIKALYTICS_AI_BASE_URL}/{PIKALYTICS_FORMAT_CODE}/{slug}"
    try:
        response = session.get(url, timeout=(5, 10))
    except requests.exceptions.RequestException as e:
        raise PikalyticsFetchError(f"Network error fetching '{display_name}' (slug '{slug}'): {e}") from e
    if response.status_code == 404:
        return None
    if response.status_code != 200:
        raise PikalyticsFetchError(f"Pikalytics returned {response.status_code} for '{display_name}' (slug '{slug}')")
    data = parse_usage_markdown(response.text)
    if not data["moves"] and not data["items"] and not data["abilities"]:
        return None
    return data


def fetch_all_usage(legal_names: list, cache_dir, session=None, delay_seconds: float = 0.5) -> dict:
    cache_dir = Path(cache_dir) / PIKALYTICS_FORMAT_CODE
    cache_dir.mkdir(parents=True, exist_ok=True)
    session = session or _new_session()

    usage_by_species = {}
    fetched, cached, failed = 0, 0, []
    for name in legal_names:
        cache_file = cache_dir / simple_cache_filename(name)
        if cache_file.exists():
            with open(cache_file) as f:
                data = json.load(f)
            cached += 1
        else:
            try:
                data = fetch_pikalytics_usage(name, session=session)
            except PikalyticsFetchError:
                failed.append(name)
                if delay_seconds:
                    time.sleep(delay_seconds)
                continue
            with open(cache_file, "w") as f:
                json.dump(data, f, indent=2)
            fetched += 1
            if delay_seconds:
                time.sleep(delay_seconds)
        if data is not None:
            usage_by_species[name] = data

    return {"usage_by_species": usage_by_species, "fetched": fetched, "cached": cached, "failed": failed}
