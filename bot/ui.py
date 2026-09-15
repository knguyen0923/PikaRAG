import discord


class NameSuggestionView(discord.ui.View):
    """Shared 'did you mean...?' dropdown, offered wherever a name lookup
    misses but bot.pokemon_lookup.suggest_names has close matches. on_select
    is an async (interaction, chosen_name) -> None callback the call site
    supplies -- this view has no opinion on what happens after a pick,
    since that differs per command (re-run /stats, retry /calc with one
    field corrected, etc.)."""

    def __init__(self, user_id: int, suggestions: list, on_select):
        if not suggestions:
            raise ValueError("NameSuggestionView requires at least one suggestion, got an empty list.")
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

    async def on_error(self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item) -> None:
        # discord.ui.View's default on_error only logs a traceback and lets
        # Discord show its own generic failure message -- every other error
        # path in this bot (see on_tree_error in bot/main.py) instead shows a
        # friendly red embed. Mirror that same fallback message/style here so
        # a raise from on_select (e.g. a /calc replay) behaves consistently.
        print(f"Unhandled error in NameSuggestionView: {error!r}")
        embed = discord.Embed(
            description="Something went wrong running that command. Please try again.",
            color=discord.Color.red(),
        )
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)
