"""Monster definitions (data/monsters.json, edited in the map editor's Monsters screen): the file format and its
validation, loading into the game's tables, spawning with a per-map level range / skills / own drop list / ranges, the
picture sent to clients; and the Monsters panel driven by clicks (create, duplicate, delete, filter, edit anything)."""
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


def check(d, tid="murloc_raider"):
    return monster_defs.validate(tid, d, SKILLS, ITEMS)


class DefinitionTest(unittest.TestCase):
    def test_a_good_definition(self):
        self.assertEqual(check(murloc()), [])

    def test_bad_definitions(self):
        bad = {"name": murloc(name=""), "sprite": murloc(sprite={"sheet": "creatures", "col": 99, "row": 0}),
               "category": murloc(category="robot"), "attack": murloc(attack="magic"),
               "ac": murloc(ac=99), "speed": murloc(speed=0), "hp_mult": murloc(hp_mult=True),
               "skills": murloc(skills=["Teleport"]), "drops": murloc(drops=[["gold_bar", 0.1]]),
               "chance": murloc(drops=[["water", 2]]), "drop levels": murloc(drops=[["water", 0.1, 5, 2]]),
               "duplicate drop": murloc(drops=[["water", 0.1], ["water", 0.2]]),
               "raw hp": murloc(hp=0), "attack range": murloc(attack_range=5), "swing": murloc(swing=0),
               "hive": murloc(hive_mind={"range": 1, "types": []}), "hive types": murloc(hive_mind={"range": 500, "types": [3]}),
               "boss skill": murloc(boss_skills={"fireball": {}}), "boss setting": murloc(boss_skills={"enrage": {"x": "a"}}),
               "whole number": murloc(ac=14.5), "file sprite": murloc(sprite={"file": "assets/nope.png"})}
        for what, d in bad.items():
            self.assertTrue(check(d), what)
        self.assertTrue(check(murloc(), tid="Bad Id"))

    def test_the_full_set_of_settings_is_valid(self):
        d = murloc(boss=True, unique=True, relentless=True, swing=1.2, respawn_mult=3, attack="ranged", sense_range=300,
                   attack_range=250, hp=10, dmg=3, xp=40, hive_mind={"range": 800, "types": ["murloc_raider"]},
                   boss_skills={k: json.loads(json.dumps(v)) for k, v in monster_defs.BOSS_SKILL_DEFAULTS.items()})
        self.assertEqual(check(d), [])
        s = monster_defs.to_spawn_stats(d)
        self.assertEqual((s["swing"], s["respawn_mult"], s["sense_range"], s["attack_range"], s["ranged"]),
                         (1.2, 3, 300, 250, True))
        self.assertEqual(s["hive_mind"], (800, ["murloc_raider"]))
        self.assertEqual(s["skills"]["deep_breath"]["at_hp_pct"], (0.5, 0.2))      # what engine/skills.py reads
        self.assertEqual((s["boss"], s["unique"], s["relentless"], s["kit"]), (True, True, True, ["Frost Nova"]))

    def test_defaults_when_a_setting_is_missing(self):
        s = monster_defs.to_spawn_stats({"name": "X", "sprite": {"sheet": "creatures", "col": 0, "row": 0}})
        self.assertEqual((s["category"], s["ac"], s["speed"], s["sense_range"], s["attack_range"], s["drops"]),
                         ("humanoid", 14, 5, 170, 50, []))
        self.assertEqual(monster_defs.to_spawn_stats(dict(murloc(), attack="ranged"))["attack_range"], 220)

    def test_ids_duplicate_and_round_trip(self):
        self.assertEqual(monster_defs.type_id_for("Murloc Raider!", {"murloc_raider"}), "murloc_raider_2")
        d = murloc()
        c = monster_defs.duplicate(d, "Murloc Elder")
        self.assertEqual((c["name"], c["drops"], c["skills"]), ("Murloc Elder", d["drops"], d["skills"]))
        c["drops"][0][1] = 0.9                                         # its own list: the original is untouched
        self.assertEqual(d["drops"][0][1], 0.5)
        path = os.path.join(tempfile.mkdtemp(), "m.json")
        monster_defs.save({"murloc_raider": d, "other": c}, path)
        self.assertEqual(list(monster_defs.load(path)), ["murloc_raider", "other"])      # order is kept
        self.assertEqual(monster_defs.load(path)["murloc_raider"], d)

    def test_which_maps_use_a_monster(self):
        maps = {"a": {"spawns": [{"type": "snake", "x": 1, "y": 1}]}, "b": {"monster_levels": {"grey_wolf": [1, 2]}}}
        self.assertEqual(monster_defs.maps_using("snake", maps), ["a"])
        self.assertEqual(monster_defs.maps_using("grey_wolf", maps), ["b"])
        self.assertEqual(monster_defs.maps_using("vecna", maps), [])


