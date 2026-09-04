# Pika-RAG: Pokepaste Import + Team Memory — Design

Status: Approved
Date: 2026-09-04

## Purpose

Let a Discord user quickly load "my team" and "opponent's team" into the bot for a
session, then have `/calc` and `/ask` automatically draw on that context instead of
requiring every stat to be typed by hand each time. Two realistic input modes are
needed: a full team import (when the exact set is known — your own team, or an
opponent's team found posted online) and incremental manual entry (when scouting an
opponent live, where only species is known at first and item/moves/Tera are revealed
piece by piece over the course of team preview and battle).

## Scope

In scope:
- Parsing the standard Pokemon Showdown / Pokepaste export text format
- Fetching a team from a `pokepast.es` URL
- In-memory, per-Discord-user storage of "mine" and "opponent" teams (no disk
  persistence — cleared on bot restart, same lifetime as a chat session)
- `/import` (full team, replaces a side), `/scout` (single Pokemon, merges into a
  side), `/team` (view/recall)
- Feeding stored team data into `/calc` (per-field override precedence) and `/ask`
  (as extra grounding context)

Out of scope (see "Out of scope" section for detail):
- Disk/database persistence of teams across restarts
- Feeding real (non-31) IVs into damage calculation
- A command to clear/reset a single scouted Pokemon or a whole side
- Move legality/set validation against real usage data (Pikalytics) — still deferred
  from the original data-pipeline spec

## Data model

One parsed/stored Pokemon ("team member"):

```python
{
    "species": str,            # matched against pokemon_records["name"] where possible
    "nickname": str | None,
    "gender": str | None,      # "M" / "F", cosmetic only — not used by calc
    "item": str | None,
    "ability": str | None,
    "level": int,              # default 50
    "tera_type": str | None,
    "evs": {"hp": int, "attack": int, "defense": int,
            "sp_attack": int, "sp_defense": int, "speed": int},  # default 0 each
    "ivs": {...same six stats...},  # default 31 each; parsed and stored for
                                     # display only, see "Out of scope"
    "nature": str,             # default "Hardy" (neutral)
    "moves": list[str],        # 0-4 entries; empty until any are known/parsed
}
```

Team store (in-memory, `bot/team_store.py`):

```python
_TEAM_STORE: dict[int, dict[str, list[dict]]]
# _TEAM_STORE[discord_user_id]["mine"] = [team_member, ...]
# _TEAM_STORE[discord_user_id]["opponent"] = [team_member, ...]
```

Both lists are capped at 6 entries (a VGC team size). No disk writes; lost on
restart, matching the "this session" framing rather than a permanent record.

## Parsing (`bot/pokepaste.py`)

Pure function: `parse_pokepaste(text: str) -> list[dict]`. No I/O, no network, no
knowledge of Discord or the team store.

Input is one or more blocks separated by a blank line, each in Showdown export
format:

```
Iron Hands @ Assault Vest
Ability: Quark Drive
Level: 50
Tera Type: Water
EVs: 236 HP / 4 Atk / 4 Def / 116 SpD / 148 Spe
Adamant Nature
- Fake Out
- Wild Charge
- Drain Punch
- Heavy Slam
```

Rules:
- First line: `[Nickname (Species)] [(Gender)] [@ Item]`. If there's no
  parenthetical species, the leading name IS the species (no nickname). A trailing
  `(M)`/`(F)` is the gender marker, item follows ` @ `.
- Following lines until the blank-line block boundary, each matched independently
  and in any order: `Ability: X`, `Level: N`, `Tera Type: X`, `EVs: ...`, `IVs: ...`,
  `<Nature> Nature`, `- <Move>` (0-4 of these). `Shiny:`, `Happiness:`, and `Ball:`
  lines are recognized and ignored (cosmetic/irrelevant to damage calc).
- `EVs:`/`IVs:` lines use Showdown's stat abbreviations (`HP`/`Atk`/`Def`/`SpA`/
  `SpD`/`Spe`) mapped to this project's snake_case stat names; any stat omitted
  from the line defaults (0 for EVs, 31 for IVs).
- A block missing a parseable species line is a hard parse failure for the whole
  call — see "Error handling."
- Species/move name matching against this project's data (`pokemon_records`,
  `vgc_moves`) is NOT done inside `parse_pokepaste` — it stays a pure text-in,
  structured-data-out function. Cross-checking against real data (and producing
  "did you mean" warnings) is `bot/commands/team.py`'s job, reusing the existing
  `find_record`/`suggest_names` helpers from `pokemon_lookup`.

## Commands

### `/import side:(mine|opponent) pokepaste:str`

`pokepaste` is either a raw pasted block (parsed directly) or a `pokepast.es` URL
(detected by an `http`-prefixed value; the bot fetches `<url>/raw` for the plain
text before parsing). Replaces the named side's stored team outright — this is
"I now have the full, current list," not a merge.

On success: confirmation listing what was stored, plus a warning line per any
species/move that didn't match known data (kept as-is, not rejected — could be a
different regulation or a typo, either way still useful to have stored).

### `/scout species:str item? ability? tera_type? move1? move2? move3? move4? side:(mine|opponent)=opponent`

Adds one Pokemon to the named side, or **merges into it** if that species is
already stored: any field not passed this call keeps its previous stored value,
and any newly-given move names are added to the existing move list (deduplicated,
capped at 4) rather than replacing it. This is the "team preview only showed
species, item revealed on turn 2, second move seen on turn 4" incremental-scouting
path the full `/import` can't serve since it always replaces.

