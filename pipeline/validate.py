REQUIRED_STATS = {"hp", "attack", "defense", "sp_attack", "sp_defense", "speed"}

# Independent of any source file's own declared count -- exists specifically
# to catch a corrupted/truncated legal-Pokemon source file whose own "count"
# field is also wrong (the existing written-vs-declared check in
# validate_write_count can't catch this, since it only compares a source
# file against itself). Confirmed from this project's own deployment
# history (STATUS.md: "315 -> 345 legal Pokemon" for the M-B -> M-C
# transition), not derived from any pipeline output. Add a regulation only
# once its live count is confirmed the same way M-C's was -- an
# unrecognized regulation (including old ones like M-B, now retired, and
# any synthetic test regulation) returns no problems: nothing to compare
# against, not a failure.
EXPECTED_REGULATION_COUNTS = {
    "M-C": 345,
}
COUNT_TOLERANCE = 0.05


def validate_records(records: list) -> list:
    """Returns a list of problems found; empty means valid."""
    problems = []
    for r in records:
        if not r.get("name"):
            problems.append(f"record missing name: {r}")
        if not r.get("learnset"):
            problems.append(f"{r.get('name', '?')} has an empty learnset")
        if not r.get("base_stats", {}).keys() >= REQUIRED_STATS:
            problems.append(f"{r.get('name', '?')} missing base stat fields")
    return problems


def validate_items(items: list) -> list:
    """Returns a list of problems found; empty means valid."""
    problems = []
    for item in items:
        if not item.get("name"):
            problems.append(f"item missing name: {item}")
        if not item.get("description"):
            problems.append(f"{item.get('name', '?')} has no description")
    return problems


def validate_usage(usage: dict, known_species: set) -> list:
    """Referential check only: every usage entry must reference a known
    species. Does NOT check for completeness -- a species legitimately
    having no usage data is not a problem this function detects (see the
    ingestion-robustness spec's Purpose section for why)."""
    problems = []
    for species in usage:
        if species not in known_species:
            problems.append(f"usage data references unknown species: {species}")
    return problems


def validate_legal_count(regulation: str, declared_count: int) -> list:
    """Sanity-checks a source file's own declared legal-Pokemon count
    against an independent, hard-coded expected size for that regulation.
    Catches a corrupted/truncated source file whose own count field is
    also wrong -- validate_write_count can't, since it only compares the
    source file against itself."""
    expected = EXPECTED_REGULATION_COUNTS.get(regulation)
    if expected is None:
        return []
    lower = expected * (1 - COUNT_TOLERANCE)
    upper = expected * (1 + COUNT_TOLERANCE)
    if not (lower <= declared_count <= upper):
        return [
            f"{regulation}'s legal Pokemon count is {declared_count}, expected "
            f"around {expected} (+/-{int(COUNT_TOLERANCE * 100)}%) -- source file "
            f"may be truncated or corrupted"
        ]
    return []


def validate_write_count(written: int, expected: int) -> list:
    """Compares how many records were actually written against the source
    file's own declared count. Any shortfall -- whether from a fetch
    failure or a corrupted source file -- is a hard failure under this
    project's validate-before-swap design: partial/incomplete data must
    not go live silently."""
    if written != expected:
        return [
            f"wrote {written} records but the source file declares {expected} "
            f"legal Pokemon ({expected - written} missing)"
        ]
    return []
