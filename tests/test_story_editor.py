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
NPCS = {"deputy_willem", "marshal_mcbride"}
MONSTERS = {1, 2, 5}


def good():
    return {"map": "t", "quests": [
        {"id": "a", "title": "A", "description": "x", "objectives": [{"monster": 1, "count": 3}], "rewards_xp": 1,
         "rewards_gold": 2, "npc_id": "deputy_willem", "level_req": 1, "prerequisites": []},
        {"id": "b", "title": "B", "description": "", "objectives": [], "rewards_xp": 0, "rewards_gold": 0,
         "npc_id": "marshal_mcbride", "level_req": 2, "prerequisites": ["a"]}],
        "questlines": [["a", "b"]]}


class QuestDataTest(unittest.TestCase):
    def check(self, d):
        return quests.validate_quest_data(d, NPCS, MONSTERS)

    def test_a_good_file(self):
        self.assertEqual(self.check(good()), [])

    def test_bad_files(self):
        def edit(fn):
            d = good()
            fn(d)
            return d
        bad = {"giver": edit(lambda d: d["quests"][0].update(npc_id="nobody")),
               "monster": edit(lambda d: d["quests"][0]["objectives"][0].update(monster=99)),
               "count": edit(lambda d: d["quests"][0]["objectives"][0].update(count=0)),
               "twice": edit(lambda d: d["quests"][0]["objectives"].append({"monster": 1, "count": 1})),
               "prereq": edit(lambda d: d["quests"][1].update(prerequisites=["zzz"])),
               "self prereq": edit(lambda d: d["quests"][1].update(prerequisites=["b"])),
               "level": edit(lambda d: d["quests"][0].update(level_req=0)),
               "title": edit(lambda d: d["quests"][0].update(title=" ")),
               "line": edit(lambda d: d["questlines"].append(["a"])),
               "unknown in line": edit(lambda d: d["questlines"].append(["q"])),
               "dup id": edit(lambda d: d["quests"][1].update(id="a"))}
        for what, d in bad.items():
            self.assertTrue(self.check(d), what)

    def test_slug_is_unique(self):
        self.assertEqual(quests.quest_slug("Kobold Camp: Cleanup!", set()), "kobold_camp_cleanup")
        self.assertEqual(quests.quest_slug("A", {"a", "a_2"}), "a_3")
        self.assertEqual(quests.quest_slug("!!!", set()), "quest")

    def test_save_and_load_round_trip(self):
        d = tempfile.mkdtemp()
        self.assertEqual(quests.load_quest_data("none", d), {"map": "none", "quests": [], "questlines": []})
        quests.save_quest_data("t", good(), d)
        self.assertEqual(quests.load_quest_data("t", d), good())
        log = quests.load_quest_log("t", d)
        self.assertEqual(log.available_for_npc("deputy_willem", 1), ["a"])

    def test_the_real_quest_file_is_valid(self):
        with open(os.path.join(ROOT, "data", "maps", "northshire.json")) as f:
            npcs = {n["npc_id"] for n in json.load(f)["npcs"]}
        self.assertEqual(quests.validate_quest_data(quests.load_quest_data("northshire"), npcs,
                                                    set(monster_defs.load())), [])


