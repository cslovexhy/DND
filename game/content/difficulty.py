"""Map-level "players" difficulty (Diablo II style /players X), pure rules.

At {x}pp every monster has  HP = base HP * x,  deals  damage = base damage * (1 + x) / 2,  and gives
XP = base XP * (1 + x) / 2  (rounded to a whole number; gold is not scaled). 1pp is the normal game.
"""
PP_MIN, PP_MAX, PP_DEFAULT = 1, 8, 1


def clamp_pp(pp):
    """Validated pp value (int 1..8); anything else raises ValueError."""
    if not isinstance(pp, int) or isinstance(pp, bool) or not PP_MIN <= pp <= PP_MAX:
        raise ValueError(f"pp must be an integer {PP_MIN}..{PP_MAX}, got {pp!r}")
    return pp


def hp_multiplier(pp):
    return pp


def damage_multiplier(pp):
    return (1 + pp) / 2


def xp_multiplier(pp):
    return (1 + pp) / 2


def scaled_xp(base_xp, pp):
    """Whole-number XP for a kill at this pp (halves round up: 5 XP at 2pp -> 8)."""
    return int(base_xp * xp_multiplier(pp) + 0.5)


def map_title(map_name, pp):
    """How a map is shown to everyone in the game, e.g. 'Northshire (8pp)'."""
    return f"{map_name} ({pp}pp)"
