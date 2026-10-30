"""Unit tests for the pygame-free simulation layer (engine/world.py, engine/player.py)."""
import random
import sys
import unittest

from game.content.heroes import HERO_CLASS_BY_NAME
from game.content.monsters import SPAWN_STATS
from game.engine.entities import GameState
from game.engine.events import FloatText, LevelUp, NpcDialogue
from game.engine.player import PlayerState
from game.engine.world import World
from game.engine.world_map import WorldMap
from game.quests import load_quest_log

MAP = "data/maps/northshire.json"


def make_world(hero_class="Fighter"):
    random.seed(1)
    wm = WorldMap.load(MAP)
    wx, wy = wm.get_start_pos()
    hero = HERO_CLASS_BY_NAME[hero_class]["create"]("Tester", wx, wy)
    gs = GameState()
    gs.heroes.append(hero)
    world = World(wm, gs, hero, quests=load_quest_log("northshire"))
    return world, hero, gs


class WorldTest(unittest.TestCase):
    def test_sim_runs_without_pygame(self):
        self.assertNotIn("pygame", sys.modules)

    def test_spawns_monsters_from_map(self):
        world, hero, gs = make_world()
        world.spawn_world_map_monsters()
        known = [sp for sp in world.world_map.get_monster_spawns() if sp.type in SPAWN_STATS]  # unknown types are skipped
        self.assertEqual(len(gs.monsters), len(known))
        self.assertGreater(len(known), 0)
        self.assertTrue(all(m.alive for m in gs.monsters))

    def test_kill_awards_xp_and_respawns_after_delay(self):
        world, hero, gs = make_world()
        world.spawn_world_map_monsters()
        n = len(gs.monsters)
        m = gs.monsters[0]
        xp = m.experience
        m.take_damage(m.max_hp * 10)
        self.assertFalse(m.alive)
        world.process_kills()
        self.assertEqual(hero.kills, 1)
        self.assertGreaterEqual(hero.xp + (hero.level - 1) * 1000, xp - 0)  # xp granted (may have levelled)
        self.assertTrue(any(isinstance(e, FloatText) and "xp" in e.text for e in world.events))
        # not yet due
        world.process_respawns()
        self.assertEqual(len(gs.monsters), n)
        gs.game_time += 10000
        world.process_respawns()
        self.assertEqual(len(gs.monsters), n + 1)

    def test_level_up_emits_event(self):
        world, hero, gs = make_world()
        hero.xp = 10 ** 6
        world.process_level_ups()
        self.assertGreater(hero.level, 1)
        self.assertTrue(any(isinstance(e, LevelUp) for e in world.events))

    def test_player_state_defaults_and_potion_free_cast_no_target(self):
        world, hero, gs = make_world("Fighter")
        player = PlayerState(world, hero)
        self.assertEqual(player.potions, 3)
        key, ab = next(iter(hero.abilities.items()))
        player.cast_ability(key, ab, hero.x, hero.y, None)   # single-target skill with no target must not crash
        self.assertEqual(player.move_path, [])

    def test_npc_quest_offer_and_accept(self):
        world, hero, gs = make_world()
        world.load_npcs()
        self.assertTrue(world.npcs)
        npc = next((n for n in world.npcs if n.has_available_quest()), None)
        self.assertIsNotNone(npc, "northshire should have an NPC with a level-1 quest")
        self.assertTrue(npc.is_in_range(npc.x, npc.y))
        self.assertTrue(world.interact_with_npc(npc))
        dialogues = [e for e in world.events if isinstance(e, NpcDialogue)]
        self.assertEqual(len(dialogues), 1)
        self.assertIn(dialogues[0].mode, ("accept", "turnin"))
        # a second conversation does not offer the same quest again
        world.events.clear()
        world.interact_with_npc(npc)
        self.assertFalse(any(e.quest is dialogues[0].quest and e.mode == "accept"
                             for e in world.events if isinstance(e, NpcDialogue)))


if __name__ == "__main__":
    unittest.main()