class DataFileTest(unittest.TestCase):
    """data/monsters.json is the one place monsters are defined: it must be sound whatever you edit in it."""

    def test_every_definition_is_valid(self):
        defs = monster_defs.load()
        self.assertGreaterEqual(len(defs), 20)
        for tid, d in defs.items():
            self.assertEqual(check(d, tid), [], tid)
        self.assertEqual(list(M.SPAWN_STATS), list(defs))              # nothing was skipped while loading

    def test_every_type_has_its_own_drop_list_category_and_picture(self):
        for tid, s in M.SPAWN_STATS.items():
            self.assertIn(s["category"], ("humanoid", "beast", "demon"), tid)
            self.assertIsInstance(s["drops"], list, tid)
            self.assertTrue(s["sprite"], tid)
            self.assertIs(M.MONSTER_DROPS[tid], s["drops"], tid)

    def test_every_map_only_spawns_monsters_that_exist(self):
        from game.engine.map_schema import validate_map
        for name, data in monster_defs.map_files().items():
            errors, warnings = validate_map(data, set(M.SPAWN_STATS))
            self.assertEqual(errors, [], name)
            unknown = [w for w in warnings if "unknown monster type" in w and "'npc_" not in w]   # (old NPC placeholders)
            self.assertFalse(unknown, (name, warnings))
            for tid in data.get("monster_levels", {}):
                self.assertIn(tid, M.SPAWN_STATS, f"{name}: level range for unknown monster {tid}")

    def test_the_old_board_game_list_was_kept_apart(self):
        self.assertTrue(os.path.exists(os.path.join(ROOT, "data", "board_game_monsters.json")))
        with open(os.path.join(ROOT, "data", "monsters.json")) as f:
            self.assertEqual(json.load(f)["version"], monster_defs.VERSION)


