"""Cleric / Paladin autopilot: heal the lowest-HP% party member once below 70%, before anything else."""
import unittest

from game import saves
from game.engine.ai import aggro_monster
from game.engine.bootstrap import create_world, join_player

MAP = "data/maps/bossTestRoom.json"
DT = 1 / 30


def party(healer_class, *others):
    """A healer (player 0) and `others` standing together, with an aggroed boss further away (so the healer has a
    target to fight)."""
    world, p0 = create_world(MAP, saves.blank_character("healer", healer_class, level=30), autopilot=True)
    players = [p0] + [join_player(world, i + 1, saves.blank_character(f"m{i}", cls, level=30), MAP, autopilot=True)
                      for i, cls in enumerate(others)]
    gs = world.game_state
    boss = next(m for m in gs.monsters if m.is_boss)
    gs.monsters[:] = [boss]
    for p in players:
        p.hero.x, p.hero.y = p0.hero.x, p0.hero.y
        p.hero.hp = p.hero.max_hp
    aggro_monster(boss, p0.hero, [boss])
    return world, players, boss


def decide(world, player, boss):
    """What this player's autopilot would do right now (no world step, so nothing else acts first)."""
    return player.hero_ai.update([boss], DT, world.is_wall)


class ClericHealsFirstTest(unittest.TestCase):
    def setUp(self):
        self.world, (self.cleric, self.fighter, self.rogue), self.boss = party("Cleric", "Fighter", "Rogue")

    def set_pct(self, p, pct):
        p.hero.hp = p.hero.max_hp * pct

    def test_heals_the_lowest_percentage_not_the_lowest_absolute_hp(self):
        self.set_pct(self.fighter, 0.60)     # more absolute HP missing...
        self.set_pct(self.rogue, 0.40)       # ...but this one is the lowest percentage
        a = decide(self.world, self.cleric, self.boss)
        self.assertEqual(a["use_ability"], "R")                       # Wall first
        self.assertIs(a["ability_target_ally"], self.rogue.hero)

    def test_renew_when_wall_is_unavailable_or_target_already_shielded(self):
        self.set_pct(self.fighter, 0.50)
        self.fighter.hero.absorb_shield = 100
        a = decide(self.world, self.cleric, self.boss)
        self.assertEqual(a["use_ability"], "E")
        self.assertIs(a["ability_target_ally"], self.fighter.hero)
        self.fighter.hero.buffs["Renew"] = {"remaining": 5.0, "hot_per_sec": 10.0}
        a = decide(self.world, self.cleric, self.boss)
        self.assertNotIn(a["use_ability"], ("R", "E"))                # nothing left to cast on them: back to fighting

    def test_includes_self(self):
        self.set_pct(self.cleric, 0.30)
        a = decide(self.world, self.cleric, self.boss)
        self.assertEqual(a["use_ability"], "R")
        self.assertIs(a["ability_target_ally"], self.cleric.hero)

    def test_no_heal_at_or_above_70_percent(self):
        for pct in (0.70, 0.75, 1.0):
            self.set_pct(self.fighter, pct)
            a = decide(self.world, self.cleric, self.boss)
            self.assertNotIn(a["use_ability"], ("R", "E"), pct)

    def test_heal_beats_attacking(self):
        self.set_pct(self.fighter, 0.69)
        a = decide(self.world, self.cleric, self.boss)
        self.assertEqual(a["use_ability"], "R")                       # not "Q" (Wanding)


class PaladinHealsFirstTest(unittest.TestCase):
    def setUp(self):
        self.world, (self.paladin, self.wizard, self.fighter), self.boss = party("Paladin", "Wizard", "Fighter")

    def test_holy_light_on_the_lowest_percentage_below_70(self):
        self.wizard.hero.hp = self.wizard.hero.max_hp * 0.65
        self.fighter.hero.hp = self.fighter.hero.max_hp * 0.55
        a = decide(self.world, self.paladin, self.boss)
        self.assertEqual(a["use_ability"], "F")
        self.assertIs(a["ability_target_ally"], self.fighter.hero)

    def test_no_holy_light_at_or_above_70_percent(self):
        for pct in (0.70, 0.9):
            self.wizard.hero.hp = self.wizard.hero.max_hp * pct
            a = decide(self.world, self.paladin, self.boss)
            self.assertNotEqual(a["use_ability"], "F", pct)

    def test_paladin_heals_itself_too(self):
        self.paladin.hero.hp = self.paladin.hero.max_hp * 0.5
        a = decide(self.world, self.paladin, self.boss)
        self.assertEqual(a["use_ability"], "F")
        self.assertIs(a["ability_target_ally"], self.paladin.hero)

    def test_holy_light_waits_for_cooldown_then_attacks(self):
        self.wizard.hero.hp = self.wizard.hero.max_hp * 0.4
        self.paladin.hero.abilities["F"].remaining = 5.0
        a = decide(self.world, self.paladin, self.boss)
        self.assertNotEqual(a["use_ability"], "F")


if __name__ == "__main__":
    unittest.main()
