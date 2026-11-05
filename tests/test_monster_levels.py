"""XP curve, monster levels (map "monster_levels") and level-adjusted kill XP."""
import copy
import json
import random
import tempfile
import unittest

from game import saves
from game.content.monsters import SPAWN_STATS, kill_xp
from game.engine.bootstrap import create_world
from game.engine.entities import HP_SCALE
from game.engine.map_schema import validate_map
from game.progression import MAX_LEVEL, xp_to_next_level

MAP = "data/maps/northshire.json"
saves.SAVE_DIR = tempfile.mkdtemp()

NORTHSHIRE_LEVELS = {"Human Cultist": (3, 4), "Kobold Dragonshield": (2, 4), "Grey Wolf": (1, 2), "Snake": (2, 3),
                     "Garrick Padfoot": (5, 5)}


def northshire(level=1, seed=1):
    random.seed(seed)
    world, player = create_world(MAP, saves.blank_character("t", "Fighter", level=level))
    return world, player


class XpCurveTest(unittest.TestCase):
    def test_curve(self):
        self.assertEqual(xp_to_next_level(1), 100)
        for level in range(2, MAX_LEVEL):
            growth = 1 + max(0.05, 0.50 - 0.02 * level)
            # each level costs the previous one x growth (rounded to whole XP)
            self.assertAlmostEqual(xp_to_next_level(level) / xp_to_next_level(level - 1), growth, delta=0.01)
        self.assertEqual([xp_to_next_level(lv) for lv in (2, 3, 10, 20, 29)], [146, 210, 1804, 10152, 16354])

    def test_always_increasing(self):
        costs = [xp_to_next_level(lv) for lv in range(1, MAX_LEVEL)]
        self.assertEqual(costs, sorted(costs))


class KillXpTest(unittest.TestCase):
    def test_formula(self):
        self.assertEqual(kill_xp(30, 1, 3), 30)       # below the monster: full
        self.assertEqual(kill_xp(30, 3, 3), 30)
        self.assertEqual(kill_xp(30, 4, 3), 25)       # 5/6
        self.assertEqual(kill_xp(30, 6, 3), 15)       # 3/6
        self.assertEqual(kill_xp(30, 9, 3), 0)        # 6 above: nothing
        self.assertEqual(kill_xp(30, 20, 3), 0)

    def test_kill_awards_level_adjusted_xp(self):
        world, player = northshire(level=5)
        m = next(m for m in world.game_state.monsters if m.name == "Grey Wolf" and m.level == 1)
        m.take_damage(m.max_hp * 10)
        world.process_kills()
        self.assertEqual(player.hero.xp, kill_xp(10, 5, 1))     # 10 x 2/6 = 3


class MonsterLevelTest(unittest.TestCase):
    def test_northshire_levels_hp_and_xp(self):
        seen = {}
        for seed in range(1, 6):
            world, _ = northshire(seed=seed)
            for m in world.game_state.monsters:
                lo, hi = NORTHSHIRE_LEVELS[m.name]
                self.assertTrue(m.leveled)
                self.assertTrue(lo <= m.level <= hi, (m.name, m.level))
                self.assertEqual(m.experience, m.level * 10)
                mult = 2 if m.name == "Garrick Padfoot" else 1                # per-type HP multiplier
                self.assertEqual(m.max_hp, (50 + 25 * (m.level - 1)) * mult)  # level (x type multiplier) sets HP
                self.assertEqual(m.ac, SPAWN_STATS[m.spawn_type]["ac"])        # AC stays hand-tuned
                seen.setdefault(m.name, set()).add(m.level)
        for name, (lo, hi) in NORTHSHIRE_LEVELS.items():
            self.assertEqual(seen[name], set(range(lo, hi + 1)), name)            # every level in the range shows up

    def test_higher_level_always_has_more_hp(self):
        world, _ = northshire()
        by_level = {}
        for m in world.game_state.monsters:
            if m.name == "Garrick Padfoot":
                continue                       # hp_mult 2 on purpose
            by_level.setdefault(m.level, set()).add(m.max_hp)
        levels = sorted(by_level)
        for a, b in zip(levels, levels[1:]):
            self.assertLess(max(by_level[a]), min(by_level[b]))

    def test_hp_multiplier_defaults_to_1_and_padfoot_is_2(self):
        from game.content.monsters import monster_hp_mult
        self.assertEqual({k for k, s in SPAWN_STATS.items() if monster_hp_mult(s) != 1}, {"garrick_padfoot"})
        self.assertEqual(monster_hp_mult(SPAWN_STATS["garrick_padfoot"]), 2)
        world, _ = northshire()
        garrick = next(m for m in world.game_state.monsters if m.name == "Garrick Padfoot")
        self.assertEqual(garrick.max_hp, 300)          # level 5: 150 x 2

    def test_levelled_damage_is_level_plus_5_rolled_per_hit(self):
        world, _ = northshire()
        for m in world.game_state.monsters:
            self.assertEqual(m.base_damage, m.level + 5)
        m = next(m for m in world.game_state.monsters if m.level == 4)
        rolls = {m.hit_damage() for _ in range(500)}
        self.assertTrue(rolls <= {8, 9, 10}, rolls)          # round(9 x 0.9..1.1) = 8.1..9.9 -> 8..10
        self.assertGreater(len(rolls), 1)                      # it really varies per hit

    def test_default_swing_is_2s_and_bosses_are_20_percent_faster(self):
        world, _ = northshire()
        self.assertEqual({m.weapon_speed for m in world.game_state.monsters}, {2.0})
        random.seed(1)
        room, _ = create_world("data/maps/bossTestRoom.json", saves.blank_character("t", "Fighter"))
        boss = next(m for m in room.game_state.monsters if m.is_boss)
        self.assertAlmostEqual(boss.weapon_speed, 1.6)

    def test_maps_without_levels_are_unchanged(self):
        random.seed(1)
        world, _ = create_world("data/maps/haycock.json", saves.blank_character("t", "Fighter"))
        for m in world.game_state.monsters:
            self.assertFalse(m.leveled)
            self.assertEqual(m.experience, SPAWN_STATS[m.spawn_type]["xp"])
            self.assertEqual(m.max_hp, SPAWN_STATS[m.spawn_type]["hp"] * HP_SCALE)

    def test_bad_monster_levels_are_rejected(self):
        with open(MAP) as f:
            data = json.load(f)
        self.assertEqual(validate_map(data)[0], [])
        for bad in ({"snake": [3, 2]}, {"snake": [0, 2]}, {"snake": "x"}, []):
            d = copy.deepcopy(data)
            d["monster_levels"] = bad
            self.assertTrue(validate_map(d)[0], bad)


if __name__ == "__main__":
    unittest.main()
