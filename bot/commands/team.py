import discord

from bot.pokemon_lookup import find_record, format_with_suggestions, suggest_names
from bot.pokepaste import parse_pokepaste, PokepasteParseError
from bot.team_store import get_team, merge_scout, store_team
from damage_calc.data.natures import get_nature_modifiers
from damage_calc.data.type_chart import ALL_TYPES

_SIDE_LABELS = {"mine": "Your team", "opponent": "Opponent's team"}
_POSSESSIVE_LABELS = {"mine": "your", "opponent": "the opponent's"}


def format_team_block(team: list, label: str) -> str:
    if not team:
        return ""
    lines = [f"{label}:"]
    for member in team:
        item = f" @ {member['item']}" if member["item"] else ""
        ability = f" ({member['ability']})" if member["ability"] else ""
        tera = f" -- Tera {member['tera_type']}" if member["tera_type"] else ""
        moves = ", ".join(member["moves"]) if member["moves"] else "no known moves"
        lines.append(f"- {member['species']}{item}{ability}{tera} -- {member['nature']} -- {moves}")
    return "\n".join(lines)


def view_team_response(user_id: int, side: str) -> str:
    team = get_team(user_id, side)
    if not team:
        return f"No team loaded for '{side}'. Use /import or /scout to load one."
    return format_team_block(team, _SIDE_LABELS[side])


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


def _validate_member(records: list, moves: list, items: list, member: dict) -> list:
    warnings = []
    if find_record(records, member["species"]) is None:
        suggestions = suggest_names(records, member["species"])
        warnings.append(format_with_suggestions(f"'{member['species']}' not recognized.", suggestions))
    if items and member["item"] is not None:
        item_record = find_record(items, member["item"])
        if item_record is None:
            suggestions = suggest_names(items, member["item"])
            warnings.append(format_with_suggestions(f"Item '{member['item']}' not recognized.", suggestions))
        else:
            member["item"] = item_record["name"]
    for move_name in member["moves"]:
        if find_record(moves, move_name) is None:
            suggestions = suggest_names(moves, move_name)
            warnings.append(format_with_suggestions(f"Move '{move_name}' not recognized.", suggestions))
    if member["nature"] is not None:
        try:
            get_nature_modifiers(member["nature"])
        except KeyError:
            warnings.append(f"Nature '{member['nature']}' not recognized -- using Hardy instead.")
            member["nature"] = "Hardy"
    if member["tera_type"] is not None and member["tera_type"] not in ALL_TYPES:
        warnings.append(f"Tera type '{member['tera_type']}' not recognized -- ignoring it.")
        member["tera_type"] = None
    return warnings


def _format_warnings(warnings: list) -> list:
    if not warnings:
        return []
    return ["", "Warnings:"] + [f"- {w}" for w in warnings]


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


_EMPTY_EVS = {"hp": 0, "attack": 0, "defense": 0, "sp_attack": 0, "sp_defense": 0, "speed": 0}
_MAX_IVS = {"hp": 31, "attack": 31, "defense": 31, "sp_attack": 31, "sp_defense": 31, "speed": 31}


def scout_response(
    records: list,
    moves: list,
    user_id: int,
    species: str,
    item=None,
    ability=None,
    tera_type=None,
    move1=None,
    move2=None,
    move3=None,
    move4=None,
    side: str = "opponent",
    items: list = None,
) -> str:
    member = {
        "species": species, "nickname": None, "gender": None,
        "item": item, "ability": ability, "level": 50, "tera_type": tera_type,
        "evs": dict(_EMPTY_EVS), "ivs": dict(_MAX_IVS), "nature": "Hardy",
        "moves": [m for m in (move1, move2, move3, move4) if m],
    }
    warnings = _validate_member(records, moves, items, member)

    try:
        stored = merge_scout(user_id, side, member)
    except ValueError as e:
        return str(e)

    moves_text = ", ".join(stored["moves"]) if stored["moves"] else "no known moves"
    lines = [f"Updated {stored['species']} in {_POSSESSIVE_LABELS[side]} team -- known moves: {moves_text}."]
    lines.extend(_format_warnings(warnings))
    return "\n".join(lines)


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
