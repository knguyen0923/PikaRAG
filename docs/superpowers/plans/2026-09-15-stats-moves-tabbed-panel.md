# Stats/Moves Tabbed Panel (Slice B) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `/stats` and `/moves` keep their own names and independent registration, but whichever one is run opens a shared Stats/Moves/Usage tab panel, so pivoting between views doesn't require retyping the species name in a second command.

**Architecture:** A new `bot/commands/pokemon_info.py` holds `usage_response` (a new pure formatter — no existing function shows the *full* Pikalytics breakdown; `stats_response` only surfaces the single top item/ability and `moves_response` only the top moves) and `PokemonInfoView(discord.ui.View)`, which holds three buttons ("Stats"/"Moves"/"Usage") styled so the active tab (`discord.ButtonStyle.primary`) is visually distinct from the other two (`discord.ButtonStyle.secondary`) — a deliberate departure from `/team`'s `TeamView`, which gives its two buttons identical styling since they represent peer choices rather than a persistent tab set. Each tab's callback calls the matching response function (`stats_response`, `moves_response`, or the new `usage_response`) for the same species and re-renders via `edit_message`. `bot/main.py`'s `/stats` and `/moves` handlers attach an initial `PokemonInfoView` (starting on "Stats" or "Moves" respectively) whenever the species resolves.

**Tech Stack:** Python 3.9, `discord.py` 2.7.1's `discord.ui` — no new dependencies.

**Spec:** `docs/superpowers/specs/2026-09-15-poketwo-style-ui-design.md` (Slice B).

## Global Constraints

