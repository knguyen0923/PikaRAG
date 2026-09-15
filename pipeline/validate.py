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

# Some records (e.g. community-created Mega forms PokeAPI has no learnset
# data for -- verified against this repo's own data: Mega Absol Z, Mega
# Baxcalibur, Mega Garchomp Z, Mega Golisopod, Mega Lucario Z) legitimately
# have an empty learnset. A truly corrupted/truncated fetch would produce
# far more than a small, stable fraction of these -- close to 100% of
# records, not a handful -- so this is a proportional check, not a
# per-record one, mirroring validate_legal_count's tolerance pattern.
EMPTY_LEARNSET_TOLERANCE = 0.05


def validate_records(records: list) -> list:
    """Returns a list of problems found; empty means valid."""
    problems = []
    empty_learnset_names = []
    for r in records:
        if not r.get("name"):
            problems.append(f"record missing name: {r}")
        if not r.get("learnset"):
            empty_learnset_names.append(r.get("name", "?"))
        if not r.get("base_stats", {}).keys() >= REQUIRED_STATS:
            problems.append(f"{r.get('name', '?')} missing base stat fields")
    if records and len(empty_learnset_names) / len(records) > EMPTY_LEARNSET_TOLERANCE:
        shown = ", ".join(empty_learnset_names[:10])
        more = "..." if len(empty_learnset_names) > 10 else ""
        problems.append(
            f"{len(empty_learnset_names)}/{len(records)} records have an empty learnset "
            f"(over the {int(EMPTY_LEARNSET_TOLERANCE * 100)}% tolerance): {shown}{more}"
        )
    return problems


def validate_items(items: list) -> list:
    """Returns a list of problems found; empty means valid.

    Not currently wired into any refresh job's validate-before-swap gate --
    data/source/vgc_items.json is static source data with no refresh job
    that regenerates it, unlike pokemon_records.json/pikalytics_usage.json.
    Implemented per the ingestion-robustness spec's schema-validation scope
    and available for a future items-refresh job, or for manual/on-demand
    validation, if one is ever added."""
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
    ingestion-robustness spec's Purpose section for why).

    Note: in production, pipeline.refresh_pikalytics_job.run_pikalytics_refresh
    always passes usage data whose keys are drawn from the same legal-species
    list this function checks against, so this check can never actually find
    a problem in that call site today -- it exists as a general-purpose
    referential validator (e.g. useful if usage data is ever sourced or
    merged from elsewhere), not as active production protection. A shape
    check on usage entries' contents (moves/items/abilities present,
    usage_pct numeric) would give real teeth against a corrupted Pikalytics
    fetch, but that's a larger addition than this function's current scope."""
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
