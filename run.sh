#!/bin/bash
# Launch DND ARPG
# Usage: ./run.sh [--map path/to/map.json] [--auto] [--hero 0-4 (class)] [--debug]
# Default: character select (create/delete here), then map select. ESC steps back.
# First run on a new computer sets up .venv and installs pygame-ce (same as run.bat on Windows).
# Each launch logs to its own file, /tmp/dnd_<time>_<pid>.log (two windows on one computer keep separate logs);
# /tmp/dnd_v1.log always points to the newest one.

cd "$(dirname "$0")"
PYTHON=".venv/bin/python3"
PYGAME="pygame-ce==2.5.7"   # keep in sync with run.bat: every computer in a co-op game runs the same version
if [ ! -x "$PYTHON" ]; then
  echo "Setting up the game (first run)..."
  if ! command -v python3 >/dev/null 2>&1; then
    echo "ERROR: python3 not found. Install Python 3 from https://www.python.org/downloads/ and run again."
    exit 1
  fi
  python3 -m venv .venv || { echo "ERROR: could not create .venv"; exit 1; }
  .venv/bin/pip install "$PYGAME" || { echo "ERROR: could not install $PYGAME"; exit 1; }
  echo "Setup complete."
fi
LOG="/tmp/dnd_$(date +%Y%m%d-%H%M%S)_$$.log"
$PYTHON -m game.main "$@" > "$LOG" 2>&1 &
ln -sf "$LOG" /tmp/dnd_v1.log
echo "Game running (PID: $!) — log at $LOG"
echo "  tail -f $LOG  to watch"
echo "  kill $!  to stop"
