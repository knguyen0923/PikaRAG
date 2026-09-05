from bot.pokemon_lookup import find_record, not_found_message, usage_for_record


def moves_response(records: list, name: str, usage: dict = None) -> str:
    record = find_record(records, name)
    if record is None:
        return not_found_message(records, name)

    species_usage = usage_for_record(usage, record)
    top_moves = species_usage.get("moves") if species_usage else None
    if top_moves:
        moves_text = ", ".join(f"{m['name']} {m['usage_pct']}%" for m in top_moves)
        return f"{record['name']}'s top moves (by usage): {moves_text}."

    if not record["learnset"]:
        return f"{record['name']} has no legal moves on record."

    moves = ", ".join(record["learnset"])
    return f"{record['name']}'s legal moveset: {moves}."
