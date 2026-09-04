import math
from damage_calc.calc import calculate_stat, calculate_damage


def test_hp_stat_formula():
    # base 90, 31 IV, 252 EV, level 50 -> floor((2*90 + 31 + 63) * 50 / 100) + 50 + 10
    # = floor(274 * 50 / 100) + 60 = 137 + 60 = 197
    assert calculate_stat(90, 31, 252, 50, 1.0, "hp") == 197


def test_non_hp_stat_formula_neutral_nature():
    # base 92 attack, 31 IV, 252 EV, level 50, neutral nature
    # = floor((floor((2*92 + 31 + 63) * 50 / 100) + 5) * 1.0) = floor((139 + 5) * 1.0) = 144
    assert calculate_stat(92, 31, 252, 50, 1.0, "attack") == 144


def test_non_hp_stat_formula_boosting_nature():
    # same as above but with a 1.1 boosting nature multiplier
    # = floor((139 + 5) * 1.1) = floor(158.4) = 158
    assert calculate_stat(92, 31, 252, 50, 1.1, "attack") == 158


def _make_combatant(base_stats, level=50, evs=None, nature="Hardy", stat_stages=None, ability=None, item=None, tera_type=None, types=None):
    return {
        "record": {
            "name": "TestMon",
            "types": types or ["Normal"],
            "base_stats": base_stats,
            "abilities": [],
            "learnset": [],
            "legal_in": ["M-B"],
        },
        "level": level,
        "evs": evs or {"hp": 0, "attack": 0, "defense": 0, "sp_attack": 0, "sp_defense": 0, "speed": 0},
        "ivs": {"hp": 31, "attack": 31, "defense": 31, "sp_attack": 31, "sp_defense": 31, "speed": 31},
        "nature": nature,
        "stat_stages": stat_stages or {"attack": 0, "defense": 0, "sp_attack": 0, "sp_defense": 0, "speed": 0},
        "tera_type": tera_type,
        "item": item,
        "ability": ability,
        "current_hp_fraction": 1.0,
    }


_BASE_CONTEXT = {
    "weather": None, "terrain": None, "is_spread_target": False,
    "screen": None, "is_doubles": True,
}


def test_basic_physical_hit_neutral_type():
    move = {"name": "Tackle", "type": "Normal", "category": "Physical", "power": 40, "accuracy": 100, "pp": 35, "effect": None}
    attacker = _make_combatant(
        {"hp": 100, "attack": 100, "defense": 100, "sp_attack": 100, "sp_defense": 100, "speed": 100},
        evs={"hp": 0, "attack": 252, "defense": 0, "sp_attack": 0, "sp_defense": 0, "speed": 0},
        nature="Adamant",
        types=["Normal"],
    )
    defender = _make_combatant(
        {"hp": 100, "attack": 100, "defense": 100, "sp_attack": 100, "sp_defense": 100, "speed": 100},
        evs={"hp": 252, "attack": 0, "defense": 0, "sp_attack": 0, "sp_defense": 0, "speed": 0},
        types=["Water"],
    )

    result = calculate_damage(move, attacker, defender, _BASE_CONTEXT)

    assert result.min_damage > 0
    assert result.max_damage >= result.min_damage
    # STAB (Normal atk on Normal-type attacker) applied, neutral type effectiveness vs Water.
    # attack_stat=167 (100 base, 252 EV, Adamant), defense_stat=120 (100 base, 0 EV, neutral)
    # base_damage = floor(floor(floor(2*50/5+2)*40*167/120)/50)+2 = 26
    #
    # Step-by-step chain (no spread/weather/terrain/screen, so those are 1.0):
    #   min roll: 26 -> floor(26*1.0)=26 -> floor(26*1.0)=26 -> floor(26*0.85)=22
    #             -> poke_round(22*1.5)=poke_round(33.0)=33 -> floor(33*1.0)=33 -> 33 -> 33
    #   max roll: 26 -> 26 -> 26 -> floor(26*1.00)=26
    #             -> poke_round(26*1.5)=poke_round(39.0)=39 -> 39 -> 39 -> 39
    # Same as the old flat-product order for this case, confirmed rather than assumed.
    assert result.min_damage == 33
    assert result.max_damage == 39


