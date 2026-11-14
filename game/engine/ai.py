"""
Monster AI with aggro system.

Aggro rules:
- Monsters start IDLE (not aggroed)
- SENSE RANGE: monster detects hero within this radius → aggro
- CALL FOR HELP: when attacked, monsters within call_range also aggro
- LEASH: a monster further than leash_range from its spawn gives up (walks home and resets) once it has gone
  LEASH_TIME seconds without combat. Taking damage from a hero, or landing a hit, restarts that timer, so a hero
  who keeps hitting it keeps it fighting (it used to reset the instant it crossed the line, then re-aggro on the
  next hit, then reset again: ping-pong).
- LINKED GROUPS: optional, pull one = pull all in group
- HATE: every monster keeps a hate table (Monster.hate). 1 hate per damage dealt to it, 0.8 per HP a healer heals or
  shields on a hero already on its table; healing such a friend also puts the healer on the table. Every aggroed
  monster chases the top-hated living hero (pick_target). Only difference: normal monsters can be unleashed (leash
  range, nobody left to fight) and then clear their table; BOSSES never release aggro.

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
from .pathfinding import astar, has_line_of_sight
from .skills import check_skill_triggers


# === AGGRO STATE ===
class AggroState:
    IDLE = "idle"        # Not aware of hero
    AGGROED = "aggroed"  # Chasing/attacking hero
    RESETTING = "reset"  # Walking back to spawn (lost aggro)


HEAL_HATE_PER_HP = 0.8   # hate per HP healed or shielded (damage is 1 hate per point)
LEASH_TIME = 5.0         # seconds without combat (beyond leash range) before a monster gives up
EVADE_TIME = 8.0         # a monster walking home that still isn't there after this long teleports to its spawn


def release_aggro(monster):
    """Monster gives up: forget its target and hate table and walk back to spawn. Never call this on a boss."""
    monster.aggro_state = AggroState.RESETTING
    monster.aggro_target = None
    monster.hate.clear()
    monster.resetting_for = 0.0


def is_fighting(hero, monsters) -> bool:
    """`hero` is in combat: an aggroed monster is fighting them (has them as its target or on its hate table).
    Out-of-combat-only skills (Stealth) are refused then."""
    return any(m.alive and m.aggro_state == AggroState.AGGROED and (m.aggro_target is hero or hero in m.hate)
               for m in monsters)


def drop_from_hate(monster, hero):
    """`hero` is no longer a valid target for this monster (fell and respawned elsewhere): take them off
    the hate table. A boss never lets go; any other monster resets if nobody alive is left on its table."""
    monster.hate.pop(hero, None)
    if monster.aggro_target is hero:
        monster.aggro_target = None
    if not monster.is_boss and not any(h.alive for h in monster.hate):
        release_aggro(monster)


def credit_heal_hate(monsters, healer, target, amount):
    """`healer` healed/shielded `amount` HP on `target`: every living monster that has `target` on its hate table
    gets `amount` x 0.8 hate for the healer, and the healer joins the table even when the heal did nothing."""
    for m in monsters:
        if m.alive and target in m.hate:
            m.add_hate(healer, amount * HEAL_HATE_PER_HP)


def init_monster_aggro(monster: Monster, sense_range=180, call_range=120, leash_range=500,
                       group_id=None, relentless=False, hive_mind=None):
    """Attach aggro data to a monster. Call after creating the monster."""
    monster.aggro_state = AggroState.IDLE
    monster.sense_range = sense_range        # Detection radius (pixels)
    monster.stealth_sense_range = sense_range * 0.1  # Detection radius vs stealthed hero (10% default)
    monster.call_range = call_range          # Call-for-help radius when attacked
    monster.leash_range = leash_range        # Max chase distance from spawn
    monster.relentless = relentless          # If True, never leash-resets aggro (hunts forever)
    # hive_mind: optional (range, [spawn_type_names]). If any monster of the listed
    # types is attacked within `range`, this monster also aggros. None = disabled.
    monster.hive_mind = hive_mind
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
        # Check leash — bosses and relentless monsters never leash-reset.
        dx = monster.x - monster.spawn_x
        dy = monster.y - monster.spawn_y
        exempt = monster.is_boss or getattr(monster, 'relentless', False)
        if (not exempt and math.sqrt(dx*dx + dy*dy) > monster.leash_range
                and getattr(monster, "since_combat", 0.0) >= LEASH_TIME):
            release_aggro(monster)
        return

    if monster.aggro_state == AggroState.RESETTING:
        # Walk back to spawn
        dx = monster.spawn_x - monster.x
        dy = monster.spawn_y - monster.y
        if math.sqrt(dx*dx + dy*dy) < 20:
            monster.aggro_state = AggroState.IDLE
            monster.hate.clear()
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
            # Line of sight check — can't aggro through walls
            if hasattr(monster, '_nav_dungeon') and monster._nav_dungeon:
                if not has_line_of_sight(monster._nav_dungeon, monster.x, monster.y, hero.x, hero.y):
                    continue
            aggro_monster(monster, hero, all_monsters)
            break


def aggro_monster(monster: Monster, target: Hero, all_monsters: list[Monster]):
    """Aggro a monster and optionally its linked group. Breaks stealth."""
    monster.aggro_state = AggroState.AGGROED
    monster.aggro_target = target
    monster.add_hate(target)
    monster.since_combat = 0.0

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
                    m.add_hate(target)


def call_for_help(attacked_monster: Monster, all_monsters: list[Monster], target: Hero):
    """When a monster is attacked, nearby monsters also aggro.

    Two mechanics are applied:
    1. call_range: idle monsters within the attacked monster's call_range aggro.
    2. hive_mind: a monster with hive_mind=(range, [spawn_types]) aggros when a
       monster whose spawn_type is in its list is attacked within that range.
    """
    attacked_type = getattr(attacked_monster, 'spawn_type', None)
    for m in all_monsters:
        if m == attacked_monster or not m.alive:
            continue
        if not hasattr(m, 'aggro_state') or m.aggro_state != AggroState.IDLE:
            continue

        # 1) Standard proximity call-for-help
        if attacked_monster.distance_to(m) <= attacked_monster.call_range:
            m.aggro_state = AggroState.AGGROED
            m.aggro_target = target
            m.add_hate(target)
            continue

        # 2) Hive mind: m watches for specific types being attacked within range
        hive = getattr(m, 'hive_mind', None)
        if hive and attacked_type is not None:
            hive_range, hive_types = hive
            if attacked_type in hive_types and attacked_monster.distance_to(m) <= hive_range:
                m.aggro_state = AggroState.AGGROED
                m.aggro_target = target
                m.add_hate(target)


# === MOVEMENT WITH PROPER SPACING ===

def face_target(monster: Monster, target) -> None:
    """Turn the sprite toward `target` (left or right). Only changes when the target is clearly to one side, so a
    target straight above/below doesn't make it flicker."""
    dx = target.x - monster.x
    if abs(dx) > 1.0:
        monster.facing_left = dx < 0


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
        face_target(monster, target)   # backing off must not turn its back on the target it is attacking
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
    target = pick_target(monster, heroes)
    if target is None:
        return None
    monster.aggro_target = target

    in_range = move_to_attack_range(monster, target, dt, collision_fn)

    if in_range:
        dmg = monster.try_basic_attack(target)
        if dmg is not None:
            monster.since_combat = 0.0          # it reached someone: the leash timer starts over
            return ("attack", target, dmg)      # (World spends an armed Poison Dagger on this hit)
    return ("move", target, 0)


