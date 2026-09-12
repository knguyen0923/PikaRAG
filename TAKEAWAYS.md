# Building PikaRAG — Project Takeaways

A retrospective on building PikaRAG: a Discord bot for Pokémon VGC (Champions
ranked doubles) that answers questions grounded in real competitive data,
calculates exact battle damage, and remembers a user's team. Built solo,
2026-09-03 to 2026-09-12 (96 commits), from empty repo to a live, deployed bot.

## What it does

PikaRAG combines two very different kinds of "answer a question about
Pokémon" into one bot:

- **Knowledge questions** ("what's a good spread for Landorus?") go through a
  RAG pipeline: retrieve real data, hand it to an LLM to phrase a grounded
  answer.
- **Math questions** ("how much damage does this move do?") go through a
  deterministic damage calculator — no LLM involved, because damage numbers
  need to be *exactly* right, not *plausibly* right.

Keeping those two paths separate was the single most important design
decision in the project, and it held up all the way through.

## Tech stack

| Layer | Choice | Why |
|---|---|---|
| LLM | Claude Haiku 4.5 | Cheap enough for a hobby project's per-query cost (~$0.003–0.007), prepaid spend cap as a hard ceiling |
| Embeddings | `sentence-transformers` (local) | Runs on the bot host, no extra API dependency or per-embedding cost |
| Vector store | ChromaDB | File-based, zero ops, plenty for a few hundred Pokémon |
| RAG "framework" | Raw Python | No LangChain/LlamaIndex — deliberately hand-rolled retrieval + prompting to actually learn how the pieces fit, not just call a library |
| Damage engine | Hand-ported `@smogon/calc` (JS → Python) | A pure function, verified against Bulbapedia's own mechanics reference, not an LLM guess |
| Bot framework | `discord.py` (slash commands) | Native Discord integration, typed command params |
| Hosting | Oracle Cloud Free Tier (ARM, Ubuntu) | Always-on, $0/month, systemd-managed |
| Testing | `pytest`, TDD throughout | 262 tests, more test code than source code |
| CI | GitHub Actions | Runs the full suite on every push |

## Architecture

```
Discord (slash command)
      │
      ▼
discord.py bot (Oracle Cloud, systemd, always-on)
      │
      ├─ /calc            → pure-Python damage calculator (deterministic)
      │
      ├─ /stats, /moves    → direct data lookup (no LLM)
      │
      ├─ /import, /scout,  → Pokepaste parsing + per-user team memory
      │  /team               (feeds /calc and /ask so you can say "my
      │                       Landorus" instead of a full spread)
      │
      └─ /ask              → Chroma retrieval (local embeddings)
                                   │
                                   ▼
                            Claude Haiku (prompt + retrieved context only)
                                   │
                                   ▼
                            Response → Discord
```

Behind all of this: a data pipeline (`pipeline/`) that fetches from PokéAPI
and scrapes Pikalytics usage stats, merges them, and feeds both the vector
store and the damage calculator's stat lookups. It's regulation-aware — when
Pokémon Champions rotates its legal-Pokémon list (which happened mid-project,
M-B → M-C), the pipeline re-derives everything without a code change.

## What I actually learned, by area

### RAG, for real (not through a framework)

Building retrieval by hand instead of reaching for LangChain forced me to
understand what those frameworks are actually doing under the hood:

- **Embeddings are just a similarity search.** Turn text into vectors, store
  them, and at query time find the nearest ones to the question's vector.
  That's the whole trick — the "magic" is in what you choose to embed and
  how you chunk it, not in the search itself.
- **Grounding beats prompting.** The single biggest lever against
  hallucination wasn't a clever system prompt — it was constraining the
  model's context to *only* what retrieval actually found, and explicitly
  telling it to say "I don't know" rather than fill gaps. A small, honest
  context beats a large, hopeful one.
- **Retrieval quality is a data problem, not a model problem.** Most of the
  actual RAG debugging time went into what gets chunked and how records are
  keyed for lookup — not into prompt engineering.
- **Not everything belongs in the RAG path.** The decision to keep the
  damage calculator entirely outside the LLM was the single choice that made
  the bot trustworthy for numbers. An LLM asked "how much damage does
  Flamethrower do" will confidently produce a wrong number; a ported formula
  won't.

