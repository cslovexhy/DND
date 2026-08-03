"""
Wrath of Ashardalon Heroes — all 5 heroes with stats and abilities from card data.
"""
from game.engine.entities import Hero, Ability

# Ability colors by class
FIGHTER_COLOR = (200, 200, 255)
CLERIC_COLOR = (255, 220, 100)
PALADIN_COLOR = (255, 255, 200)
ROGUE_COLOR = (180, 255, 180)
WIZARD_COLOR = (255, 130, 50)


def create_vistra(x: float, y: float) -> Hero:
    """Vistra — Dwarf Fighter. 1H Sword + Shield — balanced speed and defense."""
    h = Hero("Vistra", "Dwarf", "Fighter", x, y, hp=8, ac=17, speed=5, surge_value=4,
             special_ability="Cast-Iron Stomach: Immune to Poison")
    # Weapon: 1H Sword + Shield — balanced
    h.base_damage = 40
    h.weapon_speed = 1.6  # 1.6s between swings
    h.attack_range = 60
    # Skills (damage = base_damage * multiplier + flat)
    h.add_ability("Q", Ability("Reaping Strike", cooldown=0, multiplier=1.2, flat_bonus=0,
                               radius=70, range=70,
                               effect="Melee sweep hitting all adjacent enemies (120% weapon dmg)",
                               power_type="at_will", color=FIGHTER_COLOR))
    h.add_ability("R", Ability("Charge", cooldown=8.0, multiplier=2.0, flat_bonus=0,
                               radius=0, range=250,
                               effect="Dash to target (200% weapon dmg + stun 1.5s)",
                               power_type="daily", color=(255, 160, 50),
                               is_dash=True, stun_duration=1.5))
    h.add_ability("E", Ability("Demoralizing Shout", cooldown=5.0, multiplier=0, flat_bonus=0,
                               radius=120, range=0,
                               effect="Reduces nearby enemies damage by 50% for 10s, slows 3s",
                               power_type="encounter", color=(200, 150, 50)))
    return h


def create_quinn(x: float, y: float) -> Hero:
    """Quinn — Human Cleric. Ranged healer/support with projectile auto-attack."""
    h = Hero("Quinn", "Human", "Cleric", x, y, hp=8, ac=16, speed=5, surge_value=4,
             special_ability="Divine Warding: Protective wards and healing over time")
    # Weapon: Wand — ranged, moderate speed (30 base / 1.2s = 25 dps)
    h.base_damage = 30
    h.weapon_speed = 1.2
    h.attack_range = 200  # Ranged
    # Skills
    h.add_ability("Q", Ability("Wanding", cooldown=0, multiplier=1.0, flat_bonus=0,
                               radius=0, range=200,
                               effect="Ranged bolt (100% weapon dmg). Fires a projectile.",
                               power_type="at_will", color=CLERIC_COLOR))
    h.add_ability("R", Ability("Wall", cooldown=15.0, multiplier=0, flat_bonus=0,
                               radius=0, range=0,
                               effect="Absorb shield on self. Absorbs potion-amount of damage.",
                               power_type="utility", color=(100, 180, 255)))
    h.add_ability("E", Ability("Renew", cooldown=16.0, multiplier=0, flat_bonus=0,
                               radius=0, range=0,
                               effect="Heal 50% potion-amount over 8s.",
                               power_type="utility", color=(100, 255, 150)))
    return h

def create_keyleth(x: float, y: float) -> Hero:
    """Keyleth — Elf Paladin. 2H Mace — Seal/Smite/Judgement holy warrior."""
    h = Hero("Keyleth", "Elf", "Paladin", x, y, hp=8, ac=17, speed=6, surge_value=4,
             special_ability="Seal System: Seals buff Smite and empower Judgement")
    # Weapon: 2H Mace — slow, hard hits
    h.base_damage = 55
    h.weapon_speed = 2.2
    h.attack_range = 60
    # Skills
    h.add_ability("Q", Ability("Smite", cooldown=0, multiplier=1.0, flat_bonus=30,
                               radius=0, range=75,
                               effect="Melee divine strike (100% + 30 holy). Boosted by Seal.",
                               power_type="at_will", color=PALADIN_COLOR))
    h.add_ability("R", Ability("Righteous Seal", cooldown=10.0, multiplier=0, flat_bonus=0,
                               radius=0, range=0,
                               effect="Buff: Smite +25% for 10s. Consumed by Judgement.",
                               power_type="utility", color=(255, 220, 80)))
    h.add_ability("E", Ability("Judgement", cooldown=10.0, multiplier=0.8, flat_bonus=0,
                               radius=0, range=250,
                               effect="Ranged holy bolt (80% weapon). Consumes Seal for +100% bonus.",
                               power_type="daily", color=(255, 255, 150)))
    h.add_ability("F", Ability("Holy Light", cooldown=30.0, multiplier=0, flat_bonus=0,
                               radius=0, range=0,
                               effect="Channel 2s: heal 150 HP. Immobilizes during cast.",
                               power_type="utility", color=(255, 255, 220)))
    return h

