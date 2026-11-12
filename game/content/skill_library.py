"""Every skill in the game, defined once (pure; no pygame).

A skill is an Ability built by its factory here. Heroes (content/heroes.py) and monsters (a spawn type's "kit" in
content/monsters.py) get their skills from the same factories, so a skill has the same damage formula
(a x weapon damage + b, per skill level), mana weight and cooldown whoever uses it. What a skill DOES when cast
lives in engine/abilities.py (shared effects) and engine/player.py (hero-only casting); which skills a monster can
actually use, and when, is engine/monster_casting.py.

    make_skill("Poison Dagger")   -> a fresh Ability (each caster needs its own: cooldown and level are per caster)
"""
from game.engine.entities import Ability

# Ability colors by class
FIGHTER_COLOR = (200, 200, 255)
CLERIC_COLOR = (255, 220, 100)
PALADIN_COLOR = (255, 255, 200)
ROGUE_COLOR = (180, 255, 180)

# Wizard bolt range by skill level 1 / 2 / 3 (Frostbolt and Fire Blast)
WIZARD_BOLT_RANGES = (200, 230, 260)

# Mana (Ability.mana_cost): at every character level each class spends the same mana per second when it casts
# every unlocked in-combat skill as soon as it is ready (progression.mana_rate), so a bigger pool lasts longer.
# mana_weight splits that spending over the skills: melee basic attacks are cheap (still usable when out of mana),
# caster basic attacks are dear (casters are punished harder when out of mana). Openers (out of combat only: Rogue
# Stealth + Ambush) cost mana_secs seconds of mana_rate instead. Tuned with tools/mana_bench.py.


# --- Fighter ---------------------------------------------------------------------------------------------------
def strike():
    return Ability("Strike", mana_weight=0.3, cooldown=0, a_levels=(1.0,), b_levels=(1, 2, 3),
                   radius=0, range=70, heroic=True,
                   effect="Basic melee attack (100% weapon dmg + 1/2/3).",
                   power_type="at_will", color=FIGHTER_COLOR)


def charge():
    return Ability("Charge", mana_weight=1.0, cooldown=8.0, a_levels=(1.3, 1.4, 1.5), b_levels=(3, 6, 9),
                   radius=0, range=250,
                   effect="Dash to target (130/140/150% weapon dmg + 3/6/9, stun 1.5s)",
                   power_type="daily", color=(255, 160, 50),
                   is_dash=True, stun_duration=1.5)


def demoralizing_shout():
    return Ability("Demoralizing Shout", mana_weight=1.0, target_kind="self", cooldown=10.0, multiplier=0,
                   flat_bonus=0,
                   effect_levels=(0.9, 0.8, 0.7),   # enemies deal 90/80/70% damage (user-tuned)
                   radius=120, range=0,
                   effect="Reduces nearby enemies damage by 10/20/30% (skill level 1/2/3) for 10s, slows 3s",
                   power_type="encounter", color=(200, 150, 50))


def heroic_strike():
    # no damage of its own; a buff that empowers the next Strike / Cleave hit
    return Ability("Heroic Strike", mana_weight=1.0, target_kind="self", cooldown=4.0, multiplier=0,
                   b_levels=(2, 4, 6), threat_mult=1.5,
                   radius=0, range=0,
                   effect="Next Strike or Cleave: +2/4/6 dmg and 150% threat on that target.",
                   power_type="encounter", color=(255, 120, 60))


def cleave():
    return Ability("Cleave", mana_weight=1.0, cooldown=6.0, a_levels=(0.8,), b_levels=(1, 2, 3),
                   max_targets_levels=(2, 3, 4), radius=70, range=70, heroic=True,
                   effect="Hits the target and the nearest enemies next to you, 2/3/4 in total "
                          "(80% weapon dmg + 1/2/3).",
                   power_type="encounter", color=(220, 220, 255))


# --- Cleric ----------------------------------------------------------------------------------------------------
def wanding():
    return Ability("Wanding", mana_weight=2.0, cooldown=0, a_levels=(1.0,), b_levels=(1, 2, 3),
                   radius=0, range=200,
                   effect="Ranged bolt (100% weapon dmg + 1/2/3). Fires a projectile.",
                   power_type="at_will", color=CLERIC_COLOR)


def wall():
    # b = HP absorbed per skill level
    return Ability("Wall", mana_weight=1.0, target_kind="ally", cooldown=15.0, multiplier=0, b_levels=(66, 134, 200),
                   radius=0, range=0,
                   effect="Absorb shield on self. Absorbs 66/134/200 damage.",
                   power_type="utility", color=(100, 180, 255))


def renew():
    # b = HP healed over 8 s per skill level
    return Ability("Renew", mana_weight=1.0, target_kind="ally", cooldown=16.0, multiplier=0, b_levels=(33, 67, 100),
                   radius=0, range=0,
                   effect="Heal 33/67/100 over 8s.",
                   power_type="utility", color=(100, 255, 150))


# --- Paladin ---------------------------------------------------------------------------------------------------
def smite():
    return Ability("Smite", mana_weight=0.3, cooldown=0, a_levels=(1.0,), b_levels=(1, 2, 3),
                   radius=0, range=75,
                   effect="Melee divine strike (100% weapon dmg + 1/2/3). Boosted by Seal.",
                   power_type="at_will", color=PALADIN_COLOR)


