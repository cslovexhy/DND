"""One cast path for every caster (pure; no pygame). See design/07_skills_and_factions.md.

SKILLS[name] is a SkillSpec: how the skill picks and checks its target, its gates, its effect (engine/abilities.py)
and an AI hint (when a brain should use it, and on whom). try_cast(world, caster, ab, target) validates and casts
for any entity — the player's input (engine/player.py) and the monster brain (monster_turn, below) both use it.

Targeting kinds
    enemy    one hostile entity: in ab.range (+ line of sight when `los`)
    sweep    one hostile in ab.range (default: the nearest within ab.radius) + its neighbours (Cleave)
    dash     one hostile in ab.range and line of sight; the caster dashes to it (Charge)
    ally     a friend (the caster when none is given) within SUPPORT_RANGE and line of sight
    nova     everything hostile within ab.radius of the caster (no target to pick)
    self     the caster

A failed cast spends nothing and says why (CastResult.reason): "not ready", "busy", "no target", "out of range",
"no line of sight", "swing", or a gate's message.
"""
from dataclasses import dataclass
from typing import Callable, Optional

from game.engine import abilities as A
from game.engine import combat
from game.engine.entities import Condition
from game.engine.events import SkillCast

SUPPORT_RANGE = 300          # px: how far a friend can be for an ally skill (hero_ai.SUPPORT_RANGE is the same)


@dataclass
class SkillSpec:
    targeting: str                      # enemy / sweep / dash / ally / nova / self
    effect: Callable                    # effect(world, caster, ab, target) -> None | False (could not happen)
    los: bool = False                   # needs line of sight to its target
    swing: bool = False                 # waits for and uses up a weapon swing (weapon attacks, Cleave, Ambush)
    gcd: bool = True                    # starts the global cooldown (weapon attacks don't: they are swing-paced)
    requires_stealth: bool = False      # Ambush
    stops_attack: bool = False          # a player's auto-attack stops (Stealth)
    channel: bool = False               # starts a channel (Frostbolt, Holy Light) or a dash (Charge): not while
                                        # another one runs; instant skills can be cast during a channel
    ai: Optional[Callable] = None       # ai(world, caster, ab) -> target or None: worth casting now? (None: never)


@dataclass
class CastResult:
    ok: bool
    reason: str = ""
    target: object = None


# --- AI hints: is it worth casting now, and on whom? -------------------------------------------------------------

def _current_enemy(world, caster):
    """The enemy the caster is fighting: a monster's aggro target (heroes' brains choose their own)."""
    t = getattr(caster, "aggro_target", None)
    return t if t is not None and t.alive and combat.hostile(caster, t) and not getattr(t, "stealthed", False) else None


def _ai_enemy_in_range(world, caster, ab):
    t = _current_enemy(world, caster)
    if t is None or caster.distance_to(t) > ab.range:
        return None
    return t if world.check_los(caster.x, caster.y, t.x, t.y) else None


def _ai_charge(world, caster, ab):
    t = _ai_enemy_in_range(world, caster, ab)
    return t if t is not None and caster.distance_to(t) > 2 * caster.attack_range else None   # worth a dash


def _ai_sweep(world, caster, ab):
    t = _current_enemy(world, caster)
    if t is None or caster.distance_to(t) > ab.range:
        return None
    near = [e for e in combat.enemies_of(world, caster) if caster.distance_to(e) <= ab.radius]
    return t if len(near) >= 2 else None


def _ai_nova(missing):
    """An AoE around the caster: worth it while an enemy within the radius lacks its effect."""
    def pick(world, caster, ab):
        near = [e for e in combat.enemies_of(world, caster) if caster.distance_to(e) <= ab.radius]
        return caster if any(missing(e) for e in near) else None
    return pick


def _ai_in_melee_buff(buff, extra=lambda world, caster, t: True):
    """A self-buff for the next melee hits: in melee with its enemy and not armed yet."""
    def pick(world, caster, ab):
        t = _current_enemy(world, caster)
        if (t is None or buff in caster.buffs or caster.distance_to(t) > caster.attack_range + 10
                or not extra(world, caster, t)):
            return None
        return caster
    return pick


def _poison_left(e):
    return max((c.duration for c in e.conditions if c.condition == Condition.POISONED), default=0.0)


POISON_REFRESH_SECS = 1.0    # re-arm Poison Dagger once the target's poison has this little left


def _ai_hurt_friend(below_pct, ok):
    """The friend (the caster included) with the lowest HP% under `below_pct` within SUPPORT_RANGE that `ok` allows."""
    def pick(world, caster, ab):
        hurt = [f for f in combat.friends_of(world, caster)
                if f.max_hp > 0 and caster.distance_to(f) <= SUPPORT_RANGE and f.hp < f.max_hp * below_pct and ok(f)
                and (f is caster or getattr(f, "aggro_state", "aggroed") == "aggroed" or f.faction == "heroes")]
        return min(hurt, key=lambda f: f.hp / f.max_hp, default=None)
    return pick


# --- the skills --------------------------------------------------------------------------------------------------

