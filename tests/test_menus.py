"""Menu flow (map select keys for solo / host / join). Runs pygame in a subprocess with SDL's dummy
drivers, so the pure-sim tests in this process keep running without pygame loaded."""
import os
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SCRIPT = r'''
import os, sys, json
os.environ["SDL_VIDEODRIVER"] = "dummy"; os.environ["SDL_AUDIODRIVER"] = "dummy"
import pygame
pygame.init()
pygame.display.set_mode((1024, 768))
from game.menus import MenuContext, map_select
ctx = MenuContext(clock=pygame.time.Clock(), font=pygame.font.Font(None, 20), big_font=pygame.font.Font(None, 32),
                  title_font=pygame.font.Font(None, 48), hero_sprites={})
char = {"name": "t", "level": 1, "class_name": "Fighter"}
out = {}
for key in ("RETURN", "h", "j", "ESCAPE"):
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=getattr(pygame, "K_" + key)))
    out[key] = map_select(ctx, char)
print(json.dumps(out))
'''


class MenuTest(unittest.TestCase):
    def test_map_select_solo_host_join_back(self):
        p = subprocess.run([sys.executable, "-c", SCRIPT], cwd=ROOT, capture_output=True, text=True, timeout=60)
        self.assertEqual(p.returncode, 0, p.stderr[-1500:])
        import json
        out = json.loads(p.stdout.strip().splitlines()[-1])
        self.assertTrue(out["RETURN"].endswith(".json"))
        self.assertEqual(set(out["h"]), {"host"})
        self.assertTrue(out["h"]["host"].endswith(".json"))
        self.assertEqual(out["j"], {"join": True})
        self.assertIsNone(out["ESCAPE"])


if __name__ == "__main__":
    unittest.main()
