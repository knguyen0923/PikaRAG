# Pika-RAG: Pikalytics Usage Data — Design

Status: Approved
Date: 2026-09-04

## Purpose

The original data-pipeline spec explicitly deferred real usage data ("common EV
spreads/movesets... for now the damage calculator takes explicit EVs/nature/etc. as
input rather than inferring them"), citing an unconfirmed ToS. That block is lifted:
Pikalytics' own `robots.txt` broadly allows crawling and explicitly welcomes named AI
crawlers (including Anthropic), and their `/llms.txt` describes dedicated
AI-facing endpoints (`/ai/pokedex/<format>/<species>`) serving Markdown-formatted
usage data with no stated usage restrictions. This is not scraping in the adversarial
sense — these endpoints appear built for exactly this kind of consumption.

This closes the single largest gap between the project plan's stated scope
("common EV/nature spreads and movesets... sourced from real tournament/ladder
data") and what the bot has actually delivered so far: `/stats` and `/moves` today
show only base stats and the full legal learnset, not what's actually used in VGC.

## Scope

In scope:
- A new pipeline stage fetching per-species usage data (top moves, items, and
  abilities) from Pikalytics' AI-facing endpoint, for the current regulation's
  legal roster.
- `/stats` augmented with a "Common build" line when usage data exists for that
  species.
- `/moves` switched to show top moves by usage % when usage data exists, falling
  back to today's full-legal-learnset behavior otherwise.

Explicitly out of scope:
- Common teammates — confirmed in the real response to have literal `undefined%`
  usage values, and neither `/stats` nor `/moves` needs them.
- EV spreads — confirmed in the real response: there is no EV data anywhere on the
  page (see "Confirmed page format" below). The original design carried a
  best-effort `evs` field for this; it's dropped entirely now that its absence is
  confirmed rather than merely suspected.
- Any change to `/calc`, `/import`, `/scout`, `/team`, `bot/team_store.py`,
  `bot/pokepaste.py`, or anything under `damage_calc/`. This feature is purely
  additive to `/stats` and `/moves`; the full existing test suite must pass
  unmodified as proof.
- Automatically deriving Pikalytics' format code from our own regulation label (see
  "Format code" below) — it's a manually-set, manually-verified constant.

## Format code (must be verified by a human, not automated)

Pikalytics' per-format usage data lives under a format code like
`battledataregmbs3` — confirmed via their own `/llms.txt` to mean "Pokemon Champions
VGC 2026 Regulation Set M-B S3." VGC is the doubles format (as opposed to their
"Battle Stadium" singles variants or Smogon OU/Ubers data also hosted on the same
site), matching this project's doubles-only assumptions throughout
`damage_calc/calc.py` (spread-move reduction, doubles screen values, etc.).

The trailing `s3` is Pikalytics' own internal season counter for that regulation —
it is **not** derivable from our own `legal_pokemon_m-*.json` regulation label, and
will change independently of when we roll to a new regulation file. `PIKALYTICS_FORMAT_CODE`
is therefore a manually-set constant in `pipeline/fetch_pikalytics.py`, to be
re-verified against Pikalytics' current format list at the same time a new
regulation file is dropped in — this is an addition to, not a replacement for, the
existing "regulation legality... needs periodic manual check" step the project
already has.

## Data model

One usage record per species (only present for species Pikalytics has data for):

```python
{
    "moves": [{"name": str, "usage_pct": float}, ...],       # top 6 by usage, sorted desc
    "items": [{"name": str, "usage_pct": float}, ...],       # top 6 by usage, sorted desc
    "abilities": [{"name": str, "usage_pct": float}, ...],   # all listed abilities, sorted desc
}
```

Stored in `data/processed/pikalytics_usage.json` as `{species_name: usage_record, ...}` —
species with no Pikalytics coverage simply have no key, which is how "no usage data"
is represented throughout (no null placeholders).

## Confirmed page format

Fetched directly (`curl`, not a summarizing tool) against three real cases to
confirm the literal wire format before writing any parsing code:

- **Success** (`GET /ai/pokedex/battledataregmbs3/Garchomp`) — HTTP 200,
  `content-type: text/markdown; charset=utf-8`. Body is plain Markdown with a
  fixed section structure; the three sections this feature reads are exactly:
  ```
  ## Common Moves
  - **Dragon Claw**: 89.4%
  - **Rock Slide**: 82.0%
  ...

  ## Common Abilities
  - **Rough Skin**: 98.5%
  - **Sand Veil**: 1.5%

  ## Common Items
  - **Life Orb**: 51.5%
  - **Sitrus Berry**: 13.6%
  ...
  ```
  Each line is `- **<name>**: <percent>%`, one section per heading, sections
  always appear in this order. A `## Common Teammates` section follows Items,
  with every value literally the string `undefined%` — confirming it's unusable
  and correctly out of scope. No EV data appears anywhere on the page — confirming
  the original best-effort `evs` field would always have been empty, so it's
  dropped from the data model entirely rather than kept as a permanently-empty field.
