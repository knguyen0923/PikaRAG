import json
import os
from pathlib import Path

import discord
from discord import app_commands

from bot.commands.ask import ask_response_async
from bot.commands.moves import moves_response
from bot.commands.ping import ping_response
from bot.commands.stats import stats_response
from rag.answer import HaikuAnswerer
from rag.embed import SentenceTransformerEmbedder
from rag.store import ChromaIndex

PROCESSED_RECORDS_PATH = Path("data/processed/pokemon_records.json")


def build_client(
    index=None, answerer=None, records=None
) -> tuple[discord.Client, app_commands.CommandTree]:
    intents = discord.Intents.default()
    client = discord.Client(intents=intents)
    tree = app_commands.CommandTree(client)

    @tree.command(name="ping", description="Check that the bot is responsive.")
    async def ping(interaction: discord.Interaction) -> None:
        await interaction.response.send_message(ping_response())

    @tree.command(name="ask", description="Ask a question about VGC Pokemon stats and movesets.")
    async def ask(interaction: discord.Interaction, question: str) -> None:
        await interaction.response.send_message(await ask_response_async(index, answerer, question))

    @tree.command(name="stats", description="Look up a Pokemon's base stats, types, and abilities.")
    async def stats(interaction: discord.Interaction, name: str) -> None:
        await interaction.response.send_message(stats_response(records, name))

    @tree.command(name="moves", description="Look up a Pokemon's legal moveset.")
    async def moves(interaction: discord.Interaction, name: str) -> None:
        await interaction.response.send_message(moves_response(records, name))

    @client.event
    async def on_ready() -> None:
        await tree.sync()

    return client, tree


def _load_records() -> list:
    return json.loads(PROCESSED_RECORDS_PATH.read_text())


def _build_real_index(records: list) -> ChromaIndex:
    # Fixed collection name: build() upserts, so restarting the bot refreshes
    # this same persisted collection in place instead of leaking a new one.
    index = ChromaIndex(embedder=SentenceTransformerEmbedder(), collection_name="pokemon")
    index.build(records)
    return index


def main() -> None:
    token = os.environ["DISCORD_TOKEN"]
    records = _load_records()
    client, _tree = build_client(
        index=_build_real_index(records), answerer=HaikuAnswerer(), records=records
    )
    client.run(token)


if __name__ == "__main__":
    main()
