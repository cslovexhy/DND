#!/bin/bash
# Launch DND ARPG
# Usage: ./run.sh [--map path/to/map.json] [--auto] [--hero 0-4] [--debug]
# Default: shows map select screen, then hero select
# Log saved to /tmp/dnd_v1.log

cd "$(dirname "$0")"
rm -f /tmp/dnd_v1.log
python3 -m game.main "$@" > /tmp/dnd_v1.log 2>&1 &
echo "Game running (PID: $!) — log at /tmp/dnd_v1.log"
echo "  tail -f /tmp/dnd_v1.log  to watch"
echo "  kill $!  to stop"
