"""Build a ready-to-run World for one character on one map (pure; no pygame).

Shared by the pygame client (game/session.py) and by pygame-free tools/tests (headless replays,
and later the dedicated/listen server), so both create the world in exactly the same order.
"""
import os

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


def create_world(map_path, char_data, debug=False, autopilot=False, auto_companion=False, hooks=None):
    """Create world + local player (id 0) and spawn the map's monsters and NPCs.

    hooks: optional client callbacks that decorate new entities with art (the sim never draws):
      hero(hero, hero_class_info), monster(m), companion(comp, info), npc(npc, npc_def).
    auto_companion: also summon a companion (Wizard unless that's the hero's class), as --auto does.
    Raises ValueError if the map has no hero start.
    """
    hooks = hooks or {}
    world_map = WorldMap.load(map_path)
    if world_map.hero_start is None:
        raise ValueError(f"Map '{map_path}' has no hero_start spawn point.")
    map_id = map_id_for(map_path)
    hero_wx, hero_wy = world_map.get_start_pos()

    hero_class = HERO_CLASS_BY_NAME[char_data["class_name"]]
    hero = hero_class["create"](char_data["name"].capitalize(), hero_wx, hero_wy)
    if hooks.get("hero"):
        hooks["hero"](hero, hero_class)
    hero.xp = char_data["xp"]
    hero.gold = char_data["gold"]
    hero.kills = char_data["kills"]
    set_hero_level(hero, char_data["level"])  # re-applies per-level stat growth

    # Quest definitions come from data/quests/<map>.json; progress is per character AND per map.
    quests = load_quest_log(map_id)
    quests.load_state(char_data.get("quests", {}).get(map_id))

    game_state = GameState()
    game_state.heroes.append(hero)
    game_state.objective_text = f"Explore {map_id.replace('_', ' ').title()} and clear the area of monsters!"

    world = World(world_map, game_state, hero, quests=quests, debug=debug)
    world.on_monster_spawned = hooks.get("monster")
    world.on_companion_spawned = hooks.get("companion")
    world.on_npc_spawned = hooks.get("npc")

    player = PlayerState(world, hero, ai_enabled=autopilot)
    world.add_player(0, player)   # local player (id 0)

    if auto_companion and world.available_companions:
        info = next((c for c in world.available_companions if c["class"] == "Wizard"), world.available_companions[0])
        world.spawn_companion(info)

    world.spawn_world_map_monsters()
    world.load_npcs()
    return world, player
