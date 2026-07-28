"""
Core entity system — Entity, Hero, Monster.
All game logic here is headless (no rendering dependency).
Stats derived from board game data scaled for real-time ARPG.
"""
import math
from enum import Enum, auto
from dataclasses import dataclass, field
from typing import Optional

# === SCALING CONSTANTS ===
# Board game HP 1-12 → ARPG HP (×50 for granularity)
HP_SCALE = 50
# Board game Speed 5-7 → ARPG speed in pixels/sec
SPEED_SCALE = 30  # speed 5 → 150 px/s, speed 6 → 180 px/s


class Condition(Enum):
    POISONED = auto()   # Take damage over time, save to remove
    DAZED = auto()      # Can only move OR attack, not both
    SLOWED = auto()     # Movement speed halved
    IMMOBILIZED = auto()  # Cannot move
    STUNNED = auto()    # Cannot move or act
    FROZEN = auto()     # Cannot move or act (ice effect)


@dataclass
class ActiveCondition:
    condition: Condition
    duration: float      # seconds remaining
    tick_damage: float = 0.0  # damage per second (for Poison)
    source: str = ""
    slow_factor: float = 0.5  # speed multiplier when SLOWED (0.25 = 25% speed)


@dataclass
class Ability:
    name: str
    cooldown: float       # seconds (how often you can use this skill)
    remaining: float = 0.0
    multiplier: float = 1.0   # damage = base_damage * multiplier + flat_bonus
    flat_bonus: float = 0.0   # flat added damage
    radius: float = 0.0  # AoE radius (0 = single target)
    range: float = 50.0  # max range in pixels
    effect: str = ""     # description of special effect
    power_type: str = "at_will"  # at_will, daily, utility
    color: tuple = (200, 200, 255)
    is_dash: bool = False       # hero dashes to target on use
    stun_duration: float = 0.0  # applies stun to target (seconds)

    def calc_damage(self, base_damage: float) -> float:
        """Calculate skill damage from hero's base weapon damage."""
        return base_damage * self.multiplier + self.flat_bonus

    def is_ready(self) -> bool:
        return self.remaining <= 0

    def use(self):
        self.remaining = self.cooldown

    def update(self, dt: float):
        self.remaining = max(0, self.remaining - dt)


@dataclass
class Projectile:
    """A missile that travels from source to target, dealing damage on arrival."""
    x: float
    y: float
    target: 'Entity' = None
    speed: float = 500.0       # pixels per second
    damage: float = 0.0
    color: tuple = (255, 220, 100)
    radius: float = 6.0        # visual radius
    alive: bool = True
    source: 'Entity' = None    # who fired it (for aggro)

    def update(self, dt: float):
        if not self.alive or not self.target or not self.target.alive:
            self.alive = False
            return None
        dx = self.target.x - self.x
        dy = self.target.y - self.y
        dist = math.sqrt(dx * dx + dy * dy)
        if dist < 15:
            # Hit! Returns (damage_dealt, target) so caller can handle aggro
            self.alive = False
            dmg = self.target.take_damage(self.damage)
            return (dmg, self.target)
        move = min(self.speed * dt, dist)
        self.x += (dx / dist) * move
        self.y += (dy / dist) * move
        return None