SKILLS = {
    # weapon attacks (a brain uses its own basic attack; no AI hint)
    "Strike": SkillSpec("enemy", A.strike, swing=True, gcd=False),
    "Stab": SkillSpec("enemy", A.stab, swing=True, gcd=False),
    "Smite": SkillSpec("enemy", A.smite, swing=True, gcd=False),
    "Wanding": SkillSpec("enemy", A.wanding, los=True, swing=True, gcd=False),
    "Frostbolt": SkillSpec("enemy", A.frostbolt, los=True, gcd=False, channel=True, ai=_ai_enemy_in_range),
    # damage skills
    "Fire Blast": SkillSpec("enemy", A.fire_blast, los=True, ai=_ai_enemy_in_range),
    "Judgement": SkillSpec("enemy", A.judgement, los=True, ai=_ai_enemy_in_range),
    "Ambush": SkillSpec("enemy", A.ambush, swing=True, requires_stealth=True),
    "Cleave": SkillSpec("sweep", A.cleave, swing=True, ai=_ai_sweep),
    "Charge": SkillSpec("dash", A.charge, los=True, channel=True, ai=_ai_charge),
    "Frost Nova": SkillSpec("nova", A.frost_nova,
                            ai=_ai_nova(lambda e: not e.has_condition(Condition.FROZEN) and not e.immune_freeze)),
    "Demoralizing Shout": SkillSpec("nova", A.demoralizing_shout, ai=_ai_nova(lambda e: "Demoralized" not in e.buffs)),
    # self-buffs
    "Heroic Strike": SkillSpec("self", A.heroic_strike, ai=_ai_in_melee_buff("Heroic Strike")),
    "Righteous Seal": SkillSpec("self", A.righteous_seal, ai=_ai_in_melee_buff("Righteous Seal")),
    "Poison Dagger": SkillSpec("self", A.poison_dagger, ai=_ai_in_melee_buff(
        "Poison Dagger", lambda world, caster, t: _poison_left(t) <= POISON_REFRESH_SECS)),
    "Stealth": SkillSpec("self", A.stealth, stops_attack=True),
    # support
    "Renew": SkillSpec("ally", A.renew, ai=_ai_hurt_friend(0.70, lambda f: "Renew" not in f.buffs)),
    "Wall": SkillSpec("ally", A.wall, ai=_ai_hurt_friend(0.50, lambda f: f.absorb_shield <= 0)),
    "Holy Light": SkillSpec("ally", A.holy_light, channel=True, ai=_ai_hurt_friend(0.60, lambda f: True)),
}
AI_CASTABLE = tuple(n for n, s in SKILLS.items() if s.ai is not None)   # what a monster brain can use from a kit


# --- casting -----------------------------------------------------------------------------------------------------

def _resolve_target(world, caster, ab, spec, target):
    """(target, failure reason) for the skill's targeting kind."""
    kind = spec.targeting
    if kind in ("self", "nova"):
        return caster, ""
    if kind == "ally":
        if target is None or target is caster:
            return caster, ""
        if not target.alive or combat.hostile(caster, target):
            return None, "no target"
        if caster.distance_to(target) > SUPPORT_RANGE or not world.check_los(caster.x, caster.y, target.x, target.y):
            return None, "out of range"
        return target, ""
    # enemy / sweep / dash
    if target is None and kind == "sweep":
        near = [e for e in combat.enemies_of(world, caster) if caster.distance_to(e) <= ab.radius]
        target = min(near, key=caster.distance_to, default=None)
    if target is None or not target.alive or not combat.hostile(caster, target):
        return None, "no target"
    if caster.distance_to(target) > ab.range:
        return target, "out of range"
    if (spec.los or kind == "dash") and not world.check_los(caster.x, caster.y, target.x, target.y):
        return target, "no line of sight"
    return target, ""


def try_cast(world, caster, ab, target=None):
    """Cast `ab` (one of `caster`'s abilities) at `target` if everything allows it. Spends cooldown, mana, the swing
    and the global cooldown only when the cast happens."""
    spec = SKILLS.get(ab.name)
    if spec is None:
        return CastResult(False, "unknown skill")
    if not caster.can_act or caster.gcd > 0 or not ab.is_ready():
        return CastResult(False, "not ready")
    if caster.dash is not None or (spec.channel and caster.channel is not None):
        return CastResult(False, "busy")
    if ab.out_of_combat_only and combat.in_combat(world, caster):
        return CastResult(False, "Can't do that in combat!")
    if spec.requires_stealth and not caster.stealthed:
        return CastResult(False, "Must be stealthed!")
    target, why = _resolve_target(world, caster, ab, spec, target)
    if why:
        return CastResult(False, why, target)
    if spec.swing and caster.swing_timer > 0:
        return CastResult(False, "swing", target)
    if spec.targeting in ("enemy", "sweep", "dash", "nova") and not spec.requires_stealth:
        A.break_stealth(world, caster)            # attacking reveals you (Ambush does it itself)
    if spec.effect(world, caster, ab, target) is False:
        return CastResult(False, "can't reach", target)
    ab.use()                                      # cooldown + mana
    if spec.swing:
        caster.swing_timer = caster.weapon_speed
    if spec.gcd:
        caster.gcd = caster.GCD_DURATION
    world.events.append(SkillCast(caster.eid, ab.name, target.eid if target is not None else caster.eid))
    return CastResult(True, "", target)


def monster_turn(world, m):
    """An aggroed monster's skill use: the first kit skill that is ready and worth casting right now (its AI hint).
    Returns the skill's name, or None."""
    if m.gcd > 0 or m.channel is not None or m.dash is not None or not m.can_act:
        return None
    for ab in m.abilities.values():
        spec = SKILLS.get(ab.name)
        if spec is None or spec.ai is None or not ab.is_ready():
            continue
        target = spec.ai(world, m, ab)
        if target is not None and try_cast(world, m, ab, target).ok:
            return ab.name
    return None
