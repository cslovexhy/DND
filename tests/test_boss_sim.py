"""The boss simulation (game/boss_sim.py, game/boss_tune.py): the ONLY tests you need while tuning bosses.

    .venv/bin/python3 -m unittest tests.test_boss_sim        (a few seconds)
"""
import unittest

from game.boss_sim import PARTY_CLASSES, BossStats, build_fight, run_fight, score_of
from game.boss_tune import Tuner

T = 40.0   # short target time keeps these tests fast


class BossStatsTest(unittest.TestCase):
    def test_board_units_convert_to_real_numbers(self):
        s = BossStats(ac=16, dmg=2, hp=12)
        self.assertEqual(s.real_hp, 600)
        self.assertEqual(s.real_dmg, 50)
        self.assertEqual(BossStats.from_real(16, 50, 600), s)

    def test_the_room_holds_exactly_one_boss_with_the_given_stats(self):
        world, boss = build_fight(PARTY_CLASSES, 5, BossStats(14, 3, 20), seed=1)
        self.assertEqual([m for m in world.game_state.monsters], [boss])
        self.assertEqual((boss.ac, boss.max_hp, boss.base_damage), (14, 1000, 75))
        self.assertEqual(len(world.game_state.heroes), 5)
        self.assertEqual({h.level for h in world.game_state.heroes}, {5})

    def test_other_boss_type_can_be_put_in_the_room(self):
        world, boss = build_fight(("Fighter",), 3, BossStats(15, 1, 5), seed=1, boss_type=21)
        self.assertEqual(boss.name, "Otyugh")
        self.assertEqual(len(world.game_state.monsters), 1)


class FightTest(unittest.TestCase):
    def test_same_seed_same_result(self):
        a = run_fight(PARTY_CLASSES, 10, BossStats(16, 2, 150), seed=3, target_time=T)
        b = run_fight(PARTY_CLASSES, 10, BossStats(16, 2, 150), seed=3, target_time=T)
        self.assertEqual(a, b)

    def test_weak_boss_dies_fast_and_scores_low(self):
        r = run_fight(PARTY_CLASSES, 10, BossStats(16, 1, 3), target_time=T)
        self.assertTrue(r.win)
        self.assertLess(score_of(r, T), 0.3)

    def test_unkillable_boss_is_a_loss_at_the_deadline_with_score_above_one(self):
        r = run_fight(PARTY_CLASSES, 10, BossStats(16, 1, 99999), target_time=T)
        self.assertFalse(r.win)
        self.assertAlmostEqual(r.fight_time, T, delta=0.1)
        self.assertGreater(score_of(r, T), 1.0)

    def test_a_party_that_cannot_reach_the_boss_loses_instead_of_hanging(self):
        # no classes at all would be a setup error; one Wizard against a huge boss just runs out the clock
        r = run_fight(("Wizard",), 1, BossStats(16, 5, 5000), target_time=15.0)
        self.assertFalse(r.win)

    def test_ambush_damage_does_not_depend_on_the_targets_max_hp(self):
        """Ambush is 5x weapon damage only: the same hit on a small boss and a huge one."""
        from game.engine import commands as C
        hits = []
        for board_hp in (20, 5000):
            world, boss = build_fight(("Rogue",), 10, BossStats(16, 0, board_hp), seed=1)
            boss.regen_rate_combat = boss.regen_rate_ooc = 0.0         # (regen is % of max HP: it would skew the diff)
            rogue = world.game_state.heroes[0]
            world.players[0].ai_enabled = False                        # we drive the Rogue by hand
            rogue.x, rogue.y = boss.x - 40, boss.y
            world.submit(C.Cast("R", rogue.x, rogue.y, None), 0)      # Stealth
            for _ in range(20):                                        # (let the global cooldown pass)
                world.step(1 / 30)
            self.assertTrue(rogue.stealthed)
            before = boss.hp
            world.submit(C.Cast("E", boss.x, boss.y, boss.eid), 0)    # Ambush
            world.step(1 / 30)
            hits.append(before - boss.hp)
        self.assertGreater(hits[0], 0)
        self.assertAlmostEqual(hits[0], hits[1], delta=1.0)
        self.assertLess(hits[1], 600)                                  # ~5 x 50 weapon damage, less armor


class TunerTest(unittest.TestCase):
    def tuner(self, **kw):
        kw.setdefault("group", PARTY_CLASSES)
        kw.setdefault("level", 10)
        kw.setdefault("target_time", T)
        kw.setdefault("seeds", (1,))
        return Tuner(**kw)

    def test_variants_are_each_member_missing_and_everyone_one_level_lower(self):
        names = list(self.tuner().variants())
        self.assertEqual(names, [f"without {c}" for c in PARTY_CLASSES] + ["level 9"])
        v = self.tuner(group=("Fighter", "Fighter", "Cleric")).variants()
        self.assertEqual(v["without Fighter"][0], ("Fighter", "Cleric"))

    def test_tune_hp_lands_on_the_aimed_score(self):
        """The score is a step function of HP (a single-seed fight flips on one death or one cast timing: e.g. 0.90
        at 77 HP, 0.98 at 78), so 'lands on the aim' means: the tuned HP is where the score crosses the aim —
        at or above it there, below it just under it."""
        t = self.tuner()
        hp = t.tune_hp(dmg=2)
        self.assertGreaterEqual(t.full_score(hp, 2), t.aim - 0.03)
        self.assertLess(t.full_score(hp - 0.5, 2), t.aim + 0.03)

    def test_more_hp_never_makes_the_fight_easier(self):
        t = self.tuner()
        scores = [t.full_score(hp, 2) for hp in (50, 100, 150, 200)]
        self.assertEqual(scores, sorted(scores))

    def test_assessment_of_a_pushover_and_of_an_impossible_boss(self):
        t = self.tuner()
        easy = t.assess(BossStats(16, 2, 2))
        self.assertFalse(easy.feasible)                       # the weaker groups win too
        hard = t.assess(BossStats(16, 2, 99999))
        self.assertFalse(hard.feasible)                       # even the full group loses
        self.assertFalse(hard.full.all_win)

    def test_tuned_boss_is_feasible_for_the_full_group_and_fails_every_weaker_group(self):
        t = self.tuner(seeds=(1, 2))
        # damage 1: with level-1..30 hero HP (120..1270) a damage-2 boss kills a hero now and then in this short
        # 40 s check, and one death decides a 2-seed win/lose; the full 8-seed tuner covers damage 2
        a = t.assess_dmg(1)
        self.assertTrue(a.full.all_win, a.full.scores)
        # (the level -1 group is only ~4% weaker, too close a call for a 2-seed, 40 s check: it is covered by the tuner)
        missing_one = {n: e for n, e in a.variants.items() if n.startswith("without")}
        self.assertTrue(all(e.all_lose for e in missing_one.values()), {n: e.scores for n, e in missing_one.items()})


if __name__ == "__main__":
    unittest.main()
