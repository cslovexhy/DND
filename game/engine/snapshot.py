"""World -> client snapshots (pure; no pygame).

A snapshot is everything one player's client needs to draw a frame, as plain JSON-able data:
entities (by stable id), projectiles, and that player's private HUD state (abilities, potions,
quests...). The client never reads the World directly (design/06 phase 3); over the network
(phase 4) the host sends these to each client.
"""

SNAPSHOT_VERSION = 1

from game.engine.ai import is_fighting   # noqa: E402  (pure: no pygame)


def _conditions(e):
    return [c.condition.name for c in getattr(e, "conditions", [])]


def _entity(e, kind, ctl=None):
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
        d["say"] = getattr(e, "say", "")
        d["leveled"] = bool(getattr(e, "leveled", False))   # has a real level (map monster_levels): show "Lv N"
    elif kind in ("hero", "ally", "companion"):
        d["class_name"] = e.class_name
        d["mana"], d["max_mana"] = e.mana, e.max_mana
        d["absorb_shield"] = e.absorb_shield
        d["buffs"] = sorted(e.buffs)
        d["chill_visual"] = getattr(e, "chill_visual", 0.0)
        d["weapon_speed"] = e.weapon_speed
        d["xp"], d["gold"], d["kills"] = e.xp, e.gold, e.kills
        # channel-bar progress (0..1) while channelling Frostbolt — everyone sees everyone's cast bar
        d["channel"] = (1.0 - ctl.frostbolt_channel_timer / e.weapon_speed
                        if ctl is not None and ctl.frostbolt_channeling else None)
    return d


def _food(hero):
    """The hero's food state for the HUD: the meal being eaten and the food buff (item, seconds left)."""
    out = {}
    for key, buff in (("eating", hero.buffs.get("Eating")), ("buff", hero.buffs.get("Well Fed"))):
        if buff:
            out[key] = {"item": buff.get("item"), "remaining": buff["remaining"]}
    return out


def quest_info(q):
    """Static description of a quest (for dialogue panels)."""
    return {"quest_id": q.quest_id, "title": q.title, "description": q.description,
            "objectives": [dict(o) for o in q.objectives],
            "rewards_xp": q.rewards_xp, "rewards_gold": q.rewards_gold}


def _quests(player):
    ql = player.quests
    active = [{"title": q.title, "accepted": q.accepted, "turned_in": q.turned_in,
               "has_objectives": bool(q.objectives), "progress_text": q.get_progress_text(),
               "complete": q.is_complete()}
              for q in ql.active_objects()]
    return {"active": active, "any_available": bool(ql.available(player.hero.level)), "has_quests": bool(ql.quests)}


def make_snapshot(world, player_id=0):
    player = world.players[player_id]
    hero = player.hero
    gs = world.game_state
    entities = [_entity(hero, "hero", player)]
    for other in world.player_list:          # every other player's hero: humans are allies, AI players companions
        if other is not player:
            if other.is_companion:
                d = _entity(other.hero, "companion", other)
                d["owner_id"] = other.owner.player_id     # whose companion (the HUD lists only your own)
            else:
                d = _entity(other.hero, "ally", other)
            d["player_name"] = other.name
            entities.append(d)
    entities += [_entity(m, "monster") for m in gs.monsters]
    for n in world.npcs:
        d = _entity(n, "npc")
        d["sprite_tile"] = list(getattr(n, "sprite_tile", None) or ())
        d["turn_in"] = n.has_turn_in(player)
        d["quest_available"] = n.has_available_quest(player)
        entities.append(d)
    projectiles = [{"x": p.x, "y": p.y, "color": list(p.color), "radius": p.radius,
                    "target_id": p.target.eid if p.target is not None else None}
                   for p in world.projectiles]
    fighting = is_fighting(hero, gs.alive_monsters)
    you = {
        "hero_id": hero.eid,
        "potions": player.potions,
        "potion_cooldown": player.potion_cooldown,
        "inventory": player.inventory.to_state(),
        "trade": world.trade_of(player).view(player) if world.trade_of(player) else None,
        "food": _food(hero),
        "ai_enabled": player.ai_enabled,
        "selected_target_id": player.selected_target.eid if player.selected_target is not None else None,
        "target_id": player.target.eid if player.target is not None else None,   # hotbar skills go here
        "move_path": [list(wp) for wp in player.move_path[:8]],
        "frostbolt_channeling": player.frostbolt_channeling,
        "frostbolt_channel_timer": player.frostbolt_channel_timer,
        "abilities": [{"key": k, "name": a.name, "remaining": a.remaining,
                       "ready": a.is_ready() and not (a.out_of_combat_only and fighting),
                       "level": a.level, "max_level": a.max_level, "range": a.range, "cooldown": a.cooldown,
                       "mana_cost": a.mana_cost, "has_mana": a.has_mana()}
                      for k, a in hero.abilities.items()],
        "player_id": player.player_id,
        "quests": _quests(player),
        "progress": {"level": hero.level, "xp": hero.xp, "gold": hero.gold, "kills": hero.kills,
                     "quests": player.quests.to_state(),
                     "inventory": player.inventory.to_state()},   # what this player's machine saves
    }
    ground_items = [{"id": g.item_id, "item": g.item, "x": g.x, "y": g.y} for g in world.ground_items]
    hazards = [{"kind": z.kind, "x": z.x, "y": z.y, "radius": z.radius, "elapsed": z.elapsed,
                "remaining": z.remaining, "duration": z.duration, "cycles": z.cycles, "color": list(z.color)}
               for z in world.hazards]
    return {
        "v": SNAPSHOT_VERSION,
        "tick": world.tick,
        "game_time": gs.game_time,
        "objective_text": gs.objective_text,
        "pp": world.pp,                     # map difficulty, shown to everyone as "Map (Npp)"
        "adventure_failed": gs.adventure_failed,
        "entities": entities,
        "projectiles": projectiles,
        "hazards": hazards,                 # ground zones such as a boss' Deep Breath
        "ground_items": ground_items,       # monster drops anyone can pick up
        "you": you,
    }
