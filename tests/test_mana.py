"""Mana: per-class pools (level 1 -> 30, linear); skill costs make every class spend the same mana per second at a
level when it casts everything as soon as it is ready (progression.mana_rate); casting spends mana, an unaffordable
skill can't be cast, mana regenerates and refills on level-up / respawn; the AIs cope with running dry."""
import random
import tempfile
import unittest

from game import saves
from game.content.heroes import HERO_CLASSES
from game.engine import commands as C
from game.engine.bootstrap import create_world
from game.engine.entities import Ability
from game.engine.snapshot import make_snapshot
from game.progression import HERO_MANA, MAX_LEVEL, hero_max_mana, mana_rate

MAP = "data/maps/northshire.json"
DT = 1 / 30
saves.SAVE_DIR = tempfile.mkdtemp()


def hero_at(cls, level):
    random.seed(1)
    world, player = create_world(MAP, saves.blank_character("t", cls, level=level))
    world.game_state.monsters.clear()
    return world, player


class ManaPoolTest(unittest.TestCase):
    def test_pools_by_class(self):
        expect = {"Wizard": (150, 2000), "Rogue": (100, 1000), "Cleric": (120, 1500), "Paladin": (120, 1300),
                  "Fighter": (80, 800)}
        self.assertEqual(HERO_MANA, expect)
        for cls, (lo, hi) in expect.items():
            self.assertEqual(hero_max_mana(cls, 1), lo)
            self.assertEqual(hero_max_mana(cls, MAX_LEVEL), hi)

    def test_hero_starts_full_at_its_level(self):
        for info in HERO_CLASSES:
            cls = info["class"]
            for level in (1, 10, MAX_LEVEL):
                _, p = hero_at(cls, level)
                self.assertEqual(p.hero.max_mana, hero_max_mana(cls, level), f"{cls} L{level}")
                self.assertEqual(p.hero.mana, p.hero.max_mana, f"{cls} L{level}")

    def test_snapshot_carries_mana(self):
        world, p = hero_at("Wizard", 1)
        snap = make_snapshot(world, 0)
        me = next(e for e in snap["entities"] if e["kind"] == "hero")
        self.assertEqual((me["mana"], me["max_mana"]), (150, 150))
        q = next(a for a in snap["you"]["abilities"] if a["key"] == "Q")
        self.assertEqual(q["mana_cost"], p.hero.abilities["Q"].mana_cost)
        self.assertGreater(q["mana_cost"], 0)
        self.assertTrue(q["has_mana"])


