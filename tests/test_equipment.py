"""Equipment: weapon / shield stats on the hero (damage a x class + b, slower-of swing, weight -> move speed, shield
block), equip / unequip rules (2h, off hand, dual wield only for Rogue and Fighter), saving, snapshots, the
character window."""
import json
import os
import random
import subprocess
import sys
import tempfile
import unittest

from game import saves
from game.content.equipment import (GEAR, ICONIC, SHIELD_BASE_BLOCK, equip, gear_stats, slot_for,
                                    validate_equipment)
from game.engine import commands as C
from game.engine.bootstrap import create_world, sanitize_character
from game.engine.snapshot import make_snapshot

MAP = "data/maps/northshire.json"
DT = 1 / 30
saves.SAVE_DIR = tempfile.mkdtemp()
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def solo(cls="Fighter", level=10, items=(), equipment=None):
    random.seed(1)
    char = saves.blank_character("t", cls, level=level)
    char["inventory"] = [{"slot": i, "item": it, "count": 1} for i, it in enumerate(items)]
    if equipment is not None:
        char["equipment"] = equipment
    world, player = create_world(MAP, char)
    world.game_state.monsters.clear()
    return world, player


def use(world, item, player):
    slot = next(s["slot"] for s in player.inventory.to_state() if s["item"] == item)
    world.submit(C.UseItem(slot), 0)
    world.step(DT)


class GearStatsTest(unittest.TestCase):
    def test_bare_hands_keep_the_class_numbers(self):
        for cls, (dmg, swing, speed) in {"Fighter": (46.0, 1.6, 75), "Rogue": (15.7, 0.5, 90),
                                         "Paladin": (52.5, 2.2, 90), "Wizard": (38.7, 2.0, 90),
                                         "Cleric": (35.0, 1.2, 75)}.items():
            world, p = solo(cls)
            h = p.hero
            self.assertAlmostEqual(h.base_damage, dmg, places=6, msg=cls)
            self.assertEqual((h.weapon_speed, h.speed, h.block_chance, h.gear_weight), (swing, speed, 0.0, 0), cls)

    def test_two_handed_weapon_multiplies_and_adds(self):
        world, p = solo("Paladin", equipment={"main": "warhammer", "off": None})
        h = p.hero
        self.assertAlmostEqual(h.base_damage, 1.5 * 52.5 + 6)
        self.assertEqual(h.weapon_speed, 2.2)                     # iconic: same as the class swing
        self.assertAlmostEqual(h.speed, 90 * 0.90)                # weight 10

    def test_slow_weapon_slows_a_fast_class_fast_weapon_never_speeds_it_up(self):
        world, p = solo("Rogue", equipment={"main": "broadsword", "off": None})
        self.assertEqual(p.hero.weapon_speed, 1.8)
        world, p = solo("Paladin", equipment={"main": "dagger", "off": None})
        self.assertEqual(p.hero.weapon_speed, 2.2)
        self.assertAlmostEqual(p.hero.base_damage, 52.5 + 1)

    def test_dual_wield_half_off_hand_bonus_and_average_swing(self):
        world, p = solo("Fighter", equipment={"main": "broadsword", "off": "cleaver"})
        h = p.hero
        self.assertAlmostEqual(h.base_damage, 46 + 5 + 3 / 2)
        self.assertAlmostEqual(h.weapon_speed, max(1.6, (1.8 + 1.4) / 2))
        self.assertAlmostEqual(h.speed, 75 * (100 - 7) / 100)

    def test_shields_block(self):
        self.assertAlmostEqual(gear_stats({"main": None, "off": "round_shield"})["block"], SHIELD_BASE_BLOCK + 0.03)
        self.assertAlmostEqual(gear_stats({"main": "axe", "off": "buckler"})["block"], 0.10)
        self.assertEqual(gear_stats({"main": "axe", "off": "dagger"})["block"], 0.0)

    def test_weights_from_the_user(self):
        want = {"dagger": 1, "short_sword": 2, "cleaver": 3, "broadsword": 4, "wooden_sword": 1, "double_axe": 8,
                "axe": 5, "spear": 4, "wand": 1, "staff": 4, "warhammer": 10, "round_shield": 3, "buckler": 5}
        self.assertEqual({k: g["weight"] for k, g in GEAR.items()}, want)

    def test_iconic_weapons_match_the_class_swing(self):
        for cls, item in ICONIC.items():
            world, p = solo(cls)
            self.assertEqual(GEAR[item]["swing"], p.hero.weapon_speed, cls)

    def test_level_up_grows_the_class_damage_under_the_gear(self):
        world, p = solo("Paladin", level=10, equipment={"main": "warhammer", "off": None})
        h = p.hero
        h.xp = 10 ** 6
        world.process_level_ups()
        self.assertGreater(h.level, 10)
        from game.progression import growth_for
        bare = 12 + growth_for("Paladin")["damage"] * (h.level - 1)
        self.assertAlmostEqual(h.class_damage, bare)
        self.assertAlmostEqual(h.base_damage, 1.5 * bare + 6)

    def test_skills_use_the_gear_damage(self):
        world, p = solo("Wizard", equipment={"main": "staff", "off": None})
        q = p.hero.abilities["Q"]
        self.assertAlmostEqual(q.calc_damage(p.hero.base_damage), q.multiplier * (1.4 * 38.7 + 5) + q.flat_bonus)


