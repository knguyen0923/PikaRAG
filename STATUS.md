# PikaRAG — Status

Point Claude at this file after `/clear` to pick up where things left off.
This is a snapshot, not a source of truth — always re-verify against the repo
(`git log`, `git status`, `pytest -q`) rather than trusting this blindly if
it's been a while.

**Last updated:** 2026-09-18 (this worktree, branch `ability-held-item-interactions`,
commit `159bc4f`, Task 1/4 complete) — mid-execution of `docs/superpowers/plans/2026-09-18-ability-held-item-interactions.md`
via `subagent-driven-development`, running in parallel with a sibling
worktree (`hybrid-bm25-retrieval`) implementing the other bounded backlog
item. Not yet merged to `main`; `main`'s own STATUS.md is unaffected by
this worktree's commits until merge. See this worktree's
`.superpowers/sdd/2026-09-18-ability-held-item-interactions/progress.md`
for exact task-by-task progress. Everything below this point reflects
`main`'s state as of `b849fcd`/`25e1976` (2026-09-18/2026-09-17), unaffected
by this worktree.

**Immediate next action:** the 7 plans listed in the previous update (all
of `worktree-team-button-ui-plan`'s planning output, none involving the
LLM) have now all been executed and merged into `main`, in dependency
order, with a full-suite test run after every merge:

1. `name-suggestion-dropdown` (Slice A) — shared `NameSuggestionView`
   dropdown for `/stats`, `/moves`, `/calc` name misses. Clean merge.
2. `dex-browse-command` (Slice D) — new `/dex` Prev/Next roster browser
   (built on Slice A). Clean merge. (Finished this session — was left
   uncommitted mid-task from an earlier interrupted run.)
3. `team-button-ui` — `TeamView` with "Your team"/"Opponent's team"
   buttons replacing `/team`'s `side` parameter. Clean merge.
4. `import-confirmation-view-team-link` (Slice C) — Confirm/Cancel
   overwrite prompt + "View team" button on `/import` (built on
   `team-button-ui`'s `TeamView`). Clean merge. (Also finished this
   session from an uncommitted mid-task state.)
5. `damage-calc-abilities` — Choice Scarf + `ability` param threaded
   through `/calc` + 6 ability modifiers. **Conflicted** in `bot/main.py`:
   this plan was written against the old flat `/calc` handler, but Slice A
   had since refactored it into `_run_calc`/`_calc_send` helpers (for the
   suggestion-dropdown retry flow). Resolved by hand-threading
   `attacker_ability`/`defender_ability` through the new helper structure
   instead of picking either side wholesale.
6. `pipeline-error-handling` — network timeouts + error hardening in
   `pipeline/fetch_pokeapi.py` and `pipeline/refresh_job.py`. Clean merge
   (fully independent of the bot/ changes).
7. `stats-moves-tabbed-panel` (Slice B) — shared Stats/Moves/Usage tab
   panel on `/stats` and `/moves`. **Conflicted** in `bot/main.py` for the
   same reason as #5 (written against the pre-Slice-A handler bodies).
   Resolved by attaching `PokemonInfoView` in both the direct-hit and
   suggestion-picked paths — but the first resolution had a real bug
   (unconditionally read `record["name"]` after a miss with no
   suggestions, where `record` is `None`) caught by the test suite
   (`test_stats_command_shows_no_view_when_there_are_no_close_matches`)
   and fixed in a follow-up commit before moving on.

All 7 source `worktree-*` branches are still present locally (some also
pushed to origin) and their `.worktrees/*`/`.claude/worktrees/*` working
copies still exist on disk — neither the branches nor the worktrees have
been cleaned up yet; that's a deliberate pause point, not an oversight.
`main` itself has not been pushed to origin.

Separately, and not blocking any of the above: Task 5 of the local LLM
migration (physical hardware setup) is still open — see "Local LLM
migration" section below for exact in-progress state and the specific
network fix still needed on the Windows laptop.

Also this session: found and fixed (with explicit user sign-off) that
`.claude/settings.json` and `.claude/hooks/` were never tracked in git —
a global `~/.gitignore_global` excludes `.claude/` in every repo on this
machine, so the Stop/PostCompact hooks `.claude/settings.json` declares
had no backing scripts in any of the 7 worktrees created this session,
and the Stop hook failed silently (exit 127) every time it fired there.
Force-added `.claude/settings.json` and `.claude/hooks/*.sh` to this repo
specifically (commit `d90c432`); the global ignore is untouched for every
other project.

## Grounding & trust — shipped

