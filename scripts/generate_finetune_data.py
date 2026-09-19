import json
from pathlib import Path

RECORDS_PATH = Path("data/processed/pokemon_records.json")
ITEMS_PATH = Path("data/source/vgc_items.json")
MOVES_PATH = Path("data/source/vgc_moves.json")
TRAIN_DATA_PATH = Path("data/finetune/train.jsonl")

_MOVES_PER_RECORD = 3


def build_stats_pairs(record: dict) -> list[dict]:
    name = record["name"]
    stats = record["base_stats"]
    full_answer = (
        f"{name} has base stats: HP {stats['hp']}, Attack {stats['attack']}, "
        f"Defense {stats['defense']}, Sp. Atk {stats['sp_attack']}, "
        f"Sp. Def {stats['sp_defense']}, Speed {stats['speed']}."
    )
    return [
        {"question": f"What are {name}'s base stats?", "answer": full_answer},
        {"question": f"What is {name}'s base HP?", "answer": f"{name}'s base HP is {stats['hp']}."},
    ]


def build_type_pairs(record: dict) -> list[dict]:
    name = record["name"]
    types = "/".join(record["types"])
    return [
        {"question": f"What type is {name}?", "answer": f"{name} is a {types}-type Pokemon."},
    ]


def build_ability_pairs(record: dict) -> list[dict]:
    name = record["name"]
    abilities = ", ".join(record["abilities"])
    return [
        {"question": f"What are {name}'s abilities?", "answer": f"{name}'s abilities are: {abilities}."},
        {
            "question": f"What abilities can {name} have?",
            "answer": f"{name} can have the following abilities: {abilities}.",
        },
    ]


def build_moveset_pairs(
    record: dict,
    moves_pool: list[dict],
    n_learned: int = _MOVES_PER_RECORD,
    n_not_learned: int = _MOVES_PER_RECORD,
) -> list[dict]:
    name = record["name"]
    learnset = record["learnset"]
    learnset_set = set(learnset)

    pairs = []
    for move in learnset[:n_learned]:
        pairs.append({"question": f"Does {name} learn {move}?", "answer": f"Yes, {name} learns {move}."})

    not_learned = [m["name"] for m in moves_pool if m["name"] not in learnset_set][:n_not_learned]
    for move in not_learned:
        pairs.append({"question": f"Does {name} learn {move}?", "answer": f"No, {name} does not learn {move}."})

    return pairs


def build_item_pairs(item: dict) -> list[dict]:
    name = item["name"]
    description = item["description"]
    return [
        {"question": f"What does {name} do?", "answer": f"{name}: {description}"},
        {"question": f"What is {name} used for?", "answer": description},
    ]


def generate_finetune_data(records: list[dict], items: list[dict], moves: list[dict]) -> list[dict]:
    pairs = []
    for record in records:
        pairs.extend(build_stats_pairs(record))
        pairs.extend(build_type_pairs(record))
        pairs.extend(build_ability_pairs(record))
        pairs.extend(build_moveset_pairs(record, moves))
    for item in items:
        pairs.extend(build_item_pairs(item))
    return pairs


def main() -> None:
    records = json.loads(RECORDS_PATH.read_text())
    items = json.loads(ITEMS_PATH.read_text())
    moves = json.loads(MOVES_PATH.read_text())["moves"]

    pairs = generate_finetune_data(records, items, moves)

    TRAIN_DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    with TRAIN_DATA_PATH.open("w") as f:
        for pair in pairs:
            f.write(json.dumps(pair) + "\n")
    print(f"Wrote {len(pairs)} training pairs to {TRAIN_DATA_PATH}")


if __name__ == "__main__":
    main()
