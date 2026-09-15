# Team Button UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `/team`'s `side: Literal["mine", "opponent"]` slash-command parameter with two buttons ("Your team" / "Opponent's team") that re-render the same message in place, validating discord.ui.View usage on one low-risk command before any other command adopts the pattern.

**Architecture:** A new `TeamView(discord.ui.View)` class in `bot/commands/team.py` holds two `discord.ui.Button`s, one per side, built from the file's existing `_SIDE_LABELS` mapping. Each button's callback re-renders the message via `interaction.response.edit_message(...)`, passing a fresh `TeamView` reflecting the newly-selected side. `TeamView.interaction_check` restricts clicks to whoever ran `/team`, sending its own ephemeral rejection (a `discord.ui.View` check does not route through `bot/main.py`'s `@tree.error` handler — that's a separate mechanism for `app_commands.check` failures only). `bot/main.py`'s `/team` command drops its `side` parameter, always starts on `"mine"`, and attaches an initial `TeamView` to its first response. All existing pure functions (`view_team_response`, `format_team_block`) are reused completely unchanged.

**Tech Stack:** Python 3.9, `discord.py` 2.7.1's `discord.ui` module (this bot's first use of it) — no new dependencies.

**Spec:** `docs/superpowers/specs/2026-09-15-team-button-ui-design.md`

## Global Constraints

