"""Ashardalon enrages at 50% HP: its attacks deal 50% more damage, once per life, instantly."""
import unittest

from game.boss_sim import BossStats, build_fight
from game.engine import skills
from game.engine.events import FloatText

DT = 1 / 30


def fight():
    world, boss = build_fight(["Fighter", "Cleric"], 10, BossStats(16, 2, 343.1), 1)
    return world, boss


class EnrageTest(unittest.TestCase):
    def test_enrages_once_at_half_hp_with_50_percent_more_damage(self):
        world, boss = fight()
        base = boss.base_damage
        boss.hp = boss.max_hp * 0.6
        skills.check_skill_triggers(boss)
        skills.cast_queued_skills(world)
        self.assertFalse(boss.enraged)
        self.assertEqual(boss.base_damage, base)
        boss.hp = boss.max_hp * 0.49
        skills.check_skill_triggers(boss)
        skills.cast_queued_skills(world)
        self.assertTrue(boss.enraged)
        self.assertAlmostEqual(boss.base_damage, base * 1.5)
        self.assertTrue(any(isinstance(e, FloatText) and e.text == "ENRAGED!" for e in world.events))
        for _ in range(3):                                   # never stacks
            skills.check_skill_triggers(boss)
            skills.cast_queued_skills(world)
        self.assertAlmostEqual(boss.base_damage, base * 1.5)

    def test_enrage_is_instant_even_with_deep_breath_winding_up(self):
        world, boss = fight()
        boss.hp = boss.max_hp * 0.49          # both Deep Breath and Enrage trigger at 50%
        skills.check_skill_triggers(boss)
        skills.cast_queued_skills(world)
        self.assertTrue(boss.enraged)
        self.assertTrue(any(c.monster is boss for c in world.casts))   # the breath is winding up as well


if __name__ == "__main__":
    unittest.main()
