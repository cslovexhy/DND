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
# Poison applied by monster hits: damage per second (scaled by the map's pp, see World._apply_pp)
POISON_DPS = 10.0
# Character scale: 1.0 = same size as map tile, 0.5 = half size. Gameplay constant (not just art):
# movement speed scales with it so the map feels bigger. The client sizes sprites from it too.
CHAR_SCALE = 0.5
# Board game Speed 5-7 → ARPG speed in pixels/sec: 30 px/s per point at CHAR_SCALE 1.0
SPEED_SCALE = int(30 * CHAR_SCALE)  # speed 5 → 75 px/s, speed 6 → 90 px/s


class Condition(Enum):
    POISONED = auto()   # Take damage over time, save to remove
    DAZED = auto()      # Can only move OR attack, not both
    SLOWED = auto()     # Movement speed halved
    IMMOBILIZED = auto()  # Cannot move
    STUNNED = auto()    # Cannot move or act
    FROZEN = auto()     # Cannot move or act (ice effect)


# One immunity flag per condition: Entity.<flag> = True makes apply_condition ignore that condition.
CONDITION_IMMUNITY_FLAG = {
    Condition.POISONED: "immune_poison",
    Condition.DAZED: "immune_daze",
    Condition.SLOWED: "immune_slow",
    Condition.IMMOBILIZED: "immune_immobilize",
    Condition.STUNNED: "immune_stun",
    Condition.FROZEN: "immune_freeze",
}


@dataclass
class ActiveCondition:
    condition: Condition
    duration: float      # seconds remaining
    tick_damage: float = 0.0  # damage per second (for Poison)
    source: str = ""
    slow_factor: float = 0.5  # speed multiplier when SLOWED (0.25 = 25% speed)


# Skill level -> share of the level-3 (full) damage / heal / effect strength
LEVEL_POWER = {1: 0.33, 2: 0.67, 3: 1.0}


