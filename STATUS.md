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
metered API anywhere in the system. 612/612 tests passing, CI green
(lint + coverage + pinned-dep checks). Data current for Regulation M-C
(345 legal Pokémon, 197 items).

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
- **Local LLM, self-hosted** — `OllamaAnswerer` (`rag/answer.py`) replaced
  paid Claude Haiku entirely; a `CircuitBreaker` short-circuits `/ask`
  when the host is unreachable instead of paying a full timeout per call.
  Currently served from a MacBook (not the originally-planned Windows
  laptop), with a LaunchAgent making the required `OLLAMA_HOST=0.0.0.0`
  setting survive reboot/logout — see `docs/DEPLOYMENT.md` section 3.
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

Nothing on `IMPROVEMENTS.md` — the one remaining item (fine-tune vs. RAG
comparison) was decided against (2026-09-21): the local LLM is meant to
stay generic, not fine-tuned to this project's domain. The infrastructure
stays in the repo unused; see `IMPROVEMENTS.md`.

Only one known item left project-wide, and it's external:

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

<!-- STATUS_COMMIT: 594e69f -->
<!-- This HTML comment is machine-read by a Stop hook (.claude/settings.json)
     that nags to refresh this file whenever HEAD moves past this hash.
     Update it to the current `git rev-parse --short HEAD` every time you
     update this file. -->
