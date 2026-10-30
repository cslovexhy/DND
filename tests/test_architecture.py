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
    + [os.path.join(ROOT, "game", "client", n) for n in ("view.py", "local_host.py")]
)


def imported_modules(path):
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read())
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
            with open(path, encoding="utf-8") as f:
                src = f.read()
            for bad in ("time.time()", "time.monotonic()", "perf_counter()", "get_ticks()"):
                self.assertNotIn(bad, src, f"{os.path.relpath(path, ROOT)} calls {bad}")


class ClientReadsOnlySnapshotsTest(unittest.TestCase):
    def test_render_code_does_not_touch_the_simulation(self):
        """Everything after '# --- RENDER ---' in session.py draws from `view` (snapshots), never the sim."""
        with open(os.path.join(ROOT, "game", "session.py"), encoding="utf-8") as f:
            src = f.read()
        render = src[src.index("    # --- RENDER ---"):].split("\nif world.record_commands")[0]
        code = "\n".join(line.split("#")[0] for line in render.splitlines())   # ignore comments
        import re
        for bad in (r"(?<![\w.])world\.", r"(?<![\w.])game_state\.", r"(?<![\w.])player\.",
                    r"(?<![\w.])quests\.", r"(?<![\w.])projectiles\b", r"(?<![\w.])companions\b"):
            self.assertIsNone(re.search(bad, code), f"render code uses {bad}")


if __name__ == "__main__":
    unittest.main()