- No persistence: the view relies on discord.py's default (non-`custom_id`) 180-second timeout. `View.on_timeout` is a no-op in the base class, so nothing automatically greys out the buttons or notifies the user when it elapses — a stale click after timeout just fails with Discord's generic "This interaction failed" error toast. No `on_timeout` override.
- Only `/team` changes. `/ask`, `/stats`, `/moves`, `/calc`, `/import`, `/scout`, `/debug-last`, `/llmstatus`, `/ping` are untouched.
- No per-slot pagination, no modal editing — clicking a button only swaps which side's team is displayed.
- `interaction_check` must send its own ephemeral rejection before returning `False` — a bare `return False` silently no-ops the click with zero feedback to the user, which reads as a broken button.
- Every button click uses `interaction.response.edit_message(...)`, never a new `send_message` — that in-place edit is the entire reason to use a View here.
- No test requires real Discord network access — everything uses `MagicMock`/`AsyncMock`, consistent with every other test in this codebase (see `tests/test_bot_main.py`'s existing pattern).

---

## File structure

- Modify `bot/commands/team.py` — add `import discord`, a `_team_embed(description) -> discord.Embed` helper (blurple, matching `bot/main.py`'s existing `_COMMAND_COLORS["team"]`), and the new `TeamView(discord.ui.View)` class. All existing functions in this file (`format_team_block`, `view_team_response`, `import_team_response`, `_validate_member`, `_format_warnings`, `scout_response`) are untouched.
- Modify `tests/test_bot_team.py` — add tests for `TeamView`'s two button callbacks and its `interaction_check`.
- Modify `bot/main.py` — import `TeamView` alongside the existing `bot.commands.team` imports; change the `/team` command's signature (drop `side`, always start on `"mine"`, attach `view=TeamView(...)` to the initial response). `_COMMAND_COLORS`, `_embed`, and every other command are untouched.
- Modify `tests/test_bot_main.py` — add a test confirming `/team`'s initial response attaches a `TeamView` starting on `"mine"`, and a registration-level test confirming the `side` parameter is gone.

---

### Task 1: `TeamView` in `bot/commands/team.py`

**Files:**
- Modify: `bot/commands/team.py`
- Test: `tests/test_bot_team.py`

**Interfaces:**
- Consumes: `view_team_response(user_id: int, side: str) -> str` (already exists, unchanged), `_SIDE_LABELS` (already exists in this file: `{"mine": "Your team", "opponent": "Opponent's team"}`).
- Produces: `TeamView(user_id: int, side: str)` — a `discord.ui.View` with a `.user_id` attribute, a `.side` attribute, and two children (`.children[0]` is the "Your team" button bound to side `"mine"`, `.children[1]` is the "Opponent's team" button bound to side `"opponent"`, matching `_SIDE_LABELS`' insertion order). Task 2's `bot/main.py` constructs `TeamView(interaction.user.id, "mine")` for `/team`'s initial response.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_bot_team.py` (add these imports to the top of the file alongside the existing ones):

```python
import asyncio
from unittest.mock import AsyncMock, MagicMock

from bot.commands.team import TeamView
```

Then append these tests at the end of the file:

```python
def test_team_view_has_your_team_and_opponents_team_buttons_in_order():
    view = TeamView(user_id=9001, side="mine")

    labels = [child.label for child in view.children]

    assert labels == ["Your team", "Opponent's team"]


def test_team_view_mine_button_edits_message_with_mine_side_and_a_fresh_view():
    view = TeamView(user_id=9001, side="opponent")
    mine_button = view.children[0]
    interaction = MagicMock()
    interaction.user.id = 9001
    interaction.response.edit_message = AsyncMock()

    asyncio.run(mine_button.callback(interaction))

    _args, kwargs = interaction.response.edit_message.call_args
    assert "no team" in kwargs["embed"].description.lower()
    assert isinstance(kwargs["view"], TeamView)
    assert kwargs["view"].side == "mine"
    assert kwargs["view"].user_id == 9001


def test_team_view_opponent_button_edits_message_with_opponent_side():
    view = TeamView(user_id=9001, side="mine")
    opponent_button = view.children[1]
    interaction = MagicMock()
    interaction.user.id = 9001
    interaction.response.edit_message = AsyncMock()

    asyncio.run(opponent_button.callback(interaction))

    _args, kwargs = interaction.response.edit_message.call_args
    assert isinstance(kwargs["view"], TeamView)
    assert kwargs["view"].side == "opponent"


def test_team_view_interaction_check_rejects_a_different_user_with_an_ephemeral_message():
    view = TeamView(user_id=9001, side="mine")
    interaction = MagicMock()
    interaction.user.id = 424242
    interaction.response.send_message = AsyncMock()

    allowed = asyncio.run(view.interaction_check(interaction))

    assert allowed is False
    interaction.response.send_message.assert_awaited_once()
    _args, kwargs = interaction.response.send_message.call_args
    assert kwargs["ephemeral"] is True


def test_team_view_interaction_check_allows_the_original_invoker():
    view = TeamView(user_id=9001, side="mine")
    interaction = MagicMock()
    interaction.user.id = 9001
    interaction.response.send_message = AsyncMock()

    allowed = asyncio.run(view.interaction_check(interaction))

    assert allowed is True
    interaction.response.send_message.assert_not_awaited()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_bot_team.py -v -k team_view`
Expected: FAIL with `ImportError: cannot import name 'TeamView' from 'bot.commands.team'`.

- [ ] **Step 3: Implement `TeamView` in `bot/commands/team.py`**

Add `import discord` as the first line of `bot/commands/team.py` (above the existing `from bot.pokemon_lookup import ...` line).

Then add this after the `view_team_response` function (right after its closing line, before `def _validate_member(...)`):

```python
def _team_embed(description: str) -> discord.Embed:
    return discord.Embed(description=description, color=discord.Color.blurple())


class TeamView(discord.ui.View):
    """Side-switcher for /team: two buttons that re-render the same message
    in place with the other side's team. discord.ui.View's interaction_check
    is a separate mechanism from app_commands.check (used by /debug-last and
    /llmstatus) and does not route through bot/main.py's @tree.error handler,
    so a rejected click must send its own ephemeral message here."""

    def __init__(self, user_id: int, side: str):
        super().__init__()
        self.user_id = user_id
        self.side = side
        for button_side, label in _SIDE_LABELS.items():
            button = discord.ui.Button(label=label)
            button.callback = self._make_callback(button_side)
            self.add_item(button)

    def _make_callback(self, side: str):
        async def callback(interaction: discord.Interaction) -> None:
            response = view_team_response(self.user_id, side)
            await interaction.response.edit_message(
                embed=_team_embed(response), view=TeamView(self.user_id, side)
            )

        return callback

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your team view.", ephemeral=True)
            return False
        return True
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_bot_team.py -v`
Expected: all PASS (new and pre-existing).

- [ ] **Step 5: Commit**

```bash
git add bot/commands/team.py tests/test_bot_team.py
git commit -m "feat: add TeamView side-switcher buttons for /team"
```

---

### Task 2: Wire `TeamView` into `/team` in `bot/main.py`

**Files:**
- Modify: `bot/main.py`
- Modify: `tests/test_bot_main.py`

**Interfaces:**
- Consumes: `TeamView(user_id: int, side: str)` (Task 1).
- Produces: nothing new consumed by a later task — this is the final task in this plan.

- [ ] **Step 1: Write the failing tests**

Add these tests to `tests/test_bot_main.py` (reuses the `asyncio`, `AsyncMock`, `MagicMock` imports already at the top of that file):

```python
def test_team_command_has_no_side_parameter():
    _client, tree = build_client()
    command = tree.get_command("team")

    assert command.get_parameter("side") is None


def test_team_command_attaches_a_team_view_starting_on_mine():
    from bot.commands.team import TeamView

    _client, tree = build_client()
    command = tree.get_command("team")
    interaction = MagicMock()
    interaction.user.id = 1
    interaction.response.send_message = AsyncMock()

    asyncio.run(command.callback(interaction))

    _args, kwargs = interaction.response.send_message.call_args
    assert isinstance(kwargs["view"], TeamView)
    assert kwargs["view"].side == "mine"
    assert kwargs["view"].user_id == 1
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_bot_main.py -v -k team_command`
Expected: `test_team_command_has_no_side_parameter` FAILs with `AssertionError` (the parameter still exists); `test_team_command_attaches_a_team_view_starting_on_mine` FAILs with `TypeError` (the callback still requires a `side` argument).

- [ ] **Step 3: Implement the changes to `bot/main.py`**

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
    TeamView,
    format_team_block,
    import_team_response,
    scout_response,
    view_team_response,
)
```

Change the `/team` command from:

```python
    @tree.command(name="team", description="View the Pokemon currently stored for your team or the opponent's team.")
    @app_commands.checks.cooldown(1, _COOLDOWN_SECONDS)
    async def team(interaction: discord.Interaction, side: Literal["mine", "opponent"]) -> None:
        await interaction.response.send_message(embed=_embed("team", view_team_response(interaction.user.id, side)))
```

to:

```python
    @tree.command(name="team", description="View the Pokemon currently stored for your team or the opponent's team.")
    @app_commands.checks.cooldown(1, _COOLDOWN_SECONDS)
    async def team(interaction: discord.Interaction) -> None:
        await interaction.response.send_message(
            embed=_embed("team", view_team_response(interaction.user.id, "mine")),
            view=TeamView(interaction.user.id, "mine"),
        )
```

`_embed`, `_COMMAND_COLORS["team"]`, and `view_team_response` are unchanged and still used for the initial response — only the button-click re-renders (Task 1) use `TeamView`'s own `_team_embed` helper, since `bot/commands/team.py` cannot import `_embed` from `bot/main.py` without creating a circular import (`bot/main.py` already imports from `bot/commands/team.py`).

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_bot_main.py -v -k team`
Expected: all PASS, including the pre-existing `test_team_view_command_is_registered_on_the_tree`.

- [ ] **Step 5: Run the entire test suite as a final check**

Run: `pytest -q`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add bot/main.py tests/test_bot_main.py
git commit -m "feat: wire TeamView buttons into the /team command"
```

---

## Self-review notes

- **Spec coverage:** two buttons labeled "Your team"/"Opponent's team" replacing the `side` parameter (Task 2); edit-in-place via `interaction.response.edit_message` on every click, never a new message (Task 1); invoker-only `interaction_check` with its own ephemeral rejection, explicitly not routed through `@tree.error` (Task 1); no persistence — relies on `discord.ui.View`'s default timeout, no `on_timeout` added (Task 1, nothing added); `view_team_response`/`format_team_block` reused completely unchanged (both tasks — neither function's body is touched) — all covered. Out-of-scope items (pagination, modal editing, any other command's buttons, persistent `custom_id` views) are correctly not touched by either task.
- **Placeholder scan:** no TBD/TODO markers; every step has runnable code and exact file paths.
- **Type consistency checked:** `TeamView.__init__(self, user_id: int, side: str)` is called identically in Task 1's own recursive re-construction (`TeamView(self.user_id, side)`) and in Task 2's `bot/main.py` (`TeamView(interaction.user.id, "mine")`) — same two positional args, same order, both times. `view_team_response(user_id, side)`'s signature (already existing) is called unchanged in both the pre-existing `bot/main.py` initial-response path and Task 1's new button-callback path.
- **Circular-import check:** `bot/commands/team.py` gains `import discord` only — it does not import anything from `bot/main.py`, so the existing one-directional import (`bot/main.py` → `bot/commands/team.py`) is preserved. This is why Task 1 gives `TeamView` its own `_team_embed` helper instead of reusing `bot/main.py`'s `_embed`.