def ai_ranged(monster: Monster, heroes: list[Hero], dt: float, collision_fn=None):
    """Ranged monster: keep distance, shoot from afar."""
    target = pick_target(monster, heroes)
    if target is None:
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
        # In sweet spot — only attack if line of sight is clear
        can_shoot = True
        if hasattr(monster, '_nav_dungeon') and monster._nav_dungeon:
            can_shoot = has_line_of_sight(monster._nav_dungeon, monster.x, monster.y, target.x, target.y)
        face_target(monster, target)
        if can_shoot and monster.swing_timer <= 0:
            monster.swing_timer = monster.weapon_speed
            # Cast time: freeze in place while shooting
            monster.apply_condition(Condition.IMMOBILIZED, 0.5)
            # Return signal to spawn projectile (damage applied on hit)
            ranged_dmg = monster.hit_damage()       # (Demoralized etc. apply when it lands: Entity.damage_mult)
            return ("ranged_attack_projectile", target, ranged_dmg)

    return ("move", target, 0)


def pick_target(monster: Monster, heroes: list[Hero]):
    """Who an aggroed monster chases: the living hero with the most hate (the current target wins ties). If nobody alive is on
    its hate table it keeps its current target, else the closest living hero. None only when every hero is dead."""
    alive = [h for h in heroes if h.alive]
    if not alive:
        return None
    current = monster.aggro_target if monster.aggro_target in alive else None
    top = monster.top_hate_target(alive)
    if top is None:
        return current or _find_closest_alive(monster, alive)
    if current is not None and monster.hate.get(current, 0.0) >= monster.hate[top]:
        return current
    return top


