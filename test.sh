#!/bin/bash
# Run all tests (headless, no window). Usage: ./test.sh [fast]
#   fast = skip the slow headless golden/determinism runs
cd "$(dirname "$0")"
PYTHON=".venv/bin/python3"
[ -x "$PYTHON" ] || PYTHON=python3
if [ "$1" = "fast" ]; then
  exec $PYTHON -m unittest tests.test_progression_saves_quests tests.test_architecture tests.test_headless.HeadlessUnitTest
fi
exec $PYTHON -m unittest discover -s tests -t . "$@"