def test_stat_stage_negative_attack_reduces_damage():
    move = {"name": "Tackle", "type": "Normal", "category": "Physical", "power": 40, "accuracy": 100, "pp": 35, "effect": None}
    stats = {"hp": 100, "attack": 100, "defense": 100, "sp_attack": 100, "sp_defense": 100, "speed": 100}
    attacker_neutral = _make_combatant(stats, types=["Normal"])
    attacker_intimidated = _make_combatant(stats, types=["Normal"], stat_stages={"attack": -1, "defense": 0, "sp_attack": 0, "sp_defense": 0, "speed": 0})
    defender = _make_combatant(stats, types=["Water"])

    result_neutral = calculate_damage(move, attacker_neutral, defender, _BASE_CONTEXT)
    result_intimidated = calculate_damage(move, attacker_intimidated, defender, _BASE_CONTEXT)

    assert result_intimidated.max_damage < result_neutral.max_damage


def test_spread_move_applies_075_multiplier_in_doubles():
    move = {"name": "Earthquake", "type": "Ground", "category": "Physical", "power": 100, "accuracy": 100, "pp": 10, "effect": None}
    stats = {"hp": 100, "attack": 100, "defense": 100, "sp_attack": 100, "sp_defense": 100, "speed": 100}
    attacker = _make_combatant(stats, types=["Ground"])
    defender = _make_combatant(stats, types=["Water"])

    single_target_context = {**_BASE_CONTEXT, "is_spread_target": False}
    spread_context = {**_BASE_CONTEXT, "is_spread_target": True}

    single = calculate_damage(move, attacker, defender, single_target_context)
    spread = calculate_damage(move, attacker, defender, spread_context)

    assert spread.max_damage < single.max_damage
    assert spread.max_damage == math.floor(single.max_damage * 0.75) or spread.max_damage == math.floor(single.max_damage * 0.75) - 1


def test_tera_type_changes_effectiveness_and_stab():
    # Attacker is pure Normal but Tera'd into Fighting; move is Fighting-type
    # Fighting is 2x vs Normal defender base type... use a defender that's Rock (Fighting is 2x vs Rock)
    move = {"name": "Close Combat", "type": "Fighting", "category": "Physical", "power": 120, "accuracy": 100, "pp": 8, "effect": None}
    stats = {"hp": 100, "attack": 100, "defense": 100, "sp_attack": 100, "sp_defense": 100, "speed": 100}
    attacker_no_tera = _make_combatant(stats, types=["Normal"], tera_type=None)
    attacker_tera_fighting = _make_combatant(stats, types=["Normal"], tera_type="Fighting")
    defender = _make_combatant(stats, types=["Rock"])

    no_tera = calculate_damage(move, attacker_no_tera, defender, _BASE_CONTEXT)
    tera = calculate_damage(move, attacker_tera_fighting, defender, _BASE_CONTEXT)

    # No Tera: no STAB (Normal attacker using Fighting move), just 2x type effectiveness vs Rock
    # Tera Fighting: STAB applies too (1.5x on top), so damage should be higher
    assert tera.max_damage > no_tera.max_damage


def test_rain_boosts_water_move():
    move = {"name": "Surf", "type": "Water", "category": "Special", "power": 90, "accuracy": 100, "pp": 15, "effect": None}
    stats = {"hp": 100, "attack": 100, "defense": 100, "sp_attack": 100, "sp_defense": 100, "speed": 100}
    attacker = _make_combatant(stats, types=["Water"])
    defender = _make_combatant(stats, types=["Normal"])

    no_weather = calculate_damage(move, attacker, defender, {**_BASE_CONTEXT, "weather": None})
    rain = calculate_damage(move, attacker, defender, {**_BASE_CONTEXT, "weather": "Rain"})

    assert rain.max_damage > no_weather.max_damage


