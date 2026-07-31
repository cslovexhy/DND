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

Patrol:
- Each monster gets a randomized patrol route near its spawn (3-5 waypoints within patrol_radius)
- While IDLE, monster walks the route in a loop at reduced speed
- On aggro, drops patrol and fights
- On reset (leash), walks back to spawn, then resumes patrol from nearest waypoint
"""
import math
import random
from typing import Optional
from .entities import Monster, Hero, Entity, Condition
from .pathfinding import astar


# === AGGRO STATE ===
class AggroState:
    IDLE = "idle"        # Not aware of hero
    AGGROED = "aggroed"  # Chasing/attacking hero
    RESETTING = "reset"  # Walking back to spawn (lost aggro)


def init_monster_aggro(monster: Monster, sense_range=180, call_range=120, leash_range=500, group_id=None):
    """Attach aggro data to a monster. Call after creating the monster."""
    monster.aggro_state = AggroState.IDLE
    monster.sense_range = sense_range        # Detection radius (pixels)
    monster.stealth_sense_range = sense_range * 0.1  # Detection radius vs stealthed hero (10% default)
    monster.call_range = call_range          # Call-for-help radius when attacked
    monster.leash_range = leash_range        # Max chase distance from spawn
    monster.spawn_x = monster.x             # Remember where it spawned
    monster.spawn_y = monster.y
    monster.group_id = group_id             # Linked group (pull one = pull all)
    monster.aggro_target = None             # Current target

    # Patrol system
    monster.patrol_route = []               # List of (x, y) waypoints
    monster.patrol_index = 0                # Current waypoint index
    monster.patrol_wait = 0.0               # Time to pause at waypoint
    monster.patrol_speed_mult = 0.4         # Patrol at 40% speed


def generate_patrol_route(monster: Monster, patrol_radius=80, num_waypoints=None, collision_fn=None):
    """Generate a random patrol route around the monster's spawn point.
    Call after the monster is placed and aggro is initialized."""
    if num_waypoints is None:
        num_waypoints = random.randint(3, 5)

    route = []
    for _ in range(num_waypoints):
        # Generate random point within patrol_radius of spawn
        angle = random.uniform(0, 2 * math.pi)
        dist = random.uniform(patrol_radius * 0.3, patrol_radius)
        wx = monster.spawn_x + math.cos(angle) * dist
        wy = monster.spawn_y + math.sin(angle) * dist

        # If collision function provided, skip blocked waypoints
        if collision_fn and collision_fn(wx, wy):
            continue
        route.append((wx, wy))

    # Always include spawn as a waypoint so they return to base
    if route:
        route.append((monster.spawn_x, monster.spawn_y))

    monster.patrol_route = route
    monster.patrol_index = 0
    monster.patrol_wait = random.uniform(0.5, 2.0)  # Initial pause before starting


def patrol_tick(monster: Monster, dt: float, collision_fn=None):
    """Advance patrol movement. Called when monster is IDLE."""
    if not monster.patrol_route:
        return

    # Waiting at waypoint
    if monster.patrol_wait > 0:
        monster.patrol_wait -= dt
        return

    # Move toward current waypoint at reduced speed
    wx, wy = monster.patrol_route[monster.patrol_index]
    dx = wx - monster.x
    dy = wy - monster.y
    dist = math.sqrt(dx * dx + dy * dy)

    if dist < 8:
        # Reached waypoint — pause then advance to next
        monster.patrol_index = (monster.patrol_index + 1) % len(monster.patrol_route)
        monster.patrol_wait = random.uniform(1.0, 3.0)
    else:
        # Check if direct path is blocked — skip waypoint if stuck
        if collision_fn and collision_fn(wx, wy):
            # Waypoint became invalid, skip it
            monster.patrol_index = (monster.patrol_index + 1) % len(monster.patrol_route)
            monster.patrol_wait = 0.5
            return

        # Move toward waypoint (use reduced speed)
        orig_speed = monster.speed
        monster.speed = orig_speed * monster.patrol_speed_mult
        monster.move_toward(wx, wy, dt, collision_fn)
        monster.speed = orig_speed

        # Stuck detection: if barely moved after several frames, skip waypoint
        if not hasattr(monster, '_patrol_stuck_check'):
            monster._patrol_stuck_check = (monster.x, monster.y)
            monster._patrol_stuck_timer = 0.0
        monster._patrol_stuck_timer += dt
        if monster._patrol_stuck_timer >= 1.0:
            moved = math.sqrt((monster.x - monster._patrol_stuck_check[0])**2 +
                              (monster.y - monster._patrol_stuck_check[1])**2)
            if moved < 3:
                # Stuck — skip this waypoint
                monster.patrol_index = (monster.patrol_index + 1) % len(monster.patrol_route)
                monster.patrol_wait = 0.5
            monster._patrol_stuck_check = (monster.x, monster.y)
            monster._patrol_stuck_timer = 0.0


def resume_patrol_from_nearest(monster: Monster):
    """After resetting from aggro, find the nearest patrol waypoint to resume from."""
    if not monster.patrol_route:
        return
    best_idx = 0
    best_dist = float('inf')
    for i, (wx, wy) in enumerate(monster.patrol_route):
        dx = monster.x - wx
        dy = monster.y - wy
        d = dx * dx + dy * dy
        if d < best_dist:
            best_dist = d
            best_idx = i
    monster.patrol_index = best_idx
    monster.patrol_wait = random.uniform(0.5, 1.5)


def check_aggro(monster: Monster, heroes: list[Hero], all_monsters: list[Monster]):
    """Check if monster should aggro based on sense range."""
    if monster.aggro_state == AggroState.AGGROED:
        # Check leash
        dx = monster.x - monster.spawn_x
        dy = monster.y - monster.spawn_y
        if not monster.is_boss and math.sqrt(dx*dx + dy*dy) > monster.leash_range:
            monster.aggro_state = AggroState.RESETTING
            monster.aggro_target = None
        return

    if monster.aggro_state == AggroState.RESETTING:
        # Walk back to spawn
        dx = monster.spawn_x - monster.x
        dy = monster.spawn_y - monster.y
        if math.sqrt(dx*dx + dy*dy) < 20:
            monster.aggro_state = AggroState.IDLE
            resume_patrol_from_nearest(monster)
        return

    # IDLE: check sense range
    for hero in heroes:
        if not hero.alive:
            continue
        dist = monster.distance_to(hero)
        # Use stealth sense range if hero is stealthed
        effective_sense = monster.stealth_sense_range if getattr(hero, 'stealthed', False) else monster.sense_range
        if dist <= effective_sense:
            aggro_monster(monster, hero, all_monsters)
            break


def aggro_monster(monster: Monster, target: Hero, all_monsters: list[Monster]):
    """Aggro a monster and optionally its linked group. Breaks stealth."""
    monster.aggro_state = AggroState.AGGROED
    monster.aggro_target = target

    # Break stealth if hero is stealthed and detected
    if getattr(target, 'stealthed', False):
        target.stealthed = False

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
    """Move toward target but stop at attack range (not 0 distance).
    Uses A* pathfinding to navigate around obstacles."""
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
        # Use pathfinding if we have a dungeon reference and collision function
        if collision_fn and hasattr(monster, '_nav_dungeon') and monster._nav_dungeon:
            # Repath periodically (every 0.5s) or if no path
            if not hasattr(monster, '_chase_path'):
                monster._chase_path = []
                monster._chase_repath_timer = 0
            monster._chase_repath_timer -= dt
            if monster._chase_repath_timer <= 0 or not monster._chase_path:
                monster._chase_path = astar(monster._nav_dungeon, monster.x, monster.y,
                                            target.x, target.y, max_steps=60)
                monster._chase_repath_timer = 0.5

            if monster._chase_path:
                # Move toward next waypoint
                wx, wy = monster._chase_path[0]
                wpd = math.sqrt((wx - monster.x)**2 + (wy - monster.y)**2)
                if wpd < 10:
                    monster._chase_path.pop(0)
                    if monster._chase_path:
                        wx, wy = monster._chase_path[0]
                    else:
                        monster.move_toward(target.x, target.y, dt, collision_fn)
                        return False
                monster.move_toward(wx, wy, dt, collision_fn)
            else:
                # Fallback: direct movement
                monster.move_toward(target.x, target.y, dt, collision_fn)
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
        if monster.swing_timer <= 0:
            monster.swing_timer = monster.weapon_speed
            # Cast time: freeze in place while shooting
            monster.apply_condition(Condition.IMMOBILIZED, 0.5)
            # Return signal to spawn projectile (damage applied on hit)
            return ("ranged_attack_projectile", target, monster.base_damage)

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
        monster.weapon_speed = max(0.6, monster.weapon_speed * 0.98)

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


def setup_monster_aggro(monster: Monster, nav_dungeon=None):
    """Initialize aggro for a newly spawned monster."""
    sense = SENSE_RANGES.get(monster.name, 170)
    atk_range = ATTACK_RANGES.get(monster.name, 50)
    monster.attack_range = atk_range
    init_monster_aggro(monster, sense_range=sense, call_range=120, leash_range=500)
    monster._nav_dungeon = nav_dungeon  # Reference for A* pathfinding


def run_monster_ai(monster: Monster, heroes: list[Hero], dt: float,
                   collision_fn=None, all_monsters=None):
    """Run aggro check + AI for a monster."""
    if not monster.alive:
        return None
    if monster.has_condition(Condition.STUNNED) or monster.has_condition(Condition.FROZEN):
        return None
    if not hasattr(monster, 'aggro_state'):
        setup_monster_aggro(monster)

    # Check aggro
    check_aggro(monster, heroes, all_monsters or [])

    # If resetting, walk back to spawn
    if monster.aggro_state == AggroState.RESETTING:
        monster.move_toward(monster.spawn_x, monster.spawn_y, dt, collision_fn)
        return None

    # If idle, patrol
    if monster.aggro_state == AggroState.IDLE:
        patrol_tick(monster, dt, collision_fn)
        return None

    # Aggroed: run behavior
    ai_fn = AI_BEHAVIORS.get(monster.name, ai_melee)
    return ai_fn(monster, heroes, dt, collision_fn)