class Entity:
    """Base class for all game entities (heroes and monsters)."""

    def __init__(self, name: str, x: float, y: float,
                 hp: int, ac: int, speed: int,
                 attack_bonus: int = 0, attack_damage: int = 0,
                 attack_range: float = 50.0, attack_cooldown: float = 1.0):
        self.name = name
        self.x = x
        self.y = y

        # Stats (scaled from board game)
        self.max_hp = hp * HP_SCALE
        self.hp = self.max_hp
        self.ac = ac
        self.base_speed = speed * SPEED_SCALE  # pixels per second
        self.speed = self.base_speed

        # Weapon / Attack
        self.base_damage = attack_damage * HP_SCALE // 2  # weapon base damage
        self.weapon_speed = attack_cooldown  # seconds between swings
        self.attack_range = attack_range
        self.swing_timer = 0.0  # time until next swing is ready
        self.crit_chance = 0.05   # 5% base crit chance
        self.crit_multiplier = 2.0  # crits deal 2x damage
        self.last_crit = False  # whether last attack was a crit

        # State
        self.alive = True
        self.facing_left = False
        self.conditions: list[ActiveCondition] = []

        # Absorb shield (Wall spell etc.)
        self.absorb_shield = 0.0  # current shield HP remaining

        # Visual
        self.flash_timer = 0.0
        self.sprite = None

    @property
    def armor_reduction(self) -> float:
        """Convert AC to damage reduction percentage.
        AC 14 → ~25%, AC 16 → ~35%, AC 17 → ~40%
        """
        return (self.ac - 10) / (self.ac - 10 + 12)

    def distance_to(self, other: 'Entity') -> float:
        return math.sqrt((self.x - other.x)**2 + (self.y - other.y)**2)

    def move_toward(self, tx: float, ty: float, dt: float, collision_fn=None):
        """Move toward target position. collision_fn(x,y) returns True if blocked."""
        dx, dy = tx - self.x, ty - self.y
        dist = math.sqrt(dx*dx + dy*dy)
        if dist < 2:
            return

        # Check conditions
        if self.has_condition(Condition.IMMOBILIZED) or self.has_condition(Condition.STUNNED) or self.has_condition(Condition.FROZEN):
            return
        
        effective_speed = self.speed
        if self.has_condition(Condition.SLOWED):
            # Use slow_factor from condition if set, else default 50%
            slow_cond = next((c for c in self.conditions if c.condition == Condition.SLOWED), None)
            slow_factor = getattr(slow_cond, 'slow_factor', 0.5) if slow_cond else 0.5
            effective_speed *= slow_factor
        if getattr(self, 'stealthed', False):
            effective_speed *= 0.6

        move_dist = min(effective_speed * dt, dist)
        nx = self.x + (dx/dist) * move_dist
        ny = self.y + (dy/dist) * move_dist

        if collision_fn:
            if not collision_fn(nx, self.y):
                self.x = nx
            if not collision_fn(self.x, ny):
                self.y = ny
        else:
            self.x = nx
            self.y = ny

        self.facing_left = dx < 0

    def take_damage(self, raw_damage: float, ignore_armor: bool = False) -> float:
        """Apply damage after armor reduction. Shield absorbs first. Returns actual damage dealt."""
        if not self.alive:
            return 0

        if ignore_armor:
            actual = raw_damage
        else:
            actual = raw_damage * (1.0 - self.armor_reduction)

        # Absorb shield absorbs damage before HP
        if self.absorb_shield > 0:
            if actual <= self.absorb_shield:
                self.absorb_shield -= actual
                self.flash_timer = 0.12
                return actual  # All absorbed
            else:
                actual -= self.absorb_shield
                self.absorb_shield = 0

        self.hp -= actual
        self.flash_timer = 0.12

        if self.hp <= 0:
            self.hp = 0
            self.alive = False

        return actual

    def heal(self, amount: float) -> float:
        """Heal HP. Returns actual amount healed."""
        if not self.alive:
            return 0
        actual = min(amount, self.max_hp - self.hp)
        self.hp += actual
        return actual

    def has_condition(self, condition: Condition) -> bool:
        return any(c.condition == condition for c in self.conditions)

    def apply_condition(self, condition: Condition, duration: float,
                        tick_damage: float = 0.0, source: str = "",
                        slow_factor: float = 0.5):
        """Apply a condition. Replaces existing condition of same type."""
        # Remove existing
        self.conditions = [c for c in self.conditions if c.condition != condition]
        self.conditions.append(ActiveCondition(condition, duration, tick_damage, source, slow_factor))

    def update_conditions(self, dt: float):
        """Update condition timers, apply tick damage (poison)."""
        for cond in self.conditions:
            cond.duration -= dt
            if cond.tick_damage > 0:
                self.take_damage(cond.tick_damage * dt, ignore_armor=True)
        # Remove expired
        self.conditions = [c for c in self.conditions if c.duration > 0]

    def update(self, dt: float):
        """Per-frame update."""
        self.flash_timer = max(0, self.flash_timer - dt)
        self.swing_timer = max(0, self.swing_timer - dt)
        self.update_conditions(dt)

    def can_swing(self) -> bool:
        """Check if entity can swing (weapon timer ready)."""
        if not self.alive:
            return False
        if self.has_condition(Condition.STUNNED):
            return False
        if self.has_condition(Condition.FROZEN):
            return False
        if self.has_condition(Condition.IMMOBILIZED):
            return False
        return self.swing_timer <= 0

    def try_basic_attack(self, target: 'Entity') -> Optional[float]:
        """Swing weapon at target. Returns damage dealt or None."""
        if not self.can_swing():
            return None
        if self.distance_to(target) > self.attack_range:
            return None

        self.swing_timer = self.weapon_speed
        import random
        damage = self.base_damage
        self.last_crit = random.random() < self.crit_chance
        if self.last_crit:
            damage *= self.crit_multiplier
        return target.take_damage(damage)


