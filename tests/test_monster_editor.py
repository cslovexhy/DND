"""Custom monster types (map editor Monsters screen -> data/custom_monsters.json -> the game): validation, merging into
the monster tables, spawning with a per-map level range, skills, drops, ranged AI, the picture sent to clients; and
the editor's Monsters panel driven by clicks."""
import json
import os
import random
import subprocess
import sys
import tempfile
import unittest

from game import saves
from game.content import monster_defs
from game.content import monsters as M
from game.content.items import ITEMS
from game.content.skill_library import SKILLS
from game.engine.bootstrap import create_world
from game.engine.snapshot import make_snapshot
from game.engine.world_map import SpawnPoint

MAP = "data/maps/northshire.json"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
saves.SAVE_DIR = tempfile.mkdtemp()


def murloc(**over):
    d = monster_defs.new_definition("Murloc Raider")
    d.update({"sprite": {"sheet": "creatures", "col": 6, "row": 2}, "category": "beast", "ac": 13, "speed": 6,
              "skills": ["Frost Nova"], "drops": [["water", 0.5], ["elven_nectar", 1.0, 10, 20]]})
    d.update(over)
    return d


class DefinitionTest(unittest.TestCase):
    def check(self, d, tid="murloc_raider"):
        return monster_defs.validate(tid, d, SKILLS, ITEMS, M.BUILTIN_TYPES)

    def test_a_good_definition(self):
        self.assertEqual(self.check(murloc()), [])

    def test_bad_definitions(self):
        bad = {"name": murloc(name=""), "sprite": murloc(sprite={"sheet": "creatures", "col": 99, "row": 0}),
               "category": murloc(category="robot"), "attack": murloc(attack="magic"),
               "ac": murloc(ac=99), "speed": murloc(speed=0), "hp_mult": murloc(hp_mult=True),
               "skills": murloc(skills=["Teleport"]), "drops": murloc(drops=[["gold_bar", 0.1]]),
               "chance": murloc(drops=[["water", 2]]), "drop levels": murloc(drops=[["water", 0.1, 5, 2]])}
        for what, d in bad.items():
            self.assertTrue(self.check(d), what)
        self.assertTrue(self.check(murloc(), tid="grey_wolf"))         # can't replace a built-in type
        self.assertTrue(self.check(murloc(), tid="Bad Id"))

    def test_ids_and_round_trip(self):
        self.assertEqual(monster_defs.type_id_for("Murloc Raider!", {"murloc_raider"}), "murloc_raider_2")
        path = os.path.join(tempfile.mkdtemp(), "m.json")
        self.assertEqual(monster_defs.load(path), {})
        monster_defs.save({"murloc_raider": murloc()}, path)
        self.assertEqual(monster_defs.load(path), {"murloc_raider": murloc()})

    def test_the_old_board_game_monster_list_is_not_touched(self):
        self.assertTrue(monster_defs.CUSTOM_PATH.endswith(os.path.join("data", "custom_monsters.json")))


class CustomMonsterInGameTest(unittest.TestCase):
    def setUp(self):
        self.added = M.register_custom({"murloc_raider": murloc(), "murloc_archer": murloc(name="Murloc Archer",
                                                                                          attack="ranged",
                                                                                          skills=[], drops=[]),
                                        "broken": {"name": ""}})

    def tearDown(self):
        M.unregister_custom(self.added)

    def test_registered_into_the_monster_tables(self):
        self.assertEqual(sorted(self.added), ["murloc_archer", "murloc_raider"])   # the broken one is skipped
        s = M.SPAWN_STATS["murloc_raider"]
        self.assertEqual((s["name"], s["ac"], s["speed"], s["kit"]), ("Murloc Raider", 13, 6, ["Frost Nova"]))
        self.assertEqual(M.MONSTER_CATEGORY["murloc_raider"], "beast")
        self.assertEqual(M.MONSTER_DROPS["murloc_raider"], [("water", 0.5), ("elven_nectar", 1.0, 10, 20)])

    def spawn(self, tid, levels=(2, 4)):
        random.seed(3)
        world, p = create_world(MAP, saves.blank_character("t", "Fighter", level=5))
        world.world_map.data.setdefault("monster_levels", {})[tid] = list(levels)
        m = world.spawn_single_world_monster(SpawnPoint(tid, 30, 30))
        world.game_state.monsters.append(m)
        return world, p, m

    def test_spawns_with_its_map_level_range_skills_and_drops(self):
        world, p, m = self.spawn("murloc_raider", (2, 4))
        self.assertEqual(m.name, "Murloc Raider")
        self.assertTrue(m.leveled and 2 <= m.level <= 4)
        self.assertEqual(m.max_hp, M.hp_for_level(m.level))
        self.assertIn("Frost Nova", m.abilities)
        self.assertEqual(m.category, "beast")
        from game.content.items import roll_drops

        class Always:
            def random(self):
                return 0.0
        self.assertEqual(roll_drops(m.drops, m.level, Always()), ["water"])   # nectar only from levels 10-20
        self.assertEqual(roll_drops(m.drops, 15, Always()), ["water", "elven_nectar"])

    def test_ranged_custom_type_uses_the_ranged_ai(self):
        from game.engine import ai
        world, p, m = self.spawn("murloc_archer")
        self.assertGreater(m.ranged_attack_range, 0)
        self.assertEqual(m.attack_range, 220)
        m.x, m.y = p.hero.x + 150, p.hero.y
        ai.aggro_monster(m, p.hero, world.game_state.monsters)
        m.swing_timer = 0
        res = ai.run_monster_ai(m, [p.hero], 1 / 30, world.is_wall, all_monsters=world.game_state.monsters)
        self.assertEqual(res[0], "ranged_attack_projectile")             # shoots from 150 px instead of walking in

    def test_clients_are_told_which_picture_to_draw(self):
        world, p, m = self.spawn("murloc_raider")
        d = next(e for e in make_snapshot(world)["entities"] if e["id"] == m.eid)
        self.assertEqual(d["art"], {"sheet": "creatures", "col": 6, "row": 2})
        wolf = next(e for e in make_snapshot(world)["entities"] if e.get("name") == "Grey Wolf")
        self.assertNotIn("art", wolf)                                  # built-ins: the client knows them

    def test_map_validation_knows_custom_types(self):
        from game.engine.map_schema import validate_map
        with open(os.path.join(ROOT, MAP)) as f:
            data = json.load(f)
        data["spawns"].append({"type": "murloc_raider", "x": 30, "y": 30})
        errors, warnings = validate_map(data, set(M.SPAWN_STATS))
        self.assertEqual(errors, [])
        self.assertFalse([w for w in warnings if "murloc" in w])


