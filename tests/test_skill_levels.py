"""Skill levels: skills unlock every 2 character levels; level 1/2/3 of a skill is 33% / 67% / 100% of its damage or
heal; ranges stay the same except the Wizard's bolts (200 / 230 / 260)."""
import random
import tempfile
import unittest

from game import saves
from game.content.heroes import HERO_CLASSES
from game.content.skill_tree import SKILL_SCHEDULE, skill_levels, unlock_level
from game.engine import commands as C
from game.engine import events as E
from game.engine.bootstrap import create_world
from game.engine.snapshot import make_snapshot
from game.progression import MAX_LEVEL, xp_to_next_level

MAP = "data/maps/northshire.json"
DT = 1 / 30
saves.SAVE_DIR = tempfile.mkdtemp()


def hero_at(cls, level):
    random.seed(1)
    world, player = create_world(MAP, saves.blank_character("t", cls, level=level))
    world.game_state.monsters.clear()
    return world, player


class ScheduleTest(unittest.TestCase):
    def test_level_one_has_only_the_basic_attack(self):
        for cls in SKILL_SCHEDULE:
            self.assertEqual(skill_levels(cls, 1), {"Q": 1}, cls)

    def test_one_new_skill_or_skill_level_every_two_levels(self):
        for cls in SKILL_SCHEDULE:
            for level in range(2, MAX_LEVEL + 1):
                before = sum(skill_levels(cls, level - 1).values())
                after = sum(skill_levels(cls, level).values())
                steps = len(SKILL_SCHEDULE[cls])
                if level % 2 == 0 and level // 2 < steps:
                    self.assertEqual(after - before, 1, f"{cls} L{level}")
                else:
                    self.assertEqual(after, before, f"{cls} L{level}")

    def test_everything_is_maxed_eventually_and_nothing_exceeds_max(self):
        for cls, info in ((c["class"], c) for c in HERO_CLASSES):
            world, player = hero_at(cls, MAX_LEVEL)
            for key, ab in player.hero.abilities.items():
                self.assertEqual(ab.level, ab.max_level, f"{cls} {ab.name}")
            self.assertEqual(set(player.hero.abilities), set(player.hero.all_abilities), cls)

    def test_unlock_levels(self):
        self.assertEqual([unlock_level(i) for i in range(4)], [1, 2, 4, 6])


class PowerTest(unittest.TestCase):
    def test_damage_is_33_67_100_percent(self):
        _, full = hero_at("Fighter", MAX_LEVEL)
        dmg3 = full.hero.abilities["Q"].calc_damage(100.0)
        ab = full.hero.abilities["Q"]
        for level, share in ((1, 0.33), (2, 0.67), (3, 1.0)):
            ab.set_level(level)
            self.assertAlmostEqual(ab.calc_damage(100.0), dmg3 * share, places=6)

    def test_flat_bonus_scales_too(self):
        _, paladin = hero_at("Paladin", MAX_LEVEL)
        smite = paladin.hero.abilities["Q"]
        smite.set_level(1)
        self.assertAlmostEqual(smite.calc_damage(0.0), 30 * 0.33)

    def test_ranges_only_change_for_wizard_bolts(self):
        for cls in ("Fighter", "Cleric", "Paladin", "Rogue"):
            _, p = hero_at(cls, MAX_LEVEL)
            for ab in p.hero.all_abilities.values():
                full_range = ab.range
                for level in (1, 2, 3):
                    ab.set_level(level)
                    self.assertEqual(ab.range, full_range, f"{cls} {ab.name}")
        _, wiz = hero_at("Wizard", MAX_LEVEL)
        for key in ("Q", "R"):
            ab = wiz.hero.abilities[key]
            self.assertEqual([(ab.set_level(lv), ab.range)[1] for lv in (1, 2, 3)], [200, 230, 260])
        nova = wiz.hero.abilities["E"]
        nova.set_level(1)
        self.assertEqual(nova.radius, 120)

    def test_wizard_levels_set_its_weapon_range(self):
        for level, rng in ((1, 200), (6, 230), (12, 260)):
            _, wiz = hero_at("Wizard", level)
            self.assertEqual(wiz.hero.abilities["Q"].range, rng, level)
            self.assertEqual(wiz.hero.attack_range, rng, level)

    def test_heals_and_shields_scale(self):
        from game.content import skill_tree as T
        _, cleric = hero_at("Cleric", MAX_LEVEL)
        wall, renew = cleric.hero.abilities["R"], cleric.hero.abilities["E"]
        for level, share in ((1, 0.33), (2, 0.67), (3, 1.0)):
            wall.set_level(level)
            renew.set_level(level)
            self.assertAlmostEqual(T.wall_shield(cleric.hero, wall), 200 * share)
            self.assertAlmostEqual(T.renew_total(cleric.hero, renew), 100 * share)
        _, pal = hero_at("Paladin", MAX_LEVEL)
        hl = pal.hero.abilities["F"]
        hl.set_level(1)
        self.assertAlmostEqual(T.holy_light_heal(hl), 150 * 0.33)

    def test_wall_cast_absorbs_the_level_amount(self):
        world, cleric = hero_at("Cleric", 8)     # Wall is at skill level 2 here (R: L2, L8)
        self.assertEqual(cleric.hero.abilities["R"].level, 2)
        world.submit(C.Cast("R", 0, 0, None), 0)
        world.step(DT)
        self.assertAlmostEqual(cleric.hero.absorb_shield, 200 * 0.67, places=3)