`/scout` deliberately has no EVs/nature/IVs parameters at all — those aren't
observable by watching a battle, so there's nothing real to enter. They stay at
the standard neutral defaults (0 EVs, Hardy nature, 31 IVs) unless that side is
later replaced with a full `/import`. A scouted mon otherwise behaves exactly like
a fully-imported one once it reaches `/calc`.

### `/team side:(mine|opponent)`

View/recall: one line per stored Pokemon (species, item, Tera type, nature, known
moves). An empty/never-loaded side reports that plainly and points at `/import`
or `/scout`.

**Revised during final review (2026-09-04):** the original draft of this
section also called for `/team` to re-surface "any still-pending unmatched-name
warnings for that side." This was never implemented — warnings are already
shown once, immediately, in `/import`'s and `/scout`'s own confirmation
message, at the moment the unrecognized name is stored. Persisting them
separately so `/team` could show them again would mean carrying warning state
alongside every stored Pokemon and threading it through `format_team_block`,
for a case that's already surfaced to the user at the moment it matters.
Descoped rather than implemented; if a user wants to double-check a stored
Pokemon's name later, `/team`'s existing species listing already lets them see
exactly what's stored.

## Feeding `/calc`

`bot/main.py`'s `/calc` handler resolves each side independently, in this
precedence order per field (EVs, nature, item, Tera):

```
explicit Discord option (if provided) > stored team member's value (if the
attacker/defender name matches one) > neutral default (0 EVs / Hardy / no item /
no Tera)
```

Team lookup checks the invoking user's "mine" list first, then "opponent" — if the
same species name happens to be stored on both sides, "mine" wins. This merge
logic lives in one small, independently-testable helper (e.g.
`resolve_calc_overrides(...)` in `bot/team_store.py`), called by `bot/main.py`
before it invokes `calc_response`. **`calc_response`'s own signature and tests are
completely unchanged** — from its point of view it's just receiving a possibly-
different EVs string / item / etc. than before, the same as any other explicit
Discord option today.

## Feeding `/ask`

`ask_response`/`ask_response_async` gain one new optional parameter,
`extra_context: str = None`, prepended to the retrieved context block before it
reaches the answerer:

```python
def ask_response(index, answerer, question, n_results=5, extra_context=None):
    context_block = build_context_block(index, question, n_results=n_results)
    if extra_context:
        context_block = f"{extra_context}\n\n{context_block}"
    return answerer.answer(question, context_block)
```

`bot/main.py`'s `/ask` handler builds `extra_context` from whichever of the
invoking user's "mine"/"opponent" teams are currently loaded (reusing the same
formatting helper `/team` uses), and passes it on every call — no relevance
filtering. If nothing is loaded, `extra_context` is `None` and behavior is
identical to today. This keeps `ask_response`'s existing tests and behavior
untouched when there's no team loaded, and is a one-parameter, backward-compatible
addition otherwise.

## Error handling

- A structurally unparseable block (no recognizable species line) rejects the
  *entire* `/import` or `/scout` call with an error naming which block/position
  failed — never a partially-stored team.
- Unmatched species/move names (parses fine, just not found in `pokemon_records`/
  `vgc_moves`) are stored as given and surfaced as warnings, not rejected.
- More than 6 blocks in one `/import`, or a `/scout` that would push a side over 6
  distinct species, is rejected with a clear count-based message.
- A bad `pokepast.es` URL or fetch failure (network error, 404) reports that
  plainly rather than falling through to a parse error about empty text.
- `/team` on a side with nothing stored says so and points at `/import`/`/scout`.

## Testing plan

- `bot/pokepaste.py`: pure parser unit tests — full spec, nickname, gender marker,
  omitted optional fields (defaults), multiple blocks, malformed block raises.
- `bot/team_store.py`: store/replace (`/import` semantics)/merge (`/scout`
  semantics), per-user isolation, mine-before-opponent lookup precedence,
  `resolve_calc_overrides` precedence rules (explicit > team > default) as its own
  unit tests independent of Discord or `calc_response`.
- `bot/commands/team.py` (`import_team_response`, `scout_response`,
  `view_team_response`): validation/warning-flagging against fixture records and
  moves, merge-on-rescout behavior, view formatting, empty-side messaging.
- `bot/commands/ask.py`: new `extra_context` param — one test confirming it's
  prepended and reaches the answerer; existing tests unchanged (default `None`).
- `bot/main.py`: registration tests for `/import`, `/scout`, `/team` (mirroring the
  existing `test_bot_main.py` pattern), plus wiring tests that the `/calc` and
  `/ask` handlers actually call the new resolver/context-building helpers.
- `calc_response`/`ask_response` core signatures: no existing test changes needed
  beyond the one additive `extra_context` test above.
- Manual end-to-end smoke test with a real Pokepaste sample, same as prior
  sessions' verification style.

## Out of scope

- Disk or database persistence — restart clears all stored teams (see "Scope").
- Feeding real (non-31) IVs into `calculate_damage`. The formula never reads Speed
  (no turn-order modeling), and the only IV deviations from 31 that actually change
  damage output (0 Atk to minimize confusion self-hit, etc.) are rare enough not to
  justify a whole new override surface in `/calc` right now. Parsed IVs are still
  stored on the team-member record for completeness, even though `/team`'s
  display (see "Commands") doesn't surface them — matching every other
  VGC-standard-assumed field that isn't worth a dedicated display line.
- A command to clear/reset a single scouted Pokemon or an entire side. Re-`/import`
  already replaces a side outright; nothing today removes a single `/scout`-added
  entry without doing that.
- Real usage/spread data (Pikalytics) — already deferred in the original
  data-pipeline spec and unaffected by this feature.
