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


def format_with_suggestions(base_message: str, suggestions: list) -> str:
    """Append a "Did you mean: ...?" clause to `base_message` when there are
    close-match suggestions, shared by every not-found/not-recognized message
    in the bot so a wording change only has one place to make it.
    """
    if suggestions:
        return f"{base_message} Did you mean: {', '.join(suggestions)}?"
    return base_message


def not_found_message(records: list, name: str, kind: str = "Pokemon") -> str:
    suggestions = suggest_names(records, name)
    return format_with_suggestions(f"No {kind} found matching '{name}'.", suggestions)


def usage_for_record(usage: dict, record: dict):
    """Look up one resolved record's Pikalytics usage entry, if any.

    `usage` may be None (no usage data loaded at all); shared here so
    /stats and /moves don't each re-derive the same None-safe lookup.
    """
    return (usage or {}).get(record["name"])