def test_sun_weakens_water_move():
    move = {"name": "Surf", "type": "Water", "category": "Special", "power": 90, "accuracy": 100, "pp": 15, "effect": None}
    stats = {"hp": 100, "attack": 100, "defense": 100, "sp_attack": 100, "sp_defense": 100, "speed": 100}
    attacker = _make_combatant(stats, types=["Water"])
    defender = _make_combatant(stats, types=["Normal"])

    no_weather = calculate_damage(move, attacker, defender, {**_BASE_CONTEXT, "weather": None})
    sun = calculate_damage(move, attacker, defender, {**_BASE_CONTEXT, "weather": "Sun"})

    assert sun.max_damage < no_weather.max_damage


def test_electric_terrain_boosts_electric_move():
    move = {"name": "Thunderbolt", "type": "Electric", "category": "Special", "power": 90, "accuracy": 100, "pp": 15, "effect": None}
    stats = {"hp": 100, "attack": 100, "defense": 100, "sp_attack": 100, "sp_defense": 100, "speed": 100}
    attacker = _make_combatant(stats, types=["Electric"])
    defender = _make_combatant(stats, types=["Water"])

    no_terrain = calculate_damage(move, attacker, defender, {**_BASE_CONTEXT, "terrain": None})
    terrain = calculate_damage(move, attacker, defender, {**_BASE_CONTEXT, "terrain": "Electric"})

    assert terrain.max_damage > no_terrain.max_damage


def test_reflect_halves_physical_damage():
    move = {"name": "Tackle", "type": "Normal", "category": "Physical", "power": 40, "accuracy": 100, "pp": 35, "effect": None}
    stats = {"hp": 100, "attack": 100, "defense": 100, "sp_attack": 100, "sp_defense": 100, "speed": 100}
    attacker = _make_combatant(stats, types=["Normal"])
    defender = _make_combatant(stats, types=["Water"])

    no_screen = calculate_damage(move, attacker, defender, {**_BASE_CONTEXT, "screen": None})
    reflect = calculate_damage(move, attacker, defender, {**_BASE_CONTEXT, "screen": "Reflect"})

    assert reflect.max_damage < no_screen.max_damage


def test_light_screen_does_not_affect_physical_damage():
    move = {"name": "Tackle", "type": "Normal", "category": "Physical", "power": 40, "accuracy": 100, "pp": 35, "effect": None}
    stats = {"hp": 100, "attack": 100, "defense": 100, "sp_attack": 100, "sp_defense": 100, "speed": 100}
    attacker = _make_combatant(stats, types=["Normal"])
    defender = _make_combatant(stats, types=["Water"])

    no_screen = calculate_damage(move, attacker, defender, {**_BASE_CONTEXT, "screen": None})
    light_screen = calculate_damage(move, attacker, defender, {**_BASE_CONTEXT, "screen": "Light Screen"})

    assert light_screen.max_damage == no_screen.max_damage


_NEUTRAL_STATS = {"hp": 100, "attack": 100, "defense": 100, "sp_attack": 100, "sp_defense": 100, "speed": 100}
# For all three cases below: base 100 / 31 IV / 0 EV / level 50 / neutral nature
# gives an offensive and defensive stat of 120 each:
#   core = floor((2*100 + 31 + 0) * 50/100) = floor(115.5) = 115; (115+5)*1.0 = 120


