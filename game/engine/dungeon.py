"""
Dungeon generator — produces connected rooms for an adventure.
Based on the D&D Adventure System tile-stack mechanic:
- Rooms are generated in a semi-linear graph
- Quest rooms placed at specific depths
- White/black triangle determines danger level
"""
import random
import math
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional


class RoomType(Enum):
    STANDARD = auto()    # White triangle — monsters spawn, no extra event
    DANGEROUS = auto()   # Black triangle — monsters + encounter event
    QUEST = auto()       # Named tile — boss or objective
    START = auto()       # Starting room
    TREASURE = auto()    # Optional side room with chest


class Direction(Enum):
    NORTH = auto()
    SOUTH = auto()
    EAST = auto()
    WEST = auto()

    @property
    def opposite(self):
        return {
            Direction.NORTH: Direction.SOUTH,
            Direction.SOUTH: Direction.NORTH,
            Direction.EAST: Direction.WEST,
            Direction.WEST: Direction.EAST,
        }[self]

    @property
    def dx_dy(self):
        return {
            Direction.NORTH: (0, -1),
            Direction.SOUTH: (0, 1),
            Direction.EAST: (1, 0),
            Direction.WEST: (-1, 0),
        }[self]


@dataclass
class Door:
    direction: Direction
    target_room_id: int
    x: int  # position in room grid
    y: int


@dataclass
class Room:
    id: int
    room_type: RoomType
    name: str = ""
    grid_x: int = 0  # position in dungeon graph
    grid_y: int = 0

    # Room layout
    width: int = 15   # tiles wide
    height: int = 11  # tiles tall
    tiles: list = field(default_factory=list)  # 2D grid: "floor", "wall"
    
    # Connections
    doors: list = field(default_factory=list)
    
    # Content
    monster_spawns: list = field(default_factory=list)  # [(x, y), ...]
    has_chest: bool = False
    chest_pos: tuple = (0, 0)
    
    # State
    explored: bool = False
    cleared: bool = False
    monsters_spawned: bool = False

    # World position (in pixels, computed after layout)
    world_x: float = 0.0
    world_y: float = 0.0


TILE_SIZE = 48  # pixels per tile (16 * 3 scale)


def generate_room_tiles(width: int, height: int, num_pillars: int = 0) -> list[list[str]]:
    """Generate a room grid with walls on edges and optional pillars."""
    tiles = []
    for ry in range(height):
        row = []
        for rx in range(width):
            if rx == 0 or rx == width-1 or ry == 0 or ry == height-1:
                row.append("wall")
            else:
                row.append("floor")
        tiles.append(row)

    # Add random pillars (not near edges or doors)
    for _ in range(num_pillars):
        px = random.randint(3, width-4)
        py = random.randint(3, height-4)
        tiles[py][px] = "wall"

    return tiles


def place_door(tiles: list[list[str]], direction: Direction, width: int, height: int) -> tuple[int, int]:
    """Place a door opening on a wall. Returns (x, y) of door position."""
    if direction == Direction.NORTH:
        x = width // 2
        y = 0
    elif direction == Direction.SOUTH:
        x = width // 2
        y = height - 1
    elif direction == Direction.WEST:
        x = 0
        y = height // 2
    elif direction == Direction.EAST:
        x = width - 1
        y = height // 2

    # Clear the door area (3 tiles wide for walkability)
    if direction in (Direction.NORTH, Direction.SOUTH):
        for dx in range(-1, 2):
            if 0 <= x+dx < width:
                tiles[y][x+dx] = "floor"
    else:
        for dy in range(-1, 2):
            if 0 <= y+dy < height:
                tiles[y+dy][x] = "floor"

    return (x, y)


def generate_monster_spawns(tiles: list[list[str]], count: int, width: int, height: int) -> list[tuple[int, int]]:
    """Pick spawn points along room edges (not in walls)."""
    spawns = []
    candidates = []
    for ry in range(2, height-2):
        for rx in range(2, width-2):
            if tiles[ry][rx] == "floor":
                # Prefer edges
                edge_dist = min(rx, ry, width-1-rx, height-1-ry)
                if edge_dist <= 2:
                    candidates.append((rx, ry))

    random.shuffle(candidates)
    return candidates[:count]


