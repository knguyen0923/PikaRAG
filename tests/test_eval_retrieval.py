import json
from pathlib import Path

import chromadb

from bot.main import _build_real_index
from eval.metrics import recall_at_k

RECORDS_PATH = Path("data/processed/pokemon_records.json")
ITEMS_PATH = Path("data/source/vgc_items.json")
GOLDEN_SET_PATH = Path("data/eval/golden_set.json")

_RECALL_THRESHOLD = 0.9


def test_recall_at_5_meets_the_threshold_against_the_real_index():
    records = json.loads(RECORDS_PATH.read_text())
    items = json.loads(ITEMS_PATH.read_text())
    golden_set = json.loads(GOLDEN_SET_PATH.read_text())

    index = _build_real_index(records, items, client=chromadb.Client())

    score = recall_at_k(index, golden_set, n_results=5)

    if score < _RECALL_THRESHOLD:
        missed = []
        for entry in golden_set:
            results = index.query(entry["question"], n_results=5)
            found_ids = {result["id"] for result in results}
            if entry["source_chunk_id"] not in found_ids:
                missed.append(entry["id"])
        assert False, f"recall@5 dropped to {score:.2f} (threshold {_RECALL_THRESHOLD}); missed: {missed}"
