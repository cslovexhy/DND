"""PlayerState: the local player's hero controller (pure; no pygame).

Holds the per-player control state that used to be module globals in session.py (move path, target,
dash/channel state, queued casts, potions, autopilot) and the rules that act on it. The client feeds
it intents (cast_ability, move_path, selected_target ...) and calls the update_* methods in frame order.
Skill-slot bindings (which key is the left/right click skill) are UI state and stay in the client;
the controller asks the client to rebind through a BindRightSkill event.
"""
import math
import random

from game.engine import abilities
from game.engine.ai import aggro_monster, call_for_help, drop_from_hate, AggroState
from game.engine.entities import Condition, Projectile
from game.engine.commands import (MoveTo, SelectTarget, Cast, InteractNpc, AmbushTarget, UsePotion,
                                  ToggleAutopilot, ToggleCompanion, CancelChannel, BindLeftSkill, HoldPosition,
                                  UseItem, PickUp, SetTarget, MoveDir, TradeOpen, TradeOffer, TradeTake,
                                  TradeAccept, TradeCancel)
from game.engine.inventory import Inventory
from game.content.items import ITEMS, POTION_COOLDOWN, FOOD_DURATION, FOOD_BUFF, FOOD_HOT
from game.engine.events import Ring, BindRightSkill, GOLD
from game.engine.hero_ai import create_hero_ai
from game.content.heroes import HERO_CLASSES
from game.engine.pathfinding import astar
from game.engine.world_map import TILE_SIZE


from game.content.skill_tree import (wall_shield, renew_total, seal_bonus, holy_light_heal, shout_reduction,
                                     smite_damage)
HEROIC_STRIKE_WINDOW = 10.0   # seconds a Heroic Strike buff waits for the next Strike / Cleave
from game.engine.hero_ai import SUPPORT_RANGE   # px: how far away an ally can be for Wall / Renew / Holy Light


