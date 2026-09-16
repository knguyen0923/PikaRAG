import asyncio
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional

import discord
from discord import app_commands

from bot.commands.ask import GATE_MESSAGE, ask_response_async, format_ask_response
from bot.commands.calc import calc_response, is_error_response
from bot.commands.debug import format_debug_last
from bot.commands.dex import DexBrowseView, dex_page_response
from bot.commands.llmstatus import format_llmstatus
from bot.commands.moves import moves_response
from bot.commands.ping import ping_response
from bot.commands.pokemon_info import PokemonInfoView
from bot.commands.stats import stats_response
from bot.commands.team import (
    ImportConfirmView,
    TeamView,
    ViewTeamButtonView,
    finalize_import,
    format_team_block,
    prepare_import,
    scout_response,
    view_team_response,
)
from bot.pokemon_lookup import find_record, not_found_message, suggest_names
from bot.pokepaste_fetch import PokepasteFetchError, resolve_pokepaste_text
from bot.team_store import find_team_member, get_team, resolve_calc_overrides
from bot.ui import NameSuggestionView
from rag.answer import OFFLINE_MESSAGE, OllamaAnswerer
from rag.circuit_breaker import CircuitBreaker
from rag.embed import SentenceTransformerEmbedder
from rag.observability import get_last_ask_log, log_ask
from rag.store import ChromaIndex

PROCESSED_RECORDS_PATH = Path("data/processed/pokemon_records.json")
VGC_MOVES_PATH = Path("data/source/vgc_moves.json")
VGC_ITEMS_PATH = Path("data/source/vgc_items.json")
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
    "dex": discord.Color.magenta(),
    "debug": discord.Color.dark_grey(),
    "llmstatus": discord.Color.orange(),
}


def _embed(command_name: str, description: str) -> discord.Embed:
    return discord.Embed(description=description, color=_COMMAND_COLORS[command_name])


def _owner_only(interaction: discord.Interaction) -> bool:
    owner_id = os.environ.get("BOT_OWNER_ID")
    if owner_id is None:
        return False
    try:
        return interaction.user.id == int(owner_id)
    except (TypeError, ValueError):
        return False


