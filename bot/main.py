import asyncio
import json
import os
from pathlib import Path
from typing import Literal, Optional

import discord
from discord import app_commands

from bot.commands.ask import ask_response_async
from bot.commands.calc import calc_response
from bot.commands.moves import moves_response
from bot.commands.ping import ping_response
from bot.commands.stats import stats_response
from bot.commands.team import (
    format_team_block,
    import_team_response,
    scout_response,
    view_team_response,
)
from bot.pokepaste_fetch import PokepasteFetchError, resolve_pokepaste_text
from bot.team_store import find_team_member, get_team, resolve_calc_overrides
from rag.answer import HaikuAnswerer
from rag.embed import SentenceTransformerEmbedder
from rag.store import ChromaIndex

PROCESSED_RECORDS_PATH = Path("data/processed/pokemon_records.json")
VGC_MOVES_PATH = Path("data/source/vgc_moves.json")
USAGE_DATA_PATH = Path("data/processed/pikalytics_usage.json")
_COOLDOWN_SECONDS = 3.0

_COMMAND_COLORS = {
    "ping": discord.Color.light_grey(),
    "ask": discord.Color.purple(),
    "stats": discord.Color.blue(),
    "moves": discord.Color.teal(),
    "calc": discord.Color.red(),
    "import": discord.Color.green(),
    "scout": discord.Color.gold(),
    "team": discord.Color.blurple(),
}


def _embed(command_name: str, description: str) -> discord.Embed:
    return discord.Embed(description=description, color=_COMMAND_COLORS[command_name])


