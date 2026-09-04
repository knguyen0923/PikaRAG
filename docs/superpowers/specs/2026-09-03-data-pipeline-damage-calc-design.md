# Pika-RAG: Data Pipeline + Damage Calculator — Design

Status: Approved
Date: 2026-09-03

## Purpose

First implementation slice of Pika-RAG (see `pika-rag-project-plan.md` for full project
context). Scope is limited to the two pieces that are fully testable without any external
credentials (no Discord token, no Anthropic API key): the data pipeline and the damage
calculator. These are also independent of each other and can be built in parallel.

Later slices (RAG index, Haiku integration, Discord bot) build on top of this and are out
of scope here.

## Source data

The repo root already contains four JSON files, hand-verified as correct for the current
regulation set (M-B):

- `legal_pokemon_m-b.json` — the 315 legal Pokémon for M-B, including Mega/regional forms
- `vgc_abilities.json` — ability name → description
- `vgc_items.json` — item name → description
- `vgc_moves.json` — `meta` (regulation/season/counts), `pokemon` (name + types only), and
  `moves` (name/type/category/power/accuracy/pp/effect)

These files are **authoritative and used as-is** — not re-derived or overwritten by the
pipeline. When regulation M-C (or later) is announced, new versions of these four files
will be dropped in to replace the M-B ones, and the pipeline re-run. The pipeline must not
hardcode "M-B" anywhere except as a value read from the source files' own `regulation`
fields.

What the source JSONs do **not** contain, and what PokéAPI fetching must fill in:
- Base stats (HP/Atk/Def/SpA/SpD/Spe) per Pokémon
- Learnset / move pool per Pokémon (which of the 496 moves each Pokémon can actually learn)

Usage/spread data (Pikalytics) is explicitly out of scope for this slice — ToS is
unconfirmed (see project plan's Open Items). Real EV spreads/movesets come later; for now
the damage calculator takes explicit EVs/nature/etc. as input rather than inferring them.

## Project structure

```
pika-rag/
├── data/
│   ├── source/                    # the 4 authoritative JSONs (moved here from repo root)
│   │   ├── legal_pokemon_m-b.json
│   │   ├── vgc_abilities.json
│   │   ├── vgc_items.json
│   │   └── vgc_moves.json
│   ├── raw/                       # cached PokéAPI responses, checked into git for reproducibility (offline reruns, no live network needed to rebuild processed/)
│   └── processed/
│       └── pokemon_records.json   # merged output
├── pipeline/
│   ├── fetch_pokeapi.py           # pulls base stats + learnsets for each legal Pokémon
│   ├── build_records.py           # merges source/ + raw/ into processed/pokemon_records.json
│   └── refresh_job.py             # rerun entrypoint (e.g. after dropping in new regulation source files)
├── damage_calc/
│   ├── calc.py                    # ported @smogon/calc core damage formula
│   └── data/                      # calc-only lookups (nature table, type effectiveness chart, stat stage multipliers)
├── tests/
│   ├── test_pipeline.py
│   └── test_calc.py
└── requirements.txt
```

## Data pipeline

**`fetch_pokeapi.py`**
- Input: list of 315 legal Pokémon names from `data/source/legal_pokemon_m-b.json`
- For each name, resolve to a PokéAPI species/pokemon identifier — handling name variants
  not native to PokéAPI's naming scheme (e.g. `"Mega Absol"` → `absol-mega`, `"Aegislash
  [Blade Forme]"` → `aegislash-blade`, `"Arcanine [Hisuian Form]"` → `arcanine-hisui`).
  A small manual alias map is expected and acceptable for edge cases PokéAPI's fuzzy
  matching can't resolve.
- Fetch and cache: base stats, and the move-learn list (names only, filtered down to moves
  that exist in `vgc_moves.json` — moves outside the current move list aren't relevant).
- Output: raw cached JSON per Pokémon under `data/raw/`, so reruns don't re-hit the network
  unless the cache is cleared.
- Must be safe to re-run (idempotent) and must not fail the whole run if one Pokémon's
  lookup fails — log and continue, report a summary of failures at the end.

**`build_records.py`**
- Merges `data/source/*.json` + `data/raw/*` into `data/processed/pokemon_records.json`.
- One record per legal Pokémon: `name`, `types`, `base_stats`, `abilities` (cross-referenced
  against `vgc_abilities.json` — only the abilities that Pokémon can actually have, from
  PokéAPI), `learnset` (list of move names, cross-referenced against `vgc_moves.json`),
  `legal_in` (regulation tag(s), read from source `meta.regulation` — a list so future
  regs can be unioned in rather than replacing).
- Deterministic given the same inputs (no network calls here — pure merge/transform).

**`refresh_job.py`**
- Thin entrypoint: `fetch_pokeapi.py` then `build_records.py`. This is what gets re-run
  when new regulation source JSONs are dropped into `data/source/`.

## Damage calculator

**`damage_calc/calc.py`**
- Pure function(s), no I/O: given attacker record + config (EVs, IVs, nature, stat stages,
  Tera type, held item, ability, current HP%), defender record + equivalent config, a move
  (from `vgc_moves.json` data), and battle context (weather, terrain, is-spread-target for
  doubles, screens, any other relevant field modifiers) → returns a damage range (min–max)
  and derived KO-chance percentage.
- Ported from `@smogon/calc`'s core formula (referenced, not copied wholesale — adapt to
  Python idiom). Needs its own small lookup tables under `damage_calc/data/` (type chart,
  nature multiplier table, stat stage multiplier table) — these are calculator constants,
  not regulation-dependent, so they don't move with regulation updates.
- Explicitly does not fetch or infer "common" spreads — caller supplies exact EVs/nature/etc.
  Higher-level "common spread" lookup is a later RAG-layer concern.

## Testing

- `tests/test_pipeline.py`: uses fixture/mocked PokéAPI responses (no live network calls in
  the test suite) to verify name-resolution edge cases, merge correctness, and that a
  malformed/missing individual Pokémon lookup doesn't crash the whole build.
- `tests/test_calc.py`: asserts exact min/max damage output against a handful of hand-picked
  reference calculations (cross-checked against Smogon's own published calculator output)
  covering: a basic physical hit, a spread move in doubles, a super-effective hit with Tera,
  and a case involving an ability that modifies damage (e.g. Intimidate on the attacker).

## Out of scope for this slice

- RAG/embeddings/Chroma index
- Anthropic/Haiku integration
- Discord bot (any part)
- Pikalytics scraping / real usage stats / common spreads
- Live deployment of anything — all verification is via `pytest`, no API keys required
- Held-item damage multipliers (Life Orb, Choice Band, Assault Vest, etc.) — a combatant's
  `item` field is accepted as an input for forward-compatibility but is not yet applied to
  the damage calculation. Adding real item mechanics is a follow-up task, not a bug in this
  slice.

## Known gap (post-implementation, added after final review)

Some Pokémon in `legal_pokemon_m-b.json` are Champions-format-original Mega Evolutions with
no PokéAPI record under any name (PokéAPI's Mega roster stops at Gen 6/7's canonical set).
These cannot be resolved by name-mapping fixes alone — the pipeline surfaces them in its
`failed` list rather than fabricating data, but sourcing real stats for them (hand-authored?
derived from base forme? a different data source?) is an open product decision for whoever
picks up the next data-pipeline task.
