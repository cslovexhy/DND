"""The map editor's Quests & NPCs screen: quest file helpers and validation, and the panel driven by clicks."""
import json
import os
import subprocess
import sys
import tempfile
import unittest

from game import quests
from game.content import monster_defs
from tests import mob_ids as ID

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NPCS = {"deputy_willem", "marshal_mcbride", "far_away_npc"}
MONSTERS = {1, 2, 5}


def good():
    return {"quests": [
        {"id": "a", "title": "A", "description": "x", "objectives": [{"monster": 1, "count": 3}], "rewards_xp": 1,
         "rewards_gold": 2, "giver": "deputy_willem", "level_req": 1, "prerequisites": []},
        {"id": "b", "title": "B", "description": "", "objectives": [], "rewards_xp": 0, "rewards_gold": 0,
         "giver": "marshal_mcbride", "turn_in": "deputy_willem", "reward_npc": "far_away_npc", "level_req": 2,
         "prerequisites": ["a"]}]}


class QuestDataTest(unittest.TestCase):
    def check(self, d):
        return quests.validate_quest_data(d, NPCS, MONSTERS, {7})

    def test_a_good_file(self):
        self.assertEqual(self.check(good()), [])

    def test_bad_files(self):
        def edit(fn):
            d = good()
            fn(d)
            return d
        bad = {"giver": edit(lambda d: d["quests"][0].update(giver="nobody")),
               "turn in": edit(lambda d: d["quests"][1].update(turn_in="nobody")),
               "reward npc": edit(lambda d: d["quests"][1].update(reward_npc="nobody")),
               "monster": edit(lambda d: d["quests"][0]["objectives"][0].update(monster=99)),
               "count": edit(lambda d: d["quests"][0]["objectives"][0].update(count=0)),
               "twice": edit(lambda d: d["quests"][0]["objectives"].append({"monster": 1, "count": 1})),
               "item": edit(lambda d: d["quests"][0]["objectives"].append({"item": 99, "count": 1})),
               "both": edit(lambda d: d["quests"][0]["objectives"].append({"item": 7, "monster": 1, "count": 1})),
               "prereq": edit(lambda d: d["quests"][1].update(prerequisites=["zzz"])),
               "self prereq": edit(lambda d: d["quests"][1].update(prerequisites=["b"])),
               "circle": edit(lambda d: d["quests"][0].update(prerequisites=["b"])),
               "level": edit(lambda d: d["quests"][0].update(level_req=0)),
               "title": edit(lambda d: d["quests"][0].update(title=" ")),
               "dup id": edit(lambda d: d["quests"][1].update(id="a"))}
        for what, d in bad.items():
            self.assertTrue(self.check(d), what)

    def test_kill_and_item_objectives_can_be_mixed(self):
        d = good()
        d["quests"][0]["objectives"].append({"item": 7, "count": 2})
        self.assertEqual(self.check(d), [])

    def test_topological_order(self):
        qs = [{"id": "c", "prerequisites": ["b"]}, {"id": "b", "prerequisites": ["a"]}, {"id": "a"}, {"id": "d"}]
        ordered, cyclic = quests.topo_order(qs)
        self.assertEqual([q["id"] for q in ordered], ["a", "d", "b", "c"])
        self.assertEqual(cyclic, [])
        ordered, cyclic = quests.topo_order([{"id": "x", "prerequisites": ["y"]}, {"id": "y", "prerequisites": ["x"]},
                                             {"id": "z"}])
        self.assertEqual(([q["id"] for q in ordered], [q["id"] for q in cyclic]), (["z"], ["x", "y"]))

    def test_slug_is_unique(self):
        self.assertEqual(quests.quest_slug("Kobold Camp: Cleanup!", set()), "kobold_camp_cleanup")
        self.assertEqual(quests.quest_slug("A", {"a", "a_2"}), "a_3")
        self.assertEqual(quests.quest_slug("!!!", set()), "quest")

    def test_save_and_load_round_trip(self):
        path = os.path.join(tempfile.mkdtemp(), "quests.json")
        self.assertEqual(quests.load_quest_data(path), {"version": 2, "quests": []})
        quests.save_quest_data(good(), path)
        self.assertEqual(quests.load_quest_data(path)["quests"], good()["quests"])
        log = quests.load_quest_log(path=path)
        self.assertEqual(log.available_for_npc("deputy_willem", 1), ["a"])
        self.assertEqual((log.quests["b"].turn_in, log.quests["b"].reward_npc), ("deputy_willem", "far_away_npc"))
        self.assertEqual((log.quests["a"].turn_in, log.quests["a"].reward_npc), ("deputy_willem", "deputy_willem"))

    def test_the_real_quest_file_is_valid(self):
        self.assertEqual(quests.validate_quest_data(quests.load_quest_data(), set(quests.npc_directory(refresh=True)),
                                                    set(monster_defs.load())), [])

    def test_npc_ids_are_unique_across_maps(self):
        seen = {}
        for name, data in monster_defs.map_files().items():
            for n in data.get("npcs", []):
                self.assertNotIn(n["npc_id"], seen, f"{n['npc_id']} is on {name} and {seen.get(n['npc_id'])}")
                seen[n["npc_id"]] = name


