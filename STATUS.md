# PikaRAG — Status

Point Claude at this file after `/clear` to pick up where things left off.
This is a snapshot, not a source of truth — always re-verify against the repo
(`git log`, `git status`, `pytest -q`) rather than trusting this blindly if
it's been a while. Detailed build history (bug postmortems, review findings,
per-feature commit ranges) lives in `git log` and the design docs under
`docs/superpowers/`, not here — this file tracks current state only.

If `RESUME.md` says anything other than "nothing in progress," read it
first — it holds exact in-flight state from a session that paused mid-task,
which is more specific than this snapshot.

## Current state

Deployed and live: Discord bot on Oracle Cloud (Always Free tier, systemd,
always-on, $0/month), `/ask` served by self-hosted Ollama (`qwen3.5:9b`,
a thinking model) on a MacBook reached over Tailscale, $0 per query — no
metered API anywhere in the system. 648/648 tests passing, CI green
(lint + coverage + pinned-dep checks). Data current for Regulation M-C
(345 legal Pokémon, 197 items).

Bot presence now set explicitly on connect (2026-09-22, commit `5c43eb0`):
`on_ready` calls `client.change_presence(status=online, activity=Game("/ask"))`
in `bot/main.py`, so the bot shows online with a "Playing /ask" status while
the process is running and flips to offline automatically when it exits —
purely cosmetic, no change to connect/disconnect behavior (still
`client.run(token)`, blocking until the process is killed).

Added mention-triggered Q&A (2026-09-21, commit `88fcbef`): a new
`MENTION_CHANNEL_IDS` env var lets people @mention the bot for a one-off
answer (`bot/conversation.py`'s `should_respond_to_mention`/
`strip_bot_mention`) in channels separate from the always-on
`CONVERSATION_CHANNEL_IDS` chat channels — no rolling history kept for
mention answers. Not yet deployed to the live Oracle instance.

A code-review polish pass (2026-09-20/21, commit `db24ca3`) fixed 6 bugs
in the conversational chat feature: the privileged `message_content`
intent was requested unconditionally instead of only when
`CONVERSATION_CHANNEL_IDS` is set (would have crashed the whole bot's
gateway connection on any deployment upgrading without a matching portal
change), unguarded `int()` parsing of that env var, `on_message` replies
with no 2000-char truncation or empty-content guard, `GATE_MESSAGE`
missing from the history-exclusion check, `should_respond` not filtering
content-less messages, and a blocking `answer_with_tools` call left
un-threaded on the event loop. Pulled and restarted on the live Oracle
instance same-day; gateway reconnect confirmed clean in
`journalctl -u pikarag-bot.service`.

Also noted but **not yet investigated**: a `/ask` call in the live logs
failed with `Could not resolve authentication method... api_key/
auth_token/credentials` (looks like a ChromaDB client auth error) —
unrelated to the chat fixes above, pre-existing, needs a follow-up
session.

## Shipped features

One line each — see the plan/spec doc for implementation detail, or
`git log --oneline --grep=<topic>` for the commit history.

- **Core RAG `/ask`** — Chroma vector store + `rag/bm25.py` hybrid
  (Reciprocal Rank Fusion) retrieval, entity-aware filtering
  (`rag/entity.py`) for known Pokémon/item names, a confidence gate that
  refuses to answer out-of-domain questions, source citations.
- **`/analyze`** — agentic variant of `/ask`: the model can call 3 tools
  (damage calc, stored-team lookup, usage stats) via Ollama's native
  tool-calling before answering. `docs/superpowers/plans/2026-09-19-agentic-tool-calling.md`.
- **Conversational chat** — plain messages (no slash command) in
  admin-designated channels (`CONVERSATION_CHANNEL_IDS` env var, off by
  default) reuse `/analyze`'s tool-calling loop, extended with a short
  rolling per-channel history for natural follow-ups. Requires Discord's
  Message Content Intent, enabled for this bot.
  `docs/superpowers/plans/2026-09-21-conversational-chat.md`.
