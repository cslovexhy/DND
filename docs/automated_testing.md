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
