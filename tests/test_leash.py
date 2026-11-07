"""Leash: a monster pulled beyond its leash range keeps fighting while it is being hit (or hits someone); it gives
up only after LEASH_TIME seconds without combat. It used to reset the instant it was past the line, re-aggro on the
next hit and reset again (ping-pong)."""
import random
import tempfile
import unittest

from game import saves
from game.engine import commands as C
from game.engine.ai import AggroState, LEASH_TIME
from game.engine.bootstrap import create_world

MAP = "data/maps/northshire.json"
DT = 1 / 30
saves.SAVE_DIR = tempfile.mkdtemp()


def pulled_far():
    """A Cleric 200 px from a monster that is already 550 px from its spawn (past its 500 px leash), fighting."""
    random.seed(1)
    w, p = create_world(MAP, saves.blank_character("c", "Cleric", level=10))
    h = p.hero
    m = w.game_state.monsters[0]
    del w.game_state.monsters[1:]
    m.hp = m.max_hp = 10 ** 6
    m.regen_rate_combat = m.regen_rate_ooc = 0.0
    m.speed = m.base_speed = 0                     # it can't reach the cleric: only her hits keep it busy
    m.x, m.y = h.x + 150, h.y
    m.spawn_x, m.spawn_y = m.x + 550, m.y           # spawn far behind it
    from game.engine.ai import aggro_monster
    aggro_monster(m, h, w.game_state.monsters)
    return w, p, m


class LeashTest(unittest.TestCase):
    def test_keeps_fighting_while_being_hit(self):
        w, p, m = pulled_far()
        states = []
        for i in range(int(12 / DT)):
            if i % 30 == 0:                         # wand it once a second
                w.submit(C.Cast("Q", m.x, m.y, m.eid), 0)
            w.step(DT)
            states.append(m.aggro_state)
        self.assertNotIn(AggroState.RESETTING, states)

    def test_gives_up_after_leash_time_without_combat(self):
        w, p, m = pulled_far()
        resets_at = None
        for i in range(int(10 / DT)):
            w.step(DT)
            if m.aggro_state == AggroState.RESETTING:
                resets_at = i * DT
                break
        self.assertIsNotNone(resets_at)
        self.assertAlmostEqual(resets_at, LEASH_TIME, delta=0.2)

    def test_within_leash_range_never_resets(self):
        w, p, m = pulled_far()
        m.spawn_x, m.spawn_y = m.x + 100, m.y
        for _ in range(int(8 / DT)):
            w.step(DT)
        self.assertEqual(m.aggro_state, AggroState.AGGROED)


if __name__ == "__main__":
    unittest.main()