class StoryPanelTest(unittest.TestCase):
    CODE = """
import os, json; os.environ["SDL_VIDEODRIVER"] = "dummy"
import pygame; pygame.init(); screen = pygame.display.set_mode((1400, 900))
from game import quests
from game.content import monster_defs
from game.editor.monster_panel import Art
from game.editor.story_panel import StoryPanel
data = quests.load_quest_data("northshire")
npcs = json.load(open("data/maps/northshire.json"))["npcs"]
answers = iter(%(answers)r)
saved = {}
p = StoryPanel(npcs, data, monster_defs.load(), lambda t, d, long=False: next(answers), Art(), (80, 80),
               quest_save=lambda d: saved.update(d))
font = pygame.font.SysFont("monospace", 13); big = pygame.font.SysFont("monospace", 18, bold=True)
def click(action, arg=None, button=1):
    p.draw(screen, font, big)
    r = next(r for r, a, x in p.hits if a == action and (arg is None or x == arg))
    p.click(r.center, button)
log = {}
p.draw(screen, font, big)
# quests: hook two more monsters into the echo ridge quest, raise the count, drop the old one
click("q_select", "investigate_echo_ridge")
click("obj_add"); p.draw(screen, font, big); click("obj_pick", 27)
click("obj_add"); click("obj_pick", 28)
click("obj_count", 1)                                   # the kobold workers: 10 -> 4
click("obj_del", 0)
log["objectives"] = p.q["objectives"]
click("q_field", "title"); click("q_field", "rewards_xp"); click("q_field", "level_req"); click("q_field", "level_req")
log["bad_level_msg"] = p.message
click("q_field", "description")
# a new quest, offered by the next NPC, after the echo ridge one, needing it
click("q_new"); new = p.selected
click("q_field", "npc_id")
click("q_prereq", "skirmish_at_echo_ridge")
click("q_line"); log["line_after_click"] = p.line_of(new)             # leaves its own line -> none
click("q_line"); click("q_line")                                       # -> line 1 -> line 2
click("q_move", -1)
click("tab", "npcs")
click("n_new"); click("n_pick", {"sheet": "dungeon", "col": 5, "row": 4})
click("n_field", "role"); click("n_field", "role"); click("n_field", "shop")
click("n_field", "pos"); log["pos_msg"] = p.message
click("n_field", "pos")
click("n_select", 0); click("n_delete"); log["delete_msg"] = p.message
click("tab", "quests")
click("q_select", "a_threat_within")
click("q_delete")
click("done"); assert p.done, p.message
log["saved_ids"] = [q["id"] for q in saved["quests"]]
log["lines"] = saved["questlines"]
log["quest"] = next(q for q in saved["quests"] if q["id"] == "investigate_echo_ridge")
log["new"] = next(q for q in saved["quests"] if q["id"] == new)
log["new_id"] = new
log["npc"] = p.npcs[-1]
print(json.dumps(log))
"""

    def test_edit_quests_and_npcs_by_clicking(self):
        answers = ["4",                         # echo ridge: 4 kobold workers
                   "Echo Ridge Part Two",       # title
                   "500",                       # xp
                   "7",                         # level 7
                   "99",                        # level 99: refused
                   "Go and kill them.",         # description
                   "Kobold Chieftain Hunt",     # new quest
                   "Old Smith",                 # new NPC
                   "x,y",                       # position typed wrong
                   "50,60"]                     # position
        r = subprocess.run([sys.executable, "-c", self.CODE % {"answers": answers}], cwd=ROOT, capture_output=True,
                           text=True, timeout=90)
        self.assertEqual(r.returncode, 0, r.stderr[-2500:])
        log = json.loads(r.stdout.strip().splitlines()[-1])
        self.assertEqual(log["objectives"], [{"monster": 27, "count": 4}, {"monster": 28, "count": 10}])   # old one removed
        self.assertIn("1-30", log["bad_level_msg"])
        q = log["quest"]
        self.assertEqual((q["title"], q["rewards_xp"], q["level_req"], q["description"]),
                         ("Echo Ridge Part Two", 500, 7, "Go and kill them."))
        new = log["new"]
        self.assertEqual(log["new_id"], "kobold_chieftain_hunt")
        self.assertEqual(new["prerequisites"], ["skirmish_at_echo_ridge"])
        self.assertIsNone(log["line_after_click"])
        line = next(line for line in log["lines"] if log["new_id"] in line)
        self.assertEqual(line, ["brotherhood_of_thieves", log["new_id"], "bounty_on_garrick_padfoot"])   # moved up one
        self.assertEqual(log["new"]["npc_id"], "marshal_mcbride")              # cycled to the next NPC
        npc = log["npc"]
        self.assertEqual((npc["name"], npc["npc_id"], npc["role"], npc["x"], npc["y"], npc["sprite_col"],
                          npc["sprite_row"]), ("Old Smith", "old_smith", "vendor", 50, 60, 5, 4))
        self.assertIn("gives", log["delete_msg"])              # Deputy Willem still gives quests: refused
        self.assertNotIn("a_threat_within", log["saved_ids"])
        for line in log["lines"]:
            self.assertNotIn("a_threat_within", line)


if __name__ == "__main__":
    unittest.main()
