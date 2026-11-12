"""The quest bot (game/quest_bot.py) behind tools/early_class_bench.py, the on-demand early-level class benchmark
(level 1 -> 6 in Northshire by questing). Quick checks only; run the benchmark itself on demand:
    .venv/bin/python3 tools/early_class_bench.py"""
import io
import contextlib
import random
import tempfile
import unittest

from game import saves
from game.engine.ai import AggroState, EVADE_TIME, release_aggro
from game.engine.bootstrap import create_world
from game.quest_bot import QuestBot, SKIP

MAP = "data/maps/northshire.json"
DT = 1 / 30
saves.SAVE_DIR = tempfile.mkdtemp()


def bot_run(cls, seed, until_level, cap_min):
    random.seed(seed)
    w, p = create_world(MAP, saves.blank_character(cls.lower(), cls), autopilot=True)
    bot = QuestBot(w, p)
    t, i = 0.0, 0
    with contextlib.redirect_stdout(io.StringIO()):
        while p.hero.level < until_level and t < cap_min * 60:
            if i % 5 == 0:
                bot.step()
            w.step(DT)
            w.events.clear()
            t += DT
            i += 1
    return p, t


class QuestBotTest(unittest.TestCase):
    def test_fighter_quests_to_level_3(self):
        # (cap: the Fighter, smallest mana pool, rests the most; seed 1 reaches level 3 at ~8.5 sim min)
        p, t = bot_run("Fighter", 1, 3, cap_min=12)
        self.assertGreaterEqual(p.hero.level, 3)
        self.assertIn("a_threat_within", p.quests.completed)
        # the next quests are done or being worked on (with slower regen the level can come from kills first)
        worked = set(p.quests.completed) | set(p.quests.to_state()["active"])
        self.assertTrue({"kobold_camp_cleanup", "wolves_across_the_border"} & worked, worked)
        self.assertTrue(set(p.quests.completed).isdisjoint(SKIP))

    def test_rogue_no_longer_stuck_behind_a_wall_corner(self):
        """Seed 2: a Kobold 40 px away behind a wall corner froze the Rogue (no line of sight, too close to walk)."""
        p, t = bot_run("Rogue", 2, 2, cap_min=8)
        self.assertGreaterEqual(p.hero.level, 2)

    def test_garrick_padfoot_bounty_is_skipped(self):
        self.assertIn("bounty_on_garrick_padfoot", SKIP)


class EvadeTest(unittest.TestCase):
    def test_a_monster_that_cannot_get_home_teleports_back(self):
        random.seed(1)
        w, p = create_world(MAP, saves.blank_character("t", "Fighter"))
        m = w.game_state.monsters[0]
        del w.game_state.monsters[1:]
        m.speed = m.base_speed = 0                       # can't walk at all (like stuck behind a wall)
        m.x += 300
        release_aggro(m)
        for _ in range(int((EVADE_TIME + 0.5) / DT)):
            w.step(DT)
        self.assertEqual((m.x, m.y), (m.spawn_x, m.spawn_y))
        self.assertNotEqual(m.aggro_state, AggroState.AGGROED)


if __name__ == "__main__":
    unittest.main()
