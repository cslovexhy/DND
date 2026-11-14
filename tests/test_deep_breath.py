"""Ashardalon's Deep Breath: at 50% and again at 20% HP he "took a deep breath..." for 1.5 s, then a red zone (radius 200)
lasts 3 s and pulses 3 times; each pulse hits every hero inside for 100 (300 in all)."""
import json
import unittest

from game import saves
from game.client.view import ClientView
from game.engine.ai import aggro_monster
from game.engine.bootstrap import create_world, join_player
from game.engine.events import FloatText
from game.engine.snapshot import make_snapshot

MAP = "data/maps/bossTestRoom.json"
DT = 1 / 30
WINDUP = 1.5


def room():
    world, p0 = create_world(MAP, saves.blank_character("tank", "Fighter"))
    p1 = join_player(world, 1, saves.blank_character("buddy", "Cleric"), MAP)
    gs = world.game_state
    boss = next(m for m in gs.monsters if m.is_boss)
    gs.monsters[:] = [boss]
    boss.regen_rate_combat = boss.regen_rate_ooc = 0.0       # (so HP percentages stay where the test puts them)
    boss.attack_range = 1                                     # (and the boss does not hurt anyone: only the zone does)
    boss.base_damage = 0
    boss.speed = boss.base_speed = 0                          # (and stands still, so the zone is where the boss is)
    aggro_monster(boss, p0.hero, [boss])
    for p in (p0, p1):
        p.hero.max_hp = 100000
        p.hero.hp = p.hero.max_hp
        p.hero.regen_rate_combat = p.hero.regen_rate_ooc = 0.0    # (so only the zone changes their HP)
    return world, p0, p1, boss


def run(world, seconds):
    for _ in range(round(seconds / DT)):
        world.step(DT)


def breathe(world, boss, pct=0.49):
    """Drop the boss under a threshold and run through the wind-up: the zone is on the ground afterwards."""
    boss.hp = boss.max_hp * pct
    run(world, WINDUP + 0.1)


class SkillDataTest(unittest.TestCase):
    def test_ashardalon_has_deep_breath_and_other_bosses_do_not(self):
        world, _, _, boss = room()
        self.assertEqual(boss.skills["deep_breath"],
                         {"radius": 200, "duration": 3.0, "cycles": 3, "dps": 100, "windup": 1.5,
                          "at_hp_pct": (0.5, 0.2)})
        other = world.spawn_single_world_monster(type(boss.spawn_point)(21, 20, 15))
        self.assertEqual(other.skills, {})


class WindupTest(unittest.TestCase):
    def test_the_message_appears_first_then_the_zone_after_the_windup(self):
        world, _, _, boss = room()
        self.assertEqual(boss.say, "")
        boss.hp = boss.max_hp * 0.49
        run(world, 0.2)
        self.assertEqual(boss.say, "Ashardalon took a deep breath...")
        self.assertEqual(world.hazards, [])                       # not yet
        run(world, WINDUP - 0.5)
        self.assertEqual(world.hazards, [])                       # still winding up
        self.assertEqual(boss.say, "Ashardalon took a deep breath...")
        run(world, 0.6)
        self.assertEqual(len(world.hazards), 1)                   # now the zone
        self.assertEqual(boss.say, "")                            # and the message is gone

    def test_the_message_is_in_the_snapshot_for_the_client(self):
        world, _, _, boss = room()
        boss.hp = boss.max_hp * 0.49
        run(world, 0.2)
        snap = make_snapshot(world, 0)
        monster = next(e for e in snap["entities"] if e["kind"] == "monster")
        self.assertEqual(monster["say"], "Ashardalon took a deep breath...")
        v = ClientView()
        v.apply(snap)
        self.assertEqual(v.monsters[0].say, "Ashardalon took a deep breath...")

    def test_a_boss_that_dies_while_winding_up_leaves_no_zone_and_no_message(self):
        world, _, _, boss = room()
        boss.hp = boss.max_hp * 0.49
        run(world, 0.5)
        boss.hp = 0
        boss.alive = False
        run(world, 2.0)
        self.assertEqual(world.hazards, [])
        self.assertEqual(world.casts, [])
        self.assertEqual(boss.say, "")


