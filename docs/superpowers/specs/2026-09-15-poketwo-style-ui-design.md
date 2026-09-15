# Pika-RAG: Cross-Command Button UI (Poketwo-style) — Design

Status: Draft (pending review)
Date: 2026-09-15

## Purpose

The bot's Discord button-UI backlog item (open since 2026-09-13) has one already-approved, not-yet-executed slice: `2026-09-15-team-button-ui-design.md`, which adds a side-switcher View to `/team` alone, deliberately deferring every other command until that pattern proved itself in production. That gating decision is explicitly overridden by this spec at the user's direction — this spec plans (and, once approved, may execute) button/component UI for the remaining commands without waiting on `/team` to ship first. It does not replace or modify the `/team` spec; `/team` remains its own independently-approved unit, and one slice below (C) depends on its `TeamView` class existing.

This spec covers four independent slices, each separately plannable and shippable:

- **A** — a shared `NameSuggestionView` component, replacing plain-text "did you mean X, Y, Z?" messages with an interactive dropdown, wherever a *single* name lookup misses.
- **B** — `/stats` and `/moves` share one tabbed panel (Stats / Moves / Usage), swapping in place instead of requiring two separate command invocations.
- **C** — `/import` gains an overwrite-confirmation step and a "View team" cross-link into `/team`'s `TeamView`.
- **D** — a new `/dex` command: a Pokedex-style Prev/Next browser over the current regulation's legal roster.

## Scope

In scope: the four slices above, each detailed in its own section.

Explicitly out of scope, with reasons (discovered while investigating the actual code, not assumed upfront):

- **`/ask`'s entity-detection ambiguity.** `rag/entity.py`'s `detect_entity` collapses "no entity found" and "entity match is ambiguous" into the same `None` return — the `_AMBIGUOUS` sentinel exists only inside that module and is never surfaced to any caller. Giving `/ask` a "did you mean X or Y?" dropdown would require changing `detect_entity`'s return contract, which is part of an already-shipped, carefully-tuned, recall@5-measured feature (`2026-09-13-retrieval-quality-design.md`). That's a real, separate design question, not a bolt-on UI change — left as a follow-up.
- **`/scout` and `/import`'s per-member validation warnings.** `bot/commands/team.py`'s `_validate_member` collects a *batch* of warnings across up to 6 Pokemon × (species, item, up to 4 moves) into one text response (`import_team_response`/`scout_response`). A single dropdown fits one miss with one retry target; it does not fit "here are 4 unrelated problems across 3 different Pokemon" without redesigning that whole flow into a multi-step correction wizard. Left as a follow-up; `/import`'s and `/scout`'s existing plain-text warnings are unchanged by this spec.
- **Command deprecation.** `/stats` and `/moves` both keep their existing names and independent slash-command registration (see Slice B) — this spec adds a shared panel, it does not remove either command.
- **`/ping`, `/debug-last`, `/llmstatus`.** Single-shot utility/admin commands with no natural multi-step or browsable interaction — left as plain responses, consistent with the principle that not every command benefits from a button.
- **Persistent (`custom_id`-backed) views surviving a bot restart.** Same reasoning as the `/team` spec: not needed for anything in this spec, all interactions here are short-lived.

## Architecture

**Shared module:** a new `bot/ui.py` holds `NameSuggestionView` (Slice A) — the one component genuinely shared across multiple command files. `PokemonInfoView` (Slice B), the import confirmation view (Slice C), and the dex browser view (Slice D) each live next to the command(s) they belong to (`bot/commands/stats.py` or a shared `bot/commands/dex_common.py`, `bot/commands/team.py` alongside the existing `TeamView`, and a new `bot/commands/dex.py` respectively) — matching this codebase's existing convention of colocating a View with the command module that owns it (`TeamView` already lives in `bot/commands/team.py`, not a shared UI module), reserving `bot/ui.py` for the one component with more than one owner.

**Shared conventions**, applied to every new View in this spec:

- **Invoker-only `interaction_check`.** Every View restricts clicks to whoever triggered the original interaction, sending its own ephemeral rejection (`"This isn't your ... menu/panel."`) before returning `False` — the exact pattern `/team`'s `TeamView` already established, for the same reason: a `discord.ui.View`'s `interaction_check` does not route through `bot/main.py`'s `@tree.error` handler, so a silent `False` reads as a broken button.
- **No persistence.** Every View relies on `discord.ui.View`'s default timeout with no `custom_id` and no `on_timeout` override. **Side-finding, unrelated to this spec:** the already-approved `/team` spec's own text says this default is "~15 minutes of inactivity" — the actual `discord.ui.View` default is 180 seconds (3 minutes), confirmed directly against the installed `discord.py` 2.7.1. This spec uses the correct 180-second figure throughout; the `/team` spec's text is not corrected here (out of scope for this document) but should be fixed whenever that plan is next touched.
- **Edit in place.** Every multi-step interaction (tab switch, dropdown pick, confirm/cancel, page turn) calls `interaction.response.edit_message(...)`, never sends a new message — same reasoning as `/team`: that's the entire reason to use a View instead of a fresh command invocation.

