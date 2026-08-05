"""
Map loader — reads JSON map files created by the map editor.
Provides tile data, walkability grid, and spawn points for the game.
"""
import json
from dataclasses import dataclass, field
from typing import Optional

TILE_SIZE = 48  # pixels per tile (same as dungeon.py)


@dataclass
class MapTile:
    """A single tile from the spritesheet."""
    col: int
    row: int
    walkable: bool = True


@dataclass
class SpawnPoint:
    """An entity spawn position."""
    type: str  # "hero_start", "kobold_dragonshield", etc.
    x: int     # tile x
    y: int     # tile y


class WorldMap:
    """A loaded map from JSON — replaces UnifiedDungeon for open world areas."""

    def __init__(self):
        self.width = 0   # in tiles
        self.height = 0  # in tiles
        self.ground = []  # 2D list of MapTile or None
        self.objects = []  # 2D list of MapTile or None
        self.spawns: list[SpawnPoint] = []
        self.hero_start: Optional[tuple] = None  # (tx, ty)

    @classmethod
    def load(cls, path: str) -> 'WorldMap':
        """Load a map from a JSON file."""
        with open(path, "r") as f:
            data = json.load(f)

        m = cls()
        m.width = data["width"]
        m.height = data["height"]
        m.tile_size = data.get("tile_size", TILE_SIZE)

        # Load layers
        for layer_data in data.get("layers", []):
            name = layer_data["name"]
            tiles = []
            for row in layer_data["tiles"]:
                tile_row = []
                for cell in row:
                    if cell is None:
                        tile_row.append(None)
                    else:
                        tile_row.append(MapTile(
                            col=cell["col"],
                            row=cell["row"],
                            walkable=cell.get("walkable", True)
                        ))
                tiles.append(tile_row)

            if name == "ground":
                m.ground = tiles
            elif name == "objects":
                m.objects = tiles

        # Load spawns
        for sp in data.get("spawns", []):
            spawn = SpawnPoint(type=sp["type"], x=sp["x"], y=sp["y"])
            if spawn.type == "hero_start":
                m.hero_start = (spawn.x, spawn.y)
            else:
                m.spawns.append(spawn)

        return m

    def is_walkable(self, wx, wy) -> bool:
        """Check if a world-pixel position is walkable."""
        ts = getattr(self, 'tile_size', TILE_SIZE)
        tx = int(wx // ts)
        ty = int(wy // ts)
        return self.is_tile_walkable(tx, ty)

    def is_tile_walkable(self, tx, ty) -> bool:
        """Check if a tile coordinate is walkable."""
        if tx < 0 or tx >= self.width or ty < 0 or ty >= self.height:
            return False

        # Objects layer overrides ground (e.g. a tree on grass = blocked)
        if self.objects and self.objects[ty][tx] is not None:
            return self.objects[ty][tx].walkable

        # Fall back to ground layer
        if self.ground and self.ground[ty][tx] is not None:
            return self.ground[ty][tx].walkable

        # Empty tile (no visual) = still walkable
        return True

    # Compatibility with dungeon.py / pathfinding.py interface
    def is_floor(self, tx, ty) -> bool:
        """Same as is_tile_walkable — for pathfinding compatibility."""
        return self.is_tile_walkable(tx, ty)

    def is_wall(self, wx, wy) -> bool:
        """Inverse of is_walkable — for dungeon.is_wall() compatibility."""
        return not self.is_walkable(wx, wy)

    def get_start_pos(self) -> tuple:
        """Get hero start position in world pixel coords (center of tile)."""
        ts = self.tile_size
        if self.hero_start:
            tx, ty = self.hero_start
            return (tx * ts + ts // 2, ty * ts + ts // 2)
        # Fallback: center of map
        return (self.width * ts // 2, self.height * ts // 2)

    def get_spawn_world_pos(self, tx, ty) -> tuple:
        """Convert tile coords to world pixel center."""
        ts = self.tile_size
        return (tx * ts + ts // 2, ty * ts + ts // 2)

    def get_monster_spawns(self) -> list:
        """Return all monster/entity spawn points (excluding hero_start)."""
        return self.spawns
