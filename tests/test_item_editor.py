"""The map editor's Items screen: item definition validation, and the panel driven by clicks."""
import json
import os
import subprocess
import sys
import tempfile
import unittest

from game.content import item_defs
from tests import item_ids as I

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class ItemDefsTest(unittest.TestCase):
    def test_every_shipped_item_is_valid_and_ids_are_numbers(self):
        for iid, d in item_defs.load().items():
            self.assertIsInstance(iid, int)
            self.assertEqual(item_defs.validate(iid, d), [], iid)

    def test_bad_items(self):
        base = item_defs.load()[I.BREAD]

        def with_(**kw):
            d = json.loads(json.dumps(base))
            d.update(kw)
            return d
        bad = {"name": with_(name=" "), "icon": with_(icon=["dungeon", 99, 0]), "sheet": with_(icon=["nope", 0, 0]),
               "kind": with_(kind="gem"), "price": with_(price=0), "buff key": with_(buff={"mana_regen_pct": 0.1}),
               "buff time": with_(buff={"damage_pct": 0.1}, buff_duration=0), "no heal": with_(heal=0),
               "food mana": with_(mana=5), "description": with_(description="x" * 400)}
        for what, d in bad.items():
            self.assertTrue(item_defs.validate(I.BREAD, d), what)
        weapon = json.loads(json.dumps(item_defs.load()[I.AXE]))
        for what, kw in {"hands": {"hands": "3h"}, "swing": {"swing": 0}, "a": {"a": 0}, "type": {"weapon_type": ""},
                         "weight": {"weight": 99}}.items():
            self.assertTrue(item_defs.validate(I.AXE, dict(weapon, **kw)), what)
        self.assertTrue(item_defs.validate(0, base))
        self.assertEqual(item_defs.validate(5, item_defs.new_definition("Wolf Meat", "misc")), [])

    def test_new_definitions_of_every_kind_are_valid(self):
        for kind in item_defs.KINDS:
            self.assertEqual(item_defs.validate(1, item_defs.new_definition("X", kind)), [], kind)

    def test_item_id_accepts_ids_and_old_names(self):
        self.assertEqual([item_defs.item_id(v) for v in (5, "5", "bread", "nope", None, True, [1])],
                         [5, 5, I.BREAD, None, None, None, None])

    def test_where_an_item_is_used(self):
        monsters = {1: {"name": "Wolf", "drops": [[I.BREAD, 0.1]]}}
        quests = [{"id": "q", "title": "Q", "objectives": [{"item": I.WATER, "count": 1}]}]
        maps = {"m": {"item_spawns": [{"item": I.COFFEE, "x": 1, "y": 1}]}}
        self.assertEqual(item_defs.items_used_by(I.BREAD, monsters, quests, maps), ["drops of Wolf"])
        self.assertEqual(item_defs.items_used_by(I.WATER, monsters, quests, maps), ["quest Q"])
        self.assertEqual(item_defs.items_used_by(I.COFFEE, monsters, quests, maps), ["item spawns on m"])
        self.assertEqual(item_defs.items_used_by(I.WINE, monsters, quests, maps), [])


