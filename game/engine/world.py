"""World: the simulation state and rules for one running map (pure; no pygame).

Being extracted from game/session.py step by step (design/06, phase 1). The session (client) owns
input, camera and drawing; the World owns heroes, companions, monsters, spawning and respawning.
Anything the player should see is reported through self.events (see engine/events.py).
"""
import heapq
import itertools
import math
import random

from game.engine import abilities
from game.content.heroes import HERO_CLASSES
from game.engine.ai import (generate_patrol_route, setup_monster_aggro, aggro_monster, call_for_help,
                            run_monster_ai, AggroState)
from game.engine.entities import Condition, Monster, Projectile
from game.engine.events import FloatText, Ring, LevelUp, QuestReady, NpcDialogue, GOLD, HP_RED
from game.engine.hero_ai import create_hero_ai
from game.engine.npc import NPC
from game.engine.snapshot import quest_info
from game.engine.pathfinding import astar, has_line_of_sight
from game.engine.world_map import TILE_SIZE
from game.content.monsters import SPAWN_STATS, respawn_delay
from game.progression import (MAX_LEVEL, xp_to_next_level, apply_level_growth, set_hero_level, growth_for)

# --- Demogorgon special skills ---
DEMOGORGON_STEALTH_DELAY = 6.0   # seconds since last attack before auto-stealth
DEMOGORGON_AURA_RADIUS = 90.0    # pixels; aura reaches this far
DEMOGORGON_AURA_SLOW = 0.8       # enemies move at 80% speed (20% slow) in aura


