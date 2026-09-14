# PikaRAG — Status

Point Claude at this file after `/clear` to pick up where things left off.
This is a snapshot, not a source of truth — always re-verify against the repo
(`git log`, `git status`, `pytest -q`) rather than trusting this blindly if
it's been a while.

**Last updated:** 2026-09-14, at commit `3d3991e` (main, not yet pushed).

**Immediate next action:** run `writing-plans` on
`docs/superpowers/specs/2026-09-13-retrieval-quality-design.md`, then
execute via `subagent-driven-development` (same pattern as the local LLM
migration and eval harness). The spec is reviewed, fixed, and now carries
measured real-world evidence (see "Retrieval quality — spec ready, real
evidence in hand" below) — no further brainstorming needed, just go
straight to a plan. This is genuinely the next unblocked step; nothing
else needs a decision first.

Session summary (2026-09-13 through 2026-09-14): shipped the local LLM
migration (code) and the eval harness (both merged to `main`, both fully
tested — see their own sections below); ran a verification pass that
caught and fixed real bugs in all 6 unimplemented 2026-09-13 design
specs (wrong file paths, a false "caught by tests" safety claim, a
circuit breaker with nothing to catch, an unstated cross-spec
dependency, a debunked motivating claim — full detail preserved in git
history, `git log --oneline --grep=eval-harness` and
`--grep="design specs"` for the commits); then used the eval harness
itself to find two real retrieval-quality bugs (see below) and traced
them to root cause. 292/292 tests passing throughout.
<!-- STATUS_COMMIT: 3d3991e -->
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
merged to `main` (commit `7532f22`, 2026-09-14): `/ask` calls a new
`OllamaAnswerer` (`rag/answer.py`) over HTTP to a local Ollama server
instead of paid Claude Haiku; `HaikuAnswerer`/`rag/spend_tracker.py`/the
`anthropic` dependency are deleted entirely, no paid fallback path
anywhere. The final review for that plan caught a real bug: `/ask` never
deferred its Discord interaction, so under CPU-bound Ollama inference both
the normal answer and the offline-degradation message would have missed
Discord's 3-second ack window — fixed (`interaction.response.defer()` +
`followup.send()`). **Task 5 is not done:** the physical Windows laptop
needs Tailscale + Ollama installed (`ollama pull llama3.2:3b`), the live
Oracle Cloud instance needs Tailscale installed and `LLM_HOST` set in its
`.env`, and `/ask` needs to be verified end-to-end (including the
offline-degradation path) against real hardware — see
`docs/DEPLOYMENT.md`'s "Local LLM (Ollama + Tailscale)" section (now §3)
and the plan's Task 5 checklist. **The live deployed bot still runs the
old paid-Haiku code** until this commit is pulled and Task 5 is completed
on the server.

## Eval harness — shipped, one real bug caught and fixed

`2026-09-14-eval-harness.md`'s all 8 tasks are implemented and merged
(commit `6d021d5`). `eval/generate_golden_set.py` builds a 48-entry golden
Q&A set from real Pokemon/item/move data (`data/eval/golden_set.json`,
committed to the repo, not gitignored); `tests/test_eval_retrieval.py`
gates `recall@5 >= 0.9` in CI against the real embedder/index — measured
0.9583 (46/48); `scripts.run_eval --with-answers` exercises the full
`/ask` path against a live Ollama model on demand, never gated in CI (no
Tailscale access there). The final whole-branch review caught a real
production-safety bug: `scripts.run_eval` would have written into the
bot's *live* persistent Chroma store (the same collection `/ask` serves
from) — fixed with a backward-compatible `client=` parameter on
`bot.main._build_real_index`, with the eval script now using an in-memory
client. 292/292 tests passing. Deferred, non-blocking: all six
"No"-answer moveset questions test the same move (low signal diversity,
not wrong); golden-set size floor isn't enforced at generation time, only
in a unit test. The two real retrieval misses this harness found are
being acted on now — see next section.

## Retrieval quality — spec ready, real evidence in hand, next to implement

`2026-09-13-retrieval-quality-design.md` proposes entity-aware retrieval:
detect a Pokemon/item name in the question, then constrain the Chroma
query to that entity's own chunks (`where={"pokemon": "Abomasnow"}`)
instead of searching the whole 542-chunk corpus.

This isn't speculative — the eval harness (`data/eval/golden_set.json`)
measured a concrete failure it fixes. Two golden questions
(`Abomasnow-moveset-learned-question`, `Dragalge-moveset-not-learned-question`)
miss their target `-moveset` chunk in the top 5 entirely. Root cause,
confirmed by querying the real index directly: every sampled Pokemon that
also has a Mega Stone item (Abomasnow, Dragalge, Kangaskhan, Medicham)
ranks that item's chunk and the Pokemon's `-stats` chunk *above* its own
`-moveset` chunk, every single time, regardless of the question —
`all-MiniLM-L6-v2`'s mean-pooled embedding favors a short sentence
repeating the exact Pokemon name over the long, diluted move-list text.
Kangaskhan/Medicham happened to still squeak into rank 4-5; Abomasnow/
Dragalge landed at rank 6+. Confirmed (by tracing the design, not
guessing) that entity-aware filtering eliminates this outright: a
Pokemon-scoped query only has that Pokemon's own 2 chunks to rank
between, and the Mega Stone's chunk carries `metadata={"item": ...}` —
no `"pokemon"` key at all — so it's excluded from a filtered query
entirely, not just outranked. Full writeup in the spec's Purpose section
(commit `3d3991e`).

**Next action:** `writing-plans` on this spec, then
`subagent-driven-development` to implement — no more design discussion
needed, the spec already reflects this evidence and was reviewed/fixed
earlier this session (see git history for that pass).

## Next up after that (4 more designs, not implemented)

4 more verified-and-fixed design specs from the 2026-09-13 brainstorm have
no implementation plans yet, but are believed implementation-ready:

1. `2026-09-13-grounding-trust-design.md` — source attribution + a
   distance-based confidence gate before the LLM is called.
2. `2026-09-13-observability-design.md` — SQLite log of every `/ask` call +
   an admin `/debug-last` command. **Depends on grounding-trust landing
   first** (needs its `sources`/`best_distance`/`gate_fired` fields).
3. `2026-09-13-reliability-design.md` — circuit breaker around Ollama calls
   (via string-match against `OFFLINE_MESSAGE`, not exceptions) + an
   admin-only `/llmstatus` health check.
4. `2026-09-13-ingestion-robustness-design.md` — schema + freshness
   validation on pipeline refreshes, rescoped to drop a justification that
   didn't hold up (see git history).

Suggested order: retrieval-quality (spec ready, see above) first, then
grounding-trust before observability specifically (the one real
dependency), reliability and ingestion-robustness anytime, independent of
everything else.

Also still open: a Discord button-UI request (replacing slash commands
with clickable message components) — raised early in the 2026-09-13
session, not yet brainstormed at all.

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
