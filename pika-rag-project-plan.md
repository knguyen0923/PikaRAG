# Pika-RAG

A Discord bot for **Pokémon Champions VGC (doubles)** that answers questions about stats, common EV/nature spreads, common movesets, and calculates battle damage — grounded in real competitive usage data and current regulation legality.

---

## Tech Stack

| Component | Choice | Notes |
|---|---|---|
| LLM | Claude Haiku | Prepaid API credit, no auto-recharge |
| Embeddings | sentence-transformers (local) | Free, runs on the bot host, no extra API dependency |
| Vector DB | Chroma | File-based, simple, plenty for a curated ~300-500 Pokémon roster |
| RAG framework | Raw Python | No LangChain/LlamaIndex — full control, better for learning + resume |
| Damage calculator | Ported `@smogon/calc` (JS → Python) | Deterministic function, not LLM-generated math |
| Bot framework | discord.py | Slash commands |
| Hosting | Oracle Cloud Free Tier | Always-on, free ARM instance |
| Data refresh | Hybrid | Scheduled job for routine refresh + manual trigger for regulation changes |

---

## Architecture

```
Discord (slash command)
      │
      ▼
discord.py bot (Oracle Cloud, free tier)
      │
      ├─ /calc  → Python-ported damage calc (deterministic, no LLM)
      │
      └─ /ask, /stats, /spread → Chroma retrieval (local embeddings)
                                        │
                                        ▼
                                Claude Haiku (prompt + retrieved context)
                                        │
                                        ▼
                                Response → Discord
```

**Key principle:** RAG handles *knowledge* questions (stats, spreads, movesets, lore). The damage calculator is a pure function the bot calls directly with structured inputs — never routed through the LLM.

---

## Scope

- **Stats & spreads** — base stats, common EV spreads + natures seen in VGC doubles, Tera type
- **Common movesets** — top moves per Pokémon with usage %, sourced from real tournament/ladder data
- **Damage calculator** — attacker/defender + move → damage range; doubles-aware (spread move reduction, redirection, Intimidate, weather/terrain, Tera)
- **Format awareness** — only surfaces info relevant to the *currently active* regulation set (e.g. M-B, M-C — these rotate every few months)

---

## Data Sources

| Source | Use | Notes |
|---|---|---|
| [PokéAPI](https://pokeapi.co/) | Base stats, types, move data, abilities | Free, no key needed |
| [Pikalytics](https://www.pikalytics.com/) | Real VGC usage stats, common spreads/moves, teammates | Check ToS before scraping; best source of "most common" data |
| [Smogon Strategy Dex](https://www.smogon.com/) | Secondary context on *why* a spread/moveset is used | Good for RAG lore/reasoning chunks |
| [`smogon/calc`](https://github.com/smogon/damage-calc) | Reference implementation for damage formula | Port core logic to Python rather than reimplementing blind |
| Official regulation announcements | Current legal roster / Mega availability | Needs periodic manual check — regs change every few months |

---

## Data Pipeline Notes

- Treat **regulation legality as metadata**, not as a filter on what gets embedded. Tag each Pokémon record with something like `legal_in: ["M-B", "M-C"]` and filter at query time — this avoids rebuilding the whole vector store every time the regulation set changes.
- Chunking strategy: consider separate chunk types per Pokémon (stats chunk, moveset chunk, lore chunk) so retrieval can be more precise depending on question type.
- Roster is curated (Pokémon Champions ≠ full National Dex), so the dataset is smaller than a full Pokédex RAG project — this keeps everything (embeddings, Chroma index size) lightweight.

---

## Project Structure (proposed)

```
pika-rag/
├── data/
│   ├── raw/                  # scraped/pulled raw data (PokéAPI, Pikalytics)
│   ├── processed/            # cleaned, structured records ready for embedding
│   └── regulations.json      # current + historical regulation set metadata
├── pipeline/
│   ├── fetch_pokeapi.py
│   ├── fetch_pikalytics.py
│   ├── build_records.py      # merges sources into structured Pokémon records
│   └── refresh_job.py        # scheduled refresh entrypoint
├── rag/
│   ├── embed.py              # sentence-transformers embedding logic
│   ├── store.py               # Chroma index build/query
│   └── retrieve.py           # retrieval + prompt assembly for Haiku
├── damage_calc/
│   ├── calc.py                # ported @smogon/calc logic
│   └── data/                  # move/ability/item data needed for calc
├── bot/
│   ├── main.py                # discord.py bot entrypoint
│   └── commands/
│       ├── ask.py             # /ask — general RAG queries
│       ├── stats.py           # /stats — base stats + spreads
│       ├── moves.py           # /moves — common movesets
│       └── calc.py            # /calc — damage calculator
├── .env                        # API keys (Discord token, Anthropic key) — gitignored
├── requirements.txt
└── README.md
```

---

## Build Order (suggested)

1. **Data pipeline** — pull PokéAPI + Pikalytics data, merge into structured records with regulation metadata
2. **Damage calculator** — port `@smogon/calc` core logic, test against known values before touching the bot
3. **RAG core** — embed records, build Chroma index, test retrieval quality with sample queries
4. **Haiku integration** — prompt template that injects retrieved context, test grounding (no hallucinated stats)
5. **Discord bot skeleton** — get `/ping` working on Oracle Cloud before wiring in real commands
6. **Wire up slash commands** — `/ask`, `/stats`, `/moves`, `/calc`
7. **Refresh job** — scheduled scraper + manual rebuild script
8. **Polish** — error handling, rate limiting, embed formatting for Discord responses

---

## Open Items / To Revisit

- [ ] Confirm Pikalytics scraping is within their ToS, or find an alternative/API path
- [ ] Decide exact chunking strategy (per-Pokémon vs. split by data type)
- [ ] Set prepaid budget cap for Anthropic API credit
- [ ] Set up Oracle Cloud free tier instance + confirm always-on ARM instance specs
- [ ] Define cron schedule for routine data refresh (weekly? bi-weekly?)
