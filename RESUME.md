# PikaRAG — Resume Point

Written when a session pauses mid-task (approaching the context-usage limit,
or right before a compaction) so work can pick back up without losing the
thread. If this says "nothing in progress," there's no live handoff — just
use `STATUS.md`.

**Paused at:** mid-session, working through a 9-item prioritized brainstorm
backlog the user approved in full ("Do all of them, prioritized"). Items 1-4
are now done and merged to `main`. No worktrees currently exist for this
backlog; `main` is clean at `f790174`.

## The 9-item backlog (in the order approved)

1. **Stored team persistence** (P1) — DONE, merged.
2. **`/ask` input length cap** (P1) — DONE, merged.
3. **CI lint step (ruff)** (P2) — DONE, merged.
4. **Coverage tooling (pytest-cov)** (P2) — DONE, merged (bundled into the
   same commit/worktree as item 3 since both touched the same CI file).
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

## Items 1-4 — done, merged to main

**Item 1&2** merged via `team-persistence-and-ask-hardening` (worktree/branch
now deleted). Final commit before merge: `c596a88`, applying a post-review
fix (see `STATUS.md` for detail) on top of the two feature commits
(`87c75a6`, `913531f`). Merge commit landed on `main` before item 3&4.

**Item 3&4** merged via `ci-quality-tooling` (worktree/branch now deleted,
rebased onto post-item-1&2 `main` before its own merge). Final commit
`f790174`, fast-forwarded onto `main`. Bundled coverage tooling (item 4)
into the same worktree as CI lint (item 3) since both touch
`.github/workflows/test.yml` and `requirements.txt`.

**Verified after both merges:** 564/564 tests passing on `main`, `ruff
check .` clean, `python scripts/check_pinned_deps.py` clean.

## Not yet started: items 5-9

No files touched yet for any of these. Start items 5 and 8 with the
`superpowers:writing-plans` skill (specs already exist and are
user-confirmed, listed above) — each becomes its own worktree + SDD plan,
matching this session's established pattern (see
`docs/superpowers/plans/2026-09-18-*.md` for the two examples already
executed earlier this session: `hybrid-bm25-retrieval`,
`ability-held-item-interactions` — both fully merged to `main`).

Items 6, 7, 9 are bounded (no plan doc needed per `superpowers:brainstorming`'s
bounded path) — implement directly via TDD, probably batched into one more
worktree (e.g. `observability-retention-and-stats-summary`) since 6 and 7
are both small and touch the same file (`rag/observability.py`). Item 9 is
a trivial doc fix, independent of the others.

## Repo state as of this pause

- `main` HEAD: `f790174` (feat: add ruff lint step and pytest-cov reporting
  to CI) — clean, no uncommitted changes.
- No worktrees currently exist beyond the main checkout.
