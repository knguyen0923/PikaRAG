# Pika-RAG: Ingestion Robustness — Design

Status: Approved
Date: 2026-09-13

## Purpose

The data pipeline (`pipeline/`) has no automated validation of its own
output today. This spec adds two independent checks — schema/count
validation and freshness/staleness detection — so a stuck or failing
refresh job, or a corrupted/truncated source file, is caught
automatically before it reaches the RAG index or the damage calculator,
rather than only by a person happening to notice.

These checks are not a response to, and would not have caught, the known
M-C Pikalytics format-code gap (documented in `STATUS.md`: two species,
Farfetch'd and Sirfetch'd, have no usage data specifically *because*
`PIKALYTICS_FORMAT_CODE` still points at M-B's ladder, since Pikalytics
hasn't published M-C's yet). That refresh ran successfully and on
schedule against the wrong regulation's ladder; it didn't fail or go
stale — verified directly against `data/processed/pikalytics_usage.json`,
which has usage entries for 208 of the 345 M-C-legal species. The other
~137 missing species are not evidence of the format-code bug: they're
legitimately unplayed/rare Pokemon with no usage on the current ranked
ladder at all, which is expected and correct, not a gap. A schema/count
check on the output JSON alone can't tell "missing because of the
format-code bug" apart from "missing because nobody plays this Pokemon" —
both look identical (absent from the file). A freshness check only asks
"did the job run recently," which it did; a species-count check on
`pokemon_records.json` (PokeAPI pipeline output) can't see a per-species
usage-coverage gap in the separate `pikalytics_usage.json` file
(Pikalytics pipeline output) — the two are structurally unrelated. The
checks below catch genuinely different
failure modes on their own merits: a stuck/failing cron job, and a
truncated/corrupted source file whose own self-reported count is also
wrong. See "Out of scope" for why detecting format-code drift /
regulation mismatches specifically is deliberately not attempted here.

## Scope

In scope:
- Schema validation of `pokemon_records.json`, `vgc_items.json`, and
  `pikalytics_usage.json` after each refresh job.
- A freshness/staleness check comparing the last successful refresh
  timestamp against an expected cadence.
- Aborting a refresh (keeping the last-known-good data live) if hard
  validation fails.

Out of scope (see "Out of scope" section for detail):
- A schema-validation library (Pydantic, jsonschema, etc.).
- Automated alerting beyond a log line (no Discord DM/webhook in this
  pass).
- Retroactively validating already-committed historical data.

## Schema validation

`pipeline/validate.py`, plain Python assertions rather than a new
dependency (Pydantic/jsonschema) — consistent with this project's
established preference (see [[local-llm-migration]], [[observability]])
for stdlib-only solutions where the check itself is simple enough not to
need a framework:

```python
def validate_records(records: list[dict]) -> list[str]:
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
```

