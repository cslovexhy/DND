"""Monster stat table for map spawn points (pure data; no pygame).

Keys are the spawn-type strings used in data/maps/*.json. Optional flags: boss, unique, ranged,
relentless, hive_mind, respawn_mult, skills (HP-triggered boss skills, see game/engine/skills.py),
kit (castable skills from content/skill_library.py, e.g. ["Poison Dagger"]; see engine/monster_casting.py),
hp_mult (max HP multiplier for the type, default 1; see monster_hp_mult),
swing (seconds between attacks, default MONSTER_SWING_TIME; bosses swing 20% faster).
Every type also has a category (MONSTER_CATEGORY: humanoid / beast / demon) that decides its loot.
A map spawn point may override any of these for that spawn ("stats": {...}), kit included.
"""
from game.progression import ref_mana

MONSTER_SWING_TIME = 2.0   # default seconds between a monster's attacks
RESPAWN_TIME = 60.0     # seconds before a killed regular mob respawns
BOSS_RESPAWN_MULT = 10  # bosses take 10x as long (600s) unless SPAWN_STATS sets "respawn_mult"

SPAWN_STATS = {
    "kobold_dragonshield": {"name": "Kobold Dragonshield", "hp": 1, "ac": 16, "speed": 5, "atk": 7, "dmg": 1, "xp": 5},
    "snake": {"name": "Snake", "hp": 1, "ac": 13, "speed": 6, "atk": 7, "dmg": 0, "xp": 5, "kit": ["Poison Dagger"]},
    "orc_smasher": {"name": "Orc Smasher", "hp": 2, "ac": 15, "speed": 4, "atk": 9, "dmg": 1, "xp": 10},
    "orc_archer": {"name": "Orc Archer", "hp": 1, "ac": 13, "speed": 4, "atk": 6, "dmg": 1, "xp": 5, "ranged": True},
    "grey_wolf": {"name": "Grey Wolf", "hp": 2, "ac": 14, "speed": 5, "atk": 8, "dmg": 2, "xp": 10},
    "duergar_guard": {"name": "Duergar Guard", "hp": 2, "ac": 16, "speed": 4, "atk": 8, "dmg": 1, "xp": 10},
    "gibbering_mouther": {"name": "Gibbering Mouther", "hp": 2, "ac": 14, "speed": 3, "atk": 8, "dmg": 1, "xp": 15},
    "grell": {"name": "Grell", "hp": 2, "ac": 15, "speed": 5, "atk": 7, "dmg": 1, "xp": 10, "kit": ["Poison Dagger"]},
    "human_cultist": {"name": "Human Cultist", "hp": 1, "ac": 14, "speed": 5, "atk": 6, "dmg": 1, "xp": 5, "kit": ["Poison Dagger"]},
    "legion_devil": {"name": "Legion Devil", "hp": 1, "ac": 16, "speed": 5, "atk": 11, "dmg": 1, "xp": 15},
    # Stranger Things set (Upside Down). Demogorgon: fast (1.5x player speed 6 = 9) and hits hard.
    "demogorgon": {"name": "Demogorgon", "hp": 8, "ac": 16, "speed": 9, "atk": 10, "dmg": 3, "xp": 20, "relentless": True, "hive_mind": (1000, ["demogorgon", "vecna"])},
    "demodog": {"name": "Demodog", "hp": 2, "ac": 15, "speed": 7, "atk": 8, "dmg": 2, "xp": 10},
    "demobat": {"name": "Demobat", "hp": 1, "ac": 14, "speed": 8, "atk": 7, "dmg": 1, "xp": 5},
    "vecna": {"name": "Vecna", "hp": 10, "ac": 18, "speed": 5, "atk": 11, "dmg": 3, "xp": 50, "boss": True},
    "meerak": {"name": "Meerak", "hp": 6, "ac": 17, "speed": 5, "atk": 8, "dmg": 1, "xp": 25, "boss": True},
    "ashardalon": {"name": "Ashardalon", "hp": 12, "ac": 16, "speed": 4, "atk": 10, "dmg": 2, "xp": 50, "boss": True,
                   # Deep Breath at 50% and again at 20% HP: "took a deep breath..." for 1.5 s, then a red zone of
                   # radius 200 px for 3 s that pulses 3 times, each pulse hitting everyone inside for 100 (300 total)
                   "skills": {"deep_breath": {"radius": 200, "duration": 3.0, "cycles": 3, "dps": 100, "windup": 1.5,
                                              "at_hp_pct": (0.5, 0.2)},
                              # at 50% HP the boss' melee/ranged attacks deal 50% more damage
                              "enrage": {"at_hp_pct": (0.5,), "damage_mult": 1.5}}},
    "bellax": {"name": "Bellax", "hp": 9, "ac": 17, "speed": 4, "atk": 8, "dmg": 2, "xp": 40, "boss": True},
    "karash": {"name": "Karash", "hp": 5, "ac": 15, "speed": 5, "atk": 7, "dmg": 1, "xp": 25, "boss": True},
    "margrath": {"name": "Margrath", "hp": 5, "ac": 16, "speed": 4, "atk": 8, "dmg": 1, "xp": 25, "boss": True},
    "rage_drake": {"name": "Rage Drake", "hp": 5, "ac": 15, "speed": 6, "atk": 9, "dmg": 2, "xp": 25, "boss": True},
    "otyugh": {"name": "Otyugh", "hp": 5, "ac": 14, "speed": 3, "atk": 8, "dmg": 2, "xp": 25, "boss": True},
    "garrick_padfoot": {"name": "Garrick Padfoot", "hp": 4, "ac": 15, "speed": 5, "atk": 8, "dmg": 2, "xp": 30, "unique": True, "respawn_mult": 3,
                        "hp_mult": 2},
}