class TriggerTest(unittest.TestCase):
    def test_no_breath_above_50_percent(self):
        world, _, _, boss = room()
        boss.hp = boss.max_hp * 0.51
        run(world, 3)
        self.assertEqual(world.hazards, [])
        self.assertEqual(boss.say, "")

    def test_breath_at_50_percent_then_again_at_20_but_each_only_once(self):
        world, _, _, boss = room()
        breathe(world, boss, 0.49)
        self.assertEqual(len(world.hazards), 1)
        z = world.hazards[0]
        self.assertEqual((z.radius, z.duration, z.cycles, z.pulse_damage), (200, 3.0, 3, 100))
        self.assertEqual((z.x, z.y), (boss.x, boss.y))
        run(world, 3.5)
        self.assertEqual(world.hazards, [])                       # it ended
        boss.hp = boss.max_hp * 0.40
        run(world, WINDUP + 1)
        self.assertEqual(world.hazards, [])                       # not again at 40%
        breathe(world, boss, 0.19)
        self.assertEqual(len(world.hazards), 1)                   # the 20% one
        run(world, 3.5)
        boss.hp = boss.max_hp * 0.05
        run(world, WINDUP + 1)
        self.assertEqual(world.hazards, [])                       # and no third

    def test_both_thresholds_crossed_at_once_breathe_one_after_the_other_not_together(self):
        world, _, _, boss = room()
        boss.hp = boss.max_hp * 0.10                              # a burst took it from 60% to 10%
        run(world, WINDUP + 0.1)
        self.assertEqual(len(world.hazards), 1)
        run(world, 3.0)                                           # first zone over, second one winding up
        self.assertLessEqual(len(world.hazards), 1)
        run(world, WINDUP + 3.5)
        self.assertEqual(world.hazards, [])
        self.assertEqual(world.casts, [])

    def test_the_boss_does_not_breathe_before_it_is_aggroed(self):
        world, _, _, boss = room()
        boss.aggro_state = "idle"
        boss.hp = boss.max_hp * 0.3
        run(world, 3)
        self.assertEqual(world.hazards, [])


