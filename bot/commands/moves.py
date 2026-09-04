from bot.pokemon_lookup import find_record, not_found_message


def moves_response(records: list, name: str) -> str:
    record = find_record(records, name)
    if record is None:
        return not_found_message(records, name)

    moves = ", ".join(record["learnset"])
    return f"{record['name']}'s legal moveset: {moves}."
