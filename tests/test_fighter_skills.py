"""Fighter kit: Strike (basic attack), Heroic Strike (buffs the next Strike/Cleave: +2/4/6 damage, 1.5x threat,
4 s cooldown), Cleave (target + nearest neighbours, 2/3/4 targets, 6 s cooldown, unlocks at L8); every skill has a
threat modifier (hate = damage x threat), default 1.0."""
import random
import tempfile
import unittest

from game import saves
from game.content.heroes import HERO_CLASSES
from game.content.skill_tree import skill_levels
from game.engine import commands as C
from game.engine.bootstrap import create_world

MAP = "data/maps/northshire.json"
DT = 1 / 30
saves.SAVE_DIR = tempfile.mkdtemp()


def fighter(level=30, mobs=1):
    random.seed(1)
    world, p = create_world(MAP, saves.blank_character("f", "Fighter", level=level))
    h = p.hero
    pack = world.game_state.monsters[:mobs]
    del world.game_state.monsters[mobs:]
    for i, m in enumerate(pack):
        m.x, m.y = h.x + 40, h.y + (i - (mobs - 1) / 2) * 10
        m.spawn_x, m.spawn_y = m.x, m.y           # moved here: don't leash back to the old spawn
        m.hp = m.max_hp = 10 ** 6
        m.speed = m.base_speed = 0
        m.swing_timer = 10 ** 6
        m.regen_rate_combat = m.regen_rate_ooc = 0.0
    return world, p, pack


def cast(world, key, target):
    world.submit(C.Cast(key, target.x, target.y, target.eid), 0)
    world.step(DT)


class ThreatTest(unittest.TestCase):
    def test_every_skill_has_a_threat_modifier_default_1(self):
        for info in HERO_CLASSES:
            for ab in info["create"]("x", 0, 0).abilities.values():
                expect = 1.5 if ab.name == "Heroic Strike" else 1.0
                self.assertEqual(ab.threat_mult, expect, ab.name)

    def test_threat_changes_hate_not_damage(self):
        world, p, (m,) = fighter()
        before = m.hp
        m.take_damage(100, source=p.hero, threat=2.0)
        self.assertAlmostEqual(m.hate[p.hero], (before - m.hp) * 2.0)


class HeroicStrikeTest(unittest.TestCase):
    def test_buffs_only_the_next_strike(self):
        world, p, (m,) = fighter()
        h = p.hero
        plain_hp = m.hp
        cast(world, "Q", m)                                     # plain Strike
        plain = plain_hp - m.hp
        plain_hate = m.hate[h]
        step = lambda s: [world.step(DT) for _ in range(int(s / DT))]
        step(2)
        cast(world, "F", m)                                     # Heroic Strike (no damage, no swing)
        self.assertIn("Heroic Strike", h.buffs)
        self.assertEqual(m.hp, plain_hp - plain)
        step(0.6)
        before, hate_before = m.hp, m.hate[h]
        cast(world, "Q", m)
        dealt = before - m.hp
        self.assertGreater(dealt, plain)                          # +6 at skill level 3, minus armor
        self.assertAlmostEqual(m.hate[h] - hate_before, dealt * 1.5)
        self.assertNotIn("Heroic Strike", h.buffs)              # used up by one attack
        step(2)
        before = m.hp
        cast(world, "Q", m)
        self.assertAlmostEqual(before - m.hp, plain, delta=0.01)  # back to normal
        self.assertAlmostEqual(plain_hate, plain)

    def test_cooldown_4s(self):
        world, p, (m,) = fighter()
        cast(world, "F", m)
        self.assertAlmostEqual(p.hero.abilities["F"].remaining, 4.0, delta=DT * 2)


class CleaveTest(unittest.TestCase):
    def test_hits_at_most_2_3_4_targets_by_skill_level(self):
        for level, cap in ((8, 2), (18, 3), (28, 4)):
            world, p, pack = fighter(level=level, mobs=6)
            self.assertEqual(p.hero.abilities["G"].level, {8: 1, 18: 2, 28: 3}[level])
            cast(world, "G", pack[0])
            hit = [m for m in pack if m.hp < m.max_hp]
            self.assertEqual(len(hit), cap, level)
            self.assertIn(pack[0], hit)                         # the target is always one of them
            self.assertAlmostEqual(p.hero.abilities["G"].remaining, 6.0, delta=DT * 2)

    def test_unlocks_at_level_8_after_charge_and_shout(self):
        self.assertNotIn("G", skill_levels("Fighter", 7))
        lv8 = skill_levels("Fighter", 8)
        self.assertEqual({k for k in lv8}, {"Q", "R", "F", "E", "G"})

    def test_strike_is_single_target(self):
        world, p, pack = fighter(mobs=3)
        cast(world, "Q", pack[0])
        self.assertEqual(sum(1 for m in pack if m.hp < m.max_hp), 1)


if __name__ == "__main__":
    unittest.main()