def test_spread_stab_exact_values_differ_from_flat_product_order():
    # Earthquake (Ground, 100 BP, Physical), Ground attacker (STAB), Water
    # defender (neutral), spread target in doubles (0.75).
    # base_damage = floor(floor(floor(2*50/5+2)*100*120/120)/50)+2
    #             = floor(floor(22*100)/50)+2 = floor(2200/50)+2 = 44+2 = 46
    # min roll: floor(46*0.75)=34 -> weather 34 -> floor(34*0.85)=28
    #           -> poke_round(28*1.5)=poke_round(42.0)=42 -> x1.0 -> 42
    # max roll: floor(46*0.75)=34 -> 34 -> floor(34*1.00)=34
    #           -> poke_round(34*1.5)=poke_round(51.0)=51 -> 51
    # Old flat-product order gave min = floor(46 * 1.5*1.0*0.85*0.75)
    #   = floor(43.98) = 43, so the min value proves the ordering fix.
    move = {"name": "Earthquake", "type": "Ground", "category": "Physical", "power": 100, "accuracy": 100, "pp": 10, "effect": None}
    attacker = _make_combatant(_NEUTRAL_STATS, types=["Ground"])
    defender = _make_combatant(_NEUTRAL_STATS, types=["Water"])

    result = calculate_damage(move, attacker, defender, {**_BASE_CONTEXT, "is_spread_target": True})

    assert result.min_damage == 42
    assert result.max_damage == 51


def test_rain_boosted_stab_exact_values_differ_from_flat_product_order():
    # Surf (Water, 90 BP, Special), Water attacker (STAB), Normal defender
    # (neutral), Rain (1.5x on Water).
    # base_damage = floor(floor(floor(22)*90*120/120)/50)+2
    #             = floor(1980/50)+2 = 39+2 = 41
    # min roll: spread 41 -> floor(41*1.5)=61 -> floor(61*0.85)=51
    #           -> poke_round(51*1.5)=poke_round(76.5)=77 -> 77
    # max roll: 41 -> 61 -> floor(61*1.00)=61
    #           -> poke_round(61*1.5)=poke_round(91.5)=92 -> 92
    # Old flat-product order gave min = floor(41 * 1.5*1.0*0.85*1.5)
    #   = floor(78.41) = 78. Both rolls also land exactly on a .5 boundary,
    #   so this pins the round-half-up behaviour of the STAB step.
    move = {"name": "Surf", "type": "Water", "category": "Special", "power": 90, "accuracy": 100, "pp": 15, "effect": None}
    attacker = _make_combatant(_NEUTRAL_STATS, types=["Water"])
    defender = _make_combatant(_NEUTRAL_STATS, types=["Normal"])

    result = calculate_damage(move, attacker, defender, {**_BASE_CONTEXT, "weather": "Rain"})

    assert result.min_damage == 77
    assert result.max_damage == 92


def test_resisted_stab_exact_values_differ_from_flat_product_order():
    # Thunderbolt (Electric, 90 BP, Special), Electric attacker (STAB),
    # Grass defender (0.5x). base_damage = 41 as above.
    # min roll: 41 -> 41 -> floor(41*0.85)=34
    #           -> poke_round(34*1.5)=poke_round(51.0)=51 -> floor(51*0.5)=25
    # max roll: 41 -> 41 -> 41
    #           -> poke_round(41*1.5)=poke_round(61.5)=62 -> floor(62*0.5)=31
    # Old flat-product order gave min = floor(41*1.5*0.5*0.85) = floor(26.13) = 26
    #   and max = floor(41*1.5*0.5) = floor(30.75) = 30 -- both differ.
    move = {"name": "Thunderbolt", "type": "Electric", "category": "Special", "power": 90, "accuracy": 100, "pp": 15, "effect": None}
    attacker = _make_combatant(_NEUTRAL_STATS, types=["Electric"])
    defender = _make_combatant(_NEUTRAL_STATS, types=["Grass"])

    result = calculate_damage(move, attacker, defender, _BASE_CONTEXT)

    assert result.min_damage == 25
    assert result.max_damage == 31


def test_immune_matchup_deals_zero_damage():
    # Normal move vs Ghost defender: 0x effectiveness, so exactly 0 -- the
    # "minimum 1 damage" floor must not apply.
    move = {"name": "Tackle", "type": "Normal", "category": "Physical", "power": 40, "accuracy": 100, "pp": 35, "effect": None}
    attacker = _make_combatant(_NEUTRAL_STATS, types=["Normal"])
    defender = _make_combatant(_NEUTRAL_STATS, types=["Ghost"])

    result = calculate_damage(move, attacker, defender, _BASE_CONTEXT)

    assert result.min_damage == 0
    assert result.max_damage == 0
    assert result.min_percent == 0.0
    assert result.max_percent == 0.0
    assert result.is_ko_chance is False


