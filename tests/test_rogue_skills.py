"""Rogue kit: Stealth is out of combat only (it opens a fight with Ambush); Poison Dagger arms the next Stab to poison
its target for 15/30/45 damage in total over 5 s (ignores armor, counts as the Rogue's threat); unlock order
L2 Poison Dagger, L4 Stealth, L6 Ambush."""
import random
import tempfile
import unittest

from game import saves
from game.content.skill_tree import POISON_DAGGER_SECS, skill_levels
from game.engine import commands as C
from game.engine.ai import AggroState, aggro_monster
from game.engine.bootstrap import create_world
from game.engine.entities import Condition
from game.engine.snapshot import make_snapshot

MAP = "data/maps/northshire.json"
DT = 1 / 30
saves.SAVE_DIR = tempfile.mkdtemp()


def rogue(level=30, aggroed=True):
    random.seed(1)
    world, p = create_world(MAP, saves.blank_character("r", "Rogue", level=level))
    h = p.hero
    gs = world.game_state
    m = gs.monsters[0]
    del gs.monsters[1:]
    m.x, m.y = h.x + 40, h.y
    m.spawn_x, m.spawn_y = m.x, m.y
    m.hp = m.max_hp = 10 ** 6
    m.speed = m.base_speed = 0
    m.swing_timer = 10 ** 6
    m.regen_rate_combat = m.regen_rate_ooc = 0.0
    if aggroed:
        aggro_monster(m, h, gs.monsters)
    return world, p, m


def cast(world, key, target=None, steps=1):
    x, y = (target.x, target.y) if target is not None else (world.players[0].hero.x, world.players[0].hero.y)
    world.submit(C.Cast(key, x, y, target.eid if target is not None else None), 0)
    for _ in range(steps):
        world.step(DT)
    world.players[0].selected_target = None        # count single hits, no auto-attack


def wait_gcd(world):
    for _ in range(20):
        world.step(DT)


class UnlockTest(unittest.TestCase):
    def test_poison_dagger_first_then_stealth_then_ambush(self):
        self.assertEqual(set(skill_levels("Rogue", 1)), {"Q"})
        self.assertEqual(set(skill_levels("Rogue", 2)), {"Q", "F"})
        self.assertEqual(set(skill_levels("Rogue", 4)), {"Q", "F", "R"})
        self.assertEqual(set(skill_levels("Rogue", 6)), {"Q", "F", "R", "E"})
        self.assertEqual(skill_levels("Rogue", 18), {"Q": 3, "F": 3, "R": 1, "E": 3})


class StealthTest(unittest.TestCase):
    def test_refused_in_combat_costs_nothing(self):
        world, p, m = rogue()
        h = p.hero
        mana = h.mana
        cast(world, "R")
        self.assertFalse(h.stealthed)
        self.assertEqual(h.abilities["R"].remaining, 0)
        self.assertAlmostEqual(h.mana, mana, delta=1.0)        # (regen only)

    def test_allowed_out_of_combat_then_ambush(self):
        world, p, m = rogue(aggroed=False)
        cast(world, "R")
        self.assertTrue(p.hero.stealthed)
        wait_gcd(world)
        before = m.hp
        cast(world, "E", m)
        self.assertLess(m.hp, before)
        self.assertFalse(p.hero.stealthed)
        self.assertEqual(m.aggro_state, AggroState.AGGROED)

    def test_hotbar_shows_stealth_unusable_in_combat(self):
        world, p, m = rogue()
        world.step(DT)
        ab = {a["key"]: a for a in make_snapshot(world, 0)["you"]["abilities"]}
        self.assertFalse(ab["R"]["ready"])
        self.assertTrue(ab["F"]["ready"])


