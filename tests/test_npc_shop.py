"""Vendors and class trainers: Northshire's new NPCs, buying (money, range, backpack room), learning skill levels
from the class trainer instead of getting them with the level, saves / co-op data, the client windows."""
import json
import os
import random
import subprocess
import sys
import tempfile
import unittest

from game import saves
from game.content import money
from game.content.equipment import GEAR
from game.content.shop import PRICES, SHOPS, train_cost
from game.content.skill_tree import STARTING_TRAINED, can_train, skill_levels, training_options, validate_trained
from game.engine import commands as C
from game.engine import events as E
from game.engine.bootstrap import create_world, sanitize_character
from game.engine.snapshot import make_snapshot

MAP = "data/maps/northshire.json"
DT = 1 / 30
saves.SAVE_DIR = tempfile.mkdtemp()
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def world_with(cls="Fighter", level=4, gold=0, trained=None):
    random.seed(1)
    ch = saves.blank_character("t", cls, level=level)
    ch["gold"] = gold
    if trained is not None:
        ch["trained"] = trained
    world, p = create_world(MAP, ch)
    world.game_state.monsters.clear()
    return world, p


def npc(world, npc_id):
    return next(n for n in world.npcs if n.npc_id == npc_id)


def go_to(p, n):
    p.hero.x, p.hero.y = n.x + 20, n.y


class NorthshireNpcsTest(unittest.TestCase):
    def test_trainers_for_every_class_and_three_vendors(self):
        world, p = world_with()
        trainers = {n.trains: n for n in world.npcs if n.role == "trainer"}
        self.assertEqual(set(trainers), {"Fighter", "Paladin", "Cleric", "Rogue", "Wizard"})
        self.assertEqual(sorted(n.shop for n in world.npcs if n.role == "vendor"), ["armor", "general", "weapons"])
        for n in world.npcs:
            self.assertFalse(world.is_wall(n.x, n.y), n.name)
        self.assertEqual(npc(world, "llane_beshere").title, "Fighter Trainer")
        self.assertEqual(npc(world, "janos_hammerknuckle").title, "Weaponsmith")

    def test_trainers_use_their_class_avatar(self):
        from game.content.heroes import HERO_CLASSES
        tiles = {"fighter": (0, 8), "cleric": (3, 8), "paladin": (4, 7), "rogue": (2, 7), "wizard": (0, 7)}
        world, p = world_with()
        for n in world.npcs:
            if n.role == "trainer":
                key = next(c["sprite_key"] for c in HERO_CLASSES if c["class"] == n.trains)
                self.assertEqual(n.sprite_tile, tiles[key], n.name)

    def test_what_the_vendors_sell(self):
        from game.content.items import ITEMS
        self.assertEqual(set(SHOPS["general"]), {k for k, it in ITEMS.items() if it["kind"] in ("food", "drink")})
        self.assertEqual(set(SHOPS["weapons"]), {k for k, g in GEAR.items() if g["kind"] == "weapon"})
        self.assertEqual(set(SHOPS["armor"]), {"round_shield", "buckler"})
        self.assertTrue(all(PRICES[i] > 0 for s in SHOPS.values() for i in s))

    def test_gear_costs_several_times_a_northshire_run(self):
        """Questing Northshire to level 6 earns ~150-200 bronze; the best weapons cost several times that."""
        self.assertGreaterEqual(PRICES["warhammer"], 4 * 200)
        self.assertGreaterEqual(PRICES["buckler"], 2 * 200)
        self.assertLessEqual(PRICES["bread"], 20)


class BuyTest(unittest.TestCase):
    def test_buy_spends_money_and_fills_the_backpack(self):
        world, p = world_with(gold=1000)
        janos = npc(world, "janos_hammerknuckle")
        go_to(p, janos)
        world.submit(C.Buy(janos.eid, "short_sword"), 0)
        world.step(DT)
        self.assertEqual(p.hero.gold, 1000 - PRICES["short_sword"])
        self.assertEqual(p.inventory.count("short_sword"), 1)

    def test_refused_without_money_far_away_wrong_shop_or_full_backpack(self):
        from game.engine.inventory import SIZE
        world, p = world_with(gold=100)
        janos, danil = npc(world, "janos_hammerknuckle"), npc(world, "brother_danil")
        go_to(p, janos)
        world.submit(C.Buy(janos.eid, "warhammer"), 0)        # 8 silver: too poor
        world.submit(C.Buy(janos.eid, "bread"), 0)            # the weaponsmith doesn't sell bread
        world.submit(C.Buy(danil.eid, "bread"), 0)            # too far from Brother Danil
        world.step(DT)
        self.assertEqual((p.hero.gold, p.inventory.count("warhammer"), p.inventory.count("bread")), (100, 0, 0))
        go_to(p, danil)
        p.inventory.slots = [{"item": "wine", "count": 1}] * SIZE
        world.submit(C.Buy(danil.eid, "bread"), 0)            # backpack full
        world.step(DT)
        self.assertEqual(p.hero.gold, 100)
        world.submit(C.Buy(danil.eid, "wine"), 0)             # stacks: fits
        world.step(DT)
        self.assertEqual(p.hero.gold, 100 - PRICES["wine"])

    def test_talking_to_a_vendor_opens_its_window(self):
        world, p = world_with()
        janos = npc(world, "janos_hammerknuckle")
        go_to(p, janos)
        world.submit(C.InteractNpc(janos.eid), 0)
        world.step(DT)
        self.assertIn(E.OpenNpcWindow(janos.eid, "vendor", 0), world.events)

    def test_snapshot_tells_the_client_about_npcs(self):
        world, p = world_with()
        d = next(e for e in make_snapshot(world)["entities"] if e.get("npc_id") == "godric_rothgar")
        self.assertEqual((d["role"], d["shop"], d["title"]), ("vendor", "armor", "Armorer"))


