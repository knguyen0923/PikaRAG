import math
from dataclasses import dataclass

from damage_calc.data.type_chart import get_effectiveness
from damage_calc.data.natures import get_nature_modifiers
from damage_calc.data.stat_stages import get_stage_multiplier


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
    return stat


def calculate_damage(move: dict, attacker: dict, defender: dict, context: dict) -> DamageResult:
    level = attacker["level"]
    power = move["power"] or 0
    category = move["category"]

    if category == "Physical":
        attack_stat = _effective_stat(attacker, "attack")
        defense_stat = _effective_stat(defender, "defense")
    else:
        attack_stat = _effective_stat(attacker, "sp_attack")
        defense_stat = _effective_stat(defender, "sp_defense")

    attacker_types = [attacker["tera_type"]] if attacker["tera_type"] else attacker["record"]["types"]
    stab = 1.5 if move["type"] in attacker_types else 1.0

    type_effectiveness = get_effectiveness(move["type"], defender["record"]["types"])

    base_damage = math.floor(
        math.floor(math.floor(2 * level / 5 + 2) * power * attack_stat / defense_stat) / 50
    ) + 2

    modifier_low = stab * type_effectiveness * 0.85
    modifier_high = stab * type_effectiveness * 1.0

    spread_modifier = 0.75 if context.get("is_spread_target") and context.get("is_doubles") else 1.0
    modifier_low *= spread_modifier
    modifier_high *= spread_modifier

    weather = context.get("weather")
    if weather == "Rain":
        if move["type"] == "Water":
            modifier_low *= 1.5
            modifier_high *= 1.5
        elif move["type"] == "Fire":
            modifier_low *= 0.5
            modifier_high *= 0.5
    elif weather == "Sun":
        if move["type"] == "Fire":
            modifier_low *= 1.5
            modifier_high *= 1.5
        elif move["type"] == "Water":
            modifier_low *= 0.5
            modifier_high *= 0.5

    terrain = context.get("terrain")
    _TERRAIN_TYPE_MAP = {"Electric": "Electric", "Grassy": "Grass", "Psychic": "Psychic"}
    if terrain and _TERRAIN_TYPE_MAP.get(terrain) == move["type"]:
        modifier_low *= 1.3
        modifier_high *= 1.3

    screen = context.get("screen")
    screen_applies = (
        (screen == "Reflect" and category == "Physical")
        or (screen == "Light Screen" and category == "Special")
        or (screen == "Aurora Veil")
    )
    if screen_applies:
        screen_multiplier = 2 / 3 if context.get("is_doubles") else 0.5
        modifier_low *= screen_multiplier
        modifier_high *= screen_multiplier

    min_damage = max(1, math.floor(base_damage * modifier_low)) if type_effectiveness > 0 else 0
    max_damage = max(1, math.floor(base_damage * modifier_high)) if type_effectiveness > 0 else 0

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
