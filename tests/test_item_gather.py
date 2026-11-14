"""Items to gather from the map (the map's "item_spawns"): a 2 s channel that moving or being hit cancels, shared by
everyone, gone until its respawn timer runs out."""
import random
import tempfile
import unittest

from game import saves
from game.engine import commands as C
from game.engine.bootstrap import create_world
from game.engine.inventory import SIZE
from game.engine.map_schema import validate_map
from game.engine.snapshot import make_snapshot
from game.engine.world import ItemNode
from tests import item_ids as I

MAP = "data/maps/northshire.json"
DT = 1 / 30
saves.SAVE_DIR = tempfile.mkdtemp()


def setup(respawn=60.0, dist=20, count=1):
    random.seed(1)
    world, p = create_world(MAP, saves.blank_character("t", "Fighter"))
    world.game_state.monsters.clear()                    # nobody attacks while we test
    h = p.hero
    dx, dy = next((dx, dy) for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))     # a direction that is open ground
                  if not any(world.is_wall(h.x + dx * d, h.y + dy * d) for d in range(0, dist + 1, 10)))
    node = ItemNode(1, I.BREAD, count, h.x + dx * dist, h.y + dy * dist, respawn)
    world.item_nodes.append(node)
    return world, p, h, node


def run(world, secs):
    for _ in range(int(secs / DT)):
        world.step(DT)


class GatherTest(unittest.TestCase):
    def test_two_second_channel_then_the_item_is_yours(self):
        world, p, h, node = setup()
        world.submit(C.Gather(1), 0)
        run(world, 0.1)
        self.assertEqual(h.channel.skill, "Gather")
        self.assertAlmostEqual(h.channel.total, 2.0)
        self.assertEqual(p.inventory.count(I.BREAD), 0)
        self.assertTrue(node.available)
        run(world, 1.7)
        self.assertEqual(p.inventory.count(I.BREAD), 0)             # not yet
        run(world, 0.4)
        self.assertEqual(p.inventory.count(I.BREAD), 1)
        self.assertFalse(node.available)
        self.assertIsNone(h.channel)
        self.assertEqual(make_snapshot(world)["item_nodes"], [])    # gone for everyone

    def test_it_comes_back_after_its_respawn_time(self):
        world, p, h, node = setup(respawn=10.0)
        world.submit(C.Gather(1), 0)
        run(world, 2.3)
        self.assertEqual(make_snapshot(world)["item_nodes"], [])
        run(world, 9.0)
        self.assertFalse(node.available)
        run(world, 1.5)
        self.assertTrue(node.available)
        snap = make_snapshot(world)["item_nodes"]
        self.assertEqual([(n["id"], n["item"]) for n in snap], [(1, I.BREAD)])
        world.submit(C.Gather(1), 0)                                # and can be gathered again
        run(world, 2.3)
        self.assertEqual(p.inventory.count(I.BREAD), 2)

    def test_count_is_how_many_you_get(self):
        world, p, h, node = setup(count=3)
        world.submit(C.Gather(1), 0)
        run(world, 2.3)
        self.assertEqual(p.inventory.count(I.BREAD), 3)

    def test_walks_there_first(self):
        world, p, h, node = setup(dist=150)
        world.submit(C.Gather(1), 0)
        run(world, 0.2)
        self.assertIsNone(h.channel)
        run(world, 4.5)                                              # ~2 s of walking + the 2 s channel
        self.assertEqual(p.inventory.count(I.BREAD), 1)

    def test_moving_cancels_it(self):
        world, p, h, node = setup()
        world.submit(C.Gather(1), 0)
        run(world, 1.0)
        self.assertIsNotNone(h.channel)
        world.submit(C.MoveTo(h.x + 100, h.y), 0)
        run(world, 0.1)
        self.assertIsNone(h.channel)
        run(world, 3.0)
        self.assertEqual(p.inventory.count(I.BREAD), 0)
        self.assertTrue(node.available)

    def test_walking_with_the_keyboard_cancels_it_too(self):
        world, p, h, node = setup()
        world.submit(C.Gather(1), 0)
        run(world, 0.5)
        world.submit(C.MoveDir(1, 0), 0)
        run(world, 0.1)
        self.assertIsNone(h.channel)

    def test_being_attacked_cancels_it(self):
        world, p, h, node = setup()
        monster = None
        random.seed(1)
        w2, p2 = create_world(MAP, saves.blank_character("t", "Fighter"))
        monster = w2.game_state.monsters[0]
        world.submit(C.Gather(1), 0)
        run(world, 1.0)
        self.assertIsNotNone(h.channel)
        h.take_damage(5, source=monster)
        self.assertIsNone(h.channel)
        run(world, 3.0)
        self.assertEqual(p.inventory.count(I.BREAD), 0)
        self.assertTrue(node.available)
        self.assertFalse(h.has_condition(__import__("game.engine.entities", fromlist=["Condition"]).Condition.IMMOBILIZED))

    def test_a_full_backpack_just_does_nothing(self):
        world, p, h, node = setup()
        others = [i for i in range(1, 25) if i != I.BREAD]
        for i in range(SIZE):
            p.inventory.slots[i] = {"item": others[i % len(others)], "count": 1}
        self.assertFalse(p.inventory.can_add(I.BREAD))
        texts = len(world.floating_texts) if hasattr(world, "floating_texts") else None
        world.submit(C.Gather(1), 0)
        run(world, 0.2)
        self.assertIsNone(h.channel)                             # no channel, no message: nothing happens
        self.assertTrue(node.available)
        self.assertIsNone(p.gather_target)
        if texts is not None:
            self.assertEqual(len(world.floating_texts), texts)

    def test_someone_else_took_it_meanwhile(self):
        world, p, h, node = setup()
        world.submit(C.Gather(1), 0)
        run(world, 1.0)
        node.available, node.timer = False, 30.0               # another player's channel finished first
        run(world, 1.5)
        self.assertEqual(p.inventory.count(I.BREAD), 0)

    def test_nodes_come_from_the_maps_item_spawns(self):
        random.seed(1)
        world, p = create_world(MAP, saves.blank_character("t", "Fighter"))
        world.item_nodes.clear()
        world.world_map.data["item_spawns"] = [{"item": I.WATER, "x": 30, "y": 30, "respawn": 5, "count": 2},
                                               {"item": 99999, "x": 31, "y": 30}]
        world.load_item_nodes()
        self.assertEqual([(n.item, n.count, n.respawn) for n in world.item_nodes], [(I.WATER, 2, 5.0)])   # deleted item skipped


class MapSchemaTest(unittest.TestCase):
    def test_item_spawns_are_validated(self):
        import json
        with open(MAP) as f:
            data = json.load(f)
        data["item_spawns"] = [{"item": 8, "x": 3, "y": 4, "respawn": 30, "count": 2}, {"item": 9, "x": 5, "y": 5}]
        self.assertEqual(validate_map(data)[0], [])
        for bad in ([{"item": "bread", "x": 1, "y": 1}], [{"item": 8, "x": 9999, "y": 1}], [{"item": 8, "x": 1}],
                    [{"item": 8, "x": 1, "y": 1, "respawn": 0}], [{"item": 8, "x": 1, "y": 1, "count": 0}], "x"):
            d = dict(data, item_spawns=bad)
            self.assertTrue(validate_map(d)[0], bad)


if __name__ == "__main__":
    unittest.main()
