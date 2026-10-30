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
    world.add_player(0, PlayerState(world, hero))
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
        player = world.players[0]
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


class SnapshotTest(unittest.TestCase):
    def test_snapshot_is_json_and_mirrors_world(self):
        import json
        from game import saves
        from game.client.view import ClientView
        from game.engine.bootstrap import create_world
        from game.engine.snapshot import make_snapshot
        random.seed(3)
        world, player = create_world(MAP, saves.blank_character("t", "Wizard"), autopilot=True, auto_companion=True)
        for _ in range(90):
            world.step(1 / 30)
        snap = json.loads(json.dumps(make_snapshot(world)))   # must survive a JSON round trip
        view = ClientView()
        view.apply(snap)
        self.assertEqual((view.hero.x, view.hero.y, view.hero.hp), (world.hero.x, world.hero.y, world.hero.hp))
        self.assertEqual(len(view.monsters), len(world.game_state.monsters))
        self.assertEqual(len(view.companions), len(world.companions))
        self.assertEqual(len(view.npcs), len(world.npcs))
        self.assertEqual(set(view.you.abilities), set(world.hero.abilities))
        # entity views persist across snapshots (so attached sprites survive)
        hero_view = view.hero
        world.step(1 / 30)
        view.apply(make_snapshot(world))
        self.assertIs(view.hero, hero_view)


class MultiplayerSimTest(unittest.TestCase):
    """Two players in one world (pure sim)."""

    def setUp(self):
        from game import saves
        from game.engine.bootstrap import create_world, join_player
        random.seed(5)
        self.world, self.p0 = create_world(MAP, saves.blank_character("ann", "Fighter"))
        self.p1 = join_player(self.world, 1, saves.blank_character("bob", "Wizard"), MAP)

    def test_both_heroes_exist_with_own_ids_and_quests(self):
        w = self.world
        self.assertEqual(len(w.player_heroes), 2)
        self.assertNotEqual(self.p0.hero.eid, self.p1.hero.eid)
        self.assertIsNot(self.p0.quests, self.p1.quests)
        self.assertIn(self.p1.hero, w.game_state.heroes)

    def test_commands_go_to_the_right_player(self):
        from game.engine import commands as C
        w = self.world
        x0, x1 = self.p0.hero.x, self.p1.hero.x
        w.submit(C.MoveTo(x1 + 200, self.p1.hero.y), player_id=1)
        for _ in range(30):
            w.step(1 / 30)
        self.assertEqual(self.p0.hero.x, x0)            # player 0 didn't move
        self.assertGreater(self.p1.hero.x, x1 + 30)     # player 1 walked

    def test_party_kill_credit_and_personal_level_up_events(self):
        from game.engine.events import LevelUp
        w = self.world
        w.spawn_world_map_monsters() if not w.game_state.monsters else None
        m = w.game_state.monsters[0]
        m.take_damage(m.max_hp * 10)
        self.p1.hero.xp = 10 ** 6   # player 1 will level up, player 0 won't
        w.process_kills()
        w.process_level_ups()
        self.assertEqual((self.p0.hero.kills, self.p1.hero.kills), (1, 1))
        ups = [e for e in w.events if isinstance(e, LevelUp)]
        self.assertTrue(ups and all(e.player_id == 1 for e in ups))

    def test_snapshots_are_per_player(self):
        from game.engine.snapshot import make_snapshot
        s0, s1 = make_snapshot(self.world, 0), make_snapshot(self.world, 1)
        self.assertEqual(s0["you"]["hero_id"], self.p0.hero.eid)
        self.assertEqual(s1["you"]["hero_id"], self.p1.hero.eid)
        kinds1 = {e["id"]: e["kind"] for e in s1["entities"]}
        self.assertEqual(kinds1[self.p1.hero.eid], "hero")
        self.assertEqual(kinds1[self.p0.hero.eid], "ally")

    def test_companions_follow_their_owner(self):
        from game.engine import commands as C
        w = self.world
        w.submit(C.ToggleCompanion("Cleric"), player_id=1)
        w.step(1 / 30)
        comp = w.companions[-1][0]
        self.assertIs(comp.owner, self.p1)
        # player 0 toggling Cleric summons their OWN cleric instead of dismissing player 1's
        w.submit(C.ToggleCompanion("Cleric"), player_id=0)
        w.step(1 / 30)
        self.assertEqual(sum(1 for c, _ in w.companions if c.class_name == "Cleric"), 2)

    def test_game_over_only_when_everyone_is_down(self):
        w = self.world
        self.p0.hero.take_damage(10 ** 6)
        w.step(1 / 30)
        self.assertFalse(w.game_state.adventure_failed)
        self.p1.hero.take_damage(10 ** 6)
        w.step(1 / 30)
        self.assertTrue(w.game_state.adventure_failed)

    def test_remove_player(self):
        from game.engine import commands as C
        w = self.world
        w.submit(C.ToggleCompanion("Rogue"), player_id=1)
        w.step(1 / 30)
        w.remove_player(1)
        self.assertEqual(len(w.player_heroes), 1)
        self.assertNotIn(self.p1.hero, w.game_state.heroes)
        self.assertFalse(any(getattr(c, "owner", None) is self.p1 for c, _ in w.companions))

    def test_sanitize_character(self):
        from game.engine.bootstrap import sanitize_character
        ok = sanitize_character({"name": "x" * 50, "class_name": "Rogue", "level": 3, "xp": 5, "gold": 1, "kills": 0})
        self.assertEqual(len(ok["name"]), 20)
        for bad in ({"class_name": "Dragon"}, {"class_name": "Rogue", "level": 999},
                    {"class_name": "Rogue", "gold": -5}, {"class_name": "Rogue", "xp": "lots"}, "nope"):
            with self.assertRaises(ValueError):
                sanitize_character(bad)
