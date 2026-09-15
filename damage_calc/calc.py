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
CHOICE_ITEM_STAT_MULTIPLIER = 1.5
ASSAULT_VEST_MULTIPLIER = 1.5
MIN_ROLL = 0.85
MAX_ROLL = 1.00
NEUTRAL_MULTIPLIER = 1.0

# The games track these modifiers as fixed-point /4096 fractions and chain
# multiple of them together into one combined value before ever rounding
# (Bulbapedia's "User:FIQ/Damage_calculation" reference) -- using the exact
# numerator keeps that chaining bit-faithful instead of drifting from a
# rounded-off decimal approximation. See _chain_numerators/_apply_numerator.
_NEUTRAL_NUM = 4096

# Base Power Modifiers -- chained together and applied ONCE to the move's
# base power, before the main damage formula runs.
TERRAIN_BOOST_NUM = 6144  # 1.5x -- grounded attacker, matching terrain
GEM_NUM = 5325            # ~1.300x
PLATE_NUM = 4915          # ~1.200x

# Final Modifiers -- chained together and applied ONCE to the computed
# damage, after type effectiveness. Screens, held items, and resist berries
# are all part of this single combined stage in-game -- flooring each one
# separately (as an earlier version of this file did) can be off by 1 from
# real damage whenever two or more of these apply at once.
SCREEN_DOUBLES_NUM = 2732  # ~0.667x
SCREEN_SINGLES_NUM = 2048  # 0.5x
LIFE_ORB_NUM = 5324        # ~1.300x
EXPERT_BELT_NUM = 4915     # ~1.200x
MUSCLE_BAND_NUM = 4505     # ~1.100x
WISE_GLASSES_NUM = 4505    # ~1.100x
RESIST_BERRY_NUM = 2048    # 0.5x

# Terrain name -> the move type it boosts.
_TERRAIN_TYPE_MAP = {"Electric": "Electric", "Grassy": "Grass", "Psychic": "Psychic"}

# Held item -> the stat it multiplies (applied in the stat calc, same as a stat stage).
_ITEM_STAT_BOOST = {
    "Choice Band": ("attack", CHOICE_ITEM_STAT_MULTIPLIER),
    "Choice Specs": ("sp_attack", CHOICE_ITEM_STAT_MULTIPLIER),
    "Choice Scarf": ("speed", CHOICE_ITEM_STAT_MULTIPLIER),
    "Assault Vest": ("sp_defense", ASSAULT_VEST_MULTIPLIER),
}

# Held item -> move type it boosts. Gems/plates modify the move's base POWER
# before the main damage formula runs, unlike Life Orb/Expert Belt which are
# part of the final modifier group applied after (see calculate_damage).
_GEM_TYPE = {
    "Normal Gem": "Normal", "Fire Gem": "Fire", "Water Gem": "Water", "Electric Gem": "Electric",
    "Grass Gem": "Grass", "Ice Gem": "Ice", "Fighting Gem": "Fighting", "Poison Gem": "Poison",
    "Ground Gem": "Ground", "Flying Gem": "Flying", "Psychic Gem": "Psychic", "Bug Gem": "Bug",
    "Rock Gem": "Rock", "Ghost Gem": "Ghost", "Dragon Gem": "Dragon", "Dark Gem": "Dark",
    "Steel Gem": "Steel", "Fairy Gem": "Fairy",
}
_PLATE_TYPE = {
    "Flame Plate": "Fire", "Splash Plate": "Water", "Zap Plate": "Electric",
    "Meadow Plate": "Grass", "Icicle Plate": "Ice", "Fist Plate": "Fighting",
    "Toxic Plate": "Poison", "Earth Plate": "Ground", "Sky Plate": "Flying",
    "Mind Plate": "Psychic", "Insect Plate": "Bug", "Stone Plate": "Rock",
    "Spooky Plate": "Ghost", "Draco Plate": "Dragon", "Dread Plate": "Dark",
    "Iron Plate": "Steel", "Pixie Plate": "Fairy",
}

