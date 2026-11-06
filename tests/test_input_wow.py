"""WoW-style input: left-click targets (SetTarget), Tab cycles enemies, hotbar skills go to the target / a friend /
around you, WASD walks (MoveDir), right-click attacks (SelectTarget). All through the sim's commands."""
import random
import tempfile
import unittest

from game import saves
from game.engine import commands as C
from game.engine.bootstrap import create_world, join_player
from game.engine.snapshot import make_snapshot

MAP = "data/maps/northshire.json"
DT = 1 / 30
saves.SAVE_DIR = tempfile.mkdtemp()


def world1(cls="Wizard", level=10):
    random.seed(1)
    w, p = create_world(MAP, saves.blank_character("t", cls, level=level))
    return w, p


class TargetTest(unittest.TestCase):
    def test_set_target_an_enemy_and_clear_it(self):
        w, p = world1()
        m = w.game_state.monsters[0]
        w.submit(C.SetTarget(m.eid), 0); w.step(DT)
        self.assertIs(p.target, m)
        self.assertEqual(make_snapshot(w)["you"]["target_id"], m.eid)
        w.submit(C.SetTarget(None), 0); w.step(DT)
        self.assertIsNone(p.target)

    def test_set_target_does_not_move_or_attack(self):
        w, p = world1()
        m = min(w.game_state.monsters, key=lambda m: p.hero.distance_to(m))
        x, y = p.hero.x, p.hero.y
        w.submit(C.SetTarget(m.eid), 0)
        for _ in range(30):
            w.step(DT)
        self.assertEqual((round(p.hero.x), round(p.hero.y)), (round(x), round(y)))   # stood still
        self.assertEqual(m.hp, m.max_hp)                                             # not attacked
        self.assertIsNone(p.selected_target)

    def test_target_clears_when_it_dies(self):
        w, p = world1()
        m = w.game_state.monsters[0]
        w.submit(C.SetTarget(m.eid), 0); w.step(DT)
        m.take_damage(10 ** 9, source=p.hero)
        w.step(DT)
        self.assertIsNone(p.target)

    def test_target_a_friendly_hero(self):
        w, p = world1("Cleric")
        ally = join_player(w, 1, saves.blank_character("a", "Fighter", level=10), MAP)
        w.submit(C.SetTarget(ally.hero.eid), 0); w.step(DT)
        self.assertIs(p.target, ally.hero)

    def test_right_click_attack_sets_target_and_closes_in(self):
        w, p = world1("Fighter")
        m = min((x for x in w.game_state.monsters), key=lambda x: p.hero.distance_to(x))
        w.submit(C.SelectTarget(m.eid), 0); w.step(DT)
        self.assertIs(p.target, m)
        self.assertIs(p.selected_target, m)


class HotbarRoutingTest(unittest.TestCase):
    def test_enemy_skill_hits_the_target(self):
        w, p = world1("Wizard")
        m = min(w.game_state.monsters, key=lambda x: p.hero.distance_to(x))
        m.x, m.y = p.hero.x + 120, p.hero.y
        w.submit(C.SetTarget(m.eid), 0); w.step(DT)
        before = m.hp
        w.submit(C.Cast("R", m.x, m.y, m.eid), 0)       # Fire Blast (instant) via the hotbar helper's payload
        for _ in range(10):
            w.step(DT)
        self.assertLess(m.hp, before)

    def test_support_skill_lands_on_the_targeted_friend(self):
        w, p = world1("Cleric")
        ally = join_player(w, 1, saves.blank_character("a", "Fighter", level=10), MAP)
        ally.hero.x, ally.hero.y = p.hero.x + 40, p.hero.y
        w.submit(C.Cast("E", ally.hero.x, ally.hero.y, None, ally_id=ally.hero.eid), 0)   # Renew on the friend
        w.step(DT)
        self.assertIn("Renew", ally.hero.buffs)
        self.assertNotIn("Renew", p.hero.buffs)


