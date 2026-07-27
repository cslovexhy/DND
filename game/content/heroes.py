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
    """Vistra — Dwarf Fighter. Tank with high AC and melee damage."""
    h = Hero("Vistra", "Dwarf", "Fighter", x, y, hp=8, ac=17, speed=5, surge_value=4,
             special_ability="Cast-Iron Stomach: Immune to Poison")
    h.attack_damage = 30
    h.attack_range = 55
    h.attack_cooldown = 0.5
    h.add_ability("Q", Ability("Reaping Strike", cooldown=2.0, damage=50, radius=70, range=70,
                               effect="Melee sweep hitting all adjacent enemies",
                               power_type="at_will", color=FIGHTER_COLOR))
    h.add_ability("R", Ability("Charge", cooldown=8.0, damage=100, radius=0, range=250,
                               effect="Dash to target, deal damage + stun 1.5s",
                               power_type="daily", color=(255, 160, 50),
                               is_dash=True, stun_duration=1.5))
    h.add_ability("E", Ability("Whirlwind", cooldown=10.0, damage=30, radius=70, range=70,
                               effect="Spin attack hitting all enemies in melee range",
                               power_type="daily", color=(220, 220, 255)))
    return h


def create_quinn(x: float, y: float) -> Hero:
    """Quinn — Human Cleric. Healer with support abilities."""
    h = Hero("Quinn", "Human", "Cleric", x, y, hp=8, ac=16, speed=5, surge_value=4,
             special_ability="Saving Grace: When ally on your tile drops to 0 HP, they regain 1 HP")
    h.attack_damage = 25
    h.attack_range = 55
    h.attack_cooldown = 0.6
    h.add_ability("Q", Ability("Sacred Flame", cooldown=2.5, damage=45, radius=0, range=200,
                               effect="Ranged divine bolt",
                               power_type="at_will", color=CLERIC_COLOR))
    h.add_ability("R", Ability("Healing Hymn", cooldown=10.0, damage=-100, radius=120,
                               effect="Heal all allies within range for 100 HP",
                               power_type="daily", color=(100, 255, 100)))
    h.add_ability("E", Ability("Blade Barrier", cooldown=14.0, damage=60, radius=100,
                               effect="Ring of blades damages enemies passing through",
                               power_type="daily", color=(200, 200, 255)))
    return h


def create_keyleth(x: float, y: float) -> Hero:
    """Keyleth — Elf Paladin. Tank/off-healer with divine smite."""
    h = Hero("Keyleth", "Elf", "Paladin", x, y, hp=8, ac=17, speed=6, surge_value=4,
             special_ability="Healing Hands: After using Daily power, heal adjacent ally 50 HP")
    h.attack_damage = 28
    h.attack_range = 55
    h.attack_cooldown = 0.55
    h.add_ability("Q", Ability("Holy Strike", cooldown=2.0, damage=48, radius=0, range=60,
                               effect="Melee divine strike. Bonus damage to undead.",
                               power_type="at_will", color=PALADIN_COLOR))
    h.add_ability("R", Ability("Righteous Smite", cooldown=9.0, damage=90, radius=90,
                               effect="Divine AoE smash. Heals self for 30% of damage.",
                               power_type="daily", color=(255, 230, 100)))
    h.add_ability("E", Ability("Lay on Hands", cooldown=15.0, damage=-150, radius=0, range=80,
                               effect="Heal target ally for 150 HP",
                               power_type="utility", color=(100, 255, 150)))
    return h


def create_tarak(x: float, y: float) -> Hero:
    """Tarak — Half-Orc Rogue. Fast melee DPS with burst and mobility."""
    h = Hero("Tarak", "Half-Orc", "Rogue", x, y, hp=8, ac=14, speed=6, surge_value=4,
             special_ability="Brutal Recovery: Crit chance +10% when below 50% HP")
    h.attack_damage = 35
    h.attack_range = 50
    h.attack_cooldown = 0.4
    h.add_ability("Q", Ability("Positioning Shot", cooldown=2.0, damage=55, radius=0, range=50,
                               effect="Quick stab + dash backward 3m",
                               power_type="at_will", color=ROGUE_COLOR))
    h.add_ability("R", Ability("Tornado Strike", cooldown=7.0, damage=70, radius=90,
                               effect="Spin attack hitting all adjacent enemies",
                               power_type="daily", color=(150, 255, 150)))
    h.add_ability("E", Ability("Tumbling Escape", cooldown=5.0, damage=0, radius=0, range=0,
                               effect="Dash 150px in move direction. Invincible during dash.",
                               power_type="utility", color=(200, 255, 200)))
    return h


def create_heskan(x: float, y: float) -> Hero:
    """Heskan — Dragonborn Wizard. Ranged AoE damage dealer."""
    h = Hero("Heskan", "Dragonborn", "Wizard", x, y, hp=6, ac=14, speed=6, surge_value=3,
             special_ability="Mage Hand: Can pick up treasure from 1 tile away")
    h.attack_damage = 20
    h.attack_range = 200
    h.attack_cooldown = 0.7
    h.add_ability("Q", Ability("Ray of Frost", cooldown=2.0, damage=40, radius=0, range=250,
                               effect="Ranged ice bolt. Slows target 2s.",
                               power_type="at_will", color=(150, 200, 255)))
    h.add_ability("R", Ability("Flaming Sphere", cooldown=8.0, damage=75, radius=90,
                               effect="Fireball at target location",
                               power_type="daily", color=WIZARD_COLOR))
    h.add_ability("E", Ability("Arc Lightning", cooldown=10.0, damage=60, radius=0, range=200,
                               effect="Chain lightning hitting up to 3 targets",
                               power_type="daily", color=(100, 150, 255)))
    return h


# Hero registry for selection
ALL_HEROES = [
    {"create": create_vistra, "name": "Vistra", "race": "Dwarf", "class": "Fighter",
     "desc": "Tank — High armor, strong melee AoE", "sprite_key": "vistra"},
    {"create": create_quinn, "name": "Quinn", "race": "Human", "class": "Cleric",
     "desc": "Healer — Ranged attacks, party healing", "sprite_key": "quinn"},
    {"create": create_keyleth, "name": "Keyleth", "race": "Elf", "class": "Paladin",
     "desc": "Tank/Healer — Divine smites, off-healing", "sprite_key": "keyleth"},
    {"create": create_tarak, "name": "Tarak", "race": "Half-Orc", "class": "Rogue",
     "desc": "Melee DPS — Fast attacks, burst, mobility", "sprite_key": "tarak"},
    {"create": create_heskan, "name": "Heskan", "race": "Dragonborn", "class": "Wizard",
     "desc": "Ranged DPS — AoE spells, crowd control", "sprite_key": "heskan"},
]
