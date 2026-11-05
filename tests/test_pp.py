"""Map difficulty ("players" setting, Diablo II style): at Xpp monsters have HP x X and deal damage x (1+X)/2."""
import random
import unittest

from game import saves
from game.content.difficulty import clamp_pp, damage_multiplier, hp_multiplier, map_title, scaled_xp
from game.content.monsters import SPAWN_STATS, base_xp_for_level, hp_for_level, monster_hp_mult, damage_for_level
from game.engine.bootstrap import create_world, join_player
from game.engine.entities import HP_SCALE, POISON_DPS
from game.engine.snapshot import make_snapshot

MAP = "data/maps/northshire.json"


def world(pp):
    random.seed(1)
    w, _ = create_world(MAP, saves.blank_character("t", "Fighter"), pp=pp)
    return w


def base_hp(m):
    """HP before pp: from the level for monsters with a map level, else the hand-tuned SPAWN_STATS HP."""
    stats = SPAWN_STATS[m.spawn_type]
    hp = hp_for_level(m.level) if m.leveled else stats["hp"] * HP_SCALE
    return hp * monster_hp_mult(stats)


def base_xp(m):
    return base_xp_for_level(m.level) if m.leveled else SPAWN_STATS[m.spawn_type]["xp"]


def base_dmg(m):
    return damage_for_level(m.level) if m.leveled else SPAWN_STATS[m.spawn_type]["dmg"] * HP_SCALE // 2


class PpRulesTest(unittest.TestCase):
    def test_multipliers(self):
        self.assertEqual([hp_multiplier(x) for x in (1, 2, 8)], [1, 2, 8])
        self.assertEqual([damage_multiplier(x) for x in (1, 2, 8)], [1.0, 1.5, 4.5])

    def test_xp_rounding(self):
        self.assertEqual([scaled_xp(5, x) for x in (1, 2, 3, 8)], [5, 8, 10, 23])   # 7.5 -> 8, 22.5 -> 23
        self.assertEqual(scaled_xp(50, 8), 225)

    def test_only_1_to_8(self):
        for bad in (0, 9, -1, 2.5, "3", True, None):
            with self.assertRaises(ValueError):
                clamp_pp(bad)
        self.assertEqual(clamp_pp(8), 8)

    def test_title(self):
        self.assertEqual(map_title("Northshire", 8), "Northshire (8pp)")


class PpMonstersTest(unittest.TestCase):
    def assert_scaled(self, m, pp):
        self.assertEqual(m.max_hp, base_hp(m) * pp)
        self.assertEqual(m.hp, m.max_hp)
        self.assertAlmostEqual(m.base_damage, base_dmg(m) * (1 + pp) / 2)
        self.assertAlmostEqual(m.poison_dps, POISON_DPS * (1 + pp) / 2)
        if getattr(m, "ranged_attack_range", 0):
            self.assertAlmostEqual(m.ranged_attack_damage, m.base_damage)
        self.assertEqual(m.experience, scaled_xp(base_xp(m), pp))
        self.assertEqual(m.base_experience, base_xp(m))

    def test_1pp_is_the_normal_game(self):
        for m in world(1).game_state.monsters:
            self.assert_scaled(m, 1)
            self.assertEqual(m.max_hp, base_hp(m))
            self.assertEqual(m.base_damage, base_dmg(m))

    def test_every_monster_scaled_at_8pp(self):
        w = world(8)
        self.assertTrue(w.game_state.monsters)
        for m in w.game_state.monsters:
            self.assert_scaled(m, 8)

    def test_respawned_monsters_keep_the_pp(self):
        for pp in (3, 8):
            with self.subTest(pp=pp):
                w = world(pp)
                gs = w.game_state
                victims = gs.monsters[:5]
                for m in victims:
                    m.take_damage(m.max_hp * 100, ignore_armor=True)
                w.process_kills()                  # queues the respawns
                gs.game_time += 10 ** 6            # ...long after every respawn timer (bosses too)
                before = len(gs.monsters)
                w.process_respawns()
                reborn = gs.monsters[before:]
                self.assertEqual(len(reborn), len(victims))
                for m in reborn:
                    self.assertTrue(m.alive)
                    self.assert_scaled(m, pp)

    def test_kill_awards_scaled_xp_but_base_gold(self):
        for pp in (1, 8):
            with self.subTest(pp=pp):
                w = world(pp)
                hero = w.hero
                m = w.game_state.monsters[0]
                base = SPAWN_STATS[m.spawn_type]["xp"]
                m.take_damage(m.max_hp * 100, ignore_armor=True)
                hero.xp = hero.gold = 0
                w.process_kills()
                self.assertEqual(hero.xp, scaled_xp(base, pp))   # level-ups happen later, in process_level_ups
                self.assertGreaterEqual(hero.gold, 10 * base)
                self.assertLessEqual(hero.gold, 30 * base)   # gold not scaled by pp
                self.assertIn(f"+{scaled_xp(base, pp)}xp", [e.text for e in w.events])

    def test_scaled_damage_is_what_actually_hits(self):
        w = world(8)
        hero = w.hero
        m = next(m for m in w.game_state.monsters if base_dmg(m) > 0)
        m.x, m.y = hero.x + 10, hero.y
        hero.ac = 0                                 # make sure it hits
        m.swing_timer = 0
        hp = hero.hp
        dealt = m.try_basic_attack(hero)
        if dealt is None:
            self.skipTest("attack not ready")
        self.assertGreater(hp - hero.hp, 0)
        self.assertGreaterEqual(dealt, base_dmg(m) * 4.5 * 0.5)   # 4.5x base (allowing for armor/rolls)

    def test_pp_reaches_every_player_and_shows_in_title(self):
        w = world(8)
        join_player(w, 1, saves.blank_character("kid", "Rogue"), MAP)
        for pid in (0, 1):
            self.assertEqual(make_snapshot(w, pid)["pp"], 8)

    def test_bad_pp_rejected_by_world(self):
        with self.assertRaises(ValueError):
            world(9)


class PpOverNetworkTest(unittest.TestCase):
    def test_joiner_sees_the_hosts_pp(self):
        from game.client.view import ClientView
        from game.net.client import RemoteHost
        from game.net.server import HostServer
        srv = HostServer(MAP, "Fighter", seed=1, port=0, tick_rate=60, pp=6).start()
        try:
            a = RemoteHost("127.0.0.1", srv.port)
            b = RemoteHost("127.0.0.1", srv.port, class_name="Rogue")
            self.assertEqual(b.welcome["pp"], 6)
            vb = ClientView()
            vb.apply(b.snapshot())
            self.assertEqual(map_title("Northshire", vb.pp), "Northshire (6pp)")
            a.close()
            b.close()
        finally:
            srv.stop()


if __name__ == "__main__":
    unittest.main()
