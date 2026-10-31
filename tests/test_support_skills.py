"""Support skills (Cleric Wall/Renew, Paladin Holy Light) must work on allies, not only on the caster."""
import random
import unittest

from game import saves
from game.engine import commands as C
from game.engine.bootstrap import create_world, join_player

MAP = "data/maps/northshire.json"
DT = 1 / 30


def two_players(caster_class, ally_class="Fighter"):
    random.seed(9)
    world, p0 = create_world(MAP, saves.blank_character("healer", caster_class))
    p1 = join_player(world, 1, saves.blank_character("buddy", ally_class), MAP)
    world.game_state.monsters.clear()            # no fighting: only the heal is under test
    p1.hero.x, p1.hero.y = p0.hero.x + 60, p0.hero.y  # standing next to each other
    return world, p0, p1


def cast_on(world, caster, key, target):
    world.submit(C.Cast(key, target.x, target.y, None, ally_id=target.eid), caster.player_id)
    world.step(DT)


class SupportSkillsTest(unittest.TestCase):
    def test_cleric_renew_on_ally(self):
        world, cleric, ally = two_players("Cleric")
        ally.hero.hp = ally.hero.max_hp * 0.4
        cast_on(world, cleric, "E", ally.hero)                  # E = Renew
        self.assertIn("Renew", ally.hero.buffs)
        self.assertNotIn("Renew", cleric.hero.buffs)
        before = ally.hero.hp
        for _ in range(60):
            world.step(DT)
        self.assertGreater(ally.hero.hp, before)

    def test_cleric_wall_on_ally(self):
        world, cleric, ally = two_players("Cleric")
        cast_on(world, cleric, "R", ally.hero)                  # R = Wall
        self.assertGreater(ally.hero.absorb_shield, 0)
        self.assertEqual(cleric.hero.absorb_shield, 0)

    def test_paladin_holy_light_on_ally(self):
        world, paladin, ally = two_players("Paladin")
        ally.hero.hp = ally.hero.max_hp * 0.3
        before = ally.hero.hp
        cast_on(world, paladin, "F", ally.hero)                 # F = Holy Light (2 s cast)
        for _ in range(int(2.2 / DT)):
            world.step(DT)
        self.assertGreater(ally.hero.hp, before + 100)

    def test_heal_on_companion(self):
        world, cleric, _ = two_players("Cleric")
        world.submit(C.ToggleCompanion("Fighter"), 0)
        world.step(DT)
        comp = world.companions[-1][0]
        comp.hp = comp.max_hp * 0.4
        cast_on(world, cleric, "E", comp)
        self.assertIn("Renew", comp.buffs)

    def test_no_ally_clicked_heals_self_as_before(self):
        world, cleric, ally = two_players("Cleric")
        world.submit(C.Cast("E", cleric.hero.x, cleric.hero.y, None), 0)
        world.step(DT)
        self.assertIn("Renew", cleric.hero.buffs)
        self.assertNotIn("Renew", ally.hero.buffs)

    def test_out_of_range_ally_is_refused(self):
        world, cleric, ally = two_players("Cleric")
        ally.hero.x += 2000
        cast_on(world, cleric, "E", ally.hero)
        self.assertNotIn("Renew", ally.hero.buffs)
        self.assertTrue(cleric.hero.abilities["E"].is_ready())   # no cooldown spent

    def test_cannot_heal_monsters(self):
        world, cleric, _ = two_players("Cleric")
        world.spawn_world_map_monsters()
        m = world.game_state.monsters[0]
        cast_on(world, cleric, "E", m)
        self.assertNotIn("Renew", m.buffs)

    def test_cleric_autopilot_heals_hurt_ally(self):
        world, cleric, ally = two_players("Cleric")
        world.spawn_world_map_monsters()          # the AI only acts when there are monsters around
        cleric.ai_enabled = True
        ally.hero.hp = ally.hero.max_hp * 0.3
        for _ in range(90):
            world.step(DT)
            if "Renew" in ally.hero.buffs or ally.hero.absorb_shield > 0:
                break
        self.assertTrue("Renew" in ally.hero.buffs or ally.hero.absorb_shield > 0)


class RightClickOnAllyTest(unittest.TestCase):
    def test_right_click_on_companion_sends_ally_and_heals_it(self):
        """Real input path: headless pygame client, Cleric, Renew on the right-click slot, right-click the companion."""
        import json
        import os
        import subprocess
        import sys
        import tempfile
        from game.engine import replay
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with tempfile.TemporaryDirectory() as d:
            script = os.path.join(d, "s.json")
            rec = os.path.join(d, "rec.json")
            with open(script, "w") as f:
                json.dump([{"tick": 0, "type": "key", "key": "TAB"},          # autopilot off
                           {"tick": 2, "type": "key", "key": "3"},            # right-click skill = Renew
                           {"tick": 5, "type": "click", "button": 3, "at": "nearest_ally"}], f)
            p = subprocess.run([sys.executable, "-m", "game.main", "--headless", "--seed", "3", "--max-time", "1",
                                "--hero", "1", "--map", MAP, "--input-script", script, "--record-commands", rec],
                               cwd=root, capture_output=True, text=True, timeout=60)
            self.assertEqual(p.returncode, 0, p.stderr[-1500:])
            data = replay.load_recording(rec)
        casts = [c["cmd"] for c in data["commands"] if c["cmd"]["type"] == "Cast"]
        self.assertEqual(len(casts), 1)
        self.assertEqual(casts[0]["ab_key"], "E")
        self.assertIsNotNone(casts[0]["ally_id"])
        # replay it in the pure sim and look at the companion
        random.seed(data["seed"])
        world, _ = create_world(MAP, saves.blank_character("cleric", "Cleric"), autopilot=True, auto_companion=True)
        by_tick = {c["tick"]: c for c in data["commands"]}
        for tick in range(10):
            if tick in by_tick:
                world.submit(C.from_dict(by_tick[tick]["cmd"]), 0)
            world.step(DT)
        comp = world.entity(casts[0]["ally_id"])
        self.assertIs(comp, world.companions[0][0])
        self.assertIn("Renew", comp.buffs)


if __name__ == "__main__":
    unittest.main()