def test_ground_move_vs_flying_defender_is_immune():
    move = {"name": "Earthquake", "type": "Ground", "category": "Physical", "power": 100, "accuracy": 100, "pp": 10, "effect": None}
    attacker = _make_combatant(_NEUTRAL_STATS, types=["Ground"])
    defender = _make_combatant(_NEUTRAL_STATS, types=["Flying"])

    result = calculate_damage(move, attacker, defender, _BASE_CONTEXT)

    assert result.min_damage == 0
    assert result.max_damage == 0


def test_defender_tera_type_replaces_defensive_typing():
    # Defender is Rock (Fighting hits it for 2x). Terastallizing into Flying
    # makes Fighting only 0.5x, so damage must drop by a factor of ~4.
    move = {"name": "Close Combat", "type": "Fighting", "category": "Physical", "power": 120, "accuracy": 100, "pp": 8, "effect": None}
    attacker = _make_combatant(_NEUTRAL_STATS, types=["Fighting"])
    defender_base = _make_combatant(_NEUTRAL_STATS, types=["Rock"], tera_type=None)
    defender_tera = _make_combatant(_NEUTRAL_STATS, types=["Rock"], tera_type="Flying")

    base = calculate_damage(move, attacker, defender_base, _BASE_CONTEXT)
    tera = calculate_damage(move, attacker, defender_tera, _BASE_CONTEXT)

    assert base.max_damage > tera.max_damage
    # base_damage = floor(floor(floor(22)*120*120/120)/50)+2 = floor(2640/50)+2 = 52+2 = 54
    # base (2x), max roll: 54 -> 54 -> 54 -> poke_round(54*1.5)=81 -> floor(81*2.0)=162
    # tera (0.5x), max roll: 54 -> 54 -> 54 -> poke_round(81.0)=81 -> floor(81*0.5)=40
    assert base.max_damage == 162
    assert tera.max_damage == 40


def test_defender_tera_type_can_create_an_immunity():
    # Rock defender is weak to Fighting; Tera Ghost makes it outright immune.
    move = {"name": "Close Combat", "type": "Fighting", "category": "Physical", "power": 120, "accuracy": 100, "pp": 8, "effect": None}
    attacker = _make_combatant(_NEUTRAL_STATS, types=["Fighting"])
    defender = _make_combatant(_NEUTRAL_STATS, types=["Rock"], tera_type="Ghost")

    result = calculate_damage(move, attacker, defender, _BASE_CONTEXT)

    assert result.min_damage == 0
    assert result.max_damage == 0


def test_status_move_deals_zero_damage():
    move = {"name": "Protect", "type": "Normal", "category": "Status", "power": None, "accuracy": 100, "pp": 10, "effect": "Protects the user this turn."}
    attacker = _make_combatant(_NEUTRAL_STATS, types=["Normal"])
    defender = _make_combatant(_NEUTRAL_STATS, types=["Water"])

    result = calculate_damage(move, attacker, defender, _BASE_CONTEXT)

    assert result.min_damage == 0
    assert result.max_damage == 0
    assert result.min_percent == 0.0
    assert result.max_percent == 0.0
    assert result.is_ko_chance is False


def test_zero_power_damaging_move_deals_zero_damage():
    move = {"name": "Weird Move", "type": "Normal", "category": "Physical", "power": 0, "accuracy": 100, "pp": 10, "effect": None}
    attacker = _make_combatant(_NEUTRAL_STATS, types=["Normal"])
    defender = _make_combatant(_NEUTRAL_STATS, types=["Water"])

    result = calculate_damage(move, attacker, defender, _BASE_CONTEXT)

    assert result.min_damage == 0
    assert result.max_damage == 0