class StoryPanelTest(unittest.TestCase):
    CODE = """
import os, json; os.environ["SDL_VIDEODRIVER"] = "dummy"
import pygame; pygame.init(); screen = pygame.display.set_mode((1400, 900))
from game.content import monster_defs
from game.editor.monster_panel import Art
from game.editor.story_panel import StoryPanel
def q(i, title, giver, pre=(), obj=()):
    return {"id": i, "title": title, "description": "", "objectives": list(obj), "rewards_xp": 10, "rewards_gold": 1,
            "giver": giver, "turn_in": giver, "reward_npc": giver, "level_req": 1, "prerequisites": list(pre)}
data = {"quests": [q("third", "Third", "marshal", ["second"]), q("second", "Second", "marshal", ["first"],
                                                                   [{"monster": 1, "count": 10}]),
                   q("first", "First", "deputy")]}
def npc(i, name, x, **kw):
    return dict({"name": name, "npc_id": i, "gender": "male", "x": x, "y": 5, "sprite_col": 1, "sprite_row": 8}, **kw)
npcs = [npc("deputy", "Deputy", 1), npc("marshal", "Marshal", 2)]
others = {"clerk": {"name": "Clerk", "map": "stormwind", "sprite_col": 2, "sprite_row": 8}}
answers = iter(%(answers)r)
saved = {}
p = StoryPanel(npcs, data, monster_defs.load(), lambda t, d, long=False: next(answers), Art(), (80, 80),
               quest_save=lambda d: saved.update(d), other_npcs=others)
font = pygame.font.SysFont("monospace", 13); big = pygame.font.SysFont("monospace", 18, bold=True)
def click(action, arg=None, button=1):
    p.draw(screen, font, big)
    r = next(r for r, a, x in p.hits if a == action and (arg is None or x == arg))
    p.click(r.center, button)
log = {}
p.draw(screen, font, big)
log["order"] = [x["id"] for x in p.ordered_quests()]                  # dependency order, not file order
# objectives: add two more monsters, change a count, drop the old one
click("q_select", "second")
click("obj_add"); p.draw(screen, font, big); click("obj_pick", 27)
click("obj_add"); click("obj_pick", 28)
click("obj_count", 1)                                                  # the second one: 10 -> 4
click("obj_del", 0)
log["objectives"] = p.q["objectives"]
click("q_field", "title"); click("q_field", "rewards_xp"); click("q_field", "level_req"); click("q_field", "level_req")
log["bad_level_msg"] = p.message
click("q_field", "description")
# A-B-C: given by the marshal, handed in at a clerk on another map, paid by the deputy
click("q_field", "turn_in"); p.draw(screen, font, big); click("npc_pick", "clerk")
log["reward_followed_turn_in"] = p.q["reward_npc"]
click("q_field", "reward_npc"); click("npc_pick", "deputy")
# the giver moves: whatever was still the same NPC follows
click("q_select", "first")
click("q_field", "giver"); click("npc_pick", "marshal")
log["first"] = dict(p.q)
# circular dependencies are refused
click("q_prereq", "third")
log["cycle_msg"] = p.message; log["first_pre"] = p.q["prerequisites"]
# a new quest needing "third"
click("q_new"); new = p.selected
click("q_prereq", "third")
log["order2"] = [x["id"] for x in p.ordered_quests()]
click("tab", "npcs")
click("n_new"); click("n_pick", {"sheet": "dungeon", "col": 5, "row": 4})
click("n_field", "role"); click("n_field", "role"); click("n_field", "shop")
click("n_field", "pos"); log["pos_msg"] = p.message
click("n_field", "pos")
click("n_select", 0); click("n_delete"); log["delete_msg"] = p.message           # the deputy still pays a quest
click("tab", "quests")
click("q_select", "third")
click("q_delete")
log["after_delete"] = [x["id"] for x in p.ordered_quests()]
click("done"); assert p.done, p.message
log["saved"] = {x["id"]: x for x in saved["quests"]}
log["new_id"] = new
log["npc"] = p.npcs[-1]
print(json.dumps(log))
"""

    def test_edit_quests_and_npcs_by_clicking(self):
        answers = ["4",                         # second: 4 of monster 27
                   "Second Part",               # title
                   "500",                       # xp
                   "7",                         # level 7
                   "99",                        # level 99: refused
                   "Go and kill them.",         # description
                   "Chieftain Hunt",            # new quest
                   "Old Smith",                 # new NPC
                   "x,y",                       # position typed wrong
                   "50,60"]                     # position
        r = subprocess.run([sys.executable, "-c", self.CODE % {"answers": answers}], cwd=ROOT, capture_output=True,
                           text=True, timeout=90)
        self.assertEqual(r.returncode, 0, r.stderr[-2500:])
        log = json.loads(r.stdout.strip().splitlines()[-1])
        self.assertEqual(log["order"], ["first", "second", "third"])
        self.assertEqual(log["objectives"], [{"monster": 27, "count": 4}, {"monster": 28, "count": 10}])
        self.assertIn("1-30", log["bad_level_msg"])
        second = log["saved"]["second"]
        self.assertEqual((second["title"], second["rewards_xp"], second["level_req"], second["description"]),
                         ("Second Part", 500, 7, "Go and kill them."))
        self.assertEqual(log["reward_followed_turn_in"], "clerk")             # it was the same NPC: moves along
        self.assertEqual((second["giver"], second["turn_in"], second["reward_npc"]), ("marshal", "clerk", "deputy"))
        first = log["first"]
        self.assertEqual((first["giver"], first["turn_in"], first["reward_npc"]), ("marshal",) * 3)
        self.assertIn("already needs", log["cycle_msg"])
        self.assertEqual(log["first_pre"], [])
        self.assertEqual(log["order2"], ["first", "second", "third", log["new_id"]])
        new = log["saved"][log["new_id"]]
        self.assertEqual((log["new_id"], new["prerequisites"], new["giver"]), ("chieftain_hunt", [], "deputy"))     # "third" was deleted: no longer needed
        npc = log["npc"]
        self.assertEqual((npc["name"], npc["npc_id"], npc["role"], npc["x"], npc["y"], npc["sprite_col"],
                          npc["sprite_row"]), ("Old Smith", "old_smith", "vendor", 50, 60, 5, 4))
        self.assertIn("used by", log["delete_msg"])
        self.assertNotIn("third", log["saved"])
        self.assertEqual(log["after_delete"], ["first", log["new_id"], "second"])    # it needs nothing now


if __name__ == "__main__":
    unittest.main()
