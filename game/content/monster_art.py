"""Monster pictures (pure data; the client and the map editor turn these into images).

Each monster definition (data/monsters.json) carries its own "sprite": {"sheet": "creatures" | "dungeon", "col": c,
"row": r} (16 px tiles: "creatures" = assets/tiny_creatures, "dungeon" = assets/kenney_dungeon), or {"file": path,
"scale": n} for a loose PNG drawn n x a character's size. "big": true draws a tile 1.5x bigger (the client's BOSS_SCALE):
bosses and uniques.
"""

SHEETS = {"creatures": "assets/tiny_creatures/tiny-creatures/Tilemap/tilemap_packed.png",
          "dungeon": "assets/kenney_dungeon/Tilemap/tilemap_packed.png"}
SHEET_SIZE = {"creatures": (10, 18), "dungeon": (12, 11)}     # (cols, rows) of 16 px tiles

BOSS_DEFAULT = {"sheet": "creatures", "col": 9, "row": 7}     # a boss without art: the scaled-up kobold


def art_for(spawn_type, stats=None):
    """The art reference of a spawn type (from its SPAWN_STATS entry), or None."""
    return (stats or {}).get("sprite")