class World:
    def __init__(self, world_map, game_state, hero, quests=None, debug=False):
        self.debug = debug
        self.quests = quests       # player 0's QuestLog for this map (each PlayerState has its own)
        self.projectiles = []      # active projectiles (Wanding, Frostbolt, monster arrows)
        self.world_map = world_map
        self.dungeon = world_map   # navigation duck-type (is_wall, is_floor, get_start_pos) used by AI/pathfinding
        self.game_state = game_state
        self.hero = hero           # player 0's hero (the host's own player); other players: self.players
        self.companions = []       # list of (hero_obj, ai_obj) tuples
        self.events = []           # view events produced this frame (engine/events.py)
        # Respawn queue: min-heap of (respawn_at_game_time, seq, SpawnPoint)
        self.respawn_heap = []
        self._respawn_seq = itertools.count()  # tiebreaker so equal times never compare SpawnPoint objects
        # Hooks the client sets to decorate new entities (e.g. attach sprites) without the sim knowing about art
        self.on_monster_spawned = None
        self.on_companion_spawned = None
        self.on_npc_spawned = None
        self.npcs = []
        # Entity registry (stable ids for commands/network) and command queue
        self._next_eid = itertools.count(1)
        self.entities = {}
        self.players = {}          # player_id -> PlayerState
        self.command_queue = []    # (player_id, command), applied at the start of the next frame
        self.command_log = []      # (tick, player_id, command) when recording
        self.tick = 0              # number of completed simulation steps
        self.record_commands = False
        self.register(hero)
        # One AI companion per class other than the player's own (summoned with ToggleCompanion)
        self.available_companions = [c for c in HERO_CLASSES if c["class"] != hero.class_name]

    # --- entity registry and commands ---
    def register(self, entity):
        entity.eid = next(self._next_eid)
        self.entities[entity.eid] = entity
        return entity

    def unregister(self, entity):
        self.entities.pop(entity.eid, None)

    def entity(self, eid):
        return self.entities.get(eid)

    def add_player(self, player_id, player_state):
        player_state.player_id = player_id
        self.players[player_id] = player_state
        if player_state.hero is not self.hero:   # player 0's hero is registered by __init__
            self.game_state.heroes.append(player_state.hero)
            self.register(player_state.hero)

    def remove_player(self, player_id):
        """A player left: remove their hero and their companions from the world."""
        player = self.players.pop(player_id, None)
        if player is None:
            return
        for comp, ai in [c for c in self.companions if getattr(c[0], "owner", None) is player]:
            self.companions.remove((comp, ai))
            self.game_state.heroes.remove(comp)
            self.unregister(comp)
        if player.hero in self.game_state.heroes and player.hero is not self.hero:
            self.game_state.heroes.remove(player.hero)
            self.unregister(player.hero)

    @property
    def player_list(self):
        """Players in a stable order (by id)."""
        return [self.players[pid] for pid in sorted(self.players)]

    @property
    def player_heroes(self):
        return [p.hero for p in self.player_list]

    def player_for_hero(self, hero):
        return next((p for p in self.players.values() if p.hero is hero), None)

    def submit(self, command, player_id=0):
        """Queue a player command; it is applied at the start of the next frame (begin_frame)."""
        self.command_queue.append((player_id, command))

    def _apply_commands(self):
        queue, self.command_queue = self.command_queue, []
        for player_id, cmd in queue:
            if self.record_commands:
                self.command_log.append((self.tick, player_id, cmd))
            player = self.players.get(player_id)
            if player is not None:
                player.handle(cmd)

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
    def spawn_companion(self, comp_info, owner=None):
        """Summon an AI companion of the given class for `owner` (a PlayerState; default player 0).
        Its level is fixed at the owner's CURRENT level when summoned (it does not level up afterwards)."""
        owner = owner or self.players.get(0)
        hero = owner.hero if owner else self.hero
        cx, cy = self.find_walkable_nearby(hero.x, hero.y, radius=60)
        comp = comp_info["create"](comp_info["companion_name"], cx, cy)
        comp.owner = owner       # follows and fights for this player
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
        self.register(comp)
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
        self.register(m)
        return m

    def spawn_world_map_monsters(self):
        """Spawn all monsters from world map spawn data."""
        for sp in self.world_map.get_monster_spawns():
            m = self.spawn_single_world_monster(sp)
            if m:
                self.game_state.monsters.append(m)

    def load_npcs(self):
        """Create NPCs from map data (each map defines its own NPCs in the JSON)."""
        for npc_def in self.world_map.data.get("npcs", []):
            tx, ty = npc_def["x"], npc_def["y"]
            wx, wy = self.world_map.get_spawn_world_pos(tx, ty)
            npc = NPC(self, npc_def["name"], wx, wy, npc_id=npc_def["npc_id"],
                      gender=npc_def.get("gender", "male"))
            npc.sprite_tile = (npc_def["sprite_col"], npc_def["sprite_row"])  # art reference for clients
            if self.on_npc_spawned:
                self.on_npc_spawned(npc, npc_def)
            self.npcs.append(npc)
            self.register(npc)

    def interact_with_npc(self, npc, player=None):
        """Handle quest turn-in and acceptance for a specific NPC and player (default player 0).
        Returns True if interaction happened."""
        player = player or self.players[0]
        hero = player.hero
        quests = player.quests
        pid = player.player_id
        interacted = False
        voice = "Samantha" if npc.gender == "female" else "Daniel"

        # First: turn in any completed quests at this NPC
        for qid in quests.turn_ins_for_npc(npc.npc_id):
            q = quests.turn_in(qid)
            hero.xp += q.rewards_xp
            hero.gold += q.rewards_gold
            self.float_text(hero.x, hero.y - 40, f"+{q.rewards_xp}xp +{q.rewards_gold}g", GOLD)
            self.events.append(NpcDialogue(
                quest_info(q), "turnin", npc.name,
                f"Well done! {q.title} complete. Here's your reward: {q.rewards_xp} experience and {q.rewards_gold} gold.",
                voice, pid))
            interacted = True

        # Second: offer and accept an available quest from this NPC
        if not interacted:  # Don't pile accept on top of turn-in
            for qid in quests.available_for_npc(npc.npc_id, hero.level):
                q = quests.quests[qid]
                if quests.accept(qid):
                    # No-objective quest (intro) — completed and turned in on the spot
                    hero.xp += q.rewards_xp
                    hero.gold += q.rewards_gold
                    mode = "turnin"
                else:
                    mode = "accept"
                self.events.append(NpcDialogue(quest_info(q), mode, npc.name, q.description, voice, pid))
                interacted = True
                break  # One quest popup at a time

        return interacted

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
        gs = self.game_state
        player_heroes = self.player_heroes
        # Decay the players' chill visual each frame (re-set to 0.3 while in an aura).
        for hero in player_heroes:
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
            targets = player_heroes + [c for c, _ in self.companions]
            for t in targets:
                if not t.alive:
                    continue
                if m.distance_to(t) <= DEMOGORGON_AURA_RADIUS:
                    # 20% slow (refreshed each frame so it persists while in aura)
                    t.apply_condition(Condition.SLOWED, 0.3, source="Demogorgon Aura",
                                      slow_factor=DEMOGORGON_AURA_SLOW)
                    # Blue chill VISUAL on the player (not a real freeze) — timer-based
                    # so it fades shortly after leaving the aura.
                    if t in player_heroes:
                        t.chill_visual = 0.3

    # --- kills, XP, quests, level-ups ---
    def process_kills(self):
        """Award XP/gold/quest progress for freshly killed monsters and queue their respawn."""
        # Co-op party rules: every player gets the full XP, their own gold roll, the kill and quest credit.
        for m in self.game_state.monsters:
            if not m.alive and m.experience > 0:
                for player in self.player_list:
                    hero = player.hero
                    hero.xp += m.experience
                    hero.gold += random.randint(10, 30) * m.experience
                    hero.kills += 1
                    if player.player_id == 0 or len(self.players) == 1:
                        self.float_text(m.x, m.y + 10, f"+{m.experience}xp", GOLD)
                    # Quest kill tracking
                    for aq, just_completed in player.quests.record_kill(m.name):
                        self.float_text(hero.x, hero.y - 50, aq.get_progress_text(), (200, 200, 255))
                        if just_completed:
                            self.events.append(QuestReady(aq.title, player.player_id))
                m.experience = 0
                # Queue for respawn (every monster that came from a spawn point; bosses just take much longer)
                self.queue_respawn(m)

    def process_level_ups(self):
        for player in self.player_list:
            hero = player.hero
            while hero.level < MAX_LEVEL and hero.xp >= xp_to_next_level(hero.level):
                hero.xp -= xp_to_next_level(hero.level)
                hero.level += 1
                growth = growth_for(hero.class_name)
                apply_level_growth(hero)  # also full-heals on level-up
                self.events.append(LevelUp(hero.x, hero.y, player.player_id))
                self.float_text(hero.x, hero.y - 30,
                                f"Lv {hero.level}! +{growth['hp']:.0f}HP +{growth['damage']:.0f}dmg", GOLD)

    # --- projectiles ---
    def update_projectiles(self, dt):
        gs = self.game_state
        hero_side = set(map(id, self.player_heroes)) | {id(c) for c, _ in self.companions}
        for proj in self.projectiles:
            result = proj.update(dt)
            if result is not None:
                dmg, hit_target = result
                # Determine if source is a hero (player or companion)
                source_is_hero = id(proj.source) in hero_side
                if source_is_hero:
                    self.float_text(hit_target.x, hit_target.y - 20, f"{dmg:.0f}", proj.color)
                    # Aggro on hit: directly aggro the hit monster + call for help
                    if hasattr(hit_target, 'aggro_state'):
                        if hit_target.aggro_state != "aggroed":
                            aggro_monster(hit_target, proj.source, gs.monsters)
                        call_for_help(hit_target, gs.monsters, proj.source)
                    # Frostbolt slow
                    if getattr(proj, 'apply_slow', False) and hit_target.alive:
                        hit_target.apply_condition(Condition.SLOWED, 3.0, slow_factor=0.25)
                        self.float_text(hit_target.x, hit_target.y - 35, "SLOWED", (150, 200, 255))
                else:
                    # Monster projectile hitting hero
                    self.float_text(hit_target.x + random.randint(-10, 10), hit_target.y - 30, f"{dmg:.0f}", HP_RED)
                    # Apply on-hit condition if any
                    on_hit = getattr(proj, 'on_hit_condition', None)
                    if on_hit and hit_target.alive:
                        cond, dur = on_hit
                        hit_target.apply_condition(cond, dur,
                                                   tick_damage=10.0 if cond == Condition.POISONED else 0)
        self.projectiles[:] = [p for p in self.projectiles if p.alive]

    # --- one simulation step ---
    def step(self, dt):
        """Advance the simulation by dt seconds: apply queued commands, then run every system in order."""
        gs = self.game_state
        alive = self.begin_frame(dt)
        for pid in sorted(self.players):
            player = self.players[pid]
            player.update(dt)
            player.run_ai(dt)          # autopilot, when enabled
            player.update_ambush()
            player.auto_attack()
        self.update_companions(dt)
        self.update_monsters(dt, alive)
        self.process_kills()
        self.process_level_ups()
        self.process_respawns()
        # Game over when every player's hero is down (single player: when the hero dies)
        if self.players and not any(h.alive for h in self.player_heroes):
            gs.adventure_failed = True
        self.update_projectiles(dt)
        # Expire Wall shield when buff expires
        for hero in self.player_heroes:
            if "Wall" not in hero.buffs and hero.absorb_shield > 0:
                hero.absorb_shield = 0
        self.tick += 1

    # --- per-frame start ---
    def begin_frame(self, dt):
        """Start-of-frame bookkeeping: Holy Light completion, combat flags, Demogorgon skills, entity timers.
        Returns the list of alive monsters (snapshot used by the monster AI later this frame)."""
        gs = self.game_state
        self._apply_commands()
        for hero in self.player_heroes:
            # Check Holy Light cast completion BEFORE update (buff gets removed during update)
            if "Holy Light Casting" in hero.buffs and hero.buffs["Holy Light Casting"]["remaining"] <= dt:
                heal_amount = hero.buffs["Holy Light Casting"]["heal"]
                heal = hero.heal(heal_amount)
                self.float_text(hero.x, hero.y - 30, f"+{heal:.0f} HP", (100, 255, 100))
                del hero.buffs["Holy Light Casting"]

            # Update combat state for health regeneration
            hero.in_combat = any(m.alive and getattr(m, 'aggro_target', None) == hero
                                 for m in gs.monsters)
        for comp, _ in self.companions:
            if comp.alive:
                comp.in_combat = any(m.alive and getattr(m, 'aggro_target', None) == comp
                                     for m in gs.monsters)
        for m in gs.monsters:
            if m.alive:
                m.in_combat = getattr(m, 'aggro_state', '') == 'aggroed'

        # --- Demogorgon special skills (auto-stealth + slow/freeze aura) ---
        self.update_demogorgon_skills(dt)

        gs.update(dt)
        alive = gs.alive_monsters
        return alive

    # --- companion AI ---
    def update_companions(self, dt):
        """Run each summoned companion's AI for this frame (combat abilities, then follow the hero)."""
        gs = self.game_state
        for comp, comp_ai in self.companions:
            if not comp.alive:
                continue
            owner = getattr(comp, "owner", None)
            hero = owner.hero if owner is not None else self.hero   # the player this companion follows
            # Track stealth duration
            if comp.stealthed:
                comp._stealth_time = getattr(comp, '_stealth_time', 0) + dt
            comp_action = comp_ai.update(gs.alive_monsters, dt, self.is_wall)

            if comp_action.get("use_potion") and comp.hp < comp.max_hp * 0.4:
                heal = comp.heal(150)
                if heal:
                    self.float_text(comp.x, comp.y - 30, f"+{heal:.0f}", (100, 255, 100))

            comp_acted = False
            if comp_action.get("use_ability"):
                ab_key = comp_action["use_ability"]
                ab = comp.abilities.get(ab_key)
                if ab and ab.is_ready() and comp.gcd <= 0:
                    comp_acted = True
                    target_m = comp_action.get("ability_target_monster")

                    # LOS check for targeted abilities — pathfind if blocked
                    if target_m and not self.check_los(comp.x, comp.y, target_m.x, target_m.y):
                        path = astar(self.dungeon, comp.x, comp.y, target_m.x, target_m.y)
                        if path:
                            comp.move_toward(path[0][0], path[0][1], dt, self.is_wall)
                    # Handle dash abilities (Charge) — just teleport + damage for self.companions
                    elif comp_action.get("dash"):
                        tx, ty, dash_target, dash_dmg, dash_stun = comp_action["dash"]
                        if dash_target and dash_target.alive and comp.distance_to(dash_target) <= 300:
                            if not self.check_los(comp.x, comp.y, dash_target.x, dash_target.y):
                                path = astar(self.dungeon, comp.x, comp.y, dash_target.x, dash_target.y)
                                if path:
                                    comp.move_toward(path[0][0], path[0][1], dt, self.is_wall)
                            else:
                                ab.use()
                                comp.x, comp.y = tx, ty
                                dmg = dash_target.take_damage(dash_dmg)
                                self.float_text(dash_target.x, dash_target.y - 20, f"{dmg:.0f}", (255, 200, 50))
                                if dash_stun > 0 and dash_target.alive:
                                    dash_target.apply_condition(Condition.STUNNED, dash_stun)
                                call_for_help(dash_target, gs.monsters, hero)
                    elif ab.name == "Frost Nova":
                        # Heskan's AoE freeze — specific handler (bypasses swing_timer)
                        ab.use()
                        comp.gcd = comp.GCD_DURATION
                        dmg_amount = ab.calc_damage(comp.base_damage)
                        hit_count = 0
                        for m in gs.alive_monsters:
                            if comp.distance_to(m) <= ab.radius:
                                dmg = m.take_damage(dmg_amount)
                                m.apply_condition(Condition.FROZEN, 4.0)
                                self.float_text(m.x, m.y - 20, f"{dmg:.0f}", (180, 220, 255))
                                hit_count += 1
                        if self.debug:
                            print(f"[COMP_SKILL] {comp.name} Frost Nova hit {hit_count} targets", flush=True)
                        self.events.append(Ring(comp.x, comp.y, ab.radius, (150, 200, 255)))
                    elif ab.name == "Demoralizing Shout":
                        # Vistra's AoE debuff
                        ab.use()
                        comp.gcd = comp.GCD_DURATION
                        hit_count = 0
                        for m in gs.alive_monsters:
                            if comp.distance_to(m) <= ab.radius:
                                m.buffs["Demoralized"] = {"remaining": 10.0, "damage_mult": 0.5}
                                m.apply_condition(Condition.SLOWED, 3.0, slow_factor=0.5)
                                self.float_text(m.x, m.y - 20, "Demoralized!", (200, 150, 50))
                                hit_count += 1
                        if hit_count > 0:
                            self.events.append(Ring(comp.x, comp.y, ab.radius, ab.color))
                    elif ab.radius > 0:
                        # AoE (generic)
                        hits = comp.use_ability(ab_key, gs.alive_monsters, target_pos=(comp.x, comp.y))
                        if hits:
                            self.events.append(Ring(comp.x, comp.y, ab.radius, ab.color))
                            for name, dmg in hits:
                                self.float_text(comp.x, comp.y - 20, f"{dmg:.0f}", GOLD)
                    elif ab.name == "Wanding" and target_m and target_m.alive:
                        # Quinn's ranged projectile
                        if comp.swing_timer <= 0 and abilities.can_ranged_hit(self, comp, target_m, ab):
                            abilities.ranged_projectile(self, comp, target_m, ab, color=(255, 220, 100))
                    elif ab.name == "Wall":
                        # Quinn's shield — on target ally
                        ab.use()
                        wall_target = comp_action.get("ability_target_ally", comp)
                        wall_target.absorb_shield = comp.surge_value
                        wall_target.buffs["Wall"] = {"remaining": 15.0}
                        self.float_text(wall_target.x, wall_target.y - 30, f"Wall!", (100, 180, 255))
                    elif ab.name == "Renew":
                        # Quinn's HoT — on target ally
                        ab.use()
                        renew_target = comp_action.get("ability_target_ally", comp)
                        hot_total = comp.surge_value * 0.5
                        renew_target.buffs["Renew"] = {"remaining": 8.0, "hot_per_sec": hot_total / 8.0}
                        self.float_text(renew_target.x, renew_target.y - 30, "Renew!", (100, 255, 150))
                    elif ab.name == "Frostbolt" and target_m and target_m.alive:
                        # Heskan's channeled bolt — simplified for companion (instant projectile)
                        if comp.swing_timer <= 0 and abilities.can_ranged_hit(self, comp, target_m, ab):
                            abilities.ranged_projectile(self, comp, target_m, ab, color=(150, 200, 255), apply_slow=True)
                    elif ab.name == "Fire Blast" and target_m and target_m.alive:
                        # Heskan's instant nuke
                        if abilities.can_ranged_hit(self, comp, target_m, ab):
                            abilities.fire_blast(self, comp, target_m, ab)
                    elif ab.name == "Stealth":
                        # Tarak's stealth
                        ab.use()
                        comp.stealthed = True
                        comp.gcd = comp.GCD_DURATION
                        comp._stealth_time = 0.0  # Track how long stealthed
                        # Drop aggro (except bosses)
                        for m in gs.alive_monsters:
                            if hasattr(m, 'aggro_target') and m.aggro_target == comp and not m.is_boss:
                                m.aggro_state = AggroState.RESETTING
                                m.aggro_target = None
                    elif ab.name == "Ambush" and target_m and target_m.alive:
                        # Tarak's stealth burst — need at least 0.5s in stealth
                        stealth_time = getattr(comp, '_stealth_time', 0)
                        if comp.stealthed and stealth_time >= 0.5 and comp.distance_to(target_m) <= ab.range:
                            ab.use()
                            comp.stealthed = False
                            dmg_amount = ab.calc_damage(comp.base_damage) + target_m.max_hp * 0.2
                            dmg = target_m.take_damage(dmg_amount)
                            self.float_text(target_m.x, target_m.y - 20, f"{dmg:.0f}", (255, 50, 50))
                            self.float_text(target_m.x, target_m.y - 40, "AMBUSH!", (255, 50, 50))
                            call_for_help(target_m, gs.monsters, hero)
                    elif ab.name == "Stab" and target_m and target_m.alive:
                        # Tarak's fast melee
                        if comp.swing_timer <= 0 and comp.distance_to(target_m) <= ab.range:
                            abilities.stab(self, comp, target_m, ab)
                    elif ab.name == "Smite" and target_m and target_m.alive:
                        # Keyleth's melee
                        if comp.swing_timer <= 0 and comp.distance_to(target_m) <= ab.range:
                            abilities.smite(self, comp, target_m, ab)
                    elif ab.name == "Righteous Seal":
                        # Keyleth's self-buff
                        ab.use()
                        comp.buffs["Righteous Seal"] = {"remaining": 10.0, "bonus": 0.25}
                    elif ab.name == "Judgement" and target_m and target_m.alive:
                        # Keyleth's ranged holy bolt
                        if abilities.can_ranged_hit(self, comp, target_m, ab):
                            abilities.judgement(self, comp, target_m, ab)
                    elif ab.name == "Holy Light":
                        # Keyleth's self-heal
                        ab.use()
                        heal = comp.heal(150)
                        if heal:
                            self.float_text(comp.x, comp.y - 30, f"+{heal:.0f}", (100, 255, 100))
                    elif target_m and target_m.alive:
                        # Generic fallback
                        if comp.distance_to(target_m) <= ab.range and comp.swing_timer <= 0:
                            hits = comp.use_ability(ab_key, [target_m])
                            for name, dmg in hits:
                                self.float_text(target_m.x, target_m.y - 20, f"{dmg:.0f}", (255, 255, 255))
                                call_for_help(target_m, gs.monsters, hero)

            if comp_action.get("move_to") and not comp_acted:
                tx, ty = comp_action["move_to"]
                # Repath periodically (every 0.5s) or if no cached path
                if not hasattr(comp, '_comp_path'):
                    comp._comp_path = []
                    comp._comp_repath_timer = 0
                comp._comp_repath_timer -= dt
                if comp._comp_repath_timer <= 0 or not comp._comp_path:
                    comp._comp_path = astar(self.dungeon, comp.x, comp.y, tx, ty)
                    comp._comp_repath_timer = 0.5
                if comp._comp_path:
                    wx, wy = comp._comp_path[0]
                    if math.sqrt((wx - comp.x)**2 + (wy - comp.y)**2) < 8:
                        comp._comp_path.pop(0)
                    if comp._comp_path:
                        comp.move_toward(comp._comp_path[0][0], comp._comp_path[0][1], dt, self.is_wall)

            else:
                # No combat action — follow the hero
                dist_to_hero = comp.distance_to(hero)
                if dist_to_hero > 600:
                    # Too far — teleport to hero (walkable position)
                    comp.x, comp.y = self.find_walkable_nearby(hero.x, hero.y, radius=60)
                    comp._follow_path = None
                elif dist_to_hero > 80:
                    # Recalculate path every time (hero moves)
                    comp._follow_path = astar(self.dungeon, comp.x, comp.y, hero.x, hero.y)
                else:
                    comp._follow_path = None

                # Walk along path
                if hasattr(comp, '_follow_path') and comp._follow_path:
                    tx, ty = comp._follow_path[0]
                    d = math.sqrt((tx - comp.x)**2 + (ty - comp.y)**2)
                    if d < 12:
                        comp._follow_path.pop(0)
                    else:
                        spd = comp.base_speed * dt
                        nx = comp.x + ((tx - comp.x) / d) * min(spd, d)
                        ny = comp.y + ((ty - comp.y) / d) * min(spd, d)
                        if not self.is_wall(nx, ny):
                            comp.x = nx
                            comp.y = ny
                        elif not self.is_wall(nx, comp.y):
                            comp.x = nx
                        elif not self.is_wall(comp.x, ny):
                            comp.y = ny
                        else:
                            comp._follow_path = None
                        comp.facing_left = (tx - comp.x) < 0

    # --- monster AI ---
    def update_monsters(self, dt, alive):
        """Run the AI of every monster in `alive` (all alive monsters with the aggro system)."""
        gs = self.game_state
        all_heroes = [h for h in gs.heroes if h.alive]
        for m in alive:
            result = run_monster_ai(m, all_heroes, dt, self.is_wall, all_monsters=gs.monsters)
            if result and result[0] in ("attack", "ranged_attack", "aoe_attack"):
                hit_hero = result[1]
                self.float_text(hit_hero.x+random.randint(-10,10), hit_hero.y-30, f"{result[2]:.0f}", HP_RED)
                # Demogorgon reveals when it attacks; stealth timer restarts from now.
                if m.name == "Demogorgon":
                    m._last_attack_time = gs.game_time
                    m.stealthed = False
            elif result and result[0] == "ranged_attack_projectile":
                target_hero = result[1]
                proj_damage = result[2]
                proj = Projectile(x=m.x, y=m.y, target=target_hero,
                                  speed=350.0, damage=proj_damage,
                                  color=(255, 80, 80), source=m)
                proj.on_hit_condition = m.on_hit_condition
                self.projectiles.append(proj)
