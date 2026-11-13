"""Attack animation: the simulation reports each hero's last attack / cast (cosmetic, never read by the sim) and the
client picks pose frames from it (client/gear_art.pose_for)."""
import os
import random
import subprocess
import sys
import tempfile
import unittest

from game import saves
from game.client import anim as G          # pure (no pygame): the frame choice
from game.engine import casting
from game.engine.bootstrap import create_world
from game.engine.snapshot import make_snapshot, ATTACK_ANIM_SECS

MAP = "data/maps/northshire.json"
DT = 1 / 30
saves.SAVE_DIR = tempfile.mkdtemp()


def setup(cls, dist=40):
    random.seed(1)
    world, p = create_world(MAP, saves.blank_character("t", cls, level=10))
    h = p.hero
    m = next(m for m in world.game_state.monsters if m.alive)
    world.game_state.monsters[:] = [m]
    m.x, m.y = h.x + dist, h.y
    m.max_hp = m.hp = 10 ** 6
    return world, p, h, m


def me(world):
    return next(e for e in make_snapshot(world)["entities"] if e["kind"] == "hero")


class SimReportsAttacksTest(unittest.TestCase):
    def test_melee_swing_is_reported_then_expires(self):
        world, p, h, m = setup("Fighter")
        self.assertIsNone(me(world)["attack"])
        self.assertTrue(casting.try_cast(world, h, h.abilities["Q"], m).ok)       # Strike
        a = me(world)["attack"]
        self.assertEqual((a[0], a[2]), ("melee", 1))
        for _ in range(int(ATTACK_ANIM_SECS / DT) + 2):
            h.update(DT)
        self.assertIsNone(me(world)["attack"])

    def test_ranged_basic_attack_and_instant_spells_are_casts(self):
        world, p, h, m = setup("Cleric", dist=150)
        self.assertTrue(casting.try_cast(world, h, h.abilities["Q"], m).ok)       # Wanding (ranged swing)
        self.assertEqual(me(world)["attack"][0], "cast")

    def test_channel_reports_its_skill_then_a_release(self):
        world, p, h, m = setup("Wizard", dist=150)
        self.assertTrue(casting.try_cast(world, h, h.abilities["Q"], m).ok)       # Frostbolt (channel)
        d = me(world)
        self.assertEqual(d["channel_skill"], "Frostbolt")
        self.assertIsNone(d["attack"])                                           # no attack until it releases
        for _ in range(int(2.1 / DT)):
            world.step(DT)
            if me(world)["attack"]:
                break
        d = me(world)
        self.assertIsNone(d["channel_skill"])
        self.assertEqual(d["attack"][0], "release")

    def test_count_goes_up_each_attack(self):
        world, p, h, m = setup("Rogue")
        for want in (1, 2, 3):
            h.swing_timer = 0
            self.assertTrue(casting.try_cast(world, h, h.abilities["Q"], m).ok)   # Stab
            self.assertEqual(me(world)["attack"][2], want)


class PoseChoiceTest(unittest.TestCase):
    def test_idle_without_an_attack(self):
        self.assertEqual(G.pose_for("axe", None), (None, "idle"))

    def test_chop_timeline(self):
        frames = [G.pose_for("axe", None, ["melee", t, 1]) for t in (0.0, 0.12, 0.25, 0.5)]
        self.assertEqual(frames, [("chop", "windup"), ("chop", "strike"), ("chop", "follow"), (None, "idle")])

    def test_thrust_weapons_and_bare_hands_stab(self):
        self.assertEqual(G.pose_for("spear", None, ["melee", 0.1, 1]), ("thrust", "thrust"))
        self.assertEqual(G.pose_for(None, None, ["melee", 0.1, 1]), ("thrust", "thrust"))

    def test_dual_daggers_alternate_hands(self):
        self.assertEqual(G.pose_for("dagger", "dagger", ["melee", 0.05, 1]), ("dual", "right"))
        self.assertEqual(G.pose_for("dagger", "dagger", ["melee", 0.05, 2]), ("dual", "left"))
        self.assertEqual(G.pose_for("dagger", "dagger", ["melee", 0.3, 2]), (None, "idle"))
        self.assertEqual(G.pose_for("axe", "axe", ["melee", 0.12, 1]), ("chop", "strike"))   # main hand chops

    def test_casts_and_channels_raise_the_weapon(self):
        self.assertEqual(G.pose_for("warhammer", None, ["cast", 0.1, 1]), ("cast", "raised"))
        self.assertEqual(G.pose_for("staff", None, ["release", 0.1, 1]), ("cast", "flash"))
        self.assertEqual(G.pose_for("staff", None, channel_progress=0.05, channel_skill="Frostbolt"),
                         ("cast", "half"))
        self.assertEqual(G.pose_for("staff", None, channel_progress=0.6, channel_skill="Holy Light"),
                         ("cast", "raised"))
        self.assertEqual(G.pose_for("axe", None, channel_progress=0.5, channel_skill="Charge"), (None, "idle"))

    def test_every_pose_draws_for_every_class_and_weapon(self):
        """(In a subprocess: the art needs pygame, and other tests check the sim runs without it loaded.)"""
        code = """
import os; os.environ["SDL_VIDEODRIVER"] = "dummy"
import pygame; pygame.init(); pygame.display.set_mode((1, 1))
from game.client import gear_art as G
from game.content.equipment import GEAR
tile = pygame.Surface((16, 16), pygame.SRCALPHA); tile.fill((200, 100, 50))
weapons = [k for k, g in GEAR.items() if g["kind"] == "weapon"] + [None]
n = 0
for key in G.ARM_COLORS:
    for main in weapons:
        for off in (None, "buckler", "dagger"):
            for style, frames in G.STYLES.items():
                for frame in frames:
                    surf, pad = G.figure(tile, key, main, off, style, frame)
                    assert surf.get_width() > 16
                    n += 1
print("OK", n)
"""
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        r = subprocess.run([sys.executable, "-c", code], cwd=root, capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr[-1500:])
        self.assertIn("OK", r.stdout)


if __name__ == "__main__":
    unittest.main()