- **Mention-triggered Q&A** — `@bot "question"` in channels listed in
  `MENTION_CHANNEL_IDS` gets a one-off answer via the same tool-calling
  loop, with no persisted history (each mention stands alone). Separate
  opt-in from `CONVERSATION_CHANNEL_IDS`; same Message Content Intent
  requirement.
- **Local LLM, self-hosted** — `OllamaAnswerer` (`rag/answer.py`) replaced
  paid Claude Haiku entirely; a `CircuitBreaker` short-circuits `/ask`
  when the host is unreachable instead of paying a full timeout per call.
  Currently served from a MacBook (not the originally-planned Windows
  laptop), with a LaunchAgent making the required `OLLAMA_HOST=0.0.0.0`
  setting survive reboot/logout, and `scripts/llm_toggle.sh {on|off|status}`
  for turning that host on/off on demand — see `docs/DEPLOYMENT.md`
  section 3.
- **Damage calculator** (`damage_calc/`) — ported `@smogon/calc` logic:
  spread moves, weather/terrain (including auto-derivation from setter
  abilities), screens, Tera types, 6 type-immunity abilities, Intimidate.
- **Team memory** — Pokepaste import (`/import`), incremental team
  building (`/scout`), SQLite-persisted, surfaced via button-driven
  Discord UI (`/team`) and fed into `/calc`/`/ask` as context.
- **Data pipeline** (`pipeline/`) — PokéAPI + Pikalytics fetch/merge,
  schema validation and per-job freshness checks before any live data
  swap, regulation-aware (re-derives everything on a legal-list rotation
  without a code change).
- **Eval harness** (`eval/`, `scripts/run_eval.py`) — 48-entry golden
  Q&A set, `recall@5` gated in CI against the real embedder/index,
  `--with-answers` for on-demand live-model answer-quality checks.
- **Observability** — every `/ask` call logged to SQLite
  (`rag/observability.py`), with retention pruning and owner-only
  `/debug-last` / `/stats-summary` / `/llmstatus` commands.
- **CI** — `ruff` lint, `pytest --cov`, and a check that every pinned
  dependency in `requirements.txt` carries an explanatory comment.

## What's left

Nothing on `IMPROVEMENTS.md` — the one remaining backlog item
(fine-tune vs. RAG comparison) was decided against (2026-09-21): the
local LLM is meant to stay generic, not fine-tuned to this project's
domain. The infrastructure stays in the repo unused; see
`IMPROVEMENTS.md`.

- **Needs investigation:** a ChromaDB auth error
  (`Could not resolve authentication method...`) surfaced on a live
  `/ask` call in the Oracle instance's logs, pre-dating the 2026-09-21
  polish pass. Not yet root-caused.

Only one other known item, and it's external:

- **Known limitation, not fixable from this repo:** Pikalytics hasn't
  published a ranked-ladder format code for Regulation M-C yet, so two
  species new to M-C (Farfetch'd, Sirfetch'd) have no usage data. Re-check
  once their M-C ladder has enough data to publish a format code, update
  `PIKALYTICS_FORMAT_CODE` (`pipeline/fetch_pikalytics.py`), re-run
  `refresh_pikalytics_job`.

## Useful pointers

- `IMPROVEMENTS.md` — prioritized improvement backlog (portfolio review)
- `TAKEAWAYS.md` — portfolio retrospective (tech stack, architecture,
  what was learned)
- `pika-rag-project-plan.md` — original architecture/scope/build-order doc
- `docs/DEPLOYMENT.md` — step-by-step deploy runbook
- `docs/superpowers/plans/` and `docs/superpowers/specs/` — design docs
  and implementation plans behind each shipped feature

## How to re-orient fast

```bash
git log --oneline -10        # what shipped most recently
git status                   # anything in flight
pytest -q                    # confirm the suite still passes
```

<!-- STATUS_COMMIT: 5c43eb0 -->
<!-- This HTML comment is machine-read by a Stop hook (.claude/settings.json)
     that nags to refresh this file whenever HEAD moves past this hash.
     Update it to the current `git rev-parse --short HEAD` every time you
     update this file. -->
