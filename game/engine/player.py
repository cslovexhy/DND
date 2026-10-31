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
from game.engine.ai import aggro_monster, call_for_help, AggroState
from game.engine.entities import Condition, Projectile
from game.engine.commands import (MoveTo, SelectTarget, Cast, InteractNpc, AmbushTarget, UsePotion,
                                  ToggleAutopilot, ToggleCompanion, CancelChannel, BindLeftSkill, HoldPosition)
from game.engine.events import Ring, BindRightSkill, GOLD
from game.engine.hero_ai import create_hero_ai
from game.content.heroes import HERO_CLASSES
from game.engine.pathfinding import astar


SUPPORT_RANGE = 300   # px: how far away an ally can be for Wall / Renew / Holy Light


class PlayerState:
    def __init__(self, world, hero, ai_enabled=False, potions=3, quests=None, name=None):
        self.world = world
        self.hero = hero
        self.player_id = 0               # set by World.add_player
        self.name = name or hero.name
        self.quests = quests if quests is not None else world.quests   # this player's QuestLog for the map
        # One AI companion per class other than this player's own (summoned with ToggleCompanion)
        self.available_companions = [c for c in HERO_CLASSES if c["class"] != hero.class_name]
        self.hero_ai = create_hero_ai(hero)   # autopilot brain (HeroAI)
        self.hero_ai.set_nav_dungeon(world.dungeon)
        self.hero_ai.clock = lambda: world.game_state.game_time
        if hasattr(self.hero_ai, "allies"):
            self.hero_ai.allies = world.game_state.heroes   # support AI (Cleric) can heal the whole party
        self.ai_enabled = ai_enabled     # autopilot on/off (TAB; on in --auto/--headless)
        # Movement / targeting
        self.move_path = []
        self.selected_target = None
        self.potions = potions
        # Client choices that affect auto-attack (sent as BindLeftSkill / HoldPosition commands)
        self.left_ab_key = next(iter(hero.abilities), None)
        self.hold_position = False
        # Queued ability cast (walk to range then fire): (ab_key, ab, target_monster) or None
        self.pending_cast = None
        # Dash animation state (Charge)
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

    # --- commands (the client's only way to act; see engine/commands.py) ---
    def _live_monster(self, eid):
        m = self.world.entity(eid) if eid is not None else None
        return m if (m is not None and m.alive and m in self.world.game_state.monsters) else None

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
        """Apply one validated player command."""
        world = self.world
        hero = self.hero
        gs = world.game_state
        if isinstance(cmd, MoveTo):
            # Click ground = move (cancel channel)
            if self.frostbolt_channeling:
                self._stop_channel()
            self.move_path = astar(world.dungeon, hero.x, hero.y, cmd.x, cmd.y)
            self.selected_target = None
            self.ambush_target = None
            self.pending_cast = None
        elif isinstance(cmd, SelectTarget):
            m = self._live_monster(cmd.target_id)
            if m is None:
                return
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
            if ab.is_ready():
                self.cast_ability(cmd.ab_key, ab, cmd.x, cmd.y, self._live_monster(cmd.target_id),
                                  ally=self._friendly(cmd.ally_id))
            elif cmd.fallback_move:
                # Skill on cooldown — just move instead
                self.move_path = astar(world.dungeon, hero.x, hero.y, cmd.x, cmd.y)
                self.selected_target = None
        elif isinstance(cmd, InteractNpc):
            npc = world.entity(cmd.npc_id)
            if npc is None or npc not in world.npcs:
                return
            if npc.is_in_range(hero.x, hero.y):
                world.interact_with_npc(npc, self)
            else:
                # Walk to NPC
                self.move_path = astar(world.dungeon, hero.x, hero.y, npc.x, npc.y)
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
            if self.potions > 0 and hero.hp < hero.max_hp:
                self.potions -= 1
                heal = hero.heal(150)
                world.float_text(hero.x, hero.y - 30, f"+{heal:.0f}", (100, 255, 100))
        elif isinstance(cmd, ToggleAutopilot):
            self.ai_enabled = not self.ai_enabled
        elif isinstance(cmd, ToggleCompanion):
            comp_info = next((c for c in self.available_companions if c["class"] == cmd.class_name), None)
            if comp_info is None:
                return
            # Already summoned — dismiss; otherwise summon
            existing = [(i, c) for i, (c, _) in enumerate(world.companions)
                        if c.class_name == comp_info["class"] and getattr(c, "owner", None) is self]
            if existing:
                idx, comp = existing[0]
                world.companions.pop(idx)
                gs.heroes.remove(comp)
                world.unregister(comp)
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
                self.world.events.append(BindRightSkill("R", self.player_id))
            dmg_amount = ab.calc_damage(hero.base_damage)
            # Crit roll
            hero.last_crit = random.random() < hero.crit_chance
            if hero.last_crit:
                dmg_amount *= hero.crit_multiplier
            dmg = clicked_monster.take_damage(dmg_amount)
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
            self.world.events.append(BindRightSkill("E", self.player_id))
            # Drop aggro from all monsters targeting hero (except bosses)
            for m in gs.alive_monsters:
                if hasattr(m, 'aggro_target') and m.aggro_target == hero and not m.is_boss:
                    m.aggro_state = AggroState.RESETTING
                    m.aggro_target = None
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
            self.world.events.append(BindRightSkill("R", self.player_id))
            # Damage: 3x weapon + 20% target max HP
            dmg_amount = ab.calc_damage(hero.base_damage) + clicked_monster.max_hp * 0.2
            dmg = clicked_monster.take_damage(dmg_amount)
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
                    dmg = m.take_damage(dmg_amount)
                    m.apply_condition(Condition.FROZEN, 4.0)
                    self.world.float_text(m.x, m.y - 20, f"{dmg:.0f}", (180, 220, 255))
                    self.world.float_text(m.x, m.y - 35, "FROZEN", (150, 220, 255))
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
            shield_amount = hero.surge_value  # Same as potion amount (200)
            target.absorb_shield = shield_amount
            target.buffs["Wall"] = {"remaining": 15.0}
            self.world.float_text(target.x, target.y - 30, f"Wall +{shield_amount:.0f}!", (100, 200, 255))
            hero.gcd = hero.GCD_DURATION
            self.move_path = []
            return

        # === Quinn special: Renew (HoT on self or a chosen ally) ===
        if ab.name == "Renew":
            target = self._support_target(ally)
            if target is None:
                return
            ab.use()
            hot_total = hero.surge_value * 0.5  # 50% of potion amount (100)
            hot_duration = 8.0
            target.buffs["Renew"] = {"remaining": hot_duration, "hot_per_sec": hot_total / hot_duration}
            self.world.float_text(target.x, target.y - 30, "Renew!", (100, 255, 150))
            hero.gcd = hero.GCD_DURATION
            self.move_path = []
            return

        # === Quinn special: Righteous Seal (self-buff, no target needed) ===
        if ab.name == "Righteous Seal":
            ab.use()
            hero.buffs["Righteous Seal"] = {"remaining": 10.0, "bonus": 0.25}
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
            hero.buffs["Holy Light Casting"] = {"remaining": 2.0, "heal": 150,
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
            bonus = 1.0 + (hero.buffs.get("Righteous Seal", {}).get("bonus", 0))
            skill_dmg = ab.calc_damage(hero.base_damage) * bonus
            dmg = clicked_monster.take_damage(skill_dmg)
            color = (255, 230, 100) if bonus > 1.0 else (255, 255, 255)
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
                    # 50% damage reduction for 10s
                    m.buffs["Demoralized"] = {"remaining": 10.0, "damage_mult": 0.5}
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
                ab.use()  # Put on cooldown
                dx = clicked_monster.x - hero.x
                dy = clicked_monster.y - hero.y
                d = math.sqrt(dx*dx + dy*dy)
                if d > 0:
                    self.dash_target_x = clicked_monster.x - (dx/d) * 50
                    self.dash_target_y = clicked_monster.y - (dy/d) * 50
                    self.dash_active = True
                    self.dash_stun_target = clicked_monster
                    self.dash_stun_duration = ab.stun_duration
                    # Store damage to apply on arrival
                    self.dash_damage = ab.calc_damage(hero.base_damage)
                call_for_help(clicked_monster, gs.monsters, hero)
            else:
                # Non-dash single target: deal damage immediately
                hits = hero.use_ability(ab_key, [clicked_monster])
                for name, dmg in hits:
                    self.world.float_text(clicked_monster.x, clicked_monster.y-20, f"{dmg:.0f}", (255, 255, 255))
                if ab.stun_duration > 0 and clicked_monster.alive:
                    clicked_monster.apply_condition(Condition.STUNNED, ab.stun_duration)
                    self.world.float_text(clicked_monster.x, clicked_monster.y-35, "STUNNED", (255,255,100))
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
        # Frostbolt channel completion
        if self.frostbolt_channeling:
            self.frostbolt_channel_timer -= dt
            if self.frostbolt_channel_timer <= 0:
                self.frostbolt_channeling = False
                # Fire projectile if target still alive (range doesn't matter — bolt chases)
                if self.frostbolt_target and self.frostbolt_target.alive:
                    proj_damage = hero.base_damage  # 100% weapon
                    proj = Projectile(x=hero.x, y=hero.y, target=self.frostbolt_target,
                                      speed=500.0, damage=proj_damage,
                                      color=(150, 200, 255), source=hero)
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
                hero.x += (dx/dist) * min(spd, dist)
                hero.y += (dy/dist) * min(spd, dist)
                hero.facing_left = dx < 0

        # Dash animation (Charge skill)
        if self.dash_active:
            dx = self.dash_target_x - hero.x
            dy = self.dash_target_y - hero.y
            dist = math.sqrt(dx*dx + dy*dy)
            if dist < 10:
                # Arrived — deal damage + apply stun
                self.dash_active = False
                hero.x = self.dash_target_x
                hero.y = self.dash_target_y
                if self.dash_stun_target and self.dash_stun_target.alive:
                    dmg = self.dash_stun_target.take_damage(self.dash_damage)
                    self.world.float_text(self.dash_stun_target.x, self.dash_stun_target.y-20, f"{dmg:.0f}", (255, 200, 50))
                    if self.dash_stun_duration > 0 and self.dash_stun_target.alive:
                        self.dash_stun_target.apply_condition(Condition.STUNNED, self.dash_stun_duration)
                        self.world.float_text(self.dash_stun_target.x, self.dash_stun_target.y-35, "STUNNED", (255,255,100))
                self.dash_stun_target = None
                self.dash_damage = 0
            else:
                spd = self.dash_speed * dt
                hero.x += (dx/dist) * min(spd, dist)
                hero.y += (dy/dist) * min(spd, dist)
                hero.facing_left = dx < 0

    def run_ai(self, dt):
        """Autopilot: let the hero AI act (potion, dash, abilities, movement) when enabled."""
        hero = self.hero
        gs = self.world.game_state
        # === HERO AI (when enabled) ===
        if self.ai_enabled and not self.dash_active:
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
                for comp, _ in self.world.companions:
                    if comp.alive:
                        print(f"  [COMP] {comp.name} pos=({comp.x:.0f},{comp.y:.0f}) hp={comp.hp:.0f}/{comp.max_hp} dist_to_hero={hero.distance_to(comp):.0f}", flush=True)

            if ai_action["use_potion"] and self.potions > 0 and hero.hp < hero.max_hp:
                self.potions -= 1
                heal = hero.heal(150)
                self.world.float_text(hero.x, hero.y-30, f"+{heal:.0f}", (100,255,100))

            if ai_action["dash"]:
                # Charge ability
                tx, ty, target_m, dmg, stun = ai_action["dash"]
                ab = hero.abilities.get("R")
                if ab and ab.is_ready():
                    if not self.world.check_los(hero.x, hero.y, target_m.x, target_m.y):
                        # No LOS — pathfind toward target
                        self.move_path = astar(self.world.dungeon, hero.x, hero.y, target_m.x, target_m.y)
                    else:
                        ab.use()
                        self.dash_target_x, self.dash_target_y = tx, ty
                        self.dash_active = True
                        self.dash_stun_target = target_m
                        self.dash_stun_duration = stun
                        self.dash_damage = dmg
                    call_for_help(target_m, gs.monsters, hero)

            elif ai_action["use_ability"]:
                ab_key = ai_action["use_ability"]
                ab = hero.abilities.get(ab_key)
                if ab and ab.is_ready():
                    target_m = ai_action.get("ability_target_monster")
                    # Check LOS before casting — if blocked, pathfind toward target to get LOS
                    if target_m and not self.world.check_los(hero.x, hero.y, target_m.x, target_m.y):
                        self.move_path = astar(self.world.dungeon, hero.x, hero.y, target_m.x, target_m.y)
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
                    self.move_path = astar(self.world.dungeon, hero.x, hero.y, tx, ty)
                    hero._ai_repath_timer = 0.5
                    # If path is empty and target is nearby, it's unreachable
                    if not self.move_path and self.hero_ai.target and self.hero_ai.target.alive:
                        dist_to_target = hero.distance_to(self.hero_ai.target)
                        if dist_to_target < 300:
                            hero._ai_unreachable.add(id(self.hero_ai.target))
                            self.hero_ai.target = None  # Force retarget next frame

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
                        self.move_path = astar(self.world.dungeon, hero.x, hero.y, self.ambush_target.x, self.ambush_target.y)

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
                        self.cast_ability(ab_key, ab, self.selected_target.x, self.selected_target.y, self.selected_target)
                elif not hold_position:
                    # Out of range and shift NOT held — pathfind toward target
                    if not self.move_path:
                        self.move_path = astar(self.world.dungeon, hero.x, hero.y, self.selected_target.x, self.selected_target.y)
