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
    def test_damage_is_a_times_base_plus_b_per_skill_level(self):
        _, full = hero_at("Fighter", MAX_LEVEL)
        charge = full.hero.abilities["R"]
        got = []
        for level in (1, 2, 3):
            charge.set_level(level)
            got.append(round(charge.calc_damage(100.0), 6))
        self.assertEqual(got, [133.0, 146.0, 159.0])            # a 1.3/1.4/1.5, b 3/6/9
        cleave = full.hero.abilities["G"]
        cleave.set_level(1)
        self.assertAlmostEqual(cleave.calc_damage(100.0), 81.0)  # multi-target: a 0.8 (all levels), b 1

    def test_multi_target_a_below_1_single_target_at_least_1(self):
        from game.content.heroes import HERO_CLASSES
        for info in HERO_CLASSES:
            h = info["create"]("x", 0, 0)
            for ab in h.abilities.values():
                if not ab.a_levels:
                    continue                                    # no damage (heals, Stealth)
                if ab.target_kind == "self" and ab.radius == 0:
                    continue                                    # self-buff: its a is a bonus to another skill
                if ab.radius > 0:
                    self.assertTrue(all(a < 1 for a in ab.a_levels), ab.name)
                else:
                    self.assertTrue(all(a >= 1 for a in ab.a_levels), ab.name)

    def test_base_damage_by_class_and_level(self):
        expect = {"Fighter": (10, 4.0), "Cleric": (8, 3.0), "Paladin": (12, 4.5), "Rogue": (4, 1.3),
                  "Wizard": (9, 3.3)}
        for cls, (b1, g) in expect.items():
            for level in (1, 10, 30):
                _, p = hero_at(cls, level)
                self.assertAlmostEqual(p.hero.base_damage, b1 + g * (level - 1), msg=f"{cls} L{level}")

    def test_seal_adds_to_smite_a_and_judgement_consumes_it(self):
        from game.content.skill_tree import smite_damage
        world, pal = hero_at("Paladin", MAX_LEVEL)
        h = pal.hero
        smite = h.abilities["Q"]
        plain = smite_damage(h, smite)
        self.assertAlmostEqual(plain, h.base_damage + 3)
        world.submit(C.Cast("R", 0, 0, None), 0)                # Righteous Seal (level 3: +0.20)
        world.step(DT)
        self.assertAlmostEqual(smite_damage(h, smite), 1.2 * h.base_damage + 3)

    def test_seal_bonus_per_level_comes_from_its_a_levels(self):
        from game.content.skill_tree import seal_bonus
        _, pal = hero_at("Paladin", MAX_LEVEL)
        seal = pal.hero.abilities["R"]
        self.assertEqual(seal.a_levels, (0.10, 0.15, 0.20))
        got = [(seal.set_level(lv), seal_bonus(seal))[1] for lv in (1, 2, 3)]
        self.assertEqual(got, [0.10, 0.15, 0.20])

    def test_judgement_consuming_seal_adds_half_weapon(self):
        from game.content.skill_tree import judgement_seal_bonus
        _, pal = hero_at("Paladin", MAX_LEVEL)
        h = pal.hero
        judgement = h.abilities["E"]
        for lv in (1, 2, 3):
            judgement.set_level(lv)
            self.assertAlmostEqual(judgement_seal_bonus(h, judgement), 0.5 * h.base_damage)

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
        world, rogue = create_world(MAP, saves.blank_character("r", "Rogue", level=4), autopilot=True)
        self.assertEqual(list(rogue.hero.abilities), ["Q", "R", "F"])  # Stealth yes, Ambush not yet (L6)
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
        # Fighter: Charge (L2), Heroic Strike (L4), Demoralizing Shout (L6), Cleave (L8)
        self.assertEqual(got, [(2, "R", 1, True), (4, "F", 1, True), (6, "E", 1, True), (8, "G", 1, True)])

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


class DemoralizingShoutTest(unittest.TestCase):
    def test_damage_multiplier_is_90_80_70_percent(self):
        from game.content.skill_tree import shout_reduction
        _, f = hero_at("Fighter", MAX_LEVEL)
        shout = f.hero.abilities["E"]
        got = []
        for level in (1, 2, 3):
            shout.set_level(level)
            got.append(round(1.0 - shout_reduction(shout), 6))
        self.assertEqual(got, [0.9, 0.8, 0.7])

    def test_cast_applies_the_level_multiplier(self):
        random.seed(1)
        world, f = create_world(MAP, saves.blank_character("f", "Fighter", level=6))   # Shout at skill level 1
        m = world.game_state.monsters[0]
        m.x, m.y = f.hero.x + 60, f.hero.y
        world.submit(C.Cast("E", f.hero.x, f.hero.y, None), 0)
        world.step(DT)
        self.assertAlmostEqual(m.buffs["Demoralized"]["damage_mult"], 0.9)

    def test_ai_shouts_first_at_a_single_fresh_enemy_and_not_again_while_it_is_demoralized(self):
        random.seed(1)
        world, f = create_world(MAP, saves.blank_character("f", "Fighter", level=16), autopilot=True)
        mobs = world.game_state.monsters
        del mobs[1:]
        m = mobs[0]
        m.x, m.y = f.hero.x + 100, f.hero.y          # inside the 120 px shout, outside melee
        ai = f.hero_ai
        self.assertEqual(ai.update(mobs, DT)["use_ability"], "E")
        m.buffs["Demoralized"] = {"remaining": 10.0, "damage_mult": 0.7}
        self.assertNotEqual(ai.update(mobs, DT)["use_ability"], "E")
