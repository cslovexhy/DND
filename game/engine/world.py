"""World: the simulation state and rules for one running map (pure; no pygame).

Being extracted from game/session.py step by step (design/06, phase 1). The session (client) owns
input, camera and drawing; the World owns heroes, companions, monsters, spawning and respawning.
Anything the player should see is reported through self.events (see engine/events.py).
"""
import heapq
import itertools
import random

from game.content.heroes import HERO_CLASSES
from game.engine.ai import (generate_patrol_route, setup_monster_aggro, aggro_monster, call_for_help,
                            run_monster_ai, drop_from_hate, credit_heal_hate)
from game.engine.entities import Condition, Monster, Projectile
from game.engine.events import FloatText, LevelUp, QuestReady, NpcDialogue, GOLD, HP_RED
from game.engine.npc import NPC
from game.engine import skills
from game.engine.snapshot import quest_info
from game.engine.pathfinding import has_line_of_sight
from game.engine.world_map import TILE_SIZE
from game.content.monsters import SPAWN_STATS, respawn_delay
from game.content.difficulty import PP_DEFAULT, clamp_pp, hp_multiplier, damage_multiplier, scaled_xp
from game.engine.entities import POISON_DPS
from game.progression import (MAX_LEVEL, xp_to_next_level, apply_level_growth, set_hero_level, growth_for)

# --- Demogorgon special skills ---
DEMOGORGON_STEALTH_DELAY = 6.0   # seconds since last attack before auto-stealth
DEMOGORGON_AURA_RADIUS = 90.0    # pixels; aura reaches this far
DEMOGORGON_AURA_SLOW = 0.8       # enemies move at 80% speed (20% slow) in aura


