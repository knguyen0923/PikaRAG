import math
from dataclasses import dataclass

from damage_calc.data.type_chart import get_effectiveness
from damage_calc.data.natures import get_nature_modifiers
from damage_calc.data.stat_stages import get_stage_multiplier


# --- Damage modifier constants ---
STAB_MULTIPLIER = 1.5
NO_STAB_MULTIPLIER = 1.0
SPREAD_MULTIPLIER = 0.75          # doubles, move hits more than one target
WEATHER_BOOST_MULTIPLIER = 1.5    # Rain/Water, Sun/Fire
WEATHER_PENALTY_MULTIPLIER = 0.5  # Rain/Fire, Sun/Water
TERRAIN_BOOST_MULTIPLIER = 1.3    # grounded attacker, matching terrain
SCREEN_DOUBLES_MULTIPLIER = 2 / 3
SCREEN_SINGLES_MULTIPLIER = 0.5
LIFE_ORB_MULTIPLIER = 1.3
EXPERT_BELT_MULTIPLIER = 1.2
CHOICE_ITEM_STAT_MULTIPLIER = 1.5
MIN_ROLL = 0.85
MAX_ROLL = 1.00
NEUTRAL_MULTIPLIER = 1.0

# Terrain name -> the move type it boosts.
_TERRAIN_TYPE_MAP = {"Electric": "Electric", "Grassy": "Grass", "Psychic": "Psychic"}

# Held item -> the stat it multiplies (applied in the stat calc, same as a stat stage).
_ITEM_STAT_BOOST = {
    "Choice Band": ("attack", CHOICE_ITEM_STAT_MULTIPLIER),
    "Choice Specs": ("sp_attack", CHOICE_ITEM_STAT_MULTIPLIER),
}


def calculate_stat(base: int, iv: int, ev: int, level: int, nature_modifier: float, stat_name: str) -> int:
    core = math.floor((2 * base + iv + math.floor(ev / 4)) * level / 100)
    if stat_name == "hp":
        if base == 1:  # Shedinja-style single-HP mons, not in this dataset but keep formula honest
            return 1
        return core + level + 10
    return math.floor((core + 5) * nature_modifier)


@dataclass
class DamageResult:
    min_damage: int
    max_damage: int
    min_percent: float
    max_percent: float
    is_ko_chance: bool


def _nature_modifier_for_stat(nature: str, stat_name: str) -> float:
    mods = get_nature_modifiers(nature)
    if mods["boosted"] == stat_name:
        return 1.1
    if mods["lowered"] == stat_name:
        return 0.9
    return 1.0


def _effective_stat(combatant: dict, stat_name: str) -> int:
    base = combatant["record"]["base_stats"][stat_name]
    iv = combatant["ivs"][stat_name]
    ev = combatant["evs"][stat_name]
    level = combatant["level"]
    nature_mod = _nature_modifier_for_stat(combatant["nature"], stat_name)
    stat = calculate_stat(base, iv, ev, level, nature_mod, stat_name)
    if stat_name != "hp":
        stage = combatant["stat_stages"].get(stat_name, 0)
        stat = math.floor(stat * get_stage_multiplier(stage))
        item_stat, item_multiplier = _ITEM_STAT_BOOST.get(combatant.get("item"), (None, None))
        if item_stat == stat_name:
            stat = math.floor(stat * item_multiplier)
    return stat


def _apply_floor(value: int, multiplier: float) -> int:
    """Apply one modifier and truncate, as the games do at each chain step."""
    return math.floor(value * multiplier)


def _poke_round(value: float) -> int:
    """Round half UP -- the games' rounding for the STAB step specifically."""
    return math.floor(value + 0.5)


def _damage_at_roll(
    base_damage: int,
    roll: float,
    spread_modifier: float,
    weather_modifier: float,
    stab: float,
    type_effectiveness: float,
    terrain_modifier: float,
    screen_modifier: float,
    item_modifier: float,
) -> int:
    """Run the modifier chain for one damage roll.

    Real damage calculation truncates after EACH modifier rather than once at
    the end, and the STAB step rounds half up instead of truncating. The order
    below is the in-game order; changing it changes results in ~20-40% of cases.
    """
    damage = _apply_floor(base_damage, spread_modifier)
    damage = _apply_floor(damage, weather_modifier)
    damage = _apply_floor(damage, roll)
    damage = _poke_round(damage * stab)
    damage = _apply_floor(damage, type_effectiveness)
    damage = _apply_floor(damage, terrain_modifier)
    damage = _apply_floor(damage, screen_modifier)
    damage = _apply_floor(damage, item_modifier)
    return damage


