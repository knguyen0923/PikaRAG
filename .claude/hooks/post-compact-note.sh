#!/usr/bin/env bash
# PostCompact hook: safety net reminding Claude to reconstruct RESUME.md
# if a compaction happened before the token-budget checkpoint (see CLAUDE.md)
# caught it.
set -euo pipefail

note="A compaction just ran. If RESUME.md was not freshly updated immediately before this (check its Paused-at line), reconstruct it now from the compaction summary you just received: what was in progress, what is half-finished and where, and the exact next step. Then also verify STATUS.md's STATUS_COMMIT marker still matches the output of: git rev-parse --short HEAD"

jq -n --arg note "$note" '{hookSpecificOutput: {hookEventName: "PostCompact", additionalContext: $note}}'