class PoisonDaggerTest(unittest.TestCase):
    def test_next_stab_poisons_for_the_skill_level_dps(self):
        for level, total in ((2, 15), (10, 30), (16, 45)):
            world, p, m = rogue(level)
            cast(world, "F")
            self.assertIn("Poison Dagger", p.hero.buffs)
            wait_gcd(world)
            cast(world, "Q", m)
            poison = [c for c in m.conditions if c.condition == Condition.POISONED]
            self.assertEqual(len(poison), 1, level)
            self.assertAlmostEqual(poison[0].tick_damage * POISON_DAGGER_SECS, total, msg=level)
            self.assertAlmostEqual(poison[0].duration, POISON_DAGGER_SECS, delta=DT * 2)
            self.assertIs(poison[0].by, p.hero)
            self.assertNotIn("Poison Dagger", p.hero.buffs)     # one Stab only

    def test_only_one_stab_is_poisoned(self):
        world, p, m = rogue()
        cast(world, "F")
        wait_gcd(world)
        cast(world, "Q", m)
        m.conditions.clear()
        wait_gcd(world)
        cast(world, "Q", m)
        self.assertFalse(m.has_condition(Condition.POISONED))

    def test_poison_damage_ignores_armor_and_is_the_rogues_threat(self):
        world, p, m = rogue()
        m.apply_condition(Condition.POISONED, POISON_DAGGER_SECS, tick_damage=30 / POISON_DAGGER_SECS, by=p.hero)
        hp, hate = m.hp, m.hate.get(p.hero, 0.0)
        for _ in range(int(POISON_DAGGER_SECS / DT) + 5):
            world.step(DT)
        self.assertAlmostEqual(hp - m.hp, 30, delta=1.0)                # 30 in total, no armor
        self.assertGreater(m.hate[p.hero] - hate, 30 * 0.9)


class MidFightTest(unittest.TestCase):
    def test_poison_dagger_works_while_auto_attacking(self):
        """Pressing Poison Dagger mid-fight used to do nothing: every Stab (0.5 s swing) started the 0.5 s global
        cooldown, so the Rogue was GCD-locked until the mob died."""
        world, p, m = rogue()
        world.submit(C.Cast("Q", m.x, m.y, m.eid), 0)          # start the fight: Stab + auto-attack
        for _ in range(60):
            world.step(DT)
        self.assertIs(p.selected_target, m)                     # still auto-attacking
        world.submit(C.Cast("F", p.hero.x, p.hero.y, m.eid), 0)
        for _ in range(int(1.0 / DT)):                         # within a second the buff is up and spent on a Stab
            world.step(DT)
            if m.has_condition(Condition.POISONED):
                break
        self.assertTrue(m.has_condition(Condition.POISONED))

    def test_skill_pressed_during_global_cooldown_fires_when_it_ends(self):
        world, p, m = rogue()
        p.hero.gcd = 0.3
        world.submit(C.Cast("F", p.hero.x, p.hero.y, None), 0)
        world.step(DT)
        self.assertNotIn("Poison Dagger", p.hero.buffs)          # not yet: GCD
        for _ in range(int(0.4 / DT)):
            world.step(DT)
        self.assertIn("Poison Dagger", p.hero.buffs)             # fired as soon as the GCD ended

    def test_queued_cast_expires(self):
        world, p, m = rogue()
        p.hero.gcd = 5.0
        world.submit(C.Cast("F", p.hero.x, p.hero.y, None), 0)
        for _ in range(int(1.5 / DT)):
            world.step(DT)
        self.assertIsNone(p.queued_cast)
        p.hero.gcd = 0
        world.step(DT)
        self.assertNotIn("Poison Dagger", p.hero.buffs)


class DotFlashTest(unittest.TestCase):
    def test_poison_ticks_do_not_flash_the_target(self):
        """Every hit flashes the sprite for 0.06 s; poison ticks every frame, so it used to flash nonstop."""
        world, p, m = rogue()
        m.apply_condition(Condition.POISONED, 5.0, tick_damage=6, by=p.hero)
        hp = m.hp
        for _ in range(10):
            world.step(DT)
        self.assertLess(m.hp, hp)
        self.assertEqual(m.flash_timer, 0)

    def test_poisoned_monster_shows_the_poison_visual(self):
        from game.client.status_visuals import status_visuals
        world, p, m = rogue()
        m.apply_condition(Condition.POISONED, 5.0, tick_damage=6, by=p.hero)
        snap = make_snapshot(world, 0)
        mob = next(e for e in snap["entities"] if e["id"] == m.eid)
        self.assertTrue(status_visuals(type("V", (), mob)).get("poison"))


if __name__ == "__main__":
    unittest.main()
