import json
from pathlib import Path

import chromadb

from bot.main import _build_real_index
from eval.metrics import recall_at_k
from rag.entity import detect_entity

RECORDS_PATH = Path("data/processed/pokemon_records.json")
ITEMS_PATH = Path("data/source/vgc_items.json")
GOLDEN_SET_PATH = Path("data/eval/golden_set.json")

_RECALL_THRESHOLD = 0.9
_KNOWN_MISSES = ["Abomasnow-moveset-learned-question", "Dragalge-moveset-not-learned-question"]


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


def test_entity_aware_filtering_fixes_the_known_abomasnow_and_dragalge_misses():
    records = json.loads(RECORDS_PATH.read_text())
    items = json.loads(ITEMS_PATH.read_text())
    golden_by_id = {entry["id"]: entry for entry in json.loads(GOLDEN_SET_PATH.read_text())}

    index = _build_real_index(records, items, client=chromadb.Client())

    for golden_id in _KNOWN_MISSES:
        entry = golden_by_id[golden_id]
        entity = detect_entity(entry["question"], records, items)
        assert entity is not None, f"{golden_id}: expected an entity to be detected"

        results = index.query(entry["question"], n_results=5, where={entity["field"]: entity["name"]})
        found_ids = {result["id"] for result in results}
        assert entry["source_chunk_id"] in found_ids, (
            f"{golden_id}: target chunk {entry['source_chunk_id']!r} still missing after entity filtering"
        )


def test_recall_at_5_through_entity_aware_retrieval_does_not_regress():
    """Regression guard for the retrieval-quality feature itself: the ONLY
    other recall test in this file (test_recall_at_5_meets_the_threshold_
    against_the_real_index, above) measures the raw unfiltered index.query
    path and would not catch a regression introduced by entity-aware
    filtering. This test routes every golden question through the actual
    detect-then-filter-then-fallback sequence build_context_block uses, and
    asserts recall@5 through THAT path is at least as good as the spec's
    measured pre-change baseline (0.9583)."""
    records = json.loads(RECORDS_PATH.read_text())
    items = json.loads(ITEMS_PATH.read_text())
    golden_set = json.loads(GOLDEN_SET_PATH.read_text())

    index = _build_real_index(records, items, client=chromadb.Client())

    hits = 0
    misses = []
    for entry in golden_set:
        entity = detect_entity(entry["question"], records, items)
        if entity:
            results = index.query(entry["question"], n_results=5, where={entity["field"]: entity["name"]})
            if not results:
                results = index.query(entry["question"], n_results=5)
        else:
            results = index.query(entry["question"], n_results=5)
        found_ids = {result["id"] for result in results}
        if entry["source_chunk_id"] in found_ids:
            hits += 1
        else:
            misses.append(entry["id"])

    score = hits / len(golden_set)
    baseline = 0.9583
    assert score >= baseline, (
        f"entity-aware recall@5 {score:.4f} dropped below the {baseline} pre-change baseline; misses: {misses}"
    )
