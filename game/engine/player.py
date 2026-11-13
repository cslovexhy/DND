"""PlayerState: the local player's hero controller (pure; no pygame).

Holds the per-player control state that used to be module globals in session.py (move path, target,
queued casts, potions, autopilot; a dash or channel lives on the hero, engine/actions.py) and the rules that act on it. The client feeds
it intents (cast_ability, move_path, selected_target ...) and calls the update_* methods in frame order.
Skill-slot bindings (which key is the left/right click skill) are UI state and stay in the client;
the controller asks the client to rebind through a BindRightSkill event.
"""
import math

from game.engine import actions, casting
from game.engine.ai import AggroState
from game.engine.commands import (MoveTo, SelectTarget, Cast, InteractNpc, AmbushTarget, UsePotion,
                                  ToggleAutopilot, ToggleCompanion, CancelChannel, BindLeftSkill, HoldPosition,
                                  UseItem, Unequip, PickUp, SetTarget, MoveDir, TradeOpen, TradeOffer, TradeTake,
                                  TradeAccept, TradeCancel)
from game.engine.inventory import Inventory
from game.content.items import (ITEMS, POTION_COOLDOWN, FOOD_DURATION, FOOD_BUFF, FOOD_HOT, DRINK_DURATION,
                                DRINK_BUFF, DRINK_HOT)
from game.content.equipment import equip, is_gear, slot_for
from game.engine.events import BindRightSkill, GOLD
from game.engine.hero_ai import create_hero_ai
from game.content.heroes import HERO_CLASSES
from game.engine.world_map import TILE_SIZE
from game.content.skill_tree import stealth_upkeep

# a failed cast's reason (engine/casting.py) -> what the player sees
MESSAGES = {"no target": "No target!", "no line of sight": "No line of sight!", "out of range": "Out of range!",
            "can't reach": "Can't charge there!"}