def create_tarak(x: float, y: float) -> Hero:
    """Tarak — Half-Orc Rogue. Fast melee assassin with stealth and burst."""
    h = Hero("Tarak", "Half-Orc", "Rogue", x, y, hp=8, ac=14, speed=6, surge_value=4,
             special_ability="Stealth: Vanish from sight, Ambush from shadows")
    # Weapon: Daggers — very fast (18.75 base / 0.5s = 37.5 dps, 1.5x fighter)
    h.base_damage = 18.75
    h.weapon_speed = 0.5
    h.attack_range = 50  # Melee
    h.crit_chance = 0.10  # 10% crit (double base)
    # Skills
    h.add_ability("Q", Ability("Stab", cooldown=0, multiplier=1.0, flat_bonus=0,
                               radius=0, range=55,
                               effect="Fast melee strike (100% weapon dmg).",
                               power_type="at_will", color=ROGUE_COLOR))
    h.add_ability("R", Ability("Stealth", cooldown=6.0, multiplier=0, flat_bonus=0,
                               radius=0, range=0,
                               effect="Go invisible. 60% move speed. Mobs can't see you. Attack breaks stealth.",
                               power_type="utility", color=(100, 180, 100)))
    h.add_ability("E", Ability("Ambush", cooldown=0, multiplier=5.0, flat_bonus=0,
                               radius=0, range=55,
                               effect="Stealth only. 5x weapon dmg + 20% target max HP.",
                               power_type="daily", color=(255, 50, 50)))
    return h


def create_heskan(x: float, y: float) -> Hero:
    """Heskan — Dragonborn Wizard. Channeled ranged DPS with crowd control."""
    h = Hero("Heskan", "Dragonborn", "Wizard", x, y, hp=6, ac=14, speed=6, surge_value=3,
             special_ability="Frostbolt Channel: Immobile while casting, slows enemies")
    # Weapon: Staff — channeled ranged (36 base / 1.2s = 30 dps, 120% of baseline)
    h.base_damage = 36
    h.weapon_speed = 1.2
    h.attack_range = 260  # Ranged (long range caster)
    # Skills
    h.add_ability("Q", Ability("Frostbolt", cooldown=1.2, multiplier=1.0, flat_bonus=0,
                               radius=0, range=260,
                               effect="Channeled ranged bolt. Immobile while casting. Slows 25% for 3s.",
                               power_type="at_will", color=(150, 200, 255)))
    h.add_ability("R", Ability("Fire Blast", cooldown=8.0, multiplier=1.0, flat_bonus=0,
                               radius=0, range=260,
                               effect="Instant ranged fire bolt. Same damage as Frostbolt.",
                               power_type="daily", color=(255, 130, 50)))
    h.add_ability("E", Ability("Frost Nova", cooldown=12.0, multiplier=0.25, flat_bonus=0,
                               radius=120, range=0,
                               effect="AoE freeze around self. 4s freeze + cold damage.",
                               power_type="daily", color=(180, 220, 255)))
    return h


# Hero registry for selection
ALL_HEROES = [
    {"create": create_vistra, "name": "Vistra", "race": "Dwarf", "class": "Fighter",
     "desc": "Tank — 1H Sword+Shield, AoE melee", "sprite_key": "vistra", "wip": False},
    {"create": create_quinn, "name": "Quinn", "race": "Human", "class": "Cleric",
     "desc": "Healer — Ranged Wand, Ward, HoT", "sprite_key": "quinn", "wip": False},
    {"create": create_keyleth, "name": "Keyleth", "race": "Elf", "class": "Paladin",
     "desc": "Holy Warrior — 2H Mace, Seal/Smite/Judgement", "sprite_key": "keyleth", "wip": False},
    {"create": create_tarak, "name": "Tarak", "race": "Half-Orc", "class": "Rogue",
     "desc": "Assassin — Fast Daggers, Stealth, Ambush", "sprite_key": "tarak", "wip": False},
    {"create": create_heskan, "name": "Heskan", "race": "Dragonborn", "class": "Wizard",
     "desc": "Caster — Channeled Frostbolt, AoE spells", "sprite_key": "heskan", "wip": False},
]