class World:
    def __init__(self, world_map, game_state, hero, quests=None, debug=False, pp=PP_DEFAULT):
        self.debug = debug
        self.pp = clamp_pp(pp)
        # AI companions (F1-F4). Off in co-op (the host turns them off): they were buggy with several players
        # and are meant to be replaced by AI-driven temporary players.
        self.companions_enabled = True     # map difficulty: monsters get HP x pp, damage x (1 + pp) / 2
        self.quests = quests       # player 0's QuestLog for this map (each PlayerState has its own)
        self.projectiles = []      # active projectiles (Wanding, Frostbolt, monster arrows)
        self.hazards = []          # damaging ground zones (a boss' Deep Breath), see engine/skills.py
        self.casts = []            # monster skills in their wind-up (the message over the monster's head)
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
        # Same controller a player hero uses (casting, movement, autopilot), in companion mode:
        # always on autopilot, never runs out of potions, follows its owner when idle.
        from game.engine.player import PlayerState
        ctl = PlayerState(self, comp, ai_enabled=True, potions=None, owner=owner, name=comp.name)
        self.companions.append((comp, ctl))
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
        m.skills = dict(mt.get("skills", {}))
        m.unique = mt.get("unique", False)  # one-of-a-kind minion: name shown, but respawns/leashes like a normal mob
        if mt.get("condition"):
            m.on_hit_condition = mt["condition"]
        self._apply_pp(m)
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

    def _apply_pp(self, m):
        """Scale a freshly spawned monster for the map's pp (no-op at 1pp): HP x pp, damage and XP x (1+pp)/2."""
        m.max_hp = m.max_hp * hp_multiplier(self.pp)
        m.hp = m.max_hp
        dm = damage_multiplier(self.pp)
        m.base_damage = m.base_damage * dm
        m.poison_dps = POISON_DPS * dm
        m.base_experience = m.experience            # gold rolls stay on the base value
        m.experience = scaled_xp(m.experience, self.pp)

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
                    hero.gold += random.randint(10, 30) * getattr(m, "base_experience", m.experience)
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
                        slowed = hit_target.apply_condition(Condition.SLOWED, 3.0, slow_factor=0.25)
                        self.float_text(hit_target.x, hit_target.y - 35, "SLOWED" if slowed else "IMMUNE", (150, 200, 255))
                else:
                    # Monster projectile hitting hero
                    self.float_text(hit_target.x + random.randint(-10, 10), hit_target.y - 30, f"{dmg:.0f}", HP_RED)
                    # Apply on-hit condition if any
                    on_hit = getattr(proj, 'on_hit_condition', None)
                    if on_hit and hit_target.alive:
                        cond, dur = on_hit
                        hit_target.apply_condition(cond, dur,
                                                   tick_damage=getattr(proj.source, "poison_dps", POISON_DPS)
                                                   if cond == Condition.POISONED else 0)
        self.projectiles[:] = [p for p in self.projectiles if p.alive]

    # --- one simulation step ---
    def step(self, dt):
        """Advance the simulation by dt seconds: apply queued commands, then run every system in order."""
        gs = self.game_state
        alive = self.begin_frame(dt)
        for pid in sorted(self.players):
            player = self.players[pid]
            if not player.hero.alive:
                continue               # a dead player's hero doesn't move, cast or think (co-op: others play on)
            player.update(dt)
            player.run_ai(dt)          # autopilot, when enabled
            player.update_ambush()
            player.auto_attack()
        self.update_companions(dt)
        self.update_monsters(dt, alive)
        skills.cast_queued_skills(self)
        skills.update_casts(self, dt)
        skills.update_hazards(self, dt)
        self.process_kills()
        self.process_level_ups()
        self.process_respawns()
        self.update_projectiles(dt)
        # Expire Wall shield when buff expires
        for hero in self.player_heroes:
            if "Wall" not in hero.buffs and hero.absorb_shield > 0:
                hero.absorb_shield = 0
        # No game over: a fallen player gets up again at the map's start point (solo and co-op)
        for player in self.player_list:
            if not player.hero.alive:
                self.respawn_player(player)
        self.tick += 1

    def credit_heal(self, healer, target, amount):
        """A heal or shield: `amount` HP on `target` by `healer` makes hate on every mob that has `target` in combat."""
        credit_heal_hate(self.game_state.monsters, healer, target, amount)

    # --- death and respawn ---
    RESPAWN_HP_PCT = 0.10   # respawn weak: the autopilot rests until 80% HP, so dying works like a cooldown

    def respawn_player(self, player):
        """Bring a dead player back at the map's start point with 10% HP and a clean slate."""
        hero = player.hero
        hero.x, hero.y = self.world_map.get_start_pos()
        hero.alive = True
        hero.hp = hero.max_hp * self.RESPAWN_HP_PCT
        hero.conditions = []          # e.g. poison would kill again
        hero.buffs = {}
        hero.absorb_shield = 0
        hero.stealthed = False
        hero.chill_visual = 0.0
        hero.in_combat = False
        hero.deaths = getattr(hero, "deaths", 0) + 1
        # forget what this player was doing
        player.move_path = []
        player.selected_target = None
        player.pending_cast = None
        player.ambush_target = None
        player.dash_active = False
        player.dash_path = []
        player.dash_stun_target = None
        player.frostbolt_channeling = False
        player.frostbolt_target = None
        player.hero_ai.target = None
        player.hero_ai._path_cache.clear()
        # monsters that were fighting this hero give up (otherwise it would be "in combat" at 10% HP)
        # A new life starts with a clean slate: every monster forgets this hero's hate (otherwise a boss would walk to
        # the start point and spawn-camp them). Bosses still never give up: they pick the next-hated hero.
        for m in self.game_state.monsters:
            if m.alive and hero in m.hate:
                drop_from_hate(m, hero)
        self.float_text(hero.x, hero.y - 30, "Respawned", (255, 220, 120))

    # --- per-frame start ---
    def begin_frame(self, dt):
        """Start-of-frame bookkeeping: Holy Light completion, combat flags, Demogorgon skills, entity timers.
        Returns the list of alive monsters (snapshot used by the monster AI later this frame)."""
        gs = self.game_state
        self._apply_commands()
        for hero in self.player_heroes:
            # Check Holy Light cast completion BEFORE update (buff gets removed during update)
            if "Holy Light Casting" in hero.buffs and hero.buffs["Holy Light Casting"]["remaining"] <= dt:
                cast = hero.buffs.pop("Holy Light Casting")
                target = self.entity(cast.get("target_id")) or hero   # the chosen ally, or the caster
                if not target.alive or target not in gs.heroes:
                    target = hero
                heal = target.heal(cast["heal"])
                self.credit_heal(hero, target, heal)
                self.float_text(target.x, target.y - 30, f"+{heal:.0f} HP", (100, 255, 100))

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
        for h in gs.heroes:                       # heal-over-time ticks (Renew) -> hate for the healer
            for healer, amount in h.heal_credits:
                self.credit_heal(healer, h, amount)
            h.heal_credits.clear()
        alive = gs.alive_monsters
        return alive

    # --- companion AI ---
    def update_companions(self, dt):
        """Run each summoned companion for this frame. Companions are driven by the same PlayerState
        controller as players (see PlayerState.update_companion)."""
        for comp, ctl in self.companions:
            if comp.alive:
                ctl.update_companion(dt)

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
