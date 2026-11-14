"""Menu flow (map select keys for solo / host / join). Runs pygame in a subprocess with SDL's dummy
drivers, so the pure-sim tests in this process keep running without pygame loaded."""
import os
import subprocess
import sys
import unittest

from tests import item_ids as I

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SCRIPT = r'''
import os, sys, json
from tests import item_ids as I
os.environ["SDL_VIDEODRIVER"] = "dummy"; os.environ["SDL_AUDIODRIVER"] = "dummy"
import pygame
pygame.init()
pygame.display.set_mode((1024, 768))
from game.menus import MenuContext, map_select
import game.menus as menus
menus.join_select = lambda ctx: {"join": True, "address": "192.168.1.23"}   # Join screen tested in test_lan
ctx = MenuContext(clock=pygame.time.Clock(), font=pygame.font.Font(None, 20), big_font=pygame.font.Font(None, 32),
                  title_font=pygame.font.Font(None, 48), hero_sprites={})
char = {"name": "t", "level": 1, "class_name": "Fighter"}
from game.menus import _pp_dropdown_rects
W = pygame.display.get_surface().get_width()
button, options = _pp_dropdown_rects(W)
def key(k):
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=getattr(pygame, "K_" + k)))
def click(pos):
    pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=pos, button=1))
out = {}
key("RETURN"); out["solo"] = map_select(ctx, char)
key("EQUALS"); key("EQUALS"); key("h"); out["host_plus2"] = map_select(ctx, char)
click(button.center); click(options[7].center); key("RETURN"); out["dropdown_8"] = map_select(ctx, char)
for _ in range(20): key("EQUALS")
key("RETURN"); out["capped"] = map_select(ctx, char)
key("MINUS"); key("RETURN"); out["floor"] = map_select(ctx, char)
key("j"); out["join"] = map_select(ctx, char)
key("l"); out["lan_host"] = map_select(ctx, char)
key("ESCAPE"); out["back"] = map_select(ctx, char)
print(json.dumps(out))
'''


class MenuTest(unittest.TestCase):
    def test_map_select_solo_host_join_back_and_pp_dropdown(self):
        p = subprocess.run([sys.executable, "-c", SCRIPT], cwd=ROOT, capture_output=True, text=True, timeout=60)
        self.assertEqual(p.returncode, 0, p.stderr[-1500:])
        import json
        out = json.loads(p.stdout.strip().splitlines()[-1])
        self.assertTrue(out["solo"]["map"].endswith(".json"))
        self.assertEqual(out["solo"]["pp"], 1)                       # default 1pp
        self.assertEqual(set(out["host_plus2"]), {"host", "pp"})
        self.assertEqual(out["host_plus2"]["pp"], 3)                 # + twice
        self.assertEqual(out["dropdown_8"]["pp"], 8)                 # dropdown: open, pick 8pp
        self.assertEqual(out["capped"]["pp"], 8)                     # never above 8
        self.assertEqual(out["floor"]["pp"], 1)                      # never below 1
        self.assertEqual(out["join"], {"join": True, "address": "192.168.1.23"})
        self.assertEqual(out["lan_host"]["lan"], True)               # L = host on the home network
        self.assertNotIn("lan", out["host_plus2"])                   # H = this computer only
        self.assertIsNone(out["back"])


FRESH_SCRIPT = r'''
import os, sys, json
import tempfile
from tests import item_ids as I
os.environ["SDL_VIDEODRIVER"] = "dummy"; os.environ["SDL_AUDIODRIVER"] = "dummy"
from game import saves
saves.SAVE_DIR = tempfile.mkdtemp()
from game.menus import fresh_character
from tests import item_ids as I
stale = saves.blank_character("pal", "Paladin", level=4)
saves.save_character(stale)
listed = saves.list_characters()[0]                   # what the character screen read when it opened
newer = dict(stale, inventory=[{"slot": 1, "item": I.SUSHI_PLATE, "count": 1}])
saves.save_character(newer)                           # another window (a co-op session) saved meanwhile
print(json.dumps(fresh_character(listed)["inventory"]))
'''


class FreshCharacterTest(unittest.TestCase):
    def test_play_uses_the_save_on_disk_not_the_list_read_earlier(self):
        """Lost-item bug: a stale copy from the character screen overwrote a co-op save made meanwhile."""
        p = subprocess.run([sys.executable, "-c", FRESH_SCRIPT], cwd=ROOT, capture_output=True, text=True, timeout=60)
        self.assertEqual(p.returncode, 0, p.stderr[-1500:])
        import json
        self.assertEqual(json.loads(p.stdout.strip().splitlines()[-1]),
                         [{"slot": 1, "item": I.SUSHI_PLATE, "count": 1}])


if __name__ == "__main__":
    unittest.main()
