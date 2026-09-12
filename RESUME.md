# PikaRAG — Resume Point

Written when a session pauses mid-task (approaching the context-usage limit,
or right before a compaction) so work can pick back up without losing the
thread. If this says "nothing in progress," there's no live handoff — just
use `STATUS.md`.

**Paused at:** 2026-09-11, deployment essentially complete — just waiting on
Discord's global slash-command propagation window (up to ~1hr). Not a
token-budget pause; safe to resume any time, or just check back in Discord.
**Working on:** Same `docs/DEPLOYMENT.md` walkthrough as before. The Oracle
Cloud instance from the prior pause (2026-09-07/08) was successfully
recreated on 2026-09-11 and the bot is now live and connected to Discord's
gateway.
**Why paused:** Nothing left to do but wait for `/ping` to actually appear
in Discord's slash-command picker (global `tree.sync()` in `bot/main.py`
propagates over up to ~1hr for a bot's first-ever sync — this is normal
Discord platform behavior, not a bug). User chose to wait it out rather
than add a guild-scoped instant-sync for testing.

**Done so far (this session, 2026-09-11):**
- Recreated the Oracle Cloud instance (`project-pikarag`, `VM.Standard.A1.Flex`,
  Canonical Ubuntu 22.04 Minimal aarch64), public IP `193.122.155.20`. See
  memory `pikarag-oracle-deployment` for full connection details (SSH key
  at `~/.ssh/pikarag-oci.key`) and `pikarag-oracle-networking-gotchas` for
  the two real bugs hit along the way (manually-created VCNs don't get an
  Internet Gateway automatically; `cloud-init.sh`'s `useradd -m` + `git clone`
  ordering bug — the latter is **still unpatched in the repo**, worth fixing
  before the next from-scratch recreation).
- Bootstrap (`deploy/cloud-init.sh`'s steps) run manually over SSH, since the
  instance's "Initialization script" field was left blank at creation time.
  Repo cloned to `/opt/pikarag`, venv built, systemd units installed.
- Real secrets copied into the server's `/opt/pikarag/.env` via `scp` of the
  local `.env` (after two failed attempts hand-typing a heredoc, which
  corrupted the file with duplicated/garbage lines both times — `scp` of the
  already-correct local file was the fix).
- Both refresh pipelines run once: PokeAPI job clean (345/345 from cache);
  Pikalytics job wrote real data for 208/210 attempted species. The 2
  failures (Farfetch'd, Sirfetch'd) are **not a bug** — confirmed via direct
  curl tests against Pikalytics plus `git log` — those two are newly-legal
  in M-C and were never in M-B, and `PIKALYTICS_FORMAT_CODE` still points at
  M-B's format code (already a tracked open item below). Nothing to fix here.
- Found and fixed a real bug: `pip install -r requirements.txt` was resolving
  `torch==2.14.0`, which crashes on any `sentence_transformers`/`transformers`
  import (`ValueError: Duplicate dispatch rule for <built-in function intern>`
  inside `torch._dynamo` triggered via `transformers`' flex_attention
  integration). Fixed by pinning `torch==2.6.0` in `requirements.txt`
  (confirmed via direct import test) — **committed to the repo**
  (uncommitted as of this write; see next step). Installed live in the
  server's venv already, bot confirmed running past this point.
- All three systemd units enabled and running:
  `pikarag-bot.service` (active, connected to Discord gateway as of
  `2026-09-12 00:48:02 UTC`), `pikarag-refresh-pokeapi.timer`,
  `pikarag-refresh-pikalytics.timer`.
- Discord invite: hit two snags along the way — (1) the app had "Requires
  OAuth2 Code Grant" enabled in Bot settings, which broke the simple invite
  link until turned off; (2) had to select Guild Install (not User Install)
  and manually add a placeholder OAuth2 redirect (`https://discord.com`,
  unused by the actual bot-scope invite flow) to satisfy an unrelated form
  validation. Bot is now a member of the target server.

**In flight (not committed / not finished):**
- `requirements.txt`'s `torch==2.6.0` pin — committed and pushed
  (`3431f78`). This bullet is stale, no longer in flight.
- `deploy/cloud-init.sh`'s `useradd -m`/`git clone` bug (see memory
  `pikarag-oracle-networking-gotchas`) is still unpatched in the repo.

**Next step:** Nothing required — just check Discord in 15-60 min and try
`/ping`. If it still doesn't respond after ~an hour, that's when it'd be
worth actually investigating (check `sudo journalctl -u pikarag-bot.service
-f` on the server for errors) rather than assuming it's still propagation
delay. Everything else from the original deployment checklist is done
(instance up, bootstrap complete, secrets in place, pipelines run, systemd
units running, torch fix committed+pushed). Remaining loose ends, all
low-priority: flip the published legal-docs Artifact
(`https://claude.ai/code/artifact/c8af5a8a-f5ad-420c-8dfe-9d260f6d0ea7`) to
public/shareable before submitting the bot anywhere that verifies those
URLs; patch `cloud-init.sh`'s useradd/git-clone bug before the next
from-scratch instance recreation; re-verify `PIKALYTICS_FORMAT_CODE` once
Pikalytics publishes an M-C ranked ladder.

**Open questions / decisions still needed:**
- Whether to patch the `cloud-init.sh` bug now (low urgency — only matters
  on the next from-scratch instance recreation) or leave it for later.

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
