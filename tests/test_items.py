"""Items: backpack stacks, Health Potion (120 HP, 90 s cooldown), food (heal over 20 s, one food buff), monster
drops by level, picking drops up, saving the backpack."""
import random
import tempfile
import unittest

from game import saves
from game.content.items import DROP_TABLE, ITEMS, roll_drops
from game.engine import commands as C
from game.engine.bootstrap import create_world, sanitize_character
from game.engine.inventory import SIZE, Inventory
from game.engine.snapshot import make_snapshot

MAP = "data/maps/northshire.json"
DT = 1 / 30
saves.SAVE_DIR = tempfile.mkdtemp()


def solo(cls="Fighter", level=10, inventory=None):
    random.seed(1)
    char = saves.blank_character("t", cls, level=level)
    if inventory is not None:
        char["inventory"] = inventory
    world, player = create_world(MAP, char)
    world.game_state.monsters.clear()
    return world, player


def step(world, seconds):
    for _ in range(int(round(seconds / DT))):
        world.step(DT)


class FixedRng:
    def __init__(self, value):
        self.value = value

    def random(self):
        return self.value


class InventoryTest(unittest.TestCase):
    def test_stacks_without_limit_and_first_empty_slot(self):
        inv = Inventory.from_state([])
        for _ in range(500):
            self.assertTrue(inv.add("bread"))
        inv.add("drumstick")
        self.assertEqual(inv.to_state(), [{"slot": 0, "item": "bread", "count": 500},
                                          {"slot": 1, "item": "drumstick", "count": 1}])
        self.assertEqual(inv.take_from_slot(1), "drumstick")
        self.assertIsNone(inv.slots[1])
        inv.add("sushi_plate")
        self.assertEqual(inv.item_at(1), "sushi_plate")          # reuses the emptied slot

    def test_full_backpack_refuses_new_items_but_still_stacks(self):
        inv = Inventory()
        inv.slots = [{"item": "drumstick", "count": 1} for _ in range(SIZE)]
        inv.slots[0] = {"item": "bread", "count": 1}
        self.assertFalse(inv.add("sushi_plate"))
        self.assertTrue(inv.add("bread"))

    def test_from_state_validates(self):
        self.assertEqual(Inventory.from_state(None).to_state(), [{"slot": 0, "item": "health_potion", "count": 3}])
        for bad in ("x", [{"slot": 40, "item": "bread", "count": 1}], [{"slot": 0, "item": "gold_bar", "count": 1}],
                    [{"slot": 0, "item": "bread", "count": 0}],
                    [{"slot": 0, "item": "bread", "count": 1}, {"slot": 0, "item": "bread", "count": 1}]):
            with self.assertRaises(ValueError):
                Inventory.from_state(bad)


class PotionTest(unittest.TestCase):
    def test_new_character_starts_with_3_potions(self):
        world, p = solo()
        self.assertEqual(p.potions, 3)
        self.assertEqual(make_snapshot(world)["you"]["potions"], 3)

    def test_potion_heals_120_now_with_a_90s_cooldown(self):
        world, p = solo()
        h = p.hero
        h.hp = 100
        world.submit(C.UsePotion(), 0)
        world.step(DT)
        self.assertAlmostEqual(h.hp, 220, delta=1.5)            # +120 (plus a frame of regen)
        self.assertEqual(p.potions, 2)
        h.hp = 100
        world.submit(C.UsePotion(), 0)                          # on cooldown: nothing
        world.step(DT)
        self.assertEqual(p.potions, 2)
        step(world, 90)
        h.hp = 100
        world.submit(C.UseItem(0), 0)                           # right-click the potion slot
        world.step(DT)
        self.assertEqual(p.potions, 1)
        self.assertGreater(h.hp, 215)

    def test_companions_have_unlimited_potions_with_the_same_cooldown(self):
        world, p = solo()
        world.submit(C.ToggleCompanion("Cleric"), 0)
        world.step(DT)
        comp = world.companions[0]
        self.assertIsNone(comp.potions)
        self.assertTrue(comp._potion_ready())
        comp._use_potion()
        self.assertFalse(comp._potion_ready())


