"""
Wrath of Ashardalon hero classes — stats and abilities from card data.

Each class has a factory create_<class>(name, x, y); the player picks a class and a name when
creating a character (see game/saves.py).
"""
from game.engine.entities import Hero, Ability
from game.progression import hero_max_hp, hero_max_mana

# Ability colors by class
FIGHTER_COLOR = (200, 200, 255)
CLERIC_COLOR = (255, 220, 100)
PALADIN_COLOR = (255, 255, 200)
ROGUE_COLOR = (180, 255, 180)
WIZARD_COLOR = (255, 130, 50)

# Wizard bolt range by skill level 1 / 2 / 3 (Frostbolt and Fire Blast)
WIZARD_BOLT_RANGES = (200, 230, 260)

# Mana (Ability.mana_cost): at every character level each class spends the same mana per second when it casts
# every unlocked in-combat skill as soon as it is ready (progression.mana_rate), so a bigger pool lasts longer.
# mana_weight splits that spending over the skills: melee basic attacks are cheap (still usable when out of mana),
# caster basic attacks are dear (casters are punished harder when out of mana). Openers (out of combat only: Rogue
# Stealth + Ambush) cost mana_secs seconds of mana_rate instead. Tuned with tools/mana_bench.py.


def create_fighter(name: str, x: float, y: float) -> Hero:
    """Fighter. 1H Sword + Shield — balanced speed and defense."""
    h = Hero(name, "Fighter", x, y, hp=8, ac=17, speed=5, surge_value=4,
             special_ability="Cast-Iron Stomach: Immune to Poison")
    h.max_hp = h.hp = h.base_max_hp = hero_max_hp("Fighter", 1)   # level-1 HP (progression.HERO_HP)
    h.max_mana = h.mana = hero_max_mana("Fighter", 1)   # level-1 mana (progression.HERO_MANA)
    # Weapon: 1H Sword + Shield — balanced
    h.base_damage = 10   # level-1 weapon damage; + per level in progression.GROWTH_RATES
    h.weapon_speed = 1.6  # 1.6s between swings
    h.attack_range = 60
    # Skills (damage = a x weapon damage + b)
    h.add_ability("Q", Ability("Strike", mana_weight=0.3, cooldown=0, a_levels=(1.0,), b_levels=(1, 2, 3),
                               radius=0, range=70, heroic=True,
                               effect="Basic melee attack (100% weapon dmg + 1/2/3).",
                               power_type="at_will", color=FIGHTER_COLOR))
    h.add_ability("R", Ability("Charge", mana_weight=1.0, cooldown=8.0, a_levels=(1.3, 1.4, 1.5), b_levels=(3, 6, 9),
                               radius=0, range=250,
                               effect="Dash to target (130/140/150% weapon dmg + 3/6/9, stun 1.5s)",
                               power_type="daily", color=(255, 160, 50),
                               is_dash=True, stun_duration=1.5))
    h.add_ability("E", Ability("Demoralizing Shout", mana_weight=1.0, target_kind="self", cooldown=10.0, multiplier=0, flat_bonus=0,
                               effect_levels=(0.9, 0.8, 0.7),   # enemies deal 90/80/70% damage (user-tuned)
                               radius=120, range=0,
                               effect="Reduces nearby enemies damage by 10/20/30% (skill level 1/2/3) for 10s, slows 3s",
                               power_type="encounter", color=(200, 150, 50)))
    # Heroic Strike: no damage of its own; a buff that empowers the next Strike / Cleave hit
    h.add_ability("F", Ability("Heroic Strike", mana_weight=1.0, target_kind="self", cooldown=4.0, multiplier=0, b_levels=(2, 4, 6), threat_mult=1.5,
                               radius=0, range=0,
                               effect="Next Strike or Cleave: +2/4/6 dmg and 150% threat on that target.",
                               power_type="encounter", color=(255, 120, 60)))
    h.add_ability("G", Ability("Cleave", mana_weight=1.0, cooldown=6.0, a_levels=(0.8,), b_levels=(1, 2, 3),
                               max_targets_levels=(2, 3, 4), radius=70, range=70, heroic=True,
                               effect="Hits the target and the nearest enemies next to you, 2/3/4 in total "
                                      "(80% weapon dmg + 1/2/3).",
                               power_type="encounter", color=(220, 220, 255)))
    return h


