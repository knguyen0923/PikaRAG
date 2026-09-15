# Import Confirmation + View-Team Link (Slice C) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**PREREQUISITE:** This plan constructs `bot/commands/team.py`'s `TeamView` class directly (Task 1 of `docs/superpowers/plans/2026-09-15-team-button-ui.md`) — that class must already exist in the codebase before Task 1 below can be implemented. It does not require the rest of that plan, and does not require `/team` to have been validated in production first.

**Goal:** `/import` checks for an already-stored team on the target side before overwriting it — if one exists, it shows a Confirm/Cancel prompt instead of silently replacing it; the common empty-side case still imports immediately, no extra click. A successful import's result also gains a "View team" button that jumps straight into `/team`'s own panel.

**Architecture:** `bot/commands/team.py`'s `import_team_response` is split into `prepare_import` (parse + validate, no storing) and `finalize_import` (the actual `store_team` call plus success/failure message) — `import_team_response` itself becomes a thin backward-compatible wrapper calling both in sequence, so every existing caller and test keeps working unchanged. Two new Views join `TeamView` in the same file: `ImportConfirmView` (Confirm/Cancel, shown only when overwriting) and `ViewTeamButtonView` (one button on a successful import's result, jumping into `TeamView`). `bot/main.py`'s `/import` handler calls `prepare_import` first (unchanged failure path on a parse error), then branches on `get_team(user_id, side)`: non-empty shows `ImportConfirmView` and defers the actual `finalize_import` call until Confirm is clicked; empty finalizes immediately, exactly as `/import` already behaves today.

**Tech Stack:** Python 3.9, `discord.py` 2.7.1's `discord.ui` — no new dependencies.

**Spec:** `docs/superpowers/specs/2026-09-15-poketwo-style-ui-design.md` (Slice C).

## Global Constraints

