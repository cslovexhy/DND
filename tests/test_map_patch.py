"""Diagonal wall gaps (two walls touching only at a corner, which players could walk through) are found and patched
on map save (map_editor.save_map -> engine/map_patch.py)."""
import glob
import json
import os
import unittest

from game.engine.map_patch import find_diagonal_gaps, patch_diagonal_gaps, walk_grid

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def make_map(rows, spawns=(), void="."):
    """rows: strings, '#' = wall, '.' = floor, ' ' = empty (no tile at all)."""
    h, w = len(rows), len(rows[0])
    ground = [[None if c == " " else {"col": 1, "row": 1, "walkable": c != "#"} for c in row] for row in rows]
    return {"width": w, "height": h,
            "layers": [{"name": "ground", "tiles": ground},
                       {"name": "objects", "tiles": [[None] * w for _ in range(h)]}],
            "spawns": [{"type": t, "x": x, "y": y} for t, x, y in spawns]}


def picture(m):
    return ["".join("." if ok else "#" for ok in row) for row in walk_grid(m)]


class FindTest(unittest.TestCase):
    def test_both_diagonals_are_gaps(self):
        self.assertEqual(find_diagonal_gaps(make_map(["#.", ".#"])), [(0, 0)])
        self.assertEqual(find_diagonal_gaps(make_map([".#", "#."])), [(0, 0)])

    def test_straight_walls_and_closed_corners_are_fine(self):
        for rows in (["##", ".."], ["#.", "#."], ["##", "#."], ["##", "##"], ["#.", ".."], ["..", ".."]):
            self.assertEqual(find_diagonal_gaps(make_map(rows)), [], rows)


class PatchTest(unittest.TestCase):
    def test_patches_until_none_are_left(self):
        m = make_map(["#....",
                      ".#...",
                      "..#..",
                      "...#."])      # a diagonal wall line: 3 gaps; patching can't create endless new ones
        patched, unfixable = patch_diagonal_gaps(m)
        self.assertEqual(unfixable, [])
        self.assertEqual(find_diagonal_gaps(m), [])
        self.assertEqual(len(patched), 3)

    def test_blocks_the_open_tile_touching_more_walls(self):
        m = make_map(["#....",
                      ".####",
                      "#####"])        # (0,1) touches 3 walls, (1,0) only 2
        patched, _ = patch_diagonal_gaps(m)
        self.assertEqual(patched, [(0, 1)])

    def test_never_blocks_a_spawn_or_npc_tile(self):
        m = make_map(["#.", ".#"], spawns=[("hero_start", 0, 1)])
        patched, _ = patch_diagonal_gaps(m)
        self.assertEqual(patched, [(1, 0)])
        m = make_map(["#.", ".#"], spawns=[("hero_start", 0, 1), ("snake", 1, 0)])
        patched, unfixable = patch_diagonal_gaps(m)
        self.assertEqual((patched, unfixable), ([], [(0, 0)]))   # reported, not patched

    def test_only_the_walkable_flag_changes(self):
        m = make_map(["#.", ".#"])
        (x, y), = patch_diagonal_gaps(m)[0]
        cell = m["layers"][0]["tiles"][y][x]
        self.assertEqual((cell["col"], cell["row"], cell["walkable"]), (1, 1, False))

    def test_empty_tile_gets_a_copy_of_the_wall(self):
        m = make_map(["# ", " #"])                    # open tiles have no art at all
        patched, _ = patch_diagonal_gaps(m)
        (x, y), = patched
        self.assertEqual(m["layers"][0]["tiles"][y][x], {"col": 1, "row": 1, "walkable": False})
        self.assertEqual(find_diagonal_gaps(m), [])


class ShippedMapsTest(unittest.TestCase):
    def test_no_shipped_map_has_diagonal_gaps(self):
        for f in sorted(glob.glob(os.path.join(ROOT, "data", "maps", "*.json"))):
            with open(f) as fh:
                self.assertEqual(find_diagonal_gaps(json.load(fh)), [], f)


if __name__ == "__main__":
    unittest.main()
