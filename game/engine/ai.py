"""
Monster AI with aggro system.

Aggro rules:
- Monsters start IDLE (not aggroed)
- SENSE RANGE: monster detects hero within this radius → aggro
- CALL FOR HELP: when attacked, monsters within call_range also aggro
- LEASH RANGE: if hero moves too far from spawn, monster resets
- LINKED GROUPS: optional, pull one = pull all in group

Attack positioning:
- All attacks have range > 0
- Melee monsters stop at their attack range (~40-50px), not 0
- Ranged monsters keep distance
"""
import math
from typing import Optional
from .entities import Monster, Hero, Entity, Condition


# === AGGRO STATE ===
class AggroState:
    IDLE = "idle"        # Not aware of hero
    AGGROED = "aggroed"  # Chasing/attacking hero
    RESETTING = "reset"  # Walking back to spawn (lost aggro)


def init_monster_aggro(monster: Monster, sense_range=180, call_range=120, leash_range=500, group_id=None):
    """Attach aggro data to a monster. Call after creating the monster."""
    monster.aggro_state = AggroState.IDLE
    monster.sense_range = sense_range        # Detection radius (pixels)
    monster.call_range = call_range          # Call-for-help radius when attacked
    monster.leash_range = leash_range        # Max chase distance from spawn
    monster.spawn_x = monster.x             # Remember where it spawned
    monster.spawn_y = monster.y
    monster.group_id = group_id             # Linked group (pull one = pull all)
    monster.aggro_target = None             # Current target


def check_aggro(monster: Monster, heroes: list[Hero], all_monsters: list[Monster]):
    """Check if monster should aggro based on sense range."""
    if monster.aggro_state == AggroState.AGGROED:
        # Check leash
        dx = monster.x - monster.spawn_x
        dy = monster.y - monster.spawn_y
        if math.sqrt(dx*dx + dy*dy) > monster.leash_range:
            monster.aggro_state = AggroState.RESETTING
            monster.aggro_target = None
        return

    if monster.aggro_state == AggroState.RESETTING:
        # Walk back to spawn
        dx = monster.spawn_x - monster.x
        dy = monster.spawn_y - monster.y
        if math.sqrt(dx*dx + dy*dy) < 20:
            monster.aggro_state = AggroState.IDLE
            monster.hp = monster.max_hp  # Reset HP on full reset
        return

    # IDLE: check sense range
    for hero in heroes:
        if not hero.alive:
            continue
        dist = monster.distance_to(hero)
        if dist <= monster.sense_range:
            aggro_monster(monster, hero, all_monsters)
            break


def aggro_monster(monster: Monster, target: Hero, all_monsters: list[Monster]):
    """Aggro a monster and optionally its linked group."""
    monster.aggro_state = AggroState.AGGROED
    monster.aggro_target = target

    # Pull linked group
    if monster.group_id is not None:
        for m in all_monsters:
            if m == monster or not m.alive:
                continue
            if hasattr(m, 'group_id') and m.group_id == monster.group_id:
                if m.aggro_state == AggroState.IDLE:
                    m.aggro_state = AggroState.AGGROED
                    m.aggro_target = target


def call_for_help(attacked_monster: Monster, all_monsters: list[Monster], target: Hero):
    """When a monster is attacked, nearby monsters within call_range also aggro."""
    for m in all_monsters:
        if m == attacked_monster or not m.alive:
            continue
        if not hasattr(m, 'aggro_state'):
            continue
        if m.aggro_state != AggroState.IDLE:
            continue
        dist = attacked_monster.distance_to(m)
        if dist <= attacked_monster.call_range:
            m.aggro_state = AggroState.AGGROED
            m.aggro_target = target


# === MOVEMENT WITH PROPER SPACING ===

def move_to_attack_range(monster: Monster, target: Hero, dt: float, collision_fn=None):
    """Move toward target but stop at attack range (not 0 distance)."""
    dist = monster.distance_to(target)
    desired_dist = monster.attack_range * 0.9  # Stop slightly inside attack range

    if dist <= desired_dist:
        # Already in range — don't move closer
        # Actually back up slightly if too close
        if dist < desired_dist * 0.5:
            dx = monster.x - target.x
            dy = monster.y - target.y
            d = math.sqrt(dx*dx + dy*dy) or 1
            retreat_x = monster.x + (dx/d) * 20
            retreat_y = monster.y + (dy/d) * 20
            monster.move_toward(retreat_x, retreat_y, dt * 0.5, collision_fn)
        return True  # In range
    else:
        monster.move_toward(target.x, target.y, dt, collision_fn)
        return False  # Not yet in range


# === AI BEHAVIORS ===

def ai_melee(monster: Monster, heroes: list[Hero], dt: float, collision_fn=None):
    """Melee monster: move to attack range, attack when close enough."""
    target = monster.aggro_target
    if not target or not target.alive:
        target = _find_closest_alive(monster, heroes)
        if not target:
            return None
        monster.aggro_target = target

    in_range = move_to_attack_range(monster, target, dt, collision_fn)

    if in_range:
        dmg = monster.try_basic_attack(target)
        if dmg is not None:
            if monster.on_hit_condition:
                cond, dur = monster.on_hit_condition
                target.apply_condition(cond, dur,
                                       tick_damage=10.0 if cond == Condition.POISONED else 0)
            return ("attack", target, dmg)
    return ("move", target, 0)


