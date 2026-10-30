"""Pure-sim replay of a recorded command log (no pygame, no window).

A recording (written by `--headless --record-commands FILE`) holds the scenario (map, hero class,
seed, length) and every player command with the simulation tick it was applied on. Replaying it
through World.step() must reproduce the original run exactly (same state digest). This is the
backbone for fast regression tests today and for the host/server simulation later.
"""
import json
import random

from game import saves
from game.engine import commands
from game.engine.bootstrap import create_world
from game.headless import FIXED_DT, format_result


def save_recording(path, scenario, world):
    data = dict(scenario)
    data["commands"] = [{"tick": t, "player": pid, "cmd": commands.to_dict(c)} for t, pid, c in world.command_log]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1)


def load_recording(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def run_recording(rec):
    """Replay a recording; returns the RESULT line (same format as a headless run)."""
    random.seed(rec["seed"])
    cls = rec["class_name"]
    char = saves.blank_character(cls.lower(), cls)
    world, _player = create_world(rec["map"], char, autopilot=True, auto_companion=True)
    by_tick = {}
    for c in rec["commands"]:
        by_tick.setdefault(c["tick"], []).append((c["player"], commands.from_dict(c["cmd"])))
    gs = world.game_state
    tick = 0
    while gs.game_time < rec["max_time"] and not gs.adventure_failed:
        for pid, cmd in by_tick.get(tick, ()):
            world.submit(cmd, pid)
        world.step(FIXED_DT)
        world.events.clear()   # nobody is watching; don't accumulate
        tick += 1
    return format_result("DEFEATED" if gs.adventure_failed else "TIMEOUT", gs, world.hero)
