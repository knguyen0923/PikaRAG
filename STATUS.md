# PikaRAG — Status

Point Claude at this file after `/clear` to pick up where things left off.
This is a snapshot, not a source of truth — always re-verify against the repo
(`git log`, `git status`, `pytest -q`) rather than trusting this blindly if
it's been a while.

**Last updated:** 2026-09-14, at commit `782d33f` (main, pushed to origin).
The local LLM migration (code + deferred-minor follow-ups) is fully merged
and pushed — see "Local LLM migration" section below for what changed and
what's still open (Task 5, hardware setup). 264/264 tests passing. Since
then, this session reviewed and refined the existing
`2026-09-13-eval-harness-design.md` spec against the current codebase: found
and fixed a file-path bug (`vgc_items.json` is at `data/source/`, not
`data/processed/`), filled in an unspecified data source for the
moveset-membership golden-question category (`data/source/vgc_moves.json`),
and corrected/addressed a "no network calls" claim about the recall@k CI
test (it uses the real `SentenceTransformerEmbedder`, unlike every other
test in the suite — added `actions/cache` for the model download). Spec is
committed; **awaiting the user's review before moving to an implementation
plan via `writing-plans`.**
<!-- STATUS_COMMIT: 782d33f -->
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

Deployment is fully done as of 2026-09-12 — bot is live, `/ping` confirmed
working in Discord, and the server is caught up to `main` (`git pull` +
restart done after the cleanup/bug-hunt commits landed). Full detail in
`RESUME.md`.

1. ~~Get a Discord bot token + invite it to a server~~ done
2. ~~Get an Anthropic API key and set a spend cap~~ done ($5 cap, both
   secrets in local `.env`; server's `.env` currently relies on
   `ANTHROPIC_SPEND_CAP_USD`'s `5.0` default rather than setting it
   explicitly -- fine, just worth tidying up eventually)
3. ~~Provision the Oracle Cloud free-tier ARM instance~~ done — recreated
   2026-09-11 (`project-pikarag`, public IP `193.122.155.20`) after the
   first attempt's private-subnet misconfig
4. ~~Server setup: clone repo, venv, `.env`, run both refresh jobs~~ done
5. ~~Install systemd units, verify the bot responds in Discord~~ done —
   `/ping` confirmed working live in Discord on 2026-09-12

## Local LLM migration — code done, hardware setup still open

`2026-09-13-local-llm-migration-design.md`'s Tasks 1-4 are implemented and
merged to `main` (commit `7532f22`, 2026-09-14) — see the "Last updated"
paragraph above for what changed. **Task 5 is not done:** the physical
Windows laptop needs Tailscale + Ollama installed
(`ollama pull llama3.2:3b`), the live Oracle Cloud instance needs
Tailscale installed and `LLM_HOST` set in its `.env`, and `/ask` needs to
be verified end-to-end (including the offline-degradation path) against
real hardware — see `docs/DEPLOYMENT.md`'s "Local LLM (Ollama +
Tailscale)" section (now §3) and the plan's Task 5 checklist. **The live
deployed bot still runs the old paid-Haiku code** until this commit is
pulled and Task 5 is completed on the server.

## Next up (design done, not implemented)

`2026-09-13-eval-harness-design.md` is **up next, spec refined and
committed this session, awaiting the user's go-ahead to turn it into an
implementation plan** (see "Last updated" above for what was fixed).

Five more design specs landed 2026-09-13 in `docs/superpowers/specs/` —
awaiting user review, not yet turned into implementation plans or code:

1. `2026-09-13-retrieval-quality-design.md` — entity-aware retrieval
   filtering, reusing existing `bot/pokemon_lookup.py` name matching.
2. `2026-09-13-grounding-trust-design.md` — source attribution + a
   distance-based confidence gate before the LLM is called.
3. `2026-09-13-observability-design.md` — SQLite log of every `/ask` call +
   an admin `/debug-last` command.
4. `2026-09-13-reliability-design.md` — circuit breaker around Ollama calls
   + an `/llmstatus` health check.
5. `2026-09-13-ingestion-robustness-design.md` — schema + freshness
   validation on pipeline refreshes.

Recommended order after eval harness: the rest in any order. Also still
open: a Discord button-UI request (replacing slash commands with clickable
message components) — raised same session, not yet brainstormed.

Everything below is optional follow-up, none of it blocking:

- **Known limitation (not fixable from this repo):** Pikalytics hasn't
  published a ranked-ladder format code for Regulation M-C yet, so
  `PIKALYTICS_FORMAT_CODE` (`pipeline/fetch_pikalytics.py`) still points at
  M-B's code as a stand-in. Two species new to M-C (Farfetch'd, Sirfetch'd)
  have no usage data as a result -- everything else works normally. Re-check
  once Pikalytics' M-C ladder has accumulated enough data to publish a
  format code, update the constant, then re-run `refresh_pikalytics_job`.
  (Documented in `README.md`'s Status section too.)
- The ToS/Privacy Policy Claude Artifact
  (`https://claude.ai/code/artifact/c8af5a8a-f5ad-420c-8dfe-9d260f6d0ea7`)
  is still private -- only matters if the bot is ever submitted somewhere
  that verifies those URLs (e.g. Discord's public bot verification).
- Confirm Pikalytics scraping is within their ToS (pipeline has been
  running against it, never formally checked).
- `deploy/cloud-init.sh` has a real bug (see memory
  `pikarag-oracle-networking-gotchas`): `useradd -m` populates `/opt/pikarag`
  with skeleton dotfiles before `git clone` runs into it, which fails since
  the directory isn't empty. Only matters on the next from-scratch instance
  recreation -- doesn't affect the currently-running instance.

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