class PlayerState:
    PICKUP_RANGE = 40   # px: how close the hero must be to pick an item up

    def __init__(self, world, hero, ai_enabled=False, potions=3, quests=None, name=None, owner=None,
                 inventory=None):
        self.world = world
        self.hero = hero
        # Companion mode: an AI-driven hero that fights for (and follows) the `owner` player. It uses exactly the
        # same casting / movement / autopilot code as a player; potions=None means it never runs out (no backpack
        # needed). Players carry their potions in the backpack (`inventory`: saved state, None = starting backpack).
        self.owner = owner
        self.player_id = 0               # set by World.add_player
        self.name = name or hero.name
        self.quests = quests if quests is not None else world.quests   # this player's QuestLog for the map
        # One AI companion per class other than this player's own (summoned with ToggleCompanion)
        self.available_companions = [c for c in HERO_CLASSES if c["class"] != hero.class_name]
        self.hero_ai = create_hero_ai(hero)   # autopilot brain (HeroAI)
        self.hero_ai.set_nav_dungeon(world.dungeon)
        self.hero_ai.clock = lambda: world.game_state.game_time
        self.hero_ai.allies = world.game_state.heroes   # the party: shared by every AI (support heals, team focus, no melee kiting)
        self.ai_enabled = ai_enabled     # autopilot on/off (TAB; on in --auto/--headless)
        # Movement / targeting
        self.move_path = []
        self.selected_target = None
        self.unlimited_potions = potions is None
        self.inventory = Inventory.from_state(inventory)
        self.potion_cooldown = 0.0       # seconds until the next Health Potion
        self.pickup_target = None        # ground item id we're walking to (PickUp)
        self.target = None               # WoW-style target (enemy or friendly hero) that hotbar skills use
        self.move_dir = (0, 0)           # WASD direction being held
        # Client choices that affect auto-attack (sent as BindLeftSkill / HoldPosition commands)
        self.left_ab_key = next(iter(hero.abilities), None)
        self.hold_position = False
        # Queued ability cast (walk to range then fire): (ab_key, ab, target_monster) or None
        self.pending_cast = None
        # Dash animation state (Charge)
        self.dash_path = []      # Charge waypoints (follows a walking path, not a straight line)
        self.dash_target_x = 0.0
        self.dash_target_y = 0.0
        self.dash_active = False
        self.dash_speed = 800.0  # pixels per second (very fast)
        self.dash_stun_target = None
        self.dash_stun_duration = 0.0
        self.dash_damage = 0.0  # damage dealt on arrival
        # Frostbolt channel state (Heskan)
        self.frostbolt_channeling = False
        self.frostbolt_channel_timer = 0.0
        self.frostbolt_target = None  # Monster being targeted
        # Ambush walk-to state (Tarak): monster to ambush (walk toward, execute when in range)
        self.ambush_target = None

    @property
    def is_companion(self):
        return self.owner is not None

    def _bind_right(self, key):
        """Ask this player's client to switch its right-click skill (companions have no client)."""
        if not self.is_companion:
            self.world.events.append(BindRightSkill(key, self.player_id))

    @property
    def potions(self):
        """Health Potions left (None = unlimited, companions)."""
        return None if self.unlimited_potions else self.inventory.count("health_potion")

    def _potion_ready(self):
        return self.potion_cooldown <= 0 and (self.unlimited_potions or self.potions > 0)

    def _use_potion(self):
        if not self.unlimited_potions and not self.inventory.take("health_potion"):
            return
        self.potion_cooldown = POTION_COOLDOWN
        heal = self.hero.heal(ITEMS["health_potion"]["heal"])
        self.world.float_text(self.hero.x, self.hero.y - 30, f"+{heal:.0f}", (100, 255, 100))

    # --- backpack items ---
    def use_item(self, slot):
        """Use one item from a backpack slot: the Health Potion heals now (shared cooldown), food heals over
        FOOD_DURATION and may give the food buff (replacing any other)."""
        hero = self.hero
        item = self.inventory.item_at(slot)
        if item is None:
            return
        info = ITEMS[item]
        if info["kind"] == "potion":
            if self.potion_cooldown > 0:
                self.world.float_text(hero.x, hero.y - 30, f"Potion ready in {self.potion_cooldown:.0f}s",
                                      (255, 150, 100))
            elif hero.hp >= hero.max_hp:
                self.world.float_text(hero.x, hero.y - 30, "Already at full health", (200, 200, 200))
            else:
                self.inventory.take_from_slot(slot)
                self.potion_cooldown = POTION_COOLDOWN
                heal = hero.heal(info["heal"])
                self.world.float_text(hero.x, hero.y - 30, f"+{heal:.0f}", (100, 255, 100))
            return
        self.inventory.take_from_slot(slot)
        # the meal: heal over time (a new meal replaces the one being eaten)
        hero.buffs[FOOD_HOT] = {"remaining": FOOD_DURATION, "hot_per_sec": info["heal"] / FOOD_DURATION,
                                "item": item}
        if info.get("buff"):
            # one food buff at a time: the new one replaces the old
            hero.buffs[FOOD_BUFF] = {"remaining": info["buff_duration"], "item": item, **info["buff"]}
            hero.refresh_max_hp()
        self.world.float_text(hero.x, hero.y - 30, f"{info['name']}!", (255, 220, 140))

    def set_target(self, eid):
        """Target an enemy (visible, alive) or a friendly hero; anything else (None) clears the target.
        While auto-attacking, a newly targeted enemy is attacked instead."""
        e = self.world.entity(eid) if eid is not None else None
        if e is not None and e in self.world.game_state.monsters:
            if not e.alive or getattr(e, "stealthed", False):
                e = None
            elif self.selected_target is not None:
                self.selected_target = e
        elif e is not None and not (e.alive and e in self.world.game_state.heroes):
            e = None
        self.target = e

    AUTOPILOT_PICKUP_RANGE = 200   # px: a player's autopilot picks up any item lying this close (companions never do)

    def _autopilot_pickup(self):
        """Autopilot (players only): go pick up any dropped item within AUTOPILOT_PICKUP_RANGE. True while doing so."""
        world, hero = self.world, self.hero
        if self.pickup_target is not None and world.ground_item(self.pickup_target) is not None:
            return True                                   # already on the way (_try_pickup takes it in reach)
        skip = self.__dict__.setdefault("_unreachable_items", set())
        items = sorted((g for g in world.ground_items
                        if g.item_id not in skip
                        and (g.x - hero.x) ** 2 + (g.y - hero.y) ** 2 <= self.AUTOPILOT_PICKUP_RANGE ** 2
                        and self.inventory.can_add(g.item)),
                       key=lambda g: (g.x - hero.x) ** 2 + (g.y - hero.y) ** 2)
        for g in items:
            near = (g.x - hero.x) ** 2 + (g.y - hero.y) ** 2 <= self.PICKUP_RANGE ** 2
            path = [] if near else self._path(hero.x, hero.y, g.x, g.y)
            if near or path:
                self.pickup_target = g.item_id
                self.move_path = path
                self._try_pickup()
                return True
            skip.add(g.item_id)                           # behind a wall: don't search for it every frame
        return False

    def _try_pickup(self):
        """Walking to a ground item: take it once in reach (stop if it is gone or the backpack is full)."""
        item = self.world.ground_item(self.pickup_target)
        if item is None:
            self.pickup_target = None
            return
        hero = self.hero
        if (item.x - hero.x) ** 2 + (item.y - hero.y) ** 2 > self.PICKUP_RANGE ** 2:
            return
        self.pickup_target = None
        self.move_path = []
        if self.inventory.add(item.item):
            self.world.remove_ground_item(item)
            self.world.float_text(hero.x, hero.y - 30, f"+{ITEMS[item.item]['name']}", (255, 220, 140))
        else:
            self.world.float_text(hero.x, hero.y - 30, "Backpack full!", (255, 150, 100))

    # --- commands (the client's only way to act; see engine/commands.py) ---
    def _live_monster(self, eid):
        m = self.world.entity(eid) if eid is not None else None
        return m if (m is not None and m.alive and m in self.world.game_state.monsters) else None

    def _path(self, ax, ay, bx, by):
        """Walking path for this hero: searches the whole map, and returns [] (stay put) when the target can't
        be reached — never a straight line through walls."""
        return astar(self.world.dungeon, ax, ay, bx, by, max_steps=None, fallback_direct=False)

    def _step_toward(self, tx, ty, dist, spd):
        """Move up to `spd` px toward (tx, ty), sliding along walls; returns False if completely blocked."""
        hero, wall = self.hero, self.world.is_wall
        step = min(spd, dist)
        nx = hero.x + (tx - hero.x) / dist * step
        ny = hero.y + (ty - hero.y) / dist * step
        if not wall(nx, ny):
            hero.x, hero.y = nx, ny
        elif not wall(nx, hero.y):
            hero.x = nx
        elif not wall(hero.x, ny):
            hero.y = ny
        else:
            return False
        return True

    def _start_dash(self, tx, ty, target, damage, stun):
        """Begin a Charge to (tx, ty) along a walking path (around walls, never through them), however long the
        detour. Range and line of sight are checked by the caller when the charge is initiated.
        Returns False — and does nothing — only if there is no walking path at all."""
        hero = self.hero
        path = self._path(hero.x, hero.y, tx, ty)
        if not path:
            # [] means unreachable — or already on the target's tile (then a short straight hop is fine)
            same_tile = (int(hero.x // TILE_SIZE), int(hero.y // TILE_SIZE)) == (int(tx // TILE_SIZE), int(ty // TILE_SIZE))
            if not same_tile:
                return False
        if not self.world.is_wall(tx, ty) and (not path or path[-1] != (tx, ty)):
            path = path + [(tx, ty)]          # finish exactly at the charge point when it is walkable
        if not path:
            return False
        self.dash_path = path
        self.dash_target_x, self.dash_target_y = path[-1]
        self.dash_active = True
        self.dash_stun_target = target
        self.dash_stun_duration = stun
        self.dash_damage = damage
        return True

    def _friendly(self, eid):
        """A living friendly hero (any player's hero or companion) by id, or None."""
        e = self.world.entity(eid) if eid is not None else None
        if e is None or not e.alive or e not in self.world.game_state.heroes:
            return None
        return e

    def _support_target(self, ally):
        """Who a support skill lands on: the chosen ally if close enough, else the caster.
        Returns None (and says why) if the chosen ally is out of reach."""
        if ally is None or ally is self.hero:
            return self.hero
        if self.hero.distance_to(ally) > SUPPORT_RANGE or not self.world.check_los(self.hero.x, self.hero.y, ally.x, ally.y):
            self.world.float_text(self.hero.x, self.hero.y - 30, "Out of range!", (255, 150, 100))
            return None
        return ally

    def _stop_channel(self):
        """Interrupt a Frostbolt channel (releases the self-immobilize)."""
        self.frostbolt_channeling = False
        self.frostbolt_target = None
        self.hero.conditions = [c for c in self.hero.conditions if c.condition != Condition.IMMOBILIZED]

    def handle(self, cmd):
        """Apply one validated player command (ignored while this player's hero is dead)."""
        world = self.world
        hero = self.hero
        if not hero.alive:
            return
        gs = world.game_state
        if isinstance(cmd, MoveTo):
            # Click ground = move (cancel channel)
            if self.frostbolt_channeling:
                self._stop_channel()
            self.move_path = self._path(hero.x, hero.y, cmd.x, cmd.y)
            self.selected_target = None
            self.ambush_target = None
            self.pending_cast = None
            self.pickup_target = None
        elif isinstance(cmd, SetTarget):
            self.set_target(cmd.target_id)
        elif isinstance(cmd, MoveDir):
            d = (max(-1, min(1, int(cmd.dx))), max(-1, min(1, int(cmd.dy))))
            self.move_dir = d
            if d != (0, 0):
                # walking by keyboard replaces click-to-move / walk-to-target / walk-to-cast
                if self.frostbolt_channeling:
                    self._stop_channel()
                self.move_path = []
                self.pickup_target = None
                self.pending_cast = None
                self.ambush_target = None
        elif isinstance(cmd, UseItem):
            if not self.is_companion:
                self.use_item(cmd.slot)
        elif isinstance(cmd, TradeOpen):
            world.open_trade(self, cmd.hero_id)
        elif isinstance(cmd, (TradeOffer, TradeTake)):
            trade = world.trade_of(self)
            if trade is not None:
                if isinstance(cmd, TradeOffer):
                    trade.offer(self, cmd.slot)
                else:
                    trade.take(self, cmd.item)
        elif isinstance(cmd, TradeAccept):
            world.accept_trade(self)
        elif isinstance(cmd, TradeCancel):
            world.cancel_trade(self)
        elif isinstance(cmd, PickUp):
            item = world.ground_item(cmd.item_id)
            if item is None or self.is_companion:
                return
            if self.frostbolt_channeling:
                self._stop_channel()
            self.pickup_target = item.item_id
            self.selected_target = None
            self.pending_cast = None
            self.ambush_target = None
            self._try_pickup()
            if self.pickup_target is not None:       # not in reach yet: walk there
                self.move_path = self._path(hero.x, hero.y, item.x, item.y)
        elif isinstance(cmd, SelectTarget):
            m = self._live_monster(cmd.target_id)
            if m is None:
                return
            self.pickup_target = None
            self.target = m
            # Click enemy = select + walk to attack range. LOS check — can't target what you can't see
            if not world.check_los(hero.x, hero.y, m.x, m.y):
                world.float_text(hero.x, hero.y - 30, "No line of sight!", (255, 150, 100))
            else:
                # Cancel any active channel
                if self.frostbolt_channeling:
                    self._stop_channel()
                    hero.swing_timer = 0.5  # Brief delay after cancel
                self.selected_target = m
                self.ambush_target = None
                self.pending_cast = None
                self.move_path = []
        elif isinstance(cmd, Cast):
            ab = hero.abilities.get(cmd.ab_key)
            if ab is None:
                return
            enemy = self._live_monster(cmd.target_id)
            # WoW: attacking an enemy with a skill (e.g. the basic attack on key 1) starts auto-attacking it
            attack = enemy is not None and ab.target_kind == "enemy" and not self.ai_enabled
            if attack:
                self.target = enemy
            if ab.is_ready():
                self.cast_ability(cmd.ab_key, ab, cmd.x, cmd.y, enemy, ally=self._friendly(cmd.ally_id))
            if attack and enemy.alive:
                self.selected_target = enemy      # (casting clears it; keep attacking afterwards)
            elif cmd.fallback_move:
                # Skill on cooldown — just move instead
                self.move_path = self._path(hero.x, hero.y, cmd.x, cmd.y)
                self.selected_target = None
        elif isinstance(cmd, InteractNpc):
            npc = world.entity(cmd.npc_id)
            if npc is None or npc not in world.npcs:
                return
            if npc.is_in_range(hero.x, hero.y):
                world.interact_with_npc(npc, self)
            else:
                # Walk to NPC
                self.move_path = self._path(hero.x, hero.y, npc.x, npc.y)
                self.selected_target = None
        elif isinstance(cmd, AmbushTarget):
            m = self._live_monster(cmd.target_id)
            ab_ambush = hero.abilities.get("E")
            if m is None or not hero.stealthed:
                return
            if ab_ambush and ab_ambush.is_ready():
                self.ambush_target = m
                self.selected_target = None
                self.move_path = []
            else:
                world.float_text(hero.x, hero.y - 30, "Ambush on CD!", (255, 150, 100))
        elif isinstance(cmd, UsePotion):
            if self._potion_ready() and hero.hp < hero.max_hp:
                self._use_potion()
        elif isinstance(cmd, ToggleAutopilot):
            self.ai_enabled = not self.ai_enabled
        elif isinstance(cmd, ToggleCompanion):
            if self.is_companion:
                return                       # companions don't summon companions
            comp_info = next((c for c in self.available_companions if c["class"] == cmd.class_name), None)
            if comp_info is None:
                return
            # Already summoned — dismiss; otherwise summon
            existing = [c for c in world.companions if c.owner is self and c.hero.class_name == comp_info["class"]]
            if existing:
                comp = existing[0].hero
                world.dismiss_companion(comp)
                world.float_text(comp.x, comp.y - 30, f"{comp.name} dismissed", (200, 150, 150))
            else:
                comp = world.spawn_companion(comp_info, owner=self)
                world.float_text(comp.x, comp.y - 30, f"{comp.name} joined! (Lv {comp.level})", GOLD)
        elif isinstance(cmd, BindLeftSkill):
            if cmd.ab_key in hero.abilities:
                self.left_ab_key = cmd.ab_key
        elif isinstance(cmd, HoldPosition):
            self.hold_position = bool(cmd.on)
        elif isinstance(cmd, CancelChannel):
            if self.frostbolt_channeling:
                # Cancel channel and stop auto-attack
                self.frostbolt_channel_timer = 0
                self.selected_target = None
                self._stop_channel()
        else:
            raise ValueError(f"unknown command: {cmd!r}")

    # --- casting ---
    def cast_ability(self, ab_key, ab, wx, wy, clicked_monster, ally=None):
        """Cast an ability — handles AoE, single target, dash, stun, call-for-help, and Quinn's Seal system."""
        hero = self.hero
        gs = self.world.game_state

        # Global Cooldown check
        if hero.gcd > 0:
            return  # Can't cast anything during GCD

        # === Tarak special: Stab (fast melee, breaks stealth) ===
        if ab.name == "Stab":
            if not clicked_monster:
                self.world.float_text(hero.x, hero.y - 30, "No target!", (255, 150, 100))
                return
            dist_to_target = hero.distance_to(clicked_monster)
            if dist_to_target > ab.range:
                self.selected_target = clicked_monster
                self.move_path = []
                return
            if hero.swing_timer > 0:
                return  # Gated by weapon speed
            ab.use()
            hero.swing_timer = hero.weapon_speed
            # Break stealth on attack
            if hero.stealthed:
                hero.stealthed = False
                self.world.float_text(hero.x, hero.y - 40, "Stealth broken!", (200, 200, 200))
                # Auto-bind right-click back to Stealth
                self._bind_right("R")
            dmg_amount = ab.calc_damage(hero.base_damage)
            # Crit roll
            hero.last_crit = random.random() < hero.crit_chance
            if hero.last_crit:
                dmg_amount *= hero.crit_multiplier
            dmg = clicked_monster.take_damage(dmg_amount, source=hero, threat=ab.threat_mult)
            color = (255, 255, 50) if hero.last_crit else (180, 255, 180)
            text = f"{dmg:.0f}!" if hero.last_crit else f"{dmg:.0f}"
            self.world.float_text(clicked_monster.x, clicked_monster.y - 20, text, color)
            call_for_help(clicked_monster, gs.monsters, hero)
            if hasattr(clicked_monster, 'aggro_state') and clicked_monster.aggro_state != "aggroed":
                from game.engine.ai import aggro_monster as _aggro
                aggro_monster(clicked_monster, hero, gs.monsters)
            hero.gcd = hero.GCD_DURATION
            self.move_path = []
            self.selected_target = clicked_monster  # Keep target for auto-attack
            return

        # === Tarak special: Stealth (go invisible) ===
        if ab.name == "Stealth":
            ab.use()
            hero.stealthed = True
            self.selected_target = None  # Stop auto-attack
            # Auto-bind right-click to Ambush
            self._bind_right("E")
            # Monsters forget the hero (and reset if nobody else is on their hate table); bosses never let go
            for m in gs.alive_monsters:
                if hero in m.hate and not m.is_boss:
                    drop_from_hate(m, hero)
            self.world.float_text(hero.x, hero.y - 30, "Stealth!", (100, 200, 100))
            hero.gcd = hero.GCD_DURATION
            self.move_path = []
            return

        # === Tarak special: Ambush (stealth-only burst) ===
        if ab.name == "Ambush":
            if not hero.stealthed:
                self.world.float_text(hero.x, hero.y - 30, "Must be stealthed!", (255, 150, 100))
                return
            if not clicked_monster:
                self.world.float_text(hero.x, hero.y - 30, "No target!", (255, 150, 100))
                return
            dist_to_target = hero.distance_to(clicked_monster)
            if dist_to_target > ab.range:
                # Queue walk-to via self.ambush_target (works while stealthed)
                self.ambush_target = clicked_monster
                self.selected_target = None
                self.move_path = []
                return
            ab.use()
            hero.swing_timer = hero.weapon_speed
            # Break stealth
            hero.stealthed = False
            # Auto-bind right-click back to Stealth
            self._bind_right("R")
            # Damage: 5x weapon (no %-of-max-HP bonus: it made boss HP meaningless)
            dmg_amount = ab.calc_damage(hero.base_damage)
            dmg = clicked_monster.take_damage(dmg_amount, source=hero, threat=ab.threat_mult)
            self.world.float_text(clicked_monster.x, clicked_monster.y - 20, f"{dmg:.0f}", (255, 50, 50))
            self.world.float_text(clicked_monster.x, clicked_monster.y - 40, "AMBUSH!", (255, 50, 50))
            self.world.events.append(Ring(clicked_monster.x, clicked_monster.y, 40, (255, 50, 50)))
            call_for_help(clicked_monster, gs.monsters, hero)
            if hasattr(clicked_monster, 'aggro_state') and clicked_monster.aggro_state != "aggroed":
                from game.engine.ai import aggro_monster as _aggro
                aggro_monster(clicked_monster, hero, gs.monsters)
            hero.gcd = hero.GCD_DURATION
            self.move_path = []
            self.selected_target = clicked_monster
            return

        # === Heskan special: Fire Blast (instant ranged single target) ===
        if ab.name == "Fire Blast":
            if not clicked_monster:
                self.world.float_text(hero.x, hero.y - 30, "No target!", (255, 150, 100))
                return
            if hero.distance_to(clicked_monster) > ab.range:
                # Queue walk-to-range
                self.pending_cast = (ab_key, ab, clicked_monster); self.selected_target = clicked_monster
                self.move_path = []
                return
            if not self.world.check_los(hero.x, hero.y, clicked_monster.x, clicked_monster.y):
                self.world.float_text(hero.x, hero.y - 30, "No line of sight!", (255, 150, 100))
                return
            abilities.fire_blast(self.world, hero, clicked_monster, ab)
            hero.gcd = hero.GCD_DURATION
            self.move_path = []
            return

        # === Heskan special: Frost Nova (AoE freeze around self) ===
        if ab.name == "Frost Nova":
            ab.use()
            dmg_amount = ab.calc_damage(hero.base_damage)  # 25% weapon
            hit_count = 0
            for m in gs.alive_monsters:
                if hero.distance_to(m) <= ab.radius:
                    dmg = m.take_damage(dmg_amount, source=hero, threat=ab.threat_mult)
                    frozen = m.apply_condition(Condition.FROZEN, 4.0)
                    self.world.float_text(m.x, m.y - 20, f"{dmg:.0f}", (180, 220, 255))
                    self.world.float_text(m.x, m.y - 35, "FROZEN" if frozen else "IMMUNE", (150, 220, 255))
                    hit_count += 1
            self.world.events.append(Ring(hero.x, hero.y, ab.radius, (150, 200, 255)))
            if hit_count == 0:
                self.world.float_text(hero.x, hero.y - 30, "No enemies in range!", (200, 200, 200))
            hero.gcd = hero.GCD_DURATION
            self.move_path = []
            return

        # === Heskan special: Frostbolt (start channel — fires on completion) ===
        if ab.name == "Frostbolt":
            if self.frostbolt_channeling:
                return  # Already channeling, wait for completion
            if not clicked_monster:
                self.world.float_text(hero.x, hero.y - 30, "No target!", (255, 150, 100))
                return
            dist_to_target = hero.distance_to(clicked_monster)
            if dist_to_target > ab.range:
                # Walk into range, then start channeling
                self.selected_target = clicked_monster
                self.move_path = []
                return
            # Line of sight check
            if not self.world.check_los(hero.x, hero.y, clicked_monster.x, clicked_monster.y):
                self.world.float_text(hero.x, hero.y - 30, "No line of sight!", (255, 150, 100))
                return
            # Start channeling (immobilize self for weapon_speed duration)
            self.frostbolt_channeling = True
            self.frostbolt_channel_timer = hero.weapon_speed
            self.frostbolt_target = clicked_monster
            self.selected_target = clicked_monster
            hero.apply_condition(Condition.IMMOBILIZED, hero.weapon_speed)
            ab.use()  # Put on cooldown at start of channel (expires when channel ends)
            self.move_path = []
            return

        # === Quinn special: Wanding (ranged projectile auto-attack) ===
        if ab.name == "Wanding":
            if not clicked_monster:
                self.world.float_text(hero.x, hero.y - 30, "No target!", (255, 150, 100))
                return
            dist_to_target = hero.distance_to(clicked_monster)
            if dist_to_target > ab.range:
                self.pending_cast = (ab_key, ab, clicked_monster); self.selected_target = clicked_monster
                return
            if not self.world.check_los(hero.x, hero.y, clicked_monster.x, clicked_monster.y):
                self.world.float_text(hero.x, hero.y - 30, "No line of sight!", (255, 150, 100))
                return
            if hero.swing_timer > 0:
                return  # Gated by weapon speed
            abilities.ranged_projectile(self.world, hero, clicked_monster, ab, color=(255, 220, 100))
            hero.gcd = hero.GCD_DURATION
            # Don't clear self.selected_target — keep auto-attacking
            self.move_path = []
            return

        # === Quinn special: Wall (absorb shield on self or a chosen ally) ===
        if ab.name == "Wall":
            target = self._support_target(ally)
            if target is None:
                return
            ab.use()
            shield_amount = wall_shield(hero, ab)   # potion amount (200) at skill level 3
            target.absorb_shield = shield_amount
            target.buffs["Wall"] = {"remaining": 15.0}
            self.world.credit_heal(hero, target, shield_amount)   # shielding generates hate like healing
            self.world.float_text(target.x, target.y - 30, f"Wall +{shield_amount:.0f}!", (255, 215, 60))
            hero.gcd = hero.GCD_DURATION
            self.move_path = []
            return

        # === Quinn special: Renew (HoT on self or a chosen ally) ===
        if ab.name == "Renew":
            target = self._support_target(ally)
            if target is None:
                return
            ab.use()
            hot_total = renew_total(hero, ab)   # 50% of the potion amount (100) at skill level 3
            hot_duration = 8.0
            target.buffs["Renew"] = {"remaining": hot_duration, "hot_per_sec": hot_total / hot_duration,
                                     "source": hero}   # each tick's healing is credited to the caster's hate
            self.world.credit_heal(hero, target, 0)       # in combat with the friend -> on the mobs' tables now
            self.world.float_text(target.x, target.y - 30, "Renew!", (100, 255, 150))
            hero.gcd = hero.GCD_DURATION
            self.move_path = []
            return

        # === Fighter: Heroic Strike (self-buff: the next Strike / Cleave hit gets +b damage and more threat) ===
        if ab.name == "Heroic Strike":
            ab.use()
            hero.buffs["Heroic Strike"] = {"remaining": HEROIC_STRIKE_WINDOW, "bonus": ab.flat_bonus,
                                           "threat": ab.threat_mult}
            self.world.float_text(hero.x, hero.y - 30, "Heroic Strike!", (255, 160, 80))
            hero.gcd = hero.GCD_DURATION
            return

        # === Fighter: Cleave (target + nearest adjacent enemies, capped by skill level) ===
        if ab.max_targets:
            target = clicked_monster
            if target is None:
                near = [m for m in gs.alive_monsters if hero.distance_to(m) <= ab.radius
                        and not getattr(m, "stealthed", False)]
                target = min(near, key=hero.distance_to) if near else None
            if target is None:
                self.world.float_text(hero.x, hero.y - 30, "No target!", (255, 150, 100))
                return
            if hero.distance_to(target) > ab.range:
                self.pending_cast = (ab_key, ab, target); self.selected_target = target
                return
            others = [m for m in gs.alive_monsters if m is not target and not getattr(m, "stealthed", False)]
            hits = hero.use_ability(ab_key, [target] + others)
            if hits:
                self.world.events.append(Ring(hero.x, hero.y, ab.radius, ab.color))
                self.world.float_text(target.x, target.y - 20, " ".join(f"{d:.0f}" for _, d in hits), GOLD)
                call_for_help(target, gs.monsters, hero)
                hero.gcd = hero.GCD_DURATION
                self.move_path = []
            return

        # === Quinn special: Righteous Seal (self-buff, no target needed) ===
        if ab.name == "Righteous Seal":
            ab.use()
            hero.buffs["Righteous Seal"] = {"remaining": 10.0, "bonus": seal_bonus(ab)}
            self.world.float_text(hero.x, hero.y - 30, "Seal Active!", (255, 220, 80))
            hero.gcd = hero.GCD_DURATION
            self.move_path = []
            return

        # === Quinn special: Holy Light (heal self or a chosen ally + immobilize self while casting) ===
        if ab.name == "Holy Light":
            target = self._support_target(ally)
            if target is None:
                return
            ab.use()
            # Start casting — immobilize for 2s, heal lands (on the target) after cast finishes
            hero.apply_condition(Condition.IMMOBILIZED, 2.0)
            hero.buffs["Holy Light Casting"] = {"remaining": 2.0, "heal": holy_light_heal(ab),
                                                "target_id": target.eid if target is not hero else None}
            self.world.float_text(hero.x, hero.y - 30, "Casting...", (255, 255, 150))
            hero.gcd = hero.GCD_DURATION
            self.move_path = []
            return

        # === Quinn special: Judgement (ranged, consumes Seal for bonus damage) ===
        if ab.name == "Judgement":
            if not clicked_monster:
                self.world.float_text(hero.x, hero.y - 30, "No target!", (255, 150, 100))
                return
            dist_to_target = hero.distance_to(clicked_monster)
            if dist_to_target > ab.range:
                self.pending_cast = (ab_key, ab, clicked_monster); self.selected_target = clicked_monster
                return
            if not self.world.check_los(hero.x, hero.y, clicked_monster.x, clicked_monster.y):
                self.world.float_text(hero.x, hero.y - 30, "No line of sight!", (255, 150, 100))
                return
            abilities.judgement(self.world, hero, clicked_monster, ab)
            hero.gcd = hero.GCD_DURATION
            self.move_path = []
            self.selected_target = None
            return

        # === Quinn special: Smite (boosted by Seal) ===
        if ab.name == "Smite":
            if not clicked_monster:
                self.world.float_text(hero.x, hero.y - 30, "No target!", (255, 150, 100))
                return
            dist_to_target = hero.distance_to(clicked_monster)
            if dist_to_target > ab.range:
                self.pending_cast = (ab_key, ab, clicked_monster); self.selected_target = clicked_monster
                return
            if hero.swing_timer > 0:
                return  # Gated by weapon speed
            ab.use()
            hero.swing_timer = hero.weapon_speed
            sealed = "Righteous Seal" in hero.buffs
            skill_dmg = smite_damage(hero, ab)     # (a + Seal bonus) x weapon + b
            dmg = clicked_monster.take_damage(skill_dmg, source=hero, threat=ab.threat_mult)
            color = (255, 230, 100) if sealed else (255, 255, 255)
            self.world.float_text(clicked_monster.x, clicked_monster.y - 20, f"{dmg:.0f}", color)
            call_for_help(clicked_monster, gs.monsters, hero)
            hero.gcd = hero.GCD_DURATION
            self.move_path = []
            self.selected_target = None
            return

        # === Vistra special: Demoralizing Shout (AoE debuff) ===
        if ab.name == "Demoralizing Shout":
            ab.use()
            hit_count = 0
            for m in gs.alive_monsters:
                if hero.distance_to(m) <= ab.radius:
                    # enemy damage x0.9 / x0.8 / x0.7 (skill level 1 / 2 / 3) for 10s
                    m.buffs["Demoralized"] = {"remaining": 10.0, "damage_mult": 1.0 - shout_reduction(ab)}
                    # Slow for 3s
                    m.apply_condition(Condition.SLOWED, 3.0, slow_factor=0.5)
                    self.world.float_text(m.x, m.y - 20, "Demoralized!", (200, 150, 50))
                    hit_count += 1
            if hit_count > 0:
                self.world.events.append(Ring(hero.x, hero.y, ab.radius, ab.color))
            hero.gcd = hero.GCD_DURATION
            self.move_path = []
            return

        # === Standard ability handling ===
        if ab.radius > 0:
            # AoE — check if click location is within ability range
            dist_to_click = math.sqrt((wx - hero.x)**2 + (wy - hero.y)**2)
            if dist_to_click > ab.range and ab.range > 0:
                self.pending_cast = (ab_key, ab, clicked_monster); self.selected_target = clicked_monster
                return
            hits = hero.use_ability(ab_key, gs.alive_monsters, target_pos=(wx, wy))
            if hits:
                self.world.events.append(Ring(wx, wy, ab.radius, ab.color))
                for name, dmg in hits:
                    self.world.float_text(wx, wy-20, f"{dmg:.0f}", GOLD)
        elif clicked_monster:
            # Single target — check range
            dist_to_target = hero.distance_to(clicked_monster)
            if dist_to_target > ab.range:
                self.pending_cast = (ab_key, ab, clicked_monster); self.selected_target = clicked_monster
                return
            # Dash abilities: delay damage until arrival
            if ab.is_dash:
                # Line of sight check — can't charge through walls
                if not self.world.check_los(hero.x, hero.y, clicked_monster.x, clicked_monster.y):
                    self.world.float_text(hero.x, hero.y - 30, "No line of sight!", (255, 150, 100))
                    return
                dx = clicked_monster.x - hero.x
                dy = clicked_monster.y - hero.y
                d = math.sqrt(dx*dx + dy*dy)
                if d > 0:
                    # stop 50 px short of the target; damage is applied on arrival
                    if not self._start_dash(clicked_monster.x - (dx/d) * 50, clicked_monster.y - (dy/d) * 50,
                                            clicked_monster, ab.calc_damage(hero.base_damage), ab.stun_duration):
                        self.world.float_text(hero.x, hero.y - 30, "Can't charge there!", (255, 150, 100))
                        return
                ab.use()  # Put on cooldown
                call_for_help(clicked_monster, gs.monsters, hero)
            else:
                # Non-dash single target: deal damage immediately
                hits = hero.use_ability(ab_key, [clicked_monster])
                for name, dmg in hits:
                    self.world.float_text(clicked_monster.x, clicked_monster.y-20, f"{dmg:.0f}", (255, 255, 255))
                if ab.stun_duration > 0 and clicked_monster.alive:
                    stunned = clicked_monster.apply_condition(Condition.STUNNED, ab.stun_duration)
                    self.world.float_text(clicked_monster.x, clicked_monster.y-35, "STUNNED" if stunned else "IMMUNE", (255,255,100))
                call_for_help(clicked_monster, gs.monsters, hero)
        else:
            # No target clicked for single-target skill
            self.world.float_text(hero.x, hero.y - 30, "No target!", (255, 150, 100))
            return
        hero.gcd = hero.GCD_DURATION
        self.move_path = []
        self.selected_target = None

    def update(self, dt):
        """Frostbolt channel completion, path-following movement and the dash animation."""
        hero = self.hero
        gs = self.world.game_state
        self.potion_cooldown = max(0.0, self.potion_cooldown - dt)
        t = self.target
        if t is not None and (not t.alive or getattr(t, "stealthed", False)):
            self.target = None               # the target died or vanished
        if self.pickup_target is not None:
            self._try_pickup()
        # Frostbolt channel completion
        if self.frostbolt_channeling:
            self.frostbolt_channel_timer -= dt
            if self.frostbolt_channel_timer <= 0:
                self.frostbolt_channeling = False
                # Fire projectile if target still alive (range doesn't matter — bolt chases)
                if self.frostbolt_target and self.frostbolt_target.alive:
                    frostbolt = next(a for a in hero.abilities.values() if a.name == "Frostbolt")
                    proj_damage = frostbolt.calc_damage(hero.base_damage)   # 100% weapon at skill level 3
                    proj = Projectile(x=hero.x, y=hero.y, target=self.frostbolt_target,
                                      speed=500.0, damage=proj_damage,
                                      color=(150, 200, 255), source=hero, threat=frostbolt.threat_mult)
                    proj.apply_slow = True  # Flag for slow on hit
                    self.world.projectiles.append(proj)
                else:
                    # Target dead — stop
                    self.frostbolt_target = None
                    self.selected_target = None
            # If target died mid-channel, cancel
            elif self.frostbolt_target and not self.frostbolt_target.alive:
                self.frostbolt_channeling = False
                self.frostbolt_target = None
                self.selected_target = None
                # Remove immobilize early
                hero.conditions = [c for c in hero.conditions if c.condition != Condition.IMMOBILIZED]

        # WASD: walk in the held direction (slides along walls), like the path walk below
        if self.move_dir != (0, 0) and not self.dash_active and not (
                hero.has_condition(Condition.IMMOBILIZED) or hero.has_condition(Condition.STUNNED)
                or hero.has_condition(Condition.FROZEN)):
            dx, dy = self.move_dir
            norm = math.hypot(dx, dy)
            spd = hero.base_speed * dt * (0.6 if hero.stealthed else 1.0)
            self._step_toward(hero.x + dx / norm * 100, hero.y + dy / norm * 100, 100, spd)
            if dx:
                hero.facing_left = dx < 0

        # Smooth movement along path
        if self.move_path and not self.dash_active and not hero.has_condition(Condition.IMMOBILIZED):
            tx, ty = self.move_path[0]
            dx, dy = tx - hero.x, ty - hero.y
            dist = math.sqrt(dx*dx + dy*dy)
            if dist < 8:
                self.move_path.pop(0)
            else:
                spd = hero.base_speed * dt
                if hero.stealthed:
                    spd *= 0.6  # 60% move speed while stealthed
                if not self._step_toward(tx, ty, dist, spd):   # never into a wall
                    self.move_path = []
                hero.facing_left = dx < 0

        # Dash animation (Charge skill)
        if self.dash_active:
            # Charge follows its path (waypoints) at dash speed
            path = getattr(self, "dash_path", None) or [(self.dash_target_x, self.dash_target_y)]
            while len(path) > 1 and math.hypot(path[0][0] - hero.x, path[0][1] - hero.y) < 10:
                path.pop(0)
            self.dash_path = path
            wx, wy = path[0]
            dx = wx - hero.x
            dy = wy - hero.y
            dist = math.sqrt(dx*dx + dy*dy)
            if dist < 10 and len(path) == 1:
                # Arrived — deal damage + apply stun
                self.dash_active = False
                self.dash_path = []
                if not self.world.is_wall(wx, wy):
                    hero.x, hero.y = wx, wy
                if self.dash_stun_target and self.dash_stun_target.alive:
                    charge = next((x for x in hero.abilities.values() if x.is_dash), None)
                    dmg = self.dash_stun_target.take_damage(self.dash_damage, source=hero,
                                                            threat=charge.threat_mult if charge else 1.0)
                    self.world.float_text(self.dash_stun_target.x, self.dash_stun_target.y-20, f"{dmg:.0f}", (255, 200, 50))
                    if self.dash_stun_duration > 0 and self.dash_stun_target.alive:
                        stunned = self.dash_stun_target.apply_condition(Condition.STUNNED, self.dash_stun_duration)
                        self.world.float_text(self.dash_stun_target.x, self.dash_stun_target.y-35, "STUNNED" if stunned else "IMMUNE", (255,255,100))
                self.dash_stun_target = None
                self.dash_damage = 0
            else:
                spd = self.dash_speed * dt
                if dist > 0 and not self._step_toward(wx, wy, dist, spd):
                    # blocked (shouldn't happen on a path): end the charge here
                    self.dash_path = [(hero.x, hero.y)]
                hero.facing_left = dx < 0

    def run_ai(self, dt):
        """Autopilot: let the hero AI act (potion, dash, abilities, movement) when enabled.
        Returns the AI's action dict (None when the autopilot is off or mid-dash)."""
        hero = self.hero
        gs = self.world.game_state
        # === HERO AI (when enabled) ===
        if not (self.ai_enabled and not self.dash_active):
            return None
        if not self.is_companion and self._autopilot_pickup():
            return None                  # walking to a dropped item: that comes first
        ai_action = self.hero_ai.update(gs.alive_monsters, dt, self.world.is_wall)

        # Debug log
        if self.world.debug and int(gs.game_time * 2) != int((gs.game_time - dt) * 2):  # Log every 0.5s
            alive_count = len(gs.alive_monsters)
            target_dist = f" target_dist={hero.distance_to(self.hero_ai.target):.0f}" if self.hero_ai.target and self.hero_ai.target.alive else ""
            target_hp = f" boss_hp={self.hero_ai.target.hp:.0f}/{self.hero_ai.target.max_hp}" if self.hero_ai.target and self.hero_ai.target.alive else ""
            action_name = ai_action['use_ability'] or ('DASH' if ai_action.get('dash') else ('MOVE' if ai_action.get('move_to') else ('BASIC_ATK' if ai_action.get('basic_attack') else ('EXPLORE' if not alive_count else 'IDLE'))))
            target_pos = f" target_pos=({self.hero_ai.target.x:.0f},{self.hero_ai.target.y:.0f})" if self.hero_ai.target and self.hero_ai.target.alive else ""
            path_len = f" path_len={len(self.move_path)}" if self.move_path else " path_len=0"
            print(f"[AI t={gs.game_time:.1f}s] monsters={alive_count} hp={hero.hp:.0f}/{hero.max_hp} pos=({hero.x:.0f},{hero.y:.0f}) action={action_name}{target_dist}{target_pos}{target_hp}{path_len}", flush=True)
            # Log all alive units
            for m in gs.alive_monsters:
                dist_to_hero = hero.distance_to(m)
                print(f"  [MOB] {m.name} pos=({m.x:.0f},{m.y:.0f}) hp={m.hp:.0f}/{m.max_hp} dist={dist_to_hero:.0f} aggro={getattr(m, 'aggro_state', '?')}", flush=True)
            for other in self.world.companions:
                comp = other.hero
                if comp.alive and other is not self:
                    print(f"  [COMP] {comp.name} pos=({comp.x:.0f},{comp.y:.0f}) hp={comp.hp:.0f}/{comp.max_hp} dist_to_hero={hero.distance_to(comp):.0f}", flush=True)

        if ai_action["use_potion"] and self._potion_ready() and hero.hp < hero.max_hp:
            self._use_potion()

        if ai_action["dash"]:
            # Charge ability
            tx, ty, target_m, dmg, stun = ai_action["dash"]
            ab = hero.abilities.get("R")
            if ab and ab.is_ready():
                if not self.world.check_los(hero.x, hero.y, target_m.x, target_m.y):
                    # No LOS — pathfind toward target
                    self.move_path = self._path(hero.x, hero.y, target_m.x, target_m.y)
                elif self._start_dash(tx, ty, target_m, dmg, stun):
                    ab.use()
                else:
                    # no walking path at all: walk toward it instead (cooldown kept)
                    self.move_path = self._path(hero.x, hero.y, target_m.x, target_m.y)
                call_for_help(target_m, gs.monsters, hero)

        elif ai_action["use_ability"]:
            ab_key = ai_action["use_ability"]
            ab = hero.abilities.get(ab_key)
            if ab and ab.is_ready():
                target_m = ai_action.get("ability_target_monster")
                # Check LOS before casting — if blocked, pathfind toward target to get LOS
                if target_m and not self.world.check_los(hero.x, hero.y, target_m.x, target_m.y):
                    self.move_path = self._path(hero.x, hero.y, target_m.x, target_m.y)
                else:
                    # Route through _cast_ability for consistent handling
                    wx = target_m.x if target_m else hero.x
                    wy = target_m.y if target_m else hero.y
                    self.cast_ability(ab_key, ab, wx, wy, target_m, ally=ai_action.get("ability_target_ally"))

        elif ai_action["move_to"]:
            tx, ty = ai_action["move_to"]
            # Repath every 0.5s or if path empty
            if not hasattr(hero, '_ai_repath_timer'):
                hero._ai_repath_timer = 0
                hero._ai_unreachable = set()  # Track unreachable monster IDs
            hero._ai_repath_timer -= dt
            if hero._ai_repath_timer <= 0 or not self.move_path:
                self.move_path = self._path(hero.x, hero.y, tx, ty)
                hero._ai_repath_timer = 0.5
                # If path is empty and target is nearby, it's unreachable
                if not self.move_path and self.hero_ai.target and self.hero_ai.target.alive:
                    dist_to_target = hero.distance_to(self.hero_ai.target)
                    if dist_to_target < 300:
                        hero._ai_unreachable.add(id(self.hero_ai.target))
                        self.hero_ai.target = None  # Force retarget next frame
        return ai_action

    def follow_owner(self, dt):
        """Companion with nothing to do: stay near the owner (teleport back if left far behind)."""
        comp, lead = self.hero, self.owner.hero
        world = self.world
        dist_to_lead = comp.distance_to(lead)
        if dist_to_lead > 600:
            # Too far — teleport to the owner (walkable position)
            comp.x, comp.y = world.find_walkable_nearby(lead.x, lead.y, radius=60)
            self._follow_path = None
        elif dist_to_lead > 80:
            self._follow_path = self._path(comp.x, comp.y, lead.x, lead.y)   # owner moves: re-path
        else:
            self._follow_path = None
        path = getattr(self, "_follow_path", None)
        if path:
            tx, ty = path[0]
            d = math.sqrt((tx - comp.x) ** 2 + (ty - comp.y) ** 2)
            if d < 12:
                path.pop(0)
            else:
                spd = comp.base_speed * dt
                nx = comp.x + ((tx - comp.x) / d) * min(spd, d)
                ny = comp.y + ((ty - comp.y) / d) * min(spd, d)
                if not world.is_wall(nx, ny):
                    comp.x, comp.y = nx, ny
                elif not world.is_wall(nx, comp.y):
                    comp.x = nx
                elif not world.is_wall(comp.x, ny):
                    comp.y = ny
                else:
                    self._follow_path = None
                comp.facing_left = (tx - comp.x) < 0

    def update_companion(self, dt):
        """One frame of an AI companion: the same steps a player hero on autopilot runs, then follow the owner
        when the AI has nothing to do (no monster to fight, no path to walk)."""
        self.update(dt)
        action = self.run_ai(dt)
        # Never follow (or teleport to) the owner during a fight: between swings / cooldowns the AI has nothing to do
        # for a moment, and stepping toward the owner then back made melee companions shuffle left and right.
        if self.in_combat():
            return
        busy = (self.dash_active or self.frostbolt_channeling or self.move_path
                or (action and (action.get("use_ability") or action.get("move_to") or action.get("dash"))))
        if not busy:
            self.follow_owner(dt)

    def in_combat(self):
        """Companion's party fight is on: an aggroed monster is fighting this companion or its owner (has them on its
        hate table or as its target), or the companion's own target is aggroed."""
        mine = (self.hero, self.owner.hero)
        for m in self.world.game_state.monsters:
            if not m.alive or m.aggro_state != AggroState.AGGROED:
                continue
            if m.aggro_target in mine or any(h in m.hate for h in mine):
                return True
        target = self.hero_ai.target
        return target is not None and target.alive and target.aggro_state == AggroState.AGGROED

    def update_ambush(self):
        """Tarak's walk-to-target Ambush while stealthed (manual play only)."""
        hero = self.hero
        gs = self.world.game_state
        # Ambush walk-to: walk toward target in stealth, execute Ambush when in range
        if self.ambush_target and not self.ai_enabled:
            if not self.ambush_target.alive or not hero.stealthed:
                self.ambush_target = None
                self.move_path = []
            elif not self.world.check_los(hero.x, hero.y, self.ambush_target.x, self.ambush_target.y):
                # Lost LOS — cancel
                self.ambush_target = None
                self.move_path = []
            else:
                dist = hero.distance_to(self.ambush_target)
                ab_ambush = hero.abilities.get("E")
                if dist <= ab_ambush.range and ab_ambush and ab_ambush.is_ready():
                    # In range — execute Ambush
                    self.cast_ability("E", ab_ambush, self.ambush_target.x, self.ambush_target.y, self.ambush_target)
                    self.ambush_target = None
                else:
                    # Walk toward target using pathfinding
                    if not self.move_path:
                        self.move_path = self._path(hero.x, hero.y, self.ambush_target.x, self.ambush_target.y)

    def auto_attack(self):
        """Auto-attack the selected target (walk to range, attack when close) with the left-click skill.
        While `hold_position` (Shift) is set it does not walk toward an out-of-range target."""
        left_ab_key = self.left_ab_key
        hold_position = self.hold_position
        hero = self.hero
        gs = self.world.game_state
        # Auto-attack selected target (walk to range, attack when close)
        if self.selected_target and not self.ai_enabled and not self.frostbolt_channeling and not hero.stealthed and not hero.has_condition(Condition.IMMOBILIZED):
            if not self.selected_target.alive:
                self.selected_target = None
                self.pending_cast = None
            elif not self.world.check_los(hero.x, hero.y, self.selected_target.x, self.selected_target.y):
                # Lost line of sight — drop target
                self.selected_target = None
                self.pending_cast = None
            else:
                dist = hero.distance_to(self.selected_target)
                # Check if we have a queued ability to fire
                if self.pending_cast and dist <= self.pending_cast[1].range:
                    ab_key, ab, target_m = self.pending_cast
                    self.pending_cast = None
                    if ab.is_ready() and hero.gcd <= 0:
                        self.cast_ability(ab_key, ab, target_m.x, target_m.y, target_m)
                elif dist <= hero.attack_range:
                    # In range — use left-click skill
                    ab_key = left_ab_key
                    ab = hero.abilities[ab_key]
                    if ab.is_ready() and hero.gcd <= 0 and hero.swing_timer <= 0:
                        target = self.selected_target
                        self.cast_ability(ab_key, ab, target.x, target.y, target)
                        if target.alive and self.selected_target is None:
                            self.selected_target = target     # casting clears it; auto-attack keeps going
                elif not hold_position and self.move_dir == (0, 0):
                    # Out of range (and not steering with WASD / holding Shift) — pathfind toward target
                    if not self.move_path:
                        self.move_path = self._path(hero.x, hero.y, self.selected_target.x, self.selected_target.y)
