import json
import os
from pathlib import Path

import discord
from discord import app_commands

from bot.commands.ask import ask_response
from bot.commands.ping import ping_response
from rag.answer import HaikuAnswerer
from rag.embed import SentenceTransformerEmbedder
from rag.store import ChromaIndex

PROCESSED_RECORDS_PATH = Path("data/processed/pokemon_records.json")


def build_client(index=None, answerer=None) -> tuple[discord.Client, app_commands.CommandTree]:
    intents = discord.Intents.default()
    client = discord.Client(intents=intents)
    tree = app_commands.CommandTree(client)

    @tree.command(name="ping", description="Check that the bot is responsive.")
    async def ping(interaction: discord.Interaction) -> None:
        await interaction.response.send_message(ping_response())

    @tree.command(name="ask", description="Ask a question about VGC Pokemon stats and movesets.")
    async def ask(interaction: discord.Interaction, question: str) -> None:
        await interaction.response.send_message(ask_response(index, answerer, question))

    @client.event
    async def on_ready() -> None:
        await tree.sync()

    return client, tree


def _build_real_index() -> ChromaIndex:
    records = json.loads(PROCESSED_RECORDS_PATH.read_text())
    index = ChromaIndex(embedder=SentenceTransformerEmbedder())
    index.build(records)
    return index


def main() -> None:
    token = os.environ["DISCORD_TOKEN"]
    client, _tree = build_client(index=_build_real_index(), answerer=HaikuAnswerer())
    client.run(token)


if __name__ == "__main__":
    main()
