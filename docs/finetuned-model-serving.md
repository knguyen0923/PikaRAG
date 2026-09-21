# Serving the fine-tuned model locally via Ollama

Run this on whichever machine currently serves Ollama for the project
(the MacBook, as of 2026-09-20 -- see `docs/DEPLOYMENT.md` section 3).
These are manual, one-time steps per notebook run -- not automated, not
run in CI.

## Prerequisites

- The merged model directory downloaded from
  `notebooks/finetune_qwen3.5.ipynb`'s final zip/download cell, unzipped
  locally.
- [llama.cpp](https://github.com/ggerganov/llama.cpp) cloned and built
  locally, for `convert_hf_to_gguf.py` and `llama-quantize`. Needs a build
  recent enough to recognize Qwen3.5's architecture (GGUF conversions of
  `Qwen/Qwen3.5-9B` already exist on Hugging Face, e.g.
  `unsloth/Qwen3.5-9B-GGUF`, confirming current llama.cpp supports it) --
  `git pull` and rebuild if `convert_hf_to_gguf.py` errors on an unknown
  architecture.
- Ollama already installed and running (it already is -- this is the same
  host serving the live `/ask` RAG path).

## Steps

1. Convert the merged FP16 HuggingFace model to GGUF:

   ```bash
   python /path/to/llama.cpp/convert_hf_to_gguf.py \
     ./pikarag-finetuned-merged \
     --outfile pikarag-finetuned-f16.gguf \
     --outtype f16
   ```

2. Quantize, matching the existing `qwen3.5:9b` quantization already
   in use for the RAG path's model:

   ```bash
   /path/to/llama.cpp/llama-quantize \
     pikarag-finetuned-f16.gguf \
     pikarag-finetuned-q4.gguf \
     Q4_K_M
   ```

3. Write a `Modelfile` next to the quantized GGUF:

   ```
   FROM ./pikarag-finetuned-q4.gguf
   ```

4. Register the model with Ollama:

   ```bash
   ollama create pikarag-finetuned -f Modelfile
   ```

5. Confirm it's available:

   ```bash
   ollama list
   ```

   `pikarag-finetuned` should now appear alongside `qwen3.5:9b`.

## Running the comparison

From the repo root, on a machine with `LLM_HOST` pointed at this Ollama
instance:

```bash
python -m scripts.run_eval --with-answers --model rag --output /tmp/rag_results.json
python -m scripts.run_eval --with-answers --model finetuned --output /tmp/finetuned_results.json
python -m eval.report --rag-results /tmp/rag_results.json --finetuned-results /tmp/finetuned_results.json
```
