#!/bin/bash
# Launch DND ARPG
# Usage: ./run.sh [--map path/to/map.json] [--auto] [--hero 0-4] [--debug]
# Default: shows map select screen, then hero select
# Log saved to /tmp/dnd_v1.log

cd "$(dirname "$0")"
PYTHON=".venv/bin/python3"
if [ ! -x "$PYTHON" ]; then
  echo "ERROR: venv not found. Run: python3 -m venv .venv && .venv/bin/pip install pygame-ce"
  exit 1
fi
rm -f /tmp/dnd_v1.log
$PYTHON -m game.main "$@" > /tmp/dnd_v1.log 2>&1 &
echo "Game running (PID: $!) — log at /tmp/dnd_v1.log"
echo "  tail -f /tmp/dnd_v1.log  to watch"
echo "  kill $!  to stop"
