"""Skill levels (pure; no pygame): which skills a hero has at a given character level, and how strong they are.

Every skill has up to 3 levels. Level 3 is the full-strength skill written in content/heroes.py; level 1 deals/heals
33% of that and level 2 deals/heals 67% (Ability.power). Ranges never change, except the Wizard's Frostbolt and Fire
Blast (200 / 230 / 260).

A character starts (level 1) with its at-will attack (Q) at skill level 1. Then, every 2 character levels (2, 4, 6, ...),
it automatically gets the next step of its class' schedule: a new skill at skill level 1, or the next level of a skill
it already has. The schedule is a fixed list per class, so a hero's skills are a pure function of its character level
(nothing extra to save, companions and joined players get the right skills too).
"""

LEVEL_STEP = 2   # a new skill or skill level every this many character levels

# One entry per step: the ability key that gets a new level. The first entry is the starting skill.
SKILL_SCHEDULE = {
    #           L1   L2   L4   L6   L8   L10  L12  L14  L16
    "Fighter": ["Q", "R", "Q", "E", "R", "Q", "E", "R", "E"],
    "Cleric":  ["Q", "R", "Q", "E", "R", "Q", "E", "R", "E"],
    #           L1   L2   L4   L6   L8   L10  L12  L14  L16  L18  L20  L22
    "Paladin": ["Q", "R", "E", "Q", "F", "R", "E", "Q", "F", "R", "E", "F"],
    #           L1   L2   L4   L6   L8   L10  L12     (Stealth has a single level)
    "Rogue":   ["Q", "R", "E", "Q", "E", "Q", "E"],
    #           L1   L2   L4   L6   L8   L10  L12  L14  L16
    "Wizard":  ["Q", "R", "E", "Q", "R", "E", "Q", "R", "E"],
}


def unlock_level(step: int) -> int:
    """Character level at which schedule step `step` (0 = the starting skill) happens."""
    return 1 if step == 0 else LEVEL_STEP * step


def skill_levels(class_name: str, hero_level: int) -> dict:
    """{ability key: skill level} for a hero of this class and character level (locked skills are absent)."""
    levels = {}
    for step, key in enumerate(SKILL_SCHEDULE.get(class_name, ())):
        if unlock_level(step) <= hero_level:
            levels[key] = levels.get(key, 0) + 1
    return levels


def apply_skill_levels(hero) -> list:
    """Give `hero` the skills and skill levels of its current character level. Locked skills are removed from
    hero.abilities (so the UI, the AI and the cast code never see them); existing Ability objects are kept, so
    cooldowns survive a level-up. Returns the changes since the last call: [(key, new_level, is_new), ...]."""
    if hero.all_abilities is None:
        hero.all_abilities = dict(hero.abilities)          # the factory builds every skill at full strength
    if hero.class_name not in SKILL_SCHEDULE:
        return []
    old = hero.skill_levels or {}
    new = skill_levels(hero.class_name, hero.level)
    abilities = {}
    for key, ab in hero.all_abilities.items():              # canonical order: Q, R, E, F
        if key in new:
            abilities[key] = ab
            ab.set_level(new[key])
    hero.abilities = abilities
    hero.skill_levels = new
    # a Wizard's weapon range follows its bolt range (200 / 230 / 260 by Frostbolt level)
    q = abilities.get("Q")
    if q is not None and q.range_levels:
        hero.attack_range = q.range
    return [(key, lvl, key not in old) for key, lvl in new.items() if old.get(key, 0) != lvl]


# --- effect strengths shared by the cast code and the descriptions -----------------------------------------------

BASE_SEAL_BONUS = 0.25          # Righteous Seal: Smite +25% (level 3)
# Demoralizing Shout: enemies deal 90% / 80% / 70% of their damage at skill level 1 / 2 / 3 (user-tuned: the old flat
# 50% made boss fights too easy), so it does not follow the usual 33/67/100% power curve.
SHOUT_DAMAGE_MULT = {1: 0.9, 2: 0.8, 3: 0.7}
BASE_HOLY_LIGHT_HEAL = 150      # Holy Light (level 3)


def wall_shield(hero, ab) -> float:
    return hero.surge_value * ab.power


