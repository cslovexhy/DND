"""Hotbar slots can be rearranged: drag one slot onto another to swap them; the key of a slot casts whatever is
in it. The order is saved with the character; new skills go to the end."""
import json
import os
import subprocess
import sys
import tempfile
import unittest

from game.client.hotbar import merge_order, swap

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class OrderTest(unittest.TestCase):
    def test_new_character_uses_the_game_order(self):
        self.assertEqual(merge_order(None, ["Q", "R"]), ["Q", "R"])

    def test_saved_order_kept_and_new_skills_appended(self):
        self.assertEqual(merge_order(["G", "Q", "R"], ["Q", "R", "E", "F", "G"]), ["G", "Q", "R", "E", "F"])

    def test_unknown_or_duplicate_saved_keys_are_dropped(self):
        self.assertEqual(merge_order(["X", "R", "R", "Q"], ["Q", "R"]), ["R", "Q"])

    def test_swap(self):
        self.assertEqual(swap(["Q", "R", "E", "F", "G"], 4, 1), ["Q", "G", "E", "F", "R"])
        self.assertEqual(swap(["Q", "R"], 0, 9), ["Q", "R"])


class DragInTheClientTest(unittest.TestCase):
    def test_drag_cleave_from_5_to_2_then_key_2_casts_cleave(self):
        """Headless pygame Fighter (level 8: Strike, Charge, Shout, Heroic Strike, Cleave): drag slot 5 onto 2, press
        2 -> Cleave, press 5 -> Charge (swapped there), click slot 1 -> Strike."""
        from game.engine import replay
        with tempfile.TemporaryDirectory() as d:
            script, rec = os.path.join(d, "s.json"), os.path.join(d, "rec.json")
            with open(script, "w") as f:
                json.dump([{"tick": 0, "type": "key", "key": "p"},
                           {"tick": 3, "type": "drag", "from": {"hotbar_slot": 4}, "to": {"hotbar_slot": 1}},
                           {"tick": 6, "type": "key", "key": "2"},
                           {"tick": 30, "type": "key", "key": "5"},
                           {"tick": 50, "type": "click", "button": 1, "at": {"hotbar_slot": 0}}], f)
            p = subprocess.run([sys.executable, "-m", "game.main", "--headless", "--seed", "3", "--max-time", "2",
                                "--hero", "0", "--level", "8", "--map", "data/maps/northshire.json",
                                "--input-script", script, "--record-commands", rec, "--no-companion"],
                               cwd=ROOT, capture_output=True, text=True, timeout=60)
            self.assertEqual(p.returncode, 0, p.stderr[-1500:])
            casts = [c["cmd"]["ab_key"] for c in replay.load_recording(rec)["commands"] if c["cmd"]["type"] == "Cast"]
        self.assertEqual(casts, ["G", "R", "Q"])          # Cleave, Charge, Strike


if __name__ == "__main__":
    unittest.main()
