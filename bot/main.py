import json
import os
from pathlib import Path
from typing import Optional

import discord
from discord import app_commands

from bot.commands.ask import ask_response_async
from bot.commands.calc import calc_response
from bot.commands.moves import moves_response
from bot.commands.ping import ping_response
from bot.commands.stats import stats_response
from rag.answer import HaikuAnswerer
from rag.embed import SentenceTransformerEmbedder
from rag.store import ChromaIndex

PROCESSED_RECORDS_PATH = Path("data/processed/pokemon_records.json")
VGC_MOVES_PATH = Path("data/source/vgc_moves.json")


def build_client(
    index=None, answerer=None, records=None, moves=None
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

    @tree.command(name="calc", description="Calculate a damage range for attacker's move vs defender.")
    async def calc(
        interaction: discord.Interaction,
        attacker: str,
        defender: str,
        move: str,
        attacker_evs: str = "0/0/0/0/0/0",
        attacker_nature: str = "Hardy",
        attacker_item: Optional[str] = None,
        attacker_tera: Optional[str] = None,
        defender_evs: str = "0/0/0/0/0/0",
        defender_nature: str = "Hardy",
        defender_item: Optional[str] = None,
        defender_tera: Optional[str] = None,
        defender_hp_percent: int = 100,
        weather: Optional[str] = None,
        terrain: Optional[str] = None,
        screen: Optional[str] = None,
        spread: bool = False,
    ) -> None:
        response = calc_response(
            records,
            moves,
            attacker,
            defender,
            move,
            attacker_evs=attacker_evs,
            attacker_nature=attacker_nature,
            attacker_item=attacker_item,
            attacker_tera=attacker_tera,
            defender_evs=defender_evs,
            defender_nature=defender_nature,
            defender_item=defender_item,
            defender_tera=defender_tera,
            defender_hp_percent=defender_hp_percent,
            weather=weather,
            terrain=terrain,
            screen=screen,
            spread=spread,
        )
        await interaction.response.send_message(response)

    @client.event
    async def on_ready() -> None:
        await tree.sync()

    return client, tree


def _load_records() -> list:
    return json.loads(PROCESSED_RECORDS_PATH.read_text())


def _load_moves() -> list:
    return json.loads(VGC_MOVES_PATH.read_text())["moves"]


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
        index=_build_real_index(records),
        answerer=HaikuAnswerer(),
        records=records,
        moves=_load_moves(),
    )
    client.run(token)


if __name__ == "__main__":
    main()
