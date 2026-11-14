"""Monster skills: a spawn type's "kit" gives monsters the hero skills of content/skill_library.py (same damage formula,
cooldown and mana cost), cast through engine/casting.py; poisoners (Cultist, Snake, Grell) poison through Poison
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
from game.engine import casting
from game.engine.ai import AggroState, aggro_monster
from game.engine.bootstrap import create_world
from game.engine.entities import Condition
from game.engine.events import SkillCast
from game.progression import mana_rate

MAP = "data/maps/northshire.json"
DT = 1 / 30
saves.SAVE_DIR = tempfile.mkdtemp()
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))


def arena(mob=9, n=1, hero_cls="Fighter", hero_level=5):
    """A hero and `n` monsters of one monster id from Northshire, aggroed on the hero, the rest of the map removed.
    Monster 9 is given a Poison Dagger kit if the data file doesn't (monster content is edited freely)."""
    random.seed(1)
    world, p = create_world(MAP, saves.blank_character("t", hero_cls, level=hero_level))
    gs = world.game_state
    mobs = [m for m in gs.monsters if m.spawn_type == mob][:n]
    gs.monsters[:] = mobs
    h = p.hero
    for i, m in enumerate(mobs):
        if mob == 9 and "Poison Dagger" not in m.abilities:
            world._give_kit(m, ["Poison Dagger"])
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
        world, p, (m,) = arena(5)
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
        casting.monster_turn(world, healer)
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
        self.assertIsNone(casting.monster_turn(world, healer))

    def test_wall_shields_a_friend_below_half_and_expires(self):
        world, p, (caster, friend) = arena(n=2)
        caster.abilities.clear()                           # (cultists carry Poison Dagger first)
        give(world, caster, "Wall")
        friend.hp = friend.max_hp * 0.4
        casting.monster_turn(world, caster)
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
        self.assertEqual(casting.monster_turn(world, m), "Fire Blast")
        self.assertLess(p.hero.hp, hp)
        self.assertEqual(other.aggro_state, AggroState.IDLE)   # a monster hitting a hero calls no one for help

    def test_not_cast_out_of_range(self):
        world, p, (m,) = arena()
        m.abilities.clear()
        give(world, m, "Fire Blast")
        p.hero.x = m.x + 1000
        self.assertIsNone(casting.monster_turn(world, m))

    def test_heroes_fire_blast_still_pulls_the_monster(self):
        world, p, mobs = arena(9, 1, hero_cls="Wizard", hero_level=10)
        m = mobs[0]
        m.aggro_state = AggroState.IDLE
        m.hate.clear()
        m.x = p.hero.x + 150
        from game.engine import commands as C
        world.submit(C.Cast("R", m.x, m.y, m.eid), 0)
        world.step(DT)
        self.assertEqual(m.aggro_state, AggroState.AGGROED)


class FactionTest(unittest.TestCase):
    def test_enemies_and_friends_by_faction(self):
        from game.engine import combat
        world, p, (m, m2) = arena(n=2)
        self.assertEqual(combat.enemies_of(world, p.hero), [m, m2])
        self.assertEqual(combat.enemies_of(world, m), [p.hero])
        self.assertEqual(set(map(id, combat.friends_of(world, m))), {id(m), id(m2)})
        m2.stealthed = True
        self.assertEqual(combat.enemies_of(world, p.hero), [m])          # stealthed: not a valid target


