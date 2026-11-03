"""Monsters face the hero they are attacking, even when standing still or backing away from it."""
import unittest

from game.engine.ai import AggroState, move_to_attack_range, run_monster_ai, setup_monster_aggro
from game.engine.entities import Hero, Monster


def boss_and_hero(hero_dx):
    boss = Monster("Ashardalon", "Monster", 500, 500, hp=12, ac=16, speed=4, attack_bonus=10, attack_damage=2,
                   is_boss=True)
    setup_monster_aggro(boss)
    hero = Hero("Tank", "Fighter", 500 + hero_dx, 500, hp=8, ac=17, speed=5, surge_value=4)
    return boss, hero


class FacingTest(unittest.TestCase):
    def test_faces_a_target_on_the_left_while_attacking_it_in_range(self):
        boss, hero = boss_and_hero(-60)
        boss.facing_left = False
        move_to_attack_range(boss, hero, 1 / 30)
        self.assertTrue(boss.facing_left)

    def test_faces_a_target_on_the_right(self):
        boss, hero = boss_and_hero(+60)
        boss.facing_left = True
        move_to_attack_range(boss, hero, 1 / 30)
        self.assertFalse(boss.facing_left)

    def test_backing_away_from_a_too_close_target_still_faces_it(self):
        # a target on the left, closer than half the attack range: the boss steps RIGHT but must keep looking left
        boss, hero = boss_and_hero(-10)
        boss.attack_range = 70
        x0 = boss.x
        move_to_attack_range(boss, hero, 1 / 30)
        self.assertGreater(boss.x, x0)            # it did back away (to the right)
        self.assertTrue(boss.facing_left)         # ...facing the target on its left

    def test_a_target_straight_above_does_not_flip_the_sprite(self):
        boss, hero = boss_and_hero(0)
        hero.y = boss.y - 40
        boss.facing_left = True
        move_to_attack_range(boss, hero, 1 / 30)
        self.assertTrue(boss.facing_left)

    def test_whole_ai_tick_leaves_the_boss_facing_its_target(self):
        for dx, expect_left in ((-60, True), (60, False)):
            boss, hero = boss_and_hero(dx)
            boss.aggro_state = AggroState.AGGROED
            boss.aggro_target = hero
            boss.add_hate(hero, 10)
            boss.facing_left = not expect_left
            run_monster_ai(boss, [hero], 1 / 30, None, all_monsters=[boss])
            self.assertEqual(boss.facing_left, expect_left, dx)


if __name__ == "__main__":
    unittest.main()
