"""Shared helpers for the raw PokeAPI cache layout.

`fetch_pokeapi` writes the raw cache and `build_records` reads it back, so the
display-name -> filename mapping is a contract between the two modules. It
lives here so the two sides cannot drift: if they did, `build_records` would
silently treat every Pokemon as "no raw cache" and emit zero records while
both modules' own tests stayed green.
"""


def simple_cache_filename(display_name: str) -> str:
    """Map a legal-list display name to its raw cache filename."""
    slug = display_name.lower()
    slug = slug.replace("[", "").replace("]", "")
    slug = slug.replace(" ", "_")
    return f"{slug}.json"
