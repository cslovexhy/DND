"""Run with: .venv/bin/python -m unittest discover -s tests -t ."""
import json
import os
import tempfile
import unittest

from game import saves
from game.content.heroes import HERO_CLASSES
from game.progression import set_hero_level, growth_for, hero_max_hp, MAX_LEVEL, HERO_HP
from game.quests import load_quest_log
from tests import item_ids as I


class SavesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_name_validation(self):
        for bad in ["", "Bob", "bob1", "bob smith", "a" * 13, "con", "bob-x"]:
            self.assertIsNotNone(saves.validate_name(bad, self.d), bad)
        for good in ["bob", "a", "a" * 12]:
            self.assertIsNone(saves.validate_name(good, self.d), good)

    def test_create_duplicate_and_delete(self):
        data, err = saves.create_character("bob", "Rogue", self.d)
        self.assertIsNone(err)
        self.assertTrue(os.path.exists(os.path.join(self.d, "bob.json")))
        _, err = saves.create_character("bob", "Wizard", self.d)
        self.assertIn("exists", err)
        self.assertEqual([c["name"] for c in saves.list_characters(self.d)], ["bob"])
        self.assertTrue(saves.delete_character("bob", self.d))
        self.assertFalse(saves.delete_character("bob", self.d))
        self.assertEqual(saves.list_characters(self.d), [])

    def test_legacy_migration_preserves_progress(self):
        legacy = {"name": "Heskan", "class_name": "Wizard", "level": 16, "xp": 367, "gold": 5, "kills": 7,
                  "completed_quests": ["a_threat_within"], "active_quests": ["kobold_camp_cleanup"]}
        with open(os.path.join(self.d, "heskan.json"), "w") as f:
            json.dump(legacy, f)
        (c,) = saves.list_characters(self.d)
        self.assertEqual(c["name"], "heskan")
        self.assertEqual((c["level"], c["xp"], c["gold"], c["kills"]), (16, 367, 5, 7))
        self.assertEqual(c["quests"]["completed"], ["a_threat_within"])
        self.assertEqual(c["quests"]["active"], ["kobold_camp_cleanup"])
        self.assertNotIn("completed_quests", c)
        # the file on disk was rewritten in the new format
        with open(os.path.join(self.d, "heskan.json")) as f:
            self.assertIn("quests", json.load(f))


class QuestTest(unittest.TestCase):
    def test_northshire_chain_and_state_roundtrip(self):
        log = load_quest_log("northshire")
        self.assertEqual(len(log.quests), 8)
        self.assertEqual(log.available_for_npc("deputy_willem", 1), ["a_threat_within"])
        self.assertTrue(log.accept("a_threat_within"))  # no objectives -> auto turn-in
        self.assertEqual(log.available_for_npc("marshal_mcbride", 1), ["kobold_camp_cleanup"])
        self.assertFalse(log.accept("kobold_camp_cleanup"))
        for _ in range(4):
            log.record_kill(1)
        state = json.loads(json.dumps(log.to_state()))
        self.assertEqual(state["progress"]["kobold_camp_cleanup"], {"1": 4})

        fresh = load_quest_log("northshire")
        fresh.load_state(state)
        self.assertEqual(fresh.active, ["kobold_camp_cleanup"])
        self.assertEqual(fresh.quests["kobold_camp_cleanup"].progress[1], 4)
        for _ in range(6):
            fresh.record_kill(1)
        self.assertEqual(fresh.turn_ins_for_npc("marshal_mcbride"), ["kobold_camp_cleanup"])

    def test_progress_is_per_log_and_quests_belong_to_no_map(self):
        a, b = load_quest_log("northshire"), load_quest_log("northshire")
        a.accept("a_threat_within")
        self.assertEqual(b.completed, [])
        self.assertEqual(list(load_quest_log("goldshire").quests), list(a.quests))     # same quests on every map

    def test_quests_are_listed_in_dependency_order(self):
        log = load_quest_log()
        seen = set()
        for qid, q in log.quests.items():
            self.assertTrue(set(q.prerequisites) <= seen, qid)
            seen.add(qid)

    def test_legacy_per_map_saves_are_merged(self):
        from game.quests import normalize_state
        old = {"northshire": {"completed": ["a_threat_within"], "active": ["kobold_camp_cleanup"],
                              "progress": {"kobold_camp_cleanup": {"1": 3}}}, "goldshire": {"completed": ["x"]}}
        new = normalize_state(old)
        self.assertEqual((new["completed"], new["active"]), (["a_threat_within", "x"], ["kobold_camp_cleanup"]))
        self.assertEqual(normalize_state(new), new)                                        # already current
        log = load_quest_log()
        log.load_state(old)
        self.assertEqual((log.completed, log.active), (["a_threat_within"], ["kobold_camp_cleanup"]))

    def test_old_saves_keyed_by_monster_name_still_load(self):
        log = load_quest_log("northshire")
        log.load_state({"active": ["kobold_camp_cleanup"],
                        "progress": {"kobold_camp_cleanup": {"Kobold Dragonshield": 2}}})
        self.assertEqual(log.quests["kobold_camp_cleanup"].progress, {1: 2})

    def test_garrick_bounty_requires_killing_garrick(self):
        log = load_quest_log("northshire")
        log.load_state({"completed": ["a_threat_within", "brotherhood_of_thieves"]})
        self.assertFalse(log.accept("bounty_on_garrick_padfoot"))
        for _ in range(20):
            log.record_kill(9)
        self.assertEqual(log.turn_ins_for_npc("deputy_willem"), [])
        log.record_kill(22)
        self.assertEqual(log.turn_ins_for_npc("deputy_willem"), ["bounty_on_garrick_padfoot"])

    def test_level_requirement(self):
        log = load_quest_log("northshire")
        log.load_state({"completed": ["a_threat_within", "kobold_camp_cleanup"]})
        self.assertEqual(log.available_for_npc("marshal_mcbride", 2), [])
        self.assertEqual(log.available_for_npc("marshal_mcbride", 3), ["investigate_echo_ridge"])