class ManaCostTest(unittest.TestCase):
    def test_max_burn_is_the_same_mana_rate_for_every_class_at_every_level(self):
        """Casting every unlocked in-combat skill whenever it is ready spends mana_rate(level) per second (up to the
        0.1-mana rounding of each cost), whatever the class: a bigger pool lasts longer."""
        for info in HERO_CLASSES:
            cls = info["class"]
            for level in range(1, MAX_LEVEL + 1):
                _, p = hero_at(cls, level)
                abs_ = [ab for ab in p.hero.abilities.values() if not ab.mana_secs]   # in-combat skills
                burn = sum(ab.mana_cost / ab.mana_gap for ab in abs_)
                slack = sum(0.05 / ab.mana_gap for ab in abs_)
                self.assertAlmostEqual(burn, mana_rate(level), delta=slack + 1e-9, msg=f"{cls} L{level}")

    def test_cost_grows_with_level(self):
        for info in HERO_CLASSES:
            cls = info["class"]
            _, low = hero_at(cls, 10)
            _, high = hero_at(cls, MAX_LEVEL)
            for key, ab in low.hero.abilities.items():
                self.assertGreater(high.hero.abilities[key].mana_cost, ab.mana_cost, f"{cls} {ab.name}")

    def test_melee_basic_attacks_cheap_caster_basic_attacks_dear(self):
        """Out of mana a melee hero still swings its cheap basic attack; a caster's basic attack is its main cost."""
        def basic_share(cls):
            _, p = hero_at(cls, MAX_LEVEL)
            abs_ = p.hero.abilities
            return (abs_["Q"].mana_cost / abs_["Q"].mana_gap) / mana_rate(MAX_LEVEL)
        for cls in ("Fighter", "Paladin", "Rogue"):
            self.assertLess(basic_share(cls), 0.15, cls)
        for cls in ("Cleric", "Wizard"):
            self.assertGreater(basic_share(cls), 0.4, cls)

    def test_rogue_opener_costs_seconds_of_mana_rate(self):
        """Stealth + Ambush only open a fight, so they sit outside the in-combat budget: 1 s and 4 s of mana_rate."""
        for level in (6, 18, MAX_LEVEL):
            _, r = hero_at("Rogue", level)
            stealth, ambush = r.hero.abilities["R"], r.hero.abilities["E"]
            self.assertAlmostEqual(stealth.mana_cost, mana_rate(level), delta=0.05)
            self.assertAlmostEqual(ambush.mana_cost, 4 * mana_rate(level), delta=0.05)

    def test_mana_gap_of_basic_attacks_is_the_swing(self):
        _, f = hero_at("Fighter", MAX_LEVEL)
        self.assertEqual(f.hero.abilities["Q"].mana_gap, f.hero.weapon_speed)

    def test_monster_style_ability_is_free(self):
        ab = Ability("Bite", cooldown=1.0)
        self.assertEqual(ab.mana_cost, 0)
        self.assertTrue(ab.is_ready())


class ManaCastTest(unittest.TestCase):
    def test_cast_spends_mana(self):
        world, pal = hero_at("Paladin", 2)              # Righteous Seal (R)
        h = pal.hero
        before = h.mana
        cost = h.abilities["R"].mana_cost
        world.submit(C.Cast("R", 0, 0, None), 0)
        world.step(DT)
        self.assertIn("Righteous Seal", h.buffs)
        self.assertAlmostEqual(h.mana, before - cost, delta=h.max_mana * h.mana_regen_ooc * DT * 2)

    def test_not_enough_mana_blocks_the_cast(self):
        world, pal = hero_at("Paladin", 2)
        h = pal.hero
        h.mana = 1.0
        h.mana_regen_ooc = h.mana_regen_combat = 0.0
        seal = h.abilities["R"]
        self.assertFalse(seal.is_ready())
        world.submit(C.Cast("R", 0, 0, None), 0)
        world.step(DT)
        self.assertNotIn("Righteous Seal", h.buffs)
        self.assertEqual(seal.remaining, 0)              # no cooldown started either
        self.assertEqual(h.mana, 1.0)

    def test_mana_regenerates_up_to_max(self):
        world, p = hero_at("Wizard", 1)
        h = p.hero
        h.mana = 0.0
        for _ in range(30):                              # 1 s out of combat: 2% of max
            world.step(DT)
        self.assertAlmostEqual(h.mana, h.max_mana * h.mana_regen_ooc, delta=0.5)
        h.mana = h.max_mana - 0.01
        world.step(DT)
        self.assertEqual(h.mana, h.max_mana)

    def test_respawn_refills_mana(self):
        world, p = hero_at("Wizard", 1)
        p.hero.mana = 0.0
        world.respawn_player(p)
        self.assertEqual(p.hero.mana, p.hero.max_mana)


