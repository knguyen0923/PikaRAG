_NEUTRAL_NATURES = {"Hardy", "Docile", "Serious", "Bashful", "Quirky"}

_NATURE_TABLE = {
    "Lonely": ("attack", "defense"),
    "Adamant": ("attack", "sp_attack"),
    "Naughty": ("attack", "sp_defense"),
    "Brave": ("attack", "speed"),
    "Bold": ("defense", "attack"),
    "Impish": ("defense", "sp_attack"),
    "Lax": ("defense", "sp_defense"),
    "Relaxed": ("defense", "speed"),
    "Modest": ("sp_attack", "attack"),
    "Mild": ("sp_attack", "defense"),
    "Rash": ("sp_attack", "sp_defense"),
    "Quiet": ("sp_attack", "speed"),
    "Calm": ("sp_defense", "attack"),
    "Gentle": ("sp_defense", "defense"),
    "Careful": ("sp_defense", "sp_attack"),
    "Sassy": ("sp_defense", "speed"),
    "Timid": ("speed", "attack"),
    "Hasty": ("speed", "defense"),
    "Jolly": ("speed", "sp_attack"),
    "Naive": ("speed", "sp_defense"),
}


def get_nature_modifiers(nature: str) -> dict:
    if nature in _NEUTRAL_NATURES:
        return {"boosted": None, "lowered": None}
    boosted, lowered = _NATURE_TABLE[nature]
    return {"boosted": boosted, "lowered": lowered}
