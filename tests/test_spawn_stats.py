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
        self.assertEqual(boss.ac, 16)

    def test_a_spawn_override_beats_the_shared_stats(self):
        import random
        from game.engine.world_map import SpawnPoint
        world, _ = create_world("data/maps/bossTestRoom.json", saves.blank_character("t", "Fighter"))
        plain = world.spawn_single_world_monster(SpawnPoint(16, 5, 5))
        tuned = world.spawn_single_world_monster(SpawnPoint(16, 5, 5, {"ac": 3, "level": [10, 10]}))
        self.assertEqual((plain.ac, tuned.ac, tuned.level), (SPAWN_STATS[16]["ac"], 3, 10))


if __name__ == "__main__":
    unittest.main()
