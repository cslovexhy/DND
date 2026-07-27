"""
Monster AI — behavior trees derived from board game tactic scripts.

Board game tactics are if/then priority lists:
  "If within 1 tile of Hero → move adjacent and attack"
  "Otherwise → move 1 tile toward closest Hero"

We translate these to real-time behavior trees with the same priority logic.
"""
import math
from typing import Optional
from .entities import Monster, Hero, Entity, Condition

TILE_RANGE = 48 * 4  # "1 tile" in pixels (~4 tile-widths for ARPG feel)


def find_closest_hero(monster: Monster, heroes: list[Hero]) -> Optional[Hero]:
    """Find closest alive hero."""
    alive = [h for h in heroes if h.alive]
    if not alive:
        return None
    return min(alive, key=lambda h: monster.distance_to(h))


def find_lowest_hp_hero(monster: Monster, heroes: list[Hero]) -> Optional[Hero]:
    """Find alive hero with lowest HP (for smart monsters)."""
    alive = [h for h in heroes if h.alive]
    if not alive:
        return None
    return min(alive, key=lambda h: h.hp)


# === BEHAVIOR FUNCTIONS ===

def ai_melee_rusher(monster: Monster, heroes: list[Hero], dt: float, collision_fn=None):
    """
    Standard melee monster (Orc Smasher, Kobold, Duergar, etc.)
    Tactic: Move to closest hero, attack when in range.
    """
    target = find_closest_hero(monster, heroes)
    if not target:
        return None

    dist = monster.distance_to(target)

    # If in attack range, attack
    if dist <= monster.attack_range:
        dmg = monster.try_basic_attack(target)
        if dmg is not None:
            # Apply on-hit condition if any
            if monster.on_hit_condition:
                cond, dur = monster.on_hit_condition
                target.apply_condition(cond, dur, 
                                       tick_damage=10.0 if cond == Condition.POISONED else 0)
            return ("attack", target, dmg)
    else:
        # Move toward target
        monster.move_toward(target.x, target.y, dt, collision_fn)
        return ("move", target, 0)

    return None


def ai_ranged_kiter(monster: Monster, heroes: list[Hero], dt: float, collision_fn=None):
    """
    Ranged monster (Orc Archer, Cultist).
    Tactic: Stay at range, shoot. If hero gets too close, back away.
    """
    target = find_closest_hero(monster, heroes)
    if not target:
        return None

    dist = monster.distance_to(target)
    preferred_range = monster.ranged_attack_range * 0.7  # Stay at ~70% of max range

    # If target is too close, back away
    if dist < monster.attack_range * 1.5:
        # Move away from target
        dx = monster.x - target.x
        dy = monster.y - target.y
        d = math.sqrt(dx*dx + dy*dy) or 1
        flee_x = monster.x + (dx/d) * 100
        flee_y = monster.y + (dy/d) * 100
        monster.move_toward(flee_x, flee_y, dt, collision_fn)
        return ("flee", target, 0)

    # If in ranged attack range, shoot
    if dist <= monster.ranged_attack_range and monster.attack_cd_remaining <= 0:
        monster.attack_cd_remaining = monster.attack_cooldown
        dmg = target.take_damage(monster.ranged_attack_damage)
        if monster.on_hit_condition:
            cond, dur = monster.on_hit_condition
            target.apply_condition(cond, dur,
                                   tick_damage=10.0 if cond == Condition.POISONED else 0)
        return ("ranged_attack", target, dmg)

    # Otherwise move toward preferred range
    if dist > monster.ranged_attack_range:
        monster.move_toward(target.x, target.y, dt, collision_fn)
        return ("move", target, 0)

    return None


def ai_aoe_attacker(monster: Monster, heroes: list[Hero], dt: float, collision_fn=None):
    """
    AoE monster (Gibbering Mouther).
    Tactic: Move to center of heroes, attack all in range.
    """
    alive_heroes = [h for h in heroes if h.alive]
    if not alive_heroes:
        return None

    # Find center of heroes
    cx = sum(h.x for h in alive_heroes) / len(alive_heroes)
    cy = sum(h.y for h in alive_heroes) / len(alive_heroes)

    target = find_closest_hero(monster, heroes)
    dist = monster.distance_to(target)

    # If heroes are within range, AoE attack all
    if dist <= monster.attack_range and monster.attack_cd_remaining <= 0:
        monster.attack_cd_remaining = monster.attack_cooldown
        total_dmg = 0
        for h in alive_heroes:
            if monster.distance_to(h) <= monster.attack_range * 1.5:
                dmg = h.take_damage(monster.attack_damage)
                total_dmg += dmg
                if monster.on_hit_condition:
                    cond, dur = monster.on_hit_condition
                    h.apply_condition(cond, dur)
        return ("aoe_attack", target, total_dmg)
    else:
        # Move toward center of heroes
        monster.move_toward(cx, cy, dt, collision_fn)
        return ("move", target, 0)


def ai_boss(monster: Monster, heroes: list[Hero], dt: float, collision_fn=None):
    """
    Boss AI — more aggressive, targets lowest HP hero, has phases.
    """
    # Phase check: enrage at 30% HP
    hp_pct = monster.hp / monster.max_hp
    
    target = find_lowest_hp_hero(monster, heroes) if hp_pct < 0.5 else find_closest_hero(monster, heroes)
    if not target:
        return None

    dist = monster.distance_to(target)

    # Enrage: attack faster when low
    if hp_pct < 0.3:
        monster.attack_cooldown = 0.8  # Much faster attacks

    if dist <= monster.attack_range:
        dmg = monster.try_basic_attack(target)
        if dmg is not None:
            if monster.on_hit_condition:
                cond, dur = monster.on_hit_condition
                target.apply_condition(cond, dur,
                                       tick_damage=10.0 if cond == Condition.POISONED else 0)
            return ("attack", target, dmg)
    else:
        # Bosses are relentless
        effective_speed = monster.speed * (1.3 if hp_pct < 0.3 else 1.0)
        old_speed = monster.speed
        monster.speed = effective_speed
        monster.move_toward(target.x, target.y, dt, collision_fn)
        monster.speed = old_speed
        return ("move", target, 0)

    return None


# === AI ASSIGNMENT ===

# Map monster names to their AI behavior
AI_BEHAVIORS = {
    # Melee rushers
    "Orc Smasher": ai_melee_rusher,
    "Kobold Dragonshield": ai_melee_rusher,
    "Duergar Guard": ai_melee_rusher,
    "Cave Bear": ai_melee_rusher,
    "Legion Devil": ai_melee_rusher,
    "Snake": ai_melee_rusher,
    "Grell": ai_melee_rusher,

    # Ranged kiters
    "Orc Archer": ai_ranged_kiter,
    "Human Cultist": ai_ranged_kiter,

    # AoE attacker
    "Gibbering Mouther": ai_aoe_attacker,

    # Bosses
    "Ashardalon": ai_boss,
    "Gauth": ai_boss,
    "Rage Drake": ai_boss,
    "Otyugh": ai_boss,
    "Meerak": ai_boss,
    "Karash": ai_boss,
    "Margrath": ai_boss,
}


def run_monster_ai(monster: Monster, heroes: list[Hero], dt: float, collision_fn=None):
    """Run the appropriate AI for a monster."""
    if not monster.alive:
        return None
    if monster.has_condition(Condition.STUNNED):
        return None

    ai_fn = AI_BEHAVIORS.get(monster.name, ai_melee_rusher)
    return ai_fn(monster, heroes, dt, collision_fn)
