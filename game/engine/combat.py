"""Who fights whom, and how a hit lands (pure; no pygame). See design/07_skills_and_factions.md.

Every entity has a faction (Entity.faction: "heroes" / "monsters"). Skills ask for enemies / friends of their caster
and never whether something is a hero or a monster.

    enemies_of(world, e)       living, visible entities of another faction
    friends_of(world, e)       living entities of e's faction (e included)
    hit(world, src, tgt, amt)  the one way a skill / projectile deals damage: the source's outgoing multiplier
                               (Entity.damage_mult) and the target's armor, shield and hate table apply in
                               Entity.take_damage; then the target engages its attacker (engage).
"""
from game.engine.ai import AggroState, aggro_monster, call_for_help

HEROES, MONSTERS = "heroes", "monsters"


def hostile(a, b) -> bool:
    fa, fb = getattr(a, "faction", None), getattr(b, "faction", None)
    return fa is not None and fb is not None and fa != fb


def _everyone(world):
    gs = world.game_state
    return gs.heroes + gs.monsters


def enemies_of(world, e, include_stealthed=False):
    """Living entities hostile to `e` (stealthed ones are not valid targets unless asked for)."""
    return [x for x in _everyone(world) if x.alive and hostile(e, x)
            and (include_stealthed or not getattr(x, "stealthed", False))]


def friends_of(world, e):
    """Living entities of `e`'s faction, `e` included."""
    return [x for x in _everyone(world) if x.alive and getattr(x, "faction", None) == e.faction]


def in_combat(world, e) -> bool:
    """`e` is fighting: a monster brain that is aggroed, or anyone an aggroed enemy has as its target / on its hate
    table (out-of-combat-only skills such as Stealth are refused then)."""
    if getattr(e, "aggro_state", None) == AggroState.AGGROED:
        return True
    return any(getattr(x, "aggro_state", None) == AggroState.AGGROED
               and (getattr(x, "aggro_target", None) is e or e in getattr(x, "hate", {}))
               for x in enemies_of(world, e, include_stealthed=True))


def engage(world, target, source):
    """`target` was hit by `source`: if it has an aggro brain (monsters) and `source` is hostile, it fights back and
    calls the friends around it for help."""
    if not hasattr(target, "aggro_state") or not hostile(target, source) or not target.alive:
        return
    monsters = world.game_state.monsters
    if target.aggro_state != AggroState.AGGROED:
        aggro_monster(target, source, monsters)
    call_for_help(target, monsters, source)


def hit(world, source, target, amount, threat=1.0, ignore_armor=False, flash=True):
    """Deal `amount` (before the source's multiplier and the target's armor) to `target`. Returns damage dealt."""
    dealt = target.take_damage(amount, ignore_armor=ignore_armor, source=source, threat=threat, flash=flash)
    if hasattr(source, "since_combat"):
        source.since_combat = 0.0          # a monster that reached someone: its leash timer starts over
    engage(world, target, source)
    return dealt