@dataclass
class Ability:
    name: str
    cooldown: float       # seconds (how often you can use this skill)
    remaining: float = 0.0
    multiplier: float = 1.0   # "a": damage = a x base_damage + b (at the CURRENT skill level)
    flat_bonus: float = 0.0   # "b": flat added damage (current skill level)
    radius: float = 0.0  # AoE radius (0 = single target)
    range: float = 50.0  # max range in pixels
    effect: str = ""     # description of special effect (written for the full, level-3 skill)
    power_type: str = "at_will"  # at_will, daily, utility
    color: tuple = (200, 200, 255)
    is_dash: bool = False       # hero dashes to target on use
    stun_duration: float = 0.0  # applies stun to target (seconds)
    # Skill levels (see content/skill_tree.py). Damage is a x base + b, with a / b per skill level from a_levels /
    # b_levels (skill level 1, 2, 3); without them `multiplier` / `flat_bonus` are used at every level. Level 3 is the
    # default, so abilities that never call set_level (monsters, tests) use their level-3 values.
    level: int = 3
    max_level: int = 3
    range_levels: tuple = ()    # optional range per skill level (e.g. Wizard bolts 200 / 230 / 260)
    a_levels: tuple = ()        # optional "a" per skill level
    b_levels: tuple = ()        # optional "b" per skill level
    # Threat: hate a hit adds = damage dealt x threat_mult (never changes the damage itself)
    threat_mult: float = 1.0
    max_targets_levels: tuple = ()   # optional cap on targets hit per skill level (Cleave 2 / 3 / 4)
    heroic: bool = False        # an attack that the Heroic Strike buff empowers (Fighter Strike, Cleave)
    # What the skill is aimed at: "enemy" (casting it at an enemy also starts auto-attacking it), "ally" (a friend or
    # yourself) or "self" (fires on the spot: buffs, shouts, novas)
    target_kind: str = "enemy"

    def __post_init__(self):
        self.full_multiplier = self.multiplier
        self.full_flat_bonus = self.flat_bonus
        self.set_level(self.level)

    @property
    def power(self) -> float:
        """Strength of a heal / shield at the current skill level: 33% / 67% / 100% of its level-3 amount.
        (Damage uses a_levels / b_levels instead.) Skills with a single level always run at full strength."""
        return LEVEL_POWER[self.level] if self.max_level == 3 else 1.0

    def set_level(self, level: int):
        """Use the a / b (and range, if it has per-level ranges) of the given skill level."""
        self.level = max(1, min(self.max_level, level))
        i = self.level - 1
        self.multiplier = self.a_levels[min(i, len(self.a_levels) - 1)] if self.a_levels else self.full_multiplier
        self.flat_bonus = self.b_levels[min(i, len(self.b_levels) - 1)] if self.b_levels else self.full_flat_bonus
        if self.range_levels:
            self.range = self.range_levels[min(self.level, len(self.range_levels)) - 1]

    @property
    def max_targets(self):
        """Most targets this skill hits at its level (None = no cap)."""
        if not self.max_targets_levels:
            return None
        return self.max_targets_levels[min(self.level, len(self.max_targets_levels)) - 1]

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
    threat: float = 1.0        # threat modifier of the skill that fired it

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
            dmg = self.target.take_damage(self.damage, source=self.source, threat=self.threat)
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
        self.eid = None   # stable id assigned by World.register() (used by commands / network)
        self.x = x
        self.y = y

        # Level
        self.level = 1

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

        # Abilities & cooldowns
        self.abilities: dict[str, 'Ability'] = {}
        self.gcd = 0.0  # Global cooldown
        self.GCD_DURATION = 0.5

        # Stealth
        self.stealthed: bool = False

        # State
        self.alive = True
        self.facing_left = False
        self.conditions: list[ActiveCondition] = []
        # Condition immunities (all off by default; see CONDITION_IMMUNITY_FLAG). Bosses turn on slow, freeze, stun and immobilize.
        self.immune_poison = False
        self.immune_daze = False
        self.immune_slow = False
        self.immune_immobilize = False
        self.immune_stun = False
        self.immune_freeze = False

        # Health regeneration
        self.in_combat = False  # set externally by game loop
        self.regen_rate_combat = 0.005     # 0.5% of max HP per second in combat
        self.regen_rate_ooc = 0.02         # 2% of max HP per second out of combat

        # Active buffs/debuffs (name -> {remaining: float, ...data})
        self.buffs: dict[str, dict] = {}

        # Absorb shield (Wall spell etc.)
        self.absorb_shield = 0.0  # current shield HP remaining
        # (healer, hp healed) from heal-over-time ticks this frame; World drains it into the mobs' hate tables
        self.heal_credits: list = []

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
            can_x = not collision_fn(nx, self.y)
            can_y = not collision_fn(self.x, ny)
            if can_x and can_y:
                # Both axes free — check diagonal too
                if not collision_fn(nx, ny):
                    self.x = nx
                    self.y = ny
                else:
                    # Diagonal blocked but axes individually free — pick dominant axis
                    if abs(dx) >= abs(dy):
                        self.x = nx
                    else:
                        self.y = ny
            elif can_x:
                # Slide along wall horizontally at full speed
                self.x += (1 if dx > 0 else -1) * min(effective_speed * dt, abs(dx))
            elif can_y:
                # Slide along wall vertically at full speed
                self.y += (1 if dy > 0 else -1) * min(effective_speed * dt, abs(dy))
            # else: completely blocked, don't move
        else:
            self.x = nx
            self.y = ny

        self.facing_left = dx < 0

    def take_damage(self, raw_damage: float, ignore_armor: bool = False, source: 'Entity' = None,
                    threat: float = 1.0) -> float:
        """Apply damage after armor reduction. Shield absorbs first. Returns actual damage dealt.
        `source` is who dealt it and `threat` the skill's threat modifier (only Monster uses them: hate table)."""
        if not self.alive:
            return 0

        self.was_hit = True  # flag for stealth-reveal logic (any incoming damage)

        if ignore_armor:
            actual = raw_damage
        else:
            actual = raw_damage * (1.0 - self.armor_reduction)

        # Absorb shield absorbs damage before HP
        if self.absorb_shield > 0:
            if actual <= self.absorb_shield:
                self.absorb_shield -= actual
                self.flash_timer = 0.06
                return actual  # All absorbed
            else:
                actual -= self.absorb_shield
                self.absorb_shield = 0

        self.hp -= actual
        self.flash_timer = 0.06

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
        """Apply a condition. Replaces existing condition of same type.
        Returns False (and does nothing) if the entity is immune to it."""
        if getattr(self, CONDITION_IMMUNITY_FLAG[condition]):
            return False
        # Remove existing
        self.conditions = [c for c in self.conditions if c.condition != condition]
        self.conditions.append(ActiveCondition(condition, duration, tick_damage, source, slow_factor))
        return True

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
        self.gcd = max(0, self.gcd - dt)
        self.update_conditions(dt)
        # Ability cooldowns
        for ab in self.abilities.values():
            ab.update(dt)
        # Health regeneration
        if self.alive and self.hp < self.max_hp:
            rate = self.regen_rate_combat if self.in_combat else self.regen_rate_ooc
            self.hp = min(self.max_hp, self.hp + self.max_hp * rate * dt)
        # Tick buff/debuff timers
        for k, v in list(self.buffs.items()):
            v["remaining"] -= dt
            # HoT tick processing (heals each frame proportionally)
            if "hot_per_sec" in v and v["remaining"] > -dt:
                healed = self.heal(v["hot_per_sec"] * dt)
                if v.get("source") is not None:
                    self.heal_credits.append((v["source"], healed))
        expired = [k for k, v in self.buffs.items() if v["remaining"] <= 0]
        for k in expired:
            del self.buffs[k]

    def add_ability(self, key: str, ability: 'Ability'):
        """Add an ability to this entity."""
        self.abilities[key] = ability

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

    def hit_damage(self) -> float:
        """Damage of one basic attack before buffs/crits (Monster overrides it with a per-hit roll)."""
        return self.base_damage

    def try_basic_attack(self, target: 'Entity') -> Optional[float]:
        """Swing weapon at target. Returns damage dealt or None."""
        if not self.can_swing():
            return None
        if self.distance_to(target) > self.attack_range:
            return None

        self.swing_timer = self.weapon_speed
        import random
        damage = self.hit_damage()
        # Demoralized debuff reduces damage output
        if "Demoralized" in getattr(self, 'buffs', {}):
            damage *= self.buffs["Demoralized"].get("damage_mult", 1.0)
        self.last_crit = random.random() < self.crit_chance
        if self.last_crit:
            damage *= self.crit_multiplier
        return target.take_damage(damage, source=self)


