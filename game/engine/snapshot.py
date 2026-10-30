"""World -> client snapshots (pure; no pygame).

A snapshot is everything one player's client needs to draw a frame, as plain JSON-able data:
entities (by stable id), projectiles, and that player's private HUD state (abilities, potions,
quests...). The client never reads the World directly (design/06 phase 3); over the network
(phase 4) the host sends these to each client.
"""

SNAPSHOT_VERSION = 1


def _conditions(e):
    return [c.condition.name for c in getattr(e, "conditions", [])]


def _entity(e, kind):
    d = {
        "id": e.eid, "kind": kind, "name": e.name,
        "x": e.x, "y": e.y, "hp": e.hp, "max_hp": e.max_hp, "alive": e.alive,
        "facing_left": e.facing_left, "flash_timer": getattr(e, "flash_timer", 0.0),
        "stealthed": bool(getattr(e, "stealthed", False)), "level": getattr(e, "level", 1),
        "conditions": _conditions(e),
    }
    if kind == "monster":
        d["is_boss"] = bool(e.is_boss)
        d["unique"] = bool(getattr(e, "unique", False))
    elif kind in ("hero", "companion"):
        d["class_name"] = e.class_name
        d["absorb_shield"] = e.absorb_shield
        d["buffs"] = sorted(e.buffs)
        d["chill_visual"] = getattr(e, "chill_visual", 0.0)
        d["weapon_speed"] = e.weapon_speed
        d["xp"], d["gold"], d["kills"] = e.xp, e.gold, e.kills
    return d


def quest_info(q):
    """Static description of a quest (for dialogue panels)."""
    return {"quest_id": q.quest_id, "title": q.title, "description": q.description,
            "objectives": [dict(o) for o in q.objectives],
            "rewards_xp": q.rewards_xp, "rewards_gold": q.rewards_gold}


def _quests(world):
    ql = world.quests
    active = [{"title": q.title, "accepted": q.accepted, "turned_in": q.turned_in,
               "has_objectives": bool(q.objectives), "progress_text": q.get_progress_text(),
               "complete": q.is_complete()}
              for q in ql.active_objects()]
    return {"active": active, "any_available": bool(ql.available(world.hero.level)), "has_quests": bool(ql.quests)}


def make_snapshot(world, player_id=0):
    player = world.players[player_id]
    hero = player.hero
    gs = world.game_state
    entities = [_entity(hero, "hero")]
    entities += [_entity(c, "companion") for c, _ in world.companions]
    entities += [_entity(m, "monster") for m in gs.monsters]
    for n in world.npcs:
        d = _entity(n, "npc")
        d["sprite_tile"] = list(getattr(n, "sprite_tile", None) or ())
        d["turn_in"] = n.has_turn_in()
        d["quest_available"] = n.has_available_quest()
        entities.append(d)
    projectiles = [{"x": p.x, "y": p.y, "color": list(p.color), "radius": p.radius,
                    "target_id": p.target.eid if p.target is not None else None}
                   for p in world.projectiles]
    you = {
        "hero_id": hero.eid,
        "potions": player.potions,
        "ai_enabled": player.ai_enabled,
        "selected_target_id": player.selected_target.eid if player.selected_target is not None else None,
        "move_path": [list(wp) for wp in player.move_path[:8]],
        "frostbolt_channeling": player.frostbolt_channeling,
        "frostbolt_channel_timer": player.frostbolt_channel_timer,
        "abilities": [{"key": k, "name": a.name, "remaining": a.remaining, "ready": a.is_ready()}
                      for k, a in hero.abilities.items()],
        "quests": _quests(world),
    }
    return {
        "v": SNAPSHOT_VERSION,
        "tick": world.tick,
        "game_time": gs.game_time,
        "objective_text": gs.objective_text,
        "adventure_failed": gs.adventure_failed,
        "entities": entities,
        "projectiles": projectiles,
        "you": you,
    }
