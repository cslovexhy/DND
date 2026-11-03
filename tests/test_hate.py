"""Hate tables: damage = 1 hate per point, heals/shields = 0.8 per HP, healing a friend in combat puts the healer on
the table. Every aggroed mob chases the top-hated hero; bosses never release aggro, other mobs can be unleashed
(and then forget their hate table)."""
import random
import unittest

from game import saves
from game.engine import commands as C
from game.engine.ai import AggroState, aggro_monster, credit_heal_hate, release_aggro
from game.engine.bootstrap import create_world, join_player

MAP = "data/maps/bossTestRoom.json"
DT = 1 / 30


def room(second_class="Fighter", boss_type="ashardalon"):
    """A bossTestRoom world holding only one boss; two players standing next to it (boss idle, far from them)."""
    random.seed(3)
    world, p0 = create_world(MAP, saves.blank_character("tank", "Fighter"))
    p1 = join_player(world, 1, saves.blank_character("buddy", second_class), MAP)
    gs = world.game_state
    boss = next(m for m in gs.monsters if getattr(m, "spawn_type", None) == boss_type)
    gs.monsters[:] = [boss]
    for p, dy in ((p0, 0), (p1, 40)):
        p.hero.x, p.hero.y = boss.x - 100, boss.y + dy
    return world, p0, p1, boss


class HateTableTest(unittest.TestCase):
    def test_damage_is_one_hate_per_point_and_adds_up(self):
        world, p0, _, boss = room()
        dealt = boss.take_damage(40, source=p0.hero) + boss.take_damage(25, source=p0.hero)
        self.assertAlmostEqual(boss.hate[p0.hero], dealt)

    def test_damage_without_a_source_makes_no_hate(self):
        _, _, _, boss = room()
        boss.take_damage(40)
        self.assertEqual(boss.hate, {})

    def test_heal_is_08_hate_for_a_friend_in_combat_and_adds_the_healer(self):
        world, p0, p1, boss = room("Cleric")
        boss.add_hate(p0.hero, 100)
        self.assertNotIn(p1.hero, boss.hate)
        credit_heal_hate([boss], p1.hero, p0.hero, 150)
        self.assertAlmostEqual(boss.hate[p1.hero], 120.0)
        self.assertAlmostEqual(boss.hate[p0.hero], 100.0)

    def test_healing_someone_not_on_the_table_makes_no_hate(self):
        world, p0, p1, boss = room("Cleric")
        credit_heal_hate([boss], p1.hero, p0.hero, 150)
        self.assertEqual(boss.hate, {})

    def test_zero_heal_still_adds_the_healer(self):
        world, p0, p1, boss = room("Cleric")
        boss.add_hate(p0.hero)
        credit_heal_hate([boss], p1.hero, p0.hero, 0)
        self.assertIn(p1.hero, boss.hate)

    def test_holy_light_wall_and_renew_generate_hate(self):
        for cls, key in (("Paladin", "F"), ("Cleric", "R"), ("Cleric", "E")):
            world, p0, p1, boss = room(cls)
            p0.hero.hp = p0.hero.max_hp * 0.5
            aggro_monster(boss, p0.hero, [boss])           # p0 is in combat with the boss
            world.submit(C.Cast(key, p0.hero.x, p0.hero.y, None, ally_id=p0.hero.eid), 1)
            for _ in range(int(2.5 / DT)):
                world.step(DT)
            self.assertIn(p1.hero, boss.hate, f"{cls} {key}")
            if key != "E":
                self.assertGreater(boss.hate[p1.hero], 0, f"{cls} {key}")

    def test_wall_hate_is_08_of_the_shield(self):
        world, p0, p1, boss = room("Cleric")
        boss.add_hate(p0.hero)
        world.submit(C.Cast("R", p0.hero.x, p0.hero.y, None, ally_id=p0.hero.eid), 1)
        world.step(DT)
        self.assertAlmostEqual(boss.hate[p1.hero], 0.8 * p0.hero.absorb_shield)

    def test_renew_ticks_add_hate_for_the_whole_hot(self):
        world, p0, p1, boss = room("Cleric")
        p0.hero.hp = p0.hero.max_hp * 0.5
        boss.add_hate(p0.hero)
        world.submit(C.Cast("E", p0.hero.x, p0.hero.y, None, ally_id=p0.hero.eid), 1)
        for _ in range(int(9 / DT)):
            world.step(DT)
        total_hot = p1.hero.surge_value * 0.5                # Renew heals 50% of a potion over 8 s
        self.assertAlmostEqual(boss.hate[p1.hero], 0.8 * total_hot, delta=1.0)

    def test_normal_mob_reset_forgets_hate(self):
        world, p0, _, boss = room()
        boss.add_hate(p0.hero, 50)
        release_aggro(boss)
        self.assertEqual(boss.hate, {})
        self.assertEqual(boss.aggro_state, AggroState.RESETTING)


