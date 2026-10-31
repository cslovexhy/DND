"""Home-network co-op: finding games (subnet scan + info), what the host listens on, who gets player 0."""
import ipaddress
import os
import socket
import subprocess
import sys
import unittest

from game import saves
from game.net import discovery
from game.net.client import RemoteHost
from game.net.server import HostServer

MAP = "data/maps/northshire.json"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def host(**kw):
    char = kw.pop("character", saves.blank_character("quinn", "Cleric"))
    return HostServer(MAP, port=0, tick_rate=60, host_character=char, **kw).start()


class DiscoveryTest(unittest.TestCase):
    def test_describe_uses_the_agreed_format(self):
        g = {"host_name": "Quinn", "host_level": 7, "map_name": "Northshire", "pp": 8, "players": 2,
             "max_players": 4, "address": "192.168.1.23"}
        self.assertEqual(discovery.describe(g), "Quinn (Lv 7) - Northshire (8pp) (LAN 192.168.1.23) · 2/4 players")
        g["address"] = "127.0.0.1"
        self.assertIn("(this computer)", discovery.describe(g))

    def test_lan_address_is_private_or_none(self):
        ip = discovery.lan_address()
        if ip is not None:
            a = ipaddress.IPv4Address(ip)
            self.assertTrue(a.is_private and not a.is_loopback)

    def test_scan_finds_a_host_and_reports_its_game(self):
        srv = host(pp=8)
        try:
            a = RemoteHost("127.0.0.1", srv.port)              # host's own client
            games = discovery.scan(srv.port, prefix="127.0.0")  # scan the loopback block like a /24
            self.assertEqual(len(games), 1)
            g = games[0]
            self.assertEqual((g["host_name"], g["map_name"], g["pp"], g["players"], g["max_players"]),
                             ("Quinn", "Northshire", 8, 1, 4))
            self.assertTrue(g["compatible"])
            self.assertEqual(discovery.describe(g), "Quinn (Lv 1) - Northshire (8pp) (this computer) · 1/4 players")
            a.close()
        finally:
            srv.stop()

    def test_scan_ignores_things_that_are_not_our_game(self):
        with socket.socket() as other:                          # some unrelated service on the port
            other.bind(("127.0.0.1", 0))
            other.listen()
            port = other.getsockname()[1]
            self.assertEqual(discovery.scan(port, prefix="127.0.0", timeout=0.2), [])

    def test_info_does_not_join(self):
        srv = host()
        try:
            self.assertIsNotNone(discovery.probe("127.0.0.1", srv.port))
            self.assertEqual(len(srv.world.players), 1)
            self.assertEqual(srv.info()["players"], 0)
        finally:
            srv.stop()


class ListeningTest(unittest.TestCase):
    def test_this_computer_mode_is_loopback(self):
        srv = HostServer(MAP, port=0)
        self.assertEqual(srv.listener.getsockname()[0], "127.0.0.1")
        srv.listener.close()

    def test_home_network_mode_binds_one_private_address_never_all_interfaces(self):
        ip = discovery.lan_address()
        if ip is None:
            self.skipTest("this machine has no home-network address")
        srv = HostServer(MAP, port=0, lan=True)     # not started: just check the bind, then close
        try:
            bound = srv.listener.getsockname()[0]
            self.assertEqual(bound, ip)
            self.assertNotIn(bound, ("0.0.0.0", ""))
            self.assertTrue(ipaddress.IPv4Address(bound).is_private)
        finally:
            srv.listener.close()

    def test_only_this_machine_can_take_the_hosts_hero(self):
        srv = host()
        srv.local_addresses = {"10.255.255.254"}   # pretend every connection comes from another machine
        try:
            a = RemoteHost("127.0.0.1", srv.port)
            self.assertEqual(a.welcome["player_id"], 1)   # a stranger never gets player 0 (your hero)
            a.close()
        finally:
            srv.stop()

    def test_player_limit_still_applies(self):
        from game.net.client import ConnectionRejected
        srv = host()
        try:
            clients = [RemoteHost("127.0.0.1", srv.port) for _ in range(4)]
            with self.assertRaises(ConnectionRejected):
                RemoteHost("127.0.0.1", srv.port, timeout=3)
            for c in clients:
                c.close()
        finally:
            srv.stop()