class OneRuleForEveryoneTest(unittest.TestCase):
    """The same rules hold for heroes and monsters: damage multipliers, conditions, engaging an attacker."""

    def test_demoralized_hero_deals_less(self):
        from game.engine import combat
        world, p, (m,) = arena()
        h = p.hero
        m.hp = m.max_hp = 10 ** 6
        d1 = combat.hit(world, h, m, 100)
        h.buffs["Demoralized"] = {"remaining": 10, "damage_mult": 0.7}
        d2 = combat.hit(world, h, m, 100)
        self.assertAlmostEqual(d2, d1 * 0.7)

    def test_frozen_hero_can_neither_cast_nor_walk(self):
        world, p, (m,) = arena(hero_cls="Wizard", hero_level=10)
        h = p.hero
        h.apply_condition(Condition.FROZEN, 4.0)
        self.assertFalse(casting.try_cast(world, h, h.abilities["R"], m).ok)   # Fire Blast
        x0 = h.x
        from game.engine import commands as C
        world.submit(C.MoveDir(-1, 0), 0)
        for _ in range(15):
            world.step(DT)
        self.assertEqual(h.x, x0)

    def test_slowed_hero_walks_slower(self):
        world, p, mobs = arena()
        world.game_state.monsters.clear()
        h = p.hero
        h.apply_condition(Condition.SLOWED, 5.0, slow_factor=0.5)
        x0 = h.x
        from game.engine import commands as C
        world.submit(C.MoveDir(-1, 0), 0)
        for _ in range(30):
            world.step(DT)
        self.assertAlmostEqual((x0 - h.x) / h.base_speed, 0.5, delta=0.05)

    def test_every_damaging_skill_makes_the_monster_fight_back(self):
        """Frost Nova used to hit without pulling: now every hit engages (aggro + call for help)."""
        world, p, (m,) = arena(hero_cls="Wizard", hero_level=10)
        m.aggro_state = AggroState.IDLE
        m.hate.clear()
        m.aggro_target = None
        self.assertTrue(casting.try_cast(world, p.hero, p.hero.abilities["E"]).ok)   # Frost Nova
        self.assertEqual(m.aggro_state, AggroState.AGGROED)


def with_kit(skill, n=1, hero_cls="Fighter", hero_level=10, dist=40):
    """An arena whose first monster has only `skill`."""
    world, p, mobs = arena(n=n, hero_cls=hero_cls, hero_level=hero_level)
    m = mobs[0]
    m.abilities.clear()
    give(world, m, skill)
    m.x = p.hero.x + dist
    return world, p, mobs