def build_client(
    index=None, answerer=None, raw_answerer=None, records=None, moves=None, usage=None, items=None
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
        await interaction.response.defer()
        user_id = interaction.user.id
        team_blocks = [
            format_team_block(get_team(user_id, "mine"), "Your team"),
            format_team_block(get_team(user_id, "opponent"), "Opponent's team"),
        ]
        extra_context = "\n\n".join(block for block in team_blocks if block) or None
        start_time = time.monotonic()
        result = await ask_response_async(
            index, answerer, question, records=records, items=items, extra_context=extra_context
        )
        latency_ms = int((time.monotonic() - start_time) * 1000)
        try:
            log_ask(
                timestamp=datetime.now(timezone.utc).isoformat(),
                question=question,
                retrieved_chunks=result["retrieved_chunks"],
                sources=result["sources"],
                best_distance=result["best_distance"],
                gate_fired=result["answer"] == GATE_MESSAGE,
                answer=result["answer"],
                degraded=result["answer"] == OFFLINE_MESSAGE,
                latency_ms=latency_ms,
            )
        except Exception:
            pass  # observability is best-effort; never blocks the answer
        await interaction.followup.send(embed=_embed("ask", format_ask_response(result)))

    @tree.command(name="debug-last", description="Show the most recent /ask call's full detail (bot owner only).")
    @app_commands.check(_owner_only)
    async def debug_last(interaction: discord.Interaction) -> None:
        row = get_last_ask_log()
        await interaction.response.send_message(embed=_embed("debug", format_debug_last(row)), ephemeral=True)

    @tree.command(name="llmstatus", description="Check the local LLM's health and circuit breaker state (bot owner only).")
    @app_commands.checks.cooldown(1, _COOLDOWN_SECONDS)
    @app_commands.check(_owner_only)
    async def llmstatus(interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        health = await asyncio.to_thread(raw_answerer.check_health)
        formatted = format_llmstatus(
            up=health["up"],
            models=health["models"],
            configured_model=raw_answerer.model,
            breaker_state=answerer.state,
        )
        await interaction.followup.send(embed=_embed("llmstatus", formatted), ephemeral=True)

    @tree.command(name="stats", description="Look up a Pokemon's base stats, types, and abilities.")
    @app_commands.checks.cooldown(1, _COOLDOWN_SECONDS)
    async def stats(interaction: discord.Interaction, name: str) -> None:
        record = find_record(records, name)
        if record is None:
            suggestions = suggest_names(records, name)
            if suggestions:
                async def _on_select(inner_interaction: discord.Interaction, chosen: str) -> None:
                    await inner_interaction.response.edit_message(
                        embed=_embed("stats", stats_response(records, chosen, usage=usage)),
                        view=PokemonInfoView(records, usage, chosen, inner_interaction.user.id, "Stats"),
                    )

                await interaction.response.send_message(
                    embed=_embed("stats", not_found_message(records, name)),
                    view=NameSuggestionView(interaction.user.id, suggestions, _on_select),
                )
                return
        await interaction.response.send_message(
            embed=_embed("stats", stats_response(records, name, usage=usage)),
            view=PokemonInfoView(records, usage, record["name"], interaction.user.id, "Stats"),
        )

    @tree.command(name="moves", description="Look up a Pokemon's legal moveset.")
    @app_commands.checks.cooldown(1, _COOLDOWN_SECONDS)
    async def moves_command(interaction: discord.Interaction, name: str) -> None:
        record = find_record(records, name)
        if record is None:
            suggestions = suggest_names(records, name)
            if suggestions:
                async def _on_select(inner_interaction: discord.Interaction, chosen: str) -> None:
                    await inner_interaction.response.edit_message(
                        embed=_embed("moves", moves_response(records, chosen, usage=usage)),
                        view=PokemonInfoView(records, usage, chosen, inner_interaction.user.id, "Moves"),
                    )

                await interaction.response.send_message(
                    embed=_embed("moves", not_found_message(records, name)),
                    view=NameSuggestionView(interaction.user.id, suggestions, _on_select),
                )
                return
        await interaction.response.send_message(
            embed=_embed("moves", moves_response(records, name, usage=usage)),
            view=PokemonInfoView(records, usage, record["name"], interaction.user.id, "Moves"),
        )

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

        prepared = prepare_import(records, moves, side, raw_text, items=items)
        if not prepared["ok"]:
            await interaction.followup.send(embed=_embed("import", prepared["message"]))
            return

        user_id = interaction.user.id
        members, warnings = prepared["members"], prepared["warnings"]

        async def _finalize_and_send(target_interaction: discord.Interaction, as_followup: bool) -> None:
            result = finalize_import(user_id, side, members, warnings)
            view = ViewTeamButtonView(user_id, side) if result["ok"] else None
            embed = _embed("import", result["message"])
            if as_followup:
                # discord.py's Webhook.send (unlike edit_message) treats
                # view=None the same as an invalid view object and raises
                # TypeError -- omit the kwarg entirely instead of passing
                # None through (the same class of bug caught and fixed in
                # Slice A's /calc: interaction.response.send_message has an
                # identical `view is not MISSING` check that crashes on
                # view=None; followup.send has its own copy of that check).
                if view is None:
                    await target_interaction.followup.send(embed=embed)
                else:
                    await target_interaction.followup.send(embed=embed, view=view)
            else:
                # edit_message is None-safe (uses truthiness, not `is not
                # MISSING`), so view=None here correctly clears any existing
                # view -- no special-casing needed on this branch.
                await target_interaction.response.edit_message(embed=embed, view=view)

        if get_team(user_id, side):
            async def _on_confirm(confirm_interaction: discord.Interaction) -> None:
                await _finalize_and_send(confirm_interaction, as_followup=False)

            async def _on_cancel(cancel_interaction: discord.Interaction) -> None:
                await cancel_interaction.response.edit_message(
                    embed=_embed("import", f"Import cancelled -- your stored '{side}' team is unchanged."),
                    view=None,
                )

            await interaction.followup.send(
                embed=_embed(
                    "import", f"You already have a team stored for '{side}'. Replace it with this import?"
                ),
                view=ImportConfirmView(user_id, _on_confirm, _on_cancel),
            )
            return

        await _finalize_and_send(interaction, as_followup=True)

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
            side=side, items=items,
        )
        await interaction.response.send_message(embed=_embed("scout", response))

    @tree.command(name="team", description="View the Pokemon currently stored for your team or the opponent's team.")
    @app_commands.checks.cooldown(1, _COOLDOWN_SECONDS)
    async def team(interaction: discord.Interaction) -> None:
        await interaction.response.send_message(
            embed=_embed("team", view_team_response(interaction.user.id, "mine")),
            view=TeamView(interaction.user.id, "mine"),
        )

    @tree.command(name="dex", description="Browse the current regulation's legal Pokemon roster, Pokedex-style.")
    @app_commands.checks.cooldown(1, _COOLDOWN_SECONDS)
    async def dex(interaction: discord.Interaction, start: Optional[str] = None) -> None:
        index = 0
        if start is not None:
            record = find_record(records, start)
            if record is None:
                suggestions = suggest_names(records, start)
                message = not_found_message(records, start)
                if not suggestions:
                    await interaction.response.send_message(embed=_embed("dex", message))
                    return

                async def _on_select(inner_interaction: discord.Interaction, chosen: str) -> None:
                    chosen_index = records.index(find_record(records, chosen))
                    await inner_interaction.response.edit_message(
                        embed=_embed("dex", dex_page_response(records, chosen_index)),
                        view=DexBrowseView(records, chosen_index, inner_interaction.user.id),
                    )

                await interaction.response.send_message(
                    embed=_embed("dex", message),
                    view=NameSuggestionView(interaction.user.id, suggestions, _on_select),
                )
                return
            index = records.index(record)

        await interaction.response.send_message(
            embed=_embed("dex", dex_page_response(records, index)),
            view=DexBrowseView(records, index, interaction.user.id),
        )

    async def _calc_send(interaction: discord.Interaction, send_new_message: bool, embed, view=None) -> None:
        if send_new_message:
            if view is None:
                await interaction.response.send_message(embed=embed)
            else:
                await interaction.response.send_message(embed=embed, view=view)
        else:
            await interaction.response.edit_message(embed=embed, view=view)

    async def _run_calc(interaction: discord.Interaction, send_new_message: bool, **fields) -> None:
        """fields holds /calc's parameters exactly as originally typed:
        attacker, defender, move, attacker_evs, attacker_nature,
        attacker_item, attacker_ability, attacker_tera, defender_evs,
        defender_nature, defender_item, defender_ability, defender_tera,
        defender_hp_percent, weather, terrain, screen, spread. A suggestion
        pick re-invokes this with exactly one field replaced and every
        other one untouched."""
        attacker, defender, move = fields["attacker"], fields["defender"], fields["move"]

        if find_record(records, attacker) is None:
            suggestions = suggest_names(records, attacker)
            message = not_found_message(records, attacker)
            if not suggestions:
                await _calc_send(interaction, send_new_message, _embed("calc", message))
                return

            async def _on_select(inner_interaction: discord.Interaction, chosen: str) -> None:
                await _run_calc(inner_interaction, False, **{**fields, "attacker": chosen})

            await _calc_send(
                interaction, send_new_message, _embed("calc", message),
                NameSuggestionView(interaction.user.id, suggestions, _on_select),
            )
            return

        if find_record(records, defender) is None:
            suggestions = suggest_names(records, defender)
            message = not_found_message(records, defender)
            if not suggestions:
                await _calc_send(interaction, send_new_message, _embed("calc", message))
                return

            async def _on_select(inner_interaction: discord.Interaction, chosen: str) -> None:
                await _run_calc(inner_interaction, False, **{**fields, "defender": chosen})

            await _calc_send(
                interaction, send_new_message, _embed("calc", message),
                NameSuggestionView(interaction.user.id, suggestions, _on_select),
            )
            return

        if find_record(moves, move) is None:
            suggestions = suggest_names(moves, move)
            message = not_found_message(moves, move, kind="move")
            if not suggestions:
                await _calc_send(interaction, send_new_message, _embed("calc", message))
                return

            async def _on_select(inner_interaction: discord.Interaction, chosen: str) -> None:
                await _run_calc(inner_interaction, False, **{**fields, "move": chosen})

            await _calc_send(
                interaction, send_new_message, _embed("calc", message),
                NameSuggestionView(interaction.user.id, suggestions, _on_select),
            )
            return

        user_id = interaction.user.id
        (
            resolved_attacker_evs, resolved_attacker_nature,
            resolved_attacker_item, resolved_attacker_tera, resolved_attacker_ability,
        ) = resolve_calc_overrides(
            user_id, attacker, fields["attacker_evs"], fields["attacker_nature"],
            fields["attacker_item"], fields["attacker_tera"], fields["attacker_ability"],
        )
        (
            resolved_defender_evs, resolved_defender_nature,
            resolved_defender_item, resolved_defender_tera, resolved_defender_ability,
        ) = resolve_calc_overrides(
            user_id, defender, fields["defender_evs"], fields["defender_nature"],
            fields["defender_item"], fields["defender_tera"], fields["defender_ability"],
        )

        if items:
            if resolved_attacker_item and find_record(items, resolved_attacker_item) is None:
                suggestions = suggest_names(items, resolved_attacker_item)
                if suggestions:
                    async def _on_select(inner_interaction: discord.Interaction, chosen: str) -> None:
                        await _run_calc(inner_interaction, False, **{**fields, "attacker_item": chosen})

                    await _calc_send(
                        interaction, send_new_message,
                        _embed("calc", not_found_message(items, resolved_attacker_item, kind="item")),
                        NameSuggestionView(interaction.user.id, suggestions, _on_select),
                    )
                    return
            if resolved_defender_item and find_record(items, resolved_defender_item) is None:
                suggestions = suggest_names(items, resolved_defender_item)
                if suggestions:
                    async def _on_select(inner_interaction: discord.Interaction, chosen: str) -> None:
                        await _run_calc(inner_interaction, False, **{**fields, "defender_item": chosen})

                    await _calc_send(
                        interaction, send_new_message,
                        _embed("calc", not_found_message(items, resolved_defender_item, kind="item")),
                        NameSuggestionView(interaction.user.id, suggestions, _on_select),
                    )
                    return

        response = calc_response(
            records, moves, attacker, defender, move, items=items,
            attacker_evs=resolved_attacker_evs, attacker_nature=resolved_attacker_nature,
            attacker_item=resolved_attacker_item, attacker_ability=resolved_attacker_ability,
            attacker_tera=resolved_attacker_tera,
            defender_evs=resolved_defender_evs, defender_nature=resolved_defender_nature,
            defender_item=resolved_defender_item, defender_ability=resolved_defender_ability,
            defender_tera=resolved_defender_tera,
            defender_hp_percent=fields["defender_hp_percent"], weather=fields["weather"],
            terrain=fields["terrain"], screen=fields["screen"], spread=fields["spread"],
        )
        # Only note stored-team usage on a successful calc -- not on an
        # error, where the note would be misleading.
        if not is_error_response(response):
            stored_names = [name for name in (attacker, defender) if find_team_member(user_id, name)]
            if stored_names:
                response += f" (using stored data for: {', '.join(stored_names)})"
        await _calc_send(interaction, send_new_message, _embed("calc", response))

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
        attacker_ability: Optional[str] = None,
        attacker_tera: Optional[str] = None,
        defender_evs: Optional[str] = None,
        defender_nature: Optional[str] = None,
        defender_item: Optional[str] = None,
        defender_ability: Optional[str] = None,
        defender_tera: Optional[str] = None,
        defender_hp_percent: app_commands.Range[int, 1, 100] = 100,
        weather: Optional[str] = None,
        terrain: Optional[str] = None,
        screen: Optional[str] = None,
        spread: bool = False,
    ) -> None:
        await _run_calc(
            interaction, True,
            attacker=attacker, defender=defender, move=move,
            attacker_evs=attacker_evs, attacker_nature=attacker_nature,
            attacker_item=attacker_item, attacker_ability=attacker_ability, attacker_tera=attacker_tera,
            defender_evs=defender_evs, defender_nature=defender_nature,
            defender_item=defender_item, defender_ability=defender_ability, defender_tera=defender_tera,
            defender_hp_percent=defender_hp_percent, weather=weather,
            terrain=terrain, screen=screen, spread=spread,
        )

    @client.event
    async def on_ready() -> None:
        await tree.sync()

    @tree.error
    async def on_tree_error(interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
        command_name = interaction.command.name if interaction.command else "?"
        ephemeral = False
        if isinstance(error, app_commands.CommandOnCooldown):
            message = f"Slow down! Please wait {error.retry_after:.1f}s before using that again."
            color = discord.Color.orange()
        elif isinstance(error, app_commands.CheckFailure):
            # A correctly-rejected request (e.g. a non-owner running
            # /debug-last), not a malfunction -- don't log it as one, and
            # don't broadcast the rejection to the whole channel.
            message = "You don't have permission to use that command."
            color = discord.Color.orange()
            ephemeral = True
        else:
            print(f"Unhandled error in /{command_name}: {error!r}")
            message = "Something went wrong running that command. Please try again."
            color = discord.Color.red()
        embed = discord.Embed(description=message, color=color)
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=ephemeral)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=ephemeral)

    return client, tree


