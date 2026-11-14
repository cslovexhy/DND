#!/usr/bin/env python3
"""Watch the quest bot (game/quest_bot.py — the early-level benchmark's player) in a REAL game window: a fresh
level-1 hero in Northshire, no companions, picking up / turning in quests and fighting quest mobs on its own.
Nothing is saved. ESC quits; the game starts at 4x speed (auto mode): press - twice for 1x, + to speed up.

  PYTHONPATH=. .venv/bin/python3 tools/quest_bot_demo.py [--class Cleric] [--seed 3] [--level 1]
"""
import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("--class", dest="cls", default="Cleric")
ap.add_argument("--seed", type=int, default=3)
ap.add_argument("--level", type=int, default=1)
ap.add_argument("--map", default="data/maps/northshire.json")
args = ap.parse_args()

import random                                                       # noqa: E402
import game.engine.bootstrap as bootstrap                           # noqa: E402
from game.engine.world import World                                 # noqa: E402
from game.quest_bot import QuestBot                                 # noqa: E402
from game.content.heroes import HERO_CLASSES                        # noqa: E402

_create_world = bootstrap.create_world


def demo_world(map_path, char_data, **kw):
    """Stands in for bootstrap.create_world: same world, plus a quest bot driving player 0 every few steps."""
    random.seed(args.seed)
    kw["auto_companion"] = False
    char_data = dict(char_data, level=args.level)
    world, player = _create_world(map_path, char_data, **kw)
    bot = QuestBot(world, player)
    step = World.step
    counter = [0]

    def bot_step(self, dt):
        if counter[0] % 5 == 0:
            bot.step()
        counter[0] += 1
        return step(self, dt)
    world.step = bot_step.__get__(world)
    return world, player


bootstrap.create_world = demo_world           # game.session does `from ...bootstrap import create_world` when it runs
hero_idx = next(i for i, c in enumerate(HERO_CLASSES) if c["class"] == args.cls.capitalize())
print(f"Quest bot demo: {args.cls} level {args.level}, seed {args.seed}, {args.map}", flush=True)
sys.argv = ["game.main", "--auto", "--hero", str(hero_idx), "--map", args.map, "--no-companion"]
import game.main                                                    # noqa: E402
game.main.run()
