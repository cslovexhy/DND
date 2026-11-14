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

def map_levels():
    """The level range of every leveled monster type that Northshire spawns (the content is edited in the map
    editor, so the tests read it instead of pinning numbers)."""
    from game.content import monster_defs
    defs = monster_defs.load()
    with open(MAP) as f:
        used = {sp["type"] for sp in json.load(f)["spawns"] if isinstance(sp["type"], int)}
    return {t: defs[t]["level"] for t in used if "level" in defs[t]}


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
        from game.content.monsters import monster_hp_mult
        ranges = map_levels()
        seen, count = {}, {}
        for seed in range(1, 6):
            world, _ = northshire(seed=seed)
            for m in world.game_state.monsters:
                rng = ranges.get(m.spawn_type)
                if rng is None:
                    self.assertFalse(m.leveled, m.name)            # no range on this map: hand-tuned stats
                    continue
                lo, hi = rng
                self.assertTrue(m.leveled)
                self.assertTrue(lo <= m.level <= hi, (m.name, m.level))
                self.assertEqual(m.experience, m.level * 10)
                mult = monster_hp_mult(SPAWN_STATS[m.spawn_type])             # per-type HP multiplier
                self.assertEqual(m.max_hp, (50 + 25 * (m.level - 1)) * mult)  # level (x type multiplier) sets HP
                self.assertEqual(m.ac, SPAWN_STATS[m.spawn_type]["ac"])        # AC stays hand-tuned
                seen.setdefault(m.spawn_type, set()).add(m.level)
                count[m.spawn_type] = count.get(m.spawn_type, 0) + (seed == 1)
        for tid, (lo, hi) in ranges.items():
            if count.get(tid, 0) >= 6 and hi - lo <= 3:            # plenty of spawns: every level shows up
                self.assertEqual(seen[tid], set(range(lo, hi + 1)), tid)

    def test_higher_level_always_has_more_hp(self):
        from game.content.monsters import monster_hp_mult
        world, _ = northshire()
        by_level = {}
        for m in world.game_state.monsters:
            if m.leveled and monster_hp_mult(SPAWN_STATS[m.spawn_type]) == 1:     # (a type multiplier is on purpose)
                by_level.setdefault(m.level, set()).add(m.max_hp)
        levels = sorted(by_level)
        for a, b in zip(levels, levels[1:]):
            self.assertLess(max(by_level[a]), min(by_level[b]))

    def test_hp_multiplier_defaults_to_1_and_applies_to_the_level_hp(self):
        from game.content.monsters import monster_hp_mult
        self.assertEqual(monster_hp_mult({}), 1)
        self.assertEqual(monster_hp_mult({"hp_mult": 2}), 2)
        world, _ = northshire()
        weighted = [m for m in world.game_state.monsters if m.leveled and monster_hp_mult(SPAWN_STATS[m.spawn_type]) != 1]
        for m in weighted:
            self.assertEqual(m.max_hp, (50 + 25 * (m.level - 1)) * monster_hp_mult(SPAWN_STATS[m.spawn_type]))

    def test_levelled_damage_is_level_plus_5_rolled_per_hit(self):
        world, _ = northshire()
        leveled = [m for m in world.game_state.monsters if m.leveled]
        self.assertTrue(leveled)
        for m in leveled:
            self.assertEqual(m.base_damage, m.level + 5)
        m = leveled[0]
        rolls = {m.hit_damage() for _ in range(500)}
        base = m.level + 5
        self.assertTrue(rolls <= set(range(round(base * 0.9), round(base * 1.1) + 1)), rolls)   # x0.9..1.1 rounded
        self.assertGreater(len(rolls), 1)                      # it really varies per hit

    def test_default_swing_is_2s_and_bosses_are_20_percent_faster(self):
        world, _ = northshire()
        for m in world.game_state.monsters:                    # 2.0 s unless the definition sets its own attack speed
            self.assertEqual(m.weapon_speed, SPAWN_STATS[m.spawn_type].get("swing", 2.0), m.name)
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

    def test_bad_definition_levels_are_rejected(self):
        from game.content import monster_defs
        from game.content.items import ITEMS
        from game.content.skill_library import SKILLS
        d = copy.deepcopy(monster_defs.load()[2])
        self.assertEqual(monster_defs.validate(2, d, SKILLS, ITEMS), [])
        for bad in ([3, 2], [0, 2], "x", [1], [1, 31]):
            d["level"] = bad
            self.assertTrue(monster_defs.validate(2, d, SKILLS, ITEMS), bad)

    def test_maps_do_not_carry_levels(self):
        with open(MAP) as f:
            data = json.load(f)
        data["monster_levels"] = {}
        self.assertEqual(validate_map(data)[0], [])


if __name__ == "__main__":
    unittest.main()
