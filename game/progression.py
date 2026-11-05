"""
Character progression rules: XP curve and per-class stat growth.

Pure logic (no pygame) so it can be shared by the player, AI companions and tests.
"""

from game.content.skill_tree import apply_skill_levels

MAX_LEVEL = 30
XP_BASE = 100  # XP needed for level 2 (see XP_TABLE)

# Hero max HP: (level 1, level 30) per class, linear in between. Level 30 keeps the old values; level 1 was lowered
# from 300-400 so early fights against level-scaled monsters stay dangerous.
HERO_HP = {
    "Fighter": (120, 1270),
    "Cleric":  (120, 1125),
    "Paladin": (120, 1212),
    "Rogue":   (120, 980),
    "Wizard":  (100, 822),
}


def hero_max_hp(class_name, level):
    """Max HP of a hero of this class at this level (rounded to whole HP)."""
    lo, hi = HERO_HP[class_name]
    level = max(1, min(MAX_LEVEL, level))
    return int(round(lo + (hi - lo) * (level - 1) / (MAX_LEVEL - 1)))


# Weapon damage growth per level (raw points added to base_damage). "hp" is the average HP gain per level of the
# HERO_HP line (kept for callers that show it).
GROWTH_RATES = {
    "Fighter":  {"hp": 30, "damage": 4.0},    # weapon damage 10 at level 1 (content/heroes.py) -> 126 at 30
    "Cleric":   {"hp": 25, "damage": 3.0},    # 8 -> 95
    "Paladin":  {"hp": 28, "damage": 4.5},    # 12 -> 142.5
    "Rogue":    {"hp": 20, "damage": 1.3},    # 4 -> 41.7 (0.5 s swings)
    "Wizard":   {"hp": 18, "damage": 3.3},    # 9 -> 104.7
}
DEFAULT_GROWTH = {"hp": 25, "damage": 2.5}


def growth_for(class_name):
    g = dict(GROWTH_RATES.get(class_name, DEFAULT_GROWTH))
    if class_name in HERO_HP:
        lo, hi = HERO_HP[class_name]
        g["hp"] = (hi - lo) / (MAX_LEVEL - 1)
    return g


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
    """Add `levels` levels worth of weapon-damage growth and set max HP for hero.level (call AFTER raising
    hero.level). Full-heals."""
    growth = growth_for(hero.class_name)
    hero.base_damage += growth["damage"] * levels
    if hero.class_name in HERO_HP:
        hero.max_hp = hero_max_hp(hero.class_name, hero.level)
    else:
        hero.max_hp += growth["hp"] * levels
    hero.hp = hero.max_hp


def set_hero_level(hero, level):
    """Bring a freshly-created level-1 hero up to `level` (used for loading saves and companions)."""
    level = max(1, min(MAX_LEVEL, int(level)))
    hero.level = level
    apply_level_growth(hero, level - 1)
    apply_skill_levels(hero)   # skills and skill levels follow the character level (see content/skill_tree.py)