- `/stats` and `/moves` keep their exact existing names, descriptions, and parameters — this plan adds a panel on top of a successful lookup, it does not deprecate or merge the commands.
- A species that doesn't resolve at all is unaffected by this plan — no `PokemonInfoView` is built when there's no Pokemon to show tabs for (Slice A's suggestion dropdown, if implemented, is what handles that case; this plan doesn't depend on Slice A and doesn't touch that branch).
- Every `PokemonInfoView` interaction uses `interaction.response.edit_message(...)`, never a new message, and is invoker-only (`interaction_check` compares `interaction.user.id`, ephemeral rejection on mismatch) — the same conventions `/team`'s `TeamView` and Slice A's `NameSuggestionView` both already establish.
- **Sequencing note (not a hard dependency):** this plan's diff to `bot/main.py`'s `/stats`/`/moves` handlers is written against the current, unmodified handlers. If Slice A (`2026-09-15-name-suggestion-dropdown.md`) has already been implemented by the time this plan runs, those two handlers will already contain a not-found/suggestion branch — this plan's changes only need to wrap the *found* branch in a `PokemonInfoView`, so re-targeting the diff by hand at execution time is mechanical either way. No functional conflict between the two slices; they touch different branches of the same handler.

---

## File structure

- Create `bot/commands/pokemon_info.py` — `usage_response`, `PokemonInfoView`, `_panel_embed`.
- Create `tests/test_bot_pokemon_info.py` — tests for `usage_response` and `PokemonInfoView`.
- Modify `bot/main.py` — `/stats` and `/moves` handlers attach an initial `PokemonInfoView`.
- Modify `tests/test_bot_main.py` — new tests confirming both commands attach the right starting tab.

---

### Task 1: `usage_response` — full usage breakdown formatter

**Files:**
- Create: `bot/commands/pokemon_info.py`
- Test: `tests/test_bot_pokemon_info.py`

**Interfaces:**
- Consumes: `find_record`, `not_found_message`, `usage_for_record` (`bot/pokemon_lookup.py`, already exist, unchanged).
- Produces: `usage_response(records: list, name: str, usage: dict = None) -> str`. Task 2's `PokemonInfoView` calls this for its "Usage" tab.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_bot_pokemon_info.py`:

```python
from bot.commands.pokemon_info import usage_response

_ABOMASNOW = {
    "name": "Abomasnow", "types": ["Grass", "Ice"],
    "base_stats": {"hp": 90, "attack": 92, "defense": 75, "sp_attack": 92, "sp_defense": 85, "speed": 60},
    "abilities": ["Snow Warning", "Soundproof"], "learnset": ["Blizzard", "Wood Hammer"], "legal_in": ["M-B"],
}
_RECORDS = [_ABOMASNOW]


def test_usage_response_not_found_suggests_close_matches():
    response = usage_response(_RECORDS, "Abomasno")

    assert "not found" in response.lower() or "no pokemon" in response.lower()


def test_usage_response_reports_no_usage_data_when_none_exists():
    response = usage_response(_RECORDS, "Abomasnow", usage={})

    assert "no usage data" in response.lower()


def test_usage_response_shows_items_abilities_and_moves():
    usage = {"Abomasnow": {
        "items": [{"name": "Focus Sash", "usage_pct": 40.0}],
        "abilities": [{"name": "Snow Warning", "usage_pct": 98.5}],
        "moves": [{"name": "Blizzard", "usage_pct": 91.2}, {"name": "Wood Hammer", "usage_pct": 84.0}],
    }}

    response = usage_response(_RECORDS, "Abomasnow", usage=usage)

    assert "Focus Sash 40.0%" in response
    assert "Snow Warning 98.5%" in response
    assert "Blizzard 91.2%" in response
    assert "Wood Hammer 84.0%" in response


def test_usage_response_omits_empty_sections():
    usage = {"Abomasnow": {"items": [], "abilities": [{"name": "Snow Warning", "usage_pct": 98.5}], "moves": []}}

    response = usage_response(_RECORDS, "Abomasnow", usage=usage)

    assert "Items:" not in response
    assert "Abilities: Snow Warning 98.5%" in response
    assert "Moves:" not in response
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_bot_pokemon_info.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bot.commands.pokemon_info'`.

- [ ] **Step 3: Implement**

Create `bot/commands/pokemon_info.py`:

```python
from bot.pokemon_lookup import find_record, not_found_message, usage_for_record


def usage_response(records: list, name: str, usage: dict = None) -> str:
    record = find_record(records, name)
    if record is None:
        return not_found_message(records, name)

    species_usage = usage_for_record(usage, record)
    if not species_usage:
        return f"{record['name']} has no usage data yet."

    lines = [f"{record['name']}'s usage data:"]
    if species_usage.get("items"):
        items_text = ", ".join(f"{i['name']} {i['usage_pct']}%" for i in species_usage["items"])
        lines.append(f"Items: {items_text}")
    if species_usage.get("abilities"):
        abilities_text = ", ".join(f"{a['name']} {a['usage_pct']}%" for a in species_usage["abilities"])
        lines.append(f"Abilities: {abilities_text}")
    if species_usage.get("moves"):
        moves_text = ", ".join(f"{m['name']} {m['usage_pct']}%" for m in species_usage["moves"])
        lines.append(f"Moves: {moves_text}")
    return "\n".join(lines)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_bot_pokemon_info.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add bot/commands/pokemon_info.py tests/test_bot_pokemon_info.py
git commit -m "feat: add usage_response full-breakdown formatter"
```

---

### Task 2: `PokemonInfoView` and wiring into `/stats`/`/moves`

**Files:**
- Modify: `bot/commands/pokemon_info.py`
- Modify: `tests/test_bot_pokemon_info.py`
- Modify: `bot/main.py`
- Modify: `tests/test_bot_main.py`

**Interfaces:**
- Consumes: `stats_response` (`bot/commands/stats.py`), `moves_response` (`bot/commands/moves.py`), `usage_response` (Task 1) — all unchanged.
- Produces: `PokemonInfoView(records, usage, name, user_id, active_tab)`. `bot/main.py`'s `/stats`/`/moves` handlers (this task) construct it directly; no later task in this plan.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_bot_pokemon_info.py`:

```python
import asyncio
from unittest.mock import AsyncMock, MagicMock

from bot.commands.pokemon_info import PokemonInfoView


def test_pokemon_info_view_has_three_tabs_in_order():
    view = PokemonInfoView(_RECORDS, {}, "Abomasnow", user_id=1, active_tab="Stats")

    labels = [child.label for child in view.children]

    assert labels == ["Stats", "Moves", "Usage"]


def test_pokemon_info_view_styles_the_active_tab_as_primary():
    import discord

    view = PokemonInfoView(_RECORDS, {}, "Abomasnow", user_id=1, active_tab="Moves")

    styles = {child.label: child.style for child in view.children}

    assert styles["Moves"] == discord.ButtonStyle.primary
    assert styles["Stats"] == discord.ButtonStyle.secondary
    assert styles["Usage"] == discord.ButtonStyle.secondary


def test_pokemon_info_view_moves_tab_edits_in_the_moveset():
    view = PokemonInfoView(_RECORDS, {}, "Abomasnow", user_id=1, active_tab="Stats")
    moves_button = view.children[1]
    interaction = MagicMock()
    interaction.user.id = 1
    interaction.response.edit_message = AsyncMock()

    asyncio.run(moves_button.callback(interaction))

    _args, kwargs = interaction.response.edit_message.call_args
    assert "Blizzard" in kwargs["embed"].description
    assert isinstance(kwargs["view"], PokemonInfoView)
    assert kwargs["view"].active_tab == "Moves"


def test_pokemon_info_view_usage_tab_edits_in_the_usage_breakdown():
    usage = {"Abomasnow": {"items": [], "abilities": [], "moves": [{"name": "Blizzard", "usage_pct": 91.2}]}}
    view = PokemonInfoView(_RECORDS, usage, "Abomasnow", user_id=1, active_tab="Stats")
    usage_button = view.children[2]
    interaction = MagicMock()
    interaction.user.id = 1
    interaction.response.edit_message = AsyncMock()

    asyncio.run(usage_button.callback(interaction))

    _args, kwargs = interaction.response.edit_message.call_args
    assert "Blizzard 91.2%" in kwargs["embed"].description
    assert kwargs["view"].active_tab == "Usage"


def test_pokemon_info_view_interaction_check_rejects_a_different_user():
    view = PokemonInfoView(_RECORDS, {}, "Abomasnow", user_id=1, active_tab="Stats")
    interaction = MagicMock()
    interaction.user.id = 999
    interaction.response.send_message = AsyncMock()

    allowed = asyncio.run(view.interaction_check(interaction))

    assert allowed is False
    _args, kwargs = interaction.response.send_message.call_args
    assert kwargs["ephemeral"] is True
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_bot_pokemon_info.py -v -k PokemonInfoView`
Expected: FAIL with `ImportError: cannot import name 'PokemonInfoView' from 'bot.commands.pokemon_info'`.

- [ ] **Step 3: Implement**

Add to `bot/commands/pokemon_info.py` (after `usage_response`, add `import discord` as the file's first line, and import the two other response functions):

```python
import discord

from bot.commands.moves import moves_response
from bot.commands.stats import stats_response
from bot.pokemon_lookup import find_record, not_found_message, usage_for_record


def usage_response(records: list, name: str, usage: dict = None) -> str:
    ...  # unchanged from Task 1


_TABS = ("Stats", "Moves", "Usage")
_TAB_RESPONSE = {
    "Stats": lambda records, name, usage: stats_response(records, name, usage=usage),
    "Moves": lambda records, name, usage: moves_response(records, name, usage=usage),
    "Usage": usage_response,
}


def _panel_embed(description: str) -> discord.Embed:
    return discord.Embed(description=description, color=discord.Color.blue())


class PokemonInfoView(discord.ui.View):
    """Shared Stats/Moves/Usage tab panel for /stats and /moves -- both
    commands keep their own names and registration; whichever one is run
    opens this same panel so the user can pivot between tabs without
    retyping the species name."""

    def __init__(self, records: list, usage: dict, name: str, user_id: int, active_tab: str):
        super().__init__()
        self.records = records
        self.usage = usage
        self.name = name
        self.user_id = user_id
        self.active_tab = active_tab
        for tab in _TABS:
            style = discord.ButtonStyle.primary if tab == active_tab else discord.ButtonStyle.secondary
            button = discord.ui.Button(label=tab, style=style)
            button.callback = self._make_callback(tab)
            self.add_item(button)

    def _make_callback(self, tab: str):
        async def callback(interaction: discord.Interaction) -> None:
            response = _TAB_RESPONSE[tab](self.records, self.name, self.usage)
            await interaction.response.edit_message(
                embed=_panel_embed(response),
                view=PokemonInfoView(self.records, self.usage, self.name, self.user_id, tab),
            )

        return callback

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your info panel.", ephemeral=True)
            return False
        return True
```

(Leave `usage_response`'s body exactly as Task 1 wrote it — only the new imports and the classes/constants below it are added.)

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_bot_pokemon_info.py -v`
Expected: all PASS.

- [ ] **Step 5: Write the failing tests for `bot/main.py`**

Add to `tests/test_bot_main.py`:

```python
def test_stats_command_attaches_a_pokemon_info_view_starting_on_stats():
    from bot.commands.pokemon_info import PokemonInfoView

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

    asyncio.run(stats_cmd.callback(interaction, name="Abomasnow"))

    _args, kwargs = interaction.response.send_message.call_args
    assert isinstance(kwargs["view"], PokemonInfoView)
    assert kwargs["view"].active_tab == "Stats"


def test_moves_command_attaches_a_pokemon_info_view_starting_on_moves():
    from bot.commands.pokemon_info import PokemonInfoView

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

    asyncio.run(moves_cmd.callback(interaction, name="Abomasnow"))

    _args, kwargs = interaction.response.send_message.call_args
    assert isinstance(kwargs["view"], PokemonInfoView)
    assert kwargs["view"].active_tab == "Moves"
```

- [ ] **Step 6: Run the tests to verify they fail**

Run: `pytest tests/test_bot_main.py -v -k pokemon_info_view`
Expected: both FAIL — `send_message`'s `call_args` has no `view` kwarg yet.

- [ ] **Step 7: Implement the `bot/main.py` change**

Add this import alongside the other `bot.commands.*` imports:

```python
from bot.commands.pokemon_info import PokemonInfoView
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
        record = find_record(records, name)
        response = stats_response(records, name, usage=usage)
        if record is None:
            await interaction.response.send_message(embed=_embed("stats", response))
            return
        await interaction.response.send_message(
            embed=_embed("stats", response),
            view=PokemonInfoView(records, usage, record["name"], interaction.user.id, "Stats"),
        )
```

Change the `/moves` command from:

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
        record = find_record(records, name)
        response = moves_response(records, name, usage=usage)
        if record is None:
            await interaction.response.send_message(embed=_embed("moves", response))
            return
        await interaction.response.send_message(
            embed=_embed("moves", response),
            view=PokemonInfoView(records, usage, record["name"], interaction.user.id, "Moves"),
        )
```

If `bot/main.py` does not already import `find_record` (it won't, unless Slice A has already been implemented first), add:

```python
from bot.pokemon_lookup import find_record
```

alongside the other `bot.*` imports. If Slice A's `from bot.pokemon_lookup import find_record, not_found_message, suggest_names` is already present, extend that existing line instead of adding a duplicate import.

- [ ] **Step 8: Run the tests to verify they pass**

Run: `pytest tests/test_bot_main.py -v -k "stats_command or moves_command"`
Expected: all PASS, including every pre-existing `/stats`/`/moves` test.

- [ ] **Step 9: Run the entire test suite as a final check**

Run: `pytest -q`
Expected: all PASS.

- [ ] **Step 10: Commit**

```bash
git add bot/commands/pokemon_info.py tests/test_bot_pokemon_info.py bot/main.py tests/test_bot_main.py
git commit -m "feat: add Stats/Moves/Usage tabbed panel to /stats and /moves"
```

---

## Self-review notes

- **Spec coverage:** both commands keep their names/registration; shared tabbed panel with visually distinct active-tab styling; Usage tab backed by a new full-breakdown formatter since none existed; edit-in-place, invoker-only convention matching `/team`/Slice A — all covered.
- **Placeholder scan:** no TBD/TODO; the one `...  # unchanged from Task 1` ellipsis in Task 2 Step 3 is an explicit instruction not to touch that function body, immediately followed by the real code that comes after it in the same file — not a placeholder for anything left unwritten.
- **Type consistency checked:** `PokemonInfoView.__init__`'s five positional args (`records, usage, name, user_id, active_tab`) match both `bot/main.py` call sites (Task 2) and every test construction (Tasks 1-2). `_TAB_RESPONSE`'s three keys exactly match `_TABS`'s three values, so `_TAB_RESPONSE[tab]` in `_make_callback` can never `KeyError` for any tab this view itself creates.
- **Regression risk audited:** both handlers still call `stats_response`/`moves_response` exactly once with identical arguments to before; the only behavior change on a successful lookup is the added `view=` kwarg, confirmed against every pre-existing `/stats`/`/moves` test staying unmodified.
