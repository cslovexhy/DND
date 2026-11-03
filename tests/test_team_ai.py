"""Party AI: heroes share one pool of engaged mobs and focus the weakest; melee heroes in a party do not kite."""
import random
import unittest

from game import saves
from game.engine.ai import AggroState
from game.engine.bootstrap import create_world, join_player

MAP = "data/maps/northshire.json"


def party(classes):
    random.seed(3)
    world, p0 = create_world(MAP, saves.blank_character("p0", classes[0]), autopilot=True)
    players = [p0] + [join_player(world, i, saves.blank_character(f"p{i}", c), MAP, autopilot=True)
                      for i, c in enumerate(classes[1:], start=1)]
    return world, players


def aggro(monsters, hps):
    """Aggro the first len(hps) monsters with the given HP."""
    picked = monsters[:len(hps)]
    for m, hp in zip(picked, hps):
        m.aggro_state = AggroState.AGGROED
        m.hp = hp
    return picked


class TeamTargetTest(unittest.TestCase):
    def test_every_class_focuses_lowest_hp_engaged_mob(self):
        world, players = party(["Fighter", "Wizard", "Cleric", "Rogue", "Paladin"])
        monsters = world.game_state.monsters
        picked = aggro(monsters, [50, 10, 30])
        weakest = picked[1]
        for p in players:
            self.assertIs(p.hero_ai.pick_target(monsters), weakest, p.hero.class_name)

    def test_pull_phase_still_picks_nearest(self):
        world, (p0, p1) = party(["Wizard", "Cleric"])
        monsters = world.game_state.monsters
        self.assertFalse(any(m.aggro_state == AggroState.AGGROED for m in monsters))   # nothing pulled yet
        ai = p0.hero_ai
        nearest = min((m for m in monsters if m.alive), key=lambda m: ai.path_distance(m))
        self.assertIs(ai.pick_target(monsters), nearest)


class MeleeKiteTest(unittest.TestCase):
    def test_melee_in_party_walks_straight_with_several_aggroed(self):
        world, (p0, p1) = party(["Paladin", "Wizard"])
        monsters = world.game_state.monsters
        aggro(monsters, [50, 50, 50])
        ai = p0.hero_ai
        self.assertTrue(ai.in_party())
        self.assertEqual(ai.melee_move_to(monsters, 123.0, 456.0), (123.0, 456.0))

    def test_solo_melee_still_kites_with_several_aggroed(self):
        world, (p0,) = party(["Paladin"])
        monsters = world.game_state.monsters
        ai = p0.hero_ai
        self.assertFalse(ai.in_party())
        near = [m for m in monsters if m.alive][:3]
        for m in near:                                   # all aggroed and right next to the hero
            m.aggro_state = AggroState.AGGROED
            m.x, m.y = p0.hero.x + 40, p0.hero.y
        self.assertNotEqual(ai.melee_move_to(monsters, 123.0, 456.0), (123.0, 456.0))


if __name__ == "__main__":
    unittest.main()
