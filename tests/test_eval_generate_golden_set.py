from eval.generate_golden_set import (
    build_abilities_entry,
    build_item_entry,
    build_moveset_entry,
    build_stats_entry,
    generate_golden_set,
)

_KOMMOO = {
    "name": "Kommo-o",
    "types": ["Dragon", "Fighting"],
    "base_stats": {"hp": 75, "attack": 110, "defense": 125, "sp_attack": 100, "sp_defense": 105, "speed": 85},
    "abilities": ["Bulletproof", "Overcoat", "Soundproof"],
    "learnset": ["Close Combat", "Dragon Claw"],
    "legal_in": ["M-C"],
}

_LIFE_ORB = {"name": "Life Orb", "description": "Boosts move power by 30% at the cost of recoil HP."}

_MOVES_POOL = [
    {"name": "Close Combat", "type": "Fighting"},
    {"name": "Dragon Claw", "type": "Dragon"},
    {"name": "Tackle", "type": "Normal"},
]


def test_build_stats_entry_covers_every_stat_via_set_match():
    entry = build_stats_entry(_KOMMOO)

    assert entry["match_type"] == "set"
    assert entry["source_chunk_id"] == "Kommo-o-stats"
    assert "HP 75" in entry["expected"]
    assert "Attack 110" in entry["expected"]
    assert "Defense 125" in entry["expected"]
    assert "Sp. Atk 100" in entry["expected"]
    assert "Sp. Def 105" in entry["expected"]
    assert "Speed 85" in entry["expected"]


def test_build_abilities_entry_targets_the_stats_chunk():
    entry = build_abilities_entry(_KOMMOO)

    assert entry["match_type"] == "set"
    assert entry["expected"] == ["Bulletproof", "Overcoat", "Soundproof"]
    assert entry["source_chunk_id"] == "Kommo-o-stats"


def test_build_moveset_entry_for_a_learned_move_expects_yes():
    entry = build_moveset_entry(_KOMMOO, _MOVES_POOL, want_learned=True)

    assert entry["match_type"] == "exact"
    assert entry["expected"] == "Yes"
    assert "Close Combat" in entry["question"]
    assert entry["source_chunk_id"] == "Kommo-o-moveset"


def test_build_moveset_entry_for_a_not_learned_move_expects_no():
    entry = build_moveset_entry(_KOMMOO, _MOVES_POOL, want_learned=False)

    assert entry["match_type"] == "exact"
    assert entry["expected"] == "No"
    assert "Tackle" in entry["question"]  # first move in the pool not in Kommo-o's learnset


def test_build_item_entry_uses_substring_match_against_the_raw_description():
    entry = build_item_entry(_LIFE_ORB)

    assert entry["match_type"] == "substring"
    assert entry["expected"] == "Boosts move power by 30% at the cost of recoil HP."
    assert entry["source_chunk_id"] == "item-Life Orb"


def test_generate_golden_set_has_unique_ids():
    records = [dict(_KOMMOO, name=f"Mon{i}") for i in range(30)]
    items = [dict(_LIFE_ORB, name=f"Item{i}") for i in range(20)]

    golden_set = generate_golden_set(records, items, _MOVES_POOL)

    ids = [entry["id"] for entry in golden_set]
    assert len(ids) == len(set(ids))


def test_generate_golden_set_stays_within_the_target_size_range():
    records = [dict(_KOMMOO, name=f"Mon{i}") for i in range(345)]
    items = [dict(_LIFE_ORB, name=f"Item{i}") for i in range(197)]

    golden_set = generate_golden_set(records, items, _MOVES_POOL)

    assert 30 <= len(golden_set) <= 50


def test_generate_golden_set_alternates_learned_and_not_learned_across_records():
    records = [dict(_KOMMOO, name=f"Mon{i}") for i in range(4)]
    items = []

    golden_set = generate_golden_set(records, items, _MOVES_POOL)

    moveset_entries = [e for e in golden_set if "moveset" in e["id"]]
    expecteds = [e["expected"] for e in moveset_entries]
    assert expecteds == ["Yes", "No", "Yes", "No"]
