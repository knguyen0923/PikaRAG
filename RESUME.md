# PikaRAG — Resume Point

Written when a session pauses mid-task (approaching the context-usage limit,
or right before a compaction) so work can pick back up without losing the
thread. If this says "nothing in progress," there's no live handoff — just
use `STATUS.md`.

**In progress:** the fine-tune vs. RAG comparison, the one open item on
`IMPROVEMENTS.md`. Notebook retargeted from Llama3.2-3B to
`Qwen/Qwen3.5-9B` (`notebooks/finetune_qwen3.5.ipynb`) — user is running
it manually on Colab now. **Next steps once they have a merged model:**
follow `docs/finetuned-model-serving.md` (convert to GGUF, quantize,
`ollama create pikarag-finetuned`), then `scripts/run_eval.py --model
rag` vs. `--model finetuned`, then `eval/report.py` for the side-by-side
numbers.

**Open, not urgent, independent of the above:** confirm the previously
leaked `ANTHROPIC_API_KEY` was actually revoked at console.anthropic.com
(removed from both `.env` files, but that alone doesn't invalidate a
key); make the Mac's `OLLAMA_HOST=0.0.0.0` survive reboot/logout
(currently `launchctl setenv`, session-only — see `docs/DEPLOYMENT.md`
section 3).

## Session-standing preferences (apply going forward, not just this session)

- Default to merging a finished feature branch/worktree to `main` locally
  without presenting the finishing-a-development-branch menu, when tests are
  green and the base branch is obviously `main` — saved as a memory
  (`pikarag_default_merge_to_main`).
- Commit attribution: check each session's own live system-level
  instructions rather than assuming a fixed answer — this preference has
  flipped between sessions (see `pikarag_no_coauthor_line` memory, marked
  superseded 2026-09-19).
