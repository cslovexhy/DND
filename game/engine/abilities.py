"""Shared ability execution helpers (pure; no pygame).

These are the "do the thing" functions used by the player's cast logic, the companion AI and monsters
(engine/monster_casting.py): the caster may be a hero or a monster. Validation (range, LOS, cooldown, mana) is done
by the caller. Visuals are reported as World events.
"""
import random

from game.content.skill_tree import (judgement_seal_bonus, smite_damage, poison_dps, wall_shield, renew_total,
                                     POISON_DAGGER_SECS, POISON_DAGGER_WINDOW)
from game.engine.ai import aggro_monster, call_for_help
from game.engine.entities import Condition, Projectile
from game.engine.events import Ring, FloatText

WALL_SECS = 15.0    # how long a Wall shield lasts
RENEW_SECS = 8.0    # Renew heals its total over this long


def _aggro_and_call_for_help(world, caster, target):
    """A hero hit a monster: it (and its friends nearby) fight back. Nothing to do when a monster hits a hero."""
    if target not in world.game_state.monsters:
        return
    if hasattr(target, 'aggro_state') and target.aggro_state != "aggroed":
        aggro_monster(target, caster, world.game_state.monsters)
    call_for_help(target, world.game_state.monsters, caster)


def _power(caster):
    """Multiplier on a skill's flat amounts (poison, heals, shields): 1 for heroes; a monster's map-difficulty damage
    factor (World._apply_pp), the same factor its hits get."""
    return getattr(caster, "skill_power", 1.0)


# --- self-buffs / support (any caster: hero or monster) ---------------------------------------------------------

def poison_dagger(world, caster, ab):
    """Poison Dagger: arm the caster's next melee hit (a Rogue's Stab, a monster's attack) to poison its target."""
    ab.use()
    caster.buffs["Poison Dagger"] = {"remaining": POISON_DAGGER_WINDOW, "dps": poison_dps(ab) * _power(caster),
                                     "duration": POISON_DAGGER_SECS}
    world.float_text(caster.x, caster.y - 30, "Poison Dagger!", (120, 220, 80))
    caster.gcd = caster.GCD_DURATION


def poison_on_hit(world, caster, target):
    """A melee hit landed: if the caster's Poison Dagger is armed, it is spent and the target is poisoned (damage over
    time that ignores armor and counts as the caster's damage)."""
    poison = caster.buffs.pop("Poison Dagger", None)
    if poison and target.alive:
        if target.apply_condition(Condition.POISONED, poison["duration"], tick_damage=poison["dps"],
                                  source="Poison Dagger", by=caster):
            world.float_text(target.x, target.y - 35, "Poisoned!", (120, 220, 80))


def wall(world, caster, target, ab):
    """Wall: an absorb shield on `target` (the caster or an ally) for 15 s. Returns the shield amount."""
    ab.use()
    amount = wall_shield(caster, ab) * _power(caster)
    target.absorb_shield = amount
    target.buffs["Wall"] = {"remaining": WALL_SECS}
    world.credit_heal(caster, target, amount)        # shielding generates hate like healing (heroes only)
    world.float_text(target.x, target.y - 30, f"Wall +{amount:.0f}!", (255, 215, 60))
    caster.gcd = caster.GCD_DURATION
    return amount


def renew(world, caster, target, ab):
    """Renew: heal `target` (the caster or an ally) over RENEW_SECS."""
    ab.use()
    total = renew_total(caster, ab) * _power(caster)
    target.buffs["Renew"] = {"remaining": RENEW_SECS, "hot_per_sec": total / RENEW_SECS,
                             "source": caster}       # each tick's healing is credited to the caster's hate
    world.credit_heal(caster, target, 0)             # in combat with the friend -> on the mobs' tables now
    world.float_text(target.x, target.y - 30, "Renew!", (100, 255, 150))
    caster.gcd = caster.GCD_DURATION


def can_ranged_hit(world, caster, target, ab):
    """Check if a ranged ability can hit: in range + line of sight."""
    if caster.distance_to(target) > ab.range:
        return False
    return world.check_los(caster.x, caster.y, target.x, target.y)


def fire_blast(world, caster, target, ab):
    """Fire Blast: instant ranged nuke. Returns damage dealt."""
    ab.use()
    dmg_amount = ab.calc_damage(caster.base_damage)
    dmg = target.take_damage(dmg_amount, source=caster, threat=ab.threat_mult)
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
                      color=color, source=caster, threat=ab.threat_mult)
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
    dmg = target.take_damage(total_damage, source=caster, threat=ab.threat_mult)
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
    dmg = target.take_damage(dmg_amount, source=caster, threat=ab.threat_mult)
    world.float_text(target.x, target.y - 20, f"{dmg:.0f}", (180, 255, 180))
    _aggro_and_call_for_help(world, caster, target)
    return dmg


def smite(world, caster, target, ab):
    """Smite: melee with Seal bonus. Returns damage dealt."""
    ab.use()
    caster.swing_timer = caster.weapon_speed
    dmg_amount = smite_damage(caster, ab)     # (a + Seal bonus) x weapon + b
    dmg = target.take_damage(dmg_amount, source=caster, threat=ab.threat_mult)
    world.float_text(target.x, target.y - 20, f"{dmg:.0f}", (255, 255, 255))
    _aggro_and_call_for_help(world, caster, target)
    return dmg
