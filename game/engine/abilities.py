"""What every skill does (pure; no pygame). See design/07_skills_and_factions.md.

One function per skill effect: effect(world, caster, ab, target). The caster may be any entity (hero or monster);
enemies and friends are found by faction (engine/combat.py), damage goes through combat.hit (the caster's damage
multiplier, the target's armor / shield / hate, and the target fighting back). Validation (range, line of sight,
cooldown, mana, gates) and the bookkeeping that follows a cast (cooldown, mana, swing, global cooldown) are done by
engine/casting.py. An effect returns False if it could not happen after all (a Charge with no walking path); then
nothing is spent.
"""
import random

from game.content.skill_tree import (judgement_seal_bonus, smite_damage, poison_dps, wall_shield, renew_total,
                                     holy_light_heal, seal_bonus, shout_damage_mult, stealth_speed,
                                     POISON_DAGGER_SECS, POISON_DAGGER_WINDOW)
from game.engine import actions, combat
from game.engine.entities import Condition, Projectile
from game.engine.events import Ring, FloatText, GOLD

WALL_SECS = 15.0             # how long a Wall shield lasts
RENEW_SECS = 8.0             # Renew heals its total over this long
HOLY_LIGHT_SECS = 2.0        # Holy Light channel
SEAL_SECS = 10.0             # Righteous Seal
HEROIC_STRIKE_WINDOW = 10.0  # seconds a Heroic Strike buff waits for the next Strike / Cleave / melee hit
SHOUT_SECS = 10.0            # Demoralized
SHOUT_SLOW_SECS = 3.0
FROST_NOVA_FREEZE_SECS = 4.0
FROSTBOLT_SLOW_SECS = 3.0
FROSTBOLT_SLOW = 0.25
CHARGE_STOP_SHORT = 50.0     # a Charge ends this far in front of its target
PROJECTILE_SPEED = 500.0


def _text(world, e, text, color, dy=30):
    world.float_text(e.x, e.y - dy, text, color)


def _power(caster):
    """Multiplier on a skill's flat amounts (poison, heals, shields): 1 for heroes; a monster's map-difficulty damage
    factor (World._apply_pp), the same factor its hits get."""
    return getattr(caster, "skill_power", 1.0)


def bind_right(world, caster, key):
    """Ask the caster's player client (if it has one) to switch its right-click skill."""
    player = world.player_for_hero(caster)
    if player is not None:
        player._bind_right(key)


def break_stealth(world, caster, quiet=False):
    if getattr(caster, "stealthed", False):
        caster.stealthed = False
        if not quiet:
            _text(world, caster, "Stealth broken!", (200, 200, 200), 40)
        bind_right(world, caster, "R")


def _heroic(caster, ab):
    """(bonus damage, threat factor) of an armed Heroic Strike, spent by this heroic attack (Strike, Cleave)."""
    hs = caster.buffs.pop("Heroic Strike", None) if ab.heroic else None
    return (hs["bonus"], hs["threat"]) if hs else (0.0, 1.0)


def _projectile(world, caster, target, ab, damage, color, slow=False):
    proj = Projectile(x=caster.x, y=caster.y, target=target, speed=PROJECTILE_SPEED, damage=damage,
                      color=color, source=caster, threat=ab.threat_mult)
    proj.apply_slow = slow
    world.projectiles.append(proj)
    return proj


def can_ranged_hit(world, caster, target, ab):
    """In range and in line of sight."""
    if caster.distance_to(target) > ab.range:
        return False
    return world.check_los(caster.x, caster.y, target.x, target.y)


# --- weapon attacks -----------------------------------------------------------------------------------------------

def strike(world, caster, ab, target):
    """Strike (and any plain weapon skill): a x weapon + b, plus an armed Heroic Strike."""
    bonus, threat = _heroic(caster, ab)
    dmg = combat.hit(world, caster, target, ab.calc_damage(caster.base_damage) + bonus,
                     threat=ab.threat_mult * threat)
    _text(world, target, f"{dmg:.0f}", (255, 255, 255), 20)
    poison_on_hit(world, caster, target)


def stab(world, caster, ab, target):
    """Stab: fast melee strike that can crit."""
    amount = ab.calc_damage(caster.base_damage)
    caster.last_crit = random.random() < caster.crit_chance
    if caster.last_crit:
        amount *= caster.crit_multiplier
    dmg = combat.hit(world, caster, target, amount, threat=ab.threat_mult)
    _text(world, target, f"{dmg:.0f}!" if caster.last_crit else f"{dmg:.0f}",
          (255, 255, 50) if caster.last_crit else (180, 255, 180), 20)
    poison_on_hit(world, caster, target)


def smite(world, caster, ab, target):
    """Smite: (a + Righteous Seal bonus) x weapon + b."""
    sealed = "Righteous Seal" in caster.buffs
    dmg = combat.hit(world, caster, target, smite_damage(caster, ab), threat=ab.threat_mult)
    _text(world, target, f"{dmg:.0f}", (255, 230, 100) if sealed else (255, 255, 255), 20)
    poison_on_hit(world, caster, target)


