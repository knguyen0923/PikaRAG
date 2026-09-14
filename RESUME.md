# PikaRAG — Resume Point

Written when a session pauses mid-task (approaching the context-usage limit,
or right before a compaction) so work can pick back up without losing the
thread. If this says "nothing in progress," there's no live handoff — just
use `STATUS.md`.

**Paused at:** 2026-09-14, end of session (user asked to wrap up, not a
token-budget pause — safe to resume any time).
**Working on:** Design/implementation cycle for the 6 specs from the
2026-09-13 brainstorm. Local LLM migration and the eval harness are both
shipped; retrieval-quality's spec is ready with real measured evidence but
has **no implementation plan yet** — that's the next concrete step.
**Why paused:** User asked to finish documenting the retrieval-quality
evidence and make sure the project state is legible for a future session,
then stopped there rather than continuing straight into `writing-plans`.

**Done so far (this session, 2026-09-13 through 2026-09-14):**
- Local LLM migration (code): shipped, merged, pushed. `/ask` uses a local
  Ollama server instead of paid Claude Haiku. Full detail: `STATUS.md`'s
  "Local LLM migration" section. **Task 5 (physical hardware setup) is
  still not done** — separately tracked, not part of this resume point.
- Eval harness: shipped, merged, pushed. `recall@5` gated in CI, measured
  0.9583. Full detail: `STATUS.md`'s "Eval harness" section.
- Verification + fix pass on all 6 unimplemented 2026-09-13 design specs
  (`eval-harness`, `retrieval-quality`, `grounding-trust`, `observability`,
  `reliability`, `ingestion-robustness`) — every one had real bugs, all now
  fixed and committed. See git log for the commits (`git log --oneline
  --all --grep="design specs"` or similar; committed 2026-09-14).
- Investigated 2 real retrieval misses the eval harness surfaced
  (`Abomasnow-moveset-learned-question`,
  `Dragalge-moveset-not-learned-question`) using systematic-debugging:
  root-caused to Mega Stone item chunks + stats chunks consistently
  outranking the correct moveset chunk for "Does X learn Y?" questions
  (confirmed via direct index queries, not guessed). Confirmed the
  already-approved `retrieval-quality-design.md` spec's entity-aware
  `where`-filter design fixes this exact failure mode. Added this evidence
  to the spec's Purpose section (commit `3d3991e`, local `main` only —
  **not yet pushed to origin** as of this write; `main` is 1 commit ahead
  of `origin/main`).

**In flight (not committed / not finished):**
- Nothing uncommitted. Working tree should be clean — verify with `git
  status` on resume regardless.

**Next step:** Run the `superpowers:writing-plans` skill on
`docs/superpowers/specs/2026-09-13-retrieval-quality-design.md` (already
fully reviewed and fixed, carries real measured evidence — no more
brainstorming needed). Then execute the resulting plan via
`superpowers:subagent-driven-development` (same pattern used for the local
LLM migration and eval harness plans this session: isolated worktree,
per-task implementer + reviewer dispatch, squash to one commit, final
whole-branch review, merge to `main`). After that, `STATUS.md`'s "Next up
after that" section lists 4 more design specs ready for the same
treatment (grounding-trust before observability specifically — the one
real cross-spec dependency; reliability and ingestion-robustness anytime).

**Open questions / decisions still needed:** None blocking — the path
forward is unambiguous. The only standing preference to carry forward:
this session's commit-cadence convention (implementers commit per task on
an isolated branch, squashed to one commit before merging) and the
established habit of pushing to origin only when explicitly asked, not
automatically after every merge.

---

## Prior resume point (2026-09-11, deployment) — historical, fully resolved

**Paused at:** 2026-09-11, deployment essentially complete — just waiting on
Discord's global slash-command propagation window (up to ~1hr).
**Why paused:** Nothing left to do but wait for `/ping` to actually appear
in Discord's slash-command picker. Resolved same day — `/ping` confirmed
working live in Discord on 2026-09-12 (see `STATUS.md`).

Full detail (Oracle Cloud instance recreation, `torch==2.6.0` pin fix,
systemd units, Discord invite snags) preserved in git history and in
memory `pikarag-oracle-deployment`/`pikarag-oracle-networking-gotchas` if
ever needed again — not reproduced here since it's fully resolved and
`STATUS.md` is the current source of truth for what's live.

---

## Template (overwrite the section above when pausing mid-task)

**Paused at:** <date>, ~<N>% of context budget used
**Working on:** <the task in one line>
**Why paused:** <token budget / imminent compaction>

**Done so far:**
- <bullet per completed step, with file paths / commit hashes>

**In flight (not committed / not finished):**
- <file path>: <what's half-done in it>

**Next step:** <the exact next action to take on resume — specific enough
that no re-derivation of context is needed>

**Open questions / decisions still needed:** <anything blocking that needs
the user's input>
