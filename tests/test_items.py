"""Items: backpack stacks, potions (Health 120 HP, Mana 200/400 mana, one shared 30 s cooldown), food (heal over
20 s, one food buff), drinks (HP/mana over 10 s, one drink buff), monster drops by level, picking drops up, saving the
backpack."""
import random
import tempfile
import unittest

from game import saves
from game.content.items import ITEMS, POTION_COOLDOWN, describe, roll_drops
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

    def test_potion_heals_120_now_with_a_30s_cooldown(self):
        world, p = solo()
        h = p.hero
        h.hp = 100
        world.submit(C.UsePotion(), 0)
        world.step(DT)
        self.assertAlmostEqual(h.hp, 220, delta=1.5)            # +120 (plus a frame of regen)
        self.assertEqual(p.potions, 2)
        h.hp = 100
        step(world, 29)
        h.hp = 100
        world.submit(C.UsePotion(), 0)                          # still on cooldown: nothing
        world.step(DT)
        self.assertEqual(p.potions, 2)
        step(world, 1.1)
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

    def mana_hero(self, inventory):
        world, p = solo("Wizard", level=20, inventory=inventory)    # Wizard L20: plenty of max mana
        h = p.hero
        h.mana_regen_ooc = h.mana_regen_combat = 0.0                 # measure the items alone
        h.regen_rate_ooc = h.regen_rate_combat = 0.0
        h.mana = 0.0
        return world, p, h

    def test_mana_potions_restore_200_and_400_now(self):
        for item, amount in (("minor_mana_potion", 200), ("mana_potion", 400)):
            world, p, h = self.mana_hero([{"slot": 0, "item": item, "count": 1}])
            self.assertGreater(h.max_mana, 400)
            world.submit(C.UseItem(0), 0)
            world.step(DT)
            self.assertAlmostEqual(h.mana, amount, delta=0.01)
            self.assertEqual(p.inventory.count(item), 0)
            self.assertEqual(p.potion_cooldown, POTION_COOLDOWN - DT)

    def test_all_potions_share_one_cooldown(self):
        world, p, h = self.mana_hero([{"slot": 0, "item": "health_potion", "count": 1},
                                      {"slot": 1, "item": "mana_potion", "count": 1},
                                      {"slot": 2, "item": "minor_mana_potion", "count": 1}])
        h.hp = 100
        world.submit(C.UseItem(0), 0)                           # health potion starts the cooldown
        world.step(DT)
        world.submit(C.UseItem(1), 0)                           # mana potion: blocked
        world.step(DT)
        self.assertEqual(h.mana, 0.0)
        self.assertEqual(p.inventory.count("mana_potion"), 1)
        step(world, POTION_COOLDOWN)
        world.submit(C.UseItem(1), 0)
        world.step(DT)
        self.assertAlmostEqual(h.mana, 400, delta=0.01)
        world.submit(C.UseItem(2), 0)                           # minor one is now blocked by the mana potion
        world.step(DT)
        self.assertEqual(p.inventory.count("minor_mana_potion"), 1)

    def test_mana_potion_is_not_wasted_at_full_mana(self):
        world, p, h = self.mana_hero([{"slot": 0, "item": "mana_potion", "count": 1}])
        h.mana = h.max_mana
        h.hp = 1                                                 # low HP doesn't matter for a mana potion
        world.submit(C.UseItem(0), 0)
        world.step(DT)
        self.assertEqual(p.inventory.count("mana_potion"), 1)
        self.assertEqual(p.potion_cooldown, 0.0)


