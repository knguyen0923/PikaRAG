# PikaRAG

A Discord bot for Pokemon VGC (Champions ranked doubles). It combines a
RAG pipeline over PokeAPI + Pikalytics usage data with a ported damage
calculator, so players can look up sets, check usage trends, calculate
damage, and manage a team roster without leaving Discord.

## Status

Deployed and live (Oracle Cloud, systemd-managed, always-on). Data is
current for **Regulation M-C** (345 legal Pokemon).

**Known limitation:** Pikalytics hasn't published a ranked-ladder format
code for M-C yet, so usage-stat fetching (`pipeline/fetch_pikalytics.py`)
is still pointed at M-B's format code as a stand-in. Two species that are
new to M-C (Farfetch'd, Sirfetch'd) have no usage data as a result --
everything else works normally. This isn't fixable from this repo; it
just needs Pikalytics' M-C ladder to accumulate enough data for them to
publish a format code, at which point `PIKALYTICS_FORMAT_CODE` should be
updated and `pipeline.refresh_pikalytics_job` re-run.

## Commands

| Command | Does |
|---|---|
| `/ping` | Check that the bot is responsive. |
| `/ask` | Ask a question about VGC Pokemon stats and movesets. |
| `/stats` | Look up a Pokemon's base stats, types, and abilities. |
| `/moves` | Look up a Pokemon's legal moveset. |
| `/calc` | Calculate a damage range for attacker's move vs defender. |
| `/import` | Import a full Pokemon team from Pokepaste text or a pokepast.es URL. |
| `/scout` | Add or update one Pokemon in a stored team with only what you currently know. |
| `/team` | View the Pokemon currently stored for your team or the opponent's team. |
| `/debug-last` | Show the most recent `/ask` call's full retrieval/answer detail (bot owner only). |

`/import`/`/scout`/`/team` feed stored team data into `/calc` and `/ask`, so
those commands can reference "my Landorus" instead of spelling out a full
spread each time.

## Architecture

- **`pipeline/`** — fetches from PokeAPI + Pikalytics, merges into
  `data/processed/pokemon_records.json` + `pikalytics_usage.json`
- **`damage_calc/`** — a Python port of `@smogon/calc`'s damage formula
- **`rag/`** — embeds and retrieves Pokemon data, answers `/ask` via a
  locally-run LLM (Ollama, reached over Tailscale)
- **`bot/`** — the Discord bot itself (`discord.py`), one file per slash
  command under `bot/commands/`
- **`deploy/`** — systemd units + timers and an Oracle Cloud cloud-init
  script for always-on hosting

See `pika-rag-project-plan.md` for the full build-order checklist and
`docs/superpowers/` for design docs behind each shipped feature.

## Setup

```bash
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env   # fill in DISCORD_TOKEN, LLM_HOST (see docs/DEPLOYMENT.md)
.venv/bin/python -m pipeline.refresh_job
.venv/bin/python -m pipeline.refresh_pikalytics_job
.venv/bin/python -m bot.main
```

For always-on deployment (systemd + Oracle Cloud), see `docs/DEPLOYMENT.md`.

## Testing

```bash
pytest -q
```

## Evaluation

`data/eval/golden_set.json` is an auto-generated golden Q&A set (see
`eval/generate_golden_set.py`), used two ways:

- **Retrieval quality (`recall@5`)** runs as a normal test in CI
  (`tests/test_eval_retrieval.py`) — no live LLM involved, just the
  embedding model and Chroma.
- **Answer quality** exercises the full `/ask` path against a live Ollama
  model, on demand (not run in CI, since CI has no Tailscale access to the
  laptop):
  ```bash
  .venv/bin/python -m scripts.run_eval --with-answers
  ```
  Requires `LLM_HOST` (and optionally `LLM_MODEL`/`LLM_TIMEOUT`) in the
  shell environment first, e.g. `set -a; source .env; set +a`.

  Run this after a retrieval/prompt change or a model swap, from a machine
  with tailnet access (the Oracle Cloud instance or a dev machine joined to
  the same tailnet).

Regenerate the golden set after a data refresh with:
```bash
.venv/bin/python -m eval.generate_golden_set
```
Review the diff before committing — this is a deliberate step, not
automatic.
