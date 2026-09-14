import re


def matches(actual: str, expected, match_type: str) -> bool:
    """Checks whether `actual` (an LLM's free-text answer) satisfies `expected`.

    A full free-text answer will essentially never equal a bare expected
    value like "91" or "Yes" verbatim, so "exact" means a whole-word,
    case-insensitive match within the answer -- not string equality. This
    also avoids a plain substring check's false positive on short words
    (e.g. "no" matching inside "known").
    """
    actual_lower = actual.lower()
    if match_type == "exact":
        pattern = r"\b" + re.escape(expected.lower()) + r"\b"
        return re.search(pattern, actual_lower) is not None
    if match_type == "set":
        return all(item.lower() in actual_lower for item in expected)
    if match_type == "substring":
        return expected.lower() in actual_lower
    raise ValueError(f"unknown match_type: {match_type!r}")
