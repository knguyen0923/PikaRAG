# PikaRAG — Status

Point Claude at this file after `/clear` to pick up where things left off.
This is a snapshot, not a source of truth — always re-verify against the repo
(`git log`, `git status`, `pytest -q`) rather than trusting this blindly if
it's been a while.

**Last updated:** 2026-09-11, at commit `e543231` (main). Bot deployed and
live this session (see `RESUME.md` for that detail); afterward, a project
cleanup + code-review pass landed 5 more commits: README/`.gitignore`
polish, a new spend-tracking feature for `/ask`, five real bug fixes in
`/calc` (nature/tera/EV/HP-percent validation), a team-import parsing fix
(`Hidden Power:` lines), and a correctness fix to the core damage formula
(terrain + item/screen modifier chaining, verified against Bulbapedia).
262/262 tests passing.
<!-- STATUS_COMMIT: e543231 -->
<!-- This HTML comment is machine-read by a Stop hook (.claude/settings.json)
     that nags to refresh this file whenever HEAD moves past this hash.
     Update it to the current `git rev-parse --short HEAD` every time you
     update this file. -->

If `RESUME.md` says anything other than "nothing in progress," read it first —
it holds exact in-flight state from a session that paused mid-task (token
budget or compaction), which is more specific than this snapshot.

---

## Where things stand

All planned code work is done and merged to `main`. 262/262 tests passing.
Data is current for **Regulation M-C** (315 -> 345 legal Pokemon, live since
2026-09-08) -- see the `data:`/`fix:`/`feat:` commits from 2026-09-10.
`vgc_items.json` (197 items, now complete against everything `damage_calc`
supports) is wired into `/ask` (RAG) and validated in `/calc`/`/scout`/`/import`.

- **Data pipeline** (`pipeline/`) — PokéAPI + Pikalytics fetch, merge into
  `data/processed/pokemon_records.json` + `pikalytics_usage.json`
- **Damage calculator** (`damage_calc/`) — ported `@smogon/calc` logic
- **RAG core** (`rag/`) — embed, store, retrieve, Haiku-backed `/ask`
- **Bot commands** (`bot/commands/`, wired in `bot/main.py`) — `/ping`,
  `/ask`, `/stats`, `/moves`, `/calc`, `/import`, `/scout`, `/team`
  (Pokepaste team memory, feeds stored teams into `/calc` and `/ask`)
- **CI** — `.github/workflows/test.yml` runs pytest
- **Deploy scaffolding** — systemd units + timers + Oracle Cloud runbook in
  `docs/DEPLOYMENT.md`, `deploy/`

Full checklist with what's resolved vs. open: `pika-rag-project-plan.md`
("Build Order" and "Open Items" sections).

## What's actually left

Deployment is effectively done as of 2026-09-11 — full detail in `RESUME.md`.

1. ~~Get a Discord bot token + invite it to a server~~ done
2. ~~Get an Anthropic API key and set a spend cap~~ done ($5 cap, both
   secrets in local `.env`)
3. ~~Provision the Oracle Cloud free-tier ARM instance~~ done — recreated
   2026-09-11 (`project-pikarag`, public IP `193.122.155.20`) after the
   first attempt's private-subnet misconfig
4. ~~Server setup: clone repo, venv, `.env`, run both refresh jobs~~ done
5. ~~Install systemd units, verify the bot responds in Discord~~ units
   installed and running, bot connected to Discord's gateway
   `2026-09-12 00:48:02 UTC` — **just waiting on Discord's global
   slash-command propagation (up to ~1hr) before `/ping` will respond**

**The deployed instance is now behind `main` by 5 commits** (docs polish,
spend-tracker feature, `/calc` validation fixes, pokepaste fix, damage
formula fix) plus the earlier `torch==2.6.0` pin. To pick these up on the
server: `git pull` in `/opt/pikarag`, then `sudo systemctl restart
pikarag-bot.service`. The spend-tracker feature also needs
`ANTHROPIC_SPEND_CAP_USD=5.0` (or your real cap) added to the server's
`/opt/pikarag/.env` — it defaults to `5.0` if missing, so this isn't urgent,
just worth setting explicitly to match whatever the real Console cap is.

Also pending: the ToS/Privacy Policy Claude Artifact
(`https://claude.ai/code/artifact/c8af5a8a-f5ad-420c-8dfe-9d260f6d0ea7`) needs
its share menu flipped to public before anything tries to fetch those URLs.

Also unresolved, lower priority: confirm Pikalytics scraping is within their
ToS (pipeline has been running against it, never formally checked).

Also pending, from the 2026-09-10 M-C rollout:
- `PIKALYTICS_FORMAT_CODE` (`pipeline/fetch_pikalytics.py`) still points at
  M-B's code -- no M-C ranked format code exists on Pikalytics yet. Re-verify
  once their ladder data accumulates, then run `refresh_pikalytics_job`.
- The real Chroma index (`data/chroma/`) needs the bot to actually restart
  once to pick up the new item chunks -- `build()` upserts in place, so this
  is automatic on next startup, not a manual step.

## Useful pointers

- `pika-rag-project-plan.md` — architecture, scope, build-order checklist
- `docs/DEPLOYMENT.md` — step-by-step deploy runbook (start here for next work)
- `docs/superpowers/plans/` and `docs/superpowers/specs/` — design docs and
  implementation plans for each shipped feature (data pipeline + damage calc,
  Pikalytics usage data, Pokepaste team memory)

## How to re-orient fast

```bash
git log --oneline -10        # what shipped most recently
git status                   # anything in flight
pytest -q                    # confirm the suite still passes
```