# Held item (defender) -> move type it halves damage from (single-use resist
# berries, final modifier group). Chilan Berry is the one exception: it applies
# to Normal-type moves regardless of effectiveness, since no type is ever
# super-effective against Normal.
_RESIST_BERRY_TYPE = {
    "Occa Berry": "Fire", "Passho Berry": "Water", "Wacan Berry": "Electric",
    "Rindo Berry": "Grass", "Yache Berry": "Ice", "Chople Berry": "Fighting",
    "Kebia Berry": "Poison", "Shuca Berry": "Ground", "Coba Berry": "Flying",
    "Payapa Berry": "Psychic", "Tanga Berry": "Bug", "Charti Berry": "Rock",
    "Kasib Berry": "Ghost", "Haban Berry": "Dragon", "Colbur Berry": "Dark",
    "Babiri Berry": "Steel", "Chilan Berry": "Normal", "Roseli Berry": "Fairy",
}

# Ability (attacker) -> Attack-stat multiplier, applied in _effective_stat the
# same way _ITEM_STAT_BOOST already is -- Huge Power and Pure Power are
# mechanically identical (2x Attack), just different Pokemon-specific names.
ABILITY_ATTACK_DOUBLE_MULTIPLIER = 2.0
_ABILITY_STAT_BOOST = {
    "Huge Power": ("attack", ABILITY_ATTACK_DOUBLE_MULTIPLIER),
    "Pure Power": ("attack", ABILITY_ATTACK_DOUBLE_MULTIPLIER),
}

# Ability (attacker) -> replaces the normal 1.5x STAB multiplier when the
# move's type matches the attacker's own type(s).
ADAPTABILITY_STAB_MULTIPLIER = 2.0

# Ability (defender) -> halves damage taken while at full HP. Final Modifier
# group, same numerator-chain stage as screens/items/berries.
MULTISCALE_NUM = 2048  # 0.5x
_MULTISCALE_ABILITIES = {"Multiscale", "Shadow Shield"}

# Ability (defender) -> 0.75x damage taken on a super-effective hit.
FILTER_NUM = 3072  # 0.75x
_FILTER_ABILITIES = {"Filter", "Solid Rock", "Prism Armor"}

# Ability (defender) -> halves Fire/Ice damage taken.
THICK_FAT_NUM = 2048  # 0.5x
_THICK_FAT_TYPES = {"Fire", "Ice"}

# Ability (attacker) -> doubles damage on a not-very-effective hit.
TINTED_LENS_NUM = 8192  # 2.0x


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
        ability_stat, ability_multiplier = _ABILITY_STAT_BOOST.get(combatant.get("ability"), (None, None))
        if ability_stat == stat_name:
            stat = math.floor(stat * ability_multiplier)
    return stat


def _apply_floor(value: int, multiplier: float) -> int:
    """Apply one modifier and truncate, as the games do at each chain step."""
    return math.floor(value * multiplier)


def _poke_round(value: float) -> int:
    """Round half UP -- the games' rounding for the STAB step, and for
    applying a combined Base Power/Final modifier chain (see below)."""
    return math.floor(value + 0.5)


def _chain_numerators(numerators: list) -> int:
    """Combine /4096 modifier numerators into one, per the games' fixed-point
    chaining rule: each step folds the next modifier into the running
    combined value via round_half_up((combined * next) / 4096), starting
    from a neutral 4096 (1x). An empty list yields 4096 (no-op)."""
    combined = _NEUTRAL_NUM
    for numerator in numerators:
        combined = _poke_round(combined * numerator / _NEUTRAL_NUM)
    return combined


def _apply_numerator(value: int, combined_numerator: int) -> int:
    """Apply an already-chained /4096 numerator to a value, rounding half up."""
    return _poke_round(value * combined_numerator / _NEUTRAL_NUM)


