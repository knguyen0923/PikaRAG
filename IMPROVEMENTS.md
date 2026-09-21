# PikaRAG — Improvement Backlog

Generated from a portfolio review (2026-09-16), prioritized by resume/interview
impact and effort. Cross-references `STATUS.md`/`RESUME.md`/`TAKEAWAYS.md` for
context on what's already shipped — this file is additive, not a replacement
for those.

**2026-09-17 brainstorming pass:** everything below except local-LLM Task 5
was brainstormed via `superpowers:brainstorming`. Current state:

- **Rotate leaked Discord bot token** — still not done, deliberately deferred
  by the user until after design work. Do this regardless of anything else on
  this list — see Priority 1 below for the exact steps.
- **Hybrid BM25+vector retrieval — done.** `rag/bm25.py`'s `BM25Index`
  (in-memory, 887 chunks) is now fused with the existing vector query via
  Reciprocal Rank Fusion in `rag/retrieve.py`'s `build_context_block`, wired
  into the live bot's unfiltered/no-entity-detected fallback path. 4 new
  golden-set entries target that previously-untested path; one of them,
  `Aegislash-stats`, is a real recall miss for pure vector search at k=5
  (confirmed against the live index) that BM25+RRF now recovers — the
  concrete, demonstrated benefit of hybrid retrieval, not just a smoke test.
  536/536 tests passing (560/560 after merging with the ability/held-item
  interactions branch).
- **Fine-tune vs. RAG comparison — infrastructure done.** `scripts/generate_finetune_data.py`
  template-generates 4,172 `(question, answer)` training pairs from the same
  processed records/items `rag/embed.py` chunks for RAG, committed to
  `data/finetune/train.jsonl`; `rag/answer.py`'s `OllamaAnswerer` gained
  `answer_bare(question)` (no context block, no grounding-caveat system
  prompt) for calling a fine-tuned model directly; `scripts/run_eval.py`
  gained `--model rag|finetuned` (finetuned path graded on answer-correctness
  via `eval.matchers.matches`, not recall@5, which doesn't apply without a
  retrieval step) and `--output <path>` to dump raw per-question results;
  `eval/report.py` tabulates two such result files (one per `--model` run)
  side by side. `notebooks/finetune_llama3.2.ipynb` documents the actual
  LoRA fine-tune of Llama3.2-3B via `peft`/`transformers`/`bitsandbytes` on a
  free-tier Colab T4 GPU; `docs/finetuned-model-serving.md` documents the
  merge/GGUF-convert/quantize/`ollama create` steps to deploy the result as
  `pikarag-finetuned`, run manually on whichever machine serves Ollama.
  MLX/M4-Pro local training was considered and explicitly rejected in favor
  of the portable peft/transformers stack — revisit only if the cloud-GPU
  option becomes inconvenient. 583/583 tests passing. **Manual follow-up,
  outside CI, at the user's convenience:** actually run the notebook on
  Colab, deploy `pikarag-finetuned` per the serving doc, and run the real
  `--model rag` vs. `--model finetuned` comparison to get real accuracy
  numbers for the portfolio writeup — this plan built the infrastructure,
  not the trained model itself.
- **Observability retention/prune + `/stats-summary` — done.** Bounded items
  (no spec file, approved in chat during the 2026-09-17 brainstorming pass).
  `rag/observability.py` gained `prune_old_logs(cutoff_timestamp, db_path)`
  (deletes `ask_log` rows older than an ISO8601 cutoff, returns the count
  deleted) and `get_log_summary(db_path)` (aggregate total/gate-fired/degraded
  counts + average latency). `scripts/prune_observability_log.py` is a
  manual/cron script (`--days`, default 90) mirroring `pipeline/refresh_job.py`'s
  standalone-script pattern — not wired into the bot or CI, run periodically
  on whichever machine hosts the live bot. New owner-only `/stats-summary`
  command (`bot/commands/stats_summary.py`) reports the aggregate stats,
  same ephemeral-reply pattern as `/debug-last`. 592/592 tests passing.
- **Agentic `/ask`+`/calc` tool-calling loop — done.** New `/analyze` command
  (not an extension of `/ask`) lets the model orchestrate 3 tools over
  Ollama's native `/api/chat` tool-calling: `OllamaAnswerer.answer_with_tools`
  (`rag/answer.py`) drives the round-trip loop, capped at 4 rounds (forces a
  best-effort final answer on hitting the cap rather than erroring);
  `bot/agentic.py` defines the 3 tool schemas (`run_damage_calc`,
  `get_stored_team`, `get_usage_stats`) and `build_tool_dispatch`, each a
  thin wrapper around an existing pure function (`calc_response`, `get_team`,
  `usage_for_record`) -- the model never computes damage itself, only ever
  sees `run_damage_calc`'s deterministic string output. `get_stored_team`'s
  schema takes no arguments at all -- `user_id` is bound from the real
  Discord interaction, never from the model's tool-call arguments, so a
  confused or adversarial prompt can't spoof whose stored team gets read. On
  a malformed/hallucinated tool call (unknown tool name, non-object
  arguments, or a dispatch failure), `answer_with_tools` returns the
  `MALFORMED_TOOL_CALL_MESSAGE` sentinel and `analyze_response_async` falls
  back to a plain RAG answer through the existing `ask_response_async` path
  rather than erroring. `/analyze` calls `raw_answerer` directly (not the
  `CircuitBreaker`-wrapped one, which only implements `.answer()`), same as
  `/llmstatus` already does. Full plan:
  `docs/superpowers/plans/2026-09-19-agentic-tool-calling.md`. 612/612 tests
  passing.