class EquipRulesTest(unittest.TestCase):
    def test_slot_choice(self):
        empty = {"main": None, "off": None}
        self.assertEqual(slot_for("Fighter", "axe", empty), "main")
        self.assertEqual(slot_for("Fighter", "axe", {"main": "axe", "off": None}), "off")       # dual wield
        self.assertEqual(slot_for("Paladin", "axe", {"main": "axe", "off": None}), "main")      # replaces
        self.assertEqual(slot_for("Paladin", "buckler", empty), "off")
        self.assertEqual(slot_for("Rogue", "dagger", {"main": "staff", "off": None}), "main")   # 2h replaced
        self.assertEqual(slot_for("Rogue", "spear", {"main": "dagger", "off": "dagger"}), "main")

    def test_only_rogue_and_fighter_dual_wield(self):
        for cls in ("Rogue", "Fighter"):
            equip(cls, {"main": "dagger", "off": None}, "dagger", "off")
        for cls in ("Paladin", "Cleric", "Wizard"):
            with self.assertRaises(ValueError):
                equip(cls, {"main": "dagger", "off": None}, "dagger", "off")
            equip(cls, {"main": "dagger", "off": None}, "buckler", "off")        # shields: anyone

    def test_two_hander_and_off_hand_push_each_other_off(self):
        new, removed = equip("Fighter", {"main": "axe", "off": "buckler"}, "double_axe", "main")
        self.assertEqual((new, sorted(removed)), ({"main": "double_axe", "off": None}, ["axe", "buckler"]))
        new, removed = equip("Fighter", {"main": "double_axe", "off": None}, "round_shield", "off")
        self.assertEqual((new, removed), ({"main": None, "off": "round_shield"}, ["double_axe"]))
        with self.assertRaises(ValueError):
            equip("Fighter", {"main": None, "off": None}, "staff", "off")
        with self.assertRaises(ValueError):
            equip("Fighter", {"main": None, "off": None}, "buckler", "main")

    def test_right_click_equips_and_the_replaced_item_goes_back_to_the_backpack(self):
        world, p = solo("Fighter", items=["axe", "axe", "round_shield", "double_axe"])
        h = p.hero
        use(world, "axe", p)
        use(world, "axe", p)
        self.assertEqual(h.equipment, {"main": "axe", "off": "axe"})
        use(world, "round_shield", p)                             # shield replaces the off-hand axe
        self.assertEqual(h.equipment, {"main": "axe", "off": "round_shield"})
        use(world, "double_axe", p)                               # 2h: both hands come off
        self.assertEqual(h.equipment, {"main": "double_axe", "off": None})
        self.assertEqual((p.inventory.count("axe"), p.inventory.count("round_shield"),
                          p.inventory.count("double_axe")), (2, 1, 0))

    def test_unequip_and_full_backpack(self):
        from game.engine.inventory import SIZE
        world, p = solo("Fighter", equipment={"main": "axe", "off": "buckler"})
        world.submit(C.Unequip("off"), 0)
        world.step(DT)
        self.assertEqual(p.hero.equipment, {"main": "axe", "off": None})
        self.assertEqual(p.inventory.count("buckler"), 1)
        self.assertAlmostEqual(p.hero.block_chance, 0.0)
        p.inventory.slots = [{"item": "bread", "count": 1}] * SIZE
        world.submit(C.Unequip("main"), 0)                        # no room: stays equipped
        world.step(DT)
        self.assertEqual(p.hero.equipment["main"], "axe")
        p.inventory.slots = [{"item": "bread", "count": 1}] * (SIZE - 1) + [{"item": "double_axe", "count": 1}]
        world.submit(C.UseItem(SIZE - 1), 0)                      # the axe can go into the freed slot: works
        world.step(DT)
        self.assertEqual(p.hero.equipment["main"], "double_axe")

    def test_companions_cannot_be_given_commands(self):
        world, p = solo("Fighter")
        world.submit(C.ToggleCompanion("Cleric"), 0)
        world.step(DT)
        comp = world.companions[0]
        comp.inventory.add("wand")
        comp.handle(C.UseItem(0))                                 # companions ignore item commands
        self.assertEqual(comp.hero.equipment, {"main": None, "off": None})


