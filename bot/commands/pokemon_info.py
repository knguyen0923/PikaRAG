import discord

from bot.commands.moves import moves_response
from bot.commands.stats import stats_response
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
