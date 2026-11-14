"""Monster tables for map spawn points (pure data; no pygame).

The monsters themselves are defined in data/monsters.json (format: content/monster_defs.py) and edited in the map
editor's Monsters screen (M). This module loads them into SPAWN_STATS (keys are the spawn-type strings used in
data/maps/*.json), MONSTER_CATEGORY and MONSTER_DROPS, and holds the rules that turn a monster's level into HP, damage
and XP. A map spawn point may override any SPAWN_STATS field for that spawn ("stats": {...}), kit included.
"""
from game.progression import ref_mana

MONSTER_SWING_TIME = 2.0   # default seconds between a monster's attacks
RESPAWN_TIME = 60.0     # seconds before a killed regular mob respawns
BOSS_RESPAWN_MULT = 10  # bosses take 10x as long (600s) unless SPAWN_STATS sets "respawn_mult"

HUMANOID, BEAST, DEMON = "humanoid", "beast", "demon"

SPAWN_STATS = {}         # monster id -> what the game reads (content/monster_defs.to_spawn_stats), loaded below
MONSTER_CATEGORY = {}    # monster id -> humanoid / beast / demon (loot rules: only humanoids carry money)
MONSTER_DROPS = {}       # monster id -> its own drop list: (item, chance) or (item, chance, min_lv, max_lv)
DEFINITIONS = {}         # monster id -> the definition as stored in data/monsters.json


def register(defs):
    """Add monster definitions (content/monster_defs.py) to the tables above. Invalid ones are skipped with a
    message. Returns the ids added."""
    from game.content import monster_defs
    from game.content.items import ITEMS
    from game.content.skill_library import SKILLS
    added = []
    for tid, d in defs.items():
        errs = monster_defs.validate(tid, d, SKILLS, ITEMS)
        if errs:
            print(f"[MONSTERS] skipping monster {tid!r}: {'; '.join(errs)}")
            continue
        stats = monster_defs.to_spawn_stats(d)
        SPAWN_STATS[tid] = stats
        MONSTER_CATEGORY[tid] = stats["category"]
        MONSTER_DROPS[tid] = stats["drops"]
        DEFINITIONS[tid] = d
        added.append(tid)
    return added


def unregister(type_ids):
    """Remove types again (tests, the editor reloading the file)."""
    for tid in type_ids:
        for table in (SPAWN_STATS, MONSTER_CATEGORY, MONSTER_DROPS, DEFINITIONS):
            table.pop(tid, None)


def _load_definitions():
    from game.content import monster_defs
    try:
        return register(monster_defs.load())
    except (OSError, ValueError) as e:
        raise RuntimeError(f"Cannot read the monster definitions ({monster_defs.PATH}): {e}") from e


_load_definitions()      # data/monsters.json: every monster type, edited in the map editor (M)


def monster_name(monster_id):
    """The current name of a monster type (names can be edited; ids never change)."""
    return SPAWN_STATS.get(monster_id, {}).get("name", f"monster #{monster_id}")


def humanoid_money(level, rng):
    """Bronze a humanoid of this level drops: round(max(5, level x 8 - 40) x 0.8..1.2)."""
    return int(round(max(5, level * 8 - 40) * rng.uniform(0.8, 1.2)))


# --- Monster levels ---------------------------------------------------------------------------------------------
# A monster definition may carry a level range ("level": [3, 4], data/monsters.json); the same on every map (a monster
# that must be tougher elsewhere is a second monster type). Each spawned monster rolls a level in that range; the
# level alone sets its HP and the XP it is worth (the raw "hp" is not used, so a higher-level monster always has more
# HP). AC, damage and speed stay hand-tuned in the definition. Monsters without a level keep their raw HP and XP.
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

