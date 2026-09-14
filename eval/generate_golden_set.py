import json
from pathlib import Path

RECORDS_PATH = Path("data/processed/pokemon_records.json")
ITEMS_PATH = Path("data/source/vgc_items.json")
MOVES_PATH = Path("data/source/vgc_moves.json")
GOLDEN_SET_PATH = Path("data/eval/golden_set.json")

_RECORD_SAMPLE_SIZE = 12
_ITEM_SAMPLE_SIZE = 8


def _sample(pool: list, target_count: int) -> list:
    if not pool:
        return []
    step = max(1, len(pool) // target_count)
    return pool[::step]


def build_stats_entry(record: dict) -> dict:
    name = record["name"]
    stats = record["base_stats"]
    return {
        "id": f"{name}-stats-question",
        "question": f"What are {name}'s base stats?",
        "match_type": "set",
        "expected": [
            f"HP {stats['hp']}",
            f"Attack {stats['attack']}",
            f"Defense {stats['defense']}",
            f"Sp. Atk {stats['sp_attack']}",
            f"Sp. Def {stats['sp_defense']}",
            f"Speed {stats['speed']}",
        ],
        "source_chunk_id": f"{name}-stats",
    }


def build_abilities_entry(record: dict) -> dict:
    name = record["name"]
    return {
        "id": f"{name}-abilities-question",
        "question": f"What are {name}'s abilities?",
        "match_type": "set",
        "expected": list(record["abilities"]),
        "source_chunk_id": f"{name}-stats",
    }


def build_moveset_entry(record: dict, moves_pool: list[dict], want_learned: bool) -> dict:
    name = record["name"]
    learnset = record["learnset"]
    if want_learned:
        move = learnset[0]
        expected = "Yes"
        suffix = "moveset-learned"
    else:
        learnset_set = set(learnset)
        move = next(m["name"] for m in moves_pool if m["name"] not in learnset_set)
        expected = "No"
        suffix = "moveset-not-learned"
    return {
        "id": f"{name}-{suffix}-question",
        "question": f"Does {name} learn {move}?",
        "match_type": "exact",
        "expected": expected,
        "source_chunk_id": f"{name}-moveset",
    }


def build_item_entry(item: dict) -> dict:
    name = item["name"]
    return {
        "id": f"item-{name}-question",
        "question": f"What does {name} do?",
        "match_type": "substring",
        "expected": item["description"],
        "source_chunk_id": f"item-{name}",
    }


def generate_golden_set(records: list[dict], items: list[dict], moves: list[dict]) -> list[dict]:
    sampled_records = _sample(records, _RECORD_SAMPLE_SIZE)
    sampled_items = _sample(items, _ITEM_SAMPLE_SIZE)

    entries = []
    for i, record in enumerate(sampled_records):
        entries.append(build_stats_entry(record))
        entries.append(build_abilities_entry(record))
        entries.append(build_moveset_entry(record, moves, want_learned=(i % 2 == 0)))
    for item in sampled_items:
        entries.append(build_item_entry(item))

    ids = [entry["id"] for entry in entries]
    if len(ids) != len(set(ids)):
        raise ValueError("generated golden set has duplicate ids -- sampled records/items must have unique names")
    return entries


def main() -> None:
    records = json.loads(RECORDS_PATH.read_text())
    items = json.loads(ITEMS_PATH.read_text())
    moves = json.loads(MOVES_PATH.read_text())["moves"]

    golden_set = generate_golden_set(records, items, moves)

    GOLDEN_SET_PATH.parent.mkdir(parents=True, exist_ok=True)
    GOLDEN_SET_PATH.write_text(json.dumps(golden_set, indent=2) + "\n")
    print(f"Wrote {len(golden_set)} golden entries to {GOLDEN_SET_PATH}")


if __name__ == "__main__":
    main()
