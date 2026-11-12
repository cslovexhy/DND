"""Monster skills: a spawn type's "kit" gives monsters the hero skills of content/skill_library.py (same damage formula,
cooldown and mana cost), cast by engine/monster_casting.py; poisoners (Cultist, Snake, Grell) poison through Poison
Dagger instead of a hard-coded on-hit poison. Also the skill playground tool (tools/skill_playground.py)."""
import os
import random
import sys
import tempfile
import unittest

from game import saves
from game.content import skill_library
from game.content.heroes import HERO_CLASSES
from game.content.monsters import SPAWN_STATS, monster_max_mana, monster_skill_level
from game.content.skill_tree import POISON_DAGGER_SECS
from game.engine import monster_casting
from game.engine.ai import AggroState, aggro_monster
from game.engine.bootstrap import create_world
from game.engine.entities import Condition
from game.engine.events import SkillCast
from game.progression import mana_rate

MAP = "data/maps/northshire.json"
DT = 1 / 30
saves.SAVE_DIR = tempfile.mkdtemp()
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))


def arena(mob="Human Cultist", n=1, hero_cls="Fighter", hero_level=5):
    """A hero and `n` monsters of one name from Northshire, aggroed on the hero, the rest of the map removed."""
    random.seed(1)
    world, p = create_world(MAP, saves.blank_character("t", hero_cls, level=hero_level))
    gs = world.game_state
    mobs = [m for m in gs.monsters if m.name == mob][:n]
    gs.monsters[:] = mobs
    h = p.hero
    for i, m in enumerate(mobs):
        m.x, m.y = h.x + 40, h.y + i * 20
        m.spawn_x, m.spawn_y = m.x, m.y
        aggro_monster(m, h, gs.monsters)
    return world, p, mobs


def give(world, m, name):
    """Give monster `m` one more kit skill (as World._give_kit does)."""
    world._give_kit(m, list(m.abilities) + [name])


def casts(world):
    return [ev for ev in world.events if isinstance(ev, SkillCast)]


class LibraryTest(unittest.TestCase):
    def test_every_hero_skill_comes_from_the_library(self):
        for info in HERO_CLASSES:
            for ab in info["create"]("x", 0, 0).abilities.values():
                lib = skill_library.make_skill(ab.name)
                for f in ("cooldown", "a_levels", "b_levels", "effect_levels", "mana_weight", "mana_secs", "range"):
                    self.assertEqual(getattr(lib, f), getattr(ab, f), f"{ab.name}.{f}")

    def test_make_skill_gives_a_fresh_ability(self):
        a, b = skill_library.make_skill("Renew"), skill_library.make_skill("Renew")
        self.assertIsNot(a, b)


class KitTest(unittest.TestCase):
    def test_poisoners_have_poison_dagger(self):
        for key in ("human_cultist", "snake", "grell"):
            self.assertEqual(SPAWN_STATS[key]["kit"], ["Poison Dagger"], key)
            self.assertNotIn("condition", SPAWN_STATS[key])

    def test_skill_level_follows_monster_level(self):
        self.assertEqual([monster_skill_level(lv) for lv in (1, 9, 10, 19, 20, 30)], [1, 1, 2, 2, 3, 3])

    def test_spawned_cultist_gets_its_kit_mana_and_hero_costs(self):
        world, p, (m,) = arena()
        ab = m.abilities["Poison Dagger"]
        self.assertEqual(ab.level, monster_skill_level(m.level))
        self.assertEqual(m.max_mana, monster_max_mana(m.level))
        self.assertEqual(m.mana, m.max_mana)
        # same cost rule as a hero: mana_rate(level) x time between casts x its share of the kit (all of it here)
        self.assertAlmostEqual(ab.mana_cost, mana_rate(m.level) * ab.cooldown, delta=0.05)

    def test_monsters_without_a_kit_have_no_mana(self):
        world, p, (m,) = arena("Grey Wolf")
        self.assertEqual((m.abilities, m.max_mana), ({}, 0))