class FoodTest(unittest.TestCase):
    def eat(self, item, hp=10):
        world, p = solo(inventory=[{"slot": 0, "item": item, "count": 2}])
        p.hero.hp = hp
        p.hero.regen_rate_combat = p.hero.regen_rate_ooc = 0.0    # measure the food alone
        world.submit(C.UseItem(0), 0)
        world.step(DT)
        return world, p

    def test_bread_and_drumstick_heal_over_20s(self):
        for item, total in (("bread", 120), ("drumstick", 200)):
            world, p = self.eat(item)
            self.assertEqual(p.inventory.count(item), 1)
            self.assertLess(p.hero.hp, 10 + total * 0.1)        # not instant
            step(world, 10)
            self.assertAlmostEqual(p.hero.hp, 10 + total / 2, delta=total * 0.03)
            step(world, 11)
            self.assertAlmostEqual(p.hero.hp, 10 + total, delta=total * 0.03)
            self.assertNotIn("Eating", p.hero.buffs)

    def test_roast_chicken_heals_300_and_buffs_damage_and_max_hp(self):
        world, p = self.eat("roast_chicken")
        h = p.hero
        base = h.base_max_hp
        self.assertEqual(h.max_hp, round(base * 1.05))
        self.assertAlmostEqual(h.damage_bonus, 1.05)
        step(world, 21)
        self.assertAlmostEqual(h.hp, 10 + 300 + base * 0.05, delta=10)
        step(world, 600)
        self.assertNotIn("Well Fed", h.buffs)                   # 600 s buff ran out
        self.assertEqual(h.max_hp, base)
        self.assertLessEqual(h.hp, h.max_hp)

    def test_one_food_buff_new_one_replaces_old(self):
        world, p = solo(inventory=[{"slot": 0, "item": "roast_chicken", "count": 1},
                                   {"slot": 1, "item": "sushi_plate", "count": 1},
                                   {"slot": 2, "item": "bread", "count": 1}])
        h = p.hero
        world.submit(C.UseItem(0), 0)
        world.step(DT)
        world.submit(C.UseItem(1), 0)
        world.step(DT)
        self.assertEqual(h.buffs["Well Fed"]["item"], "sushi_plate")
        self.assertAlmostEqual(h.damage_bonus, 1.10)
        self.assertEqual(h.max_hp, h.base_max_hp)               # sushi has no max HP bonus
        world.submit(C.UseItem(2), 0)                           # bread: no buff, keeps sushi's
        world.step(DT)
        self.assertEqual(h.buffs["Well Fed"]["item"], "sushi_plate")
        self.assertEqual(h.buffs["Eating"]["item"], "bread")

    def test_damage_buff_applies_to_hits(self):
        random.seed(5)
        world, p = create_world(MAP, saves.blank_character("t", "Fighter", level=10))
        m = world.game_state.monsters[0]
        m.hp = m.max_hp = 10 ** 6
        before = m.hp
        m.take_damage(100, source=p.hero)
        plain = before - m.hp
        p.hero.buffs["Well Fed"] = {"remaining": 600, "item": "sushi_plate", "damage_pct": 0.10}
        before = m.hp
        m.take_damage(100, source=p.hero)
        self.assertAlmostEqual(before - m.hp, plain * 1.10)


class DropTest(unittest.TestCase):
    def test_drop_levels(self):
        always = FixedRng(0.0)
        self.assertEqual(roll_drops(1, always), ["health_potion", "bread"])
        self.assertEqual(roll_drops(3, always), ["health_potion", "bread", "drumstick"])
        self.assertEqual(roll_drops(9, always), ["health_potion", "bread", "drumstick", "roast_chicken",
                                                 "sushi_plate"])
        self.assertEqual(roll_drops(10, always), ["bread", "drumstick", "roast_chicken", "sushi_plate"])
        self.assertEqual(roll_drops(11, always), [])
        self.assertEqual(roll_drops(5, FixedRng(0.011)), [])      # 1% each
        self.assertTrue(all(chance == 0.01 for _, chance, _, _ in DROP_TABLE))

    def test_drop_rate_is_about_1_percent(self):
        rng = random.Random(7)
        n = 20000
        got = sum(len(roll_drops(2, rng)) for _ in range(n))
        self.assertAlmostEqual(got / n, 0.02, delta=0.004)        # potion + bread at level 2

    def test_kill_drops_on_the_ground_and_pickup_puts_it_in_the_backpack(self):
        random.seed(2)
        world, p = create_world(MAP, saves.blank_character("t", "Fighter", level=10))
        m = next(m for m in world.game_state.monsters if m.level >= 4)
        import game.engine.world as W
        orig = W.roll_drops
        W.roll_drops = lambda level, rng: ["roast_chicken"]
        try:
            m.take_damage(10 ** 6, source=p.hero)
            world.process_kills()
        finally:
            W.roll_drops = orig
        self.assertEqual(len(world.ground_items), 1)
        g = world.ground_items[0]
        self.assertEqual((g.item, round(g.x), round(g.y)), ("roast_chicken", round(m.x), round(m.y)))
        snap = make_snapshot(world)
        self.assertEqual(snap["ground_items"], [{"id": g.item_id, "item": "roast_chicken", "x": g.x, "y": g.y}])
        world.game_state.monsters.clear()
        world.submit(C.PickUp(g.item_id), 0)                     # far away: walks there first
        for _ in range(30 * 120):
            world.step(DT)
            if not world.ground_items:
                break
        self.assertEqual(world.ground_items, [])
        self.assertEqual(p.inventory.count("roast_chicken"), 1)

    def test_full_backpack_leaves_the_item_on_the_ground(self):
        world, p = solo()
        p.inventory.slots = [{"item": "drumstick", "count": 1} for _ in range(SIZE)]   # every slot taken
        g = world.drop_item("sushi_plate", p.hero.x, p.hero.y)
        world.submit(C.PickUp(g.item_id), 0)
        world.step(DT)
        self.assertIn(g, world.ground_items)
        self.assertEqual(p.inventory.count("sushi_plate"), 0)