class Hero(Entity):
    """Player-controlled hero with abilities, XP, gold, equipment."""

    def __init__(self, name: str, race: str, class_name: str,
                 x: float, y: float,
                 hp: int, ac: int, speed: int, surge_value: int,
                 special_ability: str = ""):
        super().__init__(name, x, y, hp, ac, speed)
        self.race = race
        self.class_name = class_name
        self.surge_value = surge_value * HP_SCALE
        self.special_ability = special_ability

        # Abilities
        self.abilities: dict[str, Ability] = {}
        self.gcd = 0.0  # Global cooldown (disabled)
        self.GCD_DURATION = 0.0

        # Progression
        self.xp = 0
        self.gold = 0
        self.kills = 0
        self.level = 1

        # Active buffs (name -> {remaining: float, data: dict})
        self.buffs: dict[str, dict] = {}

        # Stealth state (Rogue)
        self.stealthed: bool = False

        # Equipment (slot -> item)
        self.equipment: dict[str, dict] = {}

    def add_ability(self, key: str, ability: Ability):
        self.abilities[key] = ability

    def update(self, dt: float):
        super().update(dt)
        self.gcd = max(0, self.gcd - dt)
        for ab in self.abilities.values():
            ab.update(dt)
        # Update buffs
        for k, v in list(self.buffs.items()):
            v["remaining"] -= dt
            # HoT tick processing (heals each frame proportionally)
            if "hot_per_sec" in v and v["remaining"] > -dt:
                heal_tick = v["hot_per_sec"] * dt
                self.heal(heal_tick)
        # Remove expired buffs after decrement
        expired = [k for k, v in self.buffs.items() if v["remaining"] <= 0]
        for k in expired:
            del self.buffs[k]

    def use_ability(self, key: str, targets: list['Entity'],
                    target_pos: tuple = None) -> list[tuple[str, float]]:
        """Use an ability (consumes a swing). Returns list of (target_name, damage_dealt)."""
        ab = self.abilities.get(key)
        if not ab or not ab.is_ready():
            return []
        if self.has_condition(Condition.STUNNED):
            return []
        if self.swing_timer > 0:
            return []  # Can't use skill mid-swing

        hits = []
        ab.use()
        self.swing_timer = self.weapon_speed  # Skill consumes a swing
        skill_damage = ab.calc_damage(self.base_damage)

        if ab.radius > 0:
            # AoE - check all targets in radius
            center_x = target_pos[0] if target_pos else self.x
            center_y = target_pos[1] if target_pos else self.y

            for t in targets:
                if not t.alive:
                    continue
                dx = t.x - center_x
                dy = t.y - center_y
                if math.sqrt(dx*dx + dy*dy) <= ab.radius:
                    dmg = t.take_damage(skill_damage)
                    hits.append((t.name, dmg))
        else:
            # Single target - closest in range
            in_range = [t for t in targets if t.alive and self.distance_to(t) <= ab.range]
            if in_range:
                target = min(in_range, key=lambda t: self.distance_to(t))
                dmg = target.take_damage(skill_damage)
                hits.append((target.name, dmg))

        return hits


class Monster(Entity):
    """AI-controlled monster with tactics from board game."""

    def __init__(self, name: str, monster_type: str,
                 x: float, y: float,
                 hp: int, ac: int, speed: int,
                 attack_bonus: int, attack_damage: int,
                 attack_range: float = 50.0,
                 experience: int = 1,
                 is_boss: bool = False):
        super().__init__(name, x, y, hp, ac, speed,
                         attack_bonus, attack_damage, attack_range)
        self.monster_type = monster_type
        self.experience = experience
        self.is_boss = is_boss

        # Tactics (behavior tree steps)
        self.tactics: list[dict] = []

        # Conditions this monster applies on hit
        self.on_hit_condition: Optional[tuple[Condition, float]] = None
        # e.g. (Condition.POISONED, 4.0) = apply poison for 4 seconds

        # Ranged attack (if any)
        self.ranged_attack_bonus: int = 0
        self.ranged_attack_damage: int = 0
        self.ranged_attack_range: float = 0  # 0 = no ranged attack

        # Boss scaling
        if is_boss:
            self.weapon_speed *= 0.8  # bosses attack faster


class GameState:
    """Central game state container."""

    def __init__(self):
        self.heroes: list[Hero] = []
        self.monsters: list[Monster] = []
        self.life_tokens: int = 2  # shared healing surges
        self.game_time: float = 0.0
        self.adventure_complete: bool = False
        self.adventure_failed: bool = False
        self.objective_text: str = ""
        self.wave: int = 0

    @property
    def alive_monsters(self) -> list[Monster]:
        return [m for m in self.monsters if m.alive]

    @property
    def alive_heroes(self) -> list[Hero]:
        return [h for h in self.heroes if h.alive]

    def update(self, dt: float):
        self.game_time += dt
        for h in self.heroes:
            h.update(dt)
        for m in self.monsters:
            m.update(dt)

    def check_hero_death(self, hero: Hero) -> bool:
        """Handle hero at 0 HP. Returns True if game over."""
        if hero.alive:
            return False
        if self.life_tokens > 0:
            self.life_tokens -= 1
            hero.hp = hero.surge_value
            hero.alive = True
            return False
        else:
            self.adventure_failed = True
            return True
