#!/usr/bin/env python3
"""Watch a boss hunt in a REAL game window: five autopilot heroes (one of each class, level 10) against ONE boss in
bossTestRoom, with the boss stats from the tuner. Nothing is saved; the camera follows the Fighter.

  PYTHONPATH=. .venv/bin/python3 tools/boss_hunt.py                 # the tuned Ashardalon (AC 16, dmg 2, HP 343.1)
  PYTHONPATH=. .venv/bin/python3 tools/boss_hunt.py --hp 400 --dmg 3 --level 10 --seed 2

It builds the world exactly like the tuner's simulation (game/boss_sim.build_fight), so what you watch is what the
tuner measured (apart from real-time frame steps instead of fixed 1/30 s ones). ESC quits.
"""
import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("--boss", default="ashardalon")
ap.add_argument("--classes", default="Fighter,Paladin,Cleric,Rogue,Wizard")
ap.add_argument("--level", type=int, default=10)
ap.add_argument("--ac", type=float, default=16)
ap.add_argument("--dmg", type=float, default=2, help="board damage (x25 = real per hit)")
ap.add_argument("--hp", type=float, default=343.1, help="board HP (x50 = real HP)")
ap.add_argument("--seed", type=int, default=1)
args = ap.parse_args()

from game.boss_sim import BossStats, build_fight                      # noqa: E402
import game.engine.bootstrap as bootstrap                              # noqa: E402

CLASSES = [c.strip().capitalize() for c in args.classes.split(",")]
STATS = BossStats(args.ac, args.dmg, args.hp)


def boss_hunt_world(map_path, char_data, **_ignored):
    """Stands in for bootstrap.create_world: the session gets our party and boss instead of one throwaway hero."""
    world, _boss = build_fight(CLASSES, args.level, STATS, args.seed, args.boss)
    return world, world.players[0]


bootstrap.create_world = boss_hunt_world          # game.session does `from ...bootstrap import create_world` when it runs
print(f"Boss hunt: {args.boss} AC {STATS.ac:g}, {STATS.real_dmg:.0f} dmg/hit, {STATS.real_hp:.0f} HP  vs  "
      f"{', '.join(CLASSES)} (level {args.level}), seed {args.seed}", flush=True)
sys.argv = ["game.main", "--auto", "--hero", "0", "--map", "data/maps/bossTestRoom.json"]
import game.main                                                        # noqa: E402
game.main.run()