class ItemPanelTest(unittest.TestCase):
    CODE = """
import os, json; os.environ["SDL_VIDEODRIVER"] = "dummy"
import pygame; pygame.init(); screen = pygame.display.set_mode((1400, 900))
from game.content import item_defs
from game.editor.monster_panel import Art
from game.editor.item_panel import ItemPanel
defs = item_defs.load()
answers = iter(%(answers)r)
used = {2: ["drops of Wolf"]}
p = ItemPanel(defs, lambda t, d, long=False: next(answers), Art(), usage=lambda i: used.get(i, []), path=%(out)r)
font = pygame.font.SysFont("monospace", 13); big = pygame.font.SysFont("monospace", 18, bold=True)
def click(action, arg=None, button=1):
    p.draw(screen, font, big)
    r = next(r for r, a, x in p.hits if a == action and (arg is None or x == arg))
    p.click(r.center, button)
log = {}
first_new = defs.next_id
p.draw(screen, font, big)
# a new misc item: picture, name, price, description
click("new"); new = p.selected
click("pick_icon", ("rpg", 54, 17))
click("field", "price"); click("field", "name"); click("description")
log["new_id"] = new; log["first_new"] = first_new
# a food: change the kind of a copy of bread, set heal and a damage buff
click("select", 8); click("duplicate"); food = p.selected
click("field", "heal"); click("field", "buff.damage_pct"); click("field", "buff_duration")
log["buff"] = [dict(defs[food].get("buff", {})), defs[food].get("buff_duration")]
click("field", "buff.damage_pct"); log["buff_removed"] = "buff" not in defs[food]
# changing the kind resets what the item does (food -> weapon)
click("field", "kind"); log["kind_after_click"] = defs[food]["kind"]
click("field", "weapon_type"); click("field", "hands"); click("field", "swing"); click("field", "swing")
log["swing_msg"] = p.message
click("field", "b")
log["weapon2"] = dict(defs[food])
# delete rules: protected, used, free
click("select", 1); click("delete"); log["protected_msg"] = p.message
click("select", 2); click("delete"); log["used_msg"] = p.message
click("select", food); click("delete"); log["deleted"] = food not in defs
click("filter"); log["filter"] = p.kind_filter; log["filtered"] = [defs[i]["kind"] for i in p.shown()]
click("done"); assert p.done, p.message
saved = item_defs.load(%(out)r)
log["saved_ids"] = list(saved); log["next_id"] = saved.next_id; log["new"] = saved[new]
print(json.dumps(log))
"""

    def test_edit_items_by_clicking(self):
        out = os.path.join(tempfile.mkdtemp(), "items.json")
        answers = ["Wolf Meat",                 # new item
                   "25",                        # price
                   "Tough Wolf Meat",           # renamed
                   "Gathered from wolves.",     # description
                   "Bread 2",                   # name of the copy of bread
                   "10",                        # its heal
                   "15",                        # damage +15%
                   "5",                         # 5 minutes
                   "",                          # remove the buff again
                   "1.2",                       # weapon: swing 1.2
                   "0",                         # swing 0: refused
                   "7"]                         # flat damage 7
        r = subprocess.run([sys.executable, "-c", self.CODE % {"answers": answers, "out": out}], cwd=ROOT,
                           capture_output=True, text=True, timeout=90)
        self.assertEqual(r.returncode, 0, r.stderr[-2500:])
        log = json.loads(r.stdout.strip().splitlines()[-1])
        self.assertEqual(log["new_id"], log["first_new"])                       # the next number
        new = log["new"]
        self.assertEqual((new["name"], new["kind"], new["price"], new["icon"], new["description"]),
                         ("Tough Wolf Meat", "misc", 25, ["rpg", 54, 17], "Gathered from wolves."))
        self.assertEqual(log["buff"], [{"damage_pct": 0.15}, 300.0])
        self.assertTrue(log["buff_removed"])
        self.assertEqual(log["kind_after_click"], "weapon")
        w = log["weapon2"]
        self.assertEqual((w["kind"], w["swing"], w["b"], w["name"]), ("weapon", 1.2, 7, "Bread 2"))
        self.assertIn("must be", log["swing_msg"])
        self.assertIn("can't be deleted", log["protected_msg"])
        self.assertIn("used by", log["used_msg"])
        self.assertTrue(log["deleted"])
        self.assertEqual(log["next_id"], log["new_id"] + 2)                       # ids are never reused
        self.assertIn(log["new_id"], log["saved_ids"])
        self.assertEqual(log["filter"], "potion")
        self.assertEqual(set(log["filtered"]), {"potion"})


if __name__ == "__main__":
    unittest.main()
