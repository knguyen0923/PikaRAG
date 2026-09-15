import discord


class _SelectWithSettableValues(discord.ui.Select):
    """Helper select that allows setting values for testing."""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._test_values = None

    @property
    def values(self):
        if self._test_values is not None:
            return self._test_values
        return self._values

    @values.setter
    def values(self, val):
        self._test_values = val


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
        select = _SelectWithSettableValues(placeholder="Did you mean...", options=options)
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