`2026-09-13-grounding-trust-design.md` is implemented and merged (plan
`docs/superpowers/plans/2026-09-14-grounding-trust.md`, 4 tasks):
`build_context_block` returns `{"text","sources","best_distance"}` instead
of a bare string; `ask_response`/`ask_response_async` apply a hard-coded
confidence gate (`DISTANCE_THRESHOLD = 1.4` in `bot/commands/ask.py`,
empirically derived from the real golden set — measured ceiling 1.3565 —
and a real out-of-domain sample, guarded by two regression tests in
`tests/test_eval_retrieval.py`) and always return
`{"answer","sources"}`; `/ask`'s embed now shows a trailing
`Sources: Name (chunk_type), ...` line via a new `format_ask_response`
helper. The final whole-branch review caught a real regression before
merge: the gate ran before the caller's stored-team `extra_context` was
merged in, silently disabling team-strategy `/ask` questions (an
already-shipped feature) — fixed so the gate never fires when
`extra_context` is present. Parked, not fixed: `sources` lists every
retrieved chunk unfiltered by relevance, which can show a misleading
source line for unfocused questions — a real design question for a future
spec revision, not an implementation bug. 329/329 tests passing.

Session summary (2026-09-13 through 2026-09-14): shipped the local LLM
migration (code), the eval harness, entity-aware retrieval quality, and
grounding & trust (all four merged to `main`, all fully tested — see their own sections
below); ran a verification pass that caught and fixed real bugs in all 6
unimplemented 2026-09-13 design specs (wrong file paths, a false "caught
by tests" safety claim, a circuit breaker with nothing to catch, an
unstated cross-spec dependency, a debunked motivating claim — full detail
preserved in git history, `git log --oneline --grep=eval-harness` and
`--grep="design specs"` for the commits); then used the eval harness
itself to find two real retrieval-quality bugs and fixed them via
entity-aware retrieval, and grounding & trust (see below). 329/329 tests
passing throughout.
<!-- STATUS_COMMIT: 159bc4f -->
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

**Task 5 progress as of 2026-09-14 evening (in progress, not done):**
- Laptop (Windows, Dell Inspiron 14 7435 2-in-1, no dedicated GPU): Ollama
  installed, `llama3.2:latest` (3.2B, Q4_K_M) and `nomic-embed-text`
  pulled, confirmed reachable from the laptop itself
  (`curl localhost:11434/api/tags` returned both models). Tailscale
  installed and connected; laptop's Tailscale IP is `100.111.225.17`.
- Oracle instance (`193.122.155.20`): `git pull`'d to current `main`
  (commit `7532f22`+), `.env` updated with `LLM_HOST=100.111.225.17:11434`
  and `LLM_MODEL=llama3.2:3b`, stale unused `ANTHROPIC_API_KEY` removed
  from `.env`. Tailscale installed and connected (was missing entirely
  before this session — not previously done despite the DEPLOYMENT.md
  checklist implying it). Bot service restarted successfully on the new
  config, connects to Discord fine, `/ping` works.
- **Blocking issue found:** `curl http://100.111.225.17:11434/api/tags`
  from the Oracle box hangs/times out even though both machines show
  connected on the same Tailscale network. Root cause not yet confirmed
  but two likely culprits (not yet verified fixed): (1) Ollama by default
  only binds to `127.0.0.1`, refusing any non-local connection regardless
  of network reachability — fix is setting the `OLLAMA_HOST=0.0.0.0:11434`
  environment variable on the Windows laptop and restarting Ollama; (2)
  Windows Firewall likely blocking inbound TCP 11434 — fix is
  `New-NetFirewallRule -DisplayName "Ollama" -Direction Inbound -Protocol
  TCP -LocalPort 11434 -Action Allow` in an elevated PowerShell. Neither
  fix has been applied/verified yet as of this write.
- **Separate unresolved oddity:** before the Tailscale-on-Oracle gap was
  found, `/ask` in Discord returned "the application did not respond" /
  "something went wrong" with **zero corresponding lines** in
  `journalctl -u pikarag-bot.service -f` — not even the traceback
  `OllamaAnswerer`'s error handling or discord.py's default
  `app_commands` error logger should normally produce. Only one bot
  process was confirmed running (`ps aux`), ruling out a duplicate-token
  conflict. This may simply resolve itself once the network path above is
  fixed (the offline-degradation fallback path has direct test coverage
  in `tests/test_rag_answer.py` and should be reliable) — but if `/ask`
  still fails silently after both network fixes above, this needs its own
  investigation via `systematic-debugging`, not more ad hoc log-watching.
