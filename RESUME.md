# PikaRAG — Resume Point

Written when a session pauses mid-task (approaching the context-usage limit,
or right before a compaction) so work can pick back up without losing the
thread. If this says "nothing in progress," there's no live handoff — just
use `STATUS.md`.

**Paused at:** 2026-09-07, mid deployment walkthrough (not a token-budget pause —
just where the session left off; safe to resume any time). Re-confirmed
still accurate as of 2026-09-10 — an intervening session did unrelated code
work (Regulation M-C data rollout, a slug-resolution bugfix, wiring
`vgc_items.json` into RAG/`calc`/`scout` — see `STATUS.md`) and never
touched this deployment thread, so everything below is unchanged.
**Working on:** Working through `docs/DEPLOYMENT.md` step by step with the user
to actually deploy PikaRAG (Discord bot config, Anthropic key, Oracle Cloud
instance, systemd).
**Why paused:** Session ended for the day; Oracle Cloud instance needed to be
recreated (networking misconfig) and that requires the user's next action in
the console.

**Done so far:**
- Discord: bot created, token generated, OAuth2 URL Generator permissions set
  (`bot` scope, Send Messages + Use Slash Commands), bot invited to server,
  bot description written, `Intents.default()` confirmed sufficient (no
  privileged intents needed since all commands are slash commands).
- ToS + Privacy Policy: drafted and published as a Claude Artifact (two docs,
  one page, anchor-linked) at
  `https://claude.ai/code/artifact/c8af5a8a-f5ad-420c-8dfe-9d260f6d0ea7`
  (`#terms-top` and `#privacy-top`). **The artifact is private by default —
  needs its share menu set to public/viewable before Discord's bot
  verification can actually fetch these URLs.** Not yet confirmed done.
- Anthropic: spend cap set to $5 (deliberately low for initial testing, per
  cost estimate: Haiku 4.5 model in `rag/answer.py`, ~$0.003-0.007/query, no
  rate-limiting on `/ask` in code so cap doubles as an abuse ceiling). API
  key created.
- Local `.env` (`/Users/knguyen/VSC/PikaRAG/PikaRAG/.env`, gitignored) now has
  both `DISCORD_TOKEN` and `ANTHROPIC_API_KEY` populated and verified
  non-empty (values not inspected/printed, only presence checked).
- Wrote `deploy/cloud-init.sh` (new file, untracked as of this pause) — an
  Oracle Cloud "Initialization script" that automates apt installs, creates
  the `pikarag` system user, clones the repo, sets up the venv + pip install,
  stages (but does not enable) the systemd units. Deliberately does NOT write
  real secrets into `.env` or enable the bot, since instance metadata /
  cloud-init scripts are visible to anyone with console access to the
  instance.
- First Oracle Cloud instance attempt: created with shape `VM.Standard.A1.Flex`
  (1 OCPU/6GB, ARM, Ubuntu 22.04), but the "Public IPv4 address" toggle was
  left at "No" during creation, which caused Oracle to provision the subnet
  as a **private subnet** (no internet gateway route) — this is a
  subnet-level property, not fixable per-instance after the fact (confirmed:
  no "reserve/add public IP" option available on the VNIC's private IP, only
  NSG editing). User terminated this instance (with boot volume deleted) per
  agreement in this session.

**In flight (not committed / not finished):**
- `deploy/cloud-init.sh` — since committed (`c245e3b`, prior session); this
  bullet is stale, no longer in flight.
- Oracle Cloud instance needs to be recreated from scratch. Names agreed on:
  VCN `pikarag-vcn`, subnet `pikarag-subnet`, VNIC `pikarag-vnic` (DNS Label
  sub-fields, if used, must be alphanumeric-only / no hyphens / max 15 chars,
  e.g. `pikaragvcn` / `pikaragsub` -- separate from the hyphenated Display
  Name fields, which are fine as typed).
- Oracle billing/account setup (payment verification, home region choice)
  was already completed by the user before the first (failed) instance
  attempt, so recreation should just be the instance-creation flow, not
  full account setup again.

**Next step:** Guide the user through recreating the Oracle Cloud instance,
this time confirming **Public IPv4 address = Yes** is set *first*, before
touching VCN/subnet/VNIC name fields or anything else in Networking. Reuse
`deploy/cloud-init.sh` as the Initialization script. After the instance is
up with a real public IP: SSH in, confirm cloud-init finished
(`cat /var/log/pikarag-bootstrap-done.log`), fill in the real `.env` on the
server, run both pipeline refresh jobs once, then enable the three systemd
units (`pikarag-bot.service`, `pikarag-refresh-pokeapi.timer`,
`pikarag-refresh-pikalytics.timer`). Also remember to flip the published
legal-docs Artifact to public/shareable before submitting the bot anywhere
that verifies those URLs.

**Open questions / decisions still needed:**
- Whether to enable Shielded Instance (Secure Boot/Measured Boot/TPM) on the
  recreated instance — recommended but optional, was left Disabled on the
  terminated attempt and never explicitly revisited.

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
