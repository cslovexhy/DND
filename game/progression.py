"""
Character progression rules: XP curve and per-class stat growth.

Pure logic (no pygame) so it can be shared by the player, AI companions and tests.
"""

MAX_LEVEL = 30
XP_BASE = 100  # XP needed for level 2

# Stat growth per level (HP bonus in raw points, damage in raw points added to base_damage)
GROWTH_RATES = {
    "Fighter":  {"hp": 30, "damage": 3.0},
    "Cleric":   {"hp": 25, "damage": 2.0},
    "Paladin":  {"hp": 28, "damage": 2.5},
    "Rogue":    {"hp": 20, "damage": 3.5},
    "Wizard":   {"hp": 18, "damage": 4.0},
}
DEFAULT_GROWTH = {"hp": 25, "damage": 2.5}


def growth_for(class_name):
    return GROWTH_RATES.get(class_name, DEFAULT_GROWTH)


def xp_multiplier(level):
    """Tiered growth: 1.3x early, flattens later."""
    if level <= 10:
        return 1.3
    elif level <= 20:
        return 1.2
    else:
        return 1.1


def xp_to_next_level(level):
    """XP needed from current level to reach the next."""
    return int(XP_BASE * (xp_multiplier(level) ** (level - 1)))


def apply_level_growth(hero, levels=1):
    """Add `levels` levels worth of HP/damage growth to a hero (does not touch hero.level)."""
    growth = growth_for(hero.class_name)
    for _ in range(levels):
        hero.max_hp += growth["hp"]
        hero.base_damage += growth["damage"]
    hero.hp = hero.max_hp


def set_hero_level(hero, level):
    """Bring a freshly-created level-1 hero up to `level` (used for loading saves and companions)."""
    level = max(1, min(MAX_LEVEL, int(level)))
    apply_level_growth(hero, level - 1)
    hero.level = level
