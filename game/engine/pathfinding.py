"""
A* pathfinding on the unified dungeon grid.
"""
import heapq
from typing import Optional

TILE_SIZE = 48


_NEIGHBOURS = [(dx, dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if (dx, dy) != (0, 0)]
_INF = float("inf")


def _floor_lookup(dungeon):
    """Fast is_floor(tx, ty) for a map with a precomputed walk grid; falls back to dungeon.is_floor."""
    walk = getattr(dungeon, "walk", None)
    if walk is None:
        return dungeon.is_floor
    w, h = len(walk[0]) if walk else 0, len(walk)

    def floor(x, y):
        return 0 <= x < w and 0 <= y < h and walk[y][x]
    return floor


def astar(dungeon, start_wx, start_wy, goal_wx, goal_wy, max_steps=200, fallback_direct=True):
    """
    A* pathfinding from world pos to world pos.
    Returns list of world (x, y) waypoints, or empty if no path.

    max_steps: search budget (x10 node expansions); None = the whole map (always finds a path if one exists).
    fallback_direct: when no path is found within the budget, return [goal] (a straight line). Fine for callers
    that move with wall collision (monsters) or only want a distance estimate; heroes pass False — a straight
    line used to walk them through walls.
    """
    if max_steps is None:
        max_steps = max(200, (getattr(dungeon, "width", 0) * getattr(dungeon, "height", 0)) // 10 + 1)
    floor = _floor_lookup(dungeon)
    sx = int(start_wx // TILE_SIZE)
    sy = int(start_wy // TILE_SIZE)
    gx = int(goal_wx // TILE_SIZE)
    gy = int(goal_wy // TILE_SIZE)

    # Clamp goal to valid floor
    if not floor(gx, gy):
        # Search nearby for walkable tile
        found = False
        for r in range(1, 4):
            for dx in range(-r, r+1):
                for dy in range(-r, r+1):
                    if floor(gx+dx, gy+dy):
                        gx, gy = gx+dx, gy+dy
                        found = True
                        break
                if found: break
            if found: break
        if not found:
            return []

    if (sx, sy) == (gx, gy):
        return []

    open_set = []
    heappush, heappop = heapq.heappush, heapq.heappop
    g_get = None  # set below
    heappush(open_set, (0, (sx, sy)))
    came_from = {}
    g_score = {(sx, sy): 0}
    g_get = g_score.get
    steps = 0

    while open_set and steps < max_steps * 10:
        steps += 1
        _, current = heappop(open_set)

        if current == (gx, gy):
            # Reconstruct path as world positions
            path = []
            while current in came_from:
                path.append((current[0] * TILE_SIZE + TILE_SIZE//2,
                             current[1] * TILE_SIZE + TILE_SIZE//2))
                current = came_from[current]
            path.reverse()
            # Simplify: skip every other waypoint for smoother movement
            return path[::2] if len(path) > 4 else path

        cx, cy = current
        g_cur = g_score[current]
        for dx, dy in _NEIGHBOURS:              # same order as before => identical paths
            nx, ny = cx + dx, cy + dy
            if not floor(nx, ny):
                continue
            # Diagonal: check adjacent cells
            if dx != 0 and dy != 0:
                if not floor(cx + dx, cy) or not floor(cx, cy + dy):
                    continue
            tentative = g_cur + (1.414 if (dx != 0 and dy != 0) else 1.0)
            neighbor = (nx, ny)
            if tentative < g_get(neighbor, _INF):
                came_from[neighbor] = current
                g_score[neighbor] = tentative
                heappush(open_set, (tentative + abs(nx - gx) + abs(ny - gy), neighbor))

    # No path found within the budget
    return [(goal_wx, goal_wy)] if fallback_direct else []


def has_line_of_sight(dungeon, x1, y1, x2, y2):
    """
    Check if there's a clear line of sight between two world-pixel positions.
    Uses Bresenham's line on the tile grid. Returns True if no wall blocks the path.
    """
    tx1 = int(x1 // TILE_SIZE)
    ty1 = int(y1 // TILE_SIZE)
    tx2 = int(x2 // TILE_SIZE)
    ty2 = int(y2 // TILE_SIZE)

    dx = abs(tx2 - tx1)
    dy = abs(ty2 - ty1)
    sx = 1 if tx1 < tx2 else -1
    sy = 1 if ty1 < ty2 else -1
    err = dx - dy

    while True:
        # Skip the start tile (entity is standing there)
        if (tx1, ty1) != (int(x1 // TILE_SIZE), int(y1 // TILE_SIZE)):
            if not dungeon.is_floor(tx1, ty1):
                return False

        if tx1 == tx2 and ty1 == ty2:
            break

        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            tx1 += sx
        if e2 < dx:
            err += dx
            ty1 += sy

    return True
