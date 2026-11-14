"""Map file schema: versioning, validation and content hashing (pure; no pygame).

Maps are plain JSON written by map_editor.py. Custom maps can travel over the network from a host to
joiners, so a map is treated as untrusted data: it is only ever parsed as JSON (never executed), and
validate_map() bounds-checks everything the game will index or load before it is used.

Schema history
  v0  (no "schema_version" key)  original editor format
  v1  adds "schema_version": 1. No structural change; v0 files are upgraded on load.
"""
import hashlib
import json
import posixpath

SCHEMA_VERSION = 1

MAX_SIDE = 400            # tiles per side
MAX_SHEET_INDEX = 4096    # spritesheet col/row
MAX_SPAWNS = 10000
MAX_NPCS = 200
MAX_TEXT = 80
MUSIC_DIR = "assets/music/"


class MapError(ValueError):
    pass


def upgrade_map(data):
    """Bring an older map dict up to SCHEMA_VERSION in place. Returns the dict."""
    v = data.get("schema_version", 0)
    if not isinstance(v, int) or v < 0:
        raise MapError("bad schema_version")
    if v > SCHEMA_VERSION:
        raise MapError(f"map needs a newer game (schema {v} > {SCHEMA_VERSION})")
    if v == 0:
        data["schema_version"] = 1
    return data


def _is_int(v, lo, hi):
    return isinstance(v, int) and not isinstance(v, bool) and lo <= v <= hi


def validate_map(data, known_spawn_types=None):
    """Return (errors, warnings). Errors make the map unusable; warnings are things the game ignores."""
    errors, warnings = [], []
    if not isinstance(data, dict):
        return ["map must be a JSON object"], warnings
    w, h = data.get("width"), data.get("height")
    if not (_is_int(w, 1, MAX_SIDE) and _is_int(h, 1, MAX_SIDE)):
        return [f"width/height must be integers 1..{MAX_SIDE}"], warnings
    if "tile_size" in data and not _is_int(data["tile_size"], 8, 256):
        errors.append("tile_size must be an integer 8..256")

    layers = data.get("layers", [])
    if not isinstance(layers, list) or len(layers) > 8:
        errors.append("layers must be a list (at most 8)")
        layers = []
    for li, layer in enumerate(layers):
        if not isinstance(layer, dict) or not isinstance(layer.get("name"), str):
            errors.append(f"layer {li}: needs a name")
            continue
        tiles = layer.get("tiles")
        if not isinstance(tiles, list) or len(tiles) != h or any(not isinstance(r, list) or len(r) != w for r in tiles):
            errors.append(f"layer {layer['name']!r}: tiles must be {h} rows of {w} cells")
            continue
        bad = 0
        for row in tiles:
            for cell in row:
                if cell is None:
                    continue
                if not (isinstance(cell, dict) and _is_int(cell.get("col"), 0, MAX_SHEET_INDEX)
                        and _is_int(cell.get("row"), 0, MAX_SHEET_INDEX)
                        and isinstance(cell.get("walkable", True), bool)):
                    bad += 1
        if bad:
            errors.append(f"layer {layer['name']!r}: {bad} malformed tile cell(s)")

    spawns = data.get("spawns", [])
    if not isinstance(spawns, list) or len(spawns) > MAX_SPAWNS:
        errors.append(f"spawns must be a list (at most {MAX_SPAWNS})")
        spawns = []
    has_start = False
    for i, sp in enumerate(spawns):
        if not (isinstance(sp, dict) and (_is_int(sp.get("type"), 1, 10**6) or (isinstance(sp.get("type"), str) and len(sp["type"]) <= MAX_TEXT))
                and _is_int(sp.get("x"), 0, w - 1) and _is_int(sp.get("y"), 0, h - 1)):
            errors.append(f"spawn {i}: needs a type and x/y inside the map")
            continue
        if sp["type"] == "hero_start":
            has_start = True
        elif known_spawn_types is not None and sp["type"] not in known_spawn_types:
            warnings.append(f"spawn {i}: unknown monster type {sp['type']!r} (ignored)")
    if not has_start:
        errors.append("no 'Hero Start' spawn point")

    npcs = data.get("npcs", [])
    if not isinstance(npcs, list) or len(npcs) > MAX_NPCS:
        errors.append(f"npcs must be a list (at most {MAX_NPCS})")
        npcs = []
    for i, n in enumerate(npcs):
        if not (isinstance(n, dict) and isinstance(n.get("name"), str) and len(n["name"]) <= MAX_TEXT
                and isinstance(n.get("npc_id"), str) and len(n["npc_id"]) <= MAX_TEXT
                and _is_int(n.get("x"), 0, w - 1) and _is_int(n.get("y"), 0, h - 1)
                and _is_int(n.get("sprite_col"), 0, MAX_SHEET_INDEX) and _is_int(n.get("sprite_row"), 0, MAX_SHEET_INDEX)
                and n.get("gender", "male") in ("male", "female")):
            errors.append(f"npc {i}: needs name, npc_id, x/y inside the map, sprite_col/row")
        elif not (n.get("role") is None
                  or (n["role"] == "trainer" and isinstance(n.get("trains"), str) and len(n["trains"]) <= MAX_TEXT)
                  or (n["role"] == "vendor" and isinstance(n.get("shop"), str) and len(n["shop"]) <= MAX_TEXT)):
            errors.append(f"npc {i}: role must be \"trainer\" (with \"trains\": class) or \"vendor\" "
                          f"(with \"shop\": kind)")

    music = data.get("music", [])
    if not isinstance(music, list) or len(music) > 50:
        errors.append("music must be a list of paths")
        music = []
    for track in music:
        # only files inside assets/music/, no absolute paths or ".." (a map must not point at other files)
        norm = posixpath.normpath(track) if isinstance(track, str) else ""
        if not (isinstance(track, str) and "\\" not in track and norm.startswith(MUSIC_DIR) and norm == track):
            errors.append(f"music track {track!r} must be a file under {MUSIC_DIR}")
    return errors, warnings


def check_map(data, known_spawn_types=None):
    """Upgrade + validate; raises MapError listing the problems. Returns the upgraded dict."""
    upgrade_map(data)
    errors, _ = validate_map(data, known_spawn_types)
    if errors:
        raise MapError("; ".join(errors[:5]) + (f" (+{len(errors) - 5} more)" if len(errors) > 5 else ""))
    return data


def content_hash(data):
    """Stable short hash of a map's content (key order and whitespace don't matter)."""
    canon = json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canon).hexdigest()[:16]