CAST_QUEUE_SECS = 1.0         # a skill pressed during the global cooldown waits this long to fire


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
        # A Cast pressed during the global cooldown (fires when it ends, see update)
        self.queued_cast = None
        self.queued_cast_timer = 0.0
        # Ambush walk-to state (Tarak): monster to ambush (walk toward, execute when in range)
        self.ambush_target = None

    @property
    def is_companion(self):
        return self.owner is not None

    def _end_stealth(self, text):
        """Leave stealth on purpose (cancel) or because the mana ran out."""
        hero = self.hero
        hero.stealthed = False
        self.ambush_target = None
        self._bind_right("R")                        # right-click back to Stealth
        self.world.float_text(hero.x, hero.y - 30, text, (200, 200, 200))

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

    # --- equipment (content/equipment.py) ---
    def equip_from_slot(self, slot):
        """Equip the weapon / shield in this backpack slot (where: equipment.slot_for). Whatever it replaces goes
        back into the backpack; if that does not fit, nothing changes."""
        hero = self.hero
        item = self.inventory.item_at(slot)
        if item is None or not is_gear(item):
            return
        where = slot_for(hero.class_name, item, hero.equipment)
        try:
            new_eq, removed = equip(hero.class_name, hero.equipment, item, where)
        except ValueError as e:
            self.world.float_text(hero.x, hero.y - 30, str(e).capitalize(), (255, 150, 100))
            return
        inv = self.inventory.copy()
        inv.take_from_slot(slot)
        if not all(inv.add(r) for r in removed):
            self.world.float_text(hero.x, hero.y - 30, "Backpack full!", (255, 150, 100))
            return
        self.inventory.slots = inv.slots
        self._set_equipment(new_eq)
        self.world.float_text(hero.x, hero.y - 30, f"Equipped {ITEMS[item]['name']}", (220, 220, 255))

    def unequip(self, slot):
        """Take the item in an equipment slot off, into the backpack (not if the backpack is full)."""
        hero = self.hero
        item = hero.equipment.get(slot) if slot in ("main", "off") else None
        if item is None:
            return
        if not self.inventory.add(item):
            self.world.float_text(hero.x, hero.y - 30, "Backpack full!", (255, 150, 100))
            return
        self._set_equipment({**hero.equipment, slot: None})

    def _set_equipment(self, equipment):
        hero = self.hero
        hero.equipment = equipment
        hero.refresh_gear()
        hero.swing_timer = min(hero.swing_timer, hero.weapon_speed)   # a faster weapon is ready no later

    # --- backpack items ---
    def use_item(self, slot):
        """Use one item from a backpack slot: potions restore HP / mana now (one shared cooldown), food heals over
        FOOD_DURATION and may give the food buff, drinks restore HP / mana over DRINK_DURATION and may give the drink
        buff (each buff replacing the older one of its kind)."""
        hero = self.hero
        item = self.inventory.item_at(slot)
        if item is None:
            return
        info = ITEMS[item]
        if info["kind"] in ("weapon", "shield"):
            self.equip_from_slot(slot)
            return
        if info["kind"] == "potion":
            heal, mana = info.get("heal", 0), info.get("mana", 0)
            if self.potion_cooldown > 0:
                self.world.float_text(hero.x, hero.y - 30, f"Potion ready in {self.potion_cooldown:.0f}s",
                                      (255, 150, 100))
            elif not ((heal and hero.hp < hero.max_hp) or (mana and hero.mana < hero.max_mana)):
                self.world.float_text(hero.x, hero.y - 30,
                                      "Already at full health" if heal else "Already at full mana", (200, 200, 200))
            else:
                self.inventory.take_from_slot(slot)
                self.potion_cooldown = POTION_COOLDOWN
                if heal:
                    healed = hero.heal(heal)
                    self.world.float_text(hero.x, hero.y - 30, f"+{healed:.0f}", (100, 255, 100))
                if mana:
                    restored = hero.restore_mana(mana)
                    self.world.float_text(hero.x, hero.y - 45, f"+{restored:.0f} mana", (100, 170, 255))
            return
        self.inventory.take_from_slot(slot)
        if info["kind"] == "drink":
            # the drink: HP / mana over time (a new drink replaces the one being drunk)
            hot = {"remaining": DRINK_DURATION, "item": item}
            if info.get("heal"):
                hot["hot_per_sec"] = info["heal"] / DRINK_DURATION
            if info.get("mana"):
                hot["mana_per_sec"] = info["mana"] / DRINK_DURATION
            hero.buffs[DRINK_HOT] = hot
            if info.get("buff"):
                # one drink buff at a time: the new one replaces the old
                hero.buffs[DRINK_BUFF] = {"remaining": info["buff_duration"], "item": item, **info["buff"]}
            self.world.float_text(hero.x, hero.y - 30, f"{info['name']}!", (140, 200, 255))
            return
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
        """Walking path for this hero: the whole map, [] (stay put) when the target can't be reached."""
        return actions.walk_path(self.world, ax, ay, bx, by)

    def _step_toward(self, tx, ty, dist, spd):
        """Move up to `spd` px toward (tx, ty), sliding along walls; returns False if completely blocked."""
        return actions.step_toward(self.world, self.hero, tx, ty, dist, spd)

    def _friendly(self, eid):
        """A living friendly hero (any player's hero or companion) by id, or None."""
        e = self.world.entity(eid) if eid is not None else None
        if e is None or not e.alive or e not in self.world.game_state.heroes:
            return None
        return e

    def _stop_channel(self):
        """Interrupt a channel (Frostbolt, Holy Light): nothing happens, the caster can move again."""
        actions.cancel_channel(self.hero)

    def handle(self, cmd):
        """Apply one validated player command (ignored while this player's hero is dead)."""
        world = self.world
        hero = self.hero
        if not hero.alive:
            return
        gs = world.game_state
        if isinstance(cmd, MoveTo):
            # Click ground = move (cancel channel)
            if hero.channel is not None:
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
                if hero.channel is not None:
                    self._stop_channel()
                self.move_path = []
                self.pickup_target = None
                self.pending_cast = None
                self.ambush_target = None
        elif isinstance(cmd, UseItem):
            if not self.is_companion:
                self.use_item(cmd.slot)
        elif isinstance(cmd, Unequip):
            if not self.is_companion:
                self.unequip(cmd.slot)
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
            if hero.channel is not None:
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
                if hero.channel is not None:
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
            if ab.toggle and hero.stealthed:
                self._end_stealth("Stealth cancelled")      # press again to cancel: free, no new cooldown
                return
            if hero.gcd > 0 and ab.remaining <= 0:
                # pressed during the global cooldown: queue it, it fires the moment the GCD ends (see update)
                self.queued_cast = cmd
                self.queued_cast_timer = CAST_QUEUE_SECS
                return
            enemy = self._live_monster(cmd.target_id)
            # WoW: attacking an enemy with a skill (e.g. the basic attack on key 1) starts auto-attacking it
            attack = enemy is not None and ab.target_kind == "enemy" and not self.ai_enabled
            if attack:
                self.target = enemy
            if ab.is_ready():
                self.cast_ability(cmd.ab_key, ab, cmd.x, cmd.y, enemy, ally=self._friendly(cmd.ally_id))
            elif ab.remaining <= 0 and not ab.has_mana():
                world.float_text(hero.x, hero.y - 30, "Not enough mana!", (120, 160, 255))
            elif not ab.weapon_ok():
                world.float_text(hero.x, hero.y - 30, f"Can't {ab.name} with this weapon!", (255, 110, 110))
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
            if hero.channel is not None:
                # Cancel channel and stop auto-attack
                self.selected_target = None
                self._stop_channel()
        else:
            raise ValueError(f"unknown command: {cmd!r}")

    # --- casting ---
    def cast_ability(self, ab_key, ab, wx, wy, clicked_monster, ally=None):
        """Cast a skill for this player (human or hero AI). engine/casting.try_cast applies the same rules to every
        caster; this adds what only a player has: walking into range and firing then, auto-attacking, messages."""
        hero = self.hero
        spec = casting.SKILLS.get(ab.name)
        if spec is None:
            return None
        res = casting.try_cast(self.world, hero, ab, ally if spec.targeting == "ally" else clicked_monster)
        target, why = res.target, res.reason
        if res.ok:
            if spec.stops_attack:
                self.selected_target = None
            elif spec.targeting in ("enemy", "sweep", "dash"):
                self.selected_target = target            # keep auto-attacking what you just hit
            if spec.targeting != "self" or spec.stops_attack:
                self.move_path = []
            return res
        if why == "out of range" and spec.targeting != "ally" and not self.ai_enabled:   # (the AI steers itself)
            self.move_path = []
            if ab.power_type == "at_will":
                self.selected_target = target            # weapon attack: auto-attack walks into range
            elif spec.requires_stealth:
                self.ambush_target, self.selected_target = target, None   # sneak up, then Ambush (update_ambush)
            else:
                self.pending_cast = (ab_key, ab, target)  # walk into range, then fire (auto_attack)
                self.selected_target = target
        elif why in MESSAGES:
            self.world.float_text(hero.x, hero.y - 30, MESSAGES[why], (255, 150, 100))
        elif why[:1].isupper():                          # a gate's own message ("Must be stealthed!")
            self.world.float_text(hero.x, hero.y - 30, why, (255, 150, 100))
        return res

    def update(self, dt):
        """Frostbolt channel completion, path-following movement and the dash animation."""
        hero = self.hero
        gs = self.world.game_state
        self.potion_cooldown = max(0.0, self.potion_cooldown - dt)
        # A skill pressed during the global cooldown fires as soon as it ends (or is dropped after CAST_QUEUE_SECS)
        if self.queued_cast is not None:
            self.queued_cast_timer -= dt
            if self.queued_cast_timer <= 0:
                self.queued_cast = None
            elif hero.gcd <= 0:
                cmd, self.queued_cast = self.queued_cast, None
                self.handle(cmd)
        t = self.target
        if t is not None and (not t.alive or getattr(t, "stealthed", False)):
            self.target = None               # the target died or vanished
        if self.pickup_target is not None:
            self._try_pickup()
        # Stealth upkeep: 1 / 2 / 3 mana per second (Stealth level); it breaks when the mana runs out
        if hero.stealthed:
            stealth = next((a for a in hero.abilities.values() if a.toggle), None)
            upkeep = stealth_upkeep(stealth) * dt if stealth is not None else 0.0
            if hero.mana < upkeep:
                hero.mana = 0.0
                self._end_stealth("Out of mana!")
            else:
                hero.mana -= upkeep
        actions.update_actions(self.world, hero, dt)     # channel (Frostbolt, Holy Light) and dash (Charge)

        # WASD: walk in the held direction (slides along walls), like the path walk below
        if self.move_dir != (0, 0) and hero.dash is None and hero.can_move:
            dx, dy = self.move_dir
            norm = math.hypot(dx, dy)
            spd = hero.move_speed * dt
            self._step_toward(hero.x + dx / norm * 100, hero.y + dy / norm * 100, 100, spd)
            if dx:
                hero.facing_left = dx < 0

        # Smooth movement along path
        if self.move_path and hero.dash is None and hero.can_move:
            tx, ty = self.move_path[0]
            dx, dy = tx - hero.x, ty - hero.y
            dist = math.sqrt(dx*dx + dy*dy)
            if dist < 8:
                self.move_path.pop(0)
            else:
                spd = hero.move_speed * dt        # slows, stealth (50 / 60 / 70%)
                if not self._step_toward(tx, ty, dist, spd):   # never into a wall
                    self.move_path = []
                hero.facing_left = dx < 0

    def run_ai(self, dt):
        """Autopilot: let the hero AI act (potion, dash, abilities, movement) when enabled.
        Returns the AI's action dict (None when the autopilot is off or mid-dash)."""
        hero = self.hero
        gs = self.world.game_state
        # === HERO AI (when enabled) ===
        if not (self.ai_enabled and hero.dash is None):
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
            target_m = ai_action["dash"][2]
            ab = hero.abilities.get("R")
            if ab and ab.is_ready():
                res = self.cast_ability("R", ab, target_m.x, target_m.y, target_m)
                if res is not None and not res.ok and res.reason in ("no line of sight", "can't reach"):
                    # no line of sight / no walking path for the dash: walk toward it instead (cooldown kept)
                    self.move_path = self._path(hero.x, hero.y, target_m.x, target_m.y)

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
                # Walking to the target but no walking path exists (it stands somewhere we can't reach, e.g. a
                # walled-off patch of the map): remember it, so target picking skips it, and pick another
                target = self.hero_ai.target
                if (not self.move_path and target is not None and target.alive
                        and abs(tx - target.x) < 1 and abs(ty - target.y) < 1
                        and hero.distance_to(target) > TILE_SIZE):
                    hero._ai_unreachable.add(target.eid)
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
        busy = (self.hero.dash is not None or self.hero.channel is not None or self.move_path
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
        if self.selected_target and not self.ai_enabled and hero.channel is None and not hero.stealthed and hero.can_move:
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