---

## Slice A: `NameSuggestionView` — shared "did you mean...?" dropdown

**Where it replaces existing text.** Every *single-miss* lookup that currently calls `bot/pokemon_lookup.py`'s `not_found_message`/`format_with_suggestions` and has exactly one retry target:

- `bot/commands/stats.py`'s `stats_response` (species not found)
- `bot/commands/moves.py`'s `moves_response` (species not found)
- `bot/commands/calc.py`'s `calc_response` — five independent single-miss points: attacker species, defender species, move name, attacker item (via `_canonicalize_item`), defender item (via `_canonicalize_item`)

**Component.** `NameSuggestionView(user_id, suggestions, on_select)`: a `discord.ui.View` holding one `discord.ui.Select` populated from `suggest_names`'s existing close-match list (already capped at 3 by that function's own `n=3` default, comfortably under Discord's 25-option select limit). `on_select` is an async `(interaction, chosen_name) -> None` callback supplied by the call site — what happens after picking a name differs per command, so this view has no opinion on that beyond invoking the callback. If `suggest_names` returns an empty list (no close matches at all), the call site falls back to today's plain `not_found_message` text with no view attached — there's nothing to put in a dropdown.

**`/stats`/`/moves` integration.** Each command's `bot/main.py` handler calls `find_record` itself before delegating to `stats_response`/`moves_response` (which already do the identical lookup internally — a small, cheap, accepted duplication, matching `bot/commands/calc.py`'s own `_canonicalize_item` doing an independent `find_record` today). On a miss with suggestions available, the handler sends the existing not-found text with a `NameSuggestionView` attached whose `on_select` calls `interaction.response.edit_message(...)` with the real `stats_response`/`moves_response` output for the chosen name — a single extra click resolves a typo instead of retyping the whole command.

**`/calc` integration.** `bot/main.py`'s `/calc` handler performs the same independent lookups (attacker, defender, move, and — when an `items` list is loaded — both items) in the exact short-circuit order `calc_response` already checks them internally, *before* calling `calc_response`. On the first field that misses (matching `calc_response`'s own first-error-wins behavior), the handler shows one `NameSuggestionView` for that field only; every other originally-typed parameter (EVs, nature, tera, items, weather, etc.) is preserved and replayed unchanged once a suggestion is picked. This requires refactoring the command body into an inner callable the top-level handler and each suggestion's `on_select` both invoke — full detail belongs in the implementation plan, not this spec.

**Testing approach.** `NameSuggestionView` itself: construct directly, assert its `Select`'s options match the given suggestions, invoke the select callback with a `MagicMock` interaction and assert `on_select` was awaited with the chosen value; `interaction_check` tested the same way `/team`'s already is. Per-command integration: a lookup miss with close matches attaches a `NameSuggestionView` with the right options; a miss with zero close matches attaches no view; picking a suggestion in `/calc` re-runs the full calculation with the corrected field and every other original parameter intact.

---

## Slice B: `/stats`/`/moves` tabbed panel

Both commands keep their existing names, descriptions, and independent slash-command registration — no deprecation. Whichever one is run opens a `PokemonInfoView(records, moves, usage, species_name, user_id, active_tab)` with three buttons — "Stats," "Moves," "Usage" — styled so the active tab is visually distinct (`discord.ButtonStyle.primary`) from the other two (`discord.ButtonStyle.secondary`). This is a deliberate departure from `/team`'s `TeamView`, which intentionally gives both its buttons identical styling (there, the buttons represent two peer choices, not a persistent tab set) — here, indicating which tab is active is core to reading the three buttons as tabs at all rather than arbitrary actions.

- **Stats tab** reuses `stats_response` unchanged.
- **Moves tab** reuses `moves_response` unchanged.
- **Usage tab** needs one new pure function, `usage_response(records, name, usage) -> str` (`bot/commands/stats.py` or a new small shared module — implementation plan's call), since no existing formatter shows the *full* Pikalytics breakdown — `stats_response` only surfaces the single top item/ability, `moves_response` only the top moves, and neither shows all three side by side. `usage_response` shows the up-to-6-each items/abilities/moves lists `pikalytics_usage.json` already stores per species (`fetch_pikalytics.py`'s `_TOP_N = 6`), or a clear "no usage data" message when `usage_for_record` returns `None` — mirroring the not-found handling already established by `stats_response`/`moves_response` (species-not-found still goes through Slice A's dropdown before a `PokemonInfoView` is ever constructed, since there's no Pokemon to build tabs for).

Clicking a tab button calls the corresponding response function for the same `species_name` and `edit_message`s in a fresh `PokemonInfoView` reflecting the new `active_tab`. Whichever command name the user ran becomes that view's starting tab (`/stats` opens on "Stats," `/moves` opens on "Moves").

