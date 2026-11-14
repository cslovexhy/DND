"""Which picture each monster type uses (pure data; the client and the map editor turn these into images).

An art reference is {"sheet": "creatures" | "dungeon", "col": c, "row": r} (16 px tiles: "creatures" =
assets/tiny_creatures, "dungeon" = assets/kenney_dungeon), or {"file": path, "scale": n} for a loose PNG drawn n x a
character's size. An entry with "big": true is drawn 1.5x bigger (the client's BOSS_SCALE): bosses and uniques. Custom monster types (data/custom_monsters.json,
content/monster_defs.py) carry their own "sprite" reference.
"""


def tile(sheet, col, row, big=False):
    """big: drawn 1.5x a character's size (bosses, uniques like Garrick Padfoot)."""
    t = {"sheet": sheet, "col": col, "row": row}
    if big:
        t["big"] = True
    return t


SHEETS = {"creatures": "assets/tiny_creatures/tiny-creatures/Tilemap/tilemap_packed.png",
          "dungeon": "assets/kenney_dungeon/Tilemap/tilemap_packed.png"}
SHEET_SIZE = {"creatures": (10, 18), "dungeon": (12, 11)}     # (cols, rows) of 16 px tiles

# Built-in types (spawn-type id -> art). Bosses use their boss picture.
ART = {
    "kobold_dragonshield": tile("creatures", 9, 7),
    "snake": tile("creatures", 0, 4),
    "orc_smasher": tile("creatures", 1, 1),
    "orc_archer": tile("creatures", 0, 1),
    "human_cultist": tile("creatures", 7, 6),
    "duergar_guard": tile("creatures", 4, 12),
    "legion_devil": tile("creatures", 8, 3),
    "grey_wolf": tile("creatures", 3, 2),
    "grell": tile("creatures", 0, 12),
    "gibbering_mouther": tile("creatures", 4, 8),
    "demodog": tile("creatures", 2, 10),       # Hellhound (CC0 Tiny Creatures)
    "demobat": tile("creatures", 8, 13),       # Bat
    "vecna": tile("creatures", 6, 9, big=True),   # Lich
    "demogorgon": {"file": "assets/stranger_things/sprites/demogorgon.png", "scale": 2},   # original art, 2x
    # bosses (drawn 1.5x)
    "ashardalon": tile("creatures", 3, 3, big=True),
    "rage_drake": tile("creatures", 8, 7, big=True),
    "garrick_padfoot": tile("creatures", 7, 6, big=True),   # a scaled-up Human Cultist
    "otyugh": tile("creatures", 5, 7, big=True),
    "bellax": tile("creatures", 5, 0, big=True),
    "meerak": tile("creatures", 8, 7, big=True),
    "karash": tile("creatures", 5, 12, big=True),
    "margrath": tile("creatures", 7, 2, big=True),
}
BOSS_DEFAULT = tile("creatures", 9, 7)        # a boss without art: the scaled-up kobold


def art_for(spawn_type, stats=None):
    """The art reference of a spawn type (custom types: their "sprite"), or None."""
    if stats and stats.get("sprite"):
        return stats["sprite"]
    return ART.get(spawn_type)