def renew_total(hero, ab) -> float:
    return hero.surge_value * 0.5 * ab.power


def holy_light_heal(ab) -> float:
    return BASE_HOLY_LIGHT_HEAL * ab.power


def seal_bonus(ab) -> float:
    return BASE_SEAL_BONUS * ab.power


def shout_reduction(ab) -> float:
    """Share of enemy damage Demoralizing Shout removes (0.1 / 0.2 / 0.3 by skill level)."""
    return 1.0 - SHOUT_DAMAGE_MULT[ab.level]


def judgement_seal_bonus(hero, ab) -> float:
    """Extra damage when Judgement consumes the Righteous Seal (one weapon hit at level 3)."""
    return hero.base_damage * ab.power


# --- what a skill does, in the player's words (shown in the unlock / upgrade popup) -------------------------------

def _dmg(hero, ab):
    return ab.calc_damage(hero.base_damage)


_DESCRIPTIONS = {
    "Reaping Strike": lambda h, a: f"Sweeps every enemy within {a.radius:.0f} px for {_dmg(h, a):.0f} damage. "
                                   f"Use it at will.",
    "Charge": lambda h, a: f"Dash to an enemy up to {a.range:.0f} px away: {_dmg(h, a):.0f} damage and a "
                           f"{a.stun_duration:g}s stun. {a.cooldown:g}s cooldown.",
    "Demoralizing Shout": lambda h, a: f"Enemies within {a.radius:.0f} px deal {shout_reduction(a) * 100:.0f}% less "
                                       f"damage for 10s and move at half speed for 3s. {a.cooldown:g}s cooldown.",
    "Wanding": lambda h, a: f"Ranged bolt for {_dmg(h, a):.0f} damage, up to {a.range:.0f} px away.",
    "Wall": lambda h, a: f"Shields you or an ally within 300 px: absorbs {wall_shield(h, a):.0f} damage for 15s. "
                         f"{a.cooldown:g}s cooldown.",
    "Renew": lambda h, a: f"Heals you or an ally within 300 px for {renew_total(h, a):.0f} over 8s. "
                          f"{a.cooldown:g}s cooldown.",
    "Smite": lambda h, a: f"Melee holy strike for {_dmg(h, a):.0f} damage. Stronger while Righteous Seal is active.",
    "Righteous Seal": lambda h, a: f"Your Smite deals +{seal_bonus(a) * 100:.0f}% for 10s. Judgement consumes the "
                                   f"Seal. {a.cooldown:g}s cooldown.",
    "Judgement": lambda h, a: f"Holy bolt for {_dmg(h, a):.0f} damage up to {a.range:.0f} px away, "
                              f"+{judgement_seal_bonus(h, a):.0f} if it consumes your Seal. {a.cooldown:g}s cooldown.",
    "Holy Light": lambda h, a: f"Channel for 2s (you cannot move) to heal you or an ally within 300 px for "
                               f"{holy_light_heal(a):.0f}. {a.cooldown:g}s cooldown.",
    "Stab": lambda h, a: f"Fast melee strike for {_dmg(h, a):.0f} damage.",
    "Stealth": lambda h, a: "Become invisible: monsters lose you, you move at 60% speed, and your next attack "
                            "breaks it. Opens Ambush.",
    "Ambush": lambda h, a: f"From stealth, strike for {_dmg(h, a):.0f} damage.",
    "Frostbolt": lambda h, a: f"Channeled bolt for {_dmg(h, a):.0f} damage up to {a.range:.0f} px away; slows the "
                              f"target. You cannot move while channeling.",
    "Fire Blast": lambda h, a: f"Instant fire bolt for {_dmg(h, a):.0f} damage up to {a.range:.0f} px away. "
                               f"{a.cooldown:g}s cooldown.",
    "Frost Nova": lambda h, a: f"Freezes every enemy within {a.radius:.0f} px for 4s and deals {_dmg(h, a):.0f} "
                               f"damage. {a.cooldown:g}s cooldown.",
}


def describe(hero, ab) -> str:
    """What the skill does at its current level, with real numbers."""
    fn = _DESCRIPTIONS.get(ab.name)
    return fn(hero, ab) if fn else ab.effect
