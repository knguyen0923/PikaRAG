import os

import discord
from discord import app_commands

from bot.commands.ping import ping_response


def build_client() -> tuple[discord.Client, app_commands.CommandTree]:
    intents = discord.Intents.default()
    client = discord.Client(intents=intents)
    tree = app_commands.CommandTree(client)

    @tree.command(name="ping", description="Check that the bot is responsive.")
    async def ping(interaction: discord.Interaction) -> None:
        await interaction.response.send_message(ping_response())

    @client.event
    async def on_ready() -> None:
        await tree.sync()

    return client, tree


def main() -> None:
    token = os.environ["DISCORD_TOKEN"]
    client, _tree = build_client()
    client.run(token)


if __name__ == "__main__":
    main()
