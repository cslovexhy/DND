"""
Wrath of Ashardalon hero classes — stats and abilities from card data.

Each class has a factory create_<class>(name, x, y); the player picks a class and a name when
creating a character (see game/saves.py). Skills come from content/skill_library.py (shared with monsters).
"""
from game.content import skill_library as S
from game.engine.entities import Hero
from game.progression import hero_max_hp, hero_max_mana


def create_fighter(name: str, x: float, y: float) -> Hero:
    """Fighter. 1H Sword + Shield — balanced speed and defense."""
    h = Hero(name, "Fighter", x, y, hp=8, ac=17, speed=5, surge_value=4)
    h.max_hp = h.hp = h.base_max_hp = hero_max_hp("Fighter", 1)   # level-1 HP (progression.HERO_HP)
    h.max_mana = h.mana = hero_max_mana("Fighter", 1)   # level-1 mana (progression.HERO_MANA)
    # Weapon: 1H Sword + Shield — balanced
    h.base_damage = 10   # level-1 weapon damage; + per level in progression.GROWTH_RATES
    h.weapon_speed = 1.6  # 1.6s between swings
    h.attack_range = 60
    # Skills (damage = a x weapon damage + b)
    h.add_ability("Q", S.strike())
    h.add_ability("R", S.charge())
    h.add_ability("E", S.demoralizing_shout())
    h.add_ability("F", S.heroic_strike())
    h.add_ability("G", S.cleave())
    return h


def create_cleric(name: str, x: float, y: float) -> Hero:
    """Cleric. Ranged healer/support with projectile auto-attack."""
    h = Hero(name, "Cleric", x, y, hp=8, ac=16, speed=5, surge_value=4)
    h.max_hp = h.hp = h.base_max_hp = hero_max_hp("Cleric", 1)   # level-1 HP (progression.HERO_HP)
    h.max_mana = h.mana = hero_max_mana("Cleric", 1)   # level-1 mana (progression.HERO_MANA)
    # Weapon: Wand — ranged, moderate speed (30 base / 1.2s = 25 dps)
    h.base_damage = 8
    h.weapon_speed = 1.2
    h.attack_range = 200  # Ranged
    h.add_ability("Q", S.wanding())
    h.add_ability("R", S.wall())
    h.add_ability("E", S.renew())
    return h


def create_paladin(name: str, x: float, y: float) -> Hero:
    """Paladin. 2H Mace — Seal/Smite/Judgement holy warrior."""
    h = Hero(name, "Paladin", x, y, hp=8, ac=17, speed=6, surge_value=4)
    h.max_hp = h.hp = h.base_max_hp = hero_max_hp("Paladin", 1)   # level-1 HP (progression.HERO_HP)
    h.max_mana = h.mana = hero_max_mana("Paladin", 1)   # level-1 mana (progression.HERO_MANA)
    # Weapon: 2H Mace — slow, hard hits
    h.base_damage = 12
    h.weapon_speed = 2.2
    h.attack_range = 60
    h.add_ability("Q", S.smite())
    h.add_ability("R", S.righteous_seal())
    h.add_ability("E", S.judgement())
    h.add_ability("F", S.holy_light())
    return h


def create_rogue(name: str, x: float, y: float) -> Hero:
    """Rogue. Fast melee assassin with stealth and burst."""
    h = Hero(name, "Rogue", x, y, hp=8, ac=14, speed=6, surge_value=4)
    h.max_hp = h.hp = h.base_max_hp = hero_max_hp("Rogue", 1)   # level-1 HP (progression.HERO_HP)
    h.max_mana = h.mana = hero_max_mana("Rogue", 1)   # level-1 mana (progression.HERO_MANA)
    # Weapon: Daggers — very fast (18.75 base / 0.5s = 37.5 dps, 1.5x fighter)
    h.base_damage = 4
    h.weapon_speed = 0.5
    h.attack_range = 50  # Melee
    h.crit_chance = 0.10  # 10% crit (double base)
    h.add_ability("Q", S.stab())
    h.add_ability("R", S.stealth())
    h.add_ability("E", S.ambush())
    h.add_ability("F", S.poison_dagger())
    return h


def create_wizard(name: str, x: float, y: float) -> Hero:
    """Wizard. Channeled ranged DPS with crowd control."""
    h = Hero(name, "Wizard", x, y, hp=6, ac=14, speed=6, surge_value=3)
    h.max_hp = h.hp = h.base_max_hp = hero_max_hp("Wizard", 1)   # level-1 HP (progression.HERO_HP)
    h.max_mana = h.mana = hero_max_mana("Wizard", 1)   # level-1 mana (progression.HERO_MANA)
    # Weapon: Staff — slow channeled ranged (2.0 s per Frostbolt; Frostbolt's a / b are x5/3 so the DPS is what
    # it was at 1.2 s, and its mana cost follows the swing so mana per second is unchanged too)
    h.base_damage = 9
    h.weapon_speed = 2.0
    h.attack_range = 260  # Ranged (long range caster)
    h.add_ability("Q", S.frostbolt())
    h.add_ability("R", S.fire_blast())
    h.add_ability("E", S.frost_nova())
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
