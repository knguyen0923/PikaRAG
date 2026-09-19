# PikaRAG — Resume Point

Written when a session pauses mid-task (approaching the context-usage limit,
or right before a compaction) so work can pick back up without losing the
thread. If this says "nothing in progress," there's no live handoff — just
use `STATUS.md`.

**Paused at:** mid-session, working through a 9-item prioritized brainstorm
backlog the user approved in full ("Do all of them, prioritized"). Token
budget ran low mid-way through item 3 of 9. Safe to resume any time — no
destructive state, everything below is either committed or cleanly
uncommitted-but-described.

## The 9-item backlog (in the order approved)

1. **Stored team persistence** (P1) — DONE, committed, not yet merged.
2. **`/ask` input length cap** (P1) — DONE, committed, not yet merged.
3. **CI lint step (ruff)** (P2) — IN PROGRESS, uncommitted. See below.
4. **Coverage tooling (pytest-cov)** (P2) — NOT STARTED.
5. **Fine-tune vs. RAG comparison** (P2) — NOT STARTED. Spec already exists
   and was re-confirmed with the user: `docs/superpowers/specs/2026-09-17-finetune-vs-rag-design.md`.
   Next step: `writing-plans` skill, then `subagent-driven-development`
   (matches every other plan's execution pattern this session).
6. **`observability.db` retention/prune** (P3) — NOT STARTED.
7. **`/stats-summary` command** (P3) — NOT STARTED.
8. **Agentic `/ask`+`/calc` tool-calling loop** (P3) — NOT STARTED. Spec
   already exists and was re-confirmed: `docs/superpowers/specs/2026-09-17-agentic-tool-calling-design.md`.
   Sequenced after item 1 (team persistence) since `get_stored_team` is more
   useful once teams survive a restart — item 1 is now done, so this is
   unblocked. Same `writing-plans` → `subagent-driven-development` path as 5.
9. **TAKEAWAYS.md staleness fix** (P4) — NOT STARTED. Trivial: two "future
   work" bullets (ability/item interactions, pinned-deps CI check) are
   already done and need to be updated/removed.

Full context on *why* these 9 items, plus 2 already-open pre-existing
backlog items not part of this batch (local-LLM Task 5 hardware networking,
rotating the leaked Discord token — both P1, both untouched, both
independent of this batch): see the conversation history / `IMPROVEMENTS.md`.

## Item 1 & 2 — done, sitting in an unmerged worktree

**Worktree:** `.worktrees/team-persistence-and-ask-hardening`
**Branch:** `team-persistence-and-ask-hardening`
**Commits:** `87c75a6` (team persistence → SQLite, mirrors `rag/observability.py`'s
pattern exactly, including the `__defaults__`-patching test-isolation trick
in `tests/conftest.py`), `913531f` (`/ask` 500-char length cap in
`bot/commands/ask.py`, new `MAX_QUESTION_LENGTH` constant).
**Status:** 564/564 tests passing in this worktree. The `code-review`
subagent finished (result arrived just as this pause was being written) with
3 findings, **none Critical/blocking, none yet triaged or fixed**:

1. `tests/conftest.py:199` (Minor/Important?) — the `_isolate_team_store`
   fixture manually enumerates all 5 public `bot.team_store` functions to
   patch `__defaults__` on each; a future function added to that module
   following the same `db_path: str = DEFAULT_DB_PATH` pattern but omitted
   from this list would silently read/write the real `data/team_store.db`
   during tests. Suggested deeper fix: resolve `db_path` lazily inside each
   function body against the module attribute, or centralize through one
   patchable connection factory, instead of a manually-synced tuple.
2. `bot/team_store.py:22` (worth a judgment call, not obviously wrong) —
   every team_store call now does synchronous SQLite I/O directly on
   Discord's asyncio event loop, unlike `bot/main.py`'s other blocking calls
   which get `asyncio.to_thread`-wrapped. Reviewer notes `rag/observability.py`'s
   `log_ask` already has this same unwrapped pattern, so this is extending
   an existing convention, not introducing a new risk — flagged as worth
   confirming intent on rather than an automatic must-fix, given this bot's
   traffic is low.
3. `bot/team_store.py:22` (Minor) — the `_connect`/`_CREATE_TABLE_SQL`/
   `DEFAULT_DB_PATH` boilerplate is copy-pasted verbatim from
   `rag/observability.py` rather than extracted into a shared helper.

**Next step for this worktree on resume:** decide whether to fix any of
these (none are blocking — could reasonably ship as-is and park the rest,
same adjudication pattern used throughout this session's SDD plan reviews),
then proceed to the same merge flow used for the two SDD plans earlier this
session (switch to main, `git merge team-persistence-and-ask-hardening --no-edit`,
run full suite, resolve any STATUS.md conflict by hand — same pattern as
the `hybrid-bm25-retrieval` merge — then `git worktree remove` + `git branch -d`).

## Item 3 — in progress, uncommitted

**Worktree:** `.worktrees/ci-quality-tooling`
**Branch:** `ci-quality-tooling`
**Done so far (uncommitted):**
- Installed `ruff` (0.16.8) and `pytest-cov` locally in the shared `.venv`
  (both installed via pip, NOT yet added to `requirements.txt` — that's
  still needed).
- Discovered ruff's true no-config default rule set on this version is
  very broad (111 violations across the repo, mostly `UP045`
  pyupgrade-style `Optional[X]` → `X | None` churn that would be unrelated
  scope creep). Decided to pin an explicit, minimal ruleset instead of
  relying on ruff's shifting defaults: `E4,E7,E9,F` (pyflakes + core
  pycodestyle — the classic flake8-equivalent baseline). Under that
  selection, real violations were 16, now fixed.
- Fixed all 16 real violations (mechanical import-organization only, no
  logic changes): moved scattered mid-file imports to the top of
  `pipeline/fetch_pokeapi.py` (4 instances), `tests/test_bot_dex.py`,
  `tests/test_bot_pokemon_info.py`, `tests/test_eval_retrieval.py`,
  `tests/test_rag_retrieve.py`, `tests/test_fetch_pokeapi.py`; ruff
  `--fix` auto-fixed 1 unused import (`tests/test_pokemon_lookup.py`) and
  1 F811 redefinition (`tests/test_rag_retrieve.py`).
- Verified: `ruff check . --select E4,E7,E9,F` → "All checks passed!"
- Verified: full suite still 560/560 passing after the import reorg.

**Next steps (not yet done):**
1. Add a `pyproject.toml` (doesn't exist yet) with:
   ```toml
   [tool.ruff.lint]
   select = ["E4", "E7", "E9", "F"]
   ```
   so the ruleset is pinned/reproducible regardless of ruff version drift,
   not relying on CLI flags in CI.
2. Pin `ruff==0.16.8` in `requirements.txt` with the project's established
   pinned-deps comment convention (see `scripts/check_pinned_deps.py` — every
   `==` pin needs a preceding explanatory comment, and `tests/test_check_pinned_deps.py`
   enforces this in CI).
3. Add a new step to `.github/workflows/test.yml` running `ruff check .`
   (after the existing pinned-deps check step, before `pip install`, or
   wherever fits — look at the existing step order).
4. Commit this as item 3 (e.g. `feat: add ruff lint step to CI`).
5. **Then item 4** (not started): pin `pytest-cov` in `requirements.txt`
   the same way, wire `--cov` into the CI `pytest` invocation in
   `.github/workflows/test.yml`, decide whether to set a coverage floor or
   just report it, run locally to sanity-check the report looks reasonable,
   commit.
6. Run full suite + `check_pinned_deps.py` one more time, then this
   worktree is ready for the same merge flow as item 1&2's worktree.

## Not yet started: items 5-9

No files touched yet for any of these. Start items 5 and 8 with the
`superpowers:writing-plans` skill (specs already exist and are
user-confirmed, listed above) — each becomes its own worktree + SDD plan,
matching this session's established pattern (see
`docs/superpowers/plans/2026-09-18-*.md` for the two examples already
executed this session: `hybrid-bm25-retrieval`,
`ability-held-item-interactions` — both fully merged to `main`).

Items 6, 7, 9 are bounded (no plan doc needed per `superpowers:brainstorming`'s
bounded path) — implement directly via TDD like items 1-4, probably batched
into one more worktree (e.g. `observability-retention-and-stats-summary`)
since they're both small and touch the same file (`rag/observability.py`).

## Repo state as of this pause

- `main` HEAD: `73a4903` (docs: refresh STATUS_COMMIT marker after fixing
  stale test counts) — clean, no uncommitted changes on main itself.
- Three worktrees exist: `.worktrees/team-persistence-and-ask-hardening`
  (done, unmerged), `.worktrees/ci-quality-tooling` (in progress,
  uncommitted changes present), plus whatever the two now-deleted SDD plan
  worktrees left behind (both `ability-held-item-interactions` and
  `hybrid-bm25-retrieval` worktrees/branches were already cleaned up
  earlier this session — not stale, just historical).
- A `code-review` subagent may still be running/finished in the background
  for the team-persistence-and-ask-hardening worktree — check
  `ListAgents` on resume before assuming it needs to be relaunched.