def wanding(world, caster, ab, target):
    """Wanding: a homing bolt (damage on arrival)."""
    _projectile(world, caster, target, ab, ab.calc_damage(caster.base_damage), (255, 220, 100))


def cleave(world, caster, ab, target):
    """Cleave: the target and the nearest enemies within `radius` of the caster, `max_targets` in total."""
    near = [e for e in combat.enemies_of(world, caster) if caster.distance_to(e) <= ab.radius and e is not target]
    near.sort(key=caster.distance_to)
    victims = [target] + near[:ab.max_targets - 1] if ab.max_targets else [target] + near
    bonus, threat = _heroic(caster, ab)
    base = ab.calc_damage(caster.base_damage)
    dealt = [combat.hit(world, caster, v, base + (bonus if i == 0 else 0.0),
                        threat=ab.threat_mult * (threat if i == 0 else 1.0)) for i, v in enumerate(victims)]
    world.events.append(Ring(caster.x, caster.y, ab.radius, ab.color))
    _text(world, target, " ".join(f"{d:.0f}" for d in dealt), GOLD, 20)


# --- damage spells ------------------------------------------------------------------------------------------------

def fire_blast(world, caster, ab, target):
    """Fire Blast: instant ranged nuke."""
    dmg = combat.hit(world, caster, target, ab.calc_damage(caster.base_damage), threat=ab.threat_mult)
    _text(world, target, f"{dmg:.0f}", (255, 130, 50), 20)
    world.events.append(Ring(target.x, target.y, 30, (255, 100, 0)))
    return dmg


def judgement(world, caster, ab, target):
    """Judgement: ranged holy damage; consumes the caster's Righteous Seal for extra damage."""
    total = ab.calc_damage(caster.base_damage)
    if caster.buffs.pop("Righteous Seal", None) is not None:
        total += judgement_seal_bonus(caster, ab)
        _text(world, target, "Seal Consumed!", (255, 200, 50), 40)
    dmg = combat.hit(world, caster, target, total, threat=ab.threat_mult)
    _text(world, target, f"{dmg:.0f}", (255, 255, 150), 20)
    return dmg


def frostbolt(world, caster, ab, target):
    """Frostbolt: channel for one weapon swing (immobile), then a slowing bolt."""
    def release(world, caster, target):
        if target is not None and target.alive:
            _projectile(world, caster, target, ab, ab.calc_damage(caster.base_damage), (150, 200, 255), slow=True)
    actions.start_channel(world, caster, "Frostbolt", caster.weapon_speed, target, release)


def ambush(world, caster, ab, target):
    """Ambush: from stealth, a huge hit (breaks stealth)."""
    break_stealth(world, caster, quiet=True)
    dmg = combat.hit(world, caster, target, ab.calc_damage(caster.base_damage), threat=ab.threat_mult)
    _text(world, target, f"{dmg:.0f}", (255, 50, 50), 20)
    _text(world, target, "AMBUSH!", (255, 50, 50), 40)
    world.events.append(Ring(target.x, target.y, 40, (255, 50, 50)))


def charge(world, caster, ab, target):
    """Charge: dash (along a walking path) to just in front of the target, then hit and stun it."""
    dx, dy = target.x - caster.x, target.y - caster.y
    d = (dx * dx + dy * dy) ** 0.5
    if d <= 0:
        return False
    damage = ab.calc_damage(caster.base_damage)

    def arrive(world, caster, target):
        dmg = combat.hit(world, caster, target, damage, threat=ab.threat_mult)
        _text(world, target, f"{dmg:.0f}", (255, 200, 50), 20)
        if ab.stun_duration > 0 and target.alive:
            stunned = target.apply_condition(Condition.STUNNED, ab.stun_duration)
            _text(world, target, "STUNNED" if stunned else "IMMUNE", (255, 255, 100), 35)

    stop = min(CHARGE_STOP_SHORT, d)
    return actions.start_dash(world, caster, target.x - dx / d * stop, target.y - dy / d * stop, target, arrive)


# --- area effects around the caster ----------------------------------------------------------------------------

def _enemies_around(world, caster, radius):
    return [e for e in combat.enemies_of(world, caster) if caster.distance_to(e) <= radius]


def frost_nova(world, caster, ab, target):
    """Frost Nova: damage and a 4 s freeze on every enemy within `radius`."""
    victims = _enemies_around(world, caster, ab.radius)
    amount = ab.calc_damage(caster.base_damage)
    for v in victims:
        dmg = combat.hit(world, caster, v, amount, threat=ab.threat_mult)
        frozen = v.apply_condition(Condition.FROZEN, FROST_NOVA_FREEZE_SECS)
        _text(world, v, f"{dmg:.0f}", (180, 220, 255), 20)
        _text(world, v, "FROZEN" if frozen else "IMMUNE", (150, 220, 255), 35)
    world.events.append(Ring(caster.x, caster.y, ab.radius, (150, 200, 255)))
    if not victims:
        _text(world, caster, "No enemies in range!", (200, 200, 200))


