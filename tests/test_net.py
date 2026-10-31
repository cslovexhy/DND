"""Host <-> client over real TCP on 127.0.0.1 (design/06 phase 4). No pygame."""
import json
import socket
import time
import unittest

from game.engine import commands as C
from game.engine.snapshot import make_snapshot
from game.client.view import ClientView
from game.net.client import RemoteHost, ConnectionRejected
from game.net.protocol import encode, LineBuffer, PROTOCOL_VERSION
from game.net.server import HostServer

MAP = "data/maps/northshire.json"


def wait_until(cond, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if cond():
            return True
        time.sleep(0.01)
    return False


class NetTest(unittest.TestCase):
    def setUp(self):
        self.srv = HostServer(MAP, "Wizard", seed=1, port=0, tick_rate=60).start()

    def tearDown(self):
        self.srv.stop()

    def test_listens_on_loopback_only(self):
        self.assertEqual(self.srv.listener.getsockname()[0], "127.0.0.1")

    def test_snapshots_stream_and_commands_apply(self):
        host = RemoteHost("127.0.0.1", self.srv.port, class_name="Wizard")
        try:
            view = ClientView()
            view.apply(host.snapshot())
            t0 = view.tick
            start = (view.hero.x, view.hero.y)
            host.send(C.MoveTo(start[0] + 120, start[1]))

            def moved():
                snap, _ = host.step()
                if snap:
                    view.apply(snap)
                return view.hero.x > start[0] + 20
            self.assertTrue(wait_until(moved), "hero should walk after a MoveTo command")
            self.assertGreater(view.tick, t0)
            # toggling the autopilot is reflected in the snapshot
            host.send(C.ToggleAutopilot())

            def ai_on():
                snap, _ = host.step()
                if snap:
                    view.apply(snap)
                return view.you.ai_enabled
            self.assertTrue(wait_until(ai_on))
        finally:
            host.close()

    def test_second_client_joins_as_new_player_with_own_character(self):
        a = RemoteHost("127.0.0.1", self.srv.port)
        b = RemoteHost("127.0.0.1", self.srv.port,
                       character={"name": "kid", "class_name": "Rogue", "level": 3, "xp": 10, "gold": 5,
                                  "kills": 1, "quests": {}})
        try:
            self.assertEqual(a.welcome["player_id"], 0)
            self.assertEqual(b.welcome["player_id"], 1)
            va, vb = ClientView(), ClientView()
            va.apply(a.snapshot())
            vb.apply(b.snapshot())

            def both_see_each_other():
                for h, v in ((a, va), (b, vb)):
                    snap, _ = h.step()
                    if snap:
                        v.apply(snap)
                return len(va.allies) == 1 and len(vb.allies) == 1
            self.assertTrue(wait_until(both_see_each_other))
            self.assertEqual(vb.hero.class_name, "Rogue")
            self.assertEqual(vb.hero.level, 3)
            self.assertEqual(va.allies[0].player_name, "kid")
            # b moves; a sees the ally move, a's own hero stays put
            ax = va.hero.x
            bx = vb.hero.x
            b.send(C.MoveTo(bx + 150, vb.hero.y))

            def a_sees_b_move():
                for h, v in ((a, va), (b, vb)):
                    snap, _ = h.step()
                    if snap:
                        v.apply(snap)
                return va.allies and va.allies[0].x > bx + 30
            self.assertTrue(wait_until(a_sees_b_move))
            self.assertEqual(va.hero.x, ax)
        finally:
            b.close()
            a.close()

    def test_joiner_leaving_removes_their_hero(self):
        a = RemoteHost("127.0.0.1", self.srv.port)
        b = RemoteHost("127.0.0.1", self.srv.port, class_name="Cleric")
        va = ClientView()
        va.apply(a.snapshot())
        b.close()

        def ally_gone():
            snap, _ = a.step()
            if snap:
                va.apply(snap)
            return va.tick > 3 and not va.allies
        self.assertTrue(wait_until(ally_gone))
        self.assertEqual(len(self.srv.world.players), 1)
        a.close()

    def test_full_game_and_invalid_character_rejected(self):
        self.srv.max_players = 2
        a = RemoteHost("127.0.0.1", self.srv.port)
        b = RemoteHost("127.0.0.1", self.srv.port)
        try:
            with self.assertRaises(ConnectionRejected):
                RemoteHost("127.0.0.1", self.srv.port, timeout=3)
            b.close()
            time.sleep(0.2)
            with self.assertRaises(ConnectionRejected):
                RemoteHost("127.0.0.1", self.srv.port, timeout=3,
                           character={"name": "x", "class_name": "Dragon"})
        finally:
            a.close()

    def test_joiner_receives_the_hosts_map(self):
        from game.engine.map_schema import content_hash
        from game.engine.world_map import WorldMap
        a = RemoteHost("127.0.0.1", self.srv.port)
        try:
            data = a.welcome["map_data"]
            self.assertEqual(content_hash(data), a.welcome["map_hash"])
            wm = WorldMap.from_data(data)
            self.assertEqual((wm.width, wm.height), (self.srv.world.world_map.width, self.srv.world.world_map.height))
        finally:
            a.close()

    def test_bad_protocol_version_rejected(self):
        s = socket.create_connection(("127.0.0.1", self.srv.port), timeout=3)
        s.sendall(encode({"t": "hello", "v": 999}))
        buf = LineBuffer()
        msgs = []
        while not msgs:
            data = s.recv(65536)
            if not data:
                break
            msgs += buf.feed(data)
        s.close()
        self.assertEqual(msgs[0]["t"], "reject")

    def test_garbage_input_does_not_crash_host(self):
        s = socket.create_connection(("127.0.0.1", self.srv.port), timeout=3)
        s.sendall(b"this is not json\n")
        time.sleep(0.2)
        s.close()
        s = socket.create_connection(("127.0.0.1", self.srv.port), timeout=3)
        s.sendall(encode({"t": "hello", "v": PROTOCOL_VERSION}) + encode({"t": "cmd", "cmd": {"type": "NoSuchCommand"}}))
        time.sleep(0.2)
        s.close()
        # host still alive and serving
        host = RemoteHost("127.0.0.1", self.srv.port)
        self.assertIsNotNone(host.snapshot())
        host.close()

    def test_client_view_converges_to_host_state(self):
        """Host runs exactly N ticks then shuts down; the client's final view must equal the host's state."""
        self.srv.stop()
        srv = HostServer(MAP, "Wizard", seed=1, port=0, tick_rate=60)
        import threading
        th = threading.Thread(target=srv.serve_forever, kwargs={"max_ticks": 90}, daemon=True)
        th.start()
        host = RemoteHost("127.0.0.1", srv.port, class_name="Wizard")
        try:
            view = ClientView()
            view.apply(host.snapshot())
            host.send(C.ToggleAutopilot())
            host.send(C.ToggleCompanion("Fighter"))   # refused: no companions in co-op
            deadline = time.monotonic() + 10
            while not host.closed and time.monotonic() < deadline:   # read until the host hangs up
                snap, _ = host.step()
                if snap:
                    view.apply(snap)
                time.sleep(0.005)
            th.join(5)
            expected = ClientView()
            expected.apply(json.loads(json.dumps(make_snapshot(srv.world))))
            self.assertEqual(view.tick, 90)
            self.assertEqual(view.tick, expected.tick)
            self.assertEqual(sorted((e.eid, e.x, e.y, e.hp) for e in view.entities.values()),
                             sorted((e.eid, e.x, e.y, e.hp) for e in expected.entities.values()))
            self.assertEqual(len(view.companions), 0)
            self.assertTrue(view.you.ai_enabled)
        finally:
            host.close()


class DeltaTest(unittest.TestCase):
    def test_delta_roundtrip_and_savings(self):
        import random
        from game import saves
        from game.engine.bootstrap import create_world
        from game.net.delta import DeltaEncoder, DeltaDecoder
        random.seed(4)
        world, _ = create_world(MAP, saves.blank_character("a", "Rogue"), autopilot=True, auto_companion=True)
        enc, dec = DeltaEncoder(), DeltaDecoder()
        full_bytes = delta_bytes = 0
        for i in range(150):
            world.step(1 / 30)
            if i == 60:
                m = world.game_state.monsters[0]
                world.game_state.monsters.remove(m)        # an entity disappears
            ents = make_snapshot(world)["entities"]
            d = json.loads(json.dumps(enc.encode(ents)))
            self.assertEqual(dec.decode(d), json.loads(json.dumps(ents)))
            full_bytes += len(json.dumps(ents))
            delta_bytes += len(json.dumps(d))
        self.assertLess(delta_bytes, full_bytes / 3, "deltas should be much smaller than full snapshots")


class BadNetworkTest(unittest.TestCase):
    def test_commands_and_convergence_over_laggy_jittery_link(self):
        """150 ms +-60 ms each way: commands still apply and the client ends on the host's exact state."""
        import threading
        from tests.latency_proxy import LatencyProxy
        srv = HostServer(MAP, "Fighter", seed=2, port=0, tick_rate=30)
        th = threading.Thread(target=srv.serve_forever, kwargs={"max_ticks": 120}, daemon=True)
        th.start()
        proxy = LatencyProxy(srv.port, latency=0.15, jitter=0.06, seed=1)
        host = RemoteHost("127.0.0.1", proxy.port, class_name="Fighter")
        try:
            view = ClientView()
            view.apply(host.snapshot())
            start_x = view.hero.x
            host.send(C.MoveTo(view.hero.x + 150, view.hero.y))
            host.send(C.UsePotion())   # full HP: must be refused, potions stay at 3
            deadline = time.monotonic() + 15
            while not host.closed and time.monotonic() < deadline:
                snap, _ = host.step()
                if snap:
                    view.apply(snap)
                time.sleep(0.005)
            th.join(5)
            expected = ClientView()
            expected.apply(json.loads(json.dumps(make_snapshot(srv.world))))
            self.assertEqual(view.tick, 120)
            self.assertGreater(view.hero.x, start_x + 50)
            self.assertEqual(view.you.potions, 3)
            self.assertEqual(sorted((e.eid, e.x, e.y, e.hp) for e in view.entities.values()),
                             sorted((e.eid, e.x, e.y, e.hp) for e in expected.entities.values()))
        finally:
            host.close()
            proxy.close()


class EndToEndTest(unittest.TestCase):
    def test_host_process_and_headless_pygame_client_process(self):
        """Real processes: `game.net.server` host + `game.main --headless --connect` client."""
        import os
        import subprocess
        import sys
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with socket.socket() as probe:          # find a free loopback port
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        srv = subprocess.Popen([sys.executable, "-m", "game.net.server", "--map", MAP, "--hero", "4",
                                "--port", str(port), "--auto", "--max-ticks", "900"],
                               cwd=root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        try:
            self.assertIn("127.0.0.1", srv.stdout.readline())   # host announces it is loopback-only
            cli = subprocess.run([sys.executable, "-m", "game.main", "--headless", "--connect", str(port),
                                  "--max-time", "6"], cwd=root, capture_output=True, text=True, timeout=60)
            out = cli.stdout + cli.stderr
            self.assertEqual(cli.returncode, 0, out[-1500:])
            self.assertNotIn("Traceback", out)
            line = [l for l in out.splitlines() if l.startswith("RESULT: ")]
            self.assertEqual(len(line), 1, out[-1500:])
            self.assertIn("client=remote", line[0])
            t = float(line[0].split("time=")[1].split("s")[0])
            self.assertGreaterEqual(t, 6.0)
        finally:
            srv.kill()
            srv.wait()
            srv.stdout.close()


    def test_coop_two_game_processes_host_and_join(self):
        """Game A hosts (--host-game), game B joins (--connect); both are headless pygame clients."""
        import os
        import subprocess
        import sys
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        a = subprocess.Popen([sys.executable, "-m", "game.main", "--headless", "--host-game", "--port", str(port),
                              "--map", MAP, "--hero", "4", "--max-time", "8"],
                             cwd=root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        try:
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:          # wait until A is hosting
                line = a.stdout.readline()
                if "[HOST] Hosting" in line or not line:
                    break
            b = subprocess.run([sys.executable, "-m", "game.main", "--headless", "--connect", str(port),
                                "--hero", "3", "--max-time", "5"], cwd=root, capture_output=True, text=True,
                               timeout=60)
            out_b = b.stdout + b.stderr
            self.assertEqual(b.returncode, 0, out_b[-1500:])
            res_b = [l for l in out_b.splitlines() if l.startswith("RESULT: ")]
            self.assertEqual(len(res_b), 1, out_b[-1500:])
            self.assertIn("allies=1", res_b[0])          # B saw A's hero
            out_a, _ = a.communicate(timeout=60)
            self.assertEqual(a.returncode, 0, out_a[-1500:])
            self.assertNotIn("Traceback", out_a)
            self.assertIn("joined as player 1", out_a)
        finally:
            if a.poll() is None:
                a.kill()
                a.communicate()


    def test_joiner_reconnects_after_host_restart(self):
        import os
        import subprocess
        import sys
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        server = [sys.executable, "-m", "game.net.server", "--map", MAP, "--port", str(port)]
        first = subprocess.Popen(server + ["--max-ticks", "60"], cwd=root, stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, text=True)
        first.stdout.readline()
        cli = subprocess.Popen([sys.executable, "-m", "game.main", "--headless", "--connect", str(port),
                                "--reconnect", "--max-time", "3"], cwd=root, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, text=True)
        second = None
        try:
            first.communicate(timeout=30)                 # host 1 ends after 2 s
            time.sleep(1.5)
            second = subprocess.Popen(server + ["--max-ticks", "300"], cwd=root, stdout=subprocess.PIPE,
                                      stderr=subprocess.STDOUT, text=True)
            out, _ = cli.communicate(timeout=60)
            self.assertEqual(cli.returncode, 0, out[-1500:])
            self.assertIn("[NET] Reconnected", out)
            self.assertTrue(any(l.startswith("RESULT: ") for l in out.splitlines()), out[-1500:])
        finally:
            for p in (first, cli, second):
                if p is not None and p.poll() is None:
                    p.kill()
                    p.communicate()


if __name__ == "__main__":
    unittest.main()