def test_ko_chance_true_when_max_damage_exceeds_remaining_hp():
    move = {"name": "Close Combat", "type": "Fighting", "category": "Physical", "power": 120, "accuracy": 100, "pp": 8, "effect": None}
    stats = {"hp": 100, "attack": 100, "defense": 100, "sp_attack": 100, "sp_defense": 100, "speed": 100}
    attacker = _make_combatant(stats, types=["Fighting"])
    defender = _make_combatant(stats, types=["Rock"])
    defender["current_hp_fraction"] = 0.1

    result = calculate_damage(move, attacker, defender, _BASE_CONTEXT)
    assert result.is_ko_chance is True


def test_life_orb_boosts_damage():
    move = {"name": "Tackle", "type": "Normal", "category": "Physical", "power": 40, "accuracy": 100, "pp": 35, "effect": None}
    attacker_no_item = _make_combatant(_NEUTRAL_STATS, types=["Normal"])
    attacker_life_orb = _make_combatant(_NEUTRAL_STATS, types=["Normal"], item="Life Orb")
    defender = _make_combatant(_NEUTRAL_STATS, types=["Water"])

    no_item = calculate_damage(move, attacker_no_item, defender, _BASE_CONTEXT)
    life_orb = calculate_damage(move, attacker_life_orb, defender, _BASE_CONTEXT)

    assert life_orb.max_damage > no_item.max_damage


def test_choice_band_boosts_physical_damage():
    move = {"name": "Tackle", "type": "Normal", "category": "Physical", "power": 40, "accuracy": 100, "pp": 35, "effect": None}
    attacker_no_item = _make_combatant(_NEUTRAL_STATS, types=["Normal"])
    attacker_choice_band = _make_combatant(_NEUTRAL_STATS, types=["Normal"], item="Choice Band")
    defender = _make_combatant(_NEUTRAL_STATS, types=["Water"])

    no_item = calculate_damage(move, attacker_no_item, defender, _BASE_CONTEXT)
    choice_band = calculate_damage(move, attacker_choice_band, defender, _BASE_CONTEXT)

    assert choice_band.max_damage > no_item.max_damage


def test_choice_specs_does_not_affect_physical_damage():
    move = {"name": "Tackle", "type": "Normal", "category": "Physical", "power": 40, "accuracy": 100, "pp": 35, "effect": None}
    attacker_no_item = _make_combatant(_NEUTRAL_STATS, types=["Normal"])
    attacker_choice_specs = _make_combatant(_NEUTRAL_STATS, types=["Normal"], item="Choice Specs")
    defender = _make_combatant(_NEUTRAL_STATS, types=["Water"])

    no_item = calculate_damage(move, attacker_no_item, defender, _BASE_CONTEXT)
    choice_specs = calculate_damage(move, attacker_choice_specs, defender, _BASE_CONTEXT)

    assert choice_specs.max_damage == no_item.max_damage


def test_expert_belt_boosts_only_super_effective_damage():
    super_effective_move = {"name": "Close Combat", "type": "Fighting", "category": "Physical", "power": 120, "accuracy": 100, "pp": 8, "effect": None}
    neutral_move = {"name": "Tackle", "type": "Normal", "category": "Physical", "power": 40, "accuracy": 100, "pp": 35, "effect": None}
    attacker_no_item = _make_combatant(_NEUTRAL_STATS, types=["Fighting"])
    attacker_expert_belt = _make_combatant(_NEUTRAL_STATS, types=["Fighting"], item="Expert Belt")
    defender = _make_combatant(_NEUTRAL_STATS, types=["Rock"])

    no_item = calculate_damage(super_effective_move, attacker_no_item, defender, _BASE_CONTEXT)
    expert_belt = calculate_damage(super_effective_move, attacker_expert_belt, defender, _BASE_CONTEXT)
    assert expert_belt.max_damage > no_item.max_damage

    no_item_neutral = calculate_damage(neutral_move, attacker_no_item, defender, _BASE_CONTEXT)
    expert_belt_neutral = calculate_damage(neutral_move, attacker_expert_belt, defender, _BASE_CONTEXT)
    assert expert_belt_neutral.max_damage == no_item_neutral.max_damage


