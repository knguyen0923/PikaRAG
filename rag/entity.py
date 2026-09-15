import re
from typing import Optional

from bot.pokemon_lookup import find_record, suggest_names

_BRACKET_SUFFIX = re.compile(r"\s*\[([^\]]+)\]$")
_MEGA_PREFIX = "Mega "
_MAX_BASE_NGRAM_WORDS = 2
_MIN_FUZZY_WORD_LEN = 4


def _species_key(name: str) -> str:
    """Canonical species/item name a form-variant's full record name
    reduces to, so e.g. "Abomasnow" and "Mega Abomasnow" group together."""
    stripped = _BRACKET_SUFFIX.sub("", name).strip()
    if stripped.startswith(_MEGA_PREFIX):
        stripped = stripped[len(_MEGA_PREFIX):]
    # Trailing Mega-form letter, e.g. "Charizard X" -> "Charizard".
    stripped = re.sub(r"\s+[A-Z]$", "", stripped)
    return stripped.strip().lower()


def _qualifier_word(name: str) -> Optional[str]:
    """The word a question must contain to pick this variant over its base
    form; None for a plain/unqualified record name."""
    bracket_match = _BRACKET_SUFFIX.search(name)
    if bracket_match:
        first_word = re.match(r"[A-Za-z]+", bracket_match.group(1))
        return first_word.group(0).lower() if first_word else None
    if name.startswith(_MEGA_PREFIX):
        return "mega"
    return None


def _word_present(question_lower: str, word: str) -> bool:
    return re.search(r"\b" + re.escape(word.lower()) + r"\b", question_lower) is not None


def _question_ngrams(question: str, max_words: int) -> list:
    words = re.findall(r"[A-Za-z0-9]+", question)
    ngrams = []
    for size in range(min(max_words, len(words)), 0, -1):
        for start in range(len(words) - size + 1):
            ngrams.append(" ".join(words[start : start + size]))
    return ngrams


def _base_records(candidates: list) -> list:
    """One representative record per species/item family: the plain,
    unqualified record (no Mega prefix, no bracketed form suffix)."""
    return [c for c in candidates if _qualifier_word(c["name"]) is None]


def _find_species(question: str, bases: list) -> Optional[dict]:
    """Resolve which known species/item family the question is about.
    Exact match first (reusing find_record as-is), falling back to
    fuzzy/typo matching (reusing suggest_names as-is) when nothing matches
    exactly."""
    for ngram in _question_ngrams(question, _MAX_BASE_NGRAM_WORDS):
        record = find_record(bases, ngram)
        if record:
            return record
    words = sorted(set(re.findall(r"[A-Za-z0-9]+", question)), key=len, reverse=True)
    for word in words:
        if len(word) < _MIN_FUZZY_WORD_LEN:
            continue
        suggestions = suggest_names(bases, word, n=1)
        if suggestions:
            return find_record(bases, suggestions[0])
    return None


def _resolve_variant(question_lower: str, base: dict, candidates: list) -> Optional[dict]:
    """Given the recognized base species/item, pick the specific
    Mega/regional-form variant the question means, fall back to the base
    when no variant is specifically named, or signal genuine ambiguity
    (None) when more than one variant's qualifying word is present."""
    key = _species_key(base["name"])
    variants = [c for c in candidates if c is not base and _species_key(c["name"]) == key]
    if not variants:
        return base
    qualified = [v for v in variants if _word_present(question_lower, _qualifier_word(v["name"]))]
    if not qualified:
        return base
    if len(qualified) == 1:
        return qualified[0]
    return None


def _resolve(question: str, candidates: list) -> Optional[dict]:
    if not candidates:
        return None
    bases = _base_records(candidates)
    base = _find_species(question, bases)
    if base is None:
        return None
    return _resolve_variant(question.lower(), base, candidates)


def detect_entity(question: str, records: list, items: list) -> Optional[dict]:
    """Detect a known Pokemon or item name mentioned in a free-text question.

    Returns {"field": "pokemon", "name": <canonical name>} or
    {"field": "item", "name": <canonical name>}, or None when nothing is
    recognized, or recognition is genuinely ambiguous between two
    form-variants (see the retrieval-quality design's tie-breaking rules).
    """
    pokemon_match = _resolve(question, records or [])
    if pokemon_match:
        return {"field": "pokemon", "name": pokemon_match["name"]}
    item_match = _resolve(question, items or [])
    if item_match:
        return {"field": "item", "name": item_match["name"]}
    return None
