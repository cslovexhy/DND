"""Actions in progress on any entity (pure; no pygame): a dash (Charge) and a channel (Frostbolt, Holy Light).

They live on the entity (`entity.dash`, `entity.channel`), not on a player, so a monster can charge or channel
exactly like a hero. update_actions(world, e, dt) advances both; the World calls it for every living entity.
"""
import math
from dataclasses import dataclass, field

from game.engine.entities import Condition
from game.engine.pathfinding import astar
from game.engine.world_map import TILE_SIZE

DASH_SPEED = 800.0      # px/s
DASH_ARRIVE_PX = 10.0


# --- moving on the map (shared by walking and dashing) ----------------------------------------------------------

def walk_path(world, ax, ay, bx, by):
    """Walking path from (ax, ay) to (bx, by) over the whole map; [] when it can't be reached (never a straight line
    through walls)."""
    return astar(world.dungeon, ax, ay, bx, by, max_steps=None, fallback_direct=False)


def step_toward(world, e, tx, ty, dist, spd):
    """Move `e` up to `spd` px toward (tx, ty), `dist` away, sliding along walls; False if completely blocked."""
    wall = world.is_wall
    step = min(spd, dist)
    nx = e.x + (tx - e.x) / dist * step
    ny = e.y + (ty - e.y) / dist * step
    if not wall(nx, ny):
        e.x, e.y = nx, ny
    elif not wall(nx, e.y):
        e.x = nx
    elif not wall(e.x, ny):
        e.y = ny
    else:
        return False
    return True


# --- dash ---------------------------------------------------------------------------------------------------------

@dataclass(eq=False)
class Dash:
    path: list
    target: object
    on_arrive: object = None          # on_arrive(world, entity, target): the hit at the end (Charge: damage + stun)
    speed: float = DASH_SPEED


def start_dash(world, e, tx, ty, target, on_arrive):
    """Dash `e` to (tx, ty) along a walking path (around walls, however long the detour). False — and nothing
    happens — only if there is no walking path at all."""
    path = walk_path(world, e.x, e.y, tx, ty)
    if not path:
        # [] means unreachable — or already on the target's tile (then a short straight hop is fine)
        same_tile = (int(e.x // TILE_SIZE), int(e.y // TILE_SIZE)) == (int(tx // TILE_SIZE), int(ty // TILE_SIZE))
        if not same_tile:
            return False
    if not world.is_wall(tx, ty) and (not path or path[-1] != (tx, ty)):
        path = path + [(tx, ty)]          # finish exactly at the dash point when it is walkable
    if not path:
        return False
    e.dash = Dash(path, target, on_arrive)
    return True


def _update_dash(world, e, dt):
    d = e.dash
    path = d.path
    while len(path) > 1 and math.hypot(path[0][0] - e.x, path[0][1] - e.y) < DASH_ARRIVE_PX:
        path.pop(0)
    wx, wy = path[0]
    dx, dy = wx - e.x, wy - e.y
    dist = math.hypot(dx, dy)
    if dist < DASH_ARRIVE_PX and len(path) == 1:
        e.dash = None
        if not world.is_wall(wx, wy):
            e.x, e.y = wx, wy
        if d.on_arrive is not None and d.target is not None and d.target.alive:
            d.on_arrive(world, e, d.target)
        return
    if dist > 0 and not step_toward(world, e, wx, wy, dist, d.speed * dt):
        d.path = [(e.x, e.y)]             # blocked (shouldn't happen on a path): end the dash here
    e.facing_left = dx < 0


# --- channel ------------------------------------------------------------------------------------------------------

@dataclass(eq=False)
class Channel:
    skill: str
    total: float
    remaining: float
    target: object
    on_complete: object               # on_complete(world, entity, target)
    needs_target: bool = True         # cancelled when the target dies (Frostbolt); a heal falls back to the caster
    data: dict = field(default_factory=dict)

    @property
    def progress(self):
        return 1.0 - self.remaining / self.total if self.total > 0 else 1.0


def start_channel(world, e, skill, secs, target, on_complete, needs_target=True, **data):
    """Channel for `secs` (immobile) and then run on_complete(world, e, target)."""
    e.channel = Channel(skill, secs, secs, target, on_complete, needs_target, data)
    e.apply_condition(Condition.IMMOBILIZED, secs)


def cancel_channel(e):
    """Stop a channel early (nothing happens) and free the caster."""
    if e.channel is not None:
        e.channel = None
        e.conditions = [c for c in e.conditions if c.condition != Condition.IMMOBILIZED]


def _update_channel(world, e, dt):
    c = e.channel
    c.remaining -= dt
    if c.remaining <= 0:
        e.channel = None
        c.on_complete(world, e, c.target)
    elif c.needs_target and (c.target is None or not c.target.alive):
        cancel_channel(e)                 # the target died mid-channel


def update_actions(world, e, dt):
    """One frame of `e`'s channel and dash."""
    if e.channel is not None:
        _update_channel(world, e, dt)
    if e.dash is not None:
        _update_dash(world, e, dt)