class MoveDirTest(unittest.TestCase):
    def test_wasd_walks_and_stops(self):
        w, p = world1("Fighter")
        w.game_state.monsters.clear()
        x = p.hero.x
        w.submit(C.MoveDir(1, 0), 0)
        for _ in range(30):
            w.step(DT)
        self.assertGreater(p.hero.x, x + 20)             # walked right
        p.hero.x = x
        w.submit(C.MoveDir(0, 0), 0); w.step(DT)
        moved_from = p.hero.x
        for _ in range(30):
            w.step(DT)
        self.assertAlmostEqual(p.hero.x, moved_from, delta=1)   # (0,0) stops

    def test_wasd_cancels_click_to_move(self):
        w, p = world1("Fighter")
        w.game_state.monsters.clear()
        w.submit(C.MoveTo(p.hero.x + 400, p.hero.y), 0); w.step(DT)
        self.assertTrue(p.move_path)
        w.submit(C.MoveDir(0, -1), 0); w.step(DT)
        self.assertEqual(p.move_path, [])

    def test_commands_round_trip(self):
        for cmd in (C.SetTarget(7), C.SetTarget(None), C.MoveDir(-1, 1)):
            self.assertEqual(C.from_dict(C.to_dict(cmd)), cmd)


class RealClientTest(unittest.TestCase):
    def test_p_wasd_tab_and_hotbar_keys(self):
        """Headless pygame client: P (autopilot off), hold W, Tab (target), 1 (cast), Esc (clear target)."""
        import json
        import os
        import subprocess
        import sys
        from game.engine import replay
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with tempfile.TemporaryDirectory() as d:
            script, rec = os.path.join(d, "s.json"), os.path.join(d, "rec.json")
            with open(script, "w") as f:
                json.dump([{"tick": 0, "type": "key", "key": "p"},
                           {"tick": 2, "type": "key", "key": "w", "hold": 20},
                           {"tick": 30, "type": "click", "button": 3, "at": "nearest_monster"},   # attack: walk up
                           {"tick": 450, "type": "key", "key": "TAB"},       # walked ~1000 px: the boss is on screen by now
                           {"tick": 454, "type": "key", "key": "1"},
                           {"tick": 460, "type": "key", "key": "ESCAPE"},    # 1st Esc: cancel the channel
                           {"tick": 464, "type": "key", "key": "ESCAPE"}], f)  # 2nd Esc: clear the target
            # the open boss room: one monster, clear line of sight from the start
            proc = subprocess.run([sys.executable, "-m", "game.main", "--headless", "--seed", "3", "--max-time", "16",
                                   "--hero", "4", "--map", "data/maps/bossTestRoom.json", "--input-script", script,
                                   "--record-commands", rec,
                                   "--no-companion"], cwd=root, capture_output=True, text=True, timeout=60)
            self.assertEqual(proc.returncode, 0, proc.stderr[-1500:])
            cmds = [c["cmd"] for c in replay.load_recording(rec)["commands"]]
        types = [c["type"] for c in cmds]
        self.assertEqual(types[0], "ToggleAutopilot")
        self.assertIn({"type": "MoveDir", "dx": 0, "dy": -1}, cmds)
        self.assertIn({"type": "MoveDir", "dx": 0, "dy": 0}, cmds)          # W released
        self.assertIn("SelectTarget", types)                              # right-click = attack
        target = next(c for c in cmds if c["type"] == "SetTarget" and c["target_id"] is not None)   # Tab
        cast = next(c for c in cmds if c["type"] == "Cast")
        self.assertEqual((cast["ab_key"], cast["target_id"]), ("Q", target["target_id"]))   # 1 = Frostbolt on target
        self.assertIn({"type": "CancelChannel"}, cmds)
        self.assertIn({"type": "SetTarget", "target_id": None}, cmds)        # then Esc cleared it


if __name__ == "__main__":
    unittest.main()