class TrainingTest(unittest.TestCase):
    def test_player_characters_only_have_what_they_trained(self):
        world, p = world_with(level=8, trained={"Q": 1})
        self.assertEqual(list(p.hero.abilities), ["Q"])
        rows = {r["key"]: r for r in training_options(p.hero)}
        self.assertEqual((rows["R"]["next_at"], rows["R"]["cost"]), (2, train_cost(2)))
        self.assertEqual(rows["G"]["next_at"], 8)

    def test_train_at_the_class_trainer(self):
        world, p = world_with(level=4, gold=100, trained={"Q": 1})
        h = p.hero
        llane = npc(world, "llane_beshere")
        go_to(p, llane)
        world.submit(C.Train(llane.eid, "R"), 0)                     # Charge, unlocks at 2: 5 bronze
        world.step(DT)
        self.assertEqual(h.trained, {"Q": 1, "R": 1})
        self.assertIn("R", h.abilities)
        self.assertEqual(h.gold, 100 - train_cost(2))
        self.assertTrue(any(isinstance(e, E.SkillUp) and e.key == "R" for e in world.events))
        world.submit(C.Train(llane.eid, "R"), 0)                     # Charge 2 is a level-14 skill
        world.submit(C.Train(llane.eid, "E"), 0)                     # Shout comes at level 6
        world.step(DT)
        self.assertEqual(h.trained, {"Q": 1, "R": 1})

    def test_refused_by_the_wrong_trainer_without_money_or_far_away(self):
        world, p = world_with(level=4, gold=10, trained={"Q": 1})
        h = p.hero
        sammuel, llane = npc(world, "brother_sammuel"), npc(world, "llane_beshere")
        go_to(p, sammuel)
        world.submit(C.Train(sammuel.eid, "R"), 0)                   # a Paladin trainer
        world.submit(C.Train(llane.eid, "R"), 0)                     # too far
        world.step(DT)
        self.assertEqual(h.trained, {"Q": 1})
        go_to(p, llane)
        world.submit(C.Train(llane.eid, "F"), 0)                     # Heroic Strike 20 bronze > 10
        world.step(DT)
        self.assertEqual((h.trained, h.gold), ({"Q": 1}, 10))
        self.assertEqual(can_train(h, "F")[:2], (False, "Not enough money"))

    def test_level_up_says_what_can_be_learned_and_teaches_nothing(self):
        world, p = world_with(level=1, trained={"Q": 1})
        h = p.hero
        h.xp = 10 ** 3
        world.process_level_ups()
        self.assertGreaterEqual(h.level, 2)
        self.assertEqual(list(h.abilities), ["Q"])
        ev = next(e for e in world.events if isinstance(e, E.SkillTrainable))
        self.assertEqual((ev.key, ev.name, ev.is_new, ev.cost, ev.trainer), ("R", "Charge", True, 5, "Fighter Trainer"))
        self.assertFalse(any(isinstance(e, E.SkillUp) for e in world.events))

    def test_companions_and_test_characters_still_get_skills_with_the_level(self):
        world, p = world_with(level=8)                                # blank_character: no "trained"
        self.assertIsNone(p.hero.trained)
        self.assertEqual(set(p.hero.abilities), set(skill_levels("Fighter", 8)))
        self.assertIsNone(make_snapshot(world)["you"]["training"])
        world.submit(C.ToggleCompanion("Cleric"), 0)
        world.step(DT)
        self.assertIsNone(world.companions[0].hero.trained)