class BossChaseTest(unittest.TestCase):
    def test_boss_moves_on_to_the_next_hated_hero_when_the_top_one_dies_and_respawns(self):
        world, p0, p1, boss = self.aggroed()
        boss.add_hate(p0.hero, 500)
        boss.add_hate(p1.hero, 20)
        p0.hero.alive = False
        world.step(DT)                                       # p0 respawns at the start point with a clean slate
        self.assertEqual(boss.aggro_state, AggroState.AGGROED)
        self.assertNotIn(p0.hero, boss.hate)
        self.assertIs(boss.aggro_target, p1.hero)

    def aggroed(self, **kw):
        world, p0, p1, boss = room(**kw)
        aggro_monster(boss, p0.hero, [boss])
        return world, p0, p1, boss

    def test_boss_switches_to_the_top_hated_hero_and_ties_keep_the_target(self):
        world, p0, p1, boss = self.aggroed()
        boss.add_hate(p1.hero, 0)
        world.step(DT)
        self.assertIs(boss.aggro_target, p0.hero)           # tie: no switch
        boss.add_hate(p1.hero, 10)
        world.step(DT)
        self.assertIs(boss.aggro_target, p1.hero)
        boss.add_hate(p0.hero, 100)
        world.step(DT)
        self.assertIs(boss.aggro_target, p0.hero)

    def test_boss_ignores_closer_and_weaker_heroes(self):
        world, p0, p1, boss = self.aggroed()
        boss.add_hate(p0.hero, 500)
        p1.hero.hp = 1                                       # lowest HP and as close: still not the target
        for _ in range(30):
            world.step(DT)
            self.assertIs(boss.aggro_target, p0.hero)

    def test_boss_moves_on_to_the_next_hated_hero_when_the_top_one_dies(self):
        world, p0, p1, boss = self.aggroed()
        boss.add_hate(p0.hero, 500)
        boss.add_hate(p1.hero, 20)
        p0.hero.alive = False
        world.step(DT)
        self.assertIs(boss.aggro_target, p1.hero)

    def test_boss_never_leashes_or_resets_even_when_the_hero_respawns_or_stealths(self):
        world, p0, p1, boss = self.aggroed()
        boss.add_hate(p0.hero, 500)
        boss.x += 5000                                       # far beyond any leash range
        world.step(DT)
        self.assertEqual(boss.aggro_state, AggroState.AGGROED)
        p0.hero.alive = False
        world.step(DT)                                       # the world respawns the fallen player
        self.assertTrue(p0.hero.alive)
        self.assertEqual(boss.aggro_state, AggroState.AGGROED)   # the boss still never lets go...
        self.assertNotIn(p0.hero, boss.hate)                     # ...but the new life starts with no hate (no spawn-camping)

    def test_boss_with_no_hate_entries_alive_falls_back_to_closest(self):
        world, p0, p1, boss = self.aggroed()
        boss.hate.clear()
        boss.aggro_target = None
        world.step(DT)
        self.assertIs(boss.aggro_target, p0.hero)            # the closer of the two

    def test_every_boss_uses_boss_ai(self):
        # Vecna / Bellax used to fall back to the plain melee AI (not listed in AI_BEHAVIORS)
        from game.engine.ai import run_monster_ai
        world, p0, p1, boss = room()
        boss.add_hate(p1.hero, 50)
        aggro_monster(boss, p0.hero, [boss])
        boss.name = "Vecna"                                  # not in AI_BEHAVIORS
        run_monster_ai(boss, [p0.hero, p1.hero], DT)
        self.assertIs(boss.aggro_target, p1.hero)