### Building a real Discord bot

- Slash commands with typed parameters (`app_commands`), including using
  `app_commands.Range` to get free, native input validation instead of
  hand-rolling range checks everywhere.
- Structuring one file per command (`bot/commands/`) instead of one giant
  bot file kept each command's logic independently testable — most of the
  262 tests never touch Discord at all, they call the command's response
  function directly with plain data.
- Slash-command propagation is a real thing to plan around: a bot's
  commands can take up to an hour to appear globally in Discord after first
  registering — not a bug, just a platform quirk to expect on first deploy.

### Deterministic game-logic engineering

Porting a damage calculator taught a lesson that generalizes well beyond
Pokémon: **when a spec exists, verify against it precisely — don't trust a
plausible-looking implementation, even your own.** Partway through a cleanup
pass, a code review flagged a rounding-order issue in the damage formula.
Investigating it against Bulbapedia's actual mechanics reference (rather
than fixing it from memory) turned up two *more* compounding bugs the
review had missed — a misplaced modifier stage and a wrong constant. All
three got fixed together, with regression tests whose expected values were
hand-computed against the verified formula, not just asserted from the
new code's own output (an easy trap: a test that just checks "does the code
agree with itself" verifies nothing).

### Real deployment, real infrastructure

Free-tier cloud hosting is a great way to learn networking the hard way:

- A subnet needs an **Internet Gateway** to be reachable from the internet
  at all — a plain "Create VCN" doesn't provision one automatically, only
  the guided VCN wizard does. Missing this looks like a mysterious SSH
  timeout with no obvious cause.
- Security lists, route tables, and public-IP assignment are three
  *separate* things that all have to be correct together; a green checkmark
  on one doesn't mean the others are right.
- `useradd -m` and `git clone` can conflict — `-m` seeds a home directory
  with dotfiles, so cloning into it next fails because the directory isn't
  empty. A small thing, but the kind of interaction you only find by
  actually running the automation, not by reading it.
- Python dependency resolution can hand you a genuinely broken package
  combination (a specific `torch` release that crashed on import via a
  `transformers` integration) — pinning to a known-good version and writing
  down *why* in the requirements file saves the next person (or session)
  from rediscovering the same crash.

### Working with an AI coding assistant deliberately

This project was built in close collaboration with Claude, and that
process was itself worth learning from:

- **Spec first, code second.** Non-trivial features got a written design
  doc before implementation (`docs/superpowers/specs/`) — forces scope and
  edge cases to get decided on purpose, not discovered mid-implementation.
- **Verify, don't just accept.** The damage-formula bug above is the
  clearest example: the fix an automated review proposed was checked
  against an external authoritative source before being trusted, and that
  check is what caught the deeper issues.
- **Draw a hard line between "reversible" and "not."** Local edits, tests,
  and commits happened freely; anything that touched the *live* deployed
  bot or transmitted real credentials (starting/restarting the systemd
  service, copying secrets to the server) was handed back for a human to
  actually run. That boundary made it possible to move fast on everything
  else without worrying about the one thing that really mattered.

## By the numbers

- **96 commits**, empty repo to live deployment, over 9 days
- **262 automated tests**, ~3,300 lines of test code vs. ~2,100 lines of
  source (more test code than implementation — a deliberate TDD habit, not
  an accident)
- **345 legal Pokémon**, 197 items, and a full VGC doubles-aware damage
  formula (spread-move reduction, weather, terrain, screens, Tera types,
  items, abilities-adjacent effects) covered by the calculator
- **$0/month** hosting (Oracle Cloud Always Free tier) and roughly
  **$0.003–0.007 per `/ask` query** (Claude Haiku), with a self-imposed
  spend cap plus an in-bot early-warning system as a second safety net

## What I'd do differently / next

- Add the ability check and a few more held-item/ability interactions the
  calculator doesn't cover yet (this was scoped out deliberately, not missed)
- A CI check that pins-and-explains dependency versions the way
  `requirements.txt`'s `torch` comment does, so future upgrades don't
  silently reintroduce the same class of import-time crash
- Revisit the Pikalytics scraping question formally (ToS compliance) before
  ever making this a public/multi-server bot rather than a personal one
