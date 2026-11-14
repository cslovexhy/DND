"""Attack animation and skill weapon rules.

The simulation reports each hero's last attack / cast (cosmetic, never read by the sim) and the client picks pose
frames from it (client/anim.pose_for). Each skill allows only some weapons (content/equipment.SKILL_WEAPONS; default
every weapon, bare hands always) and animates in a style that fits it (thrust / chop / sweep / raise)."""
import os
import random
import subprocess
import sys
import tempfile
import unittest

from game import saves
from game.client import anim as G          # pure (no pygame): the frame choice
from game.content.equipment import attack_hand, skill_allows, skill_anim, SKILL_WEAPONS
from game.engine import casting
from game.engine import commands as C
from game.engine.bootstrap import create_world
from game.engine.snapshot import make_snapshot, ATTACK_ANIM_SECS
from tests import item_ids as I

MAP = "data/maps/northshire.json"
DT = 1 / 30
saves.SAVE_DIR = tempfile.mkdtemp()


def setup(cls, dist=40, equipment=None):
    random.seed(1)
    char = saves.blank_character("t", cls, level=10)
    if equipment:
        char["equipment"] = equipment
    world, p = create_world(MAP, char)
    h = p.hero
    m = next(m for m in world.game_state.monsters if m.alive)
    world.game_state.monsters[:] = [m]
    m.x, m.y = h.x + dist, h.y
    m.max_hp = m.hp = 10 ** 6
    return world, p, h, m


def me(world):
    return next(e for e in make_snapshot(world)["entities"] if e["kind"] == "hero")


def ability(world, key):
    return next(a for a in make_snapshot(world)["you"]["abilities"] if a["key"] == key)


class SimReportsAttacksTest(unittest.TestCase):
    def test_melee_swing_is_reported_then_expires(self):
        world, p, h, m = setup("Fighter", equipment={"main": I.AXE, "off": None})
        self.assertIsNone(me(world)["attack"])
        self.assertTrue(casting.try_cast(world, h, h.abilities["Q"], m).ok)       # Strike with an axe: chop
        a = me(world)["attack"]
        self.assertEqual((a[0], a[2], a[3]), ("chop", 1, "main"))
        for _ in range(int(ATTACK_ANIM_SECS / DT) + 2):
            h.update(DT)
        self.assertIsNone(me(world)["attack"])

    def test_bare_handed_strike_is_a_punch(self):
        world, p, h, m = setup("Fighter")
        self.assertTrue(casting.try_cast(world, h, h.abilities["Q"], m).ok)
        self.assertEqual(me(world)["attack"][0], "thrust")

    def test_spells_raise(self):
        world, p, h, m = setup("Cleric", dist=150, equipment={"main": I.WAND, "off": None})
        self.assertTrue(casting.try_cast(world, h, h.abilities["Q"], m).ok)       # Wanding
        self.assertEqual(me(world)["attack"][0], "raise")

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

    def test_dual_wield_alternates_hands_only_with_an_allowed_off_hand_weapon(self):
        world, p, h, m = setup("Rogue", equipment={"main": I.DAGGER, "off": I.SHORT_SWORD})
        hands = []
        for _ in range(4):
            h.swing_timer = 0
            self.assertTrue(casting.try_cast(world, h, h.abilities["Q"], m).ok)   # Stab
            hands.append(me(world)["attack"][3])
        self.assertEqual(hands, ["main", "off", "main", "off"])
        # an axe can't Stab: the off hand never swings it
        eq = {"main": I.DAGGER, "off": I.AXE}
        self.assertEqual([attack_hand("Stab", eq, n) for n in (1, 2, 3, 4)], ["main"] * 4)
        # a shield never swings
        self.assertEqual(attack_hand("Strike", {"main": I.AXE, "off": I.BUCKLER}, 2), "main")
        # spells never use the off hand
        self.assertEqual(attack_hand("Fire Blast", {"main": I.AXE, "off": I.AXE}, 2), "main")