class Dungeon:
    """A complete dungeon layout for one adventure."""

    def __init__(self):
        self.rooms: list[Room] = []
        self.current_room_id: int = 0
        self.corridor_length: int = 3  # tiles of corridor between rooms

    def generate(self, num_rooms: int = 8, quest_room_depth: int = -1,
                 quest_room_name: str = "Boss Room"):
        """
        Generate a dungeon with connected rooms.
        
        Args:
            num_rooms: Total rooms on critical path
            quest_room_depth: Where to place quest room (-1 = last room)
            quest_room_name: Name of the quest/boss room
        """
        if quest_room_depth < 0:
            quest_room_depth = num_rooms - 1

        self.rooms = []

        # Generate rooms along a mostly-linear path with some branches
        # Use grid positions to track layout
        used_positions = set()
        
        # Critical path
        cx, cy = 0, 0
        last_dir = None

        for i in range(num_rooms):
            # Determine room type
            if i == 0:
                rtype = RoomType.START
                name = "Start"
            elif i == quest_room_depth:
                rtype = RoomType.QUEST
                name = quest_room_name
            elif random.random() < 0.3:
                rtype = RoomType.DANGEROUS
                name = f"Room {i+1}"
            else:
                rtype = RoomType.STANDARD
                name = f"Room {i+1}"

            # Create room
            room = Room(
                id=i,
                room_type=rtype,
                name=name,
                grid_x=cx,
                grid_y=cy,
                width=random.choice([13, 15, 17]) if rtype != RoomType.START else 15,
                height=random.choice([9, 11, 13]) if rtype != RoomType.START else 11,
            )

            # Generate tiles
            num_pillars = random.randint(1, 4) if rtype != RoomType.START else 0
            room.tiles = generate_room_tiles(room.width, room.height, num_pillars)

            # Monster spawn points
            if rtype == RoomType.START:
                spawn_count = 0
            elif rtype == RoomType.QUEST:
                spawn_count = 1  # Boss only
            elif rtype == RoomType.DANGEROUS:
                spawn_count = random.randint(3, 5)
            else:
                spawn_count = random.randint(2, 4)
            room.monster_spawns = generate_monster_spawns(
                room.tiles, spawn_count, room.width, room.height)

            # Treasure chest in some rooms
            if rtype in (RoomType.STANDARD, RoomType.DANGEROUS) and random.random() < 0.3:
                room.has_chest = True
                room.chest_pos = (room.width // 2 + random.randint(-2, 2),
                                  room.height // 2 + random.randint(-2, 2))

            self.rooms.append(room)
            used_positions.add((cx, cy))

            # Pick direction for next room
            if i < num_rooms - 1:
                possible_dirs = [d for d in Direction
                                 if (cx + d.dx_dy[0], cy + d.dx_dy[1]) not in used_positions]
                if last_dir and last_dir in possible_dirs and random.random() < 0.5:
                    chosen_dir = last_dir  # Tend to continue same direction
                elif possible_dirs:
                    chosen_dir = random.choice(possible_dirs)
                else:
                    # Fallback: force a direction
                    chosen_dir = random.choice(list(Direction))

                last_dir = chosen_dir
                cx += chosen_dir.dx_dy[0]
                cy += chosen_dir.dx_dy[1]

        # Connect rooms with doors
        for i in range(len(self.rooms) - 1):
            room_a = self.rooms[i]
            room_b = self.rooms[i + 1]

            # Determine direction from A to B
            dx = room_b.grid_x - room_a.grid_x
            dy = room_b.grid_y - room_a.grid_y

            if dx > 0:
                dir_ab = Direction.EAST
            elif dx < 0:
                dir_ab = Direction.WEST
            elif dy > 0:
                dir_ab = Direction.SOUTH
            else:
                dir_ab = Direction.NORTH

            # Place doors
            door_a_pos = place_door(room_a.tiles, dir_ab, room_a.width, room_a.height)
            door_b_pos = place_door(room_b.tiles, dir_ab.opposite, room_b.width, room_b.height)

            room_a.doors.append(Door(dir_ab, room_b.id, *door_a_pos))
            room_b.doors.append(Door(dir_ab.opposite, room_a.id, *door_b_pos))

        # Compute world positions
        self._compute_world_positions()

        # Start room is explored
        self.rooms[0].explored = True
        self.current_room_id = 0

    def _compute_world_positions(self):
        """Assign world pixel positions to each room based on grid coords."""
        for room in self.rooms:
            # Each room occupies its width + corridor space
            room.world_x = room.grid_x * (17 * TILE_SIZE + self.corridor_length * TILE_SIZE)
            room.world_y = room.grid_y * (13 * TILE_SIZE + self.corridor_length * TILE_SIZE)

    def get_room(self, room_id: int) -> Optional[Room]:
        if 0 <= room_id < len(self.rooms):
            return self.rooms[room_id]
        return None

    @property
    def current_room(self) -> Room:
        return self.rooms[self.current_room_id]

    def enter_room(self, room_id: int):
        """Player enters a room — mark explored, trigger spawns."""
        room = self.get_room(room_id)
        if room:
            room.explored = True
            self.current_room_id = room_id

    def is_wall(self, room: Room, world_x: float, world_y: float) -> bool:
        """Check if a world position is a wall in the given room."""
        # Convert world pos to tile coordinates within room
        local_x = world_x - room.world_x
        local_y = world_y - room.world_y
        tx = int(local_x // TILE_SIZE)
        ty = int(local_y // TILE_SIZE)

        if 0 <= ty < room.height and 0 <= tx < room.width:
            return room.tiles[ty][tx] == "wall"
        return True  # Out of bounds = wall

    def get_door_at(self, room: Room, world_x: float, world_y: float) -> Optional[Door]:
        """Check if position is near a door. Returns the Door or None."""
        local_x = world_x - room.world_x
        local_y = world_y - room.world_y
        tx = int(local_x // TILE_SIZE)
        ty = int(local_y // TILE_SIZE)

        for door in room.doors:
            if abs(tx - door.x) <= 1 and abs(ty - door.y) <= 1:
                return door
        return None
