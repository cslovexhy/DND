"""
Headless mode support (no window, no audio, simulated time) for automated testing.

Pure Python: must NOT import pygame (enforced by tests/test_architecture.py), so it can be
imported before pygame.init() to configure the SDL environment.

  python3 -m game.main --headless [--seed N] [--max-time SECONDS] [--hero IDX] [--map PATH] [--pp 1..8]
                       [--input-script FILE.json]   (scripted manual input; use a TAB event to turn the autopilot off)

Headless implies --auto (throwaway hero, AI on, never touches real saves). Time is simulated:
every loop iteration advances the game by FIXED_DT seconds and nothing sleeps, so a 60 s game
finishes in a few real seconds, and the same seed gives the same result.
The run ends with one line:  RESULT: <OUTCOME> time=.. hp=../.. kills=.. digest=<hash>
"""
import hashlib
import os
from dataclasses import dataclass

FIXED_DT = 1.0 / 30.0
DEFAULT_SEED = 1
DEFAULT_MAX_TIME = 60.0


@dataclass(frozen=True)
class HeadlessConfig:
    enabled: bool = False
    seed: int = DEFAULT_SEED
    max_time: float = DEFAULT_MAX_TIME   # simulated seconds
    record_commands: str = ""            # write the player-command log to this JSON file when the run ends
    input_script: str = ""               # JSON file of scripted player input (see game/input_script.py)
    fixed_dt: float = FIXED_DT


def _arg_value(argv, name, cast, default):
    for i, arg in enumerate(argv):
        if arg == name and i + 1 < len(argv):
            return cast(argv[i + 1])
    return default


def parse_args(argv):
    return HeadlessConfig(
        enabled="--headless" in argv,
        seed=_arg_value(argv, "--seed", int, DEFAULT_SEED),
        max_time=_arg_value(argv, "--max-time", float, DEFAULT_MAX_TIME),
        input_script=_arg_value(argv, "--input-script", str, ""),
        record_commands=_arg_value(argv, "--record-commands", str, ""),
    )


def apply_sdl_env():
    """Select SDL's dummy video/audio drivers. Must run before pygame.init()."""
    os.environ["SDL_VIDEODRIVER"] = "dummy"
    os.environ["SDL_AUDIODRIVER"] = "dummy"


def state_digest(game_state):
    """Short stable hash of the simulation state (positions/HP/alive of every hero and monster).
    Coordinates are rounded so harmless float noise doesn't change it."""
    parts = []
    for kind, entities in (("H", game_state.heroes), ("M", game_state.monsters)):
        for e in entities:
            parts.append(f"{kind}|{e.name}|{e.x:.1f}|{e.y:.1f}|{e.hp:.1f}|{int(e.alive)}"
                         f"|{getattr(e, 'level', 0)}|{getattr(e, 'xp', 0)}|{getattr(e, 'kills', 0)}")
    parts.append(f"T|{game_state.game_time:.2f}")
    return hashlib.sha1("\n".join(parts).encode()).hexdigest()[:12]


def format_result(outcome, game_state, hero):
    return (f"RESULT: {outcome} time={game_state.game_time:.1f}s hp={hero.hp:.0f}/{hero.max_hp} "
            f"kills={hero.kills} digest={state_digest(game_state)}")


def parse_result(line):
    """Parse a RESULT line into a dict (outcome plus key=value fields)."""
    assert line.startswith("RESULT: "), line
    outcome, *fields = line[len("RESULT: "):].split()
    out = {"outcome": outcome}
    for f in fields:
        k, v = f.split("=", 1)
        out[k] = v
    return out
