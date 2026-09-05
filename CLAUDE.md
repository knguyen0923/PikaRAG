# PikaRAG — Instructions for Claude

## Session handoff files

- `STATUS.md` — project state snapshot: what's done, what's left, pointers to docs
- `RESUME.md` — exact in-flight state when a session paused mid-task

## Token-budget checkpoint (read this every session)

Watch the `<total_tokens>N tokens left</total_tokens>` figure that appears in
`<system-reminder>` tags. When it drops to roughly **10% of the session's
starting budget** (i.e. ~90% used), stop the current task at the next safe
point and, before doing anything else:

1. Update `RESUME.md` with exactly what's in progress — done so far, what's
   still half-finished (with file paths), and the precise next step. Be
   specific enough that a fresh session with no memory of this conversation
   could pick it up correctly.
2. Update `STATUS.md`'s "Last updated" line, commit hash, and the
   `STATUS_COMMIT` marker comment to match current `git rev-parse --short HEAD`.
3. Tell the user you've paused and saved a resume point, in one sentence.

Do not wait for a hook to force this — by the time context is full enough to
trigger auto-compaction, detail has already started to degrade. This is a
proactive check you make yourself.

There is also a `PostCompact` hook configured in `.claude/settings.json` as a
safety net: if compaction happens without this checkpoint having fired (e.g.
a long single turn), it injects a reminder to reconstruct `RESUME.md` from
the fresh compaction summary immediately afterward.

## End-of-session status updates

A `Stop` hook in `.claude/settings.json` checks whether `HEAD` has moved past
the commit recorded in `STATUS.md`'s `STATUS_COMMIT` marker. If it has, it
blocks stopping once and asks you to refresh `STATUS.md` first — do that
directly (what changed, what's left, update the marker), then finish
normally. It only fires again after another commit lands, so it won't nag
about routine uncommitted edits mid-task.
