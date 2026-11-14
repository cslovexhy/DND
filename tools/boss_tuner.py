#!/usr/bin/env python3
"""Tune (or just test) boss stats against a party on autopilot, in bossTestRoom. Runs ONLY the boss simulation.

  # find stats: Ashardalon vs all five classes at level 10, 2 minutes
  PYTHONPATH=. .venv/bin/python3 tools/boss_tuner.py --boss 16 --level 10 --target-time 120

  # try specific stats (board units: hp, dmg) and see how the full group and every weaker group do
  PYTHONPATH=. .venv/bin/python3 tools/boss_tuner.py --eval 700,12 --ac 16

Board units convert to real numbers as: HP x 50, damage x 25, AC as is (see game/boss_sim.py).
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game.boss_sim import PARTY_CLASSES, BossStats                      # noqa: E402
from game.boss_tune import Tuner                                        # noqa: E402
from game.content.monsters import SPAWN_STATS                           # noqa: E402


def describe(tuner, a, seeds):
    s = a.stats
    print(f"\n  boss: AC {s.ac}   damage {s.dmg} board = {s.real_dmg:.0f} real/hit   HP {s.hp} board = {s.real_hp:.0f} real")
    print(f"  {'group':<22}{'wins':>6}{'score':>8}{'best':>7}{'deaths':>8}   per seed (score)")
    rows = [(f"full ({len(tuner.group)} x L{tuner.level})", a.full)] + list(a.variants.items())
    for name, e in rows:
        per = " ".join(f"{x:.2f}" for x in e.scores)
        print(f"  {name:<22}{e.wins:>3}/{len(e.results):<2}{e.mean_score:>8.2f}{min(e.scores):>7.2f}{e.deaths:>8.1f}   {per}")
    verdict = "OK: full group wins, every weaker group loses" if a.feasible else "NOT satisfied"
    print(f"  margin {a.margin:+.2f}  ->  {verdict}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--boss", type=int, default=16, help="monster id to fight (default 16 = Ashardalon)")
    ap.add_argument("--group", default=",".join(PARTY_CLASSES), help="comma-separated classes (default: all five)")
    ap.add_argument("--level", type=int, default=10)
    ap.add_argument("--target-time", type=float, default=120.0, help="seconds from first aggro (default 120)")
    ap.add_argument("--ac", type=float, default=None, help="boss AC (default: the boss' current AC)")
    ap.add_argument("--aim", type=float, default=0.95, help="kill the boss at this fraction of the target time")
    ap.add_argument("--seeds", type=int, default=3, help="seeds used while searching")
    ap.add_argument("--verify-seeds", type=int, default=8, help="seeds used to verify the answer")
    ap.add_argument("--eval", metavar="HP,DMG", help="don't search: assess these board stats")
    ap.add_argument("--dmg-grid", help="comma-separated board damage values to scan instead of the default grid")
    ap.add_argument("--out", help="write the result JSON here (default scratch/boss_tune_<boss>.json)")
    args = ap.parse_args()

    group = [c.strip().capitalize() for c in args.group.split(",") if c.strip()]
    bad = [c for c in group if c not in PARTY_CLASSES]
    if bad:
        ap.error(f"unknown class {bad}; choose from {PARTY_CLASSES}")
    base = SPAWN_STATS[args.boss]
    ac = args.ac if args.ac is not None else base["ac"]
    tuner = Tuner(group, args.level, args.target_time, ac, tuple(range(1, args.seeds + 1)), args.boss,
                  None, args.aim)
    print(f"Boss {args.boss} (now: AC {base['ac']}, HP {base['hp']}, dmg {base['dmg']} board)   group {group} "
          f"level {args.level}   target {args.target_time:.0f}s")

    if args.eval:
        hp, dmg = (float(x) for x in args.eval.split(","))
        describe(tuner, tuner.assess(BossStats(ac, dmg, hp), tuple(range(1, args.verify_seeds + 1))),
                 args.verify_seeds)
        print(f"\n  {tuner.fights} fights")
        return

    grid = [float(x) for x in args.dmg_grid.split(",")] if args.dmg_grid else None   # default: the library's grid
    print("\nscanning damage; for each, HP is bisected so the full group wins at "
          f"{args.aim:.0%} of the target time:")
    res = tuner.search(grid)
    if res["lowest"] is None:
        print("\nNo damage value satisfied every requirement. Closest by margin:")
        best = max(res["rows"], key=lambda a: a.margin)
        describe(tuner, tuner.assess(best.stats, tuple(range(1, args.verify_seeds + 1))), args.verify_seeds)
        return
    out = {"boss": args.boss, "group": group, "level": args.level, "target_time": args.target_time,
           "results": {}}
    for label, a in (("lowest damage that works", res["lowest"]), ("most robust (largest margin)", res["robust"])):
        print(f"\n== {label} ==")
        verified = tuner.assess(a.stats, tuple(range(1, args.verify_seeds + 1)))
        describe(tuner, verified, args.verify_seeds)
        out["results"][label] = {"ac": a.stats.ac, "hp_board": a.stats.hp, "dmg_board": a.stats.dmg,
                                 "hp_real": a.stats.real_hp, "dmg_real": a.stats.real_dmg,
                                 "verified_on_seeds": args.verify_seeds, "feasible": verified.feasible,
                                 "margin": round(verified.margin, 3)}
    path = args.out or os.path.join("scratch", f"boss_tune_{args.boss}.json")
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\n{tuner.fights} fights run; saved {path}")


if __name__ == "__main__":
    main()