class RealHomeNetworkTest(unittest.TestCase):
    def test_host_on_lan_then_find_and_join_over_the_lan_address(self):
        ip = discovery.lan_address()
        if ip is None:
            self.skipTest("this machine has no home-network address")
        srv = host(lan=True, pp=3)
        try:
            me = RemoteHost(ip, srv.port)                         # the host's own client, via the LAN address
            self.assertEqual(me.welcome["player_id"], 0)          # from this machine -> its own hero
            games = discovery.scan(srv.port, prefix=ip.rsplit(".", 1)[0], include_local=False)
            mine = [g for g in games if g["address"] == ip]
            self.assertEqual(len(mine), 1, games)
            self.assertEqual(discovery.describe(mine[0]),
                             f"Quinn (Lv 1) - Northshire (3pp) (LAN {ip}) · 1/4 players")
            kid = RemoteHost(ip, srv.port, class_name="Rogue")
            self.assertEqual(kid.welcome["player_id"], 1)
            kid.close()
            me.close()
            with self.assertRaises(OSError):                      # not on loopback: home-network address only
                socket.create_connection(("127.0.0.1", srv.port), timeout=1).close()
        finally:
            srv.stop()


class JoinScreenTest(unittest.TestCase):
    SCRIPT = r"""
import os, json
os.environ["SDL_VIDEODRIVER"] = "dummy"; os.environ["SDL_AUDIODRIVER"] = "dummy"
import pygame
pygame.init(); pygame.display.set_mode((1024, 718))
import game.net.discovery as d
d.scan = lambda port, **kw: [
    {"host_name": "Dad", "host_level": 9, "map_name": "Northshire", "pp": 8, "players": 1, "max_players": 4,
     "address": "192.168.1.23", "compatible": True},
    {"host_name": "Old", "host_level": 1, "map_name": "Haycock", "pp": 1, "players": 1, "max_players": 4,
     "address": "192.168.1.40", "compatible": False}]
from game.menus import MenuContext, join_select
ctx = MenuContext(clock=pygame.time.Clock(), font=pygame.font.Font(None, 20), big_font=pygame.font.Font(None, 32),
                  title_font=pygame.font.Font(None, 48), hero_sprites={})
import time
def keys(*ks):
    for k in ks:
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=getattr(pygame, "K_" + k), unicode=k if len(k) == 1 else ""))
out = {}
real_flip = pygame.display.flip
plan = []
def flip():
    real_flip()
    if plan:
        plan.pop(0)()
pygame.display.flip = flip
# 1) pick the first found game
plan[:] = [lambda: time.sleep(0.2), lambda: keys("RETURN")]
out["found"] = join_select(ctx, port=1)
# 2) type an address by hand
plan[:] = [lambda: time.sleep(0.2), lambda: keys("t"),
           lambda: [pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=0, unicode=c)) for c in "10.0.0.7"],
           lambda: keys("RETURN")]
out["typed"] = join_select(ctx, port=1)
# 3) incompatible game can't be joined; ESC goes back
plan[:] = [lambda: time.sleep(0.2), lambda: keys("DOWN", "RETURN"), lambda: keys("ESCAPE")]
out["incompatible"] = join_select(ctx, port=1)
print(json.dumps(out))
"""

    def test_join_screen(self):
        import json
        p = subprocess.run([sys.executable, "-c", self.SCRIPT], cwd=ROOT, capture_output=True, text=True, timeout=60)
        self.assertEqual(p.returncode, 0, p.stderr[-1500:])
        out = json.loads(p.stdout.strip().splitlines()[-1])
        self.assertEqual(out["found"], {"join": True, "address": "192.168.1.23"})
        self.assertEqual(out["typed"], {"join": True, "address": "10.0.0.7"})
        self.assertIsNone(out["incompatible"])


class EndToEndByAddressTest(unittest.TestCase):
    def test_join_by_address(self):
        srv = host()
        try:
            p = subprocess.run([sys.executable, "-m", "game.main", "--headless", "--connect",
                                f"127.0.0.1:{srv.port}", "--max-time", "2"],
                               cwd=ROOT, capture_output=True, text=True, timeout=60)
            out = p.stdout + p.stderr
            self.assertEqual(p.returncode, 0, out[-1500:])
            self.assertIn("client=remote", out)
        finally:
            srv.stop()


if __name__ == "__main__":
    unittest.main()