- `/scout` is unchanged by this plan — its writes are single-field merges (`bot/team_store.py`'s `merge_scout`), not a wholesale side-replacing operation like `/import`'s `store_team`; per the approved spec, it keeps its existing plain-text behavior.
- `import_team_response`'s public signature and return type (a plain `str`) do not change — every existing test calling it directly keeps passing unmodified.
- The "already has a team, replace it?" check reads `get_team(user_id, side)` — an empty list means nothing is stored yet, and the import proceeds immediately with no confirmation step, matching `/import`'s current behavior exactly for that case.
- Both new Views are invoker-only (`interaction_check` comparing `interaction.user.id`) with their own ephemeral rejection, and use `interaction.response.edit_message(...)` for every click — the same conventions `TeamView`, `NameSuggestionView`, and `PokemonInfoView` all already establish.
- `ImportConfirmView`/`ViewTeamButtonView` live in `bot/commands/team.py`, not a shared module — `ViewTeamButtonView` needs `TeamView`'s own embed-building convention (`_team_embed`) directly, and colocating avoids any risk of a circular import with `bot/main.py` (which already imports from `bot/commands/team.py`, never the other way).

---

## File structure

- Modify `bot/commands/team.py` — split `import_team_response` into `prepare_import`/`finalize_import`; add `ImportConfirmView`, `ViewTeamButtonView`.
- Modify `tests/test_bot_team.py` — new tests for `prepare_import`/`finalize_import`, `ImportConfirmView`, `ViewTeamButtonView`; existing `import_team_response` tests are unmodified (still pass against the new wrapper).
- Modify `bot/main.py` — `/import` handler gains the confirm/cancel branch and attaches `ViewTeamButtonView` on success.
- Modify `tests/test_bot_main.py` — new tests for the confirm/cancel flow and the "View team" button.

---

### Task 1: `bot/commands/team.py` — split `import_team_response`, add the two new Views

**Files:**
- Modify: `bot/commands/team.py`
- Modify: `tests/test_bot_team.py`

**Interfaces:**
- Consumes: `TeamView`, `_team_embed` (from the `/team` plan's Task 1 — see PREREQUISITE above), `view_team_response`, `parse_pokepaste`/`PokepasteParseError`, `store_team`/`get_team` (all already exist, unchanged).
- Produces: `prepare_import(records, moves, side, pokepaste_text, items=None) -> dict` (`{"ok": False, "message": str}` on a parse error, or `{"ok": True, "members": list, "warnings": list}`); `finalize_import(user_id, side, members, warnings) -> dict` (`{"ok": bool, "message": str}`); `ImportConfirmView(user_id, on_confirm, on_cancel)`; `ViewTeamButtonView(user_id, side)`. Task 2's `bot/main.py` handler calls all four.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_bot_team.py` (add `import asyncio` and `from unittest.mock import AsyncMock, MagicMock` to the top of the file alongside the existing imports):

```python
import asyncio
from unittest.mock import AsyncMock, MagicMock

from bot.commands.team import (
    ImportConfirmView, ViewTeamButtonView, finalize_import, prepare_import,
)


def test_prepare_import_reports_a_parse_error_without_touching_the_store():
    result = prepare_import(_RECORDS, _MOVES, "mine", "")

    assert result["ok"] is False
    assert "Could not parse team" in result["message"]


def test_prepare_import_returns_members_and_warnings_on_success():
    result = prepare_import(_RECORDS, _MOVES, "mine", "Abomasnow\n- Wood Hammer\n")

    assert result["ok"] is True
    assert result["members"][0]["species"] == "Abomasnow"
    assert result["warnings"] == []


def test_prepare_import_does_not_store_anything():
    prepare_import(_RECORDS, _MOVES, "mine", "Abomasnow\n- Wood Hammer\n")

    assert get_team(701, "mine") == []


def test_finalize_import_stores_and_reports_success():
    prepared = prepare_import(_RECORDS, _MOVES, "mine", "Abomasnow\n- Wood Hammer\n")

    result = finalize_import(702, "mine", prepared["members"], prepared["warnings"])

    assert result["ok"] is True
    assert "Loaded 1 Pokemon" in result["message"]
    assert get_team(702, "mine")[0]["species"] == "Abomasnow"


def test_finalize_import_reports_the_size_cap_without_storing():
    seven_members = [dict(_ABOMASNOW_TEAM_MEMBER, species="Abomasnow") for _ in range(7)]

    result = finalize_import(703, "mine", seven_members, [])

    assert result["ok"] is False
    assert "at most" in result["message"]
    assert get_team(703, "mine") == []


def test_import_confirm_view_confirm_button_calls_on_confirm():
    on_confirm = AsyncMock()
    on_cancel = AsyncMock()
    view = ImportConfirmView(user_id=1, on_confirm=on_confirm, on_cancel=on_cancel)
    confirm_button = view.children[0]
    interaction = MagicMock()
    interaction.user.id = 1

    asyncio.run(confirm_button.callback(interaction))

    on_confirm.assert_awaited_once_with(interaction)
    on_cancel.assert_not_awaited()


def test_import_confirm_view_cancel_button_calls_on_cancel():
    on_confirm = AsyncMock()
    on_cancel = AsyncMock()
    view = ImportConfirmView(user_id=1, on_confirm=on_confirm, on_cancel=on_cancel)
    cancel_button = view.children[1]
    interaction = MagicMock()
    interaction.user.id = 1

    asyncio.run(cancel_button.callback(interaction))

    on_cancel.assert_awaited_once_with(interaction)
    on_confirm.assert_not_awaited()


def test_import_confirm_view_interaction_check_rejects_a_different_user():
    view = ImportConfirmView(user_id=1, on_confirm=AsyncMock(), on_cancel=AsyncMock())
    interaction = MagicMock()
    interaction.user.id = 999
    interaction.response.send_message = AsyncMock()

    allowed = asyncio.run(view.interaction_check(interaction))

    assert allowed is False


def test_view_team_button_view_edits_in_the_team_panel():
    store_team(704, "mine", [_ABOMASNOW_TEAM_MEMBER])
    view = ViewTeamButtonView(user_id=704, side="mine")
    button = view.children[0]
    interaction = MagicMock()
    interaction.user.id = 704
    interaction.response.edit_message = AsyncMock()

    asyncio.run(button.callback(interaction))

    _args, kwargs = interaction.response.edit_message.call_args
    assert "Abomasnow" in kwargs["embed"].description
    from bot.commands.team import TeamView
    assert isinstance(kwargs["view"], TeamView)
    assert kwargs["view"].side == "mine"


def test_view_team_button_view_interaction_check_rejects_a_different_user():
    view = ViewTeamButtonView(user_id=704, side="mine")
    interaction = MagicMock()
    interaction.user.id = 999
    interaction.response.send_message = AsyncMock()

    allowed = asyncio.run(view.interaction_check(interaction))

    assert allowed is False
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_bot_team.py -v -k "prepare_import or finalize_import or ImportConfirmView or ViewTeamButtonView or view_team_button"`
Expected: FAIL with `ImportError` (`prepare_import`, `finalize_import`, `ImportConfirmView`, `ViewTeamButtonView` don't exist yet).

- [ ] **Step 3: Implement**

Add `import discord` as the first line of `bot/commands/team.py`.

Change `import_team_response` from:

```python
def import_team_response(
    records: list, moves: list, user_id: int, side: str, pokepaste_text: str, items: list = None
) -> str:
    try:
        members = parse_pokepaste(pokepaste_text)
    except PokepasteParseError as e:
        return f"Could not parse team: {e}"

    warnings = []
    for member in members:
        warnings.extend(_validate_member(records, moves, items, member))

    try:
        store_team(user_id, side, members)
    except ValueError as e:
        return str(e)

    lines = [f"Loaded {len(members)} Pokemon into {_POSSESSIVE_LABELS[side]} team:"]
    lines.extend(f"- {m['species']}" for m in members)
    lines.extend(_format_warnings(warnings))
    return "\n".join(lines)
```

to:

```python
def prepare_import(records: list, moves: list, side: str, pokepaste_text: str, items: list = None) -> dict:
    """Parse and validate a Pokepaste import WITHOUT storing it, so a caller
    can show an overwrite-confirmation prompt before finalize_import commits
    anything. Returns {"ok": False, "message": str} on a parse error, or
    {"ok": True, "members": list, "warnings": list} on success."""
    try:
        members = parse_pokepaste(pokepaste_text)
    except PokepasteParseError as e:
        return {"ok": False, "message": f"Could not parse team: {e}"}

    warnings = []
    for member in members:
        warnings.extend(_validate_member(records, moves, items, member))

    return {"ok": True, "members": members, "warnings": warnings}


def finalize_import(user_id: int, side: str, members: list, warnings: list) -> dict:
    """Actually stores an already-prepared import. Returns
    {"ok": False, "message": str} if store_team rejects it (e.g. over the
    6-Pokemon cap), or {"ok": True, "message": str} on success."""
    try:
        store_team(user_id, side, members)
    except ValueError as e:
        return {"ok": False, "message": str(e)}

    lines = [f"Loaded {len(members)} Pokemon into {_POSSESSIVE_LABELS[side]} team:"]
    lines.extend(f"- {m['species']}" for m in members)
    lines.extend(_format_warnings(warnings))
    return {"ok": True, "message": "\n".join(lines)}


def import_team_response(
    records: list, moves: list, user_id: int, side: str, pokepaste_text: str, items: list = None
) -> str:
    """Backward-compatible one-shot wrapper: parse, validate, and store in
    a single call with no overwrite confirmation. bot/main.py's /import
    handler no longer calls this directly -- it calls prepare_import/
    finalize_import itself so it can show ImportConfirmView in between --
    but every existing caller/test of this function keeps working exactly
    as before."""
    prepared = prepare_import(records, moves, side, pokepaste_text, items=items)
    if not prepared["ok"]:
        return prepared["message"]
    return finalize_import(user_id, side, prepared["members"], prepared["warnings"])["message"]
```

Then, at the end of the file, add the two new Views:

```python
class ImportConfirmView(discord.ui.View):
    """Shown when /import would overwrite an already-stored team on the
    target side. on_confirm/on_cancel are async (interaction) -> None
    callbacks the call site supplies -- this view has no opinion on what
    either one actually does."""

    def __init__(self, user_id: int, on_confirm, on_cancel):
        super().__init__()
        self.user_id = user_id
        confirm_button = discord.ui.Button(label="Confirm", style=discord.ButtonStyle.danger)
        confirm_button.callback = self._wrap(on_confirm)
        cancel_button = discord.ui.Button(label="Cancel", style=discord.ButtonStyle.secondary)
        cancel_button.callback = self._wrap(on_cancel)
        self.add_item(confirm_button)
        self.add_item(cancel_button)

    def _wrap(self, handler):
        async def callback(interaction: discord.Interaction) -> None:
            await handler(interaction)

        return callback

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your import confirmation.", ephemeral=True)
            return False
        return True


class ViewTeamButtonView(discord.ui.View):
    """Attached to a successful /import result: one button that jumps
    straight into the same panel /team itself produces for that side,
    reusing view_team_response/TeamView completely unchanged."""

    def __init__(self, user_id: int, side: str):
        super().__init__()
        self.user_id = user_id
        self.side = side
        button = discord.ui.Button(label="View team", style=discord.ButtonStyle.secondary)
        button.callback = self._callback
        self.add_item(button)

    async def _callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            embed=_team_embed(view_team_response(self.user_id, self.side)),
            view=TeamView(self.user_id, self.side),
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your team.", ephemeral=True)
            return False
        return True
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_bot_team.py -v`
Expected: all PASS (new and pre-existing — every existing `import_team_response`-calling test keeps passing since the wrapper's behavior is unchanged).

- [ ] **Step 5: Commit**

```bash
git add bot/commands/team.py tests/test_bot_team.py
git commit -m "feat: split import into prepare/finalize, add confirm and view-team views"
```

---

### Task 2: Wire the confirmation flow into `/import`

**Files:**
- Modify: `bot/main.py`
- Modify: `tests/test_bot_main.py`

**Interfaces:**
- Consumes: `prepare_import`, `finalize_import`, `ImportConfirmView`, `ViewTeamButtonView` (Task 1).
- Produces: nothing consumed by a later task — this is the final task in this plan.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_bot_main.py`:

```python
def test_import_command_imports_immediately_when_nothing_is_stored_yet():
    _client, tree = build_client(records=_CALC_TEST_RECORDS, moves=_CALC_TEST_MOVES)
    import_cmd = tree.get_command("import")
    interaction = MagicMock()
    interaction.user.id = 8001
    interaction.response.defer = AsyncMock()
    interaction.followup.send = AsyncMock()

    asyncio.run(import_cmd.callback(interaction, side="mine", pokepaste="Garchomp\n- Earthquake\n"))

    interaction.followup.send.assert_awaited_once()
    _args, kwargs = interaction.followup.send.call_args
    assert "Loaded 1 Pokemon" in kwargs["embed"].description
    from bot.commands.team import ViewTeamButtonView
    assert isinstance(kwargs["view"], ViewTeamButtonView)


def test_import_command_shows_a_confirmation_view_when_a_team_is_already_stored():
    from bot.team_store import store_team

    store_team(8002, "mine", [{
        "species": "Absol", "nickname": None, "gender": None, "item": None, "ability": None,
        "level": 50, "tera_type": None,
        "evs": {"hp": 0, "attack": 0, "defense": 0, "sp_attack": 0, "sp_defense": 0, "speed": 0},
        "ivs": {"hp": 31, "attack": 31, "defense": 31, "sp_attack": 31, "sp_defense": 31, "speed": 31},
        "nature": "Hardy", "moves": [],
    }])
    _client, tree = build_client(records=_CALC_TEST_RECORDS, moves=_CALC_TEST_MOVES)
    import_cmd = tree.get_command("import")
    interaction = MagicMock()
    interaction.user.id = 8002
    interaction.response.defer = AsyncMock()
    interaction.followup.send = AsyncMock()

    asyncio.run(import_cmd.callback(interaction, side="mine", pokepaste="Garchomp\n- Earthquake\n"))

    from bot.commands.team import ImportConfirmView

    interaction.followup.send.assert_awaited_once()
    _args, kwargs = interaction.followup.send.call_args
    assert isinstance(kwargs["view"], ImportConfirmView)
    from bot.team_store import get_team
    assert get_team(8002, "mine")[0]["species"] == "Absol"  # not yet overwritten


def test_import_command_confirm_button_completes_the_overwrite():
    from bot.team_store import get_team, store_team

    store_team(8003, "mine", [{
        "species": "Absol", "nickname": None, "gender": None, "item": None, "ability": None,
        "level": 50, "tera_type": None,
        "evs": {"hp": 0, "attack": 0, "defense": 0, "sp_attack": 0, "sp_defense": 0, "speed": 0},
        "ivs": {"hp": 31, "attack": 31, "defense": 31, "sp_attack": 31, "sp_defense": 31, "speed": 31},
        "nature": "Hardy", "moves": [],
    }])
    _client, tree = build_client(records=_CALC_TEST_RECORDS, moves=_CALC_TEST_MOVES)
    import_cmd = tree.get_command("import")
    interaction = MagicMock()
    interaction.user.id = 8003
    interaction.response.defer = AsyncMock()
    interaction.followup.send = AsyncMock()

    asyncio.run(import_cmd.callback(interaction, side="mine", pokepaste="Garchomp\n- Earthquake\n"))

    _args, kwargs = interaction.followup.send.call_args
    confirm_button = kwargs["view"].children[0]
    confirm_interaction = MagicMock()
    confirm_interaction.user.id = 8003
    confirm_interaction.response.edit_message = AsyncMock()

    asyncio.run(confirm_button.callback(confirm_interaction))

    assert get_team(8003, "mine")[0]["species"] == "Garchomp"
    _args, edit_kwargs = confirm_interaction.response.edit_message.call_args
    assert "Loaded 1 Pokemon" in edit_kwargs["embed"].description


def test_import_command_cancel_button_leaves_the_stored_team_untouched():
    from bot.team_store import get_team, store_team

    store_team(8004, "mine", [{
        "species": "Absol", "nickname": None, "gender": None, "item": None, "ability": None,
        "level": 50, "tera_type": None,
        "evs": {"hp": 0, "attack": 0, "defense": 0, "sp_attack": 0, "sp_defense": 0, "speed": 0},
        "ivs": {"hp": 31, "attack": 31, "defense": 31, "sp_attack": 31, "sp_defense": 31, "speed": 31},
        "nature": "Hardy", "moves": [],
    }])
    _client, tree = build_client(records=_CALC_TEST_RECORDS, moves=_CALC_TEST_MOVES)
    import_cmd = tree.get_command("import")
    interaction = MagicMock()
    interaction.user.id = 8004
    interaction.response.defer = AsyncMock()
    interaction.followup.send = AsyncMock()

    asyncio.run(import_cmd.callback(interaction, side="mine", pokepaste="Garchomp\n- Earthquake\n"))

    _args, kwargs = interaction.followup.send.call_args
    cancel_button = kwargs["view"].children[1]
    cancel_interaction = MagicMock()
    cancel_interaction.user.id = 8004
    cancel_interaction.response.edit_message = AsyncMock()

    asyncio.run(cancel_button.callback(cancel_interaction))

    assert get_team(8004, "mine")[0]["species"] == "Absol"  # unchanged
```

(`_CALC_TEST_RECORDS`/`_CALC_TEST_MOVES` already exist earlier in `tests/test_bot_main.py`.)

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_bot_main.py -v -k "import_command_imports_immediately or import_command_shows_a_confirmation or import_command_confirm or import_command_cancel"`
Expected: all 4 FAIL — the handler still calls the old `import_team_response` and never attaches a `view=` kwarg at all, so `kwargs["view"]` raises `KeyError` (or `AttributeError` for the confirm/cancel button lookups, since there's no view to index into).

- [ ] **Step 3: Implement**

Change the `bot.commands.team` import from:

```python
from bot.commands.team import (
    format_team_block,
    import_team_response,
    scout_response,
    view_team_response,
)
```

to:

```python
from bot.commands.team import (
    ImportConfirmView,
    ViewTeamButtonView,
    finalize_import,
    format_team_block,
    prepare_import,
    scout_response,
    view_team_response,
)
```

(`import_team_response` is no longer used by `bot/main.py` — this handler now calls `prepare_import`/`finalize_import` directly. It stays exported from `bot/commands/team.py` for its own direct callers/tests, per Task 1.)

Change the `/import` command from:

```python
    @tree.command(name="import", description="Import a full Pokemon team from Pokepaste text or a pokepast.es URL.")
    @app_commands.checks.cooldown(1, _COOLDOWN_SECONDS)
    async def import_team(
        interaction: discord.Interaction,
        side: Literal["mine", "opponent"],
        pokepaste: str,
    ) -> None:
        await interaction.response.defer()
        try:
            raw_text = await asyncio.to_thread(resolve_pokepaste_text, pokepaste)
        except PokepasteFetchError as e:
            await interaction.followup.send(embed=_embed("import", str(e)))
            return
        response = import_team_response(records, moves, interaction.user.id, side, raw_text, items=items)
        await interaction.followup.send(embed=_embed("import", response))
```

to:

```python
    @tree.command(name="import", description="Import a full Pokemon team from Pokepaste text or a pokepast.es URL.")
    @app_commands.checks.cooldown(1, _COOLDOWN_SECONDS)
    async def import_team(
        interaction: discord.Interaction,
        side: Literal["mine", "opponent"],
        pokepaste: str,
    ) -> None:
        await interaction.response.defer()
        try:
            raw_text = await asyncio.to_thread(resolve_pokepaste_text, pokepaste)
        except PokepasteFetchError as e:
            await interaction.followup.send(embed=_embed("import", str(e)))
            return

        prepared = prepare_import(records, moves, side, raw_text, items=items)
        if not prepared["ok"]:
            await interaction.followup.send(embed=_embed("import", prepared["message"]))
            return

        user_id = interaction.user.id
        members, warnings = prepared["members"], prepared["warnings"]

        async def _finalize_and_send(target_interaction: discord.Interaction, as_followup: bool) -> None:
            result = finalize_import(user_id, side, members, warnings)
            view = ViewTeamButtonView(user_id, side) if result["ok"] else None
            embed = _embed("import", result["message"])
            if as_followup:
                await target_interaction.followup.send(embed=embed, view=view)
            else:
                await target_interaction.response.edit_message(embed=embed, view=view)

        if get_team(user_id, side):
            async def _on_confirm(confirm_interaction: discord.Interaction) -> None:
                await _finalize_and_send(confirm_interaction, as_followup=False)

            async def _on_cancel(cancel_interaction: discord.Interaction) -> None:
                await cancel_interaction.response.edit_message(
                    embed=_embed("import", f"Import cancelled -- your stored '{side}' team is unchanged."),
                    view=None,
                )

            await interaction.followup.send(
                embed=_embed(
                    "import", f"You already have a team stored for '{side}'. Replace it with this import?"
                ),
                view=ImportConfirmView(user_id, _on_confirm, _on_cancel),
            )
            return

        await _finalize_and_send(interaction, as_followup=True)
```

(`get_team` is already imported in `bot/main.py` today via `from bot.team_store import find_team_member, get_team, resolve_calc_overrides` — no change needed to that line.)

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_bot_main.py -v -k import`
Expected: all PASS, including the pre-existing `test_import_command_is_registered_on_the_tree`, `test_import_command_reports_a_fetch_error_without_crashing`, and `test_import_then_calc_uses_the_real_parsed_team_data`.

- [ ] **Step 5: Run the entire test suite as a final check**

Run: `pytest -q`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add bot/main.py tests/test_bot_main.py
git commit -m "feat: confirm before /import overwrites a stored team, add View team button"
```

---

## Self-review notes

- **Spec coverage:** overwrite confirmation only when a team already exists on that side, immediate import otherwise; "View team" button on a successful import jumping into `/team`'s own `TeamView`; `/scout` correctly untouched — all covered.
- **Placeholder scan:** no TBD/TODO; every step has complete, runnable code.
- **Type consistency checked:** `prepare_import`'s and `finalize_import`'s `{"ok": bool, ...}` dict shape is read identically by `import_team_response` (Task 1) and `bot/main.py`'s handler (Task 2). `ImportConfirmView`'s `on_confirm`/`on_cancel` callback signature (`(interaction) -> None`) matches every closure passed to it in Task 2.
- **Backward-compatibility verified:** `import_team_response`'s signature and return type are unchanged — confirmed against every existing test in `tests/test_bot_team.py` that calls it directly (`test_import_team_response_stores_and_confirms` and 8 others), none of which are modified by this plan.
- **Prerequisite dependency called out explicitly** at the top of this document and in Task 1's Interfaces section — `TeamView`/`_team_embed` must exist before Task 1 can be implemented, even though the rest of the `/team` plan does not need to have shipped.