def build_client(
    index=None, answerer=None, records=None, moves=None, usage=None
) -> tuple[discord.Client, app_commands.CommandTree]:
    intents = discord.Intents.default()
    client = discord.Client(intents=intents)
    tree = app_commands.CommandTree(client)

    @tree.command(name="ping", description="Check that the bot is responsive.")
    @app_commands.checks.cooldown(1, _COOLDOWN_SECONDS)
    async def ping(interaction: discord.Interaction) -> None:
        await interaction.response.send_message(embed=_embed("ping", ping_response()))

    @tree.command(name="ask", description="Ask a question about VGC Pokemon stats and movesets.")
    @app_commands.checks.cooldown(1, _COOLDOWN_SECONDS)
    async def ask(interaction: discord.Interaction, question: str) -> None:
        user_id = interaction.user.id
        team_blocks = [
            format_team_block(get_team(user_id, "mine"), "Your team"),
            format_team_block(get_team(user_id, "opponent"), "Opponent's team"),
        ]
        extra_context = "\n\n".join(block for block in team_blocks if block) or None
        answer = await ask_response_async(index, answerer, question, extra_context=extra_context)
        await interaction.response.send_message(embed=_embed("ask", answer))

    @tree.command(name="stats", description="Look up a Pokemon's base stats, types, and abilities.")
    @app_commands.checks.cooldown(1, _COOLDOWN_SECONDS)
    async def stats(interaction: discord.Interaction, name: str) -> None:
        await interaction.response.send_message(embed=_embed("stats", stats_response(records, name, usage=usage)))

    @tree.command(name="moves", description="Look up a Pokemon's legal moveset.")
    @app_commands.checks.cooldown(1, _COOLDOWN_SECONDS)
    async def moves_command(interaction: discord.Interaction, name: str) -> None:
        await interaction.response.send_message(embed=_embed("moves", moves_response(records, name, usage=usage)))

    @tree.command(name="import", description="Import a full Pokemon team from Pokepaste text or a pokepast.es URL.")
    @app_commands.checks.cooldown(1, _COOLDOWN_SECONDS)
    async def import_team(
        interaction: discord.Interaction,
        side: Literal["mine", "opponent"],
        pokepaste: str,
    ) -> None:
        await interaction.response.defer()
        try:
            raw_text = await asyncio.to_thread(resolve_pokepaste_text, pokepaste)
        except PokepasteFetchError as e:
            await interaction.followup.send(embed=_embed("import", str(e)))
            return
        response = import_team_response(records, moves, interaction.user.id, side, raw_text)
        await interaction.followup.send(embed=_embed("import", response))

    @tree.command(name="scout", description="Add or update one Pokemon in a stored team with only what you currently know.")
    @app_commands.checks.cooldown(1, _COOLDOWN_SECONDS)
    async def scout(
        interaction: discord.Interaction,
        species: str,
        item: Optional[str] = None,
        ability: Optional[str] = None,
        tera_type: Optional[str] = None,
        move1: Optional[str] = None,
        move2: Optional[str] = None,
        move3: Optional[str] = None,
        move4: Optional[str] = None,
        side: Literal["mine", "opponent"] = "opponent",
    ) -> None:
        response = scout_response(
            records, moves, interaction.user.id, species,
            item=item, ability=ability, tera_type=tera_type,
            move1=move1, move2=move2, move3=move3, move4=move4,
            side=side,
        )
        await interaction.response.send_message(embed=_embed("scout", response))

    @tree.command(name="team", description="View the Pokemon currently stored for your team or the opponent's team.")
    @app_commands.checks.cooldown(1, _COOLDOWN_SECONDS)
    async def team(interaction: discord.Interaction, side: Literal["mine", "opponent"]) -> None:
        await interaction.response.send_message(embed=_embed("team", view_team_response(interaction.user.id, side)))

    @tree.command(name="calc", description="Calculate a damage range for attacker's move vs defender.")
    @app_commands.checks.cooldown(1, _COOLDOWN_SECONDS)
    async def calc(
        interaction: discord.Interaction,
        attacker: str,
        defender: str,
        move: str,
        attacker_evs: Optional[str] = None,
        attacker_nature: Optional[str] = None,
        attacker_item: Optional[str] = None,
        attacker_tera: Optional[str] = None,
        defender_evs: Optional[str] = None,
        defender_nature: Optional[str] = None,
        defender_item: Optional[str] = None,
        defender_tera: Optional[str] = None,
        defender_hp_percent: int = 100,
        weather: Optional[str] = None,
        terrain: Optional[str] = None,
        screen: Optional[str] = None,
        spread: bool = False,
    ) -> None:
        user_id = interaction.user.id
        resolved_attacker_evs, resolved_attacker_nature, resolved_attacker_item, resolved_attacker_tera = (
            resolve_calc_overrides(user_id, attacker, attacker_evs, attacker_nature, attacker_item, attacker_tera)
        )
        resolved_defender_evs, resolved_defender_nature, resolved_defender_item, resolved_defender_tera = (
            resolve_calc_overrides(user_id, defender, defender_evs, defender_nature, defender_item, defender_tera)
        )
        response = calc_response(
            records,
            moves,
            attacker,
            defender,
            move,
            attacker_evs=resolved_attacker_evs,
            attacker_nature=resolved_attacker_nature,
            attacker_item=resolved_attacker_item,
            attacker_tera=resolved_attacker_tera,
            defender_evs=resolved_defender_evs,
            defender_nature=resolved_defender_nature,
            defender_item=resolved_defender_item,
            defender_tera=resolved_defender_tera,
            defender_hp_percent=defender_hp_percent,
            weather=weather,
            terrain=terrain,
            screen=screen,
            spread=spread,
        )
        # Only note stored-team usage on a successful calc -- not on a "not
        # found"/"invalid EVs" error, where the note would be misleading.
        if not response.startswith(("No ", "Invalid ")):
            stored_names = [name for name in (attacker, defender) if find_team_member(user_id, name)]
            if stored_names:
                response += f" (using stored data for: {', '.join(stored_names)})"
        await interaction.response.send_message(embed=_embed("calc", response))

    @client.event
    async def on_ready() -> None:
        await tree.sync()

    @tree.error
    async def on_tree_error(interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
        command_name = interaction.command.name if interaction.command else "?"
        if isinstance(error, app_commands.CommandOnCooldown):
            message = f"Slow down! Please wait {error.retry_after:.1f}s before using that again."
            color = discord.Color.orange()
        else:
            print(f"Unhandled error in /{command_name}: {error!r}")
            message = "Something went wrong running that command. Please try again."
            color = discord.Color.red()
        embed = discord.Embed(description=message, color=color)
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed)
        else:
            await interaction.response.send_message(embed=embed)

    return client, tree


def _load_records() -> list:
    return json.loads(PROCESSED_RECORDS_PATH.read_text())


def _load_moves() -> list:
    return json.loads(VGC_MOVES_PATH.read_text())["moves"]


def _load_usage() -> dict:
    if not USAGE_DATA_PATH.exists():
        return {}
    return json.loads(USAGE_DATA_PATH.read_text())


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
        usage=_load_usage(),
    )
    client.run(token)


if __name__ == "__main__":
    main()