def ai_boss(monster: Monster, heroes: list[Hero], dt: float, collision_fn=None):
    """Boss: never releases aggro; chases the top-hated hero until they die (then the next one), attacks faster
    when enraged."""
    target = pick_target(monster, heroes)
    if target is None:
        return None
    monster.aggro_target = target

    hp_pct = monster.hp / monster.max_hp

    # Enrage at 30%
    if hp_pct < 0.3:
        monster.weapon_speed = max(0.6, monster.weapon_speed * 0.98)

    in_range = move_to_attack_range(monster, target, dt, collision_fn)

    if in_range:
        dmg = monster.try_basic_attack(target)
        if dmg is not None:
            monster.since_combat = 0.0          # it reached someone: the leash timer starts over
            return ("attack", target, dmg)      # (World spends an armed Poison Dagger on this hit)
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
    "Human Cultist": ai_melee,
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
    "Demogorgon": 340,  # extra-large sense range — hunts from far away
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
    "Human Cultist": 50,
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
    ranged = getattr(monster, "ranged_attack_range", 0) > 0
    atk_range = ATTACK_RANGES.get(monster.name, 220 if ranged else 50)   # (custom ranged types: archer range)
    monster.attack_range = atk_range
    # relentless / hive_mind may be pre-set on the monster from spawn data.
    relentless = getattr(monster, 'relentless', False)
    hive_mind = getattr(monster, 'hive_mind', None)
    init_monster_aggro(monster, sense_range=sense, call_range=120, leash_range=500,
                       relentless=relentless, hive_mind=hive_mind)
    monster._nav_dungeon = nav_dungeon  # Reference for A* pathfinding


def run_monster_ai(monster: Monster, heroes: list[Hero], dt: float,
                   collision_fn=None, all_monsters=None):
    """Run aggro check + AI for a monster."""
    if not monster.alive:
        return None
    if not monster.can_act:
        return None
    if monster.dash is not None or monster.channel is not None:
        return None                       # busy dashing (Charge) or channelling (engine/actions.py)
    if not hasattr(monster, 'aggro_state'):
        setup_monster_aggro(monster)

    # Check aggro (the leash timer counts time without combat while aggroed)
    if monster.aggro_state == AggroState.AGGROED:
        monster.since_combat = getattr(monster, "since_combat", 0.0) + dt
    check_aggro(monster, heroes, all_monsters or [])

    # If resetting, walk back to spawn (monsters walk straight, so a wall can block them: then they "evade" home)
    if monster.aggro_state == AggroState.RESETTING:
        monster.resetting_for = getattr(monster, "resetting_for", 0.0) + dt
        if monster.resetting_for >= EVADE_TIME:
            monster.x, monster.y = monster.spawn_x, monster.spawn_y
        else:
            monster.move_toward(monster.spawn_x, monster.spawn_y, dt, collision_fn)
        return None

    # If idle, patrol
    if monster.aggro_state == AggroState.IDLE:
        patrol_tick(monster, dt, collision_fn)
        return None

    # Aggroed: special skills whose HP trigger was reached are queued here and cast by the World
    check_skill_triggers(monster)

    # Aggroed: run behavior (every boss uses the hate rules; types without an entry: melee, or ranged if they shoot)
    default = ai_ranged if getattr(monster, "ranged_attack_range", 0) > 0 else ai_melee
    ai_fn = ai_boss if monster.is_boss else AI_BEHAVIORS.get(monster.name, default)
    return ai_fn(monster, heroes, dt, collision_fn)
