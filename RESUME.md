# PikaRAG — Resume Point

Written when a session pauses mid-task (approaching the context-usage limit,
or right before a compaction) so work can pick back up without losing the
thread. If this says "nothing in progress," there's no live handoff — just
use `STATUS.md`.

**Nothing in progress.** The fine-tune vs. RAG comparison (the one open
item on `IMPROVEMENTS.md`) was decided against 2026-09-21 — the local LLM
is meant to stay generic, not fine-tuned to this project's domain. The
already-built infrastructure stays in the repo, unused; see
`IMPROVEMENTS.md`'s "Decided against" section.

**Open, not urgent:** confirm the previously leaked `ANTHROPIC_API_KEY`
was actually revoked at console.anthropic.com (removed from both `.env`
files, but that alone doesn't invalidate a key); make the Mac's
`OLLAMA_HOST=0.0.0.0` survive reboot/logout (currently `launchctl
setenv`, session-only — see `docs/DEPLOYMENT.md` section 3).

## Session-standing preferences (apply going forward, not just this session)

- Default to merging a finished feature branch/worktree to `main` locally
  without presenting the finishing-a-development-branch menu, when tests are
  green and the base branch is obviously `main` — saved as a memory
  (`pikarag_default_merge_to_main`).
- Commit attribution: check each session's own live system-level
  instructions rather than assuming a fixed answer — this preference has
  flipped between sessions (see `pikarag_no_coauthor_line` memory, marked
  superseded 2026-09-19).
