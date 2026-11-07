"""Patch diagonal wall gaps in map data (pure; no pygame). Used by the map editor on every save.

A "diagonal gap" is a 2x2 block of tiles whose only two unwalkable tiles touch at a corner:

    # .        . #
    . #   or   # .

Players could walk diagonally between those two walls. The fix: make one of the two open tiles of the block
unwalkable too (its art stays; only "walkable" changes, like painting walkability in the editor). A patch can create
a new gap next to it, so this repeats until none are left.

Which open tile gets blocked: one with no spawn / NPC / hero start on it, preferring the one that already touches
more walls (it fills a corner).
An open tile with no art at all (empty void) gets a copy of one of the two touching wall tiles (the wall grows by
one tile), since there is no cell to flag.
"""

LAYERS = ("ground", "objects")   # the layers that decide walkability in the game (objects over ground)


def _cells(data):
    layers = {l.get("name"): l.get("tiles") for l in data.get("layers", [])}
    return layers.get("ground"), layers.get("objects")


def _top_cell(data, x, y):
    """The cell that decides walkability at (x, y): the objects cell if any, else the ground cell (or None)."""
    ground, objects = _cells(data)
    for tiles in (objects, ground):
        if tiles is not None and tiles[y][x] is not None:
            return tiles[y][x]
    return None


def walk_grid(data):
    """grid[y][x] = True if the tile is walkable."""
    w, h = data["width"], data["height"]
    grid = []
    for y in range(h):
        row = []
        for x in range(w):
            cell = _top_cell(data, x, y)
            row.append(True if cell is None else bool(cell.get("walkable", True)))
        grid.append(row)
    return grid


def _open(grid, x, y):
    return 0 <= y < len(grid) and 0 <= x < len(grid[0]) and grid[y][x]


def find_diagonal_gaps(data, grid=None):
    """Top-left corners (x, y) of every 2x2 block whose only two walls touch at a corner."""
    grid = grid or walk_grid(data)
    h, w = len(grid), len(grid[0]) if grid else 0
    walls = {(x, y) for y in range(h) for x in range(w) if not grid[y][x]}
    gaps = set()
    for (x, y) in walls:
        # the four 2x2 blocks that contain this wall; the diagonal partner is the opposite corner of each
        for dx, dy in ((1, 1), (-1, 1), (1, -1), (-1, -1)):
            px, py = x + dx, y + dy
            if 0 <= px < w and 0 <= py < h and (px, py) in walls \
                    and (px, y) not in walls and (x, py) not in walls:
                gaps.add((min(x, px), min(y, py)))
    return sorted(gaps)


def _occupied(data):
    """Tiles that must stay walkable: spawns (incl. the hero start) and NPCs."""
    return {(s["x"], s["y"]) for s in data.get("spawns", [])} | {(n["x"], n["y"]) for n in data.get("npcs", [])}


def _walls_around(grid, x, y):
    return sum(1 for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)) if not _open(grid, nx, ny))


def _put_wall_copy(data, tile, walls):
    """Empty tile: copy the art of a touching wall cell into the ground layer, unwalkable."""
    ground, _ = _cells(data)
    src = next((_top_cell(data, *w) for w in walls if _top_cell(data, *w) is not None), None)
    x, y = tile
    if ground is not None and src is not None:
        ground[y][x] = {"col": src["col"], "row": src["row"], "walkable": False}
    elif ground is not None:
        ground[y][x] = {"col": 0, "row": 0, "walkable": False}


def patch_diagonal_gaps(data, max_rounds=500):
    """Block one open tile of every diagonal gap (in place) until none are left.
    Returns (patched tiles [(x, y), ...], gaps that could not be patched [(x, y), ...])."""
    grid = walk_grid(data)
    occupied = _occupied(data)
    patched, unfixable = [], set()
    for _ in range(max_rounds):
        gaps = [g for g in find_diagonal_gaps(data, grid) if g not in unfixable]
        if not gaps:
            break
        gx, gy = gaps[0]
        block = [(gx, gy), (gx + 1, gy), (gx, gy + 1), (gx + 1, gy + 1)]
        # candidates: the open tiles of the block with nothing standing on them
        cands = [t for t in block if grid[t[1]][t[0]] and t not in occupied]
        if not cands:
            unfixable.add((gx, gy))
            continue
        best = min(cands, key=lambda t: (_top_cell(data, *t) is None, -_walls_around(grid, *t), t))
        cell = _top_cell(data, *best)
        if cell is not None:
            cell["walkable"] = False                      # same art, now blocked
        else:
            _put_wall_copy(data, best, [t for t in block if not grid[t[1]][t[0]]])
        grid[best[1]][best[0]] = False
        patched.append(best)
    return patched, sorted(unfixable)
