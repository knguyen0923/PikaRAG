"""Shared helpers mapping a display name to a filesystem-safe cache filename.

Originally written as the contract between `fetch_pokeapi` (writes the raw
cache) and `build_records` (reads it back) so the two sides cannot drift.
Also reused by `fetch_pikalytics` for its own, differently-scoped raw cache
under a different directory -- the filename mapping itself has no
PokeAPI-specific behavior; only the directory each caller passes differs.
"""


def simple_cache_filename(display_name: str) -> str:
    """Map a legal-list display name to its raw cache filename."""
    slug = display_name.lower()
    slug = slug.replace("[", "").replace("]", "")
    slug = slug.replace(" ", "_")
    return f"{slug}.json"