class SkillWeaponRulesTest(unittest.TestCase):
    def test_rules(self):
        for item in (I.DAGGER, I.SHORT_SWORD, I.WOODEN_SWORD, I.CLEAVER, I.BROADSWORD, I.SPEAR, None):   # (all 1h swords)
            self.assertTrue(skill_allows("Stab", item), item)
        for item in (I.AXE, I.DOUBLE_AXE, I.WARHAMMER, I.STAFF, I.WAND):
            self.assertFalse(skill_allows("Stab", item), item)
        self.assertFalse(skill_allows("Strike", I.WAND))
        self.assertFalse(skill_allows("Cleave", I.DAGGER))
        self.assertFalse(skill_allows("Cleave", I.SPEAR))
        self.assertTrue(skill_allows("Cleave", I.DOUBLE_AXE))
        for spell in ("Frostbolt", "Fire Blast", "Holy Light", "Renew", "Wanding", "Judgement"):
            self.assertNotIn(spell, SKILL_WEAPONS)                  # spells: any weapon
            self.assertEqual(skill_anim(spell, I.WARHAMMER), "raise")

    def test_animation_style_per_skill(self):
        self.assertEqual(skill_anim("Stab", I.SPEAR), "thrust")
        self.assertEqual(skill_anim("Strike", I.AXE), "chop")
        self.assertEqual(skill_anim("Strike", I.DAGGER), "thrust")
        self.assertEqual(skill_anim("Smite", I.WARHAMMER), "chop")
        self.assertEqual(skill_anim("Cleave", I.DOUBLE_AXE), "sweep")
        self.assertIsNone(skill_anim("Stealth", I.DAGGER))

    def test_wrong_weapon_makes_the_skill_not_ready_everywhere(self):
        world, p, h, m = setup("Rogue", equipment={"main": I.AXE, "off": None})
        q = h.abilities["Q"]                                        # Stab
        self.assertFalse(q.weapon_ok())
        self.assertFalse(q.is_ready())                              # the AI and the hotbar see it as unusable
        self.assertEqual(casting.try_cast(world, h, q, m).reason, "wrong weapon")
        a = ability(world, "Q")
        self.assertEqual((a["weapon_ok"], a["ready"]), (False, False))
        world.submit(C.Cast("Q", m.x, m.y, m.eid), 0)
        world.step(DT)
        self.assertEqual(m.hp, m.max_hp)                            # nothing happened
        p._set_equipment({"main": I.DAGGER, "off": None})
        self.assertTrue(q.is_ready())
        self.assertTrue(ability(world, "Q")["weapon_ok"])

    def test_bare_hands_and_monsters_can_use_everything(self):
        world, p, h, m = setup("Rogue")
        self.assertTrue(all(a.weapon_ok() for a in h.abilities.values()))
        from game.content.skill_library import make_skill
        ab = make_skill("Stab")
        ab.caster = m
        self.assertTrue(ab.weapon_ok())

    def test_skill_description_lists_the_weapons(self):
        from game.content.skill_tree import describe
        world, p, h, m = setup("Rogue")
        self.assertIn("Needs bare hands or: Dagger, 1H Sword, Spear.", describe(h, h.abilities["Q"]))


class PoseChoiceTest(unittest.TestCase):
    def test_idle_without_an_attack(self):
        self.assertEqual(G.pose_for(), (None, "idle"))

    def test_chop_timeline(self):
        frames = [G.pose_for(["chop", t, 1, "main"]) for t in (0.0, 0.12, 0.25, 0.5)]
        self.assertEqual(frames, [("chop", "windup"), ("chop", "strike"), ("chop", "follow"), (None, "idle")])

    def test_off_hand_uses_the_left_arm_poses(self):
        self.assertEqual(G.pose_for(["thrust", 0.1, 2, "off"]), ("thrust_l", "thrust"))
        self.assertEqual(G.pose_for(["chop", 0.12, 2, "off"]), ("chop_l", "strike"))
        self.assertEqual(G.pose_for(["sweep", 0.12, 1, "main"]), ("sweep", "strike"))

    def test_casts_and_channels_raise_the_weapon(self):
        self.assertEqual(G.pose_for(["raise", 0.1, 1, "main"]), ("cast", "raised"))
        self.assertEqual(G.pose_for(["release", 0.1, 1, "main"]), ("cast", "flash"))
        self.assertEqual(G.pose_for(channel_progress=0.05, channel_skill="Frostbolt"), ("cast", "half"))
        self.assertEqual(G.pose_for(channel_progress=0.6, channel_skill="Holy Light"), ("cast", "raised"))
        self.assertEqual(G.pose_for(channel_progress=0.5, channel_skill="Charge"), (None, "idle"))

    def test_every_pose_draws_for_every_class_and_weapon(self):
        """(In a subprocess: the art needs pygame, and other tests check the sim runs without it loaded.)"""
        code = """
from tests import item_ids as I
import os; os.environ["SDL_VIDEODRIVER"] = "dummy"
import pygame; pygame.init(); pygame.display.set_mode((1, 1))
from game.client import gear_art as G
from game.content.equipment import GEAR
tile = pygame.Surface((16, 16), pygame.SRCALPHA); tile.fill((200, 100, 50))
weapons = [k for k, g in GEAR.items() if g["kind"] == "weapon"] + [None]
n = 0
for key in G.ARM_COLORS:
    for main in weapons:
        for off in (None, I.BUCKLER, I.DAGGER, I.AXE):
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




class WeaponTypeTest(unittest.TestCase):
    def test_skills_check_the_weapon_type_not_the_item(self):
        from game.content import equipment, item_defs
        defs = item_defs.load()
        kingsfall = defs.add(dict(defs[I.DAGGER], name="Kingsfall", b=40))      # a new dagger, same type
        from game.content import items
        items.reload(defs)
        try:
            self.assertEqual(equipment.type_of(kingsfall), "dagger")
            for skill in ("Stab", "Ambush", "Poison Dagger"):
                self.assertTrue(skill_allows(skill, kingsfall), skill)
            self.assertFalse(skill_allows("Cleave", kingsfall))
            self.assertEqual(equipment.weapon_move(kingsfall), "thrust")
        finally:
            items.reload(item_defs.load())
        self.assertEqual({equipment.type_of(i) for i in (I.WOODEN_SWORD, I.SHORT_SWORD, I.CLEAVER, I.BROADSWORD)},
                         {"1h_sword"})


if __name__ == "__main__":
    unittest.main()
