"""
A* pathfinding on the unified dungeon grid.
"""
import heapq
from typing import Optional

TILE_SIZE = 48


def astar(dungeon, start_wx, start_wy, goal_wx, goal_wy, max_steps=200):
    """
    A* pathfinding from world pos to world pos.
    Returns list of world (x, y) waypoints, or empty if no path.
    """
    sx = int(start_wx // TILE_SIZE)
    sy = int(start_wy // TILE_SIZE)
    gx = int(goal_wx // TILE_SIZE)
    gy = int(goal_wy // TILE_SIZE)

    # Clamp goal to valid floor
    if not dungeon.is_floor(gx, gy):
        # Search nearby for walkable tile
        found = False
        for r in range(1, 4):
            for dx in range(-r, r+1):
                for dy in range(-r, r+1):
                    if dungeon.is_floor(gx+dx, gy+dy):
                        gx, gy = gx+dx, gy+dy
                        found = True
                        break
                if found: break
            if found: break
        if not found:
            return []

    if (sx, sy) == (gx, gy):
        return []

    def heuristic(a, b):
        return abs(a[0]-b[0]) + abs(a[1]-b[1])

    open_set = []
    heapq.heappush(open_set, (0, (sx, sy)))
    came_from = {}
    g_score = {(sx, sy): 0}
    steps = 0

    while open_set and steps < max_steps * 10:
        steps += 1
        _, current = heapq.heappop(open_set)

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

        for dx in [-1, 0, 1]:
            for dy in [-1, 0, 1]:
                if dx == 0 and dy == 0:
                    continue
                nx, ny = current[0]+dx, current[1]+dy
                if not dungeon.is_floor(nx, ny):
                    continue
                # Diagonal: check adjacent cells
                if dx != 0 and dy != 0:
                    if not dungeon.is_floor(current[0]+dx, current[1]) or \
                       not dungeon.is_floor(current[0], current[1]+dy):
                        continue

                cost = 1.414 if (dx != 0 and dy != 0) else 1.0
                tentative = g_score[current] + cost
                neighbor = (nx, ny)

                if tentative < g_score.get(neighbor, float('inf')):
                    came_from[neighbor] = current
                    g_score[neighbor] = tentative
                    heapq.heappush(open_set, (tentative + heuristic(neighbor, (gx, gy)), neighbor))

    # No path found — just return direct point
    return [(goal_wx, goal_wy)]


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
