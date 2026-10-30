# Automated AI Testing — Lessons Learned

## What We Built
A hero AI system that can play the game autonomously, allowing us to:
1. Observe gameplay without manual input
2. Collect logs to diagnose bugs
3. Tune difficulty by watching AI success/failure rates
4. Run `--auto` flag to skip hero select and enable AI immediately

## How to Run

```bash
# Visual mode (watch the AI play):
python3 game/main.py --auto

# With specific hero (0=Fighter, 1=Cleric, 2=Paladin, 3=Rogue, 4=Wizard):
python3 game/main.py --auto --hero 0

# Capture logs for analysis:
python3 game/main.py --auto > /tmp/dnd_ai_log.txt 2>&1 &
PID=$!; sleep 30; kill $PID; cat /tmp/dnd_ai_log.txt

# Toggle AI during manual play: press TAB
```

## What Needs Improvement

### 1. Game window management
**Problem:** Every test run opens a pygame window that stays open until manually killed.
**Solution needed:** Add `--headless` mode that runs the game WITHOUT opening a window. Just ticks the simulation and outputs logs. This would allow:
- Running 100 simulations in seconds
- No leftover windows
- CI/CD-style testing

### 2. Auto-termination
**Problem:** Game runs forever, must be killed externally.
**Solution needed:** Add `--max-time 60` flag that auto-exits after N seconds. Also auto-exit on victory/defeat and print a summary line:
```
RESULT: VICTORY time=45.3s hp=180/400 kills=15 rooms=7/7
RESULT: DEFEATED time=32.1s hp=0/400 kills=9 rooms=5/7
```

### 3. Seed control for reproducibility
**Problem:** Each run generates a random dungeon, can't reproduce a specific scenario.
**Solution needed:** Add `--seed 12345` flag to fix the random seed. Same seed = same dungeon layout + same monster spawns = reproducible results.

### 4. Batch testing
**Problem:** One run at a time, slow iteration.
**Solution needed:** A test runner script:
```bash
python3 tools/batch_test.py --hero 0 --runs 50 --max-time 60
# Output: Win rate, avg time, avg HP remaining, avg kills
```

### 5. Structured output (not just print)
**Problem:** Logs have null bytes from pygame, hard to parse.
**Solution needed:** Write structured JSON logs to a file:
```json
{"time": 4.5, "event": "ability_used", "ability": "Q", "targets": 3, "damage": 150}
{"time": 4.5, "event": "monster_killed", "name": "Kobold", "pos": [1200, 400]}
{"time": 45.3, "event": "adventure_complete", "result": "victory", "hp": 180}
```

## Architecture for Full Automation

```
game/main.py --auto --headless --seed 42 --max-time 60 --log /tmp/run.json
    │
    ├── No pygame window opened
    ├── Fixed random seed for reproducibility
    ├── Auto-exits after 60s or on victory/defeat
    ├── Writes structured JSON events to log file
    └── Prints summary line to stdout

tools/batch_test.py --hero 0 --runs 100
    │
    ├── Runs game/main.py 100 times with different seeds
    ├── Collects results (win/loss, time, HP, kills)
    ├── Outputs statistics:
    │     Win rate: 72%
    │     Avg clear time: 38.5s
    │     Avg HP remaining: 45%
    │     Avg rooms explored: 6.2/7
    └── Flags if win rate is outside target range (60-80%)

tools/tune_difficulty.py
    │
    ├── Runs batch_test for each hero class
    ├── Adjusts monster HP/damage/speed if win rate off-target
    ├── Re-runs until all heroes have 60-80% win rate
    └── Outputs balanced stat values
```

## Next Implementation Steps
1. Add `--headless` mode (no pygame.display, just tick loop)
2. Add `--max-time` and `--seed` flags
3. Add structured JSON logging
4. Build batch_test.py runner
5. Build tune_difficulty.py auto-balancer

## Headless mode (implemented — design/06 phase 0)

```bash
.venv/bin/python3 -m game.main --headless --seed 1 --max-time 60 --hero 0 --map data/maps/northshire.json
# -> RESULT: TIMEOUT time=60.0s hp=430/430 kills=10 digest=31f54792fce7
./test.sh          # all tests (unit, architecture, determinism, golden runs)
./test.sh fast     # skip the slow headless runs
```

- No window/audio (SDL dummy drivers); simulated time advances 1/30 s per loop iteration with no sleeping.
- Implies `--auto` (throwaway hero, never touches real saves). `--max-time` is simulated seconds.
- Same seed => identical `digest` (hash of all hero/monster state). Golden results: `tests/golden/headless.json`;
  regenerate deliberately with `UPDATE_GOLDEN=1 .venv/bin/python3 -m unittest tests.test_headless`.
- Hero AI path caches now use game time instead of wall-clock (needed for determinism).
- Rendering still runs each iteration (to a dummy display); skipping it comes with phase 3 (view separation).

### Scripted input and command replays (design/06 phase 2)

```bash
# Drive the real mouse/keyboard code from a JSON script (see game/input_script.py), and record the commands:
.venv/bin/python3 -m game.main --headless --seed 11 --max-time 60 --hero 0 --map data/maps/northshire.json \
    --input-script tests/scripts/manual_fighter.json --record-commands /tmp/fighter.json
# Replay the command log through the pure simulation (no pygame) — same RESULT/digest:
.venv/bin/python3 -c "from game.engine import replay; print(replay.run_recording(replay.load_recording('/tmp/fighter.json')))"
```
If you change gameplay on purpose, regenerate goldens (`UPDATE_GOLDEN=1 ...`) and re-record tests/replays/ with the
commands in tests/test_replay.py's docstring.

### Co-op / network (design/06 phases 4-7)

- Standalone host: `.venv/bin/python3 -m game.net.server --map data/maps/northshire.json --hero 4` (add `--auto` for an AI-driven host hero).
- Join it: `.venv/bin/python3 -m game.main --connect 5577`, or press J on the map-select screen (H hosts the selected map).
- Headless host for tests: `.venv/bin/python3 -m game.main --headless --host-game --map data/maps/northshire.json --max-time 8`.

Everything listens on 127.0.0.1 only. tests/test_net.py covers TCP streaming, rejection of bad/garbage input,
exact convergence of client views (also through a 150 ms ±60 ms latency proxy, tests/latency_proxy.py),
two-player sessions, real host + client processes, and reconnect after a host restart.
