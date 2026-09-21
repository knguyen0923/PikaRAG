# Fine-tune vs. RAG comparison — design

**Decided against 2026-09-21:** the infrastructure below was built, but the
user decided not to actually run the comparison against the live model —
the local LLM is meant to stay generic, not narrowed to this project's
domain via fine-tuning. Kept as a demonstrated technique, not an active
plan. See `IMPROVEMENTS.md`'s "Decided against" section.

Source: `IMPROVEMENTS.md` Priority 2. Portfolio-review backlog item — the one
ML technique (model adaptation, vs. pure retrieval/prompting) missing across
the whole project, benchmarked rigorously against the existing RAG pipeline
using infrastructure this repo already has.

## Purpose

Demonstrate model adaptation (LoRA fine-tuning) as a second technique
alongside retrieval, and produce a rigorous, explainable head-to-head
comparison against the existing `/ask` RAG pipeline, using the same 48-entry
golden set (`data/eval/golden_set.json`) the eval harness already gates CI
on. The fine-tuned model is a benchmark artifact for the comparison, not a
production replacement — see "Out of scope."

## Constraints established during brainstorming

- **$0 cost, local-first is the standing priority** ([[pikarag_cost_priority]]
  memory), but a one-time, off-repo training run on a free-tier cloud GPU
  (Google Colab or Kaggle, free T4) is an accepted exception for the training
  step only — inference/serving stays fully local via Ollama, $0, same as
  today.
- Explicitly considered and rejected: training locally via `mlx-lm` on a
  future M4 Pro Mac. Apple Silicon can run LoRA training natively and would
  keep the whole pipeline local, but ties the design to Apple-Silicon-only
  tooling instead of the portable, standard `peft`/`transformers` stack that
  works regardless of which machine is available. Revisit only if the cloud
  GPU option becomes unavailable or inconvenient.
- Base model: **Llama3.2-3B** (not Qwen2.5-1.5B) — chosen to match the model
  already serving the live RAG path (`OllamaAnswerer`, per
  `2026-09-13-local-llm-migration-design.md`), for an apples-to-apples
  comparison, accepting a slower/heavier free-tier training run than a 1.5B
  model would need. **Superseded 2026-09-21:** the live RAG path switched to
  `qwen3.5:9b`; the notebook (`notebooks/finetune_qwen3.5.ipynb`) and
  `docs/finetuned-model-serving.md` were retargeted to `Qwen/Qwen3.5-9B` to
  keep this comparison apples-to-apples with whatever model `/ask` actually
  runs. This bullet is kept for history, not re-litigated.
- Comparison re-uses the existing eval harness (`scripts/run_eval.py`,
  `data/eval/golden_set.json`) rather than building separate side-by-side
  tooling — extend, don't duplicate.
- Metric split: RAG path keeps its existing **recall@5** retrieval metric
  (unaffected by this work). The fine-tuned path has no retrieval step to
  measure recall on, so it's graded on **answer correctness against
  `golden_set.json`'s `expected` field** (exact/fuzzy string match) instead
  of an LLM-as-judge — deterministic, no new model dependency, directly
  comparable to the RAG path's own final-answer quality.

## Architecture

### 1. Training data generation — `scripts/generate_finetune_data.py` (new)

Template-based generation from the same structured source data
`rag/embed.py` already chunks for RAG (`pipeline`'s processed Pokemon
records, `vgc_items.json`), reusing its existing sentence templates and
field names (`record["base_stats"]`, `record["learnset"]`,
`record["abilities"]`, item `description`s, etc.) rather than using a larger
LLM to generate paraphrases. Produces `(question, natural-language-answer)`
training pairs — deliberately more template variety per field than the
48-question golden set needs for eval, since a training set benefits from
more examples than an eval set does.

Deterministic and fully inspectable: every generated pair traces directly to
a source record and template, no LLM-generation cost, no non-reproducible
step. Accepted tradeoff (flagged during brainstorming, not a hidden flaw):
template-only phrasing diversity is lower than a hand-curated or
LLM-paraphrased dataset would give, so the fine-tuned model may lean on
template phrasing patterns rather than generalizing as broadly as a
from-scratch dataset would encourage. Acceptable for this project's scope —
worth one sentence in the eventual portfolio writeup, not a design blocker.