def create_cleric(name: str, x: float, y: float) -> Hero:
    """Cleric. Ranged healer/support with projectile auto-attack."""
    h = Hero(name, "Cleric", x, y, hp=8, ac=16, speed=5, surge_value=4,
             special_ability="Divine Warding: Protective wards and healing over time")
    h.max_hp = h.hp = h.base_max_hp = hero_max_hp("Cleric", 1)   # level-1 HP (progression.HERO_HP)
    h.max_mana = h.mana = hero_max_mana("Cleric", 1)   # level-1 mana (progression.HERO_MANA)
    # Weapon: Wand — ranged, moderate speed (30 base / 1.2s = 25 dps)
    h.base_damage = 8
    h.weapon_speed = 1.2
    h.attack_range = 200  # Ranged
    # Skills
    h.add_ability("Q", Ability("Wanding", mana_weight=2.0, cooldown=0, a_levels=(1.0,), b_levels=(1, 2, 3),
                               radius=0, range=200,
                               effect="Ranged bolt (100% weapon dmg + 1/2/3). Fires a projectile.",
                               power_type="at_will", color=CLERIC_COLOR))
    # Wall / Renew: b = HP absorbed / healed per skill level
    h.add_ability("R", Ability("Wall", mana_weight=1.0, target_kind="ally", cooldown=15.0, multiplier=0, b_levels=(66, 134, 200),
                               radius=0, range=0,
                               effect="Absorb shield on self. Absorbs 66/134/200 damage.",
                               power_type="utility", color=(100, 180, 255)))
    h.add_ability("E", Ability("Renew", mana_weight=1.0, target_kind="ally", cooldown=16.0, multiplier=0, b_levels=(33, 67, 100),
                               radius=0, range=0,
                               effect="Heal 33/67/100 over 8s.",
                               power_type="utility", color=(100, 255, 150)))
    return h

def create_paladin(name: str, x: float, y: float) -> Hero:
    """Paladin. 2H Mace — Seal/Smite/Judgement holy warrior."""
    h = Hero(name, "Paladin", x, y, hp=8, ac=17, speed=6, surge_value=4,
             special_ability="Seal System: Seals buff Smite and empower Judgement")
    h.max_hp = h.hp = h.base_max_hp = hero_max_hp("Paladin", 1)   # level-1 HP (progression.HERO_HP)
    h.max_mana = h.mana = hero_max_mana("Paladin", 1)   # level-1 mana (progression.HERO_MANA)
    # Weapon: 2H Mace — slow, hard hits
    h.base_damage = 12
    h.weapon_speed = 2.2
    h.attack_range = 60
    # Skills
    h.add_ability("Q", Ability("Smite", mana_weight=0.3, cooldown=0, a_levels=(1.0,), b_levels=(1, 2, 3),
                               radius=0, range=75,
                               effect="Melee divine strike (100% weapon dmg + 1/2/3). Boosted by Seal.",
                               power_type="at_will", color=PALADIN_COLOR))
    # Righteous Seal: no damage of its own; a = what it adds to Smite's a while active (like Heroic Strike's b)
    h.add_ability("R", Ability("Righteous Seal", mana_weight=1.0, target_kind="self", cooldown=10.0, multiplier=0,
                               a_levels=(0.10, 0.15, 0.20),
                               radius=0, range=0,
                               effect="Buff: Smite +10/15/20% weapon dmg for 10s. Consumed by Judgement.",
                               power_type="utility", color=(255, 220, 80)))
    h.add_ability("E", Ability("Judgement", mana_weight=1.0, cooldown=10.0, a_levels=(1.2, 1.3, 1.4), b_levels=(2, 4, 6),
                               effect_levels=(0.5,),   # extra a (x weapon) when it consumes the Seal
                               radius=0, range=250,
                               effect="Ranged holy bolt (120/130/140% weapon + 2/4/6). Consumes Seal for +50% weapon dmg.",
                               power_type="daily", color=(255, 255, 150)))
    h.add_ability("F", Ability("Holy Light", mana_weight=1.0, target_kind="ally", cooldown=15.0, multiplier=0,
                               b_levels=(49.5, 100.5, 150),   # HP healed per skill level
                               radius=0, range=0,
                               effect="Channel 2s: heal 49.5/100.5/150 HP. Immobilizes during cast.",
                               power_type="utility", color=(255, 255, 220)))
    return h

