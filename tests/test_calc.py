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
    # min = floor(26*1.5*0.85) = 33, max = floor(26*1.5) = 39
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
