"""Shared ability execution helpers (pure; no pygame).

These are the "do the thing" functions used by both the player's cast logic and the companion AI.
Validation (range, LOS, cooldown) is done by the caller. Visuals are reported as World events.
"""
import random

from game.content.skill_tree import judgement_seal_bonus, smite_damage
from game.engine.ai import aggro_monster, call_for_help
from game.engine.entities import Projectile
from game.engine.events import Ring, FloatText


def _aggro_and_call_for_help(world, caster, target):
    if hasattr(target, 'aggro_state') and target.aggro_state != "aggroed":
        aggro_monster(target, caster, world.game_state.monsters)
    call_for_help(target, world.game_state.monsters, caster)


def can_ranged_hit(world, caster, target, ab):
    """Check if a ranged ability can hit: in range + line of sight."""
    if caster.distance_to(target) > ab.range:
        return False
    return world.check_los(caster.x, caster.y, target.x, target.y)


def fire_blast(world, caster, target, ab):
    """Fire Blast: instant ranged nuke. Returns damage dealt."""
    ab.use()
    dmg_amount = ab.calc_damage(caster.base_damage)
    dmg = target.take_damage(dmg_amount, source=caster)
    world.float_text(target.x, target.y - 20, f"{dmg:.0f}", (255, 130, 50))
    world.events.append(Ring(target.x, target.y, 30, (255, 100, 0)))
    _aggro_and_call_for_help(world, caster, target)
    return dmg


def ranged_projectile(world, caster, target, ab, color, apply_slow=False):
    """Spawn a homing projectile (Wanding, Frostbolt). Returns the Projectile."""
    ab.use()
    caster.swing_timer = caster.weapon_speed
    proj_damage = ab.calc_damage(caster.base_damage)
    proj = Projectile(x=caster.x, y=caster.y, target=target,
                      speed=500.0, damage=proj_damage,
                      color=color, source=caster)
    if apply_slow:
        proj.apply_slow = True
    world.projectiles.append(proj)
    return proj


def judgement(world, caster, target, ab):
    """Judgement: ranged holy damage, consumes Seal. Returns damage dealt."""
    ab.use()
    total_damage = ab.calc_damage(caster.base_damage)
    if "Righteous Seal" in caster.buffs:
        total_damage += judgement_seal_bonus(caster, ab)    # one weapon hit at skill level 3
        del caster.buffs["Righteous Seal"]
        world.float_text(target.x, target.y - 40, "Seal Consumed!", (255, 200, 50))
    dmg = target.take_damage(total_damage, source=caster)
    world.float_text(target.x, target.y - 20, f"{dmg:.0f}", (255, 255, 150))
    _aggro_and_call_for_help(world, caster, target)
    return dmg


def stab(world, caster, target, ab):
    """Stab: fast melee attack. Returns damage dealt."""
    ab.use()
    caster.swing_timer = caster.weapon_speed
    if getattr(caster, 'stealthed', False):
        caster.stealthed = False
        # The client of this player rebinds right-click back to Stealth (companions have no client)
        player = world.player_for_hero(caster)
        if player is not None:
            player._bind_right("R")
    dmg_amount = ab.calc_damage(caster.base_damage)
    # Crit check
    if random.random() < getattr(caster, 'crit_chance', 0.05):
        dmg_amount *= 2.0
        world.float_text(target.x, target.y - 40, "CRIT!", (255, 255, 0))
    dmg = target.take_damage(dmg_amount, source=caster)
    world.float_text(target.x, target.y - 20, f"{dmg:.0f}", (180, 255, 180))
    _aggro_and_call_for_help(world, caster, target)
    return dmg


def smite(world, caster, target, ab):
    """Smite: melee with Seal bonus. Returns damage dealt."""
    ab.use()
    caster.swing_timer = caster.weapon_speed
    dmg_amount = smite_damage(caster, ab)     # (a + Seal bonus) x weapon + b
    dmg = target.take_damage(dmg_amount, source=caster)
    world.float_text(target.x, target.y - 20, f"{dmg:.0f}", (255, 255, 255))
    _aggro_and_call_for_help(world, caster, target)
    return dmg
