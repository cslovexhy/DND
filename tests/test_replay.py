"""Command-log replay: a recorded session replayed through the pure simulation (no pygame) must end
in exactly the same state as the original pygame run. This proves the client only talks to the sim
through commands (design/06 phase 2) — the property the network layer relies on.

Recordings in tests/replays/ were produced with:
  .venv/bin/python3 -m game.main --headless --seed S --max-time T --hero H --map M \
      --input-script tests/scripts/manual_X.json --record-commands tests/replays/X.json
Their expected RESULT lines are the matching entries in tests/golden/headless.json.
"""
import glob
import json
import os
import sys
import unittest

from game.engine import replay
from game import headless

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOLDEN = os.path.join(ROOT, "tests", "golden", "headless.json")


class ReplayTest(unittest.TestCase):
    def test_replays_match_pygame_sessions(self):
        with open(GOLDEN) as f:
            golden = json.load(f)
        files = sorted(glob.glob(os.path.join(ROOT, "tests", "replays", "*.json")))
        self.assertTrue(files)
        for path in files:
            name = os.path.splitext(os.path.basename(path))[0]
            with self.subTest(name):
                got = headless.parse_result(replay.run_recording(replay.load_recording(path)))
                self.assertEqual(got, golden[name])

    def test_replay_runs_without_pygame(self):
        self.assertNotIn("pygame", sys.modules)

    def test_autopilot_only_matches_golden(self):
        with open(GOLDEN) as f:
            golden = json.load(f)
        got = replay.run_recording({"map": "data/maps/northshire.json", "class_name": "Fighter",
                                    "seed": 1, "max_time": 30, "commands": []})
        self.assertEqual(headless.parse_result(got), golden["hero0_seed1"])

    def test_command_roundtrip(self):
        from game.engine import commands as c
        for cmd in (c.MoveTo(1.5, 2.0), c.Cast("Q", 3, 4, target_id=7, fallback_move=True), c.UsePotion(),
                    c.ToggleCompanion("Wizard"), c.HoldPosition(True)):
            self.assertEqual(c.from_dict(json.loads(json.dumps(c.to_dict(cmd)))), cmd)


if __name__ == "__main__":
    unittest.main()
