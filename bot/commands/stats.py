from bot.pokemon_lookup import find_record, not_found_message


def stats_response(records: list, name: str, usage: dict = None) -> str:
    record = find_record(records, name)
    if record is None:
        return not_found_message(records, name)

    types = "/".join(record["types"])
    stats = record["base_stats"]
    abilities = ", ".join(record["abilities"])
    response = (
        f"{record['name']} ({types}) — "
        f"HP {stats['hp']} / Atk {stats['attack']} / Def {stats['defense']} / "
        f"SpA {stats['sp_attack']} / SpD {stats['sp_defense']} / Spe {stats['speed']}. "
        f"Abilities: {abilities}."
    )

    species_usage = (usage or {}).get(record["name"])
    if species_usage:
        build_parts = []
        if species_usage.get("items"):
            top_item = species_usage["items"][0]
            build_parts.append(f"{top_item['usage_pct']}% {top_item['name']}")
        if species_usage.get("abilities"):
            top_ability = species_usage["abilities"][0]
            build_parts.append(f"{top_ability['usage_pct']}% {top_ability['name']}")
        if build_parts:
            response += f" Common build: {', '.join(build_parts)}."

    return response
