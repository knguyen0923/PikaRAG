#!/usr/bin/env bash
# Stop hook: nags (once per commit) to refresh STATUS.md when HEAD has moved
# past the commit recorded in its STATUS_COMMIT marker comment.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."

recorded=$(grep -oE 'STATUS_COMMIT: [0-9a-f]+' STATUS.md 2>/dev/null | awk '{print $2}' || true)
current=$(git rev-parse --short HEAD 2>/dev/null || true)

if [ -z "$recorded" ] || [ -z "$current" ] || [ "$recorded" = "$current" ]; then
  echo '{"continue": true}'
  exit 0
fi

# A commit that only touches STATUS.md is the marker-refresh commit itself —
# its own hash can never be known at the time it's written, so exclude
# STATUS.md-only diffs from the staleness check to avoid nagging forever.
changed=$(git diff --name-only "$recorded" "$current" -- . ':!STATUS.md' 2>/dev/null || true)
if [ -z "$changed" ]; then
  echo '{"continue": true}'
  exit 0
fi

reason="STATUS.md is stale: last updated at commit ${recorded}, but HEAD is now ${current}. Update STATUS.md (what changed, what's left, refresh the STATUS_COMMIT marker) before finishing, then stop again."
jq -n --arg r "$reason" '{decision: "block", reason: $r}'
