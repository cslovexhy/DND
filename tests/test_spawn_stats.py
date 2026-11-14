"""Per-spawn stat overrides in map JSON ("stats" on a spawn entry) tune one map's monster without touching others."""
import tempfile
import unittest

from game import saves
from game.content.monsters import SPAWN_STATS
from game.engine.bootstrap import create_world


def boss_of(map_path):
    saves.SAVE_DIR = tempfile.mkdtemp()
    world, _ = create_world(map_path, saves.blank_character("t", "Fighter"))
    return next(m for m in world.game_state.monsters if m.is_boss)


class SpawnStatsTest(unittest.TestCase):
    def test_boss_room_uses_tuned_ashardalon(self):
        boss = boss_of("data/maps/bossTestRoom.json")
        self.assertAlmostEqual(boss.max_hp, 146 * 50, places=0)

    def test_other_maps_keep_shared_stats(self):
        boss = boss_of("data/maps/haycock.json")
        self.assertEqual(boss.max_hp, SPAWN_STATS[16]["hp"] * 50)


if __name__ == "__main__":
    unittest.main()