# --- Monster categories (loot rules, see content/items.py): humanoids carry money, beasts drop more food ----------
HUMANOID, BEAST, DEMON = "humanoid", "beast", "demon"
MONSTER_CATEGORY = {
    # humanoids: people and the people-like races
    "kobold_dragonshield": HUMANOID, "orc_smasher": HUMANOID, "orc_archer": HUMANOID, "duergar_guard": HUMANOID,
    "human_cultist": HUMANOID, "garrick_padfoot": HUMANOID, "meerak": HUMANOID,     # Meerak: kobold chieftain
    "margrath": HUMANOID,                                                             # duergar captain
    "karash": HUMANOID, "vecna": HUMANOID,                                            # Vecna: a lich (undead mage)
    # beasts: animals, and dragons (no other category fits them better)
    "snake": BEAST, "grey_wolf": BEAST, "rage_drake": BEAST, "ashardalon": BEAST,
    # demons: fiends, plus the aberrations and Upside Down creatures
    "legion_devil": DEMON, "demogorgon": DEMON, "demodog": DEMON, "demobat": DEMON,
    "gibbering_mouther": DEMON, "grell": DEMON, "otyugh": DEMON, "bellax": DEMON,  # Bellax: a gauth (beholder-kin)
}
for _key, _stats in SPAWN_STATS.items():
    _stats["category"] = MONSTER_CATEGORY[_key]       # KeyError = a new monster type without a category


def humanoid_money(level, rng):
    """Bronze a humanoid of this level drops: round(max(5, level x 8 - 40) x 0.8..1.2)."""
    return int(round(max(5, level * 8 - 40) * rng.uniform(0.8, 1.2)))


# --- Monster levels ---------------------------------------------------------------------------------------------
# A map may give spawn types a level range:  "monster_levels": {"human_cultist": [3, 4], ...}  (data/maps/*.json).
# Each spawned monster rolls a level in that range; the level alone sets its HP and the XP it is worth (the
# SPAWN_STATS "hp" is not used, so a higher-level monster always has more HP). AC, damage and speed stay
# hand-tuned in SPAWN_STATS. Spawn types without a level keep their hand-tuned HP and XP.
MONSTER_HP_LEVEL_1 = 50     # real HP of a level-1 monster
MONSTER_HP_PER_LEVEL = 25   # + per level above 1: same growth as a hero's default (progression.DEFAULT_GROWTH["hp"])
XP_PER_MONSTER_LEVEL = 10   # base XP = monster level x 10
XP_LEVEL_SPAN = 6           # a hero this many levels above a monster gets no XP from it


def monster_hp_mult(stats):
    """Per-type max HP multiplier (SPAWN_STATS "hp_mult", default 1). Applies to levelled and hand-tuned HP alike,
    before map difficulty (pp)."""
    return stats.get("hp_mult", 1)


def hp_for_level(level):
    """Max HP (real points, before pp) of a monster of this level: 50, 75, 100, 125, 150, ..."""
    return MONSTER_HP_LEVEL_1 + MONSTER_HP_PER_LEVEL * (level - 1)


def damage_for_level(level):
    """Average damage per hit (before pp) of a levelled monster: level + 5. Each hit rolls x0.9..x1.1 (rounded)."""
    return level + 5


DAMAGE_ROLL = (0.9, 1.1)    # per-hit random factor for levelled monsters


# --- Monster skills (kit) ---------------------------------------------------------------------------------------
# A monster casts its kit's skills exactly like a hero: same damage formula (a x its hit damage + b), cooldown and
# mana cost (Ability.mana_cost: mana_rate(level) x time between casts x the skill's share of the kit's weights). Its
# mana pool is the average hero pool at its level, so it spends mana at the same rate a hero does and runs dry
# after about as long.
MONSTER_SKILL_LEVEL_AT = (10, 20)   # monster level at which its skills reach skill level 2 / 3


def monster_skill_level(level):
    """Skill level (1..3) of a monster's kit at this monster level."""
    return 1 + sum(level >= lv for lv in MONSTER_SKILL_LEVEL_AT)


def monster_max_mana(level):
    """Mana pool of a monster with a kit: the average hero pool at its level (progression.ref_mana)."""
    return int(round(ref_mana(level)))


def base_xp_for_level(level):
    return XP_PER_MONSTER_LEVEL * level


def kill_xp(base_xp, hero_level, monster_level):
    """XP a hero of `hero_level` gets for killing a monster of `monster_level` worth `base_xp`:
    base x (6 - min(6, max(0, heroLv - monsterLv))) / 6 — full XP at or below the monster's level, 1/6 less per level
    above it, nothing from 6 levels up."""
    above = min(XP_LEVEL_SPAN, max(0, hero_level - monster_level))
    return int(round(base_xp * (XP_LEVEL_SPAN - above) / XP_LEVEL_SPAN))


def respawn_delay(m):
    """Seconds until a killed monster respawns: RESPAWN_TIME x its "respawn_mult" (default 1, bosses 10)."""
    stats = SPAWN_STATS.get(getattr(m, "spawn_type", None), {})
    return RESPAWN_TIME * stats.get("respawn_mult", BOSS_RESPAWN_MULT if m.is_boss else 1)
