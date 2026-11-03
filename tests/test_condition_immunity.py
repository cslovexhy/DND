"""Per-condition immunity flags: all off by default; bosses are immune to Slow, Freeze, Stun and Immobilize."""
import unittest

from game.engine.entities import Condition, Monster, CONDITION_IMMUNITY_FLAG


def mob(boss):
    return Monster("Test", "Monster", 0, 0, hp=5, ac=14, speed=5, attack_bonus=8, attack_damage=1, is_boss=boss)


class ConditionImmunityTest(unittest.TestCase):
    def test_every_condition_has_its_own_flag_and_all_default_off(self):
        self.assertEqual(set(CONDITION_IMMUNITY_FLAG), set(Condition))
        self.assertEqual(len(set(CONDITION_IMMUNITY_FLAG.values())), len(Condition))
        m = mob(False)
        for flag in CONDITION_IMMUNITY_FLAG.values():
            self.assertFalse(getattr(m, flag), flag)

    def test_normal_mob_can_be_slowed_and_frozen(self):
        m = mob(False)
        self.assertTrue(m.apply_condition(Condition.SLOWED, 3.0))
        self.assertTrue(m.apply_condition(Condition.FROZEN, 3.0))
        self.assertTrue(m.has_condition(Condition.SLOWED) and m.has_condition(Condition.FROZEN))

    BOSS_IMMUNE = {"immune_slow", "immune_freeze", "immune_stun", "immune_immobilize"}

    def test_boss_flags(self):
        b = mob(True)
        for flag in CONDITION_IMMUNITY_FLAG.values():
            self.assertEqual(getattr(b, flag), flag in self.BOSS_IMMUNE, flag)

    def test_boss_ignores_slow_freeze_stun_immobilize_but_not_poison_or_daze(self):
        b = mob(True)
        for cond in (Condition.SLOWED, Condition.FROZEN, Condition.STUNNED, Condition.IMMOBILIZED):
            self.assertFalse(b.apply_condition(cond, 3.0), cond)
        self.assertEqual(b.conditions, [])
        self.assertTrue(b.apply_condition(Condition.POISONED, 3.0))
        self.assertTrue(b.apply_condition(Condition.DAZED, 3.0))

    def charge(self, boss_as_normal_mob):
        """Fighter charges the room's boss (optionally with its boss immunities removed); returns (conditions seen, hp lost)."""
        from game import saves
        from game.engine import commands as C
        from game.engine.bootstrap import create_world
        world, p = create_world("data/maps/bossTestRoom.json", saves.blank_character("tank", "Fighter"))
        boss = next(m for m in world.game_state.monsters if m.is_boss)
        world.game_state.monsters[:] = [boss]
        if boss_as_normal_mob:
            boss.immune_stun = False
        p.hero.x, p.hero.y = boss.x - 150, boss.y
        world.submit(C.Cast("R", boss.x, boss.y, boss.eid), 0)       # Fighter: R = Charge (dash + stun)
        seen = set()
        for _ in range(60):
            world.step(1 / 30)
            seen |= {c.condition for c in boss.conditions}
        return seen, boss.max_hp - boss.hp

    def test_boss_is_not_stunned_by_a_fighter_charge(self):
        seen, lost = self.charge(boss_as_normal_mob=False)
        self.assertGreater(lost, 0)                                    # the charge landed...
        self.assertNotIn(Condition.STUNNED, seen)                      # ...but did not stun

    def test_charge_does_stun_without_the_immunity(self):
        seen, _ = self.charge(boss_as_normal_mob=True)
        self.assertIn(Condition.STUNNED, seen)

    def test_flags_are_independent(self):
        m = mob(False)
        m.immune_slow = True
        self.assertFalse(m.apply_condition(Condition.SLOWED, 3.0))
        self.assertTrue(m.apply_condition(Condition.FROZEN, 3.0))
        m.immune_stun = True
        self.assertFalse(m.apply_condition(Condition.STUNNED, 1.0))

    def test_boss_keeps_full_speed_after_frostbolt_and_frost_nova(self):
        from game import saves
        from game.engine import commands as C
        from game.engine.bootstrap import create_world
        world, p = create_world("data/maps/bossTestRoom.json", saves.blank_character("wiz", "Wizard"))
        boss = next(m for m in world.game_state.monsters if m.is_boss)
        world.game_state.monsters[:] = [boss]
        p.hero.x, p.hero.y = boss.x - 60, boss.y
        for key in ("Q", "R", "E", "F"):          # throw every Wizard skill at it
            world.submit(C.Cast(key, boss.x, boss.y, boss.eid), 0)
            for _ in range(40):
                world.step(1 / 30)
        self.assertFalse(boss.has_condition(Condition.SLOWED))
        self.assertFalse(boss.has_condition(Condition.FROZEN))
        self.assertLess(boss.hp, boss.max_hp)     # ...and the skills did hit it


if __name__ == "__main__":
    unittest.main()
