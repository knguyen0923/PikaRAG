# PikaRAG — Resume Point

Written when a session pauses mid-task (approaching the context-usage limit,
or right before a compaction) so work can pick back up without losing the
thread. If this says "nothing in progress," there's no live handoff — just
use `STATUS.md`.

**Paused at:** 2026-09-14, late evening (user asked to pivot to something
else, not a token-budget pause — safe to resume any time).
**Working on:** Local LLM migration Task 5 — physical hardware setup
connecting the live Oracle bot to a Windows laptop running Ollama. This is
**mid-troubleshooting, not finished** — see exact state below.
**Why paused:** User asked to note down what happened so far and switch
to a different task; this isn't a token-budget pause, just a deliberate
break with a network issue left unresolved.

**Done so far (Task 5, this session, 2026-09-14 evening):**
- Windows laptop (Dell Inspiron 14 7435 2-in-1, no dedicated GPU): Ollama
  installed via `winget`, pulled `llama3.2:latest` (3.2B Q4_K_M) and
  `nomic-embed-text`; confirmed both work locally
  (`curl localhost:11434/api/tags` from the laptop itself returns both).
  Tailscale installed and connected; laptop's Tailscale IP is
  `100.111.225.17`.
- Oracle instance (`193.122.155.20`, SSH via
  `ssh -i ~/.ssh/pikarag-oci.key ubuntu@193.122.155.20`): confirmed
  running current `main`. Edited `/opt/pikarag/.env` (as the `pikarag`
  user) to remove the stale unused `ANTHROPIC_API_KEY` line and add
  `LLM_HOST=100.111.225.17:11434` / `LLM_MODEL=llama3.2:3b`. Tailscale was
  **not previously installed** on this box (a gap versus what
  `docs/DEPLOYMENT.md` assumes) — installed and connected it this
  session. Restarted `pikarag-bot.service`; it comes up clean, connects to
  Discord's Gateway, `/ping` responds correctly.
- **Blocked on:** `curl http://100.111.225.17:11434/api/tags` run *from
  the Oracle box* hangs/times out, even though both machines show as
  connected peers on the same Tailscale network. Two suspected causes,
  neither yet applied/verified:
  1. Ollama defaults to binding only `127.0.0.1` — needs the Windows
     laptop's `OLLAMA_HOST` user environment variable set to
     `0.0.0.0:11434`, then Ollama restarted (quit + relaunch from the
     tray/Start menu).
  2. Windows Firewall likely blocking inbound TCP 11434 — needs, in an
     elevated PowerShell on the laptop:
     `New-NetFirewallRule -DisplayName "Ollama" -Direction Inbound
     -Protocol TCP -LocalPort 11434 -Action Allow`
- **Also flagged, not yet done:** the live Discord bot token got printed
  in plaintext into this chat session (via a `cat .env` over SSH) — it
  should be rotated in the Discord Developer Portal (Bot -> Reset Token)
  and the new value updated in the Oracle `.env`, independent of the LLM
  work.
- **Separate unresolved oddity, may be moot once the network is fixed:**
  earlier `/ask` attempts (before the missing-Tailscale-on-Oracle gap was
  discovered) returned Discord's generic "application did not respond"
  error with **zero corresponding lines** in
  `journalctl -u pikarag-bot.service -f` — no traceback, nothing. Only one
  bot process was confirmed running via `ps aux` (ruling out a
  duplicate-token conflict). Worth re-checking after the network fix; if
  `/ask` still fails silently with no server-side log output at all, that
  needs a proper `systematic-debugging` pass rather than more ad hoc log
  watching.

**Next step on resume:** on the Windows laptop, set
`OLLAMA_HOST=0.0.0.0:11434` (user environment variable) and add the
firewall rule above, restart Ollama, then from the Mac re-run
`ssh -i ~/.ssh/pikarag-oci.key ubuntu@193.122.155.20 "curl
http://100.111.225.17:11434/api/tags"` to confirm the Oracle box can now
reach it. Once that curl succeeds, retry `/ask <question>` in Discord with
`journalctl -u pikarag-bot.service -f` open on the Oracle box, and confirm
a real model-generated answer comes back (not just the offline-fallback
message) to close out Task 5.