class NormalMobTest(unittest.TestCase):
    def mob(self, second_class="Fighter"):
        """The room's boss turned into an ordinary mob (same AI as an Orc Smasher), aggroed on player 0."""
        world, p0, p1, m = room(second_class)
        m.is_boss = False
        m.name = "Orc Smasher"
        aggro_monster(m, p0.hero, [m])
        return world, p0, p1, m

    def test_mob_chases_the_top_hated_hero_not_its_first_target(self):
        world, p0, p1, m = self.mob()
        m.add_hate(p0.hero, 30)
        m.add_hate(p1.hero, 200)
        world.step(DT)
        self.assertIs(m.aggro_target, p1.hero)
        m.add_hate(p0.hero, 500)
        world.step(DT)
        self.assertIs(m.aggro_target, p0.hero)

    def test_ranged_mob_also_follows_hate(self):
        world, p0, p1, m = self.mob()
        m.name = "Orc Archer"
        m.add_hate(p1.hero, 200)
        world.step(DT)
        self.assertIs(m.aggro_target, p1.hero)

    def test_unleashed_mob_resets_and_clears_its_hate_table(self):
        world, p0, p1, m = self.mob()
        m.add_hate(p0.hero, 80)
        m.x += 5000
        world.step(DT)
        self.assertEqual(m.aggro_state, AggroState.RESETTING)
        self.assertEqual(m.hate, {})
        self.assertIsNone(m.aggro_target)

    def test_mob_back_at_spawn_has_an_empty_table_and_is_idle(self):
        world, p0, p1, m = self.mob()
        m.add_hate(p0.hero, 80)
        release_aggro(m)
        m.x, m.y = m.spawn_x, m.spawn_y
        world.step(DT)
        self.assertEqual(m.aggro_state, AggroState.IDLE)
        self.assertEqual(m.hate, {})

    def test_stealth_drops_the_rogue_but_the_mob_keeps_fighting_the_others(self):
        world, p0, p1, m = self.mob("Rogue")
        m.add_hate(p1.hero, 100)
        m.add_hate(p0.hero, 50)
        world.submit(C.Cast("R", p1.hero.x, p1.hero.y, None), 1)      # Rogue: R = Stealth
        world.step(DT)
        self.assertTrue(p1.hero.stealthed)
        self.assertNotIn(p1.hero, m.hate)
        self.assertEqual(m.aggro_state, AggroState.AGGROED)
        self.assertIs(m.aggro_target, p0.hero)

    def test_stealth_with_nobody_else_on_the_table_resets_the_mob(self):
        world, p0, p1, m = self.mob("Rogue")
        m.hate.clear()
        m.add_hate(p1.hero, 100)
        world.submit(C.Cast("R", p1.hero.x, p1.hero.y, None), 1)
        world.step(DT)
        self.assertNotEqual(m.aggro_state, AggroState.AGGROED)   # (already at spawn: reset ends at once -> idle)
        self.assertEqual(m.hate, {})

    def test_respawned_hero_is_forgotten_by_mobs(self):
        world, p0, p1, m = self.mob()
        m.add_hate(p1.hero, 100)
        m.add_hate(p0.hero, 10)
        p1.hero.alive = False
        world.step(DT)                                       # p1 respawns at the start point
        self.assertNotIn(p1.hero, m.hate)
        self.assertIs(m.aggro_target, p0.hero)


if __name__ == "__main__":
    unittest.main()
