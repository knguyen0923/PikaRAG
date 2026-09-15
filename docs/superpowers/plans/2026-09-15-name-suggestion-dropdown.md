# Name Suggestion Dropdown (Slice A) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the plain-text "did you mean X, Y, Z?" message with an interactive dropdown wherever a single name lookup misses — `/stats`, `/moves`, and `/calc`'s five independent lookup points (attacker species, defender species, move, attacker item, defender item) — so a typo can be corrected with one click instead of retyping the whole command.

**Architecture:** A new `bot/ui.py` holds `NameSuggestionView(user_id, suggestions, on_select)`, a `discord.ui.View` with one `discord.ui.Select` populated from `bot/pokemon_lookup.py`'s existing `suggest_names` output. `on_select` is an async `(interaction, chosen_name) -> None` callback the call site supplies — the view itself has no opinion on what happens after a name is picked. `/stats` and `/moves` each do their own `find_record` check before delegating to `stats_response`/`moves_response` (which already do the identical check internally — small accepted duplication, matching `bot/commands/calc.py`'s existing `_canonicalize_item` pattern), attaching a view on a miss with suggestions. `/calc`'s handler is restructured into an inner `_run_calc(interaction, send_new_message, **fields)` coroutine that both the top-level command and every suggestion's `on_select` call — `fields` carries every one of `/calc`'s original parameters unchanged except the one being corrected, so a retry replays the whole calculation exactly as typed except for the fixed typo.

**Tech Stack:** Python 3.9, `discord.py` 2.7.1's `discord.ui` (already used by `/team`'s `TeamView`) — no new dependencies.

**Spec:** `docs/superpowers/specs/2026-09-15-poketwo-style-ui-design.md` (Slice A).

## Global Constraints