def demoralizing_shout(world, caster, ab, target):
    """Demoralizing Shout: every enemy within `radius` deals less damage for 10 s and is slowed for 3 s."""
    victims = _enemies_around(world, caster, ab.radius)
    for v in victims:
        v.buffs["Demoralized"] = {"remaining": SHOUT_SECS, "damage_mult": shout_damage_mult(ab)}
        v.apply_condition(Condition.SLOWED, SHOUT_SLOW_SECS, slow_factor=0.5)
        combat.engage(world, v, caster)
        _text(world, v, "Demoralized!", (200, 150, 50), 20)
    if victims:
        world.events.append(Ring(caster.x, caster.y, ab.radius, ab.color))


# --- self-buffs ---------------------------------------------------------------------------------------------------

def heroic_strike(world, caster, ab, target):
    """Heroic Strike: the next heroic attack (Strike, Cleave; a monster's next melee hit) gets +b and more threat."""
    caster.buffs["Heroic Strike"] = {"remaining": HEROIC_STRIKE_WINDOW, "bonus": ab.flat_bonus * _power(caster),
                                     "threat": ab.threat_mult}
    _text(world, caster, "Heroic Strike!", (255, 160, 80))


def righteous_seal(world, caster, ab, target):
    """Righteous Seal: +a x weapon on Smite (a monster's melee hits) for 10 s; Judgement consumes it."""
    caster.buffs["Righteous Seal"] = {"remaining": SEAL_SECS, "bonus": seal_bonus(ab)}
    _text(world, caster, "Seal Active!", (255, 220, 80))


def poison_dagger(world, caster, ab, target=None):
    """Poison Dagger: arm the caster's next melee hit (a Rogue's Stab, a monster's attack) to poison its target."""
    caster.buffs["Poison Dagger"] = {"remaining": POISON_DAGGER_WINDOW, "dps": poison_dps(ab) * _power(caster),
                                     "duration": POISON_DAGGER_SECS}
    _text(world, caster, "Poison Dagger!", (120, 220, 80))


def poison_on_hit(world, caster, target):
    """A melee hit landed: an armed Poison Dagger is spent and the target is poisoned (damage over time that ignores
    armor and counts as the caster's damage)."""
    poison = caster.buffs.pop("Poison Dagger", None)
    if poison and target.alive:
        if target.apply_condition(Condition.POISONED, poison["duration"], tick_damage=poison["dps"],
                                  source="Poison Dagger", by=caster):
            _text(world, target, "Poisoned!", (120, 220, 80), 35)


def stealth(world, caster, ab, target):
    """Stealth: invisible to enemies; moves at the level's speed; costs mana per second (engine/player.py)."""
    caster.stealthed = True
    caster.stealth_speed = stealth_speed(ab)
    bind_right(world, caster, "E")
    _text(world, caster, "Stealth!", (100, 200, 100))


# --- support (on a friend, the caster included) ------------------------------------------------------------------

def wall(world, caster, ab, target):
    """Wall: an absorb shield on `target` for 15 s. Returns the shield amount."""
    amount = wall_shield(caster, ab) * _power(caster)
    target.absorb_shield = amount
    target.buffs["Wall"] = {"remaining": WALL_SECS}
    world.credit_heal(caster, target, amount)        # shielding a hero generates hate like healing
    _text(world, target, f"Wall +{amount:.0f}!", (255, 215, 60))
    return amount


def renew(world, caster, ab, target):
    """Renew: heal `target` over RENEW_SECS."""
    total = renew_total(caster, ab) * _power(caster)
    target.buffs["Renew"] = {"remaining": RENEW_SECS, "hot_per_sec": total / RENEW_SECS,
                             "source": caster}       # each tick's healing is credited to the caster's hate
    world.credit_heal(caster, target, 0)             # in combat with the friend -> on the mobs' tables now
    _text(world, target, "Renew!", (100, 255, 150))


def holy_light(world, caster, ab, target):
    """Holy Light: channel 2 s (immobile), then heal the friend (the caster if the friend is gone)."""
    amount = holy_light_heal(ab) * _power(caster)

    def land(world, caster, target):
        if target is None or not target.alive or combat.hostile(caster, target):
            target = caster
        healed = target.heal(amount)
        world.credit_heal(caster, target, healed)
        _text(world, target, f"+{healed:.0f} HP", (100, 255, 100))

    actions.start_channel(world, caster, "Holy Light", HOLY_LIGHT_SECS, target, land, needs_target=False)
    _text(world, caster, "Casting...", (255, 255, 150))