class MonsterSkillsTest(unittest.TestCase):
    """Every skill with an AI hint can be cast by a monster through the same cast path, on heroes by faction."""

    def test_charge_dashes_and_stuns_the_hero(self):
        world, p, (m,) = with_kit("Charge", dist=200)
        if not world.check_los(m.x, m.y, p.hero.x, p.hero.y):
            self.skipTest("no line of sight here")
        self.assertEqual(casting.monster_turn(world, m), "Charge")
        self.assertIsNotNone(m.dash)
        for _ in range(30):
            world.step(DT)
            if m.dash is None:
                break
        self.assertTrue(p.hero.has_condition(Condition.STUNNED))
        self.assertFalse(p.hero.can_act)

    def test_frost_nova_freezes_the_hero(self):
        world, p, (m,) = with_kit("Frost Nova")
        self.assertEqual(casting.monster_turn(world, m), "Frost Nova")
        self.assertTrue(p.hero.has_condition(Condition.FROZEN))

    def test_shout_demoralizes_and_slows_the_hero(self):
        world, p, (m,) = with_kit("Demoralizing Shout")
        self.assertEqual(casting.monster_turn(world, m), "Demoralizing Shout")
        self.assertLess(p.hero.damage_mult, 1.0)
        self.assertLess(p.hero.move_speed, p.hero.base_speed)
        self.assertIsNone(casting.monster_turn(world, m))      # already demoralized: not worth it again

    def test_holy_light_is_a_channel_that_heals_a_friend(self):
        world, p, (healer, friend) = with_kit("Holy Light", n=2)
        friend.hp = friend.max_hp * 0.4
        self.assertEqual(casting.monster_turn(world, healer), "Holy Light")
        self.assertEqual(healer.channel.skill, "Holy Light")
        from game.engine.snapshot import make_snapshot
        world.step(DT)
        snap = {e["id"]: e for e in make_snapshot(world, 0)["entities"]}
        self.assertIsNotNone(snap[healer.eid]["channel"])     # everyone sees the monster's cast bar
        hp = friend.hp
        p.hero.x += 2000
        for _ in range(int(2.5 / DT)):
            world.step(DT)
        self.assertGreater(friend.hp, hp)
        self.assertIsNone(healer.channel)

    def test_frostbolt_channel_then_a_slowing_bolt(self):
        world, p, (m,) = with_kit("Frostbolt", dist=150)
        if not world.check_los(m.x, m.y, p.hero.x, p.hero.y):
            self.skipTest("no line of sight here")
        self.assertEqual(casting.monster_turn(world, m), "Frostbolt")
        for _ in range(int(3 / DT)):
            world.step(DT)
            if p.hero.has_condition(Condition.SLOWED):
                break
        self.assertTrue(p.hero.has_condition(Condition.SLOWED))

    def test_heroic_strike_powers_the_monsters_next_hit(self):
        world, p, (m,) = with_kit("Heroic Strike")
        self.assertEqual(casting.monster_turn(world, m), "Heroic Strike")
        bonus = m.buffs["Heroic Strike"]["bonus"]
        self.assertGreater(bonus, 0)
        m.swing_timer = 0
        from game.engine.entities import Entity
        hp = p.hero.hp
        m.hit_damage = lambda: 10.0
        Entity.try_basic_attack(m, p.hero)
        self.assertNotIn("Heroic Strike", m.buffs)
        self.assertAlmostEqual(hp - p.hero.hp, (10.0 + bonus) * (1 - p.hero.armor_reduction), delta=0.01)

    def test_cleave_hits_two_heroes(self):
        world, p, (m,) = with_kit("Cleave")
        from game.content.heroes import HERO_CLASS_BY_NAME
        comp = world.spawn_companion(HERO_CLASS_BY_NAME["Cleric"], owner=p)
        comp.x, comp.y = p.hero.x, p.hero.y + 15
        hp1, hp2 = p.hero.hp, comp.hp
        self.assertEqual(casting.monster_turn(world, m), "Cleave")
        self.assertLess(p.hero.hp, hp1)
        self.assertLess(comp.hp, hp2)


class TryCastTest(unittest.TestCase):
    def test_reasons(self):
        world, p, (m,) = arena(hero_cls="Wizard", hero_level=10)
        h = p.hero
        fire = h.abilities["R"]
        self.assertEqual(casting.try_cast(world, h, fire, None).reason, "no target")
        self.assertEqual(casting.try_cast(world, h, fire, h).reason, "no target")          # not an enemy
        m.x = h.x + 2000
        self.assertEqual(casting.try_cast(world, h, fire, m).reason, "out of range")
        h.gcd = 0.3
        self.assertEqual(casting.try_cast(world, h, fire, m).reason, "not ready")

    def test_a_failed_cast_spends_nothing(self):
        world, p, (m,) = arena(hero_cls="Wizard", hero_level=10)
        h, fire = p.hero, p.hero.abilities["R"]
        m.x = h.x + 2000
        mana = h.mana
        casting.try_cast(world, h, fire, m)
        self.assertEqual((fire.remaining, h.mana, h.gcd), (0, mana, 0))


class PlaygroundTest(unittest.TestCase):
    def _run(self, *argv):
        import contextlib
        import io
        import skill_playground
        with contextlib.redirect_stdout(io.StringIO()):
            return skill_playground.main(list(argv))

    def test_every_castable_skill_gets_cast(self):
        import skill_playground
        for skill in casting.AI_CASTABLE:
            fight = skill in skill_playground.SUPPORT_SKILLS         # support skills need someone hurt
            out = self._run("--skill", skill, "--secs", "25", *(() if fight else ("--passive",)))
            self.assertTrue(any(c.get(skill) for c in out["casts"].values()), (skill, out))

    def test_support_skills_get_a_friend(self):
        out = self._run("--skill", "Renew", "--secs", "5")
        self.assertEqual(len(out["casts"]), 2)


if __name__ == "__main__":
    unittest.main()