class SaveTest(unittest.TestCase):
    def test_new_characters_know_only_their_first_skill(self):
        d = tempfile.mkdtemp()
        data, err = saves.create_character("newbie", "Wizard", d)
        self.assertIsNone(err)
        self.assertEqual(data["trained"], STARTING_TRAINED)
        self.assertEqual(saves.load_character("newbie", d)["trained"], {"Q": 1})

    def test_old_saves_keep_the_skills_they_had(self):
        d = tempfile.mkdtemp()
        with open(os.path.join(d, "vet.json"), "w") as f:
            json.dump({"name": "vet", "class_name": "Rogue", "level": 9, "xp": 0, "gold": 0, "kills": 0,
                       "quests": {}}, f)
        data = saves.load_character("vet", d)
        self.assertEqual(data["trained"], skill_levels("Rogue", 9))
        random.seed(1)
        world, p = create_world(MAP, data)
        self.assertEqual(set(p.hero.abilities), set(skill_levels("Rogue", 9)))

    def test_trained_round_trips_and_is_validated(self):
        world, p = world_with(level=4, trained={"Q": 1, "R": 1})
        self.assertEqual(make_snapshot(world)["you"]["progress"]["trained"], {"Q": 1, "R": 1})
        self.assertEqual(validate_trained({"Q": 3, "R": 1, "Zap": 2}, "Fighter", 4), {"Q": 1, "R": 1})   # capped
        self.assertEqual(validate_trained({}, "Fighter", 1), {"Q": 1})
        for bad in ("x", {"Q": "1"}, {"Q": -1}, {"Q": True}):
            with self.assertRaises(ValueError, msg=bad):
                validate_trained(bad, "Fighter", 4)
        base = {"name": "kid", "class_name": "Fighter", "level": 4, "xp": 0, "gold": 0, "kills": 0}
        self.assertEqual(sanitize_character({**base, "trained": {"Q": 1}})["trained"], {"Q": 1})
        self.assertIsNone(sanitize_character(base)["trained"])
        with self.assertRaises(ValueError):
            sanitize_character({**base, "trained": [1]})

    def test_commands_and_events_round_trip(self):
        for cmd in (C.Buy(3, "axe"), C.Train(4, "R")):
            self.assertEqual(C.from_dict(C.to_dict(cmd)), cmd)
        for ev in (E.OpenNpcWindow(5, "trainer", 1), E.SkillTrainable(2, "R", "Charge", 1, True, 5, "Fighter Trainer")):
            self.assertEqual(E.from_dict(E.to_dict(ev)), ev)

    def test_price_format(self):
        self.assertEqual([money.format_price(b) for b in (5, 100, 150, 800, 10050)], ["5b", "1s", "1s 50b", "8s",
                                                                                     "1g 50b"])


class ClientWindowTest(unittest.TestCase):
    def test_walk_to_the_trainer_train_then_buy_from_the_weaponsmith(self):
        """Headless pygame client: right-click the Fighter trainer (walks there), again to open his window, click
        Train on Charge; then the weaponsmith's shop, right-click the Short Sword."""
        from game.engine import replay
        with tempfile.TemporaryDirectory() as d:
            script, rec = os.path.join(d, "s.json"), os.path.join(d, "rec.json")
            with open(script, "w") as f:
                json.dump([{"tick": 0, "type": "key", "key": "p"},
                           {"tick": 10, "type": "click", "button": 3, "at": {"npc": "llane_beshere"}},
                           {"tick": 200, "type": "click", "button": 3, "at": {"npc": "llane_beshere"}},
                           {"tick": 215, "type": "click", "button": 1, "at": {"train_skill": "R"}},
                           {"tick": 230, "type": "click", "button": 3, "at": {"npc": "janos_hammerknuckle"}},
                           {"tick": 450, "type": "click", "button": 3, "at": {"npc": "janos_hammerknuckle"}},
                           {"tick": 465, "type": "click", "button": 3, "at": {"shop_item": "short_sword"}}], f)
            code = (f"import sys; sys.argv = ['game.main', '--headless', '--seed', '3', '--max-time', '17', "
                    f"'--hero', '0', '--level', '4', '--map', {MAP!r}, '--input-script', {script!r}, "
                    f"'--record-commands', {rec!r}, '--no-companion']\n"
                    "import game.saves as s\norig = s.blank_character\n"
                    "s.blank_character = lambda *a, **k: {**orig(*a, **k), 'trained': {'Q': 1}, 'gold': 600}\n"
                    "import runpy; runpy.run_module('game.main', run_name='__main__')")
            r = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, timeout=90)
            self.assertEqual(r.returncode, 0, r.stderr[-1500:])
            cmds = [c["cmd"] for c in replay.load_recording(rec)["commands"]]
        self.assertTrue(any(c["type"] == "Train" and c["ab_key"] == "R" for c in cmds), cmds)
        self.assertTrue(any(c["type"] == "Buy" and c["item"] == "short_sword" for c in cmds), cmds)


if __name__ == "__main__":
    unittest.main()
