"""Host <-> client over real TCP on 127.0.0.1 (design/06 phase 4). No pygame."""
import json
import socket
import time
import unittest

from game.engine import commands as C
from game.engine.snapshot import make_snapshot
from game.client.view import ClientView
from game.net.client import RemoteHost, ConnectionRejected
from game.net.protocol import encode, LineBuffer
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

    def test_second_client_is_rejected_for_now(self):
        a = RemoteHost("127.0.0.1", self.srv.port)
        try:
            with self.assertRaises(ConnectionRejected):
                RemoteHost("127.0.0.1", self.srv.port, timeout=3)
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
        s.sendall(encode({"t": "hello", "v": 1}) + encode({"t": "cmd", "cmd": {"type": "NoSuchCommand"}}))
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
            host.send(C.ToggleCompanion("Fighter"))
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
            self.assertEqual(len(view.companions), 1)
            self.assertTrue(view.you.ai_enabled)
        finally:
            host.close()


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


if __name__ == "__main__":
    unittest.main()