class DamageTest(unittest.TestCase):
    def test_three_pulses_of_100_for_a_hero_inside_300_total_ignoring_armor(self):
        world, p0, p1, boss = room()
        breathe(world, boss)
        for p in (p0, p1):
            p.hero.x, p.hero.y = boss.x + 150, boss.y             # inside the 200 px radius
            p.hero.hp = p.hero.max_hp
        run(world, 3.4)
        for p in (p0, p1):
            self.assertAlmostEqual(p.hero.max_hp - p.hero.hp, 300, delta=0.01)

    def test_pulses_land_halfway_through_each_cycle(self):
        world, p0, p1, boss = room()
        boss.hp = boss.max_hp * 0.49
        run(world, WINDUP + 0.05)
        p0.hero.x, p0.hero.y = boss.x + 100, boss.y
        p0.hero.hp = p0.hero.max_hp
        z = world.hazards[0]
        seen = []
        last = p0.hero.hp
        while world.hazards:
            world.step(DT)
            if p0.hero.hp < last:
                seen.append(round(z.elapsed, 1))
            last = p0.hero.hp
        self.assertEqual(seen, [0.5, 1.5, 2.5])

    def test_hero_outside_the_circle_takes_nothing(self):
        world, p0, p1, boss = room()
        breathe(world, boss)
        p0.hero.x, p0.hero.y = boss.x + 201, boss.y
        p0.hero.hp = p0.hero.max_hp
        run(world, 3.4)
        self.assertEqual(p0.hero.hp, p0.hero.max_hp)

    def test_leaving_the_circle_early_avoids_the_later_pulses(self):
        world, p0, p1, boss = room()
        boss.hp = boss.max_hp * 0.49
        run(world, WINDUP + 0.05)
        p0.hero.x, p0.hero.y = boss.x + 150, boss.y
        p0.hero.hp = p0.hero.max_hp
        run(world, 0.7)                                           # the first pulse (0.5 s) hits...
        p0.hero.x = boss.x + 300                                  # ...then the hero steps out
        run(world, 3.0)
        self.assertAlmostEqual(p0.hero.max_hp - p0.hero.hp, 100, delta=0.01)

    def test_entering_late_only_takes_the_remaining_pulses(self):
        world, p0, p1, boss = room()
        boss.hp = boss.max_hp * 0.49
        run(world, WINDUP + 0.05)
        p0.hero.x, p0.hero.y = boss.x + 500, boss.y
        p0.hero.hp = p0.hero.max_hp
        run(world, 1.6)                                           # two pulses (0.5 s, 1.5 s) go by
        p0.hero.x = boss.x + 100
        run(world, 2.0)
        self.assertAlmostEqual(p0.hero.max_hp - p0.hero.hp, 100, delta=0.01)

    def test_monsters_are_not_hurt_by_the_breath(self):
        world, p0, p1, boss = room()
        breathe(world, boss)
        hp = boss.hp
        run(world, 3.4)
        self.assertEqual(boss.hp, hp)

    def test_damage_scales_with_pp_like_all_monster_damage(self):
        world, p0, p1, boss = room()
        world.pp = 3                                              # damage x (1+3)/2
        breathe(world, boss)
        self.assertEqual(world.hazards[0].pulse_damage, 200)

    def test_zone_goes_away_when_the_boss_dies(self):
        world, p0, p1, boss = room()
        breathe(world, boss)
        boss.hp = 0
        boss.alive = False
        run(world, 0.1)
        self.assertEqual(world.hazards, [])

    def test_a_hero_killed_by_the_zone_respawns_and_the_game_goes_on(self):
        world, p0, p1, boss = room()
        boss.hp = boss.max_hp * 0.49
        run(world, WINDUP + 0.05)
        p1.hero.x, p1.hero.y = boss.x + 100, boss.y
        p1.hero.max_hp = 150
        p1.hero.hp = 150
        run(world, 3.0)
        self.assertGreaterEqual(p1.hero.deaths, 1)
        self.assertTrue(p1.hero.alive)

    def test_a_number_floats_over_the_hero_for_each_pulse(self):
        world, p0, p1, boss = room()
        breathe(world, boss)
        p0.hero.x, p0.hero.y = boss.x + 100, boss.y
        world.events.clear()
        run(world, 3.4)
        numbers = [e.text for e in world.events if isinstance(e, FloatText) and e.text.startswith("-")]
        self.assertEqual(numbers, ["-100", "-100", "-100"])


class ClientTest(unittest.TestCase):
    def test_snapshot_carries_the_zone_as_json_and_the_view_reads_it(self):
        world, p0, _, boss = room()
        breathe(world, boss)
        run(world, 0.4)
        snap = make_snapshot(world, 0)
        json.dumps(snap)
        self.assertEqual(len(snap["hazards"]), 1)
        h = snap["hazards"][0]
        self.assertEqual((h["kind"], h["radius"], h["duration"], h["cycles"]), ("deep_breath", 200, 3.0, 3))
        self.assertTrue(0 < h["elapsed"] < 3.0)
        view = ClientView()
        view.apply(snap)
        self.assertEqual(view.hazards[0].radius, 200)

    def test_an_old_snapshot_without_hazards_still_loads(self):
        world, _, _, _ = room()
        snap = make_snapshot(world, 0)
        del snap["hazards"]
        view = ClientView()
        view.apply(snap)
        self.assertEqual(view.hazards, [])


if __name__ == "__main__":
    unittest.main()
