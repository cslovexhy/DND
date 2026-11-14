"""World: the simulation state and rules for one running map (pure; no pygame).

Being extracted from game/session.py step by step (design/06, phase 1). The session (client) owns
input, camera and drawing; the World owns heroes, companions, monsters, spawning and respawning.
Anything the player should see is reported through self.events (see engine/events.py).
"""
import heapq
import itertools
import random
from dataclasses import dataclass

from game.content.heroes import HERO_CLASSES, COMPANION_NAMES
from game.engine.ai import (generate_patrol_route, setup_monster_aggro, aggro_monster, call_for_help,
                            run_monster_ai, drop_from_hate, credit_heal_hate, AggroState)
from game.engine.entities import Condition, Monster, Projectile
from game.engine.events import (FloatText, LevelUp, SkillUp, QuestReady, NpcDialogue, GOLD, HP_RED, OpenNpcWindow,
                                SkillTrainable)

BLOCK_COLOR = (200, 210, 230)      # "BLOCK" over a hero whose shield took a hit
from game.engine.npc import NPC
from game.engine import abilities, actions, casting, combat, skills
from game.engine.snapshot import quest_info
from game.quests import npc_label as quests_label
from game.engine.pathfinding import has_line_of_sight
from game.engine.world_map import TILE_SIZE
from game.content.monsters import (SPAWN_STATS, respawn_delay, hp_for_level, base_xp_for_level, kill_xp,
                                    monster_hp_mult, damage_for_level, MONSTER_SWING_TIME, humanoid_money,
                                    HUMANOID, monster_skill_level, monster_max_mana)
from game.content.skill_tree import apply_skill_levels, describe, skill_levels, unlock_level_of
from game.content.shop import train_cost
from game.content.skill_library import make_skill
from game.content.difficulty import PP_DEFAULT, clamp_pp, hp_multiplier, damage_multiplier, scaled_xp
from game.content.items import roll_drops
from game.engine.trade import Trade
from game.content import money


DEFAULT_ITEM_RESPAWN = 60.0


@dataclass
class ItemNode:
    """An item lying on the map for gathering (the map's "item_spawns"): anyone can gather it with a 2 s channel; it
    is gone for everybody until its respawn timer runs out. It never moves or patrols."""
    node_id: int
    item: int          # item id (data/items.json)
    count: int
    x: float
    y: float
    respawn: float     # seconds until it is back
    available: bool = True
    timer: float = 0.0


@dataclass
class GroundItem:
    """An item lying on the map (a monster dropped it); anyone can pick it up."""
    item_id: int     # own id space (not an entity id)
    item: str        # content/items.py key
    x: float
    y: float
from game.progression import (MAX_LEVEL, xp_to_next_level, apply_level_growth, set_hero_level, growth_for)

COMPANION_ID_BASE = 1000           # player ids of AI companions start here (humans get 0, 1, 2, ...)

# --- Demogorgon special skills ---
DEMOGORGON_STEALTH_DELAY = 6.0   # seconds since last attack before auto-stealth
DEMOGORGON_AURA_RADIUS = 90.0    # pixels; aura reaches this far
DEMOGORGON_AURA_SLOW = 0.8       # enemies move at 80% speed (20% slow) in aura


