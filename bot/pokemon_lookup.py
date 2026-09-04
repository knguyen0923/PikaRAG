import difflib


def find_record(records: list, name: str):
    """Case-insensitive exact-name lookup. Returns the record dict or None."""
    target = name.strip().lower()
    for record in records:
        if record["name"].strip().lower() == target:
            return record
    return None


def suggest_names(records: list, name: str, n: int = 3) -> list:
    """Nearest-name suggestions for a lookup that missed, closest first."""
    names = [record["name"] for record in records]
    return difflib.get_close_matches(name, names, n=n)


def not_found_message(records: list, name: str) -> str:
    suggestions = suggest_names(records, name)
    if suggestions:
        return f"No Pokemon found matching '{name}'. Did you mean: {', '.join(suggestions)}?"
    return f"No Pokemon found matching '{name}'."