class PoisonDaggerTest(unittest.TestCase):
    def test_cultist_arms_in_melee_and_its_next_hit_poisons(self):
        world, p, (m,) = arena()
        h = p.hero
        world.step(DT)
        self.assertIn("Poison Dagger", [ev.skill for ev in casts(world)])
        self.assertIn("Poison Dagger", m.buffs)
        for _ in range(int(3 / DT)):                       # its next swing lands within a swing time
            world.step(DT)
            if h.has_condition(Condition.POISONED):
                break
        poison = next(c for c in h.conditions if c.condition == Condition.POISONED)
        self.assertIs(poison.by, m)
        total = m.abilities["Poison Dagger"].flat_bonus      # 15 at skill level 1
        self.assertAlmostEqual(poison.tick_damage * POISON_DAGGER_SECS, total)
        self.assertNotIn("Poison Dagger", m.buffs)

    def test_no_poison_without_the_skill(self):
        """The old hard-coded on-hit poison is gone: an out-of-mana cultist just hits."""
        world, p, (m,) = arena()
        m.mana = 0.0
        m.mana_regen_ooc = m.mana_regen_combat = 0.0
        for _ in range(int(8 / DT)):
            world.step(DT)
            self.assertFalse(p.hero.has_condition(Condition.POISONED))
        self.assertEqual(casts(world), [])

    def test_casting_spends_mana_and_respects_the_cooldown(self):
        world, p, (m,) = arena()
        ab = m.abilities["Poison Dagger"]
        world.step(DT)
        self.assertAlmostEqual(m.mana, m.max_mana - ab.mana_cost, delta=1.0)
        self.assertGreater(ab.remaining, 0)
        n = 0
        for _ in range(int(20 / DT)):
            world.step(DT)
            n += len(casts(world))
            world.events.clear()
        self.assertLessEqual(n, 20 / ab.cooldown + 1)


class SupportTest(unittest.TestCase):
    def test_renew_goes_on_the_most_hurt_friend(self):
        world, p, (healer, friend) = arena(n=2)
        healer.abilities.clear()                           # (cultists carry Poison Dagger first)
        give(world, healer, "Renew")
        friend.hp = friend.max_hp * 0.5
        healer.hp = healer.max_hp * 0.65
        before = friend.hp
        monster_casting.cast_skills(world, healer)
        self.assertIn("Renew", friend.buffs)
        self.assertNotIn("Renew", healer.buffs)
        p.hero.x += 2000                                  # (nobody hits anyone: just the heal)
        for _ in range(int(9 / DT)):
            world.step(DT)
        self.assertGreater(friend.hp, before)
        self.assertEqual(friend.heal_credits, [])          # monster heals make no hate: drained every frame

    def test_no_renew_when_nobody_is_hurt(self):
        world, p, (healer, friend) = arena(n=2)
        healer.abilities.clear()                           # (cultists carry Poison Dagger first)
        give(world, healer, "Renew")
        self.assertIsNone(monster_casting.cast_skills(world, healer))

    def test_wall_shields_a_friend_below_half_and_expires(self):
        world, p, (caster, friend) = arena(n=2)
        caster.abilities.clear()                           # (cultists carry Poison Dagger first)
        give(world, caster, "Wall")
        friend.hp = friend.max_hp * 0.4
        monster_casting.cast_skills(world, caster)
        self.assertGreater(friend.absorb_shield, 0)
        p.hero.x += 2000
        for _ in range(int(16 / DT)):
            world.step(DT)
        self.assertEqual(friend.absorb_shield, 0)


class FireBlastTest(unittest.TestCase):
    def test_hits_the_hero_in_range_without_pulling_other_mobs(self):
        world, p, (m, other) = arena(n=2)
        m.abilities.clear()
        give(world, m, "Fire Blast")
        other.aggro_state = AggroState.IDLE
        other.hate.clear()
        hp = p.hero.hp
        self.assertEqual(monster_casting.cast_skills(world, m), "Fire Blast")
        self.assertLess(p.hero.hp, hp)
        self.assertEqual(other.aggro_state, AggroState.IDLE)   # a monster hitting a hero calls no one for help

    def test_not_cast_out_of_range(self):
        world, p, (m,) = arena()
        m.abilities.clear()
        give(world, m, "Fire Blast")
        p.hero.x = m.x + 1000
        self.assertIsNone(monster_casting.cast_skills(world, m))

    def test_heroes_fire_blast_still_pulls_the_monster(self):
        world, p, mobs = arena("Human Cultist", 1, hero_cls="Wizard", hero_level=10)
        m = mobs[0]
        m.aggro_state = AggroState.IDLE
        m.hate.clear()
        m.x = p.hero.x + 150
        from game.engine import commands as C
        world.submit(C.Cast("R", m.x, m.y, m.eid), 0)
        world.step(DT)
        self.assertEqual(m.aggro_state, AggroState.AGGROED)


class PlaygroundTest(unittest.TestCase):
    def _run(self, *argv):
        import contextlib
        import io
        import skill_playground
        with contextlib.redirect_stdout(io.StringIO()):
            return skill_playground.main(list(argv))

    def test_every_castable_skill_gets_cast(self):
        for skill in monster_casting.CASTABLE:
            out = self._run("--skill", skill, "--secs", "25")
            self.assertTrue(any(c.get(skill) for c in out["casts"].values()), (skill, out))

    def test_support_skills_get_a_friend(self):
        out = self._run("--skill", "Renew", "--secs", "5")
        self.assertEqual(len(out["casts"]), 2)


if __name__ == "__main__":
    unittest.main()