def test_assault_vest_reduces_special_damage_taken():
    move = {"name": "Ember", "type": "Fire", "category": "Special", "power": 40, "accuracy": 100, "pp": 25, "effect": None}
    attacker = _make_combatant(_NEUTRAL_STATS, types=["Fire"])
    defender_no_item = _make_combatant(_NEUTRAL_STATS, types=["Normal"])
    defender_assault_vest = _make_combatant(_NEUTRAL_STATS, types=["Normal"], item="Assault Vest")

    no_item = calculate_damage(move, attacker, defender_no_item, _BASE_CONTEXT)
    assault_vest = calculate_damage(move, attacker, defender_assault_vest, _BASE_CONTEXT)

    assert assault_vest.max_damage < no_item.max_damage


def test_matching_type_gem_boosts_damage():
    move = {"name": "Surf", "type": "Water", "category": "Special", "power": 90, "accuracy": 100, "pp": 15, "effect": None}
    attacker_no_item = _make_combatant(_NEUTRAL_STATS, types=["Water"])
    attacker_gem = _make_combatant(_NEUTRAL_STATS, types=["Water"], item="Water Gem")
    defender = _make_combatant(_NEUTRAL_STATS, types=["Normal"])

    no_item = calculate_damage(move, attacker_no_item, defender, _BASE_CONTEXT)
    gem = calculate_damage(move, attacker_gem, defender, _BASE_CONTEXT)

    assert gem.max_damage > no_item.max_damage


def test_mismatched_type_gem_does_not_boost_damage():
    move = {"name": "Surf", "type": "Water", "category": "Special", "power": 90, "accuracy": 100, "pp": 15, "effect": None}
    attacker_no_item = _make_combatant(_NEUTRAL_STATS, types=["Water"])
    attacker_gem = _make_combatant(_NEUTRAL_STATS, types=["Water"], item="Fire Gem")
    defender = _make_combatant(_NEUTRAL_STATS, types=["Normal"])

    no_item = calculate_damage(move, attacker_no_item, defender, _BASE_CONTEXT)
    gem = calculate_damage(move, attacker_gem, defender, _BASE_CONTEXT)

    assert gem.max_damage == no_item.max_damage


def test_matching_type_plate_boosts_damage():
    move = {"name": "Surf", "type": "Water", "category": "Special", "power": 90, "accuracy": 100, "pp": 15, "effect": None}
    attacker_no_item = _make_combatant(_NEUTRAL_STATS, types=["Water"])
    attacker_plate = _make_combatant(_NEUTRAL_STATS, types=["Water"], item="Splash Plate")
    defender = _make_combatant(_NEUTRAL_STATS, types=["Normal"])

    no_item = calculate_damage(move, attacker_no_item, defender, _BASE_CONTEXT)
    plate = calculate_damage(move, attacker_plate, defender, _BASE_CONTEXT)

    assert plate.max_damage > no_item.max_damage


def test_muscle_band_boosts_physical_but_not_special_damage():
    physical_move = {"name": "Tackle", "type": "Normal", "category": "Physical", "power": 40, "accuracy": 100, "pp": 35, "effect": None}
    special_move = {"name": "Ember", "type": "Fire", "category": "Special", "power": 40, "accuracy": 100, "pp": 25, "effect": None}
    attacker_no_item = _make_combatant(_NEUTRAL_STATS, types=["Normal"])
    attacker_muscle_band = _make_combatant(_NEUTRAL_STATS, types=["Normal"], item="Muscle Band")
    defender = _make_combatant(_NEUTRAL_STATS, types=["Water"])

    no_item = calculate_damage(physical_move, attacker_no_item, defender, _BASE_CONTEXT)
    muscle_band = calculate_damage(physical_move, attacker_muscle_band, defender, _BASE_CONTEXT)
    assert muscle_band.max_damage > no_item.max_damage

    no_item_special = calculate_damage(special_move, attacker_no_item, defender, _BASE_CONTEXT)
    muscle_band_special = calculate_damage(special_move, attacker_muscle_band, defender, _BASE_CONTEXT)
    assert muscle_band_special.max_damage == no_item_special.max_damage


