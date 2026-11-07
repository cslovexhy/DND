#!/usr/bin/env python3
"""Early-level class strength benchmark (pure sim, no window).

Every class starts a fresh level-1 character in Northshire (no companions) and is played by the quest bot
(game/quest_bot.py): pick up level-appropriate quests whenever possible, kill the quest mobs, turn quests in as soon
as they are done (Garrick Padfoot's bounty is skipped). A run ends when the hero reaches the target level
(default 6) or the time cap. Reports, per class over the seeds: sim time to each level, deaths, kills, quests done.

    .venv/bin/python3 tools/early_class_bench.py [--seeds 3] [--to-level 6] [--cap-min 60] [--only Fighter,Rogue]
                                                 [--map data/maps/northshire.json] [--json OUT]
"""
import argparse
import contextlib
import io
import json
import os
import random
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from game import saves                                  # noqa: E402
saves.SAVE_DIR = tempfile.mkdtemp()                     # never touch real saves
from game.engine.bootstrap import create_world          # noqa: E402
from game.quest_bot import QuestBot                     # noqa: E402

CLASSES = ["Fighter", "Cleric", "Paladin", "Rogue", "Wizard"]
DT = 1 / 30


def run(cls, seed, to_level=6, cap_min=60, map_path="data/maps/northshire.json"):
    """One character from level 1. Returns a dict of results (level_at: sim seconds per level reached)."""
    random.seed(seed)
    world, player = create_world(map_path, saves.blank_character(cls.lower(), cls), autopilot=True)
    bot = QuestBot(world, player)
    hero = player.hero
    level_at = {1: 0.0}
    t, steps = 0.0, 0
    with contextlib.redirect_stdout(io.StringIO()):      # the hero AIs print debug lines
        while hero.level < to_level and t < cap_min * 60:
            if steps % 5 == 0:                           # decisions 6x a second are plenty
                bot.step()
            world.step(DT)
            world.events.clear()
            t += DT
            steps += 1
            for lv in range(2, hero.level + 1):          # a big turn-in can skip a level in one step
                level_at.setdefault(lv, t)
    return {"class": cls, "seed": seed, "reached": hero.level, "time": t, "level_at": level_at,
            "deaths": hero.deaths, "kills": hero.kills, "quests": list(player.quests.completed)}


def fmt_min(sec):
    return f"{sec / 60:5.1f}" if sec is not None else "   - "


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--to-level", type=int, default=6)
    ap.add_argument("--cap-min", type=float, default=60, help="give up after this many sim minutes")
    ap.add_argument("--only", help="comma-separated classes")
    ap.add_argument("--map", default="data/maps/northshire.json")
    ap.add_argument("--json", help="write all runs here")
    args = ap.parse_args(argv)
    classes = [c.strip().capitalize() for c in args.only.split(",")] if args.only else CLASSES
    levels = list(range(2, args.to_level + 1))
    print(f"Quest-bot benchmark: level 1 -> {args.to_level} on {args.map}, {args.seeds} seed(s), "
          f"cap {args.cap_min:g} sim min. Times are sim minutes (average over seeds).", flush=True)
    print(f"{'class':8} " + " ".join(f"  L{lv:<3}" for lv in levels) + "  deaths  kills  quests  wall", flush=True)
    all_runs = []
    for cls in classes:
        t0 = time.time()
        runs = [run(cls, s, args.to_level, args.cap_min, args.map) for s in range(1, args.seeds + 1)]
        all_runs += runs
        cells = []
        for lv in levels:
            times = [r["level_at"].get(lv) for r in runs]
            cells.append(fmt_min(sum(times) / len(times)) if all(x is not None for x in times) else "   - ")
        deaths = sum(r["deaths"] for r in runs) / len(runs)
        kills = sum(r["kills"] for r in runs) / len(runs)
        quests = sum(len(r["quests"]) for r in runs) / len(runs)
        print(f"{cls:8} " + " ".join(f"{c:>6}" for c in cells) +
              f"  {deaths:6.1f} {kills:6.0f} {quests:6.1f}  {time.time() - t0:4.0f}s", flush=True)
    if args.json:
        with open(args.json, "w") as f:
            json.dump(all_runs, f, indent=1)
    return all_runs


if __name__ == "__main__":
    main()
