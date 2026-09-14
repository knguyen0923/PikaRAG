# Pika-RAG: Evaluation Harness — Design

Status: Approved
Date: 2026-09-13

## Purpose

Give the RAG pipeline a measurable quality baseline so future changes
(chunking, retrieval, model swaps) can be checked for regressions instead of
eyeballed. This matters more now than before this project's local-LLM
migration ([[local-llm-migration]] spec): a ~3B CPU model has weaker
instruction-following than Haiku did, particularly around "answer only from
context, say you don't know otherwise" — the harness is how a quality drop
gets caught instead of discovered by users.

## Scope

In scope:
- A golden Q&A set auto-generated from the project's own processed data
  (`data/processed/pokemon_records.json`, `data/processed/vgc_items.json`),
  so it stays in sync with data refreshes at near-zero manual upkeep.
- A retrieval-quality metric (recall@k) that runs as a normal pytest test in
  the existing CI suite — deterministic, no network calls, no cost.
- An answer-quality check that exercises the full `/ask` path (including the
  local Ollama model) as an on-demand script, not gated in CI.

Out of scope (see "Out of scope" section for detail):
- Hand-curated synthesis/edge-case questions.
- LLM-as-judge grading.
- Wiring the answer-quality check into GitHub Actions CI.

## Golden set generation

`eval/generate_golden_set.py` reads the processed data files and emits
`data/eval/golden_set.json`, one entry per fact worth checking:

```python
{
    "id": "landorus-therian-speed",
    "question": "What is Landorus-Therian's base Speed stat?",
    "match_type": "exact",       # "exact" | "set" | "substring"
    "expected": "91",
    "source_chunk_id": "Landorus-Therian-stats",
}
```

Generated categories, mirroring `rag/embed.py`'s chunking:
- One base-stat question per Pokemon per stat (or a combined "base stats"
  question — pick whichever keeps the set closer to ~30-50 total entries).
- One abilities question per Pokemon (`match_type: "set"` — order-independent).
- One moveset-membership question per Pokemon ("Does X learn Y?" for a
  sampled learned + not-learned move, `match_type: "exact"` boolean-ish check
  against a yes/no answer).
- One "what does `<item>` do" question per item (`match_type: "substring"`
  against the item's own description text, since answers will be paraphrased).

Run manually (`python -m eval.generate_golden_set`) after a data refresh;
not wired automatically into `refresh_job.py`/`refresh_pikalytics_job.py` to
keep those jobs focused — regenerating the golden set is a deliberate,
reviewable step, not a silent side effect of a cron job.

## Retrieval metric — recall@k (CI, every push)

`tests/test_eval_retrieval.py` builds the real `ChromaIndex` +
`SentenceTransformerEmbedder` against the repo's checked-in processed data
(same fixtures the rest of the test suite already uses), then for each
golden entry: does `index.query(question, n_results=5)` include
`source_chunk_id` in its results? Assert aggregate recall@5 stays at or
above a fixed threshold (start at 0.9, tune once the golden set exists for
real). This is pure local computation — no Anthropic, no Ollama, no
Tailscale — so it belongs in the existing `.github/workflows/test.yml` run
with zero new infrastructure.

## Answer-quality metric — on-demand script

`scripts/run_eval.py --with-answers` runs the full `ask_response()` path
(retrieval + `OllamaAnswerer`) for every golden entry and checks the
returned text against `expected`/`match_type`:
- `exact`: case-insensitive exact string match.
- `set`: every expected item present somewhere in the answer text.
- `substring`: expected text (or a key phrase from it) appears in the
  answer.

This is **not** wired into GitHub Actions CI: the runner has no Tailscale
access to the laptop running Ollama, so it can't reach the model at all.
Run it by hand — after a retrieval/prompt change, after a model swap, before
trusting a "should still work" assumption — from a machine that does have
tailnet access (the Oracle Cloud instance, or a dev machine joined to the
same tailnet). Extending CI to join the tailnet automatically
(`tailscale/github-action`) is a reasonable future addition, not required
now.

Output: per-question pass/fail with actual-vs-expected shown for failures
(not just an aggregate score) — the point is debuggability, not a single
number.

## Error handling

- Golden-set generation fails loudly (raises, non-zero exit) if a source
  data file is missing or a record lacks an expected field — silently
  skipping a malformed record would make the golden set quietly shrink over
  time.
- `run_eval.py --with-answers` reports the "offline" message
  (`OllamaAnswerer`'s degraded response) as an explicit failure category
  distinct from a wrong-but-present answer, so a down laptop doesn't get
  misread as a quality regression.

## Testing plan

- `eval/generate_golden_set.py`: unit tests against small fixture records —
  confirms correct question/answer derivation per category, correct
  `match_type` assignment.
- Recall@k computation: unit test with a fake index returning known
  results, confirming the aggregate math (not just the real-index
  integration test).
- `tests/test_eval_retrieval.py`: the real integration test described above,
  runs in CI.
- `scripts/run_eval.py`: unit test of the matcher logic (`exact`/`set`/
  `substring`) with canned answerer output; the live-Ollama run itself is
  manual, not part of the automated suite.

## Out of scope

- **Hand-curated synthesis questions** ("what's a good Scarf user into
  Psychic-types") — deferred; the auto-generated factual set is the
  starting point, synthesis questions can be added as a follow-up golden
  file later if the auto-generated set proves insufficient.
- **LLM-as-judge grading** — skipped in favor of deterministic string
  matching, consistent with the zero-cost, low-compute priority: grading
  with a second model call adds nondeterminism and burns the same
  CPU-constrained laptop twice per question.
- **CI-gated answer-quality checks** — blocked on Tailscale-in-CI, tracked
  as a future enhancement, not required for this spec.
