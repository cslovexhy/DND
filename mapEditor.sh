#!/bin/bash
# Launch the Map Editor
cd "$(dirname "$0")"
PYTHON=".venv/bin/python3"
if [ ! -x "$PYTHON" ]; then
  echo "ERROR: venv not found. Run: python3 -m venv .venv && .venv/bin/pip install pygame-ce"
  exit 1
fi
$PYTHON map_editor.py "$@"
