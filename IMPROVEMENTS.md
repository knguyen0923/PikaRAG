# PikaRAG — Improvement Backlog

Generated from a portfolio review (2026-09-16), prioritized by resume/interview
impact and effort. Cross-references `STATUS.md`/`RESUME.md`/`TAKEAWAYS.md` for
context on what's already shipped — this file is additive, not a replacement
for those.

## Open

- **Fine-tune vs. RAG comparison — infrastructure done, not yet run.**
  `scripts/generate_finetune_data.py` generates training pairs from the
  same data RAG uses; `OllamaAnswerer.answer_bare` calls a fine-tuned
  model directly (no context/grounding prompt); `scripts/run_eval.py
  --model rag|finetuned` and `eval/report.py` do the head-to-head
  comparison. `notebooks/finetune_qwen3.5.ipynb` (LoRA via
  `peft`/`transformers`/`bitsandbytes` on a free Colab T4) and
  `docs/finetuned-model-serving.md` (GGUF convert/quantize/`ollama
  create`) cover training and deployment. **Manual follow-up, at the
  user's convenience:** run the notebook, deploy `pikarag-finetuned`, run
  the real comparison for portfolio numbers. Design:
  `docs/superpowers/specs/2026-09-17-finetune-vs-rag-design.md`.

## Done

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