def create_rogue(name: str, x: float, y: float) -> Hero:
    """Rogue. Fast melee assassin with stealth and burst."""
    h = Hero(name, "Rogue", x, y, hp=8, ac=14, speed=6, surge_value=4,
             special_ability="Stealth: Vanish from sight, Ambush from shadows")
    h.max_hp = h.hp = h.base_max_hp = hero_max_hp("Rogue", 1)   # level-1 HP (progression.HERO_HP)
    h.max_mana = h.mana = hero_max_mana("Rogue", 1)   # level-1 mana (progression.HERO_MANA)
    # Weapon: Daggers — very fast (18.75 base / 0.5s = 37.5 dps, 1.5x fighter)
    h.base_damage = 4
    h.weapon_speed = 0.5
    h.attack_range = 50  # Melee
    h.crit_chance = 0.10  # 10% crit (double base)
    # Skills
    h.add_ability("Q", Ability("Stab", mana_weight=0.15, cooldown=0, a_levels=(1.0,), b_levels=(0.5, 1, 1.5),
                               radius=0, range=55,
                               effect="Fast melee strike (100% weapon dmg + 0.5/1/1.5).",
                               power_type="at_will", color=ROGUE_COLOR))
    # Stealth + Ambush open a fight (out of combat only), so they are priced as openers, outside the in-combat budget
    h.add_ability("R", Ability("Stealth", mana_secs=1.0, out_of_combat_only=True, target_kind="self", cooldown=6.0,
                               multiplier=0, flat_bonus=0, radius=0, range=0,
                               effect="Out of combat only. Go invisible. 60% move speed. Mobs can't see you. "
                                      "Attack breaks stealth.",
                               power_type="utility", color=(100, 180, 100), max_level=1))   # nothing to scale
    h.add_ability("E", Ability("Ambush", mana_secs=4.0, cooldown=0, a_levels=(2.5, 2.75, 3.0), b_levels=(2, 4, 6),
                               radius=0, range=55,
                               effect="Stealth only. 250/275/300% weapon dmg + 2/4/6.",
                               power_type="daily", color=(255, 50, 50)))
    # Poison Dagger: no damage of its own; the next Stab poisons its target (b = poison damage per second)
    h.add_ability("F", Ability("Poison Dagger", mana_weight=1.0, target_kind="self", cooldown=8.0, multiplier=0,
                               b_levels=(10, 20, 30), radius=0, range=0,
                               effect="Next Stab poisons the target: 10/20/30 damage per second for 4s.",
                               power_type="encounter", color=(120, 220, 80)))
    return h


def create_wizard(name: str, x: float, y: float) -> Hero:
    """Wizard. Channeled ranged DPS with crowd control."""
    h = Hero(name, "Wizard", x, y, hp=6, ac=14, speed=6, surge_value=3,
             special_ability="Frostbolt Channel: Immobile while casting, slows enemies")
    h.max_hp = h.hp = h.base_max_hp = hero_max_hp("Wizard", 1)   # level-1 HP (progression.HERO_HP)
    h.max_mana = h.mana = hero_max_mana("Wizard", 1)   # level-1 mana (progression.HERO_MANA)
    # Weapon: Staff — channeled ranged (36 base / 1.2s = 30 dps, 120% of baseline)
    h.base_damage = 9
    h.weapon_speed = 1.2
    h.attack_range = 260  # Ranged (long range caster)
    # Skills
    h.add_ability("Q", Ability("Frostbolt", mana_weight=3.0, cooldown=1.2, a_levels=(1.0,), b_levels=(1, 2, 3),
                               radius=0, range=260,
                               effect="Channeled ranged bolt. Immobile while casting. Slows 25% for 3s.",
                               power_type="at_will", color=(150, 200, 255), range_levels=WIZARD_BOLT_RANGES))
    h.add_ability("R", Ability("Fire Blast", mana_weight=2.0, cooldown=8.0, a_levels=(1.2, 1.3, 1.4), b_levels=(2, 4, 6),
                               radius=0, range=260,
                               effect="Instant ranged fire bolt (120/130/140% weapon dmg + 2/4/6).",
                               power_type="daily", color=(255, 130, 50), range_levels=WIZARD_BOLT_RANGES))
    h.add_ability("E", Ability("Frost Nova", mana_weight=0.3, target_kind="self", cooldown=12.0, a_levels=(0.4,), b_levels=(1, 2, 3),
                               radius=120, range=0,
                               effect="AoE freeze around self. 4s freeze + 40% weapon dmg + 1/2/3.",
                               power_type="daily", color=(180, 220, 255)))
    return h


# Class registry.
HERO_CLASSES = [
    {"class": "Fighter", "create": create_fighter, "sprite_key": "fighter",
     "desc": "Tank — 1H Sword+Shield, AoE melee"},
    {"class": "Cleric", "create": create_cleric, "sprite_key": "cleric",
     "desc": "Healer — Ranged Wand, Ward, HoT"},
    {"class": "Paladin", "create": create_paladin, "sprite_key": "paladin",
     "desc": "Holy Warrior — 2H Mace, Seal/Smite/Judgement"},
    {"class": "Rogue", "create": create_rogue, "sprite_key": "rogue",
     "desc": "Assassin — Stealth + Ambush opener, Poison Daggers"},
    {"class": "Wizard", "create": create_wizard, "sprite_key": "wizard",
     "desc": "Caster — Channeled Frostbolt, AoE spells"},
]
HERO_CLASS_BY_NAME = {c["class"]: c for c in HERO_CLASSES}

# AI companions are ordinary players with a random name from this pool (World.spawn_companion picks one that no
# hero in the world already has, so two players' companions never share a name).
COMPANION_NAMES = [
    "Vistra", "Quinn", "Keyleth", "Tarak", "Heskan", "Aldric", "Brynn", "Cassia", "Dorian", "Elowen", "Fenwick",
    "Gwyn", "Halric", "Isolde", "Jorund", "Kaelen", "Lyra", "Marek", "Nyssa", "Orin", "Perrin", "Rowan", "Sable",
    "Thessaly", "Ulric", "Vesper", "Wren", "Xanthe", "Yorick", "Zephyr",
]