def calculate_damage(move: dict, attacker: dict, defender: dict, context: dict) -> DamageResult:
    category = move["category"]

    # Status moves and any 0-power move deal exactly zero damage; without this
    # guard the final "minimum 1 damage" floor would report a few points for
    # Protect, Tailwind, etc.
    if category == "Status" or not move.get("power"):
        return DamageResult(
            min_damage=0, max_damage=0, min_percent=0.0, max_percent=0.0, is_ko_chance=False
        )

    level = attacker["level"]
    power = move["power"]

    if category == "Physical":
        attack_stat = _effective_stat(attacker, "attack")
        defense_stat = _effective_stat(defender, "defense")
    else:
        attack_stat = _effective_stat(attacker, "sp_attack")
        defense_stat = _effective_stat(defender, "sp_defense")

    attacker_types = [attacker["tera_type"]] if attacker["tera_type"] else attacker["record"]["types"]
    stab = STAB_MULTIPLIER if move["type"] in attacker_types else NO_STAB_MULTIPLIER

    # A Terastallized defender's defensive typing is REPLACED by its Tera type.
    defender_types = [defender["tera_type"]] if defender["tera_type"] else defender["record"]["types"]
    type_effectiveness = get_effectiveness(move["type"], defender_types)

    base_damage = math.floor(
        math.floor(math.floor(2 * level / 5 + 2) * power * attack_stat / defense_stat) / 50
    ) + 2

    spread_modifier = (
        SPREAD_MULTIPLIER
        if context.get("is_spread_target") and context.get("is_doubles")
        else NEUTRAL_MULTIPLIER
    )

    weather = context.get("weather")
    weather_modifier = NEUTRAL_MULTIPLIER
    if weather == "Rain":
        if move["type"] == "Water":
            weather_modifier = WEATHER_BOOST_MULTIPLIER
        elif move["type"] == "Fire":
            weather_modifier = WEATHER_PENALTY_MULTIPLIER
    elif weather == "Sun":
        if move["type"] == "Fire":
            weather_modifier = WEATHER_BOOST_MULTIPLIER
        elif move["type"] == "Water":
            weather_modifier = WEATHER_PENALTY_MULTIPLIER

    terrain = context.get("terrain")
    terrain_modifier = (
        TERRAIN_BOOST_MULTIPLIER
        if terrain and _TERRAIN_TYPE_MAP.get(terrain) == move["type"]
        else NEUTRAL_MULTIPLIER
    )

    screen = context.get("screen")
    screen_applies = (
        (screen == "Reflect" and category == "Physical")
        or (screen == "Light Screen" and category == "Special")
        or (screen == "Aurora Veil")
    )
    if screen_applies:
        screen_modifier = (
            SCREEN_DOUBLES_MULTIPLIER if context.get("is_doubles") else SCREEN_SINGLES_MULTIPLIER
        )
    else:
        screen_modifier = NEUTRAL_MULTIPLIER

    attacker_item = attacker.get("item")
    if attacker_item == "Life Orb":
        item_modifier = LIFE_ORB_MULTIPLIER
    elif attacker_item == "Expert Belt" and type_effectiveness > 1:
        item_modifier = EXPERT_BELT_MULTIPLIER
    else:
        item_modifier = NEUTRAL_MULTIPLIER

    chain = dict(
        base_damage=base_damage,
        spread_modifier=spread_modifier,
        weather_modifier=weather_modifier,
        stab=stab,
        type_effectiveness=type_effectiveness,
        terrain_modifier=terrain_modifier,
        screen_modifier=screen_modifier,
        item_modifier=item_modifier,
    )
    min_damage = _damage_at_roll(roll=MIN_ROLL, **chain)
    max_damage = _damage_at_roll(roll=MAX_ROLL, **chain)

    # A fully immune matchup deals exactly zero; everything else deals at least 1.
    if type_effectiveness == 0:
        min_damage = max_damage = 0
    else:
        min_damage = max(1, min_damage)
        max_damage = max(1, max_damage)

    defender_hp = _effective_stat(defender, "hp")
    remaining_hp = math.floor(defender_hp * defender["current_hp_fraction"])

    min_percent = round(100 * min_damage / defender_hp, 2) if defender_hp else 0.0
    max_percent = round(100 * max_damage / defender_hp, 2) if defender_hp else 0.0
    is_ko_chance = max_damage >= remaining_hp

    return DamageResult(
        min_damage=min_damage,
        max_damage=max_damage,
        min_percent=min_percent,
        max_percent=max_percent,
        is_ko_chance=is_ko_chance,
    )
