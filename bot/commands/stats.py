from bot.pokemon_lookup import find_record, not_found_message


def stats_response(records: list, name: str) -> str:
    record = find_record(records, name)
    if record is None:
        return not_found_message(records, name)

    types = "/".join(record["types"])
    stats = record["base_stats"]
    abilities = ", ".join(record["abilities"])
    return (
        f"{record['name']} ({types}) — "
        f"HP {stats['hp']} / Atk {stats['attack']} / Def {stats['defense']} / "
        f"SpA {stats['sp_attack']} / SpD {stats['sp_defense']} / Spe {stats['speed']}. "
        f"Abilities: {abilities}."
    )
