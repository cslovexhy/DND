"""Build a ready-to-run World for one character on one map (pure; no pygame).

Shared by the pygame client (game/session.py) and by pygame-free tools/tests (headless replays,
and later the dedicated/listen server), so both create the world in exactly the same order.
"""
import os

from game.content.equipment import empty_equipment, validate_equipment
from game.content.skill_tree import validate_trained
from game.content.heroes import HERO_CLASS_BY_NAME
from game.engine.entities import GameState
from game.engine.player import PlayerState
from game.engine.world import World
from game.engine.world_map import WorldMap
from game.progression import set_hero_level
from game.quests import load_quest_log


def map_id_for(map_path):
    """Key for per-map quest progress."""
    return os.path.splitext(os.path.basename(map_path))[0]


def _make_hero(char_data, map_id, x, y, hooks=None):
    hero_class = HERO_CLASS_BY_NAME[char_data["class_name"]]
    hero = hero_class["create"](char_data["name"].capitalize(), x, y)
    if hooks and hooks.get("hero"):
        hooks["hero"](hero, hero_class)
    hero.xp = char_data["xp"]
    hero.gold = char_data["gold"]
    hero.kills = char_data["kills"]
    try:
        hero.trained = validate_trained(char_data.get("trained"), hero.class_name, char_data["level"])
    except ValueError:
        hero.trained = None                   # a broken save: skills follow the level as they used to
    set_hero_level(hero, char_data["level"])  # re-applies per-level stat growth (and the trained skills)
    try:
        hero.equipment = validate_equipment(char_data.get("equipment"), hero.class_name)
    except ValueError:
        hero.equipment = empty_equipment()    # a hand-edited / broken save: start bare-handed
    hero.refresh_gear()
    # Quest definitions come from data/quests/<map>.json; progress is per character AND per map.
    quests = load_quest_log(map_id)
    quests.load_state(char_data.get("quests", {}).get(map_id))
    return hero, quests


def join_player(world, player_id, char_data, map_path, autopilot=False):
    """Add another player's character to a running world (multiplayer). Returns their PlayerState.
    `char_data` must already be validated (see sanitize_character)."""
    sx, sy = world.world_map.get_start_pos()
    x, y = world.find_walkable_nearby(sx, sy, radius=60)
    hero, quests = _make_hero(char_data, map_id_for(map_path), x, y)
    player = PlayerState(world, hero, ai_enabled=autopilot, quests=quests, name=char_data["name"],
                         inventory=char_data.get("inventory"))
    world.add_player(player_id, player)
    return player


def sanitize_character(data):
    """Validate a character sent by a remote client; returns a clean copy or raises ValueError.
    (Co-op trust model: a client may bring its own progress, but only well-formed values.)"""
    from game.progression import MAX_LEVEL
    if not isinstance(data, dict):
        raise ValueError("character must be an object")
    name = str(data.get("name", "")).strip()[:20] or "player"
    cls = data.get("class_name")
    if cls not in HERO_CLASS_BY_NAME:
        raise ValueError(f"unknown class {cls!r}")
    def num(key, lo, hi):
        v = data.get(key, lo)
        if not isinstance(v, int) or isinstance(v, bool) or not lo <= v <= hi:
            raise ValueError(f"bad {key}")
        return v
    quests = data.get("quests", {})
    if not isinstance(quests, dict):
        raise ValueError("bad quests")
    from game.engine.inventory import Inventory
    inventory = Inventory.from_state(data.get("inventory")).to_state()   # raises ValueError if malformed
    equipment = validate_equipment(data.get("equipment"), cls)            # raises ValueError if malformed
    level = num("level", 1, MAX_LEVEL)
    trained = validate_trained(data.get("trained"), cls, level)           # raises ValueError if malformed
    return {"name": name, "class_name": cls, "level": level,
            "xp": num("xp", 0, 10 ** 9), "gold": num("gold", 0, 10 ** 9), "kills": num("kills", 0, 10 ** 9),
            "quests": quests, "inventory": inventory, "equipment": equipment, "trained": trained}


def create_world(map_path, char_data, debug=False, autopilot=False, auto_companion=False, hooks=None, pp=1):
    """Create world + local player (id 0) and spawn the map's monsters and NPCs.

    hooks: optional client callbacks that decorate new entities with art (the sim never draws):
      hero(hero, hero_class_info), monster(m), companion(comp, info), npc(npc, npc_def).
    auto_companion: also summon a companion (Wizard unless that's the hero's class), as --auto does.
    Raises ValueError if the map has no hero start.
    """
    hooks = hooks or {}
    world_map = WorldMap.load(map_path)   # validated: raises map_schema.MapError (a ValueError) if unusable
    map_id = map_id_for(map_path)
    hero_wx, hero_wy = world_map.get_start_pos()

    hero, quests = _make_hero(char_data, map_id, hero_wx, hero_wy, hooks)

    game_state = GameState()
    game_state.heroes.append(hero)
    game_state.objective_text = f"Explore {map_id.replace('_', ' ').title()} and clear the area of monsters!"

    world = World(world_map, game_state, hero, quests=quests, debug=debug, pp=pp)   # pp: map difficulty 1..8
    world.on_monster_spawned = hooks.get("monster")
    world.on_companion_spawned = hooks.get("companion")
    world.on_npc_spawned = hooks.get("npc")

    player = PlayerState(world, hero, ai_enabled=autopilot, inventory=char_data.get("inventory"))
    world.add_player(0, player)   # local player (id 0)

    if auto_companion and world.available_companions:
        info = next((c for c in world.available_companions if c["class"] == "Wizard"), world.available_companions[0])
        world.spawn_companion(info)

    world.spawn_world_map_monsters()
    world.load_npcs()
    return world, player