- **Also worth doing:** the Discord bot token was inadvertently printed in
  plaintext during a terminal session pasted into chat this session —
  should be rotated (Discord Developer Portal -> application -> Bot ->
  Reset Token) and the new value updated in the Oracle `.env`, independent
  of the LLM work above.
- **Next step on resume:** apply both Ollama fixes on the Windows laptop
  (env var + firewall rule), re-run the `curl` check from the Oracle box,
  then retry `/ask` in Discord with `journalctl -f` open to confirm it
  actually reaches the model and answers end-to-end (including the
  offline-degradation path, per the plan's Task 5 checklist).

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

## Retrieval quality — shipped

`2026-09-13-retrieval-quality-design.md` is implemented and merged
(plan `docs/superpowers/plans/2026-09-14-retrieval-quality.md`, 6 tasks via
`subagent-driven-development`, commits `0e322bb..7ec5b05`): `/ask` now
detects a known Pokemon/item name in the question (`rag/entity.py`'s
`detect_entity` — exact + fuzzy/typo matching, Mega/regional-form
tie-breaking) and constrains the Chroma query to that entity's own chunks
(`ChromaIndex.query`'s new `where` param) — falling back to the old
unfiltered search whenever no entity is detected, detection is ambiguous,
or the filtered query comes back empty.

This fixed the two eval-harness-measured misses it was built for
(`Abomasnow-moveset-learned-question`, `Dragalge-moveset-not-learned-question`
— both previously lost to their own Mega Stone item chunk + stats chunk,
per the root-cause writeup this section used to carry, now superseded).
The final whole-branch review caught 3 real Critical bugs before merge — a
crash on real questions naming a letter-suffixed Mega form (e.g. "Mega
Charizard"), a measured recall@5 regression (0.9583→0.8958) from the
Pokemon vocabulary's fuzzy match being tried before the item vocabulary's
exact match, and genuine Pokemon-name ambiguity silently leaking into a
wrong item binding instead of falling back — all three fixed in one
coordinated rewrite (`detect_entity` now tries an exact match across both
vocabularies before any fuzzy match, and uses a distinct ambiguous-sentinel
that short-circuits to the unfiltered fallback). Final measured recall@5
through the entity-aware path: **1.0000 (48/48)**, up from the 0.9583
pre-change baseline. 315/315 tests passing.

Two narrow limitations were deliberately parked, not fixed (full rulings
in the session's git history / conversation record): (1) a
Mega-letter-variant question (e.g. "Mega Charizard X") and the real nested
`Tauros [Paldean Form (... Breed)]` family can't be disambiguated with full
precision — both fall back to a safe default/unfiltered result rather than
crashing or answering wrong, matching the spec's own stated tolerance for
this class of imprecision; (2) a qualifier word (e.g. "Mega") is matched
anywhere in the question rather than adjacent to the species it modifies,
so an adversarial phrasing naming an unrelated move that happens to share
a word with a variant qualifier (e.g. "Does Abomasnow learn Mega Kick?")
can still misfire. Neither is in the golden set or believed to affect
typical `/ask` usage; worth revisiting only if real usage surfaces it.

## Observability — shipped

`2026-09-13-observability-design.md` is implemented and merged (plan
`docs/superpowers/plans/2026-09-14-observability.md`, 4 tasks via
`subagent-driven-development`, commits `c1e4e30..6550405`): every `/ask`
call is now logged to a local SQLite database (`data/observability.db`,
gitignored) via a new `rag/observability.py` module (`log_ask`/
`get_last_ask_log`, stdlib `sqlite3`/`json` only, no new dependencies) —
question, per-chunk retrieved-chunk ids + distances, sources, best
distance, `gate_fired`/`degraded` (both derived by string-sentinel
comparison against `GATE_MESSAGE`/`OFFLINE_MESSAGE`, the one place each is
derived), the answer, and `latency_ms` spanning the whole
`ask_response_async` call. A new owner-only `/debug-last` command
(`bot/commands/debug.py`'s pure `format_debug_last`, wired into
`bot/main.py`) shows the most recent call's full detail, gated by a
`BOT_OWNER_ID` env var via an `app_commands.check` predicate (this bot uses
a bare `discord.Client` + separate `CommandTree`, so `is_owner()` isn't
available) that fails closed on both an unset *and* a malformed
`BOT_OWNER_ID` — the malformed case was a real bug caught in Task 4's own
review loop and fixed before task completion.

The final whole-branch review caught 3 real Important bugs only visible
once all 4 tasks' changes sat together: (1) three pre-existing `/ask`
handler tests didn't isolate the real `log_ask` call, so running the test
suite on the deploy box would have written fixture rows into the live
`data/observability.db` and poisoned `/debug-last`'s output with test data
instead of the real most recent call — fixed via an autouse `tests/conftest.py`
fixture that patches `log_ask`'s/`get_last_ask_log`'s `db_path` default
(Python binds a default-argument value at function-definition time, so a
naive monkeypatch of the module-level constant alone would have been a
silent no-op — the fixture patches `__defaults__` directly, verified by
running the full suite twice and confirming no DB file appears); (2)
`/debug-last`'s output had no length cap and could exceed Discord's
4096-char embed limit on a long question/answer, hard-failing exactly when
the operator needs the debug view most — fixed with truncation; (3)
`/debug-last` replied non-ephemerally, publicly re-broadcasting another
user's `/ask` question/answer/chunk-ids to the whole channel — fixed with
`ephemeral=True`. All three fixed in one coordinated pass, plus 2 new
handler-level tests proving `gate_fired`/`degraded` actually evaluate
`True` (previously only the `False`/normal path was covered at that
layer). 352/352 tests passing.

## Reliability — shipped

`2026-09-13-reliability-design.md` is implemented and merged (plan
`docs/superpowers/plans/2026-09-15-reliability.md`, 4 tasks via
`subagent-driven-development`, commits `b227395..74a6820`): a
`rag/circuit_breaker.py` `CircuitBreaker` wraps the LLM answerer and
detects failure the same way the rest of the codebase does — by comparing
the return value against `OFFLINE_MESSAGE`, never by catching an exception
(`OllamaAnswerer.answer` already never raises). After 3 consecutive
failures it opens for a 60-second cooldown, short-circuiting further
`/ask` calls immediately instead of each paying a full 30-second network
timeout against a laptop that's known to be down; after the cooldown, the
next call probes for real (half-open), closing the breaker on success or
reopening it on failure. A new owner-only `/llmstatus` command (gated by
the same `BOT_OWNER_ID`/`_owner_only` mechanism as `/debug-last`) reports
LLM reachability via a new short-timeout `OllamaAnswerer.check_health()`
liveness probe against `/api/tags`, the configured vs. loaded model, and
the breaker's live state. The final whole-branch review caught 2 real
Important bugs only visible once all 4 tasks sat together: `/llmstatus`
didn't defer its interaction before the 3-second-timeout health check,
and Discord's own ACK deadline is also 3 seconds — so in the exact
"laptop asleep, not actively refusing" outage scenario the command exists
to diagnose, it could time out and show Discord's generic failure instead
of the intended offline report (fixed with `defer()`/`followup.send()`,
mirroring `/ask`'s existing pattern); and `/llmstatus` was undocumented in
`README.md` plus `docs/DEPLOYMENT.md` had drifted out of sync with
`.env.example` (fixed). 376/376 tests passing.

## Ingestion robustness — shipped

`2026-09-13-ingestion-robustness-design.md` is implemented and merged
(plan `docs/superpowers/plans/2026-09-15-ingestion-robustness.md`, 4 tasks
via `subagent-driven-development`, commits `8f304f9..71da1a9`).
`pipeline/validate.py` (schema/count checks, all plain assertions, no new
dependency) and `pipeline/freshness.py` (per-job last-successful-refresh
timestamps, 14-day/60-day independent thresholds) are wired into both
`pipeline/refresh_job.py` and `pipeline/refresh_pikalytics_job.py` via a
validate-before-swap step: each job now builds its output in memory,
validates it, and only writes it live (temp file + atomic `os.replace`) if
there are no hard failures — otherwise the previous live data is left
completely untouched. The task loop itself caught and fixed a real
test-pollution bug twice (tests silently writing real timestamp files into
the live `data/processed/` directory) before either job's task review.

The final whole-branch review caught something more serious: the new
empty-learnset schema check, run against this repo's own real committed
data, permanently rejected 5 legitimate Mega-form records (PokeAPI has no
learnset data for them) — in production this would have silently stalled
the weekly PokeAPI refresh forever, and *because* a failed validation never
records a success timestamp, the freshness check (missing timestamp =
"unknown," not "stale") could never have reported the stall either. Fixed:
the empty-learnset check is now a tolerance/percentage check (5%, mirroring
the already-established `validate_legal_count` pattern) instead of failing
on any single record, plus a new regression test
(`test_validate_records_accepts_the_repos_own_committed_data`) that runs
the real `data/source`/`data/raw` through the validators and asserts zero
problems, so this exact class of bug can't recur silently — confirmed
directly against the merged `main` (345 records, 5 known empty-learnset
Mega forms, 0 problems). Also fixed in the same pass:
`refresh_pikalytics_job.py`'s `stale_format_code` guard used to fire
*after* a stale run had already swapped in an empty `{}` and recorded
itself as a successful refresh — now folded into the validate-before-swap
gate so it actually blocks the swap and the timestamp write. Two
deliberately-documented-not-fixed gaps: `validate_usage`'s referential
check is structurally unreachable in production (the fetch function only
ever inserts keys drawn from the same list it's checked against) and
`validate_items` is implemented/tested but has no refresh job to be called
from (`vgc_items.json` is static source data) — both now carry an explicit
code comment explaining why, rather than silently implying protection that
isn't there. 407/407 tests passing.

## Discord button UI — shipped

`2026-09-15-team-button-ui-design.md` (Phase 1 of the long-open "Discord
button-UI request" backlog item) plus the follow-on
`2026-09-15-poketwo-style-ui-design.md` spec's 4 slices are all
implemented and merged to `main` — see the "Immediate next action"
section above for the full list of 7 plans, merge order, and how the 2
real merge conflicts were resolved.

Original Phase 1 scope (`/team` button-UI plan): `/team` gains two
buttons ("Your team" / "Opponent's team") replacing its current `side`
slash-command parameter, re-rendering the same message in place via a new
`TeamView` class, restricted to whoever ran `/team` (a
`discord.ui.View.interaction_check` sending its own ephemeral rejection —
note this does NOT route through `bot/main.py`'s existing
`@tree.error`/`CheckFailure` handler, since View checks are a separate
mechanism from `app_commands.check`). All existing pure functions
(`view_team_response`, `format_team_block`) are reused unchanged.

## Housekeeping — resolved (2026-09-15)

All of the previously-listed low-priority follow-up items are now closed
except the one genuinely external one (Pikalytics' missing M-C format
code, still below):

- `deploy/cloud-init.sh`'s `useradd -m` / `git clone` ordering bug (see
  memory `pikarag-oracle-networking-gotchas`) is fixed: switched to
  `useradd -M` (skip `/etc/skel` population) plus an explicit
  `mkdir`+`chown` before the clone, so `$APP_DIR` is empty when `git
  clone` runs into it. The same bug existed in `docs/DEPLOYMENT.md`'s
  manual runbook (section 2) and got the identical fix there.
- Confirmed Pikalytics scraping is fine: `robots.txt` explicitly allows
  `/ai/` (the exact path `pipeline/fetch_pikalytics.py` hits) for AI/bot
  user-agents including `ClaudeBot`/`anthropic-ai`, no crawl-delay is set,
  and their Privacy Policy (the only legal doc they publish -- no separate
  ToS exists) has no scraping/rate-limit/reuse restriction.
- 3 parked minors from the observability final review, closed: a non-owner
  running `/debug-last` now gets a friendly ephemeral "no permission"
  message instead of being logged as an "Unhandled error" and shown the
  generic public error embed (`bot/main.py`'s `on_tree_error` gained a
  `CheckFailure` branch); `/debug-last`'s `sources`/`retrieved_chunks` text
  is now truncated the same way `question`/`answer` already were, closing
  the embed-overflow risk for a future larger `n_results` or longer source
  names; `README.md`'s Commands table and `docs/DEPLOYMENT.md` now document
  `/debug-last` and `BOT_OWNER_ID`. 354/354 tests passing.

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

## Improvement backlog (2026-09-16, brainstormed 2026-09-17)

`IMPROVEMENTS.md` — a prioritized portfolio-review backlog. Status as of
2026-09-17: everything except local-LLM Task 5 has been brainstormed via
`superpowers:brainstorming` (see `IMPROVEMENTS.md` for full detail per item).

- **Rotate leaked Discord bot token** — still not done, deliberately deferred
  by the user. Do this regardless of implementation order on the rest.
- **Pinned-deps CI check — implemented and committed** (`25e1976`):
  `scripts/check_pinned_deps.py` +
  `.github/workflows/test.yml` step + documented pins in `requirements.txt` +
  `tests/test_check_pinned_deps.py`. 517/517 tests passing.
- **Hybrid BM25+vector retrieval** and **ability/held-item interactions** —
  bounded designs approved in chat, not yet implemented (no spec files by
  design — bounded path).
- **Fine-tune vs. RAG comparison** and **agentic `/ask`+`/calc` tool-calling
  loop** — architectural specs written:
  `docs/superpowers/specs/2026-09-17-finetune-vs-rag-design.md` and
  `docs/superpowers/specs/2026-09-17-agentic-tool-calling-design.md`. Next
  step for either is `writing-plans`, not direct implementation.

## Useful pointers

- `IMPROVEMENTS.md` — prioritized improvement backlog (portfolio review)
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
