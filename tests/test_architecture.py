"""Architecture-fitness tests: keep the simulation layer free of pygame (see design/06).

Modules listed in PURE must be importable with pygame uninstalled, so they can later run
on a headless server. Add modules here as they are extracted from session.py.
"""
import ast
import glob
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PURE = (
    glob.glob(os.path.join(ROOT, "game", "engine", "*.py"))
    + [os.path.join(ROOT, "game", n) for n in ("headless.py", "progression.py", "saves.py", "quests.py")]
    + glob.glob(os.path.join(ROOT, "game", "content", "*.py"))
)


def imported_modules(path):
    tree = ast.parse(open(path, encoding="utf-8").read())
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                yield a.name
        elif isinstance(node, ast.ImportFrom) and node.module:
            yield node.module


class PureLayerTest(unittest.TestCase):
    def test_pure_modules_do_not_import_pygame(self):
        self.assertTrue(PURE)
        for path in PURE:
            for mod in imported_modules(path):
                self.assertNotEqual(mod.split(".")[0], "pygame",
                                    f"{os.path.relpath(path, ROOT)} imports {mod}")

    def test_pure_modules_do_not_use_wall_clock(self):
        # Simulation code must take time from the game clock, never time.time()/monotonic() calls
        # (hero_ai keeps time.monotonic only as an injectable default).
        for path in PURE:
            src = open(path, encoding="utf-8").read()
            for bad in ("time.time()", "time.monotonic()", "perf_counter()", "get_ticks()"):
                self.assertNotIn(bad, src, f"{os.path.relpath(path, ROOT)} calls {bad}")


if __name__ == "__main__":
    unittest.main()
