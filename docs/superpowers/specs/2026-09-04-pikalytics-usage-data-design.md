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
- A new pipeline stage fetching per-species usage data (top moves, items, abilities,
  and — best-effort — EV spreads) from Pikalytics' AI-facing endpoint, for the
  current regulation's legal roster.
- `/stats` augmented with a "Common build" line when usage data exists for that
  species.
- `/moves` switched to show top moves by usage % when usage data exists, falling
  back to today's full-legal-learnset behavior otherwise.

Explicitly out of scope:
- Common teammates — the sample data had no reliable usage percentages attached to
  teammate names, and neither `/stats` nor `/moves` needs them.
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
    "items": [{"name": str, "usage_pct": float}, ...],
    "abilities": [{"name": str, "usage_pct": float}, ...],
    "evs": [{"spread": str, "usage_pct": float}, ...],        # best-effort; empty list if
                                                                # Pikalytics doesn't expose a
                                                                # clean per-species EV table
                                                                # (see "Known unknown" below)
}
```

Stored in `data/processed/pikalytics_usage.json` as `{species_name: usage_record, ...}` —
species with no Pikalytics coverage simply have no key, which is how "no usage data"
is represented throughout (no null placeholders).

## Known unknown: exact page format

Everything above about the shape of Pikalytics' `/ai/pokedex/<format>/<species>`
response comes from a tool that fetches a page and has a small model *describe* it
in Markdown — not the literal raw HTTP response body. The first implementation task
must fetch a handful of real raw responses (`requests.get(url).text`) for known
species and inspect them directly before writing the parser. If the real format
differs meaningfully from what's described here (e.g. it's HTML tables rather than
Markdown, or EV data truly isn't available per-species), the parser adapts to
reality and this spec's `evs` field may end up permanently empty — that's an
acceptable, already-anticipated outcome, not a spec violation.

## Pipeline (`pipeline/fetch_pikalytics.py`)

Mirrors the existing `pipeline/fetch_pokeapi.py` shape and conventions:

- `resolve_pikalytics_slug(display_name: str) -> str` — best-effort transform from
  this project's display-name format to Pikalytics' URL slug. Confirmed empirically:
  hyphenated/regional forms use hyphens directly (`"Rotom-Wash"`,
  `"Ninetales-Alola"`), which differs from this project's own bracket-based display
  names (`"Rotom [Wash]"`, `"Meowstic [Female]"`). The transform strips brackets and
  joins with a hyphen (`"Rotom [Wash]"` → `"Rotom-Wash"`). Not every species will
  resolve correctly on the first try — see "Fetch behavior" below for how a bad
  guess is handled.
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
  51.5% Life Orb, 98.5% Rough Skin.` EVs are appended too if that list is non-empty,
  omitted otherwise (see "Known unknown").
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