def test_wise_glasses_boosts_special_but_not_physical_damage():
    physical_move = {"name": "Tackle", "type": "Normal", "category": "Physical", "power": 40, "accuracy": 100, "pp": 35, "effect": None}
    special_move = {"name": "Ember", "type": "Fire", "category": "Special", "power": 40, "accuracy": 100, "pp": 25, "effect": None}
    attacker_no_item = _make_combatant(_NEUTRAL_STATS, types=["Fire"])
    attacker_wise_glasses = _make_combatant(_NEUTRAL_STATS, types=["Fire"], item="Wise Glasses")
    defender = _make_combatant(_NEUTRAL_STATS, types=["Water"])

    no_item_special = calculate_damage(special_move, attacker_no_item, defender, _BASE_CONTEXT)
    wise_glasses_special = calculate_damage(special_move, attacker_wise_glasses, defender, _BASE_CONTEXT)
    assert wise_glasses_special.max_damage > no_item_special.max_damage

    no_item_physical = calculate_damage(physical_move, attacker_no_item, defender, _BASE_CONTEXT)
    wise_glasses_physical = calculate_damage(physical_move, attacker_wise_glasses, defender, _BASE_CONTEXT)
    assert wise_glasses_physical.max_damage == no_item_physical.max_damage


def test_matching_resist_berry_reduces_super_effective_damage():
    move = {"name": "Ember", "type": "Fire", "category": "Special", "power": 40, "accuracy": 100, "pp": 25, "effect": None}
    attacker = _make_combatant(_NEUTRAL_STATS, types=["Fire"])
    defender_no_item = _make_combatant(_NEUTRAL_STATS, types=["Grass"])
    defender_resist_berry = _make_combatant(_NEUTRAL_STATS, types=["Grass"], item="Occa Berry")

    no_item = calculate_damage(move, attacker, defender_no_item, _BASE_CONTEXT)
    resist_berry = calculate_damage(move, attacker, defender_resist_berry, _BASE_CONTEXT)

    assert resist_berry.max_damage < no_item.max_damage


def test_mismatched_resist_berry_does_not_reduce_damage():
    move = {"name": "Ember", "type": "Fire", "category": "Special", "power": 40, "accuracy": 100, "pp": 25, "effect": None}
    attacker = _make_combatant(_NEUTRAL_STATS, types=["Fire"])
    defender_no_item = _make_combatant(_NEUTRAL_STATS, types=["Grass"])
    defender_resist_berry = _make_combatant(_NEUTRAL_STATS, types=["Grass"], item="Wacan Berry")

    no_item = calculate_damage(move, attacker, defender_no_item, _BASE_CONTEXT)
    resist_berry = calculate_damage(move, attacker, defender_resist_berry, _BASE_CONTEXT)

    assert resist_berry.max_damage == no_item.max_damage


def test_chilan_berry_reduces_normal_type_damage_without_needing_super_effective():
    # Normal-type moves are never super-effective against anything, so Chilan
    # Berry is the one resist berry that applies unconditionally on a type match.
    move = {"name": "Tackle", "type": "Normal", "category": "Physical", "power": 40, "accuracy": 100, "pp": 35, "effect": None}
    attacker = _make_combatant(_NEUTRAL_STATS, types=["Normal"])
    defender_no_item = _make_combatant(_NEUTRAL_STATS, types=["Water"])
    defender_chilan_berry = _make_combatant(_NEUTRAL_STATS, types=["Water"], item="Chilan Berry")

    no_item = calculate_damage(move, attacker, defender_no_item, _BASE_CONTEXT)
    chilan_berry = calculate_damage(move, attacker, defender_chilan_berry, _BASE_CONTEXT)

    assert chilan_berry.max_damage < no_item.max_damage