class MonsterInGameTest(unittest.TestCase):
    def setUp(self):
        self.added = M.register({
            "murloc_raider": murloc(),
            "murloc_archer": murloc(name="Murloc Archer", attack="ranged", skills=[], drops=[], sense_range=250),
            "murloc_big": murloc(name="Murloc Chief", boss=True, sprite={"sheet": "creatures", "col": 6, "row": 2,
                                                                         "big": True}, drops=[["bread", 0.2]]),
            "broken": {"name": ""}})

    def tearDown(self):
        M.unregister(self.added)

    def test_registered_into_the_monster_tables(self):
        self.assertEqual(sorted(self.added), ["murloc_archer", "murloc_big", "murloc_raider"])   # broken: skipped
        s = M.SPAWN_STATS["murloc_raider"]
        self.assertEqual((s["name"], s["ac"], s["speed"], s["kit"]), ("Murloc Raider", 13, 6, ["Frost Nova"]))
        self.assertEqual(M.MONSTER_CATEGORY["murloc_raider"], "beast")
        self.assertEqual(M.MONSTER_DROPS["murloc_raider"], [("water", 0.5), ("elven_nectar", 1.0, 10, 20)])
        M.unregister(["murloc_raider"])
        self.assertNotIn("murloc_raider", M.SPAWN_STATS)
        self.added.remove("murloc_raider")

    def spawn(self, tid, levels=(2, 4)):
        random.seed(3)
        world, p = create_world(MAP, saves.blank_character("t", "Fighter", level=5))
        world.world_map.data.setdefault("monster_levels", {})[tid] = list(levels)
        m = world.spawn_single_world_monster(SpawnPoint(tid, 30, 30))
        world.game_state.monsters.append(m)
        return world, p, m

    def test_spawns_with_its_map_level_range_skills_and_own_drops(self):
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

    def test_without_a_level_range_the_raw_stats_are_used(self):
        M.unregister(["murloc_raider"]); self.added.remove("murloc_raider")
        self.added += M.register({"murloc_raider": murloc(hp=4, dmg=2, xp=30)})
        random.seed(3)
        world, p = create_world(MAP, saves.blank_character("t", "Fighter", level=5))
        m = world.spawn_single_world_monster(SpawnPoint("murloc_raider", 30, 30))
        self.assertFalse(m.leveled)
        self.assertEqual((m.experience, m.max_hp), (30, 4 * 50))

    def test_ranges_come_from_the_definition(self):
        from game.engine import ai
        world, p, m = self.spawn("murloc_archer")
        self.assertGreater(m.ranged_attack_range, 0)
        self.assertEqual((m.attack_range, m.sense_range), (220, 250))     # ranged default, and its own sense range
        m.x, m.y = p.hero.x + 150, p.hero.y
        ai.aggro_monster(m, p.hero, world.game_state.monsters)
        m.swing_timer = 0
        res = ai.run_monster_ai(m, [p.hero], 1 / 30, world.is_wall, all_monsters=world.game_state.monsters)
        self.assertEqual(res[0], "ranged_attack_projectile")             # shoots from 150 px instead of walking in
        world, p, raider = self.spawn("murloc_raider")
        self.assertEqual((raider.attack_range, raider.sense_range), (50, 170))

    def test_attack_range_and_sense_range_can_be_set(self):
        M.register({"long_arm": murloc(name="Long Arm", attack_range=90, sense_range=400)})
        self.added.append("long_arm")
        world, p, m = self.spawn("long_arm")
        self.assertEqual((m.attack_range, m.sense_range), (90, 400))

    def test_clients_are_told_which_picture_to_draw(self):
        world, p, m = self.spawn("murloc_raider")
        ents = make_snapshot(world)["entities"]
        self.assertEqual(next(e for e in ents if e["id"] == m.eid)["art"], {"sheet": "creatures", "col": 6, "row": 2})
        wolf = next(e for e in ents if e.get("name") == "Grey Wolf")
        self.assertEqual(wolf["art"], M.SPAWN_STATS["grey_wolf"]["sprite"])    # every monster's picture comes along

    def test_every_monster_picture_can_be_drawn(self):
        code = """
import os; os.environ["SDL_VIDEODRIVER"] = "dummy"
import pygame; pygame.init(); pygame.display.set_mode((1, 1))
from game.editor.monster_panel import Art
from game.content.monsters import SPAWN_STATS
art = Art()
for tid, s in SPAWN_STATS.items():
    assert art.monster(s["sprite"], 32).get_width() == 32, tid
print("OK", len(SPAWN_STATS))
"""
        r = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, timeout=90)
        self.assertIn("OK", r.stdout, (r.stdout + r.stderr)[-1500:])


