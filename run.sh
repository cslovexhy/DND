#!/bin/bash
# Launch DND ARPG with logging
# Usage: ./run.sh [--auto] [--hero 0-4]
# Log saved to /tmp/dnd_v1.log

cd "$(dirname "$0")"
rm -f /tmp/dnd_v1.log
python3 game/main.py "$@" > /tmp/dnd_v1.log 2>&1 &
echo "Game running (PID: $!) — log at /tmp/dnd_v1.log"
echo "  tail -f /tmp/dnd_v1.log  to watch"
echo "  kill $!  to stop"