class DrinkTest(unittest.TestCase):
    def drink(self, item, extra=()):
        inv = [{"slot": 0, "item": item, "count": 2}] + list(extra)
        world, p = solo("Wizard", level=30, inventory=inv)          # big pools: nothing caps
        h = p.hero
        h.regen_rate_ooc = h.regen_rate_combat = 0.0
        h.mana_regen_ooc = h.mana_regen_combat = 0.0
        h.hp, h.mana = 10, 0.0
        world.submit(C.UseItem(0), 0)
        world.step(DT)
        return world, p, h

    def test_drinks_restore_over_10s(self):
        for item, hp, mana in (("water", 0, 300), ("coffee", 0, 600), ("wine", 300, 300), ("elven_nectar", 500, 500)):
            world, p, h = self.drink(item)
            self.assertEqual(p.inventory.count(item), 1)
            self.assertEqual(p.potion_cooldown, 0.0)                # drinks don't use the potion cooldown
            self.assertLess(h.mana, mana * 0.1 + 1)                 # not instant
            step(world, 5)
            self.assertAlmostEqual(h.mana, mana / 2, delta=mana * 0.03, msg=item)
            self.assertAlmostEqual(h.hp, 10 + hp / 2, delta=hp * 0.03 + 0.01, msg=item)
            step(world, 5.5)
            self.assertAlmostEqual(h.mana, mana, delta=mana * 0.03, msg=item)
            self.assertAlmostEqual(h.hp, 10 + hp, delta=hp * 0.03 + 0.01, msg=item)
            self.assertNotIn("Drinking", h.buffs)

    def test_coffee_doubles_mana_regen_for_10_minutes(self):
        world, p, h = self.drink("coffee")
        self.assertEqual(h.buffs["Refreshed"]["item"], "coffee")
        self.assertEqual(h.regen_multipliers(), (1.0, 2.0))
        step(world, 599)
        self.assertIn("Refreshed", h.buffs)
        step(world, 2)
        self.assertNotIn("Refreshed", h.buffs)
        self.assertEqual(h.regen_multipliers(), (1.0, 1.0))

    def test_regen_buff_doubles_actual_regeneration(self):
        world, p = solo("Wizard", level=30)
        h = p.hero
        h.hp, h.mana = 10, 0.0
        world.step(DT)
        plain_hp, plain_mana = h.hp - 10, h.mana
        h.hp, h.mana = 10, 0.0
        h.buffs["Refreshed"] = {"remaining": 600, "item": "elven_nectar", "hp_regen_pct": 1.0, "mana_regen_pct": 1.0}
        world.step(DT)
        self.assertAlmostEqual(h.hp - 10, plain_hp * 2)
        self.assertAlmostEqual(h.mana, plain_mana * 2)

    def test_eating_and_drinking_stack_and_new_drink_buff_replaces_old(self):
        world, p, h = self.drink("coffee", extra=[{"slot": 1, "item": "roast_chicken", "count": 1},
                                                  {"slot": 2, "item": "elven_nectar", "count": 1},
                                                  {"slot": 3, "item": "water", "count": 1}])
        world.submit(C.UseItem(1), 0)
        world.step(DT)
        self.assertEqual((h.buffs["Eating"]["item"], h.buffs["Drinking"]["item"]), ("roast_chicken", "coffee"))
        self.assertIn("Well Fed", h.buffs)
        world.submit(C.UseItem(2), 0)
        world.step(DT)
        self.assertEqual(h.buffs["Refreshed"]["item"], "elven_nectar")
        self.assertEqual(h.regen_multipliers(), (2.0, 2.0))
        world.submit(C.UseItem(3), 0)                           # water: no buff, keeps the nectar's
        world.step(DT)
        self.assertEqual(h.buffs["Drinking"]["item"], "water")
        self.assertEqual(h.buffs["Refreshed"]["item"], "elven_nectar")
        food = make_snapshot(world)["you"]["food"]
        self.assertEqual({k: v["item"] for k, v in food.items()},
                         {"eating": "roast_chicken", "buff": "roast_chicken", "drinking": "water",
                          "drink_buff": "elven_nectar"})

    def test_descriptions(self):
        self.assertEqual(describe("mana_potion"),
                         "Instantly restores 400 mana. 30s cooldown (shared by all potions).")
        self.assertEqual(describe("wine"), "Restores 300 HP and 300 mana over 10s.")
        self.assertEqual(describe("elven_nectar"),
                         "Restores 500 HP and 500 mana over 10s. Refreshed: +100% HP regen and +100% mana regen "
                         "for 10 min (replaces other drink buffs).")


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
    def test_every_monster_type_has_a_drop_table_of_real_items(self):
        from game.content.monsters import SPAWN_STATS
        for key, stats in SPAWN_STATS.items():
            self.assertIsInstance(stats["drops"], list, key)
            for entry in stats["drops"]:
                self.assertIn(entry[0], ITEMS, key)
                self.assertTrue(0 < entry[1] <= 1, key)
                self.assertIn(len(entry), (2, 4), key)

    def test_bread_from_humanoids_drumstick_from_beasts_at_3_percent_any_level(self):
        from game.content.monsters import SPAWN_STATS
        for lv in (1, 5, 10, 30):
            self.assertIn("bread", roll_drops(SPAWN_STATS["human_cultist"]["drops"], lv, FixedRng(0.029)))
            self.assertNotIn("bread", roll_drops(SPAWN_STATS["grey_wolf"]["drops"], lv, FixedRng(0.0)))
            self.assertIn("drumstick", roll_drops(SPAWN_STATS["grey_wolf"]["drops"], lv, FixedRng(0.029)))
            self.assertNotIn("drumstick", roll_drops(SPAWN_STATS["kobold_dragonshield"]["drops"], lv, FixedRng(0.0)))
        self.assertEqual(roll_drops(SPAWN_STATS["snake"]["drops"], 2, FixedRng(0.031)), [])

    def test_level_bounded_entries(self):
        table = [("bread", 0.5), ("elven_nectar", 0.005, 10, 20)]
        always = FixedRng(0.0)
        self.assertEqual(roll_drops(table, 9, always), ["bread"])
        self.assertEqual(roll_drops(table, 10, always), ["bread", "elven_nectar"])
        self.assertEqual(roll_drops(table, 20, always), ["bread", "elven_nectar"])
        self.assertEqual(roll_drops(table, 21, always), ["bread"])
        self.assertEqual(roll_drops(table, 15, FixedRng(0.006)), ["bread"])     # nectar 0.5%

    def test_northshire_never_drops_elven_nectar(self):
        import json
        from game.content.monsters import SPAWN_STATS
        with open(MAP) as f:
            levels = json.load(f)["monster_levels"]
        for kind, rng_ in levels.items():
            for lv in range(rng_[0], rng_[1] + 1):
                self.assertNotIn("elven_nectar", roll_drops(SPAWN_STATS[kind]["drops"], lv, FixedRng(0.0)))

    def test_drop_rate_matches_the_table(self):
        from game.content.monsters import SPAWN_STATS
        rng = random.Random(7)
        n = 20000
        got = sum(len(roll_drops(SPAWN_STATS["grey_wolf"]["drops"], 2, rng)) for _ in range(n))
        self.assertAlmostEqual(got / n, 0.04, delta=0.005)        # drumstick 3% + minor mana potion 1%

    def test_map_spawn_can_override_the_drop_table(self):
        random.seed(2)
        world, p = create_world(MAP, saves.blank_character("t", "Fighter", level=10))
        sp = next(m.spawn_point for m in world.game_state.monsters if m.spawn_type == "grey_wolf")
        sp.stats = {"drops": [("wine", 1.0)]}
        m = world.spawn_single_world_monster(sp)
        self.assertEqual(m.drops, [("wine", 1.0)])

    def test_kill_drops_on_the_ground_and_pickup_puts_it_in_the_backpack(self):
        random.seed(2)
        world, p = create_world(MAP, saves.blank_character("t", "Fighter", level=10))
        m = next(m for m in world.game_state.monsters if m.level >= 4)
        import game.engine.world as W
        orig = W.roll_drops
        W.roll_drops = lambda *a: ["roast_chicken"]
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


