from damage_calc.data.stat_stages import get_stage_multiplier
from damage_calc.data.natures import get_nature_modifiers
from damage_calc.data.type_chart import get_effectiveness


# Stat stage tests

def test_stage_zero_is_neutral():
    assert get_stage_multiplier(0) == 1.0


def test_positive_stages():
    assert get_stage_multiplier(1) == 1.5
    assert get_stage_multiplier(2) == 2.0
    assert get_stage_multiplier(6) == 4.0


def test_negative_stages():
    assert round(get_stage_multiplier(-1), 4) == round(2 / 3, 4)
    assert get_stage_multiplier(-2) == 0.5
    assert get_stage_multiplier(-6) == 0.25


# Nature tests

def test_adamant_boosts_attack_lowers_sp_attack():
    mods = get_nature_modifiers("Adamant")
    assert mods == {"boosted": "attack", "lowered": "sp_attack"}


def test_neutral_nature_has_no_boost_or_lower():
    mods = get_nature_modifiers("Hardy")
    assert mods == {"boosted": None, "lowered": None}


def test_timid_boosts_speed_lowers_attack():
    mods = get_nature_modifiers("Timid")
    assert mods == {"boosted": "speed", "lowered": "attack"}


# Type chart tests

def test_neutral_matchup():
    assert get_effectiveness("Normal", ["Grass"]) == 1.0


def test_super_effective_single_type():
    assert get_effectiveness("Fire", ["Grass"]) == 2.0


def test_not_very_effective_single_type():
    assert get_effectiveness("Fire", ["Water"]) == 0.5


def test_immune():
    assert get_effectiveness("Normal", ["Ghost"]) == 0.0


def test_dual_type_stacks_multiplicatively():
    # Ice vs Grass/Ice(Abomasnow-like dual): Ice is 2x vs Grass, 0.5x vs Ice -> 1.0
    assert get_effectiveness("Ice", ["Grass", "Ice"]) == 1.0


def test_dual_type_quad_effective():
    # Ice vs Dragon/Flying (e.g. Dragonite): 2x * 2x = 4x
    assert get_effectiveness("Ice", ["Dragon", "Flying"]) == 4.0
