"""Headless mode: unit tests for game/headless.py plus determinism + golden-run regression tests.

Golden runs live in tests/golden/headless.json. They pin current gameplay behaviour so refactors
(design/06 phases 1-3) can be proven behaviour-neutral. If you change balance/content ON PURPOSE:
    UPDATE_GOLDEN=1 .venv/bin/python -m unittest tests.test_headless
and commit the new golden file.
"""
import json
import os
import subprocess
import sys
import unittest

from game import headless
from game.engine.entities import GameState, Hero

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOLDEN = os.path.join(ROOT, "tests", "golden", "headless.json")
MAP = "data/maps/northshire.json"
MAX_TIME = 30
# (hero class index, seed) — one scenario per hero class
SCENARIOS = [(i, 1) for i in range(5)]


def run_headless(hero_idx, seed, max_time=MAX_TIME, map_path=MAP):
    env = dict(os.environ, PYTHONHASHSEED="random")
    p = subprocess.run(
        [sys.executable, "-m", "game.main", "--headless", "--seed", str(seed),
         "--max-time", str(max_time), "--hero", str(hero_idx), "--map", map_path],
        cwd=ROOT, capture_output=True, text=True, timeout=120, env=env)
    lines = [l for l in p.stdout.splitlines() if l.startswith("RESULT: ")]
    assert p.returncode == 0 and len(lines) == 1, f"rc={p.returncode}\n{p.stdout[-800:]}\n{p.stderr[-800:]}"
    return headless.parse_result(lines[0])


class HeadlessUnitTest(unittest.TestCase):
    def test_parse_args_defaults_and_values(self):
        self.assertFalse(headless.parse_args(["x"]).enabled)
        c = headless.parse_args(["x", "--headless", "--seed", "7", "--max-time", "12.5"])
        self.assertEqual((c.enabled, c.seed, c.max_time), (True, 7, 12.5))

    def test_digest_is_stable_and_sensitive(self):
        def make(x):
            gs = GameState()
            h = Hero("A", "Fighter", x, 0.0, hp=4, ac=10, speed=4, surge_value=1)
            gs.heroes.append(h)
            return gs
        self.assertEqual(headless.state_digest(make(1.0)), headless.state_digest(make(1.0)))
        self.assertNotEqual(headless.state_digest(make(1.0)), headless.state_digest(make(50.0)))

    def test_parse_result_roundtrip(self):
        r = headless.parse_result("RESULT: TIMEOUT time=30.0s hp=1/2 kills=3 digest=abc")
        self.assertEqual(r["outcome"], "TIMEOUT")
        self.assertEqual(r["kills"], "3")


class HeadlessRunTest(unittest.TestCase):
    def test_same_seed_is_deterministic(self):
        a = run_headless(0, 1, max_time=15)
        b = run_headless(0, 1, max_time=15)
        self.assertEqual(a, b)

    def test_runs_in_simulated_time_not_real_time(self):
        import time
        t0 = time.time()
        r = run_headless(0, 1, max_time=60)
        self.assertEqual(r["time"], "60.0s")
        self.assertLess(time.time() - t0, 40, "60 simulated seconds should take far less than 60 real seconds")

    def test_golden_runs(self):
        results = {f"hero{h}_seed{s}": run_headless(h, s) for h, s in SCENARIOS}
        if os.environ.get("UPDATE_GOLDEN"):
            with open(GOLDEN, "w") as f:
                json.dump(results, f, indent=2, sort_keys=True)
            self.skipTest("golden file updated")
        with open(GOLDEN) as f:
            expected = json.load(f)
        self.assertEqual(results, expected)


if __name__ == "__main__":
    unittest.main()
