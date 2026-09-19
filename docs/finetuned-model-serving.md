# Serving the fine-tuned model locally via Ollama

Run this on whichever machine currently serves Ollama for the project
(the Windows laptop, per `2026-09-13-local-llm-migration-design.md`; a
future M4 Pro Mac is a documented option, not built around). These are
manual, one-time steps per notebook run -- not automated, not run in CI.

## Prerequisites

- The merged model directory downloaded from
  `notebooks/finetune_llama3.2.ipynb`'s final zip/download cell, unzipped
  locally.
- [llama.cpp](https://github.com/ggerganov/llama.cpp) cloned and built
  locally, for `convert_hf_to_gguf.py` and `llama-quantize`.
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

2. Quantize, matching the existing `llama3.2:latest` quantization already
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

   `pikarag-finetuned` should now appear alongside `llama3.2:latest`.

## Running the comparison

From the repo root, on a machine with `LLM_HOST` pointed at this Ollama
instance:

```bash
python -m scripts.run_eval --with-answers --model rag --output /tmp/rag_results.json
python -m scripts.run_eval --with-answers --model finetuned --output /tmp/finetuned_results.json
python -m eval.report --rag-results /tmp/rag_results.json --finetuned-results /tmp/finetuned_results.json
```