class BlockTest(unittest.TestCase):
    def setUp(self):
        random.seed(3)
        self.world, self.p = create_world(MAP, saves.blank_character("t", "Fighter", level=10))
        self.m = next(m for m in self.world.game_state.monsters if m.alive)
        self.h = self.p.hero
        self.m.x, self.m.y = self.h.x + 20, self.h.y

    def test_blocked_swing_does_no_damage(self):
        self.p._set_equipment({"main": None, "off": "buckler"})
        self.h._gear = dict(self.h._gear, block=1.0)              # always block
        hp = self.h.hp
        self.m.swing_timer = 0
        self.assertEqual(self.m.try_basic_attack(self.h), 0.0)
        self.assertTrue(self.m.last_blocked)
        self.assertEqual(self.h.hp, hp)

    def test_no_shield_never_blocks_and_uses_no_random_numbers(self):
        state = random.getstate()
        self.assertFalse(self.h.try_block())
        self.assertEqual(random.getstate(), state)

    def test_arrows_can_be_blocked(self):
        from game.engine.entities import Projectile
        self.p._set_equipment({"main": None, "off": "buckler"})
        self.h._gear = dict(self.h._gear, block=1.0)
        hp = self.h.hp
        proj = Projectile(x=self.h.x + 10, y=self.h.y, target=self.h, damage=50, source=self.m, blockable=True)
        self.assertEqual(proj.update(DT), (0.0, self.h))
        self.assertTrue(proj.blocked)
        self.assertEqual(self.h.hp, hp)

    def test_block_rate(self):
        self.p._set_equipment({"main": None, "off": "buckler"})
        rnd = random.Random(5)
        orig = random.random
        random.random = rnd.random
        try:
            n = 20000
            got = sum(self.h.try_block() for _ in range(n))
        finally:
            random.random = orig
        self.assertAlmostEqual(got / n, 0.10, delta=0.01)


