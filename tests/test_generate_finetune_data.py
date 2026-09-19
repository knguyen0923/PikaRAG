from scripts.generate_finetune_data import (
    build_ability_pairs,
    build_item_pairs,
    build_moveset_pairs,
    build_stats_pairs,
    build_type_pairs,
    generate_finetune_data,
)

_KOMMOO = {
    "name": "Kommo-o",
    "types": ["Dragon", "Fighting"],
    "base_stats": {"hp": 75, "attack": 110, "defense": 125, "sp_attack": 100, "sp_defense": 105, "speed": 85},
    "abilities": ["Bulletproof", "Overcoat", "Soundproof"],
    "learnset": ["Close Combat", "Dragon Claw", "Flamethrower", "Poison Jab"],
}

_LIFE_ORB = {"name": "Life Orb", "description": "Boosts move power by 30% at the cost of recoil HP."}

_MOVES_POOL = [
    {"name": "Close Combat"},
    {"name": "Dragon Claw"},
    {"name": "Flamethrower"},
    {"name": "Poison Jab"},
    {"name": "Tackle"},
    {"name": "Splash"},
    {"name": "Rest"},
]


def test_build_stats_pairs_covers_full_stat_line_and_a_single_stat():
    pairs = build_stats_pairs(_KOMMOO)

    assert len(pairs) == 2
    full = next(p for p in pairs if "base stats" in p["question"])
    assert "HP 75" in full["answer"]
    assert "Attack 110" in full["answer"]
    assert "Defense 125" in full["answer"]
    assert "Sp. Atk 100" in full["answer"]
    assert "Sp. Def 105" in full["answer"]
    assert "Speed 85" in full["answer"]

    hp_only = next(p for p in pairs if "base HP" in p["question"])
    assert "75" in hp_only["answer"]


def test_build_type_pairs_names_both_types():
    pairs = build_type_pairs(_KOMMOO)

    assert len(pairs) == 1
    assert "Dragon" in pairs[0]["answer"]
    assert "Fighting" in pairs[0]["answer"]


def test_build_ability_pairs_lists_every_ability_in_both_templates():
    pairs = build_ability_pairs(_KOMMOO)

    assert len(pairs) == 2
    for pair in pairs:
        assert "Bulletproof" in pair["answer"]
        assert "Overcoat" in pair["answer"]
        assert "Soundproof" in pair["answer"]


def test_build_moveset_pairs_yields_learned_and_not_learned_pairs():
    pairs = build_moveset_pairs(_KOMMOO, _MOVES_POOL, n_learned=2, n_not_learned=2)

    learned = [p for p in pairs if p["answer"].startswith("Yes")]
    not_learned = [p for p in pairs if p["answer"].startswith("No")]
    assert len(learned) == 2
    assert len(not_learned) == 2
    assert "Close Combat" in learned[0]["question"]
    assert "Tackle" in not_learned[0]["question"]
    assert "Tackle" in not_learned[0]["answer"]


def test_build_item_pairs_uses_the_raw_description_in_both_templates():
    pairs = build_item_pairs(_LIFE_ORB)

    assert len(pairs) == 2
    assert all("Life Orb" in p["question"] or "Life Orb" in p["answer"] for p in pairs)
    assert any(p["answer"] == "Boosts move power by 30% at the cost of recoil HP." for p in pairs)


def test_generate_finetune_data_covers_every_record_and_item():
    records = [dict(_KOMMOO, name=f"Mon{i}") for i in range(5)]
    items = [dict(_LIFE_ORB, name=f"Item{i}") for i in range(3)]

    pairs = generate_finetune_data(records, items, _MOVES_POOL)

    questions = " ".join(p["question"] for p in pairs)
    for i in range(5):
        assert f"Mon{i}" in questions
    for i in range(3):
        assert f"Item{i}" in questions


def test_generate_finetune_data_produces_more_pairs_than_the_golden_set_needs():
    # The spec calls for "more template variety per field than the 48-question
    # golden set needs" -- one record alone should already clear a handful of
    # pairs across all field types (2 stats + 1 type + 2 ability + up to 6
    # moveset = 11 for a single record with a large enough learnset/pool).
    pairs = generate_finetune_data([_KOMMOO], [], _MOVES_POOL)

    assert len(pairs) >= 8
