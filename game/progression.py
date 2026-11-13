"""
Character progression rules: XP curve and per-class stat growth.

Pure logic (no pygame) so it can be shared by the player, AI companions and tests.
"""

from game.content.skill_tree import apply_skill_levels
from game.engine.entities import COMBAT_REGEN_SHARE

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


# Hero max mana: (level 1, level 30) per class, linear in between (user-set).
HERO_MANA = {
    "Fighter": (80, 800),
    "Cleric":  (120, 1500),
    "Paladin": (120, 1300),
    "Rogue":   (100, 1000),
    "Wizard":  (150, 2000),
}


def hero_max_mana(class_name, level):
    """Max mana of a hero of this class at this level (rounded to whole mana; 0 for unknown classes)."""
    if class_name not in HERO_MANA:
        return 0
    lo, hi = HERO_MANA[class_name]
    level = max(1, min(MAX_LEVEL, level))
    return int(round(lo + (hi - lo) * (level - 1) / (MAX_LEVEL - 1)))


# Mana spending (Ability.mana_cost): at every character level, every class casting all its unlocked skills whenever
# they are ready spends the SAME mana per second, mana_rate(level) = the average class pool / MANA_DRAIN_SECS. The
# rate is class-independent, so a bigger pool really lasts longer (Wizard 2000 vs Fighter 800 at level 30).
MANA_DRAIN_SECS = 45.0


def ref_mana(level):
    """Average max mana over the classes at this level (class-independent reference pool)."""
    return sum(hero_max_mana(c, level) for c in HERO_MANA) / len(HERO_MANA)


def mana_rate(level):
    """Mana per second any class spends at this level when it casts every unlocked skill as soon as it is ready."""
    return ref_mana(level) / MANA_DRAIN_SECS


# Hero HP and mana regeneration out of combat, share of max per second, by character level (user-set, linear):
# 2% at level 1 -> 1% at level 10 -> 0.5% at level 30 (and beyond). In combat it is COMBAT_REGEN_SHARE of that.
REGEN_POINTS = ((1, 0.02), (10, 0.01), (30, 0.005))


def regen_rate(level):
    """Out-of-combat HP / mana regeneration (share of max per second) at this character level."""
    (l0, r0), (l1, r1), (l2, r2) = REGEN_POINTS
    if level <= l0:
        return r0
    if level <= l1:
        return r0 + (r1 - r0) * (level - l0) / (l1 - l0)
    if level <= l2:
        return r1 + (r2 - r1) * (level - l1) / (l2 - l1)
    return r2


def apply_regen_rates(hero):
    """Set the hero's HP and mana regeneration for its level (in combat = COMBAT_REGEN_SHARE of out of combat)."""
    ooc = regen_rate(hero.level)
    hero.regen_rate_ooc = hero.mana_regen_ooc = ooc
    hero.regen_rate_combat = hero.mana_regen_combat = ooc * COMBAT_REGEN_SHARE


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
    """Add `levels` levels worth of weapon-damage growth and set max HP and max mana for hero.level (call AFTER
    raising hero.level). Full-heals and refills mana."""
    growth = growth_for(hero.class_name)
    if hasattr(hero, "class_damage"):
        hero.class_damage += growth["damage"] * levels     # the bare class value (gear applies on top)
    else:
        hero.base_damage += growth["damage"] * levels
    base = getattr(hero, "base_max_hp", hero.max_hp)
    if hero.class_name in HERO_HP:
        base = hero_max_hp(hero.class_name, hero.level)
    else:
        base += growth["hp"] * levels
    hero.base_max_hp = base
    hero.max_hp = base
    if hasattr(hero, "refresh_max_hp"):
        hero.refresh_max_hp()             # food buff (+max HP%)
    hero.hp = hero.max_hp
    if hero.class_name in HERO_MANA:
        hero.max_mana = hero_max_mana(hero.class_name, hero.level)
        hero.mana = hero.max_mana
    apply_regen_rates(hero)


def set_hero_level(hero, level):
    """Bring a freshly-created level-1 hero up to `level` (used for loading saves and companions)."""
    level = max(1, min(MAX_LEVEL, int(level)))
    hero.level = level
    apply_level_growth(hero, level - 1)
    apply_skill_levels(hero)   # skills and skill levels follow the character level (see content/skill_tree.py)