**Older, already-shipped work (this session, 2026-09-13 through
2026-09-14), kept for context:**
- Local LLM migration (code): shipped, merged, pushed. `/ask` uses a local
  Ollama server instead of paid Claude Haiku. Full detail: `STATUS.md`'s
  "Local LLM migration" section.
- Eval harness: shipped, merged, pushed. `recall@5` gated in CI, measured
  0.9583. Full detail: `STATUS.md`'s "Eval harness" section.
- Verification + fix pass on all 6 unimplemented 2026-09-13 design specs
  (`eval-harness`, `retrieval-quality`, `grounding-trust`, `observability`,
  `reliability`, `ingestion-robustness`) — every one had real bugs, all now
  fixed and committed. See git log for the commits (`git log --oneline
  --all --grep="design specs"` or similar; committed 2026-09-14).
- Investigated 2 real retrieval misses the eval harness surfaced
  (`Abomasnow-moveset-learned-question`,
  `Dragalge-moveset-not-learned-question`) using systematic-debugging:
  root-caused to Mega Stone item chunks + stats chunks consistently
  outranking the correct moveset chunk for "Does X learn Y?" questions
  (confirmed via direct index queries, not guessed). Confirmed the
  already-approved `retrieval-quality-design.md` spec's entity-aware
  `where`-filter design fixes this exact failure mode. Added this evidence
  to the spec's Purpose section (commit `3d3991e`, local `main` only —
  **not yet pushed to origin** as of this write; `main` is 1 commit ahead
  of `origin/main`).

**In flight (not committed / not finished):**
- Nothing uncommitted. Working tree should be clean — verify with `git
  status` on resume regardless.

**Next step:** Run the `superpowers:writing-plans` skill on
`docs/superpowers/specs/2026-09-13-retrieval-quality-design.md` (already
fully reviewed and fixed, carries real measured evidence — no more
brainstorming needed). Then execute the resulting plan via
`superpowers:subagent-driven-development` (same pattern used for the local
LLM migration and eval harness plans this session: isolated worktree,
per-task implementer + reviewer dispatch, squash to one commit, final
whole-branch review, merge to `main`). After that, `STATUS.md`'s "Next up
after that" section lists 4 more design specs ready for the same
treatment (grounding-trust before observability specifically — the one
real cross-spec dependency; reliability and ingestion-robustness anytime).

**Open questions / decisions still needed:** None blocking — the path
forward is unambiguous. The only standing preference to carry forward:
this session's commit-cadence convention (implementers commit per task on
an isolated branch, squashed to one commit before merging) and the
established habit of pushing to origin only when explicitly asked, not
automatically after every merge.

---

## Prior resume point (2026-09-11, deployment) — historical, fully resolved

**Paused at:** 2026-09-11, deployment essentially complete — just waiting on
Discord's global slash-command propagation window (up to ~1hr).
**Why paused:** Nothing left to do but wait for `/ping` to actually appear
in Discord's slash-command picker. Resolved same day — `/ping` confirmed
working live in Discord on 2026-09-12 (see `STATUS.md`).

Full detail (Oracle Cloud instance recreation, `torch==2.6.0` pin fix,
systemd units, Discord invite snags) preserved in git history and in
memory `pikarag-oracle-deployment`/`pikarag-oracle-networking-gotchas` if
ever needed again — not reproduced here since it's fully resolved and
`STATUS.md` is the current source of truth for what's live.

---

## Template (overwrite the section above when pausing mid-task)

**Paused at:** <date>, ~<N>% of context budget used
**Working on:** <the task in one line>
**Why paused:** <token budget / imminent compaction>

**Done so far:**
- <bullet per completed step, with file paths / commit hashes>

**In flight (not committed / not finished):**
- <file path>: <what's half-done in it>

**Next step:** <the exact next action to take on resume — specific enough
that no re-derivation of context is needed>

**Open questions / decisions still needed:** <anything blocking that needs
the user's input>
