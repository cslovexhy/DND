"""Status-effect visuals (Renew, Wall shield, poison, chill, stealth, channel bar) must look the same on every
player's screen: whoever looks at a hero sees the same effects (eventually — one snapshot later is fine)."""
import random
import time
import unittest

from game import saves
from game.client.status_visuals import status_visuals
from game.client.view import ClientView
from game.engine import commands as C
from game.engine.bootstrap import create_world, join_player
from game.engine.entities import Condition
from game.engine.snapshot import make_snapshot

MAP = "data/maps/northshire.json"
DT = 1 / 30


def views_of(world):
    """Each player's ClientView, built from their own snapshot."""
    out = {}
    for pid in world.players:
        v = ClientView()
        v.apply(make_snapshot(world, pid))
        out[pid] = v
    return out


class StatusVisualsTest(unittest.TestCase):
    def setUp(self):
        random.seed(1)
        self.world, self.cleric = create_world(MAP, saves.blank_character("cleric", "Cleric"))
        self.ally = join_player(self.world, 1, saves.blank_character("ally", "Wizard"), MAP)
        self.world.game_state.monsters.clear()
        self.ally.hero.x, self.ally.hero.y = self.cleric.hero.x + 60, self.cleric.hero.y

    def assert_same_on_every_screen(self, hero_eid, expected):
        views = views_of(self.world)
        seen = {pid: status_visuals(v.entities[hero_eid]) for pid, v in views.items()}
        for pid, fx in seen.items():
            self.assertTrue(expected <= set(fx), f"player {pid} sees {fx}, expected {expected}")
        self.assertEqual(len({frozenset(fx) for fx in seen.values()}), 1, f"screens disagree: {seen}")

    def test_renew_on_ally_visible_to_caster_and_ally(self):
        self.world.submit(C.Cast("E", self.ally.hero.x, self.ally.hero.y, None, ally_id=self.ally.hero.eid), 0)
        self.world.step(DT)
        self.assert_same_on_every_screen(self.ally.hero.eid, {"renew"})

    def test_wall_shield_on_ally_visible_everywhere(self):
        self.world.submit(C.Cast("R", self.ally.hero.x, self.ally.hero.y, None, ally_id=self.ally.hero.eid), 0)
        self.world.step(DT)
        self.assert_same_on_every_screen(self.ally.hero.eid, {"shield"})

    def test_poison_and_chill_visible_everywhere(self):
        h = self.ally.hero
        h.apply_condition(Condition.POISONED, 3.0, tick_damage=1.0)
        h.chill_visual = 0.3
        self.assert_same_on_every_screen(h.eid, {"poison", "chill"})

    def test_channel_bar_visible_to_others(self):
        self.world.spawn_world_map_monsters()
        wiz = self.ally
        m = min(self.world.game_state.monsters, key=lambda m: wiz.hero.distance_to(m))
        wiz.hero.x, wiz.hero.y = m.x - 150, m.y
        if not self.world.check_los(wiz.hero.x, wiz.hero.y, m.x, m.y):
            self.skipTest("no line of sight in this spot")
        self.world.submit(C.Cast("Q", m.x, m.y, m.eid), 1)    # Frostbolt: channelled
        self.world.step(DT)
        self.assertTrue(wiz.frostbolt_channeling)
        self.assert_same_on_every_screen(wiz.hero.eid, {"channel"})

    def test_companion_effects_visible(self):
        self.world.submit(C.ToggleCompanion("Fighter"), 0)
        self.world.step(DT)
        comp = self.world.companions[-1][0]
        comp.x, comp.y = self.cleric.hero.x + 40, self.cleric.hero.y
        self.world.submit(C.Cast("E", comp.x, comp.y, None, ally_id=comp.eid), 0)
        self.world.step(DT)
        self.assert_same_on_every_screen(comp.eid, {"renew"})


class OverTheNetworkTest(unittest.TestCase):
    def test_both_remote_screens_converge(self):
        from game.net.client import RemoteHost
        from game.net.server import HostServer
        srv = HostServer(MAP, "Cleric", seed=1, port=0, tick_rate=60).start()
        try:
            a = RemoteHost("127.0.0.1", srv.port, class_name="Cleric")
            b = RemoteHost("127.0.0.1", srv.port, class_name="Fighter")
            va, vb = ClientView(), ClientView()
            va.apply(a.snapshot())
            vb.apply(b.snapshot())
            ally_id = vb.hero.eid
            # put them next to each other, then the cleric renews the fighter
            srv.world.players[1].hero.x = srv.world.players[0].hero.x + 50
            srv.world.players[1].hero.y = srv.world.players[0].hero.y
            time.sleep(0.1)
            a.send(C.Cast("E", 0, 0, None, ally_id=ally_id))
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                for h, v in ((a, va), (b, vb)):
                    snap, _ = h.step()
                    if snap:
                        v.apply(snap)
                if ally_id in va.entities and "renew" in status_visuals(va.entities[ally_id]) \
                        and "renew" in status_visuals(vb.entities[ally_id]):
                    break
                time.sleep(0.01)
            self.assertIn("renew", status_visuals(va.entities[ally_id]), "caster's screen")
            self.assertIn("renew", status_visuals(vb.entities[ally_id]), "ally's own screen")
            a.close()
            b.close()
        finally:
            srv.stop()


if __name__ == "__main__":
    unittest.main()
