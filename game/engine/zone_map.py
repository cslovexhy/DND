"""
Zone Map — loads JSON zone file and provides collision/terrain queries.
Replaces UnifiedDungeon for open-world zones.
"""
import json

TILE_SIZE = 48


class ZoneMap:
    """An open-world zone loaded from JSON."""

    def __init__(self, path: str):
        with open(path) as f:
            data = json.load(f)

        self.name = data["name"]
        self.width = data["width"]
        self.height = data["height"]
        self.tile_size = data.get("tile_size", TILE_SIZE)
        self.terrain = data["terrain"]
        self.collision = data["collision"]
        self.spawn_points = data.get("spawn_points", [])
        self.regions = data.get("regions", [])

    def is_wall(self, wx: float, wy: float) -> bool:
        """Check if world position is blocked."""
        tx = int(wx // self.tile_size)
        ty = int(wy // self.tile_size)
        if tx < 0 or tx >= self.width or ty < 0 or ty >= self.height:
            return True
        return self.collision[ty][tx]

    def is_floor(self, tx: int, ty: int) -> bool:
        """Check if tile is walkable."""
        if tx < 0 or tx >= self.width or ty < 0 or ty >= self.height:
            return False
        return not self.collision[ty][tx]

    def get_terrain(self, tx: int, ty: int) -> str:
        """Get terrain type at tile."""
        if tx < 0 or tx >= self.width or ty < 0 or ty >= self.height:
            return "mountain"
        return self.terrain[ty][tx]

    def get_spawn(self, name: str) -> tuple:
        """Get spawn point world coords by name."""
        for sp in self.spawn_points:
            if sp["name"] == name:
                return (sp["x"] * self.tile_size + self.tile_size // 2,
                        sp["y"] * self.tile_size + self.tile_size // 2)
        return (self.width * self.tile_size // 2, self.height * self.tile_size // 2)

    @property
    def world_width(self) -> int:
        return self.width * self.tile_size

    @property
    def world_height(self) -> int:
        return self.height * self.tile_size