class SaveTest(unittest.TestCase):
    def test_old_saves_get_the_starting_backpack_and_backpack_round_trips(self):
        import json
        import os
        d = tempfile.mkdtemp()
        with open(os.path.join(d, "old.json"), "w") as f:
            json.dump({"name": "old", "class_name": "Rogue", "level": 3, "xp": 1, "gold": 2, "kills": 3,
                       "quests": {}}, f)
        data = saves.load_character("old", d)
        self.assertEqual(data["inventory"], [{"slot": 0, "item": "health_potion", "count": 3}])
        data["inventory"] = [{"slot": 4, "item": "bread", "count": 7}]
        saves.save_character(data, d)
        random.seed(1)
        world, p = create_world(MAP, saves.load_character("old", d))
        self.assertEqual(p.inventory.count("bread"), 7)
        self.assertEqual(p.potions, 0)

    def test_remote_characters_bring_a_validated_backpack(self):
        ok = sanitize_character({"name": "kid", "class_name": "Rogue", "level": 3, "xp": 0, "gold": 0, "kills": 0,
                                 "inventory": [{"slot": 2, "item": "bread", "count": 5}]})
        self.assertEqual(ok["inventory"], [{"slot": 2, "item": "bread", "count": 5}])
        with self.assertRaises(ValueError):
            sanitize_character({"name": "kid", "class_name": "Rogue", "inventory": [{"slot": 0, "item": "x",
                                                                                     "count": 1}]})

    def test_snapshot_progress_carries_the_backpack(self):
        world, p = solo()
        self.assertEqual(make_snapshot(world)["you"]["progress"]["inventory"], p.inventory.to_state())

    def test_item_commands_round_trip(self):
        for cmd in (C.UseItem(3), C.PickUp(12)):
            self.assertEqual(C.from_dict(C.to_dict(cmd)), cmd)


if __name__ == "__main__":
    unittest.main()


class RealInputTest(unittest.TestCase):
    def test_b_opens_the_backpack_and_right_click_on_a_slot_uses_it(self):
        """Headless pygame client: press B, right-click backpack slot 0 (the potions) -> a UseItem(0) command."""
        import json
        import os
        import subprocess
        import sys
        from game.engine import replay
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with tempfile.TemporaryDirectory() as d:
            script, rec = os.path.join(d, "s.json"), os.path.join(d, "rec.json")
            with open(script, "w") as f:
                json.dump([{"tick": 0, "type": "key", "key": "TAB"},           # autopilot off
                           {"tick": 2, "type": "key", "key": "b"},             # open the backpack
                           {"tick": 4, "type": "click", "button": 3, "at": {"backpack_slot": 0}},
                           {"tick": 6, "type": "click", "button": 1, "at": {"backpack_slot": 5}},   # left: nothing
                           {"tick": 8, "type": "key", "key": "b"}], f)
            p = subprocess.run([sys.executable, "-m", "game.main", "--headless", "--seed", "3", "--max-time", "1",
                                "--hero", "0", "--map", MAP, "--input-script", script, "--record-commands", rec,
                                "--no-companion"],
                               cwd=root, capture_output=True, text=True, timeout=60)
            self.assertEqual(p.returncode, 0, p.stderr[-1500:])
            cmds = [c["cmd"] for c in replay.load_recording(rec)["commands"]]
        self.assertIn({"type": "UseItem", "slot": 0}, cmds)
        self.assertFalse([c for c in cmds if c["type"] in ("MoveTo", "SelectTarget", "Cast")])   # panel ate clicks
