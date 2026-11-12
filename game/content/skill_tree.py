"""Skill levels (pure; no pygame): which skills a hero has at a given character level, and how strong they are.

Every skill has up to 3 levels. All per-level strengths (damage a / b, buff bonuses, heal and shield amounts, other
effect strengths) are written on the Ability in content/heroes.py (a_levels / b_levels / effect_levels). Ranges never
change, except the Wizard's Frostbolt and Fire Blast (200 / 230 / 260).

A character starts (level 1) with its at-will attack (Q) at skill level 1. Then, every 2 character levels (2, 4, 6, ...),
it automatically gets the next step of its class' schedule: a new skill at skill level 1, or the next level of a skill
it already has. The schedule is a fixed list per class, so a hero's skills are a pure function of its character level
(nothing extra to save, companions and joined players get the right skills too).
"""

LEVEL_STEP = 2   # a new skill or skill level every this many character levels

# One entry per step: the ability key that gets a new level. The first entry is the starting skill.
SKILL_SCHEDULE = {
    # Fighter: Q Strike, R Charge, F Heroic Strike, E Demoralizing Shout, G Cleave (unlocks at L8, after Charge+Shout)
    #           L1   L2   L4   L6   L8   L10  L12  L14  L16  L18  L20  L22  L24  L26  L28
    "Fighter": ["Q", "R", "F", "E", "G", "Q", "F", "R", "E", "G", "Q", "F", "R", "E", "G"],
    "Cleric":  ["Q", "R", "Q", "E", "R", "Q", "E", "R", "E"],
    #           L1   L2   L4   L6   L8   L10  L12  L14  L16  L18  L20  L22
    "Paladin": ["Q", "R", "E", "Q", "F", "R", "E", "Q", "F", "R", "E", "F"],
    #           L1   L2   L4   L6   L8   L10  L12  L14  L16  L18  L20  L22
    # Poison Dagger (F) comes first: it is the Rogue's in-combat damage. Stealth + Ambush only open a fight.
    # Stealth levels make sneaking faster (50 / 60 / 70% speed) but cost more mana per second.
    "Rogue":   ["Q", "F", "R", "E", "Q", "F", "E", "R", "Q", "F", "E", "R"],
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
# Every per-level number lives on the Ability (a_levels / b_levels / effect_levels in content/heroes.py); these
# helpers only say how each skill uses them.


def wall_shield(hero, ab) -> float:
    """Wall: b = damage absorbed."""
    return ab.flat_bonus


def renew_total(hero, ab) -> float:
    """Renew: b = total HP healed over its duration."""
    return ab.flat_bonus


def holy_light_heal(ab) -> float:
    """Holy Light: b = HP healed."""
    return ab.flat_bonus


def seal_bonus(ab) -> float:
    """Extra Smite "a" (x weapon damage) while Righteous Seal (this ability) is active: the Seal's own a."""
    return ab.multiplier


def smite_damage(hero, ab) -> float:
    """Smite: (a + Seal bonus) x weapon damage + b."""
    bonus = hero.buffs.get("Righteous Seal", {}).get("bonus", 0.0)
    return (ab.multiplier + bonus) * hero.base_damage + ab.flat_bonus


def shout_damage_mult(ab) -> float:
    """Multiplier on the damage of enemies hit by Demoralizing Shout (0.9 / 0.8 / 0.7 by skill level)."""
    return ab.effect_value


def shout_reduction(ab) -> float:
    """Share of enemy damage Demoralizing Shout removes (0.1 / 0.2 / 0.3 by skill level)."""
    return 1.0 - shout_damage_mult(ab)


def judgement_seal_bonus(hero, ab) -> float:
    """Extra damage when Judgement (ab) consumes the Righteous Seal: its effect value (0.5) x weapon damage."""
    return ab.effect_value * hero.base_damage


POISON_DAGGER_SECS = 5.0      # how long the poison from one Poison Dagger Stab lasts
POISON_DAGGER_WINDOW = 10.0   # seconds the buff waits for the next Stab


def poison_total(ab) -> float:
    """Poison Dagger: b = total poison damage (ignores armor), dealt evenly over POISON_DAGGER_SECS."""
    return ab.flat_bonus


def poison_dps(ab) -> float:
    """Poison damage per second of one Poison Dagger Stab."""
    return poison_total(ab) / POISON_DAGGER_SECS


def stealth_speed(ab) -> float:
    """Stealth: move speed while stealthed, share of normal (effect_levels: 0.5 / 0.6 / 0.7)."""
    return ab.effect_value


def stealth_upkeep(ab) -> float:
    """Stealth: b = mana per second while stealthed (on top of the cost to enter it)."""
    return ab.flat_bonus


# --- what a skill does, in the player's words (shown in the unlock / upgrade popup) -------------------------------

def _dmg(hero, ab):
    return ab.calc_damage(hero.base_damage)


_DESCRIPTIONS = {
    "Strike": lambda h, a: f"Melee attack for {_dmg(h, a):.0f} damage. Use it at will.",
    "Heroic Strike": lambda h, a: f"Your next Strike or Cleave deals +{a.flat_bonus:g} damage to its target and "
                                  f"makes {a.threat_mult * 100:.0f}% threat. {a.cooldown:g}s cooldown.",
    "Cleave": lambda h, a: f"Hits your target and the nearest enemies next to you ({a.max_targets} in total) for "
                           f"{_dmg(h, a):.0f} damage each. {a.cooldown:g}s cooldown.",
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
    "Righteous Seal": lambda h, a: f"Your Smite deals +{seal_bonus(a) * h.base_damage:.0f} damage "
                                   f"(+{seal_bonus(a) * 100:.0f}% of your weapon) for 10s. Judgement consumes the "
                                   f"Seal. {a.cooldown:g}s cooldown.",
    "Judgement": lambda h, a: f"Holy bolt for {_dmg(h, a):.0f} damage up to {a.range:.0f} px away, "
                              f"+{judgement_seal_bonus(h, a):.0f} if it consumes your Seal. {a.cooldown:g}s cooldown.",
    "Holy Light": lambda h, a: f"Channel for 2s (you cannot move) to heal you or an ally within 300 px for "
                               f"{holy_light_heal(a):.0f}. {a.cooldown:g}s cooldown.",
    "Stab": lambda h, a: f"Fast melee strike for {_dmg(h, a):.0f} damage.",
    "Stealth": lambda h, a: f"Out of combat only: become invisible and move at {stealth_speed(a) * 100:.0f}% speed. "
                            f"Costs {stealth_upkeep(a):g} mana per second while active; press again to cancel (free). "
                            f"Your next attack breaks it. Opens a fight with Ambush.",
    "Poison Dagger": lambda h, a: f"Your next Stab poisons its target for {poison_total(a):g} damage over "
                                  f"{POISON_DAGGER_SECS:g}s (ignores armor). {a.cooldown:g}s cooldown.",
    "Ambush": lambda h, a: f"From stealth, strike for {_dmg(h, a):.0f} damage.",
    "Frostbolt": lambda h, a: f"Channeled bolt for {_dmg(h, a):.0f} damage up to {a.range:.0f} px away; slows the "
                              f"target. You cannot move while channeling.",
    "Fire Blast": lambda h, a: f"Instant fire bolt for {_dmg(h, a):.0f} damage up to {a.range:.0f} px away. "
                               f"{a.cooldown:g}s cooldown.",
    "Frost Nova": lambda h, a: f"Freezes every enemy within {a.radius:.0f} px for 4s and deals {_dmg(h, a):.0f} "
                               f"damage. {a.cooldown:g}s cooldown.",
}


def describe(hero, ab) -> str:
    """What the skill does at its current level, with real numbers (and its mana cost)."""
    fn = _DESCRIPTIONS.get(ab.name)
    text = fn(hero, ab) if fn else ab.effect
    return f"{text} Costs {ab.mana_cost:g} mana." if ab.mana_cost else text
