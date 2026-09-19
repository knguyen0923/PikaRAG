# PikaRAG — Resume Point

Written when a session pauses mid-task (approaching the context-usage limit,
or right before a compaction) so work can pick back up without losing the
thread. If this says "nothing in progress," there's no live handoff — just
use `STATUS.md`.

**Paused at:** mid-session, working through a 9-item prioritized brainstorm
backlog the user approved in full ("Do all of them, prioritized"). Items 1-5
are now done and merged to `main`. No worktrees currently exist for this
backlog; `main` is clean at `9dcf7cf`.

## The 9-item backlog (in the order approved)

1. **Stored team persistence** (P1) — DONE, merged.
2. **`/ask` input length cap** (P1) — DONE, merged.
3. **CI lint step (ruff)** (P2) — DONE, merged.
4. **Coverage tooling (pytest-cov)** (P2) — DONE, merged.
5. **Fine-tune vs. RAG comparison** (P2) — DONE, merged. Infrastructure
   only (training data generator, `answer_bare`, `--model rag|finetuned`,
   `eval/report.py`, Colab notebook, serving doc) — the actual Colab
   training run and real accuracy numbers are a manual follow-up outside
   CI, not part of this repo's automated work. Plan:
   `docs/superpowers/plans/2026-09-19-finetune-vs-rag-comparison.md`.
6. **`observability.db` retention/prune** (P3) — NOT STARTED.
7. **`/stats-summary` command** (P3) — NOT STARTED.
8. **Agentic `/ask`+`/calc` tool-calling loop** (P3) — NOT STARTED. Spec
   already exists and was re-confirmed: `docs/superpowers/specs/2026-09-17-agentic-tool-calling-design.md`.
   Unblocked (item 1, team persistence, is done). Needs
   `superpowers:writing-plans` → `subagent-driven-development` (or inline,
   per the user's stated preference this session — see below), same as
   item 5's execution pattern.
9. **TAKEAWAYS.md staleness fix** (P4) — NOT STARTED. Trivial: two "future
   work" bullets (ability/item interactions, pinned-deps CI check) are
   already done and need to be updated/removed.

Full context on *why* these 9 items, plus 2 already-open pre-existing
backlog items not part of this batch (local-LLM Task 5 hardware networking,
rotating the leaked Discord token — both P1, both untouched, both
independent of this batch): see the conversation history / `IMPROVEMENTS.md`.

## Session-standing preference established this session

The user asked that finishing a development branch skip the
finishing-a-development-branch menu and just merge to `main` locally by
default (tests green, base branch obviously `main`) — saved as a memory
(`pikarag_default_merge_to_main` in the auto-memory system). Apply this for
the rest of this backlog and future PikaRAG sessions, not just item 5.

Also: this session's system-level instructions restored the
`Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>` trailer on
commits (overriding an earlier no-trailer preference from 2026-09-18) — the
old memory was updated to flag itself superseded and to check each
session's own live attribution instructions rather than assume either way.

## Items 1-5 — done, merged to main

See `STATUS.md` for full detail on what each item built. Items 1-4 merged
in two worktrees (`team-persistence-and-ask-hardening`,
`ci-quality-tooling`, both cleaned up). Item 5 merged from
`finetune-vs-rag-comparison` (also cleaned up), commit `9dcf7cf` on `main`
(fast-forward merge, no separate merge commit).

**Verified after all merges:** 583/583 tests passing on `main`, `ruff
check .` clean, `python scripts/check_pinned_deps.py` clean.

## Not yet started: items 6-9

Items 6, 7, 9 are bounded (no plan doc needed per `superpowers:brainstorming`'s
bounded path) — implement directly via TDD, batched into one worktree (e.g.
`observability-retention-and-stats-summary`) since 6 and 7 both touch
`rag/observability.py`. Item 9 is a trivial doc fix (two "future work"
bullets in `TAKEAWAYS.md` are already done and need updating/removing) —
can ride along in the same worktree or its own tiny one.

Item 8 needs a plan first: spec already exists and is user-confirmed at
`docs/superpowers/specs/2026-09-17-agentic-tool-calling-design.md`. Use
`superpowers:writing-plans` (same as item 5), then either
`subagent-driven-development` or inline execution per the user's choice at
that time.

## Repo state as of this pause

- `main` HEAD: `9dcf7cf` (docs: refresh STATUS.md/marker for the
  finetune-vs-rag-comparison branch) — clean, no uncommitted changes.
- No worktrees currently exist beyond the main checkout.