**Testing approach.** `PokemonInfoView` construction: three buttons present, correct one styled `primary`. Each tab button's callback: `edit_message` called with the right formatter's output and a new view reflecting the new active tab. `usage_response`: full breakdown when usage data exists, clear no-data message when it doesn't — mirroring the existing `stats_response`/`moves_response` test patterns in `tests/test_bot_stats.py`/`tests/test_bot_moves.py`.

---

## Slice C: `/import` overwrite confirmation + "View team" cross-link

**Dependency:** this slice constructs `bot/commands/team.py`'s `TeamView` (from the `/team` spec's Phase 1 plan) directly — it cannot be implemented before that class exists in the codebase, even though (per the user's explicit direction) it does not need to wait for `/team` to first prove itself in production.

**Overwrite confirmation.** `bot/main.py`'s `/import` handler checks `get_team(interaction.user.id, side)` before doing anything else. If that side already has a stored team, the handler shows a new `ImportConfirmView` ("You already have a team stored for '{side}'. Replace it with this import? [Confirm] [Cancel]") instead of importing immediately; only on **Confirm** does the actual parse-validate-store sequence run. If the side has nothing stored yet (the common case for a first-time import), behavior is unchanged — it imports immediately, no extra click. This requires splitting `bot/commands/team.py`'s `import_team_response` into two pieces: a parse-and-validate step that returns the parsed members and warnings without calling `store_team`, and a finalize step that does the actual `store_team` call and formats the success message — exact function boundaries belong in the implementation plan.

**"View team" cross-link.** A successful import's result embed gains one additional button, "View team," which — when clicked — replaces itself with the same `TeamView`/team-block rendering `/team` itself produces for that side, via `interaction.response.edit_message(...)`. This reuses `view_team_response`/`TeamView` completely unchanged; it's purely a navigation shortcut so a user doesn't have to separately run `/team` right after importing.

**`/scout` is unchanged** — its writes are single-field merges onto one existing team member (or a small append), not a wholesale side-replacing operation like `/import`'s `store_team`; per the "Scout/import scope" decision, it keeps its existing plain-text behavior in this spec.

**Testing approach.** `/import` with an empty target side: imports immediately, no confirmation view (regression-tests today's existing behavior is preserved). `/import` with an existing team on that side: shows `ImportConfirmView`, does *not* call `store_team` yet; clicking Confirm completes the import and shows the success embed with a "View team" button attached; clicking Cancel leaves the previously-stored team untouched and says so. The "View team" button: clicking it produces the same content `/team`'s own handler would for that side.

---

## Slice D: `/dex` — Pokedex-style roster browser

A new command, `/dex`, with one optional parameter: `start: Optional[str] = None`. With no argument, it opens on the first Pokemon in the currently-loaded `records` list (whatever order `pipeline/build_records.py` already produced — this spec does not assume or require that order to be alphabetical). With `start` given, it resolves the name via the same `find_record`/Slice A suggestion-dropdown path every other command uses, then opens on that Pokemon's position in the list.

**Component.** `DexBrowseView(records, index, user_id)` — two buttons, "◀ Prev" and "Next ▶," each `disabled=True` at the respective boundary (`index == 0` / `index == len(records) - 1`) rather than hidden, so the panel's layout doesn't shift at the ends. Each click computes the new index, calls a new pure formatter — `dex_page_response(records, index) -> str`, a compact one-Pokemon card reusing `stats_response`'s exact formatting for consistency (name, types, base stats, abilities; no usage data on this page, to keep each page a fast, uniform Prev/Next flip rather than another set of tabs) — and `edit_message`s in the new content plus a fresh `DexBrowseView` at the new index.

**Testing approach.** `DexBrowseView` at index 0: "Prev" disabled, "Next" enabled; at the last index, the reverse; in the middle, both enabled. Clicking "Next"/"Prev" edits the message with the adjacent record's card and the correctly-updated button disabled-states. `/dex` with a `start` name that doesn't exist: goes through Slice A's suggestion dropdown exactly like every other command, not a separate error path.

---

## Dependencies between slices and other in-flight work

- Slice C depends on `TeamView` (from the `/team` Phase 1 plan) existing in the codebase — it must be implemented after that plan's Task 1, though not necessarily after the whole `/team` plan has shipped/been validated in production.
- Slices A, B, and D have no dependency on `/team` or on each other, and can be planned and implemented in any order.
- None of the four slices modify `rag/entity.py`, `bot/team_store.py`'s merge-only paths, or any already-shipped, spec-approved behavior from the six 2026-09-13 design specs.

## Testing philosophy (applies to all four slices)

Every new View is tested the same way `/team`'s `TeamView` already is: construct it directly, drive its callbacks with a `MagicMock` interaction and `asyncio.run(...)`, assert on the captured `edit_message`/`send_message` kwargs — no real Discord network access anywhere, consistent with every existing test in this codebase.