class Hero(Entity):
    """Player-controlled hero with abilities, XP, gold, equipment."""

    def __init__(self, name: str, class_name: str,
                 x: float, y: float,
                 hp: int, ac: int, speed: int, surge_value: int,
                 special_ability: str = ""):
        super().__init__(name, x, y, hp, ac, speed)
        self.class_name = class_name
        self.surge_value = surge_value * HP_SCALE
        self.special_ability = special_ability

        # Progression
        self.xp = 0
        self.gold = 0
        self.kills = 0
        self.deaths = 0   # times this hero fell and respawned (no game over)

        # Equipment (slot -> item)
        self.equipment: dict[str, dict] = {}

        # Skill levels (content/skill_tree.py): None = every skill at full strength (no level gating)
        self.skill_levels = None
        self.all_abilities = None   # every ability of the class, locked ones included

        # Max HP before the food buff (set by progression.apply_level_growth); max_hp = base x (1 + food bonus)
        self.base_max_hp = self.max_hp

    # --- food buff ("Well Fed", content/items.py): +damage% and/or +max HP% ---
    def _food_buff(self):
        return self.buffs.get("Well Fed", {})

    @property
    def damage_bonus(self) -> float:
        """Multiplier on all damage this hero deals (1.0 without a food buff)."""
        return 1.0 + self._food_buff().get("damage_pct", 0.0)

    def refresh_max_hp(self):
        """Recompute max_hp from base_max_hp and the food buff. Gaining max HP also adds it to current HP; losing it
        only caps current HP."""
        new_max = int(round(self.base_max_hp * (1.0 + self._food_buff().get("max_hp_pct", 0.0))))
        gained = new_max - self.max_hp
        self.max_hp = new_max
        self.hp = min(new_max, self.hp + max(0, gained))

    def update(self, dt: float):
        fed = "Well Fed" in self.buffs
        super().update(dt)
        if fed and "Well Fed" not in self.buffs:
            self.refresh_max_hp()        # the food buff ran out

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
        # Heroic Strike: the next empowered attack hits its (first) target harder and with more threat
        hs = self.buffs.pop("Heroic Strike", None) if ab.heroic else None

        def hit(t, first):
            bonus = hs["bonus"] if (hs and first) else 0.0
            threat = ab.threat_mult * (hs["threat"] if (hs and first) else 1.0)
            return t.take_damage(skill_damage + bonus, source=self, threat=threat)

        if ab.max_targets:
            # Capped melee sweep (Cleave): the first target, then the nearest others, all within `radius` of us
            first = targets[0] if targets else None
            near = [t for t in targets if t.alive and self.distance_to(t) <= ab.radius]
            near.sort(key=lambda t: (t is not first, self.distance_to(t)))
            for i, t in enumerate(near[:ab.max_targets]):
                hits.append((t.name, hit(t, i == 0)))
        elif ab.radius > 0:
            # AoE - check all targets in radius
            center_x = target_pos[0] if target_pos else self.x
            center_y = target_pos[1] if target_pos else self.y

            for t in targets:
                if not t.alive:
                    continue
                dx = t.x - center_x
                dy = t.y - center_y
                if math.sqrt(dx*dx + dy*dy) <= ab.radius:
                    hits.append((t.name, hit(t, not hits)))
        else:
            # Single target - closest in range
            in_range = [t for t in targets if t.alive and self.distance_to(t) <= ab.range]
            if in_range:
                target = min(in_range, key=lambda t: self.distance_to(t))
                hits.append((target.name, hit(target, True)))

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
            self.immune_slow = True
            self.immune_freeze = True
            self.immune_stun = True          # Charge's stun
            self.immune_immobilize = True

        # Hate table: {hero: hate}. 1 hate per damage dealt to this monster, 0.8 per HP healed / shielded on a hero
        # already in the table (see ai.credit_heal_hate). Bosses chase the top entry (ai.boss_pick_target).
        self.hate: dict = {}

        # Special skills from the monster table (see engine/skills.py): name -> config, which HP triggers have
        # already fired this life, and the skills waiting to be cast
        self.skills: dict = {}
        self.skills_fired: set = set()
        self.enraged = False   # Enrage skill fired: attack damage already multiplied
        self.skill_queue: list = []
        self.say = ""      # a message shown over its head (e.g. "Ashardalon took a deep breath..."), "" = none

    def hit_damage(self) -> float:
        """Damage of one attack before modifiers: levelled monsters (map monster_levels) roll
        round(base x 0.9..1.1) per hit; others hit for exactly base_damage."""
        if getattr(self, "leveled", False):
            import random
            from game.content.monsters import DAMAGE_ROLL
            return round(random.uniform(*DAMAGE_ROLL) * self.base_damage)
        return self.base_damage

    def add_hate(self, hero, amount: float = 0.0):
        """Add `amount` hate for `hero` (0 just puts the hero on the table)."""
        self.hate[hero] = self.hate.get(hero, 0.0) + amount

    def top_hate_target(self, candidates):
        """The candidate with the most hate, or None if none of them is on the table."""
        listed = [c for c in candidates if c in self.hate]
        return max(listed, key=lambda c: self.hate[c], default=None)

    def take_damage(self, raw_damage: float, ignore_armor: bool = False, source: 'Entity' = None,
                    threat: float = 1.0) -> float:
        bonus = getattr(source, "damage_bonus", 1.0)     # a hero's food buff
        dealt = super().take_damage(raw_damage * bonus, ignore_armor, source)
        if source is not None and dealt > 0:
            self.add_hate(source, dealt * threat)        # threat modifier: more hate, same damage
        return dealt


class GameState:
    """Central game state container."""

    def __init__(self):
        self.heroes: list[Hero] = []
        self.monsters: list[Monster] = []
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
        self.adventure_failed = True
        return True