def _load_records() -> list:
    return json.loads(PROCESSED_RECORDS_PATH.read_text())


def _load_moves() -> list:
    return json.loads(VGC_MOVES_PATH.read_text())["moves"]


def _load_items() -> list:
    return json.loads(VGC_ITEMS_PATH.read_text())


def _load_usage() -> dict:
    if not USAGE_DATA_PATH.exists():
        return {}
    return json.loads(USAGE_DATA_PATH.read_text())


def _build_real_index(records: list, items: list, client=None) -> ChromaIndex:
    # Fixed collection name: build() upserts, so restarting the bot refreshes
    # this same persisted collection in place instead of leaking a new one.
    index = ChromaIndex(embedder=SentenceTransformerEmbedder(), client=client, collection_name="pokemon")
    index.build(records, items=items)
    return index


def _build_answerer() -> OllamaAnswerer:
    return OllamaAnswerer(
        host=os.environ["LLM_HOST"],
        model=os.environ.get("LLM_MODEL", "llama3.2:3b"),
        timeout=float(os.environ.get("LLM_TIMEOUT", "30")),
    )


def main() -> None:
    token = os.environ["DISCORD_TOKEN"]
    records = _load_records()
    items = _load_items()
    raw_answerer = _build_answerer()
    client, _tree = build_client(
        index=_build_real_index(records, items),
        answerer=CircuitBreaker(raw_answerer),
        raw_answerer=raw_answerer,
        records=records,
        moves=_load_moves(),
        usage=_load_usage(),
        items=items,
    )
    client.run(token)


if __name__ == "__main__":
    main()
