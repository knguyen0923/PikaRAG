# PikaRAG

A Discord bot for Pokemon VGC (Champions ranked doubles). It combines a
RAG pipeline over PokeAPI + Pikalytics usage data with a ported damage
calculator, so players can look up sets, check usage trends, calculate
damage, and manage a team roster without leaving Discord.

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

`/import`/`/scout`/`/team` feed stored team data into `/calc` and `/ask`, so
those commands can reference "my Landorus" instead of spelling out a full
spread each time.

## Architecture

- **`pipeline/`** — fetches from PokeAPI + Pikalytics, merges into
  `data/processed/pokemon_records.json` + `pikalytics_usage.json`
- **`damage_calc/`** — a Python port of `@smogon/calc`'s damage formula
- **`rag/`** — embeds and retrieves Pokemon data, answers `/ask` via Claude
  (Haiku)
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
cp .env.example .env   # fill in DISCORD_TOKEN and ANTHROPIC_API_KEY
.venv/bin/python -m pipeline.refresh_job
.venv/bin/python -m pipeline.refresh_pikalytics_job
.venv/bin/python -m bot.main
```

For always-on deployment (systemd + Oracle Cloud), see `docs/DEPLOYMENT.md`.

## Testing

```bash
pytest -q
```
