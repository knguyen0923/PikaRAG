import json
from pathlib import Path

import chromadb

from bot.commands.ask import DISTANCE_THRESHOLD
from bot.main import _build_real_index
from eval.metrics import recall_at_k
from rag.bm25 import BM25Index
from rag.entity import detect_entity
from rag.retrieve import build_context_block

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


def test_golden_set_best_distances_stay_under_the_confidence_gate_threshold():
    """Regression guard for bot.commands.ask.DISTANCE_THRESHOLD: if the
    embedding model or Chroma's distance metric ever changes, this catches
    the gate silently mis-firing on real, answerable questions before it
    ships."""
    records = json.loads(RECORDS_PATH.read_text())
    items = json.loads(ITEMS_PATH.read_text())
    golden_set = json.loads(GOLDEN_SET_PATH.read_text())

    index = _build_real_index(records, items, client=chromadb.Client())

    worst = 0.0
    for entry in golden_set:
        entity = detect_entity(entry["question"], records, items)
        if entity:
            matches = index.query(entry["question"], n_results=5, where={entity["field"]: entity["name"]})
            if not matches:
                matches = index.query(entry["question"], n_results=5)
        else:
            matches = index.query(entry["question"], n_results=5)
        best_distance = min((m["distance"] for m in matches), default=None)
        if best_distance is not None:
            worst = max(worst, best_distance)

    assert worst < DISTANCE_THRESHOLD, (
        f"golden-set worst best_distance {worst:.4f} is no longer safely under "
        f"DISTANCE_THRESHOLD ({DISTANCE_THRESHOLD}) -- real answerable questions would now be gated"
    )


def test_a_sample_of_out_of_domain_questions_exceed_the_confidence_gate_threshold():
    """Companion guard: confirms the threshold still meaningfully gates
    obviously irrelevant questions, not just that it never gates real ones."""
    records = json.loads(RECORDS_PATH.read_text())
    items = json.loads(ITEMS_PATH.read_text())
    out_of_domain_questions = [
        "What is the capital of France?",
        "How do I bake a chocolate cake?",
        "What time is it in Tokyo?",
        "Can you recommend a good movie?",
    ]

    index = _build_real_index(records, items, client=chromadb.Client())

    for question in out_of_domain_questions:
        entity = detect_entity(question, records, items)
        matches = (
            index.query(question, n_results=5, where={entity["field"]: entity["name"]})
            if entity
            else index.query(question, n_results=5)
        )
        if entity and not matches:
            matches = index.query(question, n_results=5)
        best_distance = min((m["distance"] for m in matches), default=None)
        assert best_distance is None or best_distance > DISTANCE_THRESHOLD, (
            f"{question!r} scored {best_distance} -- expected it to exceed DISTANCE_THRESHOLD ({DISTANCE_THRESHOLD})"
        )


def test_hybrid_retrieval_recovers_a_no_entity_detected_miss_that_pure_vector_search_misses():
    """Aegislash-stats is a REAL miss for pure vector search at k=5 on this
    question (confirmed directly against the live index while writing this
    plan) -- BM25 ranks it #1 on the same question, so RRF fusion should
    recover it. This is the concrete, demonstrated benefit of hybrid
    retrieval, not just a smoke test."""
    records = json.loads(RECORDS_PATH.read_text())
    items = json.loads(ITEMS_PATH.read_text())
    golden_by_id = {entry["id"]: entry for entry in json.loads(GOLDEN_SET_PATH.read_text())}
    entry = golden_by_id["no-entity-stance-change-question"]

    index = _build_real_index(records, items, client=chromadb.Client())
    bm25_index = BM25Index(records, items)

    # Confirm the premise: pure vector search at k=5 misses it.
    vector_only_ids = {m["id"] for m in index.query(entry["question"], n_results=5)}
    assert entry["source_chunk_id"] not in vector_only_ids, (
        "premise check failed -- pure vector search no longer misses this question; "
        "pick a different no-entity-detected golden entry that's still a real miss"
    )

    # Hybrid retrieval (through the actual build_context_block path) recovers it.
    result = build_context_block(index, entry["question"], records=records, items=items, n_results=5, bm25_index=bm25_index)
    hybrid_ids = {chunk["id"] for chunk in result["retrieved_chunks"]}
    assert entry["source_chunk_id"] in hybrid_ids


def test_recall_at_5_through_hybrid_retrieval_does_not_regress():
    """Regression guard for the actual production retrieval path: neither
    test_recall_at_5_meets_the_threshold_against_the_real_index nor
    test_recall_at_5_through_entity_aware_retrieval_does_not_regress ever
    passes a bm25_index, so neither exercises hybrid (BM25+vector RRF)
    retrieval -- the fallback build_context_block uses whenever no entity is
    detected. This test routes every golden question through
    build_context_block itself (the same detect-then-filter-then-hybrid-
    fallback sequence it implements), with a real BM25Index supplied, and
    asserts recall@5 through THAT path equals the measured baseline (1.0000
    == 52/52) so any future regression is caught immediately."""
    records = json.loads(RECORDS_PATH.read_text())
    items = json.loads(ITEMS_PATH.read_text())
    golden_set = json.loads(GOLDEN_SET_PATH.read_text())

    index = _build_real_index(records, items, client=chromadb.Client())
    bm25_index = BM25Index(records, items)

    hits = 0
    misses = []
    for entry in golden_set:
        result = build_context_block(
            index, entry["question"], records=records, items=items, n_results=5, bm25_index=bm25_index
        )
        found_ids = {chunk["id"] for chunk in result["retrieved_chunks"]}
        if entry["source_chunk_id"] in found_ids:
            hits += 1
        else:
            misses.append(entry["id"])

    score = hits / len(golden_set)
    baseline = 1.0
    assert score == baseline, (
        f"hybrid recall@5 {score:.4f} dropped below the {baseline} measured baseline; misses: {misses}"
    )


def test_new_no_entity_golden_entries_detect_no_entity():
    """Confirms the premise these 4 entries were added for: none of them
    should trigger entity-aware filtering, so they actually exercise the
    unfiltered/hybrid retrieval path build_context_block falls back to."""
    records = json.loads(RECORDS_PATH.read_text())
    items = json.loads(ITEMS_PATH.read_text())
    golden_by_id = {entry["id"]: entry for entry in json.loads(GOLDEN_SET_PATH.read_text())}

    no_entity_ids = [
        "no-entity-stance-change-question",
        "no-entity-air-balloon-question",
        "no-entity-levitate-attack-question",
        "no-entity-burn-cure-question",
    ]
    for golden_id in no_entity_ids:
        entity = detect_entity(golden_by_id[golden_id]["question"], records, items)
        assert entity is None, f"{golden_id}: expected no entity detected, got {entity}"