- `NameSuggestionView` is only ever shown when `suggest_names` returns a non-empty list — a miss with zero close matches keeps today's plain-text-only behavior (nothing to put in a dropdown).
- Every suggestion menu is invoker-only: `interaction_check` compares `interaction.user.id` against the `user_id` the view was constructed with, sending its own ephemeral rejection before returning `False` — the same pattern `/team`'s `TeamView` already established, for the same reason (`discord.ui.View.interaction_check` does not route through `bot/main.py`'s `@tree.error` handler).
- Every selection re-renders via `interaction.response.edit_message(...)`, never a new message.
- This plan does not touch `/ask`'s entity detection or `/scout`/`/import`'s batch validation warnings — both are explicitly out of scope per the spec (see spec's "Scope" section for why).
- `/calc`'s restructuring must not change `calc_response`'s or `resolve_calc_overrides`'s existing signatures or behavior — this plan only changes how `bot/main.py`'s `/calc` handler calls them.

---

## File structure

- Create `bot/ui.py` — `NameSuggestionView`.
- Create `tests/test_bot_ui.py` — full test coverage for `NameSuggestionView`.
- Modify `bot/main.py` — `/stats` and `/moves` handlers gain a pre-check + suggestion view (Task 2); `/calc` is restructured around a new `_run_calc` inner coroutine (Task 3).
- Modify `tests/test_bot_main.py` — new tests for the `/stats`/`/moves` suggestion flow and the `/calc` suggestion flow (all five fields).

---

### Task 1: `bot/ui.py` — `NameSuggestionView`

**Files:**
- Create: `bot/ui.py`
- Test: `tests/test_bot_ui.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `NameSuggestionView(user_id: int, suggestions: list, on_select)` — a `discord.ui.View` with one child (`discord.ui.Select`), options built from `suggestions` (capped at 25, Discord's own select-menu limit — `suggest_names`'s existing `n=3` default never gets close, this is a defensive cap only). Tasks 2 and 3 both construct this directly.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_bot_ui.py`:

```python
import asyncio
from unittest.mock import AsyncMock, MagicMock

from bot.ui import NameSuggestionView


def test_name_suggestion_view_has_one_option_per_suggestion():
    view = NameSuggestionView(user_id=1, suggestions=["Abomasnow", "Absol"], on_select=AsyncMock())

    select = view.children[0]
    assert [opt.label for opt in select.options] == ["Abomasnow", "Absol"]


def test_name_suggestion_view_caps_options_at_twenty_five():
    suggestions = [f"Species{i}" for i in range(30)]
    view = NameSuggestionView(user_id=1, suggestions=suggestions, on_select=AsyncMock())

    select = view.children[0]
    assert len(select.options) == 25


def test_picking_a_suggestion_calls_on_select_with_the_chosen_name():
    on_select = AsyncMock()
    view = NameSuggestionView(user_id=1, suggestions=["Abomasnow", "Absol"], on_select=on_select)
    select = view.children[0]
    select.values = ["Absol"]  # simulates Discord populating .values on submit
    interaction = MagicMock()
    interaction.user.id = 1

    asyncio.run(select.callback(interaction))

    on_select.assert_awaited_once_with(interaction, "Absol")


def test_name_suggestion_view_interaction_check_rejects_a_different_user():
    view = NameSuggestionView(user_id=1, suggestions=["Abomasnow"], on_select=AsyncMock())
    interaction = MagicMock()
    interaction.user.id = 999
    interaction.response.send_message = AsyncMock()

    allowed = asyncio.run(view.interaction_check(interaction))

    assert allowed is False
    _args, kwargs = interaction.response.send_message.call_args
    assert kwargs["ephemeral"] is True


def test_name_suggestion_view_interaction_check_allows_the_original_invoker():
    view = NameSuggestionView(user_id=1, suggestions=["Abomasnow"], on_select=AsyncMock())
    interaction = MagicMock()
    interaction.user.id = 1
    interaction.response.send_message = AsyncMock()

    allowed = asyncio.run(view.interaction_check(interaction))

    assert allowed is True
    interaction.response.send_message.assert_not_awaited()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_bot_ui.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bot.ui'`.

- [ ] **Step 3: Implement `bot/ui.py`**

```python
import discord


class NameSuggestionView(discord.ui.View):
    """Shared 'did you mean...?' dropdown, offered wherever a name lookup
    misses but bot.pokemon_lookup.suggest_names has close matches. on_select
    is an async (interaction, chosen_name) -> None callback the call site
    supplies -- this view has no opinion on what happens after a pick,
    since that differs per command (re-run /stats, retry /calc with one
    field corrected, etc.)."""

    def __init__(self, user_id: int, suggestions: list, on_select):
        super().__init__()
        self.user_id = user_id
        self._on_select = on_select
        options = [discord.SelectOption(label=name) for name in suggestions[:25]]
        select = discord.ui.Select(placeholder="Did you mean...", options=options)
        select.callback = self._make_callback(select)
        self.add_item(select)

    def _make_callback(self, select: discord.ui.Select):
        async def callback(interaction: discord.Interaction) -> None:
            await self._on_select(interaction, select.values[0])

        return callback

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your suggestion menu.", ephemeral=True)
            return False
        return True
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_bot_ui.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add bot/ui.py tests/test_bot_ui.py
git commit -m "feat: add shared NameSuggestionView dropdown component"
```

---

### Task 2: Wire `NameSuggestionView` into `/stats` and `/moves`

**Files:**
- Modify: `bot/main.py`
- Modify: `tests/test_bot_main.py`

**Interfaces:**
- Consumes: `NameSuggestionView` (Task 1), `find_record`/`suggest_names`/`not_found_message` (`bot/pokemon_lookup.py`, already exist).
- Produces: nothing consumed by a later task.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_bot_main.py`:

```python
def test_stats_command_shows_a_suggestion_view_on_a_close_miss():
    records = [{
        "name": "Abomasnow", "types": ["Grass", "Ice"],
        "base_stats": {"hp": 90, "attack": 92, "defense": 75, "sp_attack": 92, "sp_defense": 85, "speed": 60},
        "abilities": ["Snow Warning"], "learnset": ["Blizzard"], "legal_in": ["M-B"],
    }]
    _client, tree = build_client(records=records)
    stats_cmd = tree.get_command("stats")
    interaction = MagicMock()
    interaction.user.id = 1
    interaction.response.send_message = AsyncMock()

    asyncio.run(stats_cmd.callback(interaction, name="Abomasno"))

    from bot.ui import NameSuggestionView

    _args, kwargs = interaction.response.send_message.call_args
    assert isinstance(kwargs["view"], NameSuggestionView)


def test_stats_command_picking_a_suggestion_edits_in_the_real_stats():
    records = [{
        "name": "Abomasnow", "types": ["Grass", "Ice"],
        "base_stats": {"hp": 90, "attack": 92, "defense": 75, "sp_attack": 92, "sp_defense": 85, "speed": 60},
        "abilities": ["Snow Warning"], "learnset": ["Blizzard"], "legal_in": ["M-B"],
    }]
    _client, tree = build_client(records=records)
    stats_cmd = tree.get_command("stats")
    interaction = MagicMock()
    interaction.user.id = 1
    interaction.response.send_message = AsyncMock()

    asyncio.run(stats_cmd.callback(interaction, name="Abomasno"))

    _args, kwargs = interaction.response.send_message.call_args
    view = kwargs["view"]
    select = view.children[0]
    select.values = ["Abomasnow"]
    pick_interaction = MagicMock()
    pick_interaction.user.id = 1
    pick_interaction.response.edit_message = AsyncMock()

    asyncio.run(select.callback(pick_interaction))

    _args, edit_kwargs = pick_interaction.response.edit_message.call_args
    assert "Abomasnow" in edit_kwargs["embed"].description
    assert "HP 90" in edit_kwargs["embed"].description


def test_stats_command_shows_no_view_when_there_are_no_close_matches():
    records = [{
        "name": "Abomasnow", "types": ["Grass", "Ice"],
        "base_stats": {"hp": 90, "attack": 92, "defense": 75, "sp_attack": 92, "sp_defense": 85, "speed": 60},
        "abilities": ["Snow Warning"], "learnset": ["Blizzard"], "legal_in": ["M-B"],
    }]
    _client, tree = build_client(records=records)
    stats_cmd = tree.get_command("stats")
    interaction = MagicMock()
    interaction.user.id = 1
    interaction.response.send_message = AsyncMock()

    asyncio.run(stats_cmd.callback(interaction, name="Zzzznotarealpokemon"))

    _args, kwargs = interaction.response.send_message.call_args
    assert kwargs.get("view") is None


def test_moves_command_shows_a_suggestion_view_on_a_close_miss():
    records = [{
        "name": "Abomasnow", "types": ["Grass", "Ice"],
        "base_stats": {"hp": 90, "attack": 92, "defense": 75, "sp_attack": 92, "sp_defense": 85, "speed": 60},
        "abilities": ["Snow Warning"], "learnset": ["Blizzard"], "legal_in": ["M-B"],
    }]
    _client, tree = build_client(records=records)
    moves_cmd = tree.get_command("moves")
    interaction = MagicMock()
    interaction.user.id = 1
    interaction.response.send_message = AsyncMock()

    asyncio.run(moves_cmd.callback(interaction, name="Abomasno"))

    from bot.ui import NameSuggestionView

    _args, kwargs = interaction.response.send_message.call_args
    assert isinstance(kwargs["view"], NameSuggestionView)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_bot_main.py -v -k "suggestion_view or close_matches"`
Expected: `test_stats_command_shows_a_suggestion_view_on_a_close_miss` and the `/moves` equivalent FAIL because `send_message`'s `call_args` has no `view` kwarg at all yet (`KeyError`); `test_stats_command_shows_no_view_when_there_are_no_close_matches` currently PASSES trivially (no view is ever attached today) and stays passing after Step 3 too; `test_stats_command_picking_a_suggestion_edits_in_the_real_stats` FAILS the same way as the first.

- [ ] **Step 3: Implement**

Add this import to `bot/main.py`, alongside the other `bot.*` imports:

```python
from bot.pokemon_lookup import find_record, not_found_message, suggest_names
from bot.ui import NameSuggestionView
```

Change the `/stats` command from:

```python
    @tree.command(name="stats", description="Look up a Pokemon's base stats, types, and abilities.")
    @app_commands.checks.cooldown(1, _COOLDOWN_SECONDS)
    async def stats(interaction: discord.Interaction, name: str) -> None:
        await interaction.response.send_message(embed=_embed("stats", stats_response(records, name, usage=usage)))
```

to:

```python
    @tree.command(name="stats", description="Look up a Pokemon's base stats, types, and abilities.")
    @app_commands.checks.cooldown(1, _COOLDOWN_SECONDS)
    async def stats(interaction: discord.Interaction, name: str) -> None:
        if find_record(records, name) is None:
            suggestions = suggest_names(records, name)
            if suggestions:
                async def _on_select(inner_interaction: discord.Interaction, chosen: str) -> None:
                    await inner_interaction.response.edit_message(
                        embed=_embed("stats", stats_response(records, chosen, usage=usage)), view=None
                    )

                await interaction.response.send_message(
                    embed=_embed("stats", not_found_message(records, name)),
                    view=NameSuggestionView(interaction.user.id, suggestions, _on_select),
                )
                return
        await interaction.response.send_message(embed=_embed("stats", stats_response(records, name, usage=usage)))
```

Change the `/moves` command the same way, from:

```python
    @tree.command(name="moves", description="Look up a Pokemon's legal moveset.")
    @app_commands.checks.cooldown(1, _COOLDOWN_SECONDS)
    async def moves_command(interaction: discord.Interaction, name: str) -> None:
        await interaction.response.send_message(embed=_embed("moves", moves_response(records, name, usage=usage)))
```

to:

```python
    @tree.command(name="moves", description="Look up a Pokemon's legal moveset.")
    @app_commands.checks.cooldown(1, _COOLDOWN_SECONDS)
    async def moves_command(interaction: discord.Interaction, name: str) -> None:
        if find_record(records, name) is None:
            suggestions = suggest_names(records, name)
            if suggestions:
                async def _on_select(inner_interaction: discord.Interaction, chosen: str) -> None:
                    await inner_interaction.response.edit_message(
                        embed=_embed("moves", moves_response(records, chosen, usage=usage)), view=None
                    )

                await interaction.response.send_message(
                    embed=_embed("moves", not_found_message(records, name)),
                    view=NameSuggestionView(interaction.user.id, suggestions, _on_select),
                )
                return
        await interaction.response.send_message(embed=_embed("moves", moves_response(records, name, usage=usage)))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_bot_main.py -v -k "stats_command or moves_command"`
Expected: all PASS, including the pre-existing `test_stats_command_uses_usage_data_when_provided`/`test_moves_command_uses_usage_data_when_provided`.

- [ ] **Step 5: Run the entire test suite as a final check**

Run: `pytest -q`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add bot/main.py tests/test_bot_main.py
git commit -m "feat: show a suggestion dropdown on a /stats or /moves near-miss"
```

---

### Task 3: Wire `NameSuggestionView` into `/calc`

**Files:**
- Modify: `bot/main.py`
- Modify: `tests/test_bot_main.py`

**Interfaces:**
- Consumes: `NameSuggestionView` (Task 1), `find_record`/`suggest_names`/`not_found_message` (`bot/pokemon_lookup.py`), `calc_response`/`is_error_response` (`bot/commands/calc.py`, unchanged), `resolve_calc_overrides` (`bot/team_store.py`, unchanged).
- Produces: nothing consumed by a later task — this is the final task in this plan.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_bot_main.py`:

```python
def test_calc_command_shows_a_suggestion_view_for_a_mistyped_attacker():
    _client, tree = build_client(records=_CALC_TEST_RECORDS, moves=_CALC_TEST_MOVES)
    calc_cmd = tree.get_command("calc")
    interaction = MagicMock()
    interaction.user.id = 1
    interaction.response.send_message = AsyncMock()

    asyncio.run(calc_cmd.callback(interaction, attacker="Garchom", defender="Garchomp", move="Earthquake"))

    from bot.ui import NameSuggestionView

    _args, kwargs = interaction.response.send_message.call_args
    assert isinstance(kwargs["view"], NameSuggestionView)


def test_calc_command_picking_an_attacker_suggestion_replays_the_whole_calc():
    _client, tree = build_client(records=_CALC_TEST_RECORDS, moves=_CALC_TEST_MOVES)
    calc_cmd = tree.get_command("calc")
    interaction = MagicMock()
    interaction.user.id = 1
    interaction.response.send_message = AsyncMock()

    asyncio.run(calc_cmd.callback(interaction, attacker="Garchom", defender="Garchomp", move="Earthquake"))

    _args, kwargs = interaction.response.send_message.call_args
    select = kwargs["view"].children[0]
    select.values = ["Garchomp"]
    pick_interaction = MagicMock()
    pick_interaction.user.id = 1
    pick_interaction.response.edit_message = AsyncMock()

    asyncio.run(select.callback(pick_interaction))

    _args, edit_kwargs = pick_interaction.response.edit_message.call_args
    assert "Garchomp's Earthquake vs Garchomp" in edit_kwargs["embed"].description


def test_calc_command_shows_no_view_for_a_completely_unrecognized_name():
    _client, tree = build_client(records=_CALC_TEST_RECORDS, moves=_CALC_TEST_MOVES)
    calc_cmd = tree.get_command("calc")
    interaction = MagicMock()
    interaction.user.id = 1
    interaction.response.send_message = AsyncMock()

    asyncio.run(calc_cmd.callback(interaction, attacker="Zzzznotreal", defender="Garchomp", move="Earthquake"))

    _args, kwargs = interaction.response.send_message.call_args
    assert kwargs.get("view") is None
```

(`_CALC_TEST_RECORDS`/`_CALC_TEST_MOVES` already exist earlier in `tests/test_bot_main.py`, reused by the existing stored-team `/calc` tests.)

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_bot_main.py -v -k "calc_command_shows or calc_command_picking"`
Expected: all 3 FAIL — `send_message`'s `call_args` has no `view` kwarg yet, so `kwargs["view"]` raises `KeyError` in the first two, and the third's `kwargs.get("view")` is trivially `None` already (passes before this task, stays passing after).

- [ ] **Step 3: Implement**

Change the `/calc` command from:

```python
    @tree.command(name="calc", description="Calculate a damage range for attacker's move vs defender.")
    @app_commands.checks.cooldown(1, _COOLDOWN_SECONDS)
    async def calc(
        interaction: discord.Interaction,
        attacker: str,
        defender: str,
        move: str,
        attacker_evs: Optional[str] = None,
        attacker_nature: Optional[str] = None,
        attacker_item: Optional[str] = None,
        attacker_tera: Optional[str] = None,
        defender_evs: Optional[str] = None,
        defender_nature: Optional[str] = None,
        defender_item: Optional[str] = None,
        defender_tera: Optional[str] = None,
        defender_hp_percent: app_commands.Range[int, 1, 100] = 100,
        weather: Optional[str] = None,
        terrain: Optional[str] = None,
        screen: Optional[str] = None,
        spread: bool = False,
    ) -> None:
        user_id = interaction.user.id
        resolved_attacker_evs, resolved_attacker_nature, resolved_attacker_item, resolved_attacker_tera = (
            resolve_calc_overrides(user_id, attacker, attacker_evs, attacker_nature, attacker_item, attacker_tera)
        )
        resolved_defender_evs, resolved_defender_nature, resolved_defender_item, resolved_defender_tera = (
            resolve_calc_overrides(user_id, defender, defender_evs, defender_nature, defender_item, defender_tera)
        )
        response = calc_response(
            records,
            moves,
            attacker,
            defender,
            move,
            items=items,
            attacker_evs=resolved_attacker_evs,
            attacker_nature=resolved_attacker_nature,
            attacker_item=resolved_attacker_item,
            attacker_tera=resolved_attacker_tera,
            defender_evs=resolved_defender_evs,
            defender_nature=resolved_defender_nature,
            defender_item=resolved_defender_item,
            defender_tera=resolved_defender_tera,
            defender_hp_percent=defender_hp_percent,
            weather=weather,
            terrain=terrain,
            screen=screen,
            spread=spread,
        )
        # Only note stored-team usage on a successful calc -- not on an
        # error, where the note would be misleading.
        if not is_error_response(response):
            stored_names = [name for name in (attacker, defender) if find_team_member(user_id, name)]
            if stored_names:
                response += f" (using stored data for: {', '.join(stored_names)})"
        await interaction.response.send_message(embed=_embed("calc", response))
```

to:

```python
    async def _calc_send(interaction: discord.Interaction, send_new_message: bool, embed, view=None) -> None:
        if send_new_message:
            await interaction.response.send_message(embed=embed, view=view)
        else:
            await interaction.response.edit_message(embed=embed, view=view)

    async def _run_calc(interaction: discord.Interaction, send_new_message: bool, **fields) -> None:
        """fields holds /calc's parameters exactly as originally typed:
        attacker, defender, move, attacker_evs, attacker_nature,
        attacker_item, attacker_tera, defender_evs, defender_nature,
        defender_item, defender_tera, defender_hp_percent, weather,
        terrain, screen, spread. A suggestion pick re-invokes this with
        exactly one field replaced and every other one untouched."""
        attacker, defender, move = fields["attacker"], fields["defender"], fields["move"]

        if find_record(records, attacker) is None:
            suggestions = suggest_names(records, attacker)
            message = not_found_message(records, attacker)
            if not suggestions:
                await _calc_send(interaction, send_new_message, _embed("calc", message))
                return

            async def _on_select(inner_interaction: discord.Interaction, chosen: str) -> None:
                await _run_calc(inner_interaction, False, **{**fields, "attacker": chosen})

            await _calc_send(
                interaction, send_new_message, _embed("calc", message),
                NameSuggestionView(interaction.user.id, suggestions, _on_select),
            )
            return

        if find_record(records, defender) is None:
            suggestions = suggest_names(records, defender)
            message = not_found_message(records, defender)
            if not suggestions:
                await _calc_send(interaction, send_new_message, _embed("calc", message))
                return

            async def _on_select(inner_interaction: discord.Interaction, chosen: str) -> None:
                await _run_calc(inner_interaction, False, **{**fields, "defender": chosen})

            await _calc_send(
                interaction, send_new_message, _embed("calc", message),
                NameSuggestionView(interaction.user.id, suggestions, _on_select),
            )
            return

        if find_record(moves, move) is None:
            suggestions = suggest_names(moves, move)
            message = not_found_message(moves, move, kind="move")
            if not suggestions:
                await _calc_send(interaction, send_new_message, _embed("calc", message))
                return

            async def _on_select(inner_interaction: discord.Interaction, chosen: str) -> None:
                await _run_calc(inner_interaction, False, **{**fields, "move": chosen})

            await _calc_send(
                interaction, send_new_message, _embed("calc", message),
                NameSuggestionView(interaction.user.id, suggestions, _on_select),
            )
            return

        user_id = interaction.user.id
        resolved_attacker_evs, resolved_attacker_nature, resolved_attacker_item, resolved_attacker_tera = (
            resolve_calc_overrides(
                user_id, attacker, fields["attacker_evs"], fields["attacker_nature"],
                fields["attacker_item"], fields["attacker_tera"],
            )
        )
        resolved_defender_evs, resolved_defender_nature, resolved_defender_item, resolved_defender_tera = (
            resolve_calc_overrides(
                user_id, defender, fields["defender_evs"], fields["defender_nature"],
                fields["defender_item"], fields["defender_tera"],
            )
        )

        if items:
            if resolved_attacker_item and find_record(items, resolved_attacker_item) is None:
                suggestions = suggest_names(items, resolved_attacker_item)
                if suggestions:
                    async def _on_select(inner_interaction: discord.Interaction, chosen: str) -> None:
                        await _run_calc(inner_interaction, False, **{**fields, "attacker_item": chosen})

                    await _calc_send(
                        interaction, send_new_message,
                        _embed("calc", not_found_message(items, resolved_attacker_item, kind="item")),
                        NameSuggestionView(interaction.user.id, suggestions, _on_select),
                    )
                    return
            if resolved_defender_item and find_record(items, resolved_defender_item) is None:
                suggestions = suggest_names(items, resolved_defender_item)
                if suggestions:
                    async def _on_select(inner_interaction: discord.Interaction, chosen: str) -> None:
                        await _run_calc(inner_interaction, False, **{**fields, "defender_item": chosen})

                    await _calc_send(
                        interaction, send_new_message,
                        _embed("calc", not_found_message(items, resolved_defender_item, kind="item")),
                        NameSuggestionView(interaction.user.id, suggestions, _on_select),
                    )
                    return

        response = calc_response(
            records, moves, attacker, defender, move, items=items,
            attacker_evs=resolved_attacker_evs, attacker_nature=resolved_attacker_nature,
            attacker_item=resolved_attacker_item, attacker_tera=resolved_attacker_tera,
            defender_evs=resolved_defender_evs, defender_nature=resolved_defender_nature,
            defender_item=resolved_defender_item, defender_tera=resolved_defender_tera,
            defender_hp_percent=fields["defender_hp_percent"], weather=fields["weather"],
            terrain=fields["terrain"], screen=fields["screen"], spread=fields["spread"],
        )
        # Only note stored-team usage on a successful calc -- not on an
        # error, where the note would be misleading.
        if not is_error_response(response):
            stored_names = [name for name in (attacker, defender) if find_team_member(user_id, name)]
            if stored_names:
                response += f" (using stored data for: {', '.join(stored_names)})"
        await _calc_send(interaction, send_new_message, _embed("calc", response))

    @tree.command(name="calc", description="Calculate a damage range for attacker's move vs defender.")
    @app_commands.checks.cooldown(1, _COOLDOWN_SECONDS)
    async def calc(
        interaction: discord.Interaction,
        attacker: str,
        defender: str,
        move: str,
        attacker_evs: Optional[str] = None,
        attacker_nature: Optional[str] = None,
        attacker_item: Optional[str] = None,
        attacker_tera: Optional[str] = None,
        defender_evs: Optional[str] = None,
        defender_nature: Optional[str] = None,
        defender_item: Optional[str] = None,
        defender_tera: Optional[str] = None,
        defender_hp_percent: app_commands.Range[int, 1, 100] = 100,
        weather: Optional[str] = None,
        terrain: Optional[str] = None,
        screen: Optional[str] = None,
        spread: bool = False,
    ) -> None:
        await _run_calc(
            interaction, True,
            attacker=attacker, defender=defender, move=move,
            attacker_evs=attacker_evs, attacker_nature=attacker_nature,
            attacker_item=attacker_item, attacker_tera=attacker_tera,
            defender_evs=defender_evs, defender_nature=defender_nature,
            defender_item=defender_item, defender_tera=defender_tera,
            defender_hp_percent=defender_hp_percent, weather=weather,
            terrain=terrain, screen=screen, spread=spread,
        )
```

(Both `_calc_send` and `_run_calc` are defined inside `build_client`, above the `@tree.command(name="calc", ...)` decorator, the same way every other command's supporting logic already lives inside `build_client`'s closure — they capture `records`, `moves`, `items`, `_embed` from that enclosing scope exactly like the original inline handler body did.)

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_bot_main.py -v -k calc`
Expected: all PASS, including every pre-existing `/calc` test (stored-team overrides, cooldown, registration, the `import`-then-`calc` integration test).

- [ ] **Step 5: Run the entire test suite as a final check**

Run: `pytest -q`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add bot/main.py tests/test_bot_main.py
git commit -m "feat: show a suggestion dropdown for any /calc name miss"
```

---

## Self-review notes

- **Spec coverage:** `NameSuggestionView` shared component with invoker-only check and edit-in-place (Task 1); `/stats`/`/moves` single-miss integration (Task 2); `/calc`'s five independent miss points, each preserving every other originally-typed parameter on retry (Task 3) — all covered. `/ask` and `/scout`/`/import` are correctly untouched by any task, per the spec's explicit scope exclusion.
- **Placeholder scan:** no TBD/TODO; every step has complete, runnable code.
- **Type consistency checked:** `NameSuggestionView.__init__(self, user_id, suggestions, on_select)`'s parameter order matches every call site across Tasks 2 and 3. `on_select`'s `(interaction, chosen_name)` signature is honored by every closure defined in Tasks 2 and 3. `_run_calc`'s `**fields` keys (`attacker`, `defender`, `move`, `attacker_evs`, `attacker_nature`, `attacker_item`, `attacker_tera`, `defender_evs`, `defender_nature`, `defender_item`, `defender_tera`, `defender_hp_percent`, `weather`, `terrain`, `screen`, `spread`) match exactly between the top-level `calc` command's initial call and every retry closure's `{**fields, "<field>": chosen}` merge.
- **Regression risk audited:** Task 2's `/stats`/`/moves` change adds one extra `find_record` call on the happy path (species found) — negligible cost, no behavior change when a name resolves cleanly, confirmed by the pre-existing usage-data tests staying unmodified in Task 2's own test run. Task 3's restructuring preserves `calc_response`'s exact call signature and the existing "using stored data for: ..." note logic verbatim, just moved inside the new `_run_calc` function — every pre-existing `/calc` test in `tests/test_bot_main.py` exercises `calc_cmd.callback(interaction, ...)` the same way as before, unaffected by the internal restructuring.