class EditorPanelTest(unittest.TestCase):
    CODE = """
import os, json; os.environ["SDL_VIDEODRIVER"] = "dummy"
import pygame; pygame.init(); screen = pygame.display.set_mode((1400, 900))
from game.content import monster_defs
from game.editor.monster_panel import MonsterPanel, spawn_palette
defs = monster_defs.load()
answers = iter(%(answers)r)
levels = {"human_cultist": [3, 4]}
p = MonsterPanel(defs, levels, lambda t, d: next(answers), map_types=lambda: {"grey_wolf"},
                 usage=lambda t: ["northshire"] if t == "grey_wolf" else [], path=%(out)r)
font = pygame.font.SysFont("monospace", 13); big = pygame.font.SysFont("monospace", 18, bold=True)
def click(action, arg=None, button=1):
    p.draw(screen, font, big)
    r = next(r for r, a, x in p.hits if a == action and (arg is None or x == arg))
    p.click(r.center, button)
log = {}
p.draw(screen, font, big)
click("filter"); log["only_map"] = p.shown(); click("filter"); log["all"] = len(p.shown())
click("select", "grey_wolf"); click("delete"); log["delete_msg"] = p.message; log["wolf_kept"] = "grey_wolf" in defs
click("duplicate"); alpha = p.selected; log["alpha_id"] = alpha
log["alpha_own_drops"] = defs[alpha]["drops"] == defs["grey_wolf"]["drops"] and defs[alpha]["drops"] is not defs["grey_wolf"]["drops"]
click("matrix"); p.draw(screen, font, big)
click("cell", (alpha, "wine")); click("cell", (alpha, "drumstick"), button=3); click("back")
click("field", "ac"); click("field", "ac"); log["ac_msg"] = p.message
click("field", "swing"); log["swing_set"] = defs[alpha].get("swing"); click("field", "swing"); log["swing_cleared"] = "swing" not in defs[alpha]
click("boss_skill", "enrage"); click("boss_param", ("enrage", "damage_mult"))
click("hive")
click("field", "levels")
click("field", "boss"); log["big_after_boss"] = defs[alpha]["sprite"].get("big")
click("add_drop"); click("pick_item", "buckler"); click("drop_chance", len(defs[alpha]["drops"]) - 1)
click("new"); temp = p.selected; click("pick_sprite", {"sheet": "dungeon", "col": 4, "row": 9})
click("delete"); log["temp_deleted"] = temp not in defs
click("select", alpha)
click("done"); assert p.done, p.message
saved = monster_defs.load(%(out)r)
log.update(levels=levels,
           palette=[x["name"] for x in spawn_palette(saved)], order_kept=list(saved)[:3] == list(monster_defs.load())[:3])
print(json.dumps(log))
"""

    def test_edit_everything_by_clicking(self):
        out = os.path.join(tempfile.mkdtemp(), "monsters.json")
        answers = ["Grey Wolf Alpha",            # duplicate
                   "5",                          # drops table: wine 5% (the drumstick is removed by right-click)
                   "17", "99",                   # armor 17, then 99 is refused
                   "1.5", "",                    # attack speed set, then cleared
                   "2",                          # enrage damage x2
                   "600", "grey_wolf,grey_wolf_alpha",       # hive mind
                   "2-3",                        # level range on this map
                   "2.5",                        # buckler drop 2.5%
                   "Temp Mob"]                   # new type (deleted right away)
        code = self.CODE % {"answers": answers, "out": out}
        r = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, timeout=90)
        self.assertEqual(r.returncode, 0, r.stderr[-2500:])
        log = json.loads(r.stdout.strip().splitlines()[-1])
        self.assertEqual(log["only_map"], ["grey_wolf", "human_cultist"])        # the filter: the map's types + level ranges
        self.assertGreaterEqual(log["all"], 20)
        self.assertIn("northshire", log["delete_msg"])                          # refused: a map still uses it
        self.assertTrue(log["wolf_kept"])
        self.assertTrue(log["alpha_own_drops"])
        self.assertEqual(log["alpha_id"], "grey_wolf_alpha")
        saved = json.load(open(out))["monsters"]
        d = saved["grey_wolf_alpha"]
        drops = {e[0]: e for e in d["drops"]}
        self.assertEqual(drops["wine"], ["wine", 0.05])                           # added from the drops table
        self.assertNotIn("drumstick", drops)                                       # removed (right-click)
        self.assertEqual(drops["buckler"], ["buckler", 0.025])
        self.assertEqual(d["ac"], 17)
        self.assertTrue(log["swing_set"] == 1.5 and log["swing_cleared"])
        self.assertEqual(d["boss_skills"]["enrage"]["damage_mult"], 2)
        self.assertEqual(d["boss_skills"]["enrage"]["at_hp_pct"], [0.5])
        self.assertEqual(d["hive_mind"], {"range": 600, "types": ["grey_wolf", "grey_wolf_alpha"]})
        self.assertTrue(d["boss"] and log["big_after_boss"])                       # boss -> drawn big
        self.assertEqual(log["levels"], {"human_cultist": [3, 4], "grey_wolf_alpha": [2, 3]})
        self.assertNotIn("temp_mob", saved)
        self.assertEqual(saved["grey_wolf"]["drops"], [["drumstick", 0.03], ["minor_mana_potion", 0.01]])  # untouched
        self.assertIn("Grey Wolf Alpha (Boss)", log["palette"])
        self.assertTrue(log["order_kept"])

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