def three_npc_log():
    from game.engine.inventory import Inventory
    from game.quests import Quest, QuestLog
    quests = [Quest("fetch", "Fetch", "", [{"item": I.BREAD, "count": 2}, {"monster": 1, "count": 1}], 100, 5,
                    giver="a", turn_in="b", reward_npc="c"),
              Quest("after", "After", "", [], 10, 0, giver="a", prerequisites=["fetch"]),
              Quest("hello", "Hello", "", [], 7, 0, giver="a", turn_in="b")]
    inv = Inventory.from_state([])
    return QuestLog(quests, inv), inv


class ThreeNpcQuestTest(unittest.TestCase):
    def test_given_by_a_handed_in_to_b_paid_by_c(self):
        log, inv = three_npc_log()
        self.assertEqual(log.available_for_npc("a", 1), ["fetch", "hello"])                # "after" waits for "fetch"
        self.assertFalse(log.accept("fetch"))
        log.record_kill(1)
        self.assertEqual(log.turn_ins_for_npc("b"), [])                                     # items still missing
        inv.add(I.BREAD)
        inv.add(I.BREAD)
        self.assertTrue(log.quests["fetch"].get_progress_text().startswith("Bread: 2/2"))
        self.assertEqual((log.turn_ins_for_npc("a"), log.turn_ins_for_npc("b")), ([], ["fetch"]))
        q, paid = log.hand_in("fetch")
        self.assertFalse(paid)                                                              # B only takes the items
        self.assertEqual(inv.count(I.BREAD), 0)
        self.assertEqual((log.turn_ins_for_npc("b"), log.rewards_for_npc("a"), log.rewards_for_npc("c")),
                         ([], [], ["fetch"]))
        self.assertEqual(log.available_for_npc("a", 1), ["hello"])                          # not done until C pays
        self.assertEqual(log.to_state()["delivered"], ["fetch"])
        fresh, _ = three_npc_log()
        fresh.load_state(json.loads(json.dumps(log.to_state())))
        self.assertEqual(fresh.rewards_for_npc("c"), ["fetch"])
        log.turn_in("fetch")
        self.assertEqual(log.available_for_npc("a", 1), ["hello", "after"])

    def test_a_to_b_delivery_has_no_objectives_but_is_not_instant(self):
        log, _ = three_npc_log()
        self.assertFalse(log.accept("hello"))
        self.assertEqual(log.turn_ins_for_npc("b"), ["hello"])
        q, paid = log.hand_in("hello")
        self.assertTrue(paid)                                                               # B takes it and pays
        self.assertIn("hello", log.completed)


class ProgressionTest(unittest.TestCase):
    def test_set_hero_level_matches_incremental_growth(self):
        for cls in HERO_CLASSES:
            base = cls["create"]("x", 0, 0)
            hp0, dmg0 = base.max_hp, base.base_damage
            leveled = cls["create"]("y", 0, 0)
            set_hero_level(leveled, 10)
            g = growth_for(cls["class"])
            self.assertEqual(leveled.level, 10)
            self.assertEqual(hp0, hero_max_hp(cls["class"], 1))
            self.assertEqual(leveled.max_hp, hero_max_hp(cls["class"], 10))
            self.assertAlmostEqual(leveled.base_damage, dmg0 + 9 * g["damage"])
            self.assertEqual(leveled.hp, leveled.max_hp)

    def test_hero_hp_line(self):
        self.assertEqual(hero_max_hp("Wizard", 1), 100)
        self.assertEqual(hero_max_hp("Fighter", 1), 120)
        self.assertEqual(hero_max_hp("Fighter", MAX_LEVEL), 1270)
        for cls, (lo, hi) in HERO_HP.items():
            hps = [hero_max_hp(cls, lv) for lv in range(1, MAX_LEVEL + 1)]
            self.assertEqual((hps[0], hps[-1]), (lo, hi))
            self.assertEqual(hps, sorted(hps))
        h = HERO_CLASSES[0]["create"]("x", 0, 0)
        set_hero_level(h, 1)
        h.level = 2                                    # a level-up in the World: level first, then growth
        from game.progression import apply_level_growth
        apply_level_growth(h)
        self.assertEqual(h.max_hp, hero_max_hp("Fighter", 2))

    def test_level_clamped(self):
        h = HERO_CLASSES[0]["create"]("x", 0, 0)
        set_hero_level(h, 999)
        self.assertEqual(h.level, MAX_LEVEL)


if __name__ == "__main__":
    unittest.main()
