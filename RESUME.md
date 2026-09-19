# PikaRAG — Resume Point

Written when a session pauses mid-task (approaching the context-usage limit,
or right before a compaction) so work can pick back up without losing the
thread. If this says "nothing in progress," there's no live handoff — just
use `STATUS.md`.

**Nothing in progress.** The 9-item prioritized brainstorm backlog the user
approved in full ("Do all of them, prioritized") is complete — all 9 items
done and merged to `main` as of commit `b8ab5b9`. See `STATUS.md` for detail
on the final item (agentic `/ask`+`/calc` tool-calling loop / `/analyze`
command).

Two pre-existing backlog items outside that batch remain open, independent
of everything above (both P1, see `IMPROVEMENTS.md` for detail):

1. **Rotate the leaked Discord bot token** — still not done. A real
   credential exposure (plaintext leaked into an SSH session during Task 5
   troubleshooting). Do this regardless of priority order.
2. **Finish the local-LLM migration Task 5** — blocked on the Oracle box not
   being able to reach the Windows laptop's Ollama server over Tailscale
   networking.

## Session-standing preferences (apply going forward, not just this session)

- Default to merging a finished feature branch/worktree to `main` locally
  without presenting the finishing-a-development-branch menu, when tests are
  green and the base branch is obviously `main` — saved as a memory
  (`pikarag_default_merge_to_main`).
- Commit attribution: check each session's own live system-level
  instructions rather than assuming a fixed answer — this preference has
  flipped between sessions (see `pikarag_no_coauthor_line` memory, marked
  superseded 2026-09-19).
