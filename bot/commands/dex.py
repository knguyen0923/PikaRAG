import discord

from bot.commands.stats import stats_response


def dex_page_response(records: list, index: int) -> str:
    record = records[index]
    return f"({index + 1}/{len(records)}) {stats_response(records, record['name'])}"


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