class EditorPanelTest(unittest.TestCase):
    def test_create_a_monster_type_by_clicking(self):
        """The Monsters panel (game/editor/monster_panel.py), offscreen: new type, picture, level range, category,
        skills, drops with a chance and a level range, Done -> data file; Esc in run() drops edits."""
        out = os.path.join(tempfile.mkdtemp(), "custom.json")
        code = f"""
import os, json; os.environ["SDL_VIDEODRIVER"] = "dummy"
import pygame; pygame.init(); screen = pygame.display.set_mode((1400, 900))
from game.editor.monster_panel import MonsterPanel, spawn_palette
answers = iter(["Murloc Raider", "2-4", "10-20", "3", "abc"])
levels = {{"human_cultist": [3, 4]}}
p = MonsterPanel({{}}, levels, lambda t, d: next(answers), path={out!r})
font = pygame.font.SysFont("monospace", 13); big = pygame.font.SysFont("monospace", 18, bold=True)
def click(action, arg=None, button=1):
    p.draw(screen, font, big)
    r = next(r for r, a, x in p.hits if a == action and (arg is None or x == arg))
    p.click(r.center, button)
click("new")
assert p.mode == "sprite"
click("pick_sprite", {{"sheet": "creatures", "col": 6, "row": 2}})
click("levels")
click("cycle", "category")
click("toggle", "boss")
click("skill", "Frost Nova"); click("skill", "Poison Dagger"); click("skill", "Poison Dagger")
click("add_drop"); click("pick_item", "water")
click("add_drop"); click("pick_item", "elven_nectar")
click("drop_levels", 1)
click("drop_chance", 0)
click("number", "ac")                     # "abc": refused, AC stays 14
click("add_drop"); click("pick_item", "bread"); click("drop_chance", 2, button=3)   # right-click removes
click("done")
assert p.done, p.message
saved = json.load(open({out!r}))["monsters"]
names = [s["name"] for s in spawn_palette(saved)]
print(json.dumps({{"saved": saved, "levels": levels, "panel_levels": p.levels, "palette_has": "Murloc Raider (Boss) *" in names}}))
"""
        r = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr[-2000:])
        res = json.loads(r.stdout.strip().splitlines()[-1])
        d = res["saved"]["murloc_raider"]
        self.assertEqual(d["sprite"], {"sheet": "creatures", "col": 6, "row": 2})
        self.assertEqual((d["category"], d["boss"], d["ac"]), ("beast", True, 14))
        self.assertEqual(d["skills"], ["Frost Nova"])
        self.assertEqual(d["drops"], [["water", 0.03], ["elven_nectar", 0.01, 10, 20]])
        self.assertEqual(res["panel_levels"], {"human_cultist": [3, 4], "murloc_raider": [2, 4]})
        self.assertTrue(res["palette_has"])

    def test_parse_levels(self):
        code = """
import os; os.environ["SDL_VIDEODRIVER"] = "dummy"
from game.editor.monster_panel import MonsterPanel as P
assert P.parse_levels("3-5") == [3, 5] and P.parse_levels(" 4 ") == [4, 4] and P.parse_levels("") is None
for bad in ("5-3", "0-2", "x", "1-40"):
    try:
        P.parse_levels(bad); raise SystemExit("accepted " + bad)
    except ValueError:
        pass
print("OK")
"""
        r = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, timeout=60)
        self.assertIn("OK", r.stdout, r.stderr[-1500:])


if __name__ == "__main__":
    unittest.main()