Output: `data/finetune/train.jsonl` (new, follows the existing
`data/eval/golden_set.json` precedent of committing generated
data-for-training/eval to the repo).

### 2. Training — one-time, off-repo, cloud GPU

LoRA fine-tune of Llama3.2-3B via `peft` + `transformers` + `bitsandbytes`
(the standard, portable toolchain — not `mlx-lm`, not `unsloth`) on a
free-tier Colab or Kaggle T4 GPU, using `data/finetune/train.jsonl`.

This step runs outside the deployed system and outside CI — it needs a GPU
neither the Oracle box nor the Windows-laptop Ollama host has. Documented as
a reproducible notebook checked into the repo at
`notebooks/finetune_llama3.2.ipynb`, run manually when the training data or
base model changes, not automated. Output: a LoRA adapter directory,
downloaded locally after the notebook run.

### 3. Serving — local, $0, via Ollama

Standard merge-then-convert path (the safe, well-supported one — Ollama's
newer separate-`ADAPTER`-file support exists but has narrower base-model
coverage and is less battle-tested):

1. `peft`'s `merge_and_unload()` — merge the LoRA adapter into Llama3.2-3B's
   base weights.
2. `llama.cpp`'s `convert_hf_to_gguf.py` — convert merged FP16 weights to
   GGUF.
3. `llama-quantize` — quantize (e.g. Q4_K_M, matching the existing
   `llama3.2:latest` quantization already in use).
4. A `Modelfile` (`FROM ./merged-model.gguf`) + `ollama create
   pikarag-finetuned -f Modelfile`.

Runs on whichever machine is serving Ollama for the project at the time
(currently the Windows laptop; a future M4 Pro Mac is a documented option,
not built around — see Constraints).

### 4. Comparison — extends `scripts/run_eval.py`, no new tooling

A new flag (e.g. `--model rag|finetuned`) on the existing eval script:

- `--model rag` (current default/behavior, unchanged): `OllamaAnswerer` with
  the RAG-retrieved context block, graded on recall@5 as today.
- `--model finetuned` (new): calls the bare `pikarag-finetuned` Ollama model
  directly, **no retrieval/context injection** — the whole point is testing
  what the model learned via fine-tuning, not re-adding retrieval on top of
  it. Graded on answer correctness against golden_set.json's `expected`
  field (exact/fuzzy match), not recall@5.

Both runs' results are written side by side via a small new `eval/report.py`
(or similar) that tabulates RAG-path vs. fine-tuned-path accuracy per
question, for the eventual portfolio writeup — this is the "rigorous
comparison" the backlog item asks for, built on infrastructure that already
exists rather than new bespoke reporting.

## Testing

- Unit tests for `scripts/generate_finetune_data.py`: given a sample record,
  produces well-formed `(question, answer)` pairs referencing the right
  fields; no network/model calls, pure data transformation, testable the
  same way `rag/embed.py`'s chunk-building is already tested.
- Unit tests for the new `--model finetuned` path in `scripts/run_eval.py`:
  mock the Ollama call, confirm no context block is built/injected, confirm
  grading uses answer-correctness-against-`expected` rather than recall@5.
- The training notebook itself is not unit-tested (it's a manual, one-time,
  off-repo run) — its *output* (the adapter/GGUF conversion → Ollama model)
  is what the eval harness exercises.

## Out of scope

- Automating retraining or hyperparameter search — this is a one-time
  demonstration/comparison, not an ongoing training pipeline.
- Using the fine-tuned model in production `/ask` — it stays a benchmark
  artifact. The RAG path remains authoritative in production since it's
  grounded in current data and can be refreshed (via the existing pipeline
  refresh jobs) without retraining, which matters for a live-usage-data
  metagame that changes over time; a fine-tuned model would go stale the
  moment the underlying Pokemon/item/usage data changes and require
  retraining to catch up.
- LLM-as-judge grading (considered and rejected in favor of deterministic
  answer-correctness matching against `expected`, per Constraints above).