def righteous_seal():
    # no damage of its own; a = what it adds to Smite's a while active (like Heroic Strike's b)
    return Ability("Righteous Seal", mana_weight=1.0, target_kind="self", cooldown=10.0, multiplier=0,
                   a_levels=(0.10, 0.15, 0.20),
                   radius=0, range=0,
                   effect="Buff: Smite +10/15/20% weapon dmg for 10s. Consumed by Judgement.",
                   power_type="utility", color=(255, 220, 80))


def judgement():
    return Ability("Judgement", mana_weight=1.0, cooldown=10.0, a_levels=(1.2, 1.3, 1.4), b_levels=(2, 4, 6),
                   effect_levels=(0.5,),   # extra a (x weapon) when it consumes the Seal
                   radius=0, range=250,
                   effect="Ranged holy bolt (120/130/140% weapon + 2/4/6). Consumes Seal for +50% weapon dmg.",
                   power_type="daily", color=(255, 255, 150))


def holy_light():
    return Ability("Holy Light", mana_weight=1.0, target_kind="ally", cooldown=15.0, multiplier=0,
                   b_levels=(49.5, 100.5, 150),   # HP healed per skill level
                   radius=0, range=0,
                   effect="Channel 2s: heal 49.5/100.5/150 HP. Immobilizes during cast.",
                   power_type="utility", color=(255, 255, 220))


# --- Rogue -----------------------------------------------------------------------------------------------------
def stab():
    return Ability("Stab", mana_weight=0.15, cooldown=0, a_levels=(1.0,), b_levels=(0.5, 1, 1.5),
                   radius=0, range=55,
                   effect="Fast melee strike (100% weapon dmg + 0.5/1/1.5).",
                   power_type="at_will", color=ROGUE_COLOR)


def stealth():
    # opener (out of combat only), priced outside the in-combat budget. 50/60/70% move speed (effect_levels),
    # b = 1/2/3 mana per second while active; press again to cancel.
    return Ability("Stealth", mana_secs=1.0, out_of_combat_only=True, toggle=True, target_kind="self",
                   cooldown=6.0, multiplier=0, b_levels=(1, 2, 3), effect_levels=(0.5, 0.6, 0.7),
                   radius=0, range=0,
                   effect="Out of combat only. Go invisible at 50/60/70% move speed, 1/2/3 mana per "
                          "second. Press again to cancel. Attack breaks stealth.",
                   power_type="utility", color=(100, 180, 100))


def ambush():
    return Ability("Ambush", mana_secs=4.0, cooldown=0, a_levels=(2.5, 2.75, 3.0), b_levels=(2, 4, 6),
                   radius=0, range=55,
                   effect="Stealth only. 250/275/300% weapon dmg + 2/4/6.",
                   power_type="daily", color=(255, 50, 50))


def poison_dagger():
    # no damage of its own; the next melee hit (a Rogue's Stab) poisons the target (b = total poison over 5 s).
    # Cooldown = poison duration, so the poison can be kept up nonstop.
    return Ability("Poison Dagger", mana_weight=1.0, target_kind="self", cooldown=5.0, multiplier=0,
                   b_levels=(15, 30, 45), radius=0, range=0,
                   effect="Next Stab poisons the target: 15/30/45 damage over 5s.",
                   power_type="encounter", color=(120, 220, 80))


# --- Wizard ----------------------------------------------------------------------------------------------------
def frostbolt():
    return Ability("Frostbolt", mana_weight=3.0, cooldown=1.2, a_levels=(1.0,), b_levels=(1, 2, 3),
                   radius=0, range=260,
                   effect="Channeled ranged bolt. Immobile while casting. Slows 25% for 3s.",
                   power_type="at_will", color=(150, 200, 255), range_levels=WIZARD_BOLT_RANGES)


def fire_blast():
    return Ability("Fire Blast", mana_weight=2.0, cooldown=8.0, a_levels=(1.2, 1.3, 1.4), b_levels=(2, 4, 6),
                   radius=0, range=260,
                   effect="Instant ranged fire bolt (120/130/140% weapon dmg + 2/4/6).",
                   power_type="daily", color=(255, 130, 50), range_levels=WIZARD_BOLT_RANGES)


def frost_nova():
    return Ability("Frost Nova", mana_weight=0.3, target_kind="self", cooldown=12.0, a_levels=(0.4,), b_levels=(1, 2, 3),
                   radius=120, range=0,
                   effect="AoE freeze around self. 4s freeze + 40% weapon dmg + 1/2/3.",
                   power_type="daily", color=(180, 220, 255))


SKILLS = {f().name: f for f in (
    strike, charge, demoralizing_shout, heroic_strike, cleave,
    wanding, wall, renew,
    smite, righteous_seal, judgement, holy_light,
    stab, stealth, ambush, poison_dagger,
    frostbolt, fire_blast, frost_nova,
)}


def make_skill(name):
    """A fresh Ability for the skill called `name` (KeyError for an unknown skill)."""
    return SKILLS[name]()
