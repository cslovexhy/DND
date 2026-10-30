"""Monster stat table for map spawn points (pure data; no pygame).

Keys are the spawn-type strings used in data/maps/*.json. Optional flags: boss, unique, ranged,
condition (on-hit), relentless, hive_mind, respawn_mult.
"""
from game.engine.entities import Condition

RESPAWN_TIME = 60.0     # seconds before a killed regular mob respawns
BOSS_RESPAWN_MULT = 10  # bosses take 10x as long (600s) unless SPAWN_STATS sets "respawn_mult"

SPAWN_STATS = {
    "kobold_dragonshield": {"name": "Kobold Dragonshield", "hp": 1, "ac": 16, "speed": 5, "atk": 7, "dmg": 1, "xp": 5},
    "snake": {"name": "Snake", "hp": 1, "ac": 13, "speed": 6, "atk": 7, "dmg": 0, "xp": 5, "condition": (Condition.POISONED, 3.0)},
    "orc_smasher": {"name": "Orc Smasher", "hp": 2, "ac": 15, "speed": 4, "atk": 9, "dmg": 1, "xp": 10},
    "orc_archer": {"name": "Orc Archer", "hp": 1, "ac": 13, "speed": 4, "atk": 6, "dmg": 1, "xp": 5, "ranged": True},
    "grey_wolf": {"name": "Grey Wolf", "hp": 2, "ac": 14, "speed": 5, "atk": 8, "dmg": 2, "xp": 10},
    "duergar_guard": {"name": "Duergar Guard", "hp": 2, "ac": 16, "speed": 4, "atk": 8, "dmg": 1, "xp": 10},
    "gibbering_mouther": {"name": "Gibbering Mouther", "hp": 2, "ac": 14, "speed": 3, "atk": 8, "dmg": 1, "xp": 15},
    "grell": {"name": "Grell", "hp": 2, "ac": 15, "speed": 5, "atk": 7, "dmg": 1, "xp": 10, "condition": (Condition.POISONED, 3.0)},
    "human_cultist": {"name": "Human Cultist", "hp": 1, "ac": 14, "speed": 5, "atk": 6, "dmg": 1, "xp": 5, "condition": (Condition.POISONED, 3.0)},
    "legion_devil": {"name": "Legion Devil", "hp": 1, "ac": 16, "speed": 5, "atk": 11, "dmg": 1, "xp": 15},
    # Stranger Things set (Upside Down). Demogorgon: fast (1.5x player speed 6 = 9) and hits hard.
    "demogorgon": {"name": "Demogorgon", "hp": 8, "ac": 16, "speed": 9, "atk": 10, "dmg": 3, "xp": 20, "relentless": True, "hive_mind": (1000, ["demogorgon", "vecna"])},
    "demodog": {"name": "Demodog", "hp": 2, "ac": 15, "speed": 7, "atk": 8, "dmg": 2, "xp": 10},
    "demobat": {"name": "Demobat", "hp": 1, "ac": 14, "speed": 8, "atk": 7, "dmg": 1, "xp": 5},
    "vecna": {"name": "Vecna", "hp": 10, "ac": 18, "speed": 5, "atk": 11, "dmg": 3, "xp": 50, "boss": True},
    "meerak": {"name": "Meerak", "hp": 6, "ac": 17, "speed": 5, "atk": 8, "dmg": 1, "xp": 25, "boss": True},
    "ashardalon": {"name": "Ashardalon", "hp": 12, "ac": 16, "speed": 4, "atk": 10, "dmg": 2, "xp": 50, "boss": True},
    "bellax": {"name": "Bellax", "hp": 9, "ac": 17, "speed": 4, "atk": 8, "dmg": 2, "xp": 40, "boss": True},
    "karash": {"name": "Karash", "hp": 5, "ac": 15, "speed": 5, "atk": 7, "dmg": 1, "xp": 25, "boss": True},
    "margrath": {"name": "Margrath", "hp": 5, "ac": 16, "speed": 4, "atk": 8, "dmg": 1, "xp": 25, "boss": True},
    "rage_drake": {"name": "Rage Drake", "hp": 5, "ac": 15, "speed": 6, "atk": 9, "dmg": 2, "xp": 25, "boss": True},
    "otyugh": {"name": "Otyugh", "hp": 5, "ac": 14, "speed": 3, "atk": 8, "dmg": 2, "xp": 25, "boss": True},
    "garrick_padfoot": {"name": "Garrick Padfoot", "hp": 4, "ac": 15, "speed": 5, "atk": 8, "dmg": 2, "xp": 30, "unique": True, "respawn_mult": 3},
}



def respawn_delay(m):
    """Seconds until a killed monster respawns: RESPAWN_TIME x its "respawn_mult" (default 1, bosses 10)."""
    stats = SPAWN_STATS.get(getattr(m, "spawn_type", None), {})
    return RESPAWN_TIME * stats.get("respawn_mult", BOSS_RESPAWN_MULT if m.is_boss else 1)
