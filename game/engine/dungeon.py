"""
Unified dungeon generator — one continuous tile grid with rooms + corridors.
No teleports, no separate room spaces. Everything lives in one grid.
"""
import random
import math
from dataclasses import dataclass, field
from typing import Optional

TILE_SIZE = 48  # pixels per tile


class RoomType:
    START = "start"
    STANDARD = "standard"
    DANGEROUS = "dangerous"
    QUEST = "quest"


@dataclass
class RoomInfo:
    """Metadata about a room placed in the unified grid."""
    id: int
    room_type: str
    name: str
    # Position in the unified grid (top-left corner, in tiles)
    gx: int
    gy: int
    width: int
    height: int
    # State
    explored: bool = False
    monsters_spawned: bool = False
    # Spawn points (tile coords relative to grid origin, not room)
    monster_spawns: list = field(default_factory=list)

    @property
    def center_x(self):
        return self.gx + self.width // 2

    @property
    def center_y(self):
        return self.gy + self.height // 2

    def contains_tile(self, tx, ty):
        return self.gx <= tx < self.gx + self.width and self.gy <= ty < self.gy + self.height

    def contains_world(self, wx, wy):
        tx = int(wx // TILE_SIZE)
        ty = int(wy // TILE_SIZE)
        return self.contains_tile(tx, ty)


class UnifiedDungeon:
    """A single tile grid containing all rooms and corridors."""

    def __init__(self):
        self.grid_w = 0
        self.grid_h = 0
        self.tiles = []  # 2D list: "wall" or "floor"
        self.rooms: list[RoomInfo] = []
        self.current_room_id = 0

    def generate(self, num_rooms=7, quest_room_name="Tunnel Exit"):
        """Generate the full dungeon as one grid."""
        # Room sizes
        ROOM_W_MIN, ROOM_W_MAX = 11, 15
        ROOM_H_MIN, ROOM_H_MAX = 9, 11
        CORRIDOR_LEN = 4
        PADDING = 2

        # Place rooms on a placement grid
        # We'll place rooms roughly in a line with some vertical variation
        room_defs = []
        cx, cy = 5, 5  # Starting position in grid space (leave border)

        for i in range(num_rooms):
            rw = random.randint(ROOM_W_MIN, ROOM_W_MAX)
            rh = random.randint(ROOM_H_MIN, ROOM_H_MAX)

            if i == 0:
                rtype = RoomType.START
                name = "Start"
            elif i == num_rooms - 1:
                rtype = RoomType.QUEST
                name = quest_room_name
            elif random.random() < 0.3:
                rtype = RoomType.DANGEROUS
                name = f"Room {i+1}"
            else:
                rtype = RoomType.STANDARD
                name = f"Room {i+1}"

            room_defs.append({
                "gx": cx, "gy": cy, "w": rw, "h": rh,
                "type": rtype, "name": name
            })

            # Next room position: go right with some vertical offset
            cx += rw + CORRIDOR_LEN + PADDING
            cy += random.randint(-3, 3)
            cy = max(3, cy)  # Keep in bounds

        # Compute total grid size needed
        max_x = max(r["gx"] + r["w"] for r in room_defs) + 5
        max_y = max(r["gy"] + r["h"] for r in room_defs) + 5
        min_y = min(r["gy"] for r in room_defs)
        # Shift all rooms down if any have negative y
        if min_y < 3:
            offset = 3 - min_y
            for r in room_defs:
                r["gy"] += offset
            max_y += offset

        self.grid_w = max_x
        self.grid_h = max_y

        # Fill grid with walls
        self.tiles = [["wall"] * self.grid_w for _ in range(self.grid_h)]

        # Carve rooms
        self.rooms = []
        for i, rd in enumerate(room_defs):
            gx, gy, w, h = rd["gx"], rd["gy"], rd["w"], rd["h"]
            room = RoomInfo(id=i, room_type=rd["type"], name=rd["name"],
                           gx=gx, gy=gy, width=w, height=h)

            # Carve floor (leave 1-tile wall border inside)
            for ty in range(gy + 1, gy + h - 1):
                for tx in range(gx + 1, gx + w - 1):
                    if 0 <= ty < self.grid_h and 0 <= tx < self.grid_w:
                        self.tiles[ty][tx] = "floor"

            # Add pillars (not in start or quest rooms)
            if rd["type"] not in (RoomType.START, RoomType.QUEST):
                for _ in range(random.randint(1, 3)):
                    px = random.randint(gx + 3, gx + w - 4)
                    py = random.randint(gy + 3, gy + h - 4)
                    if 0 <= py < self.grid_h and 0 <= px < self.grid_w:
                        self.tiles[py][px] = "wall"

            # Monster spawn points (grid-absolute tile coords)
            if rd["type"] == RoomType.START:
                pass  # No monsters in start
            elif rd["type"] == RoomType.QUEST:
                room.monster_spawns = [(gx + w//2, gy + h//2)]
            else:
                count = random.randint(2, 4) if rd["type"] == RoomType.STANDARD else random.randint(3, 5)
                spawns = []
                for _ in range(count):
                    sx = random.randint(gx + 2, gx + w - 3)
                    sy = random.randint(gy + 2, gy + h - 3)
                    spawns.append((sx, sy))
                room.monster_spawns = spawns

            self.rooms.append(room)

        # Carve corridors between consecutive rooms
        for i in range(len(self.rooms) - 1):
            r1 = self.rooms[i]
            r2 = self.rooms[i + 1]
            self._carve_corridor(r1.center_x, r1.center_y, r2.center_x, r2.center_y)

        # Mark start room as explored
        self.rooms[0].explored = True

    def _carve_corridor(self, x1, y1, x2, y2):
        """Carve an L-shaped corridor between two points."""
        # Go horizontal first, then vertical
        cx, cy = x1, y1

        # Horizontal
        step_x = 1 if x2 > x1 else -1
        while cx != x2:
            for dy in range(-1, 2):  # 3-wide corridor
                ty = cy + dy
                if 0 <= ty < self.grid_h and 0 <= cx < self.grid_w:
                    self.tiles[ty][cx] = "floor"
            cx += step_x

        # Vertical
        step_y = 1 if y2 > y1 else -1
        while cy != y2:
            for dx in range(-1, 2):  # 3-wide corridor
                tx = cx + dx
                if 0 <= cy < self.grid_h and 0 <= tx < self.grid_w:
                    self.tiles[cy][tx] = "floor"
            cy += step_y

    def is_wall(self, wx, wy):
        """Check if world position is a wall."""
        tx = int(wx // TILE_SIZE)
        ty = int(wy // TILE_SIZE)
        if 0 <= ty < self.grid_h and 0 <= tx < self.grid_w:
            return self.tiles[ty][tx] == "wall"
        return True

    def is_floor(self, tx, ty):
        """Check if tile is walkable."""
        if 0 <= ty < self.grid_h and 0 <= tx < self.grid_w:
            return self.tiles[ty][tx] == "floor"
        return False

    def get_room_at(self, wx, wy) -> Optional[RoomInfo]:
        """Get the room containing a world position."""
        for room in self.rooms:
            if room.contains_world(wx, wy):
                return room
        return None

    @property
    def current_room(self) -> RoomInfo:
        return self.rooms[self.current_room_id]

    def update_exploration(self, hero_wx, hero_wy):
        """Mark rooms as explored when hero enters them."""
        room = self.get_room_at(hero_wx, hero_wy)
        if room and not room.explored:
            room.explored = True
            self.current_room_id = room.id
            return room  # Newly explored room (spawn monsters)
        if room:
            self.current_room_id = room.id
        return None

    def get_spawn_world_pos(self, tx, ty):
        """Convert tile spawn position to world center."""
        return (tx * TILE_SIZE + TILE_SIZE // 2, ty * TILE_SIZE + TILE_SIZE // 2)

    def get_start_pos(self):
        """Get hero start position (center of start room) in world coords."""
        r = self.rooms[0]
        return (r.center_x * TILE_SIZE, r.center_y * TILE_SIZE)
