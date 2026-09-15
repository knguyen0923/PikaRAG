# `/dex` Roster Browser (Slice D) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A new `/dex` command pages through the currently-loaded legal Pokemon roster one at a time with Prev/Next buttons, Pokedex-style, with an optional `start` parameter to jump straight to a named Pokemon's page.

**Architecture:** A new `bot/commands/dex.py` holds `dex_page_response(records, index) -> str` (a compact one-Pokemon card reusing `stats_response`'s exact formatting, prefixed with a `(N/Total)` position marker) and `DexBrowseView(discord.ui.View)`, which holds "◀ Prev"/"Next ▶" buttons, each `disabled=True` at the respective boundary rather than hidden so the panel's layout doesn't shift. `bot/main.py` registers `/dex` with one optional `start: Optional[str] = None` parameter — with no argument it opens at index 0; with `start` given, it resolves the name via `find_record` and opens at that Pokemon's position in the `records` list, falling back to Slice A's suggestion dropdown on a near-miss.

**Tech Stack:** Python 3.9, `discord.py` 2.7.1's `discord.ui` — no new dependencies.

**Spec:** `docs/superpowers/specs/2026-09-15-poketwo-style-ui-design.md` (Slice D).

## Global Constraints

- **Soft prerequisite, `start` parameter only:** `/dex`'s `start`-not-found path reuses Slice A's `NameSuggestionView` (`bot/ui.py`) — Slice A (`2026-09-15-name-suggestion-dropdown.md`) must be implemented first for that specific fallback to work. This does **not** block the rest of the command: Task 1 (`dex_page_response`) and the core Prev/Next browsing in Task 2 have no dependency on Slice A at all. This is a refinement over the spec's blanket "Slices A, B, D have no dependency on each other" line, discovered while writing this plan — the spec's own Slice D section already described the `start`-miss path going through Slice A's dropdown, this note just makes the resulting dependency explicit rather than leaving it implicit.
- `/dex` never mutates `records` — `records.index(record)` is used read-only to locate a starting position.
- Every `DexBrowseView` interaction is invoker-only (`interaction_check` comparing `interaction.user.id`, ephemeral rejection on mismatch) and re-renders via `interaction.response.edit_message(...)` — the same conventions every other View in this initiative already establishes.
- This command assumes `records` is non-empty, matching every other command in this bot (`_load_records()` always loads the live, non-empty `pokemon_records.json`) — no special-casing for an empty roster.

---

## File structure

- Create `bot/commands/dex.py` — `dex_page_response`, `_dex_embed`, `DexBrowseView`.
- Create `tests/test_bot_dex.py` — tests for `dex_page_response` and `DexBrowseView`.
- Modify `bot/main.py` — register `/dex`; add a `"dex"` entry to `_COMMAND_COLORS`.
- Modify `tests/test_bot_main.py` — tests for `/dex`'s registration, default start, `start`-name resolution, and the suggestion-dropdown fallback.

---

### Task 1: `dex_page_response` — one-Pokemon roster card

**Files:**
- Create: `bot/commands/dex.py`
- Test: `tests/test_bot_dex.py`

**Interfaces:**
- Consumes: `stats_response` (`bot/commands/stats.py`, unchanged).
- Produces: `dex_page_response(records: list, index: int) -> str`. Task 2's `DexBrowseView` calls this for every page render.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_bot_dex.py`:

```python
from bot.commands.dex import dex_page_response

_ABOMASNOW = {
    "name": "Abomasnow", "types": ["Grass", "Ice"],
    "base_stats": {"hp": 90, "attack": 92, "defense": 75, "sp_attack": 92, "sp_defense": 85, "speed": 60},
    "abilities": ["Snow Warning", "Soundproof"], "learnset": ["Blizzard", "Wood Hammer"], "legal_in": ["M-B"],
}
_GYARADOS = {
    "name": "Gyarados", "types": ["Water", "Flying"],
    "base_stats": {"hp": 95, "attack": 125, "defense": 79, "sp_attack": 60, "sp_defense": 100, "speed": 81},
    "abilities": ["Intimidate"], "learnset": ["Waterfall", "Dragon Dance"], "legal_in": ["M-B"],
}
_RECORDS = [_ABOMASNOW, _GYARADOS]


def test_dex_page_response_shows_the_record_at_the_given_index():
    response = dex_page_response(_RECORDS, 0)

    assert "Abomasnow" in response
    assert "HP 90" in response


def test_dex_page_response_shows_the_second_record():
    response = dex_page_response(_RECORDS, 1)

    assert "Gyarados" in response


def test_dex_page_response_includes_a_position_marker():
    response = dex_page_response(_RECORDS, 0)

    assert "(1/2)" in response

    response = dex_page_response(_RECORDS, 1)

    assert "(2/2)" in response
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_bot_dex.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bot.commands.dex'`.

- [ ] **Step 3: Implement**

Create `bot/commands/dex.py`:

```python
from bot.commands.stats import stats_response


def dex_page_response(records: list, index: int) -> str:
    record = records[index]
    return f"({index + 1}/{len(records)}) {stats_response(records, record['name'])}"
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_bot_dex.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add bot/commands/dex.py tests/test_bot_dex.py
git commit -m "feat: add dex_page_response roster-card formatter"
```

---

### Task 2: `DexBrowseView` and the `/dex` command

**Files:**
- Modify: `bot/commands/dex.py`
- Modify: `tests/test_bot_dex.py`
- Modify: `bot/main.py`
- Modify: `tests/test_bot_main.py`

**Interfaces:**
- Consumes: `dex_page_response` (Task 1); `NameSuggestionView` (`bot/ui.py`, from Slice A — see the soft-prerequisite Global Constraint above).
- Produces: `DexBrowseView(records, index, user_id)`. Nothing consumed by a later task — this is the final task in this plan.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_bot_dex.py`:

```python
import asyncio
from unittest.mock import AsyncMock, MagicMock

from bot.commands.dex import DexBrowseView


def test_dex_browse_view_disables_prev_at_the_first_page():
    view = DexBrowseView(_RECORDS, index=0, user_id=1)

    prev_button, next_button = view.children

    assert prev_button.disabled is True
    assert next_button.disabled is False


def test_dex_browse_view_disables_next_at_the_last_page():
    view = DexBrowseView(_RECORDS, index=1, user_id=1)

    prev_button, next_button = view.children

    assert prev_button.disabled is False
    assert next_button.disabled is True


def test_dex_browse_view_next_button_advances_the_page():
    view = DexBrowseView(_RECORDS, index=0, user_id=1)
    _prev_button, next_button = view.children
    interaction = MagicMock()
    interaction.user.id = 1
    interaction.response.edit_message = AsyncMock()

    asyncio.run(next_button.callback(interaction))

    _args, kwargs = interaction.response.edit_message.call_args
    assert "Gyarados" in kwargs["embed"].description
    assert isinstance(kwargs["view"], DexBrowseView)
    assert kwargs["view"].index == 1


def test_dex_browse_view_prev_button_goes_back_a_page():
    view = DexBrowseView(_RECORDS, index=1, user_id=1)
    prev_button, _next_button = view.children
    interaction = MagicMock()
    interaction.user.id = 1
    interaction.response.edit_message = AsyncMock()

    asyncio.run(prev_button.callback(interaction))

    _args, kwargs = interaction.response.edit_message.call_args
    assert kwargs["view"].index == 0


def test_dex_browse_view_interaction_check_rejects_a_different_user():
    view = DexBrowseView(_RECORDS, index=0, user_id=1)
    interaction = MagicMock()
    interaction.user.id = 999
    interaction.response.send_message = AsyncMock()

    allowed = asyncio.run(view.interaction_check(interaction))

    assert allowed is False
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_bot_dex.py -v -k DexBrowseView`
Expected: FAIL with `ImportError: cannot import name 'DexBrowseView' from 'bot.commands.dex'`.

- [ ] **Step 3: Implement `DexBrowseView`**

Add to `bot/commands/dex.py` (add `import discord` as the file's first line):

```python
import discord

from bot.commands.stats import stats_response


def dex_page_response(records: list, index: int) -> str:
    ...  # unchanged from Task 1


def _dex_embed(description: str) -> discord.Embed:
    return discord.Embed(description=description, color=discord.Color.magenta())


class DexBrowseView(discord.ui.View):
    """Pokedex-style Prev/Next browser over the current regulation's legal
    roster. Buttons are disabled (not hidden) at either boundary so the
    panel's layout doesn't shift at the ends."""

    def __init__(self, records: list, index: int, user_id: int):
        super().__init__()
        self.records = records
        self.index = index
        self.user_id = user_id
        prev_button = discord.ui.Button(
            label="◀ Prev", style=discord.ButtonStyle.secondary, disabled=(index == 0)
        )
        prev_button.callback = self._make_callback(-1)
        next_button = discord.ui.Button(
            label="Next ▶", style=discord.ButtonStyle.secondary, disabled=(index == len(records) - 1)
        )
        next_button.callback = self._make_callback(1)
        self.add_item(prev_button)
        self.add_item(next_button)

    def _make_callback(self, delta: int):
        async def callback(interaction: discord.Interaction) -> None:
            new_index = self.index + delta
            await interaction.response.edit_message(
                embed=_dex_embed(dex_page_response(self.records, new_index)),
                view=DexBrowseView(self.records, new_index, self.user_id),
            )

        return callback

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your dex browser.", ephemeral=True)
            return False
        return True
```

(Leave `dex_page_response`'s body exactly as Task 1 wrote it.)

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_bot_dex.py -v`
Expected: all PASS.

- [ ] **Step 5: Write the failing tests for `bot/main.py`**

Add to `tests/test_bot_main.py`:

```python
def test_dex_command_is_registered_on_the_tree():
    _client, tree = build_client()
    commands = {command.name: command for command in tree.get_commands()}

    assert "dex" in commands
    assert "browse" in commands["dex"].description.lower() or "roster" in commands["dex"].description.lower()


def test_dex_command_opens_at_the_first_page_with_no_start():
    _client, tree = build_client(records=_CALC_TEST_RECORDS)
    dex_cmd = tree.get_command("dex")
    interaction = MagicMock()
    interaction.user.id = 1
    interaction.response.send_message = AsyncMock()

    asyncio.run(dex_cmd.callback(interaction, start=None))

    from bot.commands.dex import DexBrowseView

    _args, kwargs = interaction.response.send_message.call_args
    assert isinstance(kwargs["view"], DexBrowseView)
    assert kwargs["view"].index == 0


def test_dex_command_jumps_to_a_named_start():
    records = _CALC_TEST_RECORDS + [{
        "name": "Absol", "types": ["Dark"],
        "base_stats": {"hp": 65, "attack": 130, "defense": 60, "sp_attack": 75, "sp_defense": 60, "speed": 75},
        "abilities": ["Pressure"], "learnset": ["Night Slash"], "legal_in": ["M-B"],
    }]
    _client, tree = build_client(records=records)
    dex_cmd = tree.get_command("dex")
    interaction = MagicMock()
    interaction.user.id = 1
    interaction.response.send_message = AsyncMock()

    asyncio.run(dex_cmd.callback(interaction, start="Absol"))

    _args, kwargs = interaction.response.send_message.call_args
    assert "Absol" in kwargs["embed"].description
    assert kwargs["view"].index == 1


def test_dex_command_shows_a_suggestion_view_for_a_mistyped_start():
    _client, tree = build_client(records=_CALC_TEST_RECORDS)
    dex_cmd = tree.get_command("dex")
    interaction = MagicMock()
    interaction.user.id = 1
    interaction.response.send_message = AsyncMock()

    asyncio.run(dex_cmd.callback(interaction, start="Garchom"))

    from bot.ui import NameSuggestionView

    _args, kwargs = interaction.response.send_message.call_args
    assert isinstance(kwargs["view"], NameSuggestionView)
```

(`_CALC_TEST_RECORDS` already exists earlier in `tests/test_bot_main.py`.)

- [ ] **Step 6: Run the tests to verify they fail**

Run: `pytest tests/test_bot_main.py -v -k dex_command`
Expected: all 4 FAIL — `tree.get_command("dex")` returns `None` (`AttributeError`/`TypeError` calling `.callback` on it).

- [ ] **Step 7: Implement the `bot/main.py` change**

Add these imports alongside the existing ones:

```python
from bot.commands.dex import DexBrowseView, dex_page_response
from bot.pokemon_lookup import find_record, not_found_message, suggest_names
from bot.ui import NameSuggestionView
```

(If Slice A has already been implemented, `bot/pokemon_lookup` and `bot/ui` imports already exist — extend the existing lines rather than duplicating them.)

Add `"dex": discord.Color.magenta(),` to `_COMMAND_COLORS` (matching `DexBrowseView`'s own `_dex_embed` color, so the initial response and every subsequent page look the same).

Add the new command (place it after `/team`, before `/calc`):

```python
    @tree.command(name="dex", description="Browse the current regulation's legal Pokemon roster, Pokedex-style.")
    @app_commands.checks.cooldown(1, _COOLDOWN_SECONDS)
    async def dex(interaction: discord.Interaction, start: Optional[str] = None) -> None:
        index = 0
        if start is not None:
            record = find_record(records, start)
            if record is None:
                suggestions = suggest_names(records, start)
                message = not_found_message(records, start)
                if not suggestions:
                    await interaction.response.send_message(embed=_embed("dex", message))
                    return

                async def _on_select(inner_interaction: discord.Interaction, chosen: str) -> None:
                    chosen_index = records.index(find_record(records, chosen))
                    await inner_interaction.response.edit_message(
                        embed=_embed("dex", dex_page_response(records, chosen_index)),
                        view=DexBrowseView(records, chosen_index, inner_interaction.user.id),
                    )

                await interaction.response.send_message(
                    embed=_embed("dex", message),
                    view=NameSuggestionView(interaction.user.id, suggestions, _on_select),
                )
                return
            index = records.index(record)

        await interaction.response.send_message(
            embed=_embed("dex", dex_page_response(records, index)),
            view=DexBrowseView(records, index, interaction.user.id),
        )
```

- [ ] **Step 8: Run the tests to verify they pass**

Run: `pytest tests/test_bot_main.py -v -k dex_command`
Expected: all PASS.

- [ ] **Step 9: Run the entire test suite as a final check**

Run: `pytest -q`
Expected: all PASS.

- [ ] **Step 10: Commit**

```bash
git add bot/commands/dex.py tests/test_bot_dex.py bot/main.py tests/test_bot_main.py
git commit -m "feat: add /dex Pokedex-style roster browser"
```

---

## Self-review notes

- **Spec coverage:** Prev/Next paging over the full legal roster with boundary-disabled buttons; optional `start` parameter jumping to a named Pokemon's page; a mistyped `start` falling back to Slice A's suggestion dropdown — all covered, with the Slice A dependency made explicit rather than left implicit.
- **Placeholder scan:** no TBD/TODO; the `...  # unchanged from Task 1` line in Task 2 Step 3 is an explicit "don't touch this" instruction immediately followed by the real code, not an unwritten placeholder.
- **Type consistency checked:** `DexBrowseView.__init__(self, records, index, user_id)`'s three positional args match every call site (Task 2's own recursive re-construction, and `bot/main.py`'s two construction points). `dex_page_response(records, index)`'s signature matches every caller (Task 1's tests, `DexBrowseView`, `bot/main.py`'s `/dex` handler).
- **Regression risk audited:** `/dex` is an entirely new command — no existing command's registration, behavior, or tests are touched by this plan.
