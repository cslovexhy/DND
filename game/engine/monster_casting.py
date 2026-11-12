"""Monsters cast the skills of their kit (pure; no pygame).

A spawn type's "kit" (content/monsters.py, or a map spawn's "stats") lists skills from content/skill_library.py. The
World gives the monster those Abilities at the skill level of its monster level (Ability.set_level) and a mana pool
(World._give_kit), so a monster's skill has the same damage formula (a x its hit damage + b), cooldown and mana cost
as the hero's. Every frame an aggroed monster that is not stunned / frozen and not on its global cooldown tries its
kit in order and casts the first skill that is ready (cooldown over, enough mana) and has a use right now:

    Poison Dagger   in melee with its target, not armed yet, and the target's poison is about to run out
                    (its next melee hit poisons, see abilities.poison_on_hit, called by World.update_monsters)
    Fire Blast      its target is in range (200/230/260 by skill level) and in line of sight
    Renew           the most hurt (HP%) monster near it (itself included) is below 70% and has no Renew yet
    Wall            the most hurt monster near it is below 50% and has no shield

The effects are the same functions heroes use (engine/abilities.py). A skill without a rule here can be given to a
monster but is never cast (yet). tools/skill_playground.py spawns one or two monsters with a kit to try a skill out.
"""
from game.engine import abilities
from game.engine.entities import Condition
from game.engine.events import SkillCast

SUPPORT_RANGE = 300       # px: how far an ally can be for Renew / Wall (heroes use the same, hero_ai.SUPPORT_RANGE)
RENEW_BELOW_PCT = 0.70
WALL_BELOW_PCT = 0.50
POISON_REFRESH_SECS = 1.0  # re-arm Poison Dagger once the target's poison has this little left


def _poison_left(entity):
    return max((c.duration for c in entity.conditions if c.condition == Condition.POISONED), default=0.0)


def _target(m):
    t = getattr(m, "aggro_target", None)
    return t if t is not None and t.alive else None


def _hurt_ally(world, m, below_pct, ok):
    """The living monster near `m` (itself included, others only while aggroed) with the lowest HP% under
    `below_pct` that `ok(ally)` allows, or None."""
    from game.engine.ai import AggroState
    near = [a for a in world.game_state.monsters
            if a.alive and a.max_hp > 0 and m.distance_to(a) <= SUPPORT_RANGE
            and (a is m or a.aggro_state == AggroState.AGGROED)
            and a.hp < a.max_hp * below_pct and ok(a)]
    return min(near, key=lambda a: a.hp / a.max_hp, default=None)


# --- per skill: whom to cast it on right now (None = not now), and how ------------------------------------------

def _pick_poison_dagger(world, m, ab):
    t = _target(m)
    if (t is None or "Poison Dagger" in m.buffs or m.distance_to(t) > m.attack_range + 10
            or _poison_left(t) > POISON_REFRESH_SECS):
        return None
    return m


def _pick_fire_blast(world, m, ab):
    t = _target(m)
    if t is None or not abilities.can_ranged_hit(world, m, t, ab):
        return None
    return t


def _cast_fire_blast(world, m, ab, t):
    abilities.fire_blast(world, m, t, ab)
    m.gcd = m.GCD_DURATION


def _pick_renew(world, m, ab):
    return _hurt_ally(world, m, RENEW_BELOW_PCT, lambda a: "Renew" not in a.buffs)


def _pick_wall(world, m, ab):
    return _hurt_ally(world, m, WALL_BELOW_PCT, lambda a: a.absorb_shield <= 0)


RULES = {
    "Poison Dagger": (_pick_poison_dagger, lambda world, m, ab, t: abilities.poison_dagger(world, m, ab)),
    "Fire Blast": (_pick_fire_blast, _cast_fire_blast),
    "Renew": (_pick_renew, lambda world, m, ab, t: abilities.renew(world, m, t, ab)),
    "Wall": (_pick_wall, lambda world, m, ab, t: abilities.wall(world, m, t, ab)),
}
CASTABLE = tuple(RULES)   # skills a monster can actually use (others in a kit are carried but never cast)


def cast_skills(world, m):
    """One aggroed monster's turn: cast the first skill of its kit that is ready and useful right now (if any)."""
    if m.gcd > 0 or m.has_condition(Condition.STUNNED) or m.has_condition(Condition.FROZEN):
        return None
    for ab in m.abilities.values():
        rule = RULES.get(ab.name)
        if rule is None or not ab.is_ready():
            continue
        pick, cast = rule
        target = pick(world, m, ab)
        if target is None:
            continue
        cast(world, m, ab, target)
        world.events.append(SkillCast(m.eid, ab.name, target.eid))
        return ab.name
    return None
