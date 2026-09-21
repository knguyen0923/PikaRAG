# PikaRAG — Improvement Backlog

Generated from a portfolio review (2026-09-16), prioritized by resume/interview
impact and effort. Cross-references `STATUS.md`/`RESUME.md`/`TAKEAWAYS.md` for
context on what's already shipped — this file is additive, not a replacement
for those.

## Open

Nothing open — see `STATUS.md` for current state.

## Decided against

- **Fine-tune vs. RAG comparison — infrastructure built, deliberately not
  run.** User's call (2026-09-21): the local LLM is meant to stay generic,
  not narrowed to this project's domain via fine-tuning. The full
  infrastructure remains in the repo as a demonstrated technique
  (`scripts/generate_finetune_data.py`, `OllamaAnswerer.answer_bare`,
  `scripts/run_eval.py --model rag|finetuned`, `eval/report.py`,
  `notebooks/finetune_qwen3.5.ipynb`, `docs/finetuned-model-serving.md`)
  but won't be executed against the live model. Design:
  `docs/superpowers/specs/2026-09-17-finetune-vs-rag-design.md`.

## Done

- **Conversational chat.** Plain messages (no slash command) in
  admin-designated channels reuse `/analyze`'s tool-calling loop with a
  short rolling per-channel history for natural follow-ups. Off by
  default (`CONVERSATION_CHANNEL_IDS` env var unset).
  `docs/superpowers/plans/2026-09-21-conversational-chat.md`.
- **Local-LLM migration (Task 5).** `/ask` runs on self-hosted Ollama
  (`qwen3.5:9b`) instead of paid Claude Haiku — served from a MacBook
  (the originally-planned Windows laptop was dropped; never set up).
  Verified end-to-end in Discord. `docs/DEPLOYMENT.md` section 3.
- **Discord bot token rotation.** A prior token leaked into a terminal
  session; rotated in the Discord Developer Portal, both `.env` files
  updated. The stale, unused `ANTHROPIC_API_KEY` (dead code path) was
  removed from both at the same time.
- **Agentic `/ask`+`/calc` tool-calling loop.** New `/analyze` command
  (not a merge of `/ask`/`/calc`, both untouched) lets the model call 3
  tools over Ollama's native tool-calling before answering.
  `docs/superpowers/plans/2026-09-19-agentic-tool-calling.md`.
- **Hybrid BM25+vector retrieval.** `rag/bm25.py`'s `BM25Index` fused
  with vector search via Reciprocal Rank Fusion for the
  no-entity-detected `/ask` fallback path — recovers a real recall@5 miss
  (`Aegislash-stats`) pure vector search misses at k=5.
  `docs/superpowers/plans/2026-09-18-hybrid-bm25-retrieval.md`.
- **Ability/held-item interactions in the damage calculator.** 6
  type-immunity abilities force 0 damage; weather/terrain auto-derive
  from setter abilities; Intimidate modeled via stat-stage math.
  `docs/superpowers/plans/2026-09-18-ability-held-item-interactions.md`.
- **Observability retention/prune + `/stats-summary`.**
  `rag/observability.py` gained pruning + aggregate-stats helpers; new
  owner-only `/stats-summary` command surfaces them.
- **Pinned-deps CI check.** `scripts/check_pinned_deps.py` fails CI if a
  pinned `requirements.txt` line lacks an explanatory comment.