- **Ability/held-item interactions — done.** 6 type-immunity abilities (Levitate,
  Water Absorb, Flash Fire, Volt Absorb, Lightning Rod, Storm Drain) force 0
  damage; weather auto-derives from Drought/Drizzle/Sand Stream/Snow Warning and
  terrain from Electric Surge/Grassy Surge/Psychic Surge/Misty Surge (explicit
  `--weather`/`--terrain` params override); Intimidate models via stat-stage math.
  541/541 tests passing (560/560 after merging with the hybrid BM25+vector
  retrieval branch).
- **Pinned-deps CI check — done.** `scripts/check_pinned_deps.py` fails CI if
  any `==`-pinned line in `requirements.txt` lacks a preceding explanatory
  comment; wired into `.github/workflows/test.yml`; all 5 existing pins
  (`requests`, `pytest`, `discord.py`, `chromadb`, `sentence-transformers`)
  now carry a real reason (most: "pinned at scaffold time, no known
  constraint"; `sentence-transformers`: a real one — an earlier `6.0.1` pin
  didn't exist on PyPI, silently broke test collection, fixed in commit
  `e06e6ae`); 6 new tests in `tests/test_check_pinned_deps.py`. 517/517 tests
  passing.

## Priority 1 — do first (credibility, not new skills)

- **Finish the local-LLM migration (Task 5) — done, 2026-09-20, on a
  different machine than planned.** The Windows laptop was dropped in favor
  of the MacBook already used for local dev (Tailscale + Ollama installed
  there instead). `OLLAMA_HOST` had to be set to `0.0.0.0` and Ollama
  force-restarted (quitting from the menu bar left the old process running
  bound to localhost only). Oracle's `.env` now points `LLM_HOST` at the
  Mac's Tailscale IP; `LLM_TIMEOUT` raised from the 30s default to 90s
  (qwen3.5:9b is a thinking model — slower per response than llama3.2:3b
  was). Verified end-to-end: real `/ask` question in Discord returned a
  real grounded answer. **Not yet persistent across the Mac's
  reboot/logout** — see `docs/DEPLOYMENT.md` section 3 for the redo steps
  if that happens. If a Windows machine is used later, it still needs
  Tailscale + Ollama + `qwen3.5:9b` pulled from scratch — none of that
  setup was ever done on a Windows box for this project.
  - **Found and fixed along the way:** Oracle's deployed code was 129
    commits behind `origin/main`, and `origin/main` was itself 70 commits
    behind local `main` — the entire prior 9-item backlog had been
    committed locally but never pushed to GitHub. Pushed everything and
    re-pulled on Oracle; `rank_bm25` had to be installed there via
    `pip install -r requirements.txt` for hybrid retrieval to work.

- **Rotate the leaked Discord bot token — done, 2026-09-20.** Reset in the
  Discord Developer Portal, updated in both local and Oracle `.env`; bot
  restarted and confirmed connected under the new token. The stale, unused
  `ANTHROPIC_API_KEY` (Haiku path was already deleted from the code) was
  also removed from both `.env` files while in there.

## Priority 2 — fills a real skill gap

- **Fine-tune vs. RAG comparison — infrastructure done.** See the summary
  bullet near the top of this file for what was built. Manual follow-up
  (actually running the notebook + real comparison numbers) still open.

## Priority 3 — solid extensions once the above are done

- **Agentic `/ask`+`/calc` tool-calling loop — done.** See the summary
  bullet near the top of this file for what was built (new `/analyze`
  command, not a merge of `/ask`/`/calc` themselves -- both stay untouched).

- **Add hybrid (BM25 + vector) retrieval — done.** Entity-aware filtering
  (`rag/entity.py`) already solves the case where a known Pokémon/item name
  is detected in the question. For the no-entity-detected fallback path,
  `rag/bm25.py`'s `BM25Index` is now fused with vector search via Reciprocal
  Rank Fusion in `rag/retrieve.py`'s `build_context_block`. 4 new golden-set
  entries were added to measure the retrieval-quality delta; `Aegislash-stats`
  is a real case pure vector search misses at k=5 that BM25+RRF recovers.
  Growing the golden set to include that deliberately-hard no-entity case
  slightly eroded the margins of the two pre-existing recall@5 tests that
  don't exercise hybrid retrieval (raw unfiltered recall@5: 46/48=0.9583 →
  49/52=0.9423, still above the 0.90 threshold; entity-aware recall@5:
  48/48=1.0000 → 51/52=0.9808, still above its 0.9583 baseline) -- both
  expected, since neither test passes a `bm25_index`. The number that
  actually demonstrates the fix is recall@5 through the real
  `build_context_block` hybrid path: 52/52=1.0000. 536/536 tests passing.

## Priority 4 — lower priority, explicitly optional

- Ability/held-item interactions in the damage calculator — done (see summary
  above).

- A CI check that formally documents why pinned dependency versions
  are pinned, generalizing the existing hand-written `torch` comment in
  `requirements.txt`.
