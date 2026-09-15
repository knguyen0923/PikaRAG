from bot.pokemon_lookup import find_record, not_found_message, usage_for_record


def usage_response(records: list, name: str, usage: dict = None) -> str:
    record = find_record(records, name)
    if record is None:
        return not_found_message(records, name)

    species_usage = usage_for_record(usage, record)
    if not species_usage:
        return f"{record['name']} has no usage data yet."

    lines = [f"{record['name']}'s usage data:"]
    if species_usage.get("items"):
        items_text = ", ".join(f"{i['name']} {i['usage_pct']}%" for i in species_usage["items"])
        lines.append(f"Items: {items_text}")
    if species_usage.get("abilities"):
        abilities_text = ", ".join(f"{a['name']} {a['usage_pct']}%" for a in species_usage["abilities"])
        lines.append(f"Abilities: {abilities_text}")
    if species_usage.get("moves"):
        moves_text = ", ".join(f"{m['name']} {m['usage_pct']}%" for m in species_usage["moves"])
        lines.append(f"Moves: {moves_text}")
    return "\n".join(lines)
