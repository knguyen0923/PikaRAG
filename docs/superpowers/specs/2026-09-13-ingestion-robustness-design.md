# Pika-RAG: Ingestion Robustness — Design

Status: Approved
Date: 2026-09-13

## Purpose

The data pipeline (`pipeline/`) has no automated validation of its own
output today — the known M-C Pikalytics format-code gap (documented
manually in `STATUS.md`: two species have no usage data because Pikalytics
hasn't published a ranked-ladder code for the current regulation yet) was
caught by a person noticing, not by the pipeline itself. This spec adds
schema and freshness checks so a broken or stale refresh is caught
automatically, before it reaches the RAG index or the damage calculator.

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
`pikalytics_usage.json` (usage entries reference known species). Also: a
sanity check that the total legal-Pokemon count is within a plausible
range of the current regulation's known size (a hard-coded expected count
per regulation, updated the same place regulation-rotation logic already
lives) — this is exactly the kind of check that would have flagged a
Pikalytics gap earlier, though the specific M-C gap (missing usage data
for two species) is a usage-data completeness issue this spec treats as a
*warning*, not a hard failure, since two mons in a set of many missing
optional usage data (Pikalytics stats are supplementary, not required for
`/ask`/`/calc` to function) shouldn't block an otherwise-good refresh.

## Freshness check

`refresh_job.py` and `refresh_pikalytics_job.py` already run on a cadence
(systemd timers per `docs/DEPLOYMENT.md`); each writes a
last-successful-refresh timestamp (a small JSON file, e.g.
`data/processed/.last_refresh.json`) on success. A separate check —
run as part of the same job, or as its own periodic script — compares
"now" against that timestamp; if it exceeds an expected threshold (e.g. 14
days, loosely double the actual refresh cadence), logs a clear warning.
This is what would have surfaced the M-C Pikalytics gap as an automated
signal instead of a manually-noticed one.

## Aborting on hard failure

Both refresh jobs already write to `data/processed/*.json`; this spec adds
a validate-before-swap step: write the new output to a temp path, run
`validate_records`/equivalent, and only replace the live file if there are
no *hard* failures (missing name, empty learnset, missing stat fields —
things that would break retrieval or damage calc outright). Soft issues
(the usage-data-completeness warning above) are logged but don't block the
swap. This keeps a broken pipeline run from silently degrading the live
bot with partial/malformed data.

## Error handling

- Hard validation failure: refresh job logs the specific problems found,
  aborts the swap, keeps serving the previous data — matches this
  project's existing "grounding beats prompting, don't guess" philosophy
  applied to data instead of answers.
- Soft validation issues (usage-data gaps, etc.): logged, refresh proceeds
  — matches how the current M-C gap is already being handled (documented,
  not blocking).
- Freshness check failing to find a last-refresh timestamp at all (first
  run, or file missing) is treated as "unknown," not "stale" — doesn't
  false-positive on a fresh setup.

## Testing plan

- `validate_records`/item/usage equivalents: unit tests against good
  fixture data (no problems) and deliberately broken fixtures (missing
  name, empty learnset, missing stats, wrong usage-species reference) —
  each expected problem type gets its own test.
- Refresh-job integration: a validation failure aborts the file swap
  (assert the live file is unchanged) and logs the problem; a clean run
  swaps normally, same as today.
- Freshness check: unit tests with a mocked "now" against various stored
  timestamps (fresh, stale, missing file).

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