class LockedSkillsTest(unittest.TestCase):
    def test_locked_skill_cannot_be_cast(self):
        world, cleric = hero_at("Cleric", 1)
        self.assertEqual(list(cleric.hero.abilities), ["Q"])
        world.submit(C.Cast("R", 0, 0, None), 0)       # Wall is not unlocked yet
        world.step(DT)
        self.assertEqual(cleric.hero.absorb_shield, 0)

    def test_rogue_without_ambush_does_not_stealth(self):
        random.seed(1)
        world, rogue = create_world(MAP, saves.blank_character("r", "Rogue", level=2), autopilot=True)
        self.assertEqual(list(rogue.hero.abilities), ["Q", "R"])      # Stealth yes, Ambush not yet
        for _ in range(30 * 30):
            world.step(DT)
            self.assertFalse(rogue.hero.stealthed)
        self.assertGreater(rogue.hero.kills, 0)                       # it fights with Stab instead


class LevelUpTest(unittest.TestCase):
    def test_skill_events_come_every_second_level(self):
        world, player = hero_at("Fighter", 1)
        got = []
        for target in range(2, 9):
            player.hero.xp = xp_to_next_level(player.hero.level)
            world.step(DT)
            got += [(e.hero_level, e.key, e.skill_level, e.is_new) for e in world.events if isinstance(e, E.SkillUp)]
            world.events.clear()
            self.assertEqual(player.hero.level, target)
        # Fighter: R1 (L2), Q2 (L4), E1 (L6), R2 (L8)
        self.assertEqual(got, [(2, "R", 1, True), (4, "Q", 2, False), (6, "E", 1, True), (8, "R", 2, False)])

    def test_event_text_and_serialization(self):
        world, player = hero_at("Cleric", 1)
        player.hero.xp = xp_to_next_level(1)
        world.step(DT)
        ev = next(e for e in world.events if isinstance(e, E.SkillUp))
        self.assertEqual((ev.name, ev.skill_level, ev.max_level, ev.player_id), ("Wall", 1, 3, 0))
        self.assertIn("absorbs 66", ev.text)           # 33% of the 200 shield
        again = E.from_dict(E.to_dict(ev))
        self.assertEqual(again, ev)

    def test_snapshot_carries_skill_levels(self):
        world, player = hero_at("Wizard", 10)
        abs_ = {a["key"]: a for a in make_snapshot(world)["you"]["abilities"]}
        self.assertEqual((abs_["Q"]["level"], abs_["Q"]["max_level"], abs_["Q"]["range"]), (2, 3, 230))

    def test_companions_get_skills_for_the_owners_level(self):
        world, player = hero_at("Fighter", 4)
        for cls in ("Wizard", "Cleric", "Paladin", "Rogue"):
            world.submit(C.ToggleCompanion(cls), 0)
        world.step(DT)
        for comp in world.companions:
            self.assertEqual(comp.hero.level, 4)
            self.assertEqual(comp.hero.skill_levels, skill_levels(comp.hero.class_name, 4))


if __name__ == "__main__":
    unittest.main()
