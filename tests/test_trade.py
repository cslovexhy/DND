"""Trading between players (engine/trade.py) and the player autopilot picking up nearby food."""
import random
import tempfile
import unittest

from game import saves
from game.engine import commands as C
from game.engine.bootstrap import create_world, join_player
from game.engine.snapshot import make_snapshot
from game.engine.trade import TOO_FAR

MAP = "data/maps/northshire.json"
DT = 1 / 30
saves.SAVE_DIR = tempfile.mkdtemp()


def two_players(near=True):
    random.seed(1)
    a_char = saves.blank_character("ann", "Fighter", level=5)
    a_char["inventory"] = [{"slot": 0, "item": "health_potion", "count": 3}, {"slot": 1, "item": "bread", "count": 5}]
    w, a = create_world(MAP, a_char)
    w.game_state.monsters.clear()
    b_char = saves.blank_character("bob", "Wizard", level=5)
    b_char["inventory"] = [{"slot": 0, "item": "sushi_plate", "count": 2}]
    b = join_player(w, 1, b_char, MAP)
    b.hero.x, b.hero.y = a.hero.x + (60 if near else 600), a.hero.y
    return w, a, b


def do(w, cmd, pid):
    w.submit(cmd, pid)
    w.step(DT)


class TradeTest(unittest.TestCase):
    def test_open_shows_the_window_on_both_sides(self):
        w, a, b = two_players()
        do(w, C.TradeOpen(b.hero.eid), 0)
        sa, sb = make_snapshot(w, 0)["you"]["trade"], make_snapshot(w, 1)["you"]["trade"]
        self.assertEqual((sa["partner_name"], sb["partner_name"]), ("Bob", "Ann"))

    def test_dragging_offers_one_item_not_the_stack(self):
        w, a, b = two_players()
        do(w, C.TradeOpen(b.hero.eid), 0)
        do(w, C.TradeOffer(1), 0)                     # bread x5 in slot 1 -> offer 1
        self.assertEqual(make_snapshot(w, 0)["you"]["trade"]["mine"], [{"item": "bread", "count": 1}])
        do(w, C.TradeOffer(1), 0)
        self.assertEqual(make_snapshot(w, 1)["you"]["trade"]["theirs"], [{"item": "bread", "count": 2}])
        do(w, C.TradeTake("bread"), 0)
        self.assertEqual(make_snapshot(w, 0)["you"]["trade"]["mine"], [{"item": "bread", "count": 1}])
        for _ in range(9):
            do(w, C.TradeOffer(1), 0)                 # can't offer more than you have
        self.assertEqual(make_snapshot(w, 0)["you"]["trade"]["mine"], [{"item": "bread", "count": 5}])

    def test_both_accept_swaps_the_items(self):
        w, a, b = two_players()
        do(w, C.TradeOpen(b.hero.eid), 0)
        do(w, C.TradeOffer(1), 0)
        do(w, C.TradeOffer(1), 0)                     # 2 bread from ann
        do(w, C.TradeOffer(0), 1)                     # 1 sushi from bob
        do(w, C.TradeAccept(), 0)
        self.assertEqual(a.inventory.count("bread"), 5)              # nothing yet: bob hasn't accepted
        do(w, C.TradeAccept(), 1)
        self.assertEqual((a.inventory.count("bread"), a.inventory.count("sushi_plate")), (3, 1))
        self.assertEqual((b.inventory.count("bread"), b.inventory.count("sushi_plate")), (2, 1))
        self.assertIsNone(make_snapshot(w, 0)["you"]["trade"])        # closed for both
        self.assertIsNone(make_snapshot(w, 1)["you"]["trade"])

    def test_changing_an_offer_clears_both_accepts(self):
        w, a, b = two_players()
        do(w, C.TradeOpen(b.hero.eid), 0)
        do(w, C.TradeOffer(1), 0)
        do(w, C.TradeAccept(), 1)
        do(w, C.TradeOffer(1), 0)                     # ann changes her offer
        self.assertFalse(make_snapshot(w, 1)["you"]["trade"]["my_accept"])
        do(w, C.TradeAccept(), 0)
        self.assertEqual(a.inventory.count("bread"), 5)              # bob has to accept again

    def test_too_far_says_get_closer_and_nothing_moves(self):
        w, a, b = two_players(near=False)
        do(w, C.TradeOpen(b.hero.eid), 0)
        do(w, C.TradeOffer(1), 0)
        do(w, C.TradeAccept(), 0)
        do(w, C.TradeAccept(), 1)
        self.assertEqual(a.inventory.count("bread"), 5)
        view = make_snapshot(w, 0)["you"]["trade"]
        self.assertEqual(view["message"], TOO_FAR)
        self.assertEqual(TOO_FAR, "Need to be closer to complete trade")
        self.assertFalse(view["my_accept"] or view["their_accept"])
        b.hero.x = a.hero.x + 100                     # walk closer, accept again: works
        do(w, C.TradeAccept(), 0)
        do(w, C.TradeAccept(), 1)
        self.assertEqual(b.inventory.count("bread"), 1)

    def test_cancel_closes_it_for_both(self):
        w, a, b = two_players()
        do(w, C.TradeOpen(b.hero.eid), 0)
        do(w, C.TradeCancel(), 1)
        self.assertIsNone(make_snapshot(w, 0)["you"]["trade"])

    def test_leaving_cancels(self):
        w, a, b = two_players()
        do(w, C.TradeOpen(b.hero.eid), 0)
        w.remove_player(1)
        self.assertIsNone(w.trade_of(a))

    def test_no_trading_with_companions_or_yourself(self):
        w, a, b = two_players()
        do(w, C.ToggleCompanion("Cleric"), 0)
        comp = w.companions[0]
        do(w, C.TradeOpen(comp.hero.eid), 0)
        do(w, C.TradeOpen(a.hero.eid), 0)
        self.assertIsNone(w.trade_of(a))

    def test_trade_commands_round_trip(self):
        for cmd in (C.TradeOpen(3), C.TradeOffer(4), C.TradeTake("bread"), C.TradeAccept(), C.TradeCancel()):
            self.assertEqual(C.from_dict(C.to_dict(cmd)), cmd)


class AutopilotFoodTest(unittest.TestCase):
    def setup(self, offset):
        random.seed(1)
        w, p = create_world(MAP, saves.blank_character("t", "Fighter", level=5), autopilot=True)
        w.game_state.monsters.clear()
        g = w.drop_item("bread", p.hero.x + offset, p.hero.y)
        return w, p, g

    def test_picks_up_food_within_200(self):
        w, p, g = self.setup(150)
        for _ in range(30 * 5):
            w.step(DT)
            if not w.ground_items:
                break
        self.assertEqual(p.inventory.count("bread"), 1)

    def test_ignores_food_further_than_200(self):
        w, p, g = self.setup(260)
        for _ in range(30 * 3):
            w.step(DT)
        self.assertIn(g, w.ground_items)

    def test_companions_do_not_pick_up_food(self):
        w, p, g = self.setup(150)
        p.ai_enabled = False                           # the player isn't on autopilot
        w.submit(C.ToggleCompanion("Cleric"), 0)
        w.step(DT)
        comp = w.companions[0]
        comp.hero.x, comp.hero.y = g.x - 20, g.y
        for _ in range(30 * 3):
            w.step(DT)
        self.assertIn(g, w.ground_items)


if __name__ == "__main__":
    unittest.main()