def ai_ranged(monster: Monster, heroes: list[Hero], dt: float, collision_fn=None):
    """Ranged monster: keep distance, shoot from afar."""
    target = monster.aggro_target
    if not target or not target.alive:
        target = _find_closest_alive(monster, heroes)
        if not target:
            return None
        monster.aggro_target = target

    dist = monster.distance_to(target)
    preferred_min = monster.attack_range * 0.5
    preferred_max = monster.attack_range * 0.85

    if dist < preferred_min:
        # Too close, back away
        dx = monster.x - target.x
        dy = monster.y - target.y
        d = math.sqrt(dx*dx + dy*dy) or 1
        flee_x = monster.x + (dx/d) * 100
        flee_y = monster.y + (dy/d) * 100
        monster.move_toward(flee_x, flee_y, dt, collision_fn)
    elif dist > preferred_max:
        # Too far, close in
        monster.move_toward(target.x, target.y, dt, collision_fn)
    else:
        # In sweet spot, attack
        if monster.attack_cd_remaining <= 0:
            monster.attack_cd_remaining = monster.attack_cooldown
            # Cast time: freeze in place while shooting
            monster.apply_condition(Condition.IMMOBILIZED, 0.5)
            dmg = target.take_damage(monster.attack_damage)
            if monster.on_hit_condition:
                cond, dur = monster.on_hit_condition
                target.apply_condition(cond, dur,
                                       tick_damage=10.0 if cond == Condition.POISONED else 0)
            return ("ranged_attack", target, dmg)

    return ("move", target, 0)


def ai_boss(monster: Monster, heroes: list[Hero], dt: float, collision_fn=None):
    """Boss: aggressive, targets lowest HP at low health, attacks faster when enraged."""
    target = monster.aggro_target
    if not target or not target.alive:
        target = _find_closest_alive(monster, heroes)
        if not target:
            return None
        monster.aggro_target = target

    hp_pct = monster.hp / monster.max_hp

    # Enrage at 30%
    if hp_pct < 0.3:
        monster.attack_cooldown = max(0.6, monster.attack_cooldown * 0.98)

    # Switch to lowest HP target at 50%
    if hp_pct < 0.5:
        lowest = min([h for h in heroes if h.alive], key=lambda h: h.hp, default=target)
        if lowest:
            target = lowest
            monster.aggro_target = target

    in_range = move_to_attack_range(monster, target, dt, collision_fn)

    if in_range:
        dmg = monster.try_basic_attack(target)
        if dmg is not None:
            if monster.on_hit_condition:
                cond, dur = monster.on_hit_condition
                target.apply_condition(cond, dur,
                                       tick_damage=10.0 if cond == Condition.POISONED else 0)
            return ("attack", target, dmg)
    return ("move", target, 0)


def _find_closest_alive(monster, heroes):
    alive = [h for h in heroes if h.alive]
    if not alive:
        return None
    return min(alive, key=lambda h: monster.distance_to(h))


# === AI ASSIGNMENT ===
AI_BEHAVIORS = {
    "Orc Smasher": ai_melee,
    "Kobold Dragonshield": ai_melee,
    "Duergar Guard": ai_melee,
    "Cave Bear": ai_melee,
    "Legion Devil": ai_melee,
    "Snake": ai_melee,
    "Grell": ai_melee,
    "Gibbering Mouther": ai_melee,
    "Orc Archer": ai_ranged,
    "Human Cultist": ai_ranged,
    "Meerak": ai_boss,
    "Ashardalon": ai_boss,
    "Gauth": ai_boss,
    "Rage Drake": ai_boss,
    "Otyugh": ai_boss,
    "Karash": ai_boss,
    "Margrath": ai_boss,
}

# Sense ranges by monster type
SENSE_RANGES = {
    "Kobold Dragonshield": 150,
    "Snake": 120,
    "Orc Smasher": 180,
    "Orc Archer": 220,
    "Human Cultist": 200,
    "Duergar Guard": 160,
    "Legion Devil": 170,
    "Cave Bear": 200,
    "Grell": 180,
    "Gibbering Mouther": 140,
}

# Attack ranges (pixels) - NONE are 0
ATTACK_RANGES = {
    "Orc Smasher": 50,
    "Kobold Dragonshield": 45,
    "Duergar Guard": 50,
    "Cave Bear": 55,
    "Legion Devil": 45,
    "Snake": 40,
    "Grell": 50,
    "Gibbering Mouther": 60,
    "Orc Archer": 220,
    "Human Cultist": 200,
    # Bosses
    "Meerak": 55,
    "Ashardalon": 70,
    "Gauth": 200,
    "Rage Drake": 55,
    "Otyugh": 60,
}


def setup_monster_aggro(monster: Monster):
    """Initialize aggro for a newly spawned monster."""
    sense = SENSE_RANGES.get(monster.name, 170)
    atk_range = ATTACK_RANGES.get(monster.name, 50)
    monster.attack_range = atk_range
    init_monster_aggro(monster, sense_range=sense, call_range=120, leash_range=500)


def run_monster_ai(monster: Monster, heroes: list[Hero], dt: float,
                   collision_fn=None, all_monsters=None):
    """Run aggro check + AI for a monster."""
    if not monster.alive:
        return None
    if monster.has_condition(Condition.STUNNED):
        return None
    if not hasattr(monster, 'aggro_state'):
        setup_monster_aggro(monster)

    # Check aggro
    check_aggro(monster, heroes, all_monsters or [])

    # If resetting, walk back to spawn
    if monster.aggro_state == AggroState.RESETTING:
        monster.move_toward(monster.spawn_x, monster.spawn_y, dt, collision_fn)
        return None

    # If idle, do nothing
    if monster.aggro_state == AggroState.IDLE:
        return None

    # Aggroed: run behavior
    ai_fn = AI_BEHAVIORS.get(monster.name, ai_melee)
    return ai_fn(monster, heroes, dt, collision_fn)
