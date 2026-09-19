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
- **Agentic `/ask`+`/calc` tool-calling loop** — architectural spec written
  and committed: `docs/superpowers/specs/2026-09-17-agentic-tool-calling-design.md`.
  Not yet implemented. Key decisions: new `/analyze` command (not an
  extension of `/ask`); uses Ollama's native `/api/chat` tool-calling
  (confirmed supported for `llama3.2:3b`, not hand-rolled); 3 tools
  (`run_damage_calc`, `get_stored_team`, `get_usage_stats`), each a thin
  wrapper around an existing pure function; capped at 4 tool-call
  round-trips; falls back to a plain RAG answer on any malformed/hallucinated
  tool call rather than erroring.
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

- **Finish the local-LLM migration (Task 5).** Blocked on the Oracle box
  not being able to reach the Windows laptop's Ollama server over Tailscale.
  Two likely causes, neither yet applied:
  - Ollama defaults to binding only `127.0.0.1` — set the Windows laptop's
    `OLLAMA_HOST` user environment variable to `0.0.0.0:11434`, restart Ollama.
  - Windows Firewall likely blocking inbound TCP 11434 — in an elevated
    PowerShell: `New-NetFirewallRule -DisplayName "Ollama" -Direction Inbound
    -Protocol TCP -LocalPort 11434 -Action Allow`.
  - Once `curl http://<laptop-tailscale-ip>:11434/api/tags` succeeds from the
    Oracle box, retry `/ask` end-to-end (including the offline-degradation
    path) with `journalctl -u pikarag-bot.service -f` open. This closes out
    "self-hosted inference, zero per-query cost" as an actually-true claim
    instead of a half-migrated one.

- **Rotate the leaked Discord bot token.** The live token was printed in
  plaintext into a terminal session during Task 5 troubleshooting (via
  `cat .env` over SSH). Rotate it in the Discord Developer Portal (Bot →
  Reset Token) and update the Oracle `.env`. This is a live credential
  exposure, independent of everything else on this list — do it regardless
  of priority order.

## Priority 2 — fills a real skill gap

- **Fine-tune vs. RAG comparison — infrastructure done.** See the summary
  bullet near the top of this file for what was built. Manual follow-up
  (actually running the notebook + real comparison numbers) still open.

## Priority 3 — solid extensions once the above are done

- **Merge `/ask` and `/calc` into an agentic tool-calling loop.** Right
  now they're cleanly separate (a good call for correctness — math should
  never go through the LLM). The extension: let the model decide when to
  call the damage calculator or pull live usage stats mid-conversation
  (e.g. "is Landorus a good check to this team?" → looks up the stored team,
  runs the calc against each member, reasons over the results) — the tool
  call still routes to the deterministic calculator, the LLM just decides
  when to invoke it.

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
