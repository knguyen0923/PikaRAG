import json
from typing import Callable, Optional

from bot.commands.ask import ask_response_async
from bot.commands.calc import calc_response
from bot.commands.team import format_team_block
from bot.pokemon_lookup import find_record, usage_for_record
from bot.team_store import get_team
from rag.answer import MALFORMED_TOOL_CALL_MESSAGE

RUN_DAMAGE_CALC_TOOL = {
    "type": "function",
    "function": {
        "name": "run_damage_calc",
        "description": (
            "Calculate a deterministic damage range for one attacker's move "
            "against one defender, VGC-standard (level 50, 31 IVs, neutral "
            "stat stages unless overridden). Always use this tool for any "
            "damage question -- never compute damage yourself."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "attacker_name": {"type": "string", "description": "The attacking Pokemon's name."},
                "defender_name": {"type": "string", "description": "The defending Pokemon's name."},
                "move_name": {"type": "string", "description": "The move being used."},
                "attacker_item": {"type": "string", "description": "The attacker's held item, if any."},
                "attacker_ability": {"type": "string", "description": "The attacker's ability, if any."},
                "attacker_tera": {"type": "string", "description": "The attacker's Tera type, if Terastallized."},
                "defender_item": {"type": "string", "description": "The defender's held item, if any."},
                "defender_ability": {"type": "string", "description": "The defender's ability, if any."},
                "defender_tera": {"type": "string", "description": "The defender's Tera type, if Terastallized."},
                "weather": {"type": "string", "description": "Active weather, if any (e.g. 'Sun', 'Rain')."},
                "terrain": {"type": "string", "description": "Active terrain, if any (e.g. 'Electric', 'Grassy')."},
            },
            "required": ["attacker_name", "defender_name", "move_name"],
        },
    },
}

GET_STORED_TEAM_TOOL = {
    "type": "function",
    "function": {
        "name": "get_stored_team",
        "description": (
            "Look up the current user's stored team and the stored opponent "
            "team, if any have been saved via /scout or /import. Takes no "
            "arguments -- always returns the calling user's own stored teams."
        ),
        "parameters": {"type": "object", "properties": {}},
    },
}

GET_USAGE_STATS_TOOL = {
    "type": "function",
    "function": {
        "name": "get_usage_stats",
        "description": "Look up a Pokemon's competitive usage-rate statistics, if available.",
        "parameters": {
            "type": "object",
            "properties": {"name": {"type": "string", "description": "The Pokemon's name."}},
            "required": ["name"],
        },
    },
}

TOOLS = [RUN_DAMAGE_CALC_TOOL, GET_STORED_TEAM_TOOL, GET_USAGE_STATS_TOOL]


def _run_damage_calc(records: list, moves: list, items: list, arguments: dict) -> str:
    return calc_response(
        records, moves,
        attacker_name=arguments["attacker_name"],
        defender_name=arguments["defender_name"],
        move_name=arguments["move_name"],
        items=items,
        attacker_item=arguments.get("attacker_item"),
        attacker_ability=arguments.get("attacker_ability"),
        attacker_tera=arguments.get("attacker_tera"),
        defender_item=arguments.get("defender_item"),
        defender_ability=arguments.get("defender_ability"),
        defender_tera=arguments.get("defender_tera"),
        weather=arguments.get("weather"),
        terrain=arguments.get("terrain"),
    )


def _get_stored_team(user_id: int, _arguments: dict) -> str:
    # user_id comes from the real Discord interaction (bound by
    # build_tool_dispatch), never from the model's tool-call arguments --
    # the schema takes no parameters at all, so there's nothing for a
    # confused or adversarial prompt to spoof.
    mine = format_team_block(get_team(user_id, "mine"), "Your team")
    opponent = format_team_block(get_team(user_id, "opponent"), "Opponent's team")
    blocks = [block for block in (mine, opponent) if block]
    return "\n\n".join(blocks) if blocks else "No stored team found for this user."


def _get_usage_stats(records: list, usage: Optional[dict], arguments: dict) -> str:
    record = find_record(records, arguments["name"])
    if record is None:
        return f"No Pokemon named '{arguments['name']}' found."
    stats = usage_for_record(usage, record)
    if stats is None:
        return f"No usage data available for {record['name']}."
    return json.dumps(stats)


def build_tool_dispatch(
    records: list, moves: list, items: list, usage: Optional[dict], user_id: int
) -> dict[str, Callable[[dict], str]]:
    """Binds each tool's implementation to the real request context so the
    model's tool-call arguments never carry anything security-sensitive --
    only Pokemon/move names and calc overrides, all safe to take from the
    model."""
    return {
        "run_damage_calc": lambda arguments: _run_damage_calc(records, moves, items, arguments),
        "get_stored_team": lambda arguments: _get_stored_team(user_id, arguments),
        "get_usage_stats": lambda arguments: _get_usage_stats(records, usage, arguments),
    }


async def analyze_response_async(
    answerer,
    question: str,
    records: list,
    moves: list,
    items: list,
    usage: Optional[dict],
    user_id: int,
    index=None,
    bm25_index=None,
) -> str:
    """Runs the agentic tool-calling loop, then falls back to a plain RAG
    /ask-style answer if the model's tool call was malformed or
    hallucinated. `answerer` must support answer_with_tools (pass
    raw_answerer, not a CircuitBreaker-wrapped one -- CircuitBreaker only
    implements .answer())."""
    tool_dispatch = build_tool_dispatch(records, moves, items, usage, user_id)
    answer = answerer.answer_with_tools(question, TOOLS, tool_dispatch)

    if answer == MALFORMED_TOOL_CALL_MESSAGE:
        result = await ask_response_async(
            index, answerer, question, records=records, items=items, bm25_index=bm25_index
        )
        return result["answer"]

    return answer
