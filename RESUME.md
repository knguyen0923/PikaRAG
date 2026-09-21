# PikaRAG — Resume Point

Written when a session pauses mid-task (approaching the context-usage limit,
or right before a compaction) so work can pick back up without losing the
thread. If this says "nothing in progress," there's no live handoff — just
use `STATUS.md`.

**In progress:** the fine-tune vs. RAG comparison (last item on
`IMPROVEMENTS.md`, Priority 2). Notebook retargeted from Llama3.2-3B to
`Qwen/Qwen3.5-9B` and pushed (commit `8c64787`,
`notebooks/finetune_qwen3.5.ipynb`) — user is now running it manually on
Colab. **Next steps once they have a merged model:** follow
`docs/finetuned-model-serving.md` (convert to GGUF, quantize, `ollama
create pikarag-finetuned`), then `scripts/run_eval.py --model rag` vs.
`--model finetuned`, then `eval/report.py` for the side-by-side numbers.

As of 2026-09-20 (commit `32ea903`), both P1 items from `IMPROVEMENTS.md`
were already done:

1. **Discord bot token rotated**, both local and Oracle `.env` updated, bot
   confirmed reconnected. Stale unused `ANTHROPIC_API_KEY` also removed
   from both.
2. **Local-LLM migration Task 5 done** — on the MacBook instead of the
   originally-planned Windows laptop (which was never actually set up).
   Model switched to `qwen3.5:9b`. Oracle was also found to be running code
   129 commits stale (GitHub itself was 70 commits behind local `main` —
   the whole prior 9-item backlog had never been pushed); pushed and
   re-pulled. Verified real `/ask` end-to-end in Discord.

**Open, not urgent:** confirm the leaked `ANTHROPIC_API_KEY` was actually
revoked at console.anthropic.com (removing it from `.env` files doesn't
invalidate it); make the Mac's `OLLAMA_HOST=0.0.0.0` survive
reboot/logout (currently `launchctl setenv`, session-only — see
`docs/DEPLOYMENT.md` section 3); then the **fine-tune vs. RAG
comparison manual follow-up** (run the Colab notebook, deploy
`pikarag-finetuned`, run the real `--model rag` vs. `--model finetuned`
comparison) is the last item on `IMPROVEMENTS.md`.

## Session-standing preferences (apply going forward, not just this session)

- Default to merging a finished feature branch/worktree to `main` locally
  without presenting the finishing-a-development-branch menu, when tests are
  green and the base branch is obviously `main` — saved as a memory
  (`pikarag_default_merge_to_main`).
- Commit attribution: check each session's own live system-level
  instructions rather than assuming a fixed answer — this preference has
  flipped between sessions (see `pikarag_no_coauthor_line` memory, marked
  superseded 2026-09-19).