- **Not found** (`GET /ai/pokedex/battledataregmbs3/Nonexistamon`) — HTTP 404,
  plain-text body `Pokemon not found`. Detected via status code alone; the body
  text is irrelevant.
- **Form/Mega slugs** (`GET .../Rotom-Wash`, `.../Abomasnow-Mega`,
  `.../Charizard-Mega-X`, `.../Charizard-Mega-Y`) — all HTTP 200 with the same
  section structure. Each of these is exactly this project's existing
  `pipeline.fetch_pokeapi.resolve_pokeapi_name(display_name)` slug
  (`"rotom-wash"`, `"abomasnow-mega"`, `"charizard-mega-x"`), **title-cased word by
  word**. This means Pikalytics' slug format needs no new form-parsing logic at
  all — `resolve_pokeapi_name` already correctly handles this project's
  bracket-based forms (`"Ninetales [Alolan Form]"`), prefix-form species
  (`"Wash Rotom"`), and `"Mega X"`/`"Mega X"`/`"Mega Y"` naming, all already tested
  in `tests/test_fetch_pokeapi.py`. Reusing it here means `resolve_pikalytics_slug`
  is a thin wrapper, not a parallel reimplementation.
  One confirmed miss: `resolve_pokeapi_name("Aegislash [Blade Forme]")` gives
  `"aegislash-blade"` → `"Aegislash-Blade"`, which 404s on Pikalytics (plausibly
  because Aegislash's Blade Forme is an in-battle transformation rather than a
  Pokedex entry Pikalytics tracks separately, not a slug-format bug) — an expected
  "no usage data for this one" outcome, not a defect to chase.

## Pipeline (`pipeline/fetch_pikalytics.py`)

Mirrors the existing `pipeline/fetch_pokeapi.py` shape and conventions:

- `resolve_pikalytics_slug(display_name: str) -> str` — `resolve_pokeapi_name(display_name)`
  (imported from `pipeline.fetch_pokeapi`), then title-cased word by word on `-`
  (`"rotom-wash"` → `"Rotom-Wash"`, `"charizard-mega-x"` → `"Charizard-Mega-X"`).
  Not every species will resolve correctly on the first try (see the Aegislash
  case above) — a 404 for any reason is handled identically as "no usage data,"
  never as an error to retry or chase (see `fetch_pikalytics_usage` below).
- `fetch_pikalytics_usage(display_name: str, session=None) -> dict | None` — fetches
  and parses one species' usage page. Returns `None` on a 404 rather than raising:
  missing usage data for a fringe pick is an **expected, acceptable outcome** here,
  not a data-integrity failure (unlike the PokeAPI stage, which fails loudly on a
  missing base-stat record, because every legal Pokemon must have base stats but
  not every legal Pokemon has meaningful competitive usage).
- `fetch_all_usage(legal_names: list, cache_dir, session=None) -> dict` — mirrors
  `fetch_all`'s cache-file-exists-skip behavior (including caching a `None` result,
  so a species confirmed to have no data isn't re-fetched every refresh run), plus a
  small delay (~0.5s) between live (non-cached) requests as a courtesy, even though
  `robots.txt` is permissive.
- A genuine network error during the refresh job aborts that one species (recorded
  in the refresh summary, matching the PokeAPI stage's `failed` list) without
  aborting the whole run.

## Feeding `/stats` and `/moves`

`bot/main.py` gains a `_load_usage()` helper (mirroring `_load_records()`/
`_load_moves()`) reading `data/processed/pikalytics_usage.json`, threaded into
`build_client` as a new optional parameter and passed to the `stats`/`moves`
commands.

- `stats_response(records, name, usage=None)`: unchanged base-stats output, plus —
  only when `usage.get(record["name"])` exists — an appended line: `Common build:
  51.5% Life Orb, 98.5% Rough Skin.`
- `moves_response(records, name, usage=None)`: when usage data with a non-empty
  `moves` list exists for the matched species, shows `Top moves (by usage): Dragon
  Claw 89.4%, Earthquake 76.2%, ...` instead of the full legal learnset. Falls back
  to today's full-learnset behavior for any species with no usage data or an empty
  moves list.

Both functions keep their existing signatures otherwise unchanged and backward
compatible (`usage=None` behaves identically to today).

## Testing

- `resolve_pikalytics_slug`: unit tests for plain names, bracketed forms, and the
  hyphen-join transform.
- `fetch_pikalytics_usage`: mocked-session tests for a successful parse, a 404
  (returns `None`), and a network error (raises), mirroring
  `tests/test_fetch_pokeapi.py`'s style.
- `fetch_all_usage`: cache-skip and `None`-caching behavior, mirroring
  `tests/test_fetch_pokeapi.py::test_fetch_all_skips_already_cached_files`.
- `stats_response`/`moves_response`: tested both with and without a `usage` argument,
  proving the fallback path is byte-identical to current behavior when `usage=None`
  or the species has no entry.
- The full existing test suite re-run unmodified at the end, proving `/calc`,
  `/import`, `/scout`, `/team`, `bot/team_store.py`, and `damage_calc/` are
  untouched by this feature.
