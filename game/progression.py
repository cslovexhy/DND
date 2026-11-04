"""
Character progression rules: XP curve and per-class stat growth.

Pure logic (no pygame) so it can be shared by the player, AI companions and tests.
"""

from game.content.skill_tree import apply_skill_levels

MAX_LEVEL = 30
XP_BASE = 100  # XP needed for level 2 (see XP_TABLE)

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


# XP to go from level L to L+1: 100 for 1->2; after that each level costs the previous one plus
# max(5%, 50% - L x 2%)  (L = the level you are leveling from: +46% at 2, +30% at 10, +10% at 20, 5% from 23 on).
def xp_growth(level):
    return max(0.05, 0.50 - 0.02 * level)


def _build_xp_table():
    table, cost = {1: XP_BASE}, float(XP_BASE)
    for level in range(2, MAX_LEVEL):
        cost *= 1.0 + xp_growth(level)
        table[level] = int(round(cost))
    return table


XP_TABLE = _build_xp_table()   # level -> XP needed to reach level + 1


def xp_to_next_level(level):
    """XP needed from current level to reach the next."""
    return XP_TABLE.get(level, XP_TABLE[MAX_LEVEL - 1])


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
    apply_skill_levels(hero)   # skills and skill levels follow the character level (see content/skill_tree.py)