Equivalent checks for `vgc_items.json` (name + description present) and
`pikalytics_usage.json` (usage entries reference known species — a
referential check, not a completeness one; see "Out of scope" for why
completeness detection isn't attempted here).

Also new: a sanity check that the total legal-Pokemon count is within a
plausible range of the current regulation's known size. This needs a new,
independent, hard-coded expected-count table (regulation -> expected
count) that this spec adds — no such table exists anywhere in the
pipeline today. It must be independent of, and not derived from, the
source file's own declared count: the only existing count check
(`pipeline/refresh_job.py:23`, `expected_count =
legal_data.get("count", len(legal_names))`) is circular — it validates a
source file's record count against that *same* source file's own
self-reported `count` field, so a corrupted or truncated source file
whose `count` field is also wrong (or also truncated) passes silently.
An independent, hard-coded table catches exactly that gap. This check
operates only on `pokemon_records.json`/the legal-Pokemon source list —
it says nothing about `pikalytics_usage.json` per-species coverage (see
"Purpose").

## Freshness check

`refresh_job.py` and `refresh_pikalytics_job.py` already run on a cadence
(systemd timers per `docs/DEPLOYMENT.md`) but neither writes any record of
when it last succeeded — this spec adds that. `run_refresh` (in
`refresh_job.py`) and `run_pikalytics_refresh` (in
`refresh_pikalytics_job.py`) each write a last-successful-refresh
timestamp on success. Because the two jobs run on independent schedules
(see below), each writes to its *own* file rather than sharing one — e.g.
`data/processed/.last_refresh_pokeapi.json` and
`data/processed/.last_refresh_pikalytics.json` — so the freshness check
can evaluate each job's own cadence independently.

A separate check — run as part of the same job, or as its own periodic
script — compares "now" against each timestamp; if either exceeds *that
job's own* expected threshold, logs a clear warning. The two jobs' actual
cadences differ (`deploy/systemd/pikarag-refresh-pokeapi.timer` is
weekly, `deploy/systemd/pikarag-refresh-pikalytics.timer` is monthly, per
`docs/DEPLOYMENT.md`), so a single shared threshold doesn't work: a
threshold loosely double each job's own cadence means ~14 days for the
PokeAPI job and ~60 days for the Pikalytics job. Using the PokeAPI job's
14-day threshold for Pikalytics too would false-positive as "stale" every
single month on a correctly-functioning refresh.

This check answers "did the job run recently" — it catches a stuck or
silently-failing cron job. It does not, and is not intended to, detect
whether a successful run fetched *correct* data (see "Purpose").

## Aborting on hard failure

Both refresh jobs already write to `data/processed/*.json`; this spec adds
a validate-before-swap step: write the new output to a temp path, run
`validate_records`/equivalent (including the new independent legal-count
check), and only replace the live file if there are no *hard* failures
(missing name, empty learnset, missing stat fields, or the legal-count
check tripping — things that would break retrieval or damage calc
outright, or indicate a corrupted source file). This keeps a broken
pipeline run from silently degrading the live bot with partial/malformed
data. The freshness check (above) is a separate, independent signal — it
doesn't participate in this validate-before-swap step at all, since it
isn't evaluating a specific refresh's output.

## Error handling

- Hard validation failure (schema problems, or the independent
  legal-count check tripping): refresh job logs the specific problems
  found, aborts the swap, keeps serving the previous data — matches this
  project's existing "grounding beats prompting, don't guess" philosophy
  applied to data instead of answers.
- Freshness/staleness is a logged warning only, not a swap-blocking
  condition — it runs independently of any single refresh and just
  signals that a job hasn't succeeded recently.
- Freshness check failing to find a last-refresh timestamp at all (first
  run, or file missing) is treated as "unknown," not "stale" — doesn't
  false-positive on a fresh setup.
- `pipeline/refresh_pikalytics_job.py` already has an existing
  all-or-nothing hard-failure guard (the `stale_format_code` check:
  `sys.exit` when every species comes back with zero usage data and
  nothing outright failed — the comment there already names a stale
  `PIKALYTICS_FORMAT_CODE` as the likely cause). This spec's new checks
  are additive to that guard, not a replacement for it. That guard also
  would not have caught the real M-C gap: it only fires on a *total*
  fetch failure (zero species with data), and the M-C run got data for
  208 of 345 species — nowhere close to zero.

## Testing plan

- `validate_records`/item/usage equivalents: unit tests against good
  fixture data (no problems) and deliberately broken fixtures (missing
  name, empty learnset, missing stats, wrong usage-species reference,
  legal-count mismatch against the new hard-coded table) — each expected
  problem type gets its own test.
- Refresh-job integration: a validation failure aborts the file swap
  (assert the live file is unchanged) and logs the problem; a clean run
  swaps normally, same as today.
- Freshness check: unit tests with a mocked "now" against various stored
  timestamps (fresh, stale, missing file), covering each job's own
  threshold (14 days PokeAPI / 60 days Pikalytics) and its own timestamp
  file.
- **Existing test needs rework:**
  `tests/test_refresh_job.py::test_run_refresh_reports_shortfall_when_a_fetch_fails`
  currently asserts a shortfall is reported *while the output file is
  still written* with the partial result (today `run_refresh` always
  calls `write_processed_records` unconditionally, before the
  written-vs-expected check in `__main__` even runs). Under this spec's
  validate-before-swap design, a shortfall like that should instead be a
  hard validation failure that leaves the live file unchanged — this
  test's expectations need to be updated to match the new behavior, not
  left as-is alongside new tests.

## Out of scope

- **A validation library** (Pydantic/jsonschema) — the checks needed are
  simple enough that plain assertions are clearer and add no dependency;
  revisit only if the validation logic grows complex enough that a
  declarative schema genuinely reads better than the equivalent Python.
- **Automated alerting beyond logs** (Discord DM to the bot owner, a
  webhook, etc.) — a clear log line is enough for a single-maintainer
  hobby project checking logs periodically; add real alerting if silent
  log-watching turns out to be insufficient in practice.
- **Retroactive validation of already-committed data** — this spec
  validates future refreshes going forward; it doesn't audit the data
  currently live.
- **Format-code drift / regulation-mismatch detection** — distinguishing
  "a species has no usage data because of a stale
  `PIKALYTICS_FORMAT_CODE`/fetch bug" from "a species has no usage data
  because it's legitimately unplayed this regulation" is a genuinely
  harder, currently undesigned problem. This is the actual failure class
  behind the M-C gap (see "Purpose"); the schema/freshness checks in this
  spec do not attempt to solve it, and no design for it is proposed here.
  A future spec is the right place to design real per-species
  usage-coverage detection, if it's worth building.