class SaveSnapshotTest(unittest.TestCase):
    def test_new_characters_get_their_iconic_weapon_in_the_backpack(self):
        for cls, item in ICONIC.items():
            ch = saves.blank_character("t", cls)
            self.assertIn({"slot": 1, "item": item, "count": 1}, ch["inventory"])
            self.assertEqual(ch["equipment"], {"main": None, "off": None})

    def test_equipment_round_trips_through_a_save(self):
        d = tempfile.mkdtemp()
        ch = saves.blank_character("gear", "Rogue")
        ch["equipment"] = {"main": "dagger", "off": "dagger"}
        saves.save_character(ch, d)
        random.seed(1)
        world, p = create_world(MAP, saves.load_character("gear", d))
        self.assertEqual(p.hero.equipment, {"main": "dagger", "off": "dagger"})
        self.assertAlmostEqual(p.hero.base_damage, 4 + 1 + 0.5)

    def test_broken_saved_equipment_starts_bare_handed(self):
        world, p = solo("Wizard", equipment={"main": "dagger", "off": "dagger"})   # Wizards can't dual wield
        self.assertEqual(p.hero.equipment, {"main": None, "off": None})

    def test_remote_characters_bring_validated_equipment(self):
        base = {"name": "kid", "class_name": "Fighter", "level": 3, "xp": 0, "gold": 0, "kills": 0}
        ok = sanitize_character({**base, "equipment": {"main": "axe", "off": "axe"}})
        self.assertEqual(ok["equipment"], {"main": "axe", "off": "axe"})
        self.assertEqual(sanitize_character(base)["equipment"], {"main": None, "off": None})
        for bad in ({"main": "gold_bar"}, {"main": "buckler"}, {"main": "staff", "off": "buckler"}, "axe",
                    {"main": "axe", "hat": "axe"}):
            with self.assertRaises(ValueError, msg=bad):
                sanitize_character({**base, "equipment": bad})
        with self.assertRaises(ValueError):
            validate_equipment({"main": "dagger", "off": "dagger"}, "Cleric")

    def test_snapshot_has_equipment_stats_and_progress(self):
        world, p = solo("Paladin", equipment={"main": "warhammer", "off": None})
        snap = make_snapshot(world)
        you = snap["you"]
        self.assertEqual(you["equipment"], {"main": "warhammer", "off": None})
        self.assertEqual(you["progress"]["equipment"], {"main": "warhammer", "off": None})
        me = next(e for e in snap["entities"] if e["kind"] == "hero")
        self.assertEqual(me["equipment"], ["warhammer", None])
        st = you["stats"]
        self.assertEqual((st["swing"], st["weight"], st["block"]), (2.2, 10, 0.0))
        self.assertAlmostEqual(st["move_speed"], 81.0)
        hit = p.hero.abilities["Q"].calc_damage(1.5 * 52.5 + 6)
        self.assertAlmostEqual(st["hit"], hit)
        self.assertAlmostEqual(st["dps"], hit * 1.05 / 2.2)

    def test_command_round_trip(self):
        self.assertEqual(C.from_dict(C.to_dict(C.Unequip("off"))), C.Unequip("off"))


class CharacterWindowInputTest(unittest.TestCase):
    def test_c_opens_the_window_and_right_click_on_a_slot_unequips(self):
        """Headless pygame client: equip the iconic weapon from the backpack (B, right-click slot 1), open the
        character window (C), right-click its main-hand slot -> UseItem(1) then Unequip("main")."""
        from game.engine import replay
        with tempfile.TemporaryDirectory() as d:
            script, rec = os.path.join(d, "s.json"), os.path.join(d, "rec.json")
            with open(script, "w") as f:
                json.dump([{"tick": 0, "type": "key", "key": "p"},
                           {"tick": 2, "type": "key", "key": "b"},
                           {"tick": 4, "type": "click", "button": 3, "at": {"backpack_slot": 1}},
                           {"tick": 6, "type": "key", "key": "c"},
                           {"tick": 8, "type": "click", "button": 3, "at": {"equip_slot": "main"}},
                           {"tick": 10, "type": "click", "button": 1, "at": {"equip_slot": "off"}}], f)
            r = subprocess.run([sys.executable, "-m", "game.main", "--headless", "--seed", "3", "--max-time", "1",
                                "--hero", "0", "--map", MAP, "--input-script", script, "--record-commands", rec,
                                "--no-companion"],
                               cwd=ROOT, capture_output=True, text=True, timeout=60)
            self.assertEqual(r.returncode, 0, r.stderr[-1500:])
            cmds = [c["cmd"] for c in replay.load_recording(rec)["commands"]]
        self.assertIn({"type": "UseItem", "slot": 1}, cmds)
        self.assertIn({"type": "Unequip", "slot": "main"}, cmds)
        self.assertFalse([c for c in cmds if c["type"] in ("MoveTo", "SelectTarget", "Cast", "SetTarget")])


if __name__ == "__main__":
    unittest.main()