class LootByCategoryTest(unittest.TestCase):
    def test_every_monster_has_a_category_and_northshire_is_humanoids_and_beasts(self):
        from game.content.monsters import SPAWN_STATS
        self.assertTrue(all(s["category"] in ("humanoid", "beast", "demon") for s in SPAWN_STATS.values()))
        cats = {k: SPAWN_STATS[k]["category"] for k in
                ("human_cultist", "kobold_dragonshield", "garrick_padfoot", "grey_wolf", "snake")}
        self.assertEqual(cats, {"human_cultist": "humanoid", "kobold_dragonshield": "humanoid",
                                "garrick_padfoot": "humanoid", "grey_wolf": "beast", "snake": "beast"})

    def test_humanoid_money_formula(self):
        from game.content.monsters import humanoid_money
        self.assertEqual(humanoid_money(1, FixedUniform(1.0)), 5)          # max(5, 8 - 40) = 5
        self.assertEqual(humanoid_money(4, FixedUniform(1.0)), 5)
        self.assertEqual(humanoid_money(10, FixedUniform(1.0)), 40)        # 10 x 8 - 40
        self.assertEqual(humanoid_money(10, FixedUniform(0.8)), 32)
        self.assertEqual(humanoid_money(10, FixedUniform(1.2)), 48)
        rng = random.Random(3)
        self.assertTrue(all(4 <= humanoid_money(3, rng) <= 6 for _ in range(200)))

    def test_beasts_drop_meat_and_no_bread(self):
        from game.content.monsters import SPAWN_STATS
        for kind in ("grey_wolf", "snake", "rage_drake", "ashardalon"):
            got = roll_drops(SPAWN_STATS[kind]["drops"], 5, FixedRng(0.0))
            self.assertIn("drumstick", got)
            self.assertNotIn("bread", got)

    def test_northshire_drop_rates(self):
        """User-tuned Northshire table (% per kill)."""
        from game.content.monsters import SPAWN_STATS
        expected = {
            "human_cultist":       {"health_potion": 1, "bread": 3, "water": 3, "roast_chicken": 1, "sushi_plate": 1,
                                    "coffee": 1, "wine": 2, "minor_mana_potion": 1, "mana_potion": 0.5},
            "kobold_dragonshield": {"health_potion": 1, "bread": 3, "water": 3, "roast_chicken": 1, "sushi_plate": 1,
                                    "wine": 1, "minor_mana_potion": 1},
            "garrick_padfoot":     {"health_potion": 1, "bread": 3, "water": 3, "roast_chicken": 1, "sushi_plate": 1,
                                    "coffee": 3, "wine": 3, "minor_mana_potion": 3, "mana_potion": 3},
            "grey_wolf":           {"drumstick": 3, "minor_mana_potion": 1},
            "snake":               {"drumstick": 3, "minor_mana_potion": 1},
        }
        for kind, rates in expected.items():
            got = {e[0]: round(e[1] * 100, 3) for e in SPAWN_STATS[kind]["drops"] if len(e) == 2}
            self.assertEqual(got, rates, kind)
            self.assertEqual(len({e[0] for e in SPAWN_STATS[kind]["drops"]}), len(SPAWN_STATS[kind]["drops"]), kind)

    def test_only_humanoids_give_money(self):
        random.seed(4)
        world, p = create_world(MAP, saves.blank_character("t", "Fighter", level=1))
        mobs = world.game_state.monsters
        for category in ("beast", "humanoid"):
            m = next(m for m in mobs if m.alive and m.category == category)
            before = p.hero.gold
            m.take_damage(10 ** 6, source=p.hero)
            world.process_kills()
            got = p.hero.gold - before
            if category == "beast":
                self.assertEqual(got, 0)
            else:
                self.assertTrue(4 <= got <= 6, got)                    # level 1..4 humanoid: 5 x 0.8..1.2

    def test_quest_money_was_halved(self):
        from game.quests import load_quest_log
        log = load_quest_log("northshire")
        self.assertEqual(sorted(q.rewards_gold for q in log.quests.values()), [0, 25, 25, 38, 38, 38, 50, 50])


class FixedUniform:
    def __init__(self, value):
        self.value = value

    def uniform(self, lo, hi):
        return self.value


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
                json.dump([{"tick": 0, "type": "key", "key": "p"},           # autopilot off
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
        self.assertFalse([c for c in cmds if c["type"] in ("MoveTo", "SelectTarget", "Cast", "SetTarget")])   # panel ate clicks
