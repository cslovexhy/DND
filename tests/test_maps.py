"""Map schema: upgrade, validation (maps are untrusted when they come from a co-op host), hashing,
and the editor keeping fields it doesn't edit."""
import copy
import glob
import json
import os
import unittest

from game.content.monsters import SPAWN_STATS
from game.engine.map_schema import (SCHEMA_VERSION, MapError, check_map, content_hash, upgrade_map,
                                    validate_map)
from game.engine.world_map import WorldMap

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def tiny_map():
    return {"width": 3, "height": 2,
            "layers": [{"name": "ground", "tiles": [[{"col": 1, "row": 2}, None, None], [None, None, None]]}],
            "spawns": [{"type": "hero_start", "x": 0, "y": 0}, {"type": "snake", "x": 2, "y": 1}]}


class MapSchemaTest(unittest.TestCase):
    def test_all_shipped_maps_are_valid(self):
        for f in sorted(glob.glob(os.path.join(ROOT, "data", "maps", "*.json"))):
            with open(f) as fh:
                errors, _ = validate_map(json.load(fh), set(SPAWN_STATS))
            self.assertEqual(errors, [], f)

    def test_v0_is_upgraded(self):
        m = tiny_map()
        upgrade_map(m)
        self.assertEqual(m["schema_version"], SCHEMA_VERSION)
        m["schema_version"] = SCHEMA_VERSION + 1
        with self.assertRaises(MapError):
            upgrade_map(m)

    def test_rejects_malicious_or_broken_maps(self):
        cases = {
            "huge": lambda m: m.update(width=10 ** 6),
            "rows": lambda m: m["layers"][0]["tiles"].pop(),
            "cell": lambda m: m["layers"][0]["tiles"][0].__setitem__(0, {"col": "x", "row": 0}),
            "spawn_oob": lambda m: m["spawns"].append({"type": "snake", "x": 99, "y": 0}),
            "no_start": lambda m: m.__setitem__("spawns", []),
            "music_abs": lambda m: m.__setitem__("music", ["/etc/passwd"]),
            "music_up": lambda m: m.__setitem__("music", ["assets/music/../../secret.mp3"]),
            "npc_bad": lambda m: m.__setitem__("npcs", [{"name": "x", "npc_id": 1, "x": 0, "y": 0}]),
            "not_obj": None,
        }
        for name, mutate in cases.items():
            with self.subTest(name):
                m = "nope" if mutate is None else tiny_map()
                if mutate:
                    mutate(m)
                errors, _ = validate_map(m)
                self.assertTrue(errors)
                if isinstance(m, dict):
                    with self.assertRaises(MapError):
                        WorldMap.from_data(m)

    def test_unknown_monster_is_a_warning(self):
        m = tiny_map()
        m["spawns"].append({"type": "dragon_god", "x": 1, "y": 1})
        errors, warnings = validate_map(m, set(SPAWN_STATS))
        self.assertEqual(errors, [])
        self.assertTrue(warnings)

    def test_music_under_assets_ok(self):
        m = tiny_map()
        m["music"] = ["assets/music/01. Legends of Azeroth.mp3"]
        self.assertEqual(validate_map(m)[0], [])

    def test_content_hash_ignores_key_order(self):
        a = tiny_map()
        b = json.loads(json.dumps(a, sort_keys=True))
        self.assertEqual(content_hash(a), content_hash(b))
        b["width"] = 4
        self.assertNotEqual(content_hash(a), content_hash(b))

    def test_from_data_builds_map(self):
        wm = WorldMap.from_data(check_map(tiny_map()))
        self.assertEqual((wm.width, wm.height, wm.hero_start), (3, 2, (0, 0)))


class EditorRoundTripTest(unittest.TestCase):
    def test_editor_keeps_npcs_music_and_zone_info(self):
        """MapData.to_dict(from_dict(x)) must not drop fields the editor doesn't edit (it used to lose NPCs)."""
        import ast
        with open(os.path.join(ROOT, "map_editor.py")) as f:
            src = f.read()
        tree = ast.parse(src)
        # Pull the MapLayer/MapData classes out of the editor (the module itself opens a window on import)
        classes = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name in ("MapLayer", "MapData")]
        ns = {"SCHEMA_VERSION": SCHEMA_VERSION, "DEFAULT_MAP_W": 40, "DEFAULT_MAP_H": 30, "deepcopy": copy.deepcopy}
        exec(compile(ast.Module(body=classes, type_ignores=[]), "map_editor", "exec"), ns)
        with open(os.path.join(ROOT, "data", "maps", "northshire.json")) as f:
            original = json.load(f)
        saved = ns["MapData"].from_dict(copy.deepcopy(original)).to_dict()
        for key in ("npcs", "music"):
            self.assertEqual(saved[key], original[key])
        self.assertEqual(saved["spawns"], original["spawns"])
        self.assertEqual(saved["schema_version"], SCHEMA_VERSION)
        self.assertEqual(validate_map(saved, set(SPAWN_STATS))[0], [])


if __name__ == "__main__":
    unittest.main()
