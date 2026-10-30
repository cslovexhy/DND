"""World: the simulation state and rules for one running map (pure; no pygame).

Being extracted from game/session.py step by step (design/06, phase 1). The session (client) owns
input, camera and drawing; the World owns heroes, companions, monsters, spawning and respawning.
Anything the player should see is reported through self.events (see engine/events.py).
"""
import heapq
import itertools
import random

from game.engine.ai import generate_patrol_route, setup_monster_aggro
from game.engine.entities import Condition, Monster
from game.engine.events import FloatText
from game.engine.hero_ai import create_hero_ai
from game.engine.pathfinding import has_line_of_sight
from game.engine.world_map import TILE_SIZE
from game.content.monsters import SPAWN_STATS, respawn_delay
from game.progression import set_hero_level

# --- Demogorgon special skills ---
DEMOGORGON_STEALTH_DELAY = 6.0   # seconds since last attack before auto-stealth
DEMOGORGON_AURA_RADIUS = 90.0    # pixels; aura reaches this far
DEMOGORGON_AURA_SLOW = 0.8       # enemies move at 80% speed (20% slow) in aura


class World:
    def __init__(self, world_map, game_state, hero):
        self.world_map = world_map
        self.dungeon = world_map   # navigation duck-type (is_wall, is_floor, get_start_pos) used by AI/pathfinding
        self.game_state = game_state
        self.hero = hero           # the local player's hero (becomes a list of players in phase 5)
        self.companions = []       # list of (hero_obj, ai_obj) tuples
        self.events = []           # view events produced this frame (engine/events.py)
        # Respawn queue: min-heap of (respawn_at_game_time, seq, SpawnPoint)
        self.respawn_heap = []
        self._respawn_seq = itertools.count()  # tiebreaker so equal times never compare SpawnPoint objects
        # Hooks the client sets to decorate new entities (e.g. attach sprites) without the sim knowing about art
        self.on_monster_spawned = None
        self.on_companion_spawned = None

    # --- helpers ---
    def is_wall(self, wx, wy):
        return self.dungeon.is_wall(wx, wy)

    def check_los(self, x1, y1, x2, y2):
        """Line of sight between two world positions on the active map."""
        return has_line_of_sight(self.dungeon, x1, y1, x2, y2)

    def float_text(self, x, y, text, color):
        self.events.append(FloatText(x, y, text, color))

    def find_walkable_nearby(self, x, y, radius=60, attempts=20):
        """Find a walkable position near (x, y). Returns (wx, wy) or (x, y) as fallback."""
        for _ in range(attempts):
            nx = x + random.randint(-radius, radius)
            ny = y + random.randint(-radius, radius)
            if not self.is_wall(nx, ny):
                return nx, ny
        # Fallback: try the exact point
        if not self.is_wall(x, y):
            return x, y
        # Last resort: spiral outward to find any walkable tile
        for r in range(1, radius // TILE_SIZE + 3):
            for dx in range(-r, r + 1):
                for dy in range(-r, r + 1):
                    tx = x + dx * TILE_SIZE
                    ty = y + dy * TILE_SIZE
                    if not self.is_wall(tx, ty):
                        return tx, ty
        return x, y

    # --- spawning ---
    def spawn_companion(self, comp_info):
        """Summon an AI companion of the given class. Its level is fixed at the player's CURRENT level
        when summoned (it does not level up afterwards). Returns the companion hero."""
        hero = self.hero
        cx, cy = self.find_walkable_nearby(hero.x, hero.y, radius=60)
        comp = comp_info["create"](comp_info["companion_name"], cx, cy)
        if self.on_companion_spawned:
            self.on_companion_spawned(comp, comp_info)
        set_hero_level(comp, hero.level)
        comp_ai = create_hero_ai(comp)
        comp_ai.set_nav_dungeon(self.dungeon)
        comp_ai.clock = lambda: self.game_state.game_time
        # Give AI access to all heroes for ally-targeting abilities
        if hasattr(comp_ai, 'allies'):
            comp_ai.allies = self.game_state.heroes
        self.companions.append((comp, comp_ai))
        self.game_state.heroes.append(comp)
        return comp

    def spawn_single_world_monster(self, sp):
        """Spawn a single monster from a SpawnPoint. Returns the Monster or None."""
        mt = SPAWN_STATS.get(sp.type)
        if mt is None:
            return None
        wx, wy = self.world_map.get_spawn_world_pos(sp.x, sp.y)
        is_boss = mt.get("boss", False)
        m = Monster(mt["name"], "Monster", wx, wy,
                    hp=mt["hp"], ac=mt["ac"], speed=mt["speed"],
                    attack_bonus=mt["atk"], attack_damage=mt["dmg"],
                    experience=mt["xp"], is_boss=is_boss)
        if self.on_monster_spawned:
            self.on_monster_spawned(m)
        m.unique = mt.get("unique", False)  # one-of-a-kind minion: name shown, but respawns/leashes like a normal mob
        if mt.get("condition"):
            m.on_hit_condition = mt["condition"]
        if mt.get("ranged"):
            m.ranged_attack_range = 250
            m.ranged_attack_damage = m.base_damage
        if mt.get("relentless"):
            m.relentless = True  # never leash-resets aggro (set before setup_monster_aggro)
        if mt.get("hive_mind"):
            m.hive_mind = mt["hive_mind"]  # (range, [spawn_types]) — type-filtered aggro share
        m.spawn_type = sp.type  # spawn-type key (e.g. "demogorgon") for hive_mind matching
        # Track spawn origin for respawn system
        m.spawn_point = sp
        setup_monster_aggro(m, nav_dungeon=self.dungeon)
        generate_patrol_route(m, patrol_radius=100, collision_fn=self.is_wall)
        return m

    def spawn_world_map_monsters(self):
        """Spawn all monsters from world map spawn data."""
        for sp in self.world_map.get_monster_spawns():
            m = self.spawn_single_world_monster(sp)
            if m:
                self.game_state.monsters.append(m)

    # --- respawning ---
    def queue_respawn(self, m):
        """Queue a killed monster's spawn point for respawn (bosses just take much longer)."""
        if hasattr(m, 'spawn_point') and m.spawn_point:
            heapq.heappush(self.respawn_heap, (self.game_state.game_time + respawn_delay(m),
                                               next(self._respawn_seq), m.spawn_point))

    def process_respawns(self):
        """Respawn any mobs whose time has come."""
        gs = self.game_state
        while self.respawn_heap and self.respawn_heap[0][0] <= gs.game_time:
            _, _, sp = heapq.heappop(self.respawn_heap)
            m = self.spawn_single_world_monster(sp)
            if m:
                gs.monsters.append(m)

    # --- Demogorgon special skills ---
    def update_demogorgon_skills(self, dt):
        """Per-frame skills for every Demogorgon:
        1. Auto-stealth: becomes invisible after DEMOGORGON_STEALTH_DELAY seconds have
           passed since its last attack; reveals the moment it attacks.
        2. Aura: slows nearby heroes by 20% (SLOWED) and shows a blue "chill" visual on
           the player (visual only — not a real freeze/movement lock).
        """
        hero = self.hero
        gs = self.game_state
        # Decay the player's chill visual each frame (re-set to 0.3 while in an aura).
        if getattr(hero, 'chill_visual', 0.0) > 0:
            hero.chill_visual = max(0.0, hero.chill_visual - dt)
        for m in gs.monsters:
            if not m.alive or m.name != "Demogorgon":
                continue

            # 1) Auto-stealth based purely on time since last attack.
            #    (_last_attack_time is stamped in the AI loop when it lands a hit.)
            #    Taking ANY damage (single-target or AoE) also counts as activity and
            #    reveals it, restarting the stealth timer.
            if getattr(m, 'was_hit', False):
                m._last_attack_time = gs.game_time
                m.was_hit = False
            last_atk = getattr(m, '_last_attack_time', None)
            if last_atk is None:
                # Never attacked yet — start stealthed after the delay from spawn.
                m._last_attack_time = -DEMOGORGON_STEALTH_DELAY
                last_atk = m._last_attack_time
            if gs.game_time - last_atk >= DEMOGORGON_STEALTH_DELAY:
                m.stealthed = True
            else:
                m.stealthed = False

            # 2) Slow / chill aura — affects heroes (player + companions) in radius.
            #    Gameplay effect is a 20% slow (NOT a movement lock). The player also
            #    gets a visual blue "chill" marker so the aura reads on-screen.
            targets = [hero] + [c for c, _ in self.companions]
            for t in targets:
                if not t.alive:
                    continue
                if m.distance_to(t) <= DEMOGORGON_AURA_RADIUS:
                    # 20% slow (refreshed each frame so it persists while in aura)
                    t.apply_condition(Condition.SLOWED, 0.3, source="Demogorgon Aura",
                                      slow_factor=DEMOGORGON_AURA_SLOW)
                    # Blue chill VISUAL on the player (not a real freeze) — timer-based
                    # so it fades shortly after leaving the aura.
                    if t is hero:
                        t.chill_visual = 0.3