class RegenByLevelTest(unittest.TestCase):
    """Out-of-combat HP / mana regen: 2% of max per second at L1 -> 1% at L10 -> 0.5% at L30, linear; in combat 10%
    of that."""

    def test_curve(self):
        from game.progression import regen_rate
        for level, want in ((1, 0.02), (4, 0.02 - 0.01 / 3), (10, 0.01), (20, 0.0075), (30, 0.005), (40, 0.005)):
            self.assertAlmostEqual(regen_rate(level), want, msg=level)

    def test_heroes_get_their_levels_rates(self):
        from game.progression import regen_rate
        for level in (1, 10, 30):
            _, p = hero_at("Fighter", level)
            h = p.hero
            self.assertAlmostEqual(h.regen_rate_ooc, regen_rate(level))
            self.assertAlmostEqual(h.mana_regen_ooc, regen_rate(level))
            self.assertAlmostEqual(h.regen_rate_combat, regen_rate(level) * 0.1)
            self.assertAlmostEqual(h.mana_regen_combat, regen_rate(level) * 0.1)

    def test_level_up_lowers_the_rate(self):
        from game.progression import regen_rate, xp_to_next_level
        world, p = hero_at("Cleric", 9)
        p.hero.xp = xp_to_next_level(9)
        world.step(DT)
        self.assertEqual(p.hero.level, 10)
        self.assertAlmostEqual(p.hero.regen_rate_ooc, 0.01)

    def test_monsters_keep_the_flat_rate(self):
        random.seed(1)
        world, _ = create_world(MAP, saves.blank_character("t", "Fighter", level=30))
        m = world.game_state.monsters[0]
        self.assertEqual((m.regen_rate_ooc, m.regen_rate_combat), (0.02, 0.02 * 0.1))


def hero_with_mobs(cls, level, n, dist):
    """A hero and n aggroed, harmless, unkillable mobs standing `dist` px to its right."""
    from game.engine.ai import aggro_monster
    random.seed(1)
    world, p = create_world(MAP, saves.blank_character("t", cls, level=level))
    gs = world.game_state
    h = p.hero
    mobs = gs.monsters[:n]
    del gs.monsters[n:]
    for i, m in enumerate(mobs):
        m.x, m.y = h.x + dist, h.y + i * 10
        m.spawn_x, m.spawn_y = m.x, m.y
        m.hp = m.max_hp = 10 ** 6
        m.speed = m.base_speed = 0
        m.swing_timer = 10 ** 6
        aggro_monster(m, h, gs.monsters)
    return world, p, mobs


class OutOfManaAITest(unittest.TestCase):
    def test_rogue_in_combat_never_stealths_and_arms_poison_then_stabs(self):
        world, p, mobs = hero_with_mobs("Rogue", MAX_LEVEL, 1, 40)
        h = p.hero
        self.assertTrue(h.abilities["R"].is_ready() and h.abilities["E"].remaining <= 0)   # opener available...
        action = p.hero_ai.update(mobs, DT, world.is_wall)
        self.assertEqual(action["use_ability"], "F")       # ...but in combat: Poison Dagger, not Stealth
        h.buffs["Poison Dagger"] = {"remaining": 10.0, "dps": 6, "duration": 5.0}
        action = p.hero_ai.update(mobs, DT, world.is_wall)
        self.assertEqual(action["use_ability"], "Q")       # then the Stab that carries the poison

    def test_rogue_opens_with_stealth_out_of_combat(self):
        world, p, mobs = hero_with_mobs("Rogue", MAX_LEVEL, 1, 200)
        for m in mobs:                                     # idle mob, nobody fighting the Rogue
            from game.engine.ai import release_aggro
            release_aggro(m)
            m.aggro_state = "idle"
        action = p.hero_ai.update(mobs, DT, world.is_wall)
        self.assertEqual(action["use_ability"], "R")

    def test_lone_melee_hero_walks_back_to_a_far_target(self):
        """A lone melee hero backs off from a pack only while a mob is close; further away it walks to its target
        (it used to keep 'kiting' forever, e.g. after it ran out of mana)."""
        world, p, mobs = hero_with_mobs("Paladin", 10, 2, 300)
        ai = p.hero_ai
        self.assertFalse(ai.in_party())
        target = mobs[0]
        self.assertEqual(ai.melee_move_to(mobs, target.x, target.y), (target.x, target.y))


if __name__ == "__main__":
    unittest.main()