def _damage_at_roll(
    base_damage: int,
    roll: float,
    spread_modifier: float,
    weather_modifier: float,
    stab: float,
    type_effectiveness: float,
    final_modifier_numerator: int,
) -> int:
    """Run the modifier chain for one damage roll.

    Multi-target, weather, the random roll, and type effectiveness each
    truncate immediately after being applied; STAB rounds half up instead.
    Screens/items/berries are NOT separate truncation steps -- they were
    already combined into final_modifier_numerator (see calculate_damage)
    and are applied here as that one already-chained value, per the games'
    "Final Modifiers" stage.
    """
    damage = _apply_floor(base_damage, spread_modifier)
    damage = _apply_floor(damage, weather_modifier)
    damage = _apply_floor(damage, roll)
    damage = _poke_round(damage * stab)
    damage = _apply_floor(damage, type_effectiveness)
    damage = _apply_numerator(damage, final_modifier_numerator)
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
    attacker_item = attacker.get("item")

    terrain = context.get("terrain")
    terrain_applies = bool(terrain) and _TERRAIN_TYPE_MAP.get(terrain) == move["type"]

    # Base Power Modifiers: Gem/Plate and Terrain are chained together and
    # applied once to power, before the main damage formula runs.
    power_numerators = []
    if _GEM_TYPE.get(attacker_item) == move["type"]:
        power_numerators.append(GEM_NUM)
    elif _PLATE_TYPE.get(attacker_item) == move["type"]:
        power_numerators.append(PLATE_NUM)
    if terrain_applies:
        power_numerators.append(TERRAIN_BOOST_NUM)
    power = _apply_numerator(power, _chain_numerators(power_numerators))

    if category == "Physical":
        attack_stat = _effective_stat(attacker, "attack")
        defense_stat = _effective_stat(defender, "defense")
    else:
        attack_stat = _effective_stat(attacker, "sp_attack")
        defense_stat = _effective_stat(defender, "sp_defense")

    attacker_types = [attacker["tera_type"]] if attacker["tera_type"] else attacker["record"]["types"]
    if move["type"] in attacker_types:
        stab = ADAPTABILITY_STAB_MULTIPLIER if attacker.get("ability") == "Adaptability" else STAB_MULTIPLIER
    else:
        stab = NO_STAB_MULTIPLIER

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

    # Final Modifiers: screens, the attacker's held item, and a defending
    # resist berry are all chained together and applied once to damage,
    # after type effectiveness (see _damage_at_roll).
    final_numerators = []

    screen = context.get("screen")
    screen_applies = (
        (screen == "Reflect" and category == "Physical")
        or (screen == "Light Screen" and category == "Special")
        or (screen == "Aurora Veil")
    )
    if screen_applies:
        final_numerators.append(SCREEN_DOUBLES_NUM if context.get("is_doubles") else SCREEN_SINGLES_NUM)

    if attacker_item == "Life Orb":
        final_numerators.append(LIFE_ORB_NUM)
    elif attacker_item == "Expert Belt" and type_effectiveness > 1:
        final_numerators.append(EXPERT_BELT_NUM)
    elif attacker_item == "Muscle Band" and category == "Physical":
        final_numerators.append(MUSCLE_BAND_NUM)
    elif attacker_item == "Wise Glasses" and category == "Special":
        final_numerators.append(WISE_GLASSES_NUM)

    resist_berry_type = _RESIST_BERRY_TYPE.get(defender.get("item"))
    if resist_berry_type == move["type"] and (type_effectiveness > 1 or resist_berry_type == "Normal"):
        final_numerators.append(RESIST_BERRY_NUM)

    if defender.get("ability") in _MULTISCALE_ABILITIES and defender.get("current_hp_fraction") == 1.0:
        final_numerators.append(MULTISCALE_NUM)
    if defender.get("ability") in _FILTER_ABILITIES and type_effectiveness > 1:
        final_numerators.append(FILTER_NUM)
    if defender.get("ability") == "Thick Fat" and move["type"] in _THICK_FAT_TYPES:
        final_numerators.append(THICK_FAT_NUM)
    if attacker.get("ability") == "Tinted Lens" and 0 < type_effectiveness < 1:
        final_numerators.append(TINTED_LENS_NUM)

    final_modifier_numerator = _chain_numerators(final_numerators)

    chain = dict(
        base_damage=base_damage,
        spread_modifier=spread_modifier,
        weather_modifier=weather_modifier,
        stab=stab,
        type_effectiveness=type_effectiveness,
        final_modifier_numerator=final_modifier_numerator,
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