class World:
    def __init__(self, world_map, game_state, hero, quests=None, debug=False, pp=PP_DEFAULT):
        self.debug = debug
        self.pp = clamp_pp(pp)
        self.quests = quests       # player 0's QuestLog for this map (each PlayerState has its own)
        self.projectiles = []      # active projectiles (Wanding, Frostbolt, monster arrows)
        self.hazards = []          # damaging ground zones (a boss' Deep Breath), see engine/skills.py
        self.casts = []            # monster skills in their wind-up (the message over the monster's head)
        self.world_map = world_map
        self.dungeon = world_map   # navigation duck-type (is_wall, is_floor, get_start_pos) used by AI/pathfinding
        self.game_state = game_state
        self.hero = hero           # player 0's hero (the host's own player); other players: self.players
        self.events = []           # view events produced this frame (engine/events.py)
        # Respawn queue: min-heap of (respawn_at_game_time, seq, SpawnPoint)
        self.respawn_heap = []
        self._respawn_seq = itertools.count()  # tiebreaker so equal times never compare SpawnPoint objects
        # Hooks the client sets to decorate new entities (e.g. attach sprites) without the sim knowing about art
        self.on_monster_spawned = None
        self.on_companion_spawned = None
        self.on_npc_spawned = None
        self.npcs = []
        self.ground_items = []     # GroundItem: monster drops waiting to be picked up
        self.item_nodes = []       # ItemNode: items to gather from the map (item_spawns)
        self.trades = {}           # player_id -> Trade (both traders map to the same one), see engine/trade.py
        self._next_item_id = itertools.count(1)
        # Entity registry (stable ids for commands/network) and command queue
        self._next_eid = itertools.count(1)
        self.entities = {}
        self.players = {}          # player_id -> PlayerState
        self.command_queue = []    # (player_id, command), applied at the start of the next frame
        self.command_log = []      # (tick, player_id, command) when recording
        self.tick = 0              # number of completed simulation steps
        self.record_commands = False
        self.register(hero)
        # AI companions are ordinary players (in self.players) flagged with an owner. Their ids start high so they
        # never collide with the ids the host hands out to humans; their names are random (see spawn_companion).
        self._next_companion_id = COMPANION_ID_BASE
        self._name_rng = random.Random(0xC0DE)   # own stream: picking a name must not disturb the sim's random numbers
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
        player = self.players.get(player_id)
        if player is not None:
            self.cancel_trade(player)             # the other trader's window closes
        player = self.players.pop(player_id, None)
        if player is None:
            return
        for comp in [c for c in self.companions if c.owner is player]:
            self.remove_player(comp.player_id)
        if player.hero in self.game_state.heroes and player.hero is not self.hero:
            self.game_state.heroes.remove(player.hero)
            self.unregister(player.hero)

    @property
    def companions(self):
        """The AI companions: players whose `owner` is set (stable order)."""
        return [p for p in self.player_list if p.is_companion]

    @property
    def human_players(self):
        """Everyone except the AI companions (they earn no XP or quest credit and have no client)."""
        return [p for p in self.player_list if not p.is_companion]

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
    def _companion_name(self):
        """A random name no hero in the world has yet (two players' companions must never share one)."""
        taken = {h.name.lower() for h in self.game_state.heroes}
        free = [n for n in COMPANION_NAMES if n.lower() not in taken]
        if free:
            return self._name_rng.choice(free)
        base = self._name_rng.choice(COMPANION_NAMES)
        n = 2
        while f"{base} {n}".lower() in taken:
            n += 1
        return f"{base} {n}"

    def spawn_companion(self, comp_info, owner=None):
        """Summon an AI companion of the given class for `owner` (a PlayerState; default player 0). It is an ordinary
        player (own id in self.players, same hero / controller / skills as a human) that is always on autopilot, never
        runs out of potions and follows its owner when idle. Its level is fixed at the owner's CURRENT level when
        summoned. Returns its hero."""
        from game.engine.player import PlayerState
        owner = owner or self.players.get(0)
        lead = owner.hero if owner else self.hero
        cx, cy = self.find_walkable_nearby(lead.x, lead.y, radius=60)
        comp = comp_info["create"](self._companion_name(), cx, cy)
        if self.on_companion_spawned:
            self.on_companion_spawned(comp, comp_info)
        set_hero_level(comp, lead.level)
        ctl = PlayerState(self, comp, ai_enabled=True, potions=None, owner=owner, name=comp.name)
        self.add_player(self._next_companion_id, ctl)
        self._next_companion_id += 1
        return comp

    def dismiss_companion(self, comp):
        """Remove a companion (its hero) from the world."""
        ctl = self.player_for_hero(comp)
        if ctl is not None and ctl.is_companion:
            self.remove_player(ctl.player_id)

    def spawn_single_world_monster(self, sp):
        """Spawn a single monster from a SpawnPoint. Returns the Monster or None."""
        mt = SPAWN_STATS.get(sp.type)
        if mt is None:
            return None
        if getattr(sp, "stats", None):
            mt = {**mt, **sp.stats}          # this map's override of the shared stat entry
        wx, wy = self.world_map.get_spawn_world_pos(sp.x, sp.y)
        is_boss = mt.get("boss", False)
        m = Monster(mt["name"], "Monster", wx, wy,
                    hp=1, ac=mt["ac"], speed=mt["speed"],
                    attack_bonus=0, attack_damage=0,
                    experience=0, is_boss=is_boss)
        if self.on_monster_spawned:
            self.on_monster_spawned(m)
        m.skills = dict(mt.get("skills", {}))
        m.unique = mt.get("unique", False)  # one-of-a-kind minion: name shown, but respawns/leashes like a normal mob
        m.category = mt["category"]   # humanoid / beast / demon: decides money drops
        m.drops = mt["drops"]         # this type's drop table (monsters.MONSTER_DROPS, or the map's override)
        level_range = mt["level"]
        m.leveled = True              # every monster has a level: HP, damage and XP follow the rolled one
        m.level = random.randint(level_range[0], level_range[1])
        m.max_hp = hp_for_level(m.level)
        m.experience = base_xp_for_level(m.level)
        m.base_damage = damage_for_level(m.level)   # each hit rolls x0.9..x1.1 (Monster.hit_damage)
        m.weapon_speed = mt.get("swing", MONSTER_SWING_TIME) * (0.8 if is_boss else 1.0)   # bosses swing faster
        self._give_kit(m, mt.get("kit", ()))
        m.max_hp *= monster_hp_mult(mt)   # per-type HP multiplier (default 1)
        m.hp = m.max_hp
        self._apply_pp(m)
        if mt.get("ranged"):
            m.ranged_attack_range = 250
            m.ranged_attack_damage = m.base_damage
        if mt.get("relentless"):
            m.relentless = True  # never leash-resets aggro (set before setup_monster_aggro)
        if mt.get("hive_mind"):
            m.hive_mind = mt["hive_mind"]  # (range, [spawn_types]) — type-filtered aggro share
        m.spawn_type = sp.type  # the monster's id: for hive_mind matching and quest kills
        m.stealthy = bool(mt.get("stealthy"))
        m.sense_range = mt.get("sense_range", 170)   # how far it notices heroes (the definition's)
        m.def_attack_range = mt.get("attack_range")  # px it fights from (None: 50 melee / 220 ranged)
        # Track spawn origin for respawn system
        m.spawn_point = sp
        setup_monster_aggro(m, nav_dungeon=self.dungeon)
        generate_patrol_route(m, patrol_radius=100, collision_fn=self.is_wall)
        self.register(m)
        return m

    def _give_kit(self, m, kit):
        """A monster's castable skills (content/skill_library.py, the same Ability a hero gets) at the skill level
        of its monster level, and a mana pool to pay for them (content/monsters.py)."""
        if not kit:
            return
        for name in kit:
            ab = make_skill(name)
            ab.set_level(monster_skill_level(m.level))
            m.add_ability(name, ab)
        m.max_mana = m.mana = monster_max_mana(m.level)

    def _apply_pp(self, m):
        """Scale a freshly spawned monster for the map's pp (no-op at 1pp): HP x pp, damage and XP x (1+pp)/2."""
        m.max_hp = m.max_hp * hp_multiplier(self.pp)
        m.hp = m.max_hp
        dm = damage_multiplier(self.pp)
        m.base_damage = m.base_damage * dm
        m.skill_power = dm                          # its skills' flat amounts (poison, heals, shields) scale too
        m.base_experience = m.experience            # gold rolls stay on the base value
        m.experience = scaled_xp(m.experience, self.pp)

    def spawn_world_map_monsters(self):
        """Spawn all monsters from world map spawn data."""
        for sp in self.world_map.get_monster_spawns():
            m = self.spawn_single_world_monster(sp)
            if m:
                self.game_state.monsters.append(m)

    def load_item_nodes(self):
        """Create the map's gatherable items ("item_spawns": item id, tile x/y, optional count and respawn seconds)."""
        from game.content.items import ITEMS
        for sp in self.world_map.data.get("item_spawns", []):
            if sp.get("item") not in ITEMS:
                continue                              # an item that was deleted: nothing to gather
            wx, wy = self.world_map.get_spawn_world_pos(sp["x"], sp["y"])
            self.item_nodes.append(ItemNode(len(self.item_nodes) + 1, sp["item"], sp.get("count", 1), wx, wy,
                                            float(sp.get("respawn", DEFAULT_ITEM_RESPAWN))))

    def item_node(self, node_id):
        return next((n for n in self.item_nodes if n.node_id == node_id), None) if node_id is not None else None

    def update_item_nodes(self, dt):
        for n in self.item_nodes:
            if not n.available:
                n.timer -= dt
                if n.timer <= 0:
                    n.available, n.timer = True, 0.0

    def load_npcs(self):
        """Create NPCs from map data (each map defines its own NPCs in the JSON)."""
        for npc_def in self.world_map.data.get("npcs", []):
            tx, ty = npc_def["x"], npc_def["y"]
            wx, wy = self.world_map.get_spawn_world_pos(tx, ty)
            npc = NPC(self, npc_def["name"], wx, wy, npc_id=npc_def["npc_id"],
                      gender=npc_def.get("gender", "male"), role=npc_def.get("role"),
                      trains=npc_def.get("trains"), shop=npc_def.get("shop"))
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

        def pay(q):
            hero.xp += q.rewards_xp
            hero.gold += q.rewards_gold
            self.float_text(hero.x, hero.y - 40, f"+{q.rewards_xp}xp +{money.format_short(q.rewards_gold)}", GOLD)

        # First: quests whose reward this NPC pays (handed in elsewhere)
        for qid in quests.rewards_for_npc(npc.npc_id):
            q = quests.turn_in(qid)
            pay(q)
            self.events.append(NpcDialogue(
                quest_info(q), "turnin", npc.name,
                f"Well done! {q.title} complete. Here's your reward: {q.rewards_xp} experience and "
                f"{money.format_long(q.rewards_gold)}.",
                voice, pid))
            interacted = True

        # Then: hand in the kills / items of completed quests at this NPC (and get paid if it pays too)
        for qid in quests.turn_ins_for_npc(npc.npc_id):
            q, paid = quests.hand_in(qid)
            if paid:
                pay(q)
                text = (f"Well done! {q.title} complete. Here's your reward: {q.rewards_xp} experience and "
                        f"{money.format_long(q.rewards_gold)}.")
            else:
                text = f"Thank you. Now go and see {quests_label(q.reward_npc)} for your reward."
            self.events.append(NpcDialogue(quest_info(q), "turnin" if paid else "handin", npc.name, text, voice, pid))
            interacted = True

        # Second: offer and accept an available quest from this NPC
        if not interacted:  # Don't pile accept on top of turn-in
            for qid in quests.available_for_npc(npc.npc_id, hero.level):
                q = quests.quests[qid]
                if quests.accept(qid):
                    # No-objective quest given, handed in and paid by this NPC: completed on the spot
                    hero.xp += q.rewards_xp
                    hero.gold += q.rewards_gold
                    mode = "turnin"
                else:
                    mode = "accept"
                self.events.append(NpcDialogue(quest_info(q), mode, npc.name, q.description, voice, pid))
                interacted = True
                break  # One quest popup at a time

        # Third: vendors and trainers open their window
        if not interacted and npc.role in ("vendor", "trainer"):
            self.events.append(OpenNpcWindow(npc.eid, npc.role, pid))
            interacted = True

        return interacted

    # --- respawning ---
    # --- trading between players (engine/trade.py) ---
    def trade_of(self, player):
        return self.trades.get(player.player_id)

    def open_trade(self, player, hero_id):
        """Open a trade between `player` and the player whose hero is `hero_id` (humans only)."""
        other = self.player_for_hero(self.entity(hero_id)) if hero_id is not None else None
        if other is None or other is player or other.is_companion or player.is_companion:
            self.float_text(player.hero.x, player.hero.y - 30, "Target another player to trade", (255, 150, 100))
            return None
        for p in (player, other):
            self.cancel_trade(p)
        trade = Trade(player, other)
        self.trades[player.player_id] = self.trades[other.player_id] = trade
        return trade

    def cancel_trade(self, player):
        trade = self.trades.get(player.player_id)
        if trade is None:
            return
        for p in trade.players:
            self.trades.pop(p.player_id, None)

    def accept_trade(self, player):
        trade = self.trades.get(player.player_id)
        if trade is None:
            return
        if trade.accept(player):
            for p in trade.players:
                self.float_text(p.hero.x, p.hero.y - 30, "Trade complete!", (120, 255, 140))
                self.trades.pop(p.player_id, None)
        elif trade.message:
            for p in trade.players:
                self.float_text(p.hero.x, p.hero.y - 30, trade.message, (255, 150, 100))

    # --- ground items (monster drops) ---
    def drop_item(self, item, x, y):
        g = GroundItem(next(self._next_item_id), item, x, y)
        self.ground_items.append(g)
        return g

    def ground_item(self, item_id):
        return next((g for g in self.ground_items if g.item_id == item_id), None) if item_id is not None else None

    def remove_ground_item(self, g):
        if g in self.ground_items:
            self.ground_items.remove(g)

    def roll_monster_drops(self, m):
        """A monster died: roll its drop table (content/monsters.MONSTER_DROPS) and lay the items where it fell."""
        drops = roll_drops(getattr(m, "drops", ()), m.level, random)
        for i, item in enumerate(drops):
            x, y = m.x + (i - (len(drops) - 1) / 2) * 14, m.y   # one drop where it fell; several side by side
            if self.is_wall(x, y):
                x, y = m.x, m.y
            self.drop_item(item, x, y)

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
            if not m.alive or not getattr(m, "stealthy", False):
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
            for t in player_heroes:
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
                for player in self.human_players:
                    hero = player.hero
                    # leveled monsters give less XP to heroes above their level (none from 6 levels up)
                    xp = kill_xp(m.experience, hero.level, m.level) if getattr(m, "leveled", False) else m.experience
                    hero.xp += xp
                    # only humanoids carry money (each player gets their own roll)
                    coins = humanoid_money(m.level, random) if getattr(m, "category", None) == HUMANOID else 0
                    hero.gold += coins
                    hero.kills += 1
                    if player.player_id == 0 or len(self.human_players) == 1:
                        loot = f" +{money.format_short(coins)}" if coins else ""
                        self.float_text(m.x, m.y + 10, f"+{xp}xp{loot}", GOLD)
                    # Quest kill tracking
                    for aq, just_completed in player.quests.record_kill(getattr(m, "spawn_type", None)):
                        self.float_text(hero.x, hero.y - 50, aq.get_progress_text(), (200, 200, 255))
                        if just_completed:
                            self.events.append(QuestReady(aq.title, player.player_id))
                m.experience = 0
                self.roll_monster_drops(m)
                # Queue for respawn (every monster that came from a spawn point; bosses just take much longer)
                self.queue_respawn(m)

    def process_level_ups(self):
        for player in self.human_players:     # companions keep the level they were summoned at
            hero = player.hero
            while hero.level < MAX_LEVEL and hero.xp >= xp_to_next_level(hero.level):
                hero.xp -= xp_to_next_level(hero.level)
                hero.level += 1
                growth = growth_for(hero.class_name)
                hp_before = hero.max_hp
                could_learn = skill_levels(hero.class_name, hero.level - 1)
                apply_level_growth(hero)  # also full-heals on level-up
                for key, skill_level, is_new in apply_skill_levels(hero):   # new skill / next skill level (every 2 levels)
                    ab = hero.abilities[key]
                    self.events.append(SkillUp(hero.level, key, ab.name, skill_level, ab.max_level, is_new,
                                               describe(hero, ab), player.player_id))
                if hero.trained is not None:      # player characters: a new level is learned at the trainer
                    for key, lvl in skill_levels(hero.class_name, hero.level).items():
                        if lvl > could_learn.get(key, 0):
                            ab = hero.all_abilities[key]
                            self.events.append(SkillTrainable(
                                hero.level, key, ab.name, lvl, key not in hero.trained,
                                train_cost(unlock_level_of(hero.class_name, key, lvl)),
                                f"{hero.class_name} Trainer", player.player_id))
                self.events.append(LevelUp(hero.x, hero.y, player.player_id))
                self.float_text(hero.x, hero.y - 30,
                                f"Lv {hero.level}! +{hero.max_hp - hp_before:.0f}HP +{growth['damage']:.0f}dmg", GOLD)

    # --- projectiles ---
    def update_projectiles(self, dt):
        gs = self.game_state
        for proj in self.projectiles:
            result = proj.update(dt)
            if result is not None:
                dmg, hit_target = result
                src = proj.source
                if hit_target.faction == "heroes":
                    self.float_text(hit_target.x + random.randint(-10, 10), hit_target.y - 30,
                                    "BLOCK" if proj.blocked else f"{dmg:.0f}", BLOCK_COLOR if proj.blocked else HP_RED)
                else:
                    self.float_text(hit_target.x, hit_target.y - 20, f"{dmg:.0f}", proj.color)
                if src is not None:
                    if hasattr(src, "since_combat"):
                        src.since_combat = 0.0      # it reached someone: the leash timer starts over
                    combat.engage(self, hit_target, src)
                # Frostbolt slow
                if getattr(proj, 'apply_slow', False) and hit_target.alive:
                    slowed = hit_target.apply_condition(Condition.SLOWED, abilities.FROSTBOLT_SLOW_SECS,
                                                        slow_factor=abilities.FROSTBOLT_SLOW)
                    self.float_text(hit_target.x, hit_target.y - 35, "SLOWED" if slowed else "IMMUNE", (150, 200, 255))
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
            if player.is_companion:
                player.update_companion(dt)    # autopilot, then follow the owner when idle
                continue
            player.update(dt)
            player.run_ai(dt)          # autopilot, when enabled
            player.update_ambush()
            player.auto_attack()
        self.update_monsters(dt, alive)
        skills.cast_queued_skills(self)
        skills.update_casts(self, dt)
        skills.update_hazards(self, dt)
        self.process_kills()
        self.process_level_ups()
        self.process_respawns()
        self.update_item_nodes(dt)
        self.update_projectiles(dt)
        # Expire Wall shield when buff expires (heroes, and monsters shielded by a monster's Wall)
        for e in itertools.chain(self.player_heroes, gs.monsters):
            if "Wall" not in e.buffs and e.absorb_shield > 0:
                e.absorb_shield = 0
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
        hero.conditions = []          # e.g. poison would kill again
        hero.buffs = {}               # incl. the food buff and a meal being eaten
        hero.refresh_max_hp()
        hero.hp = hero.max_hp * self.RESPAWN_HP_PCT
        hero.mana = hero.max_mana
        hero.absorb_shield = 0
        hero.stealthed = False
        hero.chill_visual = 0.0
        hero.in_combat = False
        hero.deaths = getattr(hero, "deaths", 0) + 1
        # forget what this player was doing
        player.move_path = []
        player.selected_target = None
        player.target = None
        player.move_dir = (0, 0)
        player.pending_cast = None
        player.queued_cast = None
        player.ambush_target = None
        hero.dash = None
        hero.channel = None
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
            # Update combat state for health regeneration
            hero.in_combat = any(m.alive and getattr(m, 'aggro_target', None) == hero
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
        for m in gs.monsters:                     # a monster healed by a monster: no hate to credit
            m.heal_credits.clear()
        alive = gs.alive_monsters
        return alive

    # --- monster AI ---
    def update_monsters(self, dt, alive):
        """Run the AI of every monster in `alive` (all alive monsters with the aggro system)."""
        gs = self.game_state
        all_heroes = [h for h in gs.heroes if h.alive]
        for m in alive:
            actions.update_actions(self, m, dt)          # a monster's channel / dash, same as a hero's
            result = run_monster_ai(m, all_heroes, dt, self.is_wall, all_monsters=gs.monsters)
            if result and result[0] in ("attack", "ranged_attack", "aoe_attack"):
                hit_hero = result[1]
                blocked = result[0] == "attack" and m.last_blocked
                self.float_text(hit_hero.x+random.randint(-10,10), hit_hero.y-30,
                                "BLOCK" if blocked else f"{result[2]:.0f}", BLOCK_COLOR if blocked else HP_RED)
                if result[0] == "attack" and not blocked:
                    abilities.poison_on_hit(self, m, hit_hero)   # an armed Poison Dagger rides on this hit
                # a stealthy monster (the Demogorgon) reveals itself when it attacks; its stealth timer restarts
                if getattr(m, "stealthy", False):
                    m._last_attack_time = gs.game_time
                    m.stealthed = False
            elif result and result[0] == "ranged_attack_projectile":
                target_hero = result[1]
                proj_damage = result[2]
                proj = Projectile(x=m.x, y=m.y, target=target_hero,
                                  speed=350.0, damage=proj_damage,
                                  color=(255, 80, 80), source=m, blockable=True)
                self.projectiles.append(proj)
            if m.abilities and m.alive and m.aggro_state == AggroState.AGGROED:
                casting.monster_turn(self, m)              # its kit: the same cast path as a hero's
