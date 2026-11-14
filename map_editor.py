"""
Map Editor — Paint sub-maps using Kenney Roguelike RPG spritesheet tiles.
Run: python3 map_editor.py

Controls:
  Left-click: Paint tile
  Right-click: Erase tile
  Middle-click drag / WASD: Pan canvas
  Scroll wheel: Zoom in/out
  Ctrl+Z: Undo
  Ctrl+Shift+Z: Redo
  F: Fill tool toggle
  W: Walkability overlay toggle
  1/2: Switch layers (ground/objects)
  3: Spawn palette (every monster type the game knows; * = custom)   4: Location markers
  M: Monster types — create custom monsters (picture, level range on this map, skills, drops, ...)
  Ctrl+S: Save
  Ctrl+O: Load
"""
import pygame
import json
import math
import os
import sys
from copy import deepcopy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from game.engine.map_schema import SCHEMA_VERSION, validate_map   # noqa: E402  (pure, no pygame)
from game.engine.map_patch import patch_diagonal_gaps   # noqa: E402  (pure, no pygame)
from game.content import monster_defs                               # noqa: E402  (data/monsters.json)
KNOWN_SPAWN_TYPES = set()

pygame.init()

# === CONSTANTS ===
SCREEN_W, SCREEN_H = 1400, 900
PALETTE_W = 250  # Left panel width
TOOLBAR_H = 40   # Top toolbar height
TILE_SRC = 16
TILE_MARGIN = 1
SPRITESHEET_PATH = "assets/kenney_rpg/Spritesheet/roguelikeSheet_transparent.png"

# Spritesheet dimensions: 968x526, 16x16 tiles with 1px margin
SHEET_COLS = 57
SHEET_ROWS = 31

# Default canvas
DEFAULT_MAP_W = 40
DEFAULT_MAP_H = 30

# Colors
COL_BG = (30, 30, 30)
COL_PANEL = (45, 45, 50)
COL_TOOLBAR = (55, 55, 60)
COL_GRID = (60, 60, 65)
COL_SELECTED = (255, 255, 0)
COL_HOVER = (255, 255, 255, 100)
COL_WALKABLE = (0, 200, 0, 80)
COL_BLOCKED = (200, 0, 0, 80)
COL_TEXT = (220, 220, 220)
COL_BUTTON = (70, 70, 80)
COL_BUTTON_HOVER = (90, 90, 100)
COL_BUTTON_ACTIVE = (100, 150, 100)

# === SETUP ===
screen = pygame.display.set_mode((SCREEN_W, SCREEN_H), pygame.RESIZABLE)
pygame.display.set_caption("Map Editor — Kenney Roguelike RPG")
clock = pygame.time.Clock()

# Load spritesheet
sheet_img = pygame.image.load(SPRITESHEET_PATH).convert_alpha()
from game.editor import story_panel                                 # noqa: E402
from game import quests as quests_mod                              # noqa: E402
from game.editor import monster_panel                               # noqa: E402  (needs the display for images)

font = pygame.font.SysFont("monospace", 13)
font_sm = pygame.font.SysFont("monospace", 11)


def get_tile_surface(col, row):
    """Extract a 16x16 tile from the spritesheet."""
    x = col * (TILE_SRC + TILE_MARGIN)
    y = row * (TILE_SRC + TILE_MARGIN)
    s = pygame.Surface((TILE_SRC, TILE_SRC), pygame.SRCALPHA)
    s.blit(sheet_img, (0, 0), (x, y, TILE_SRC, TILE_SRC))
    return s


# Pre-cache all tiles
tile_cache = {}
for r in range(SHEET_ROWS):
    for c in range(SHEET_COLS):
        tile_cache[(c, r)] = get_tile_surface(c, r)


# === DATA MODEL ===
class MapLayer:
    def __init__(self, name, width, height):
        self.name = name
        self.width = width
        self.height = height
        # Each cell: None or {"col": int, "row": int, "walkable": bool}
        self.tiles = [[None for _ in range(width)] for _ in range(height)]

    def set_tile(self, x, y, col, row, walkable=True):
        if 0 <= x < self.width and 0 <= y < self.height:
            self.tiles[y][x] = {"col": col, "row": row, "walkable": walkable}

    def clear_tile(self, x, y):
        if 0 <= x < self.width and 0 <= y < self.height:
            self.tiles[y][x] = None

    def get_tile(self, x, y):
        if 0 <= x < self.width and 0 <= y < self.height:
            return self.tiles[y][x]
        return None


class MapData:
    def __init__(self, width=DEFAULT_MAP_W, height=DEFAULT_MAP_H):
        self.width = width
        self.height = height
        self.layers = [
            MapLayer("ground", width, height),
            MapLayer("objects", width, height),
        ]
        self.spawns = []  # [{"type": 1, "x": 12, "y": 8}, ...]
        # Fields the editor doesn't edit (npcs, music, zone info, ...) are kept and written back unchanged
        self.extra = {}

    def add_spawn(self, spawn_type, x, y):
        # Remove existing spawn at same position
        self.spawns = [s for s in self.spawns if not (s["x"] == x and s["y"] == y)]
        self.spawns.append({"type": spawn_type, "x": x, "y": y})

    def remove_spawn(self, x, y):
        self.spawns = [s for s in self.spawns if not (s["x"] == x and s["y"] == y)]

    def get_spawn_at(self, x, y):
        for s in self.spawns:
            if s["x"] == x and s["y"] == y:
                return s
        return None

    def to_dict(self):
        return {
            **self.extra,
            "schema_version": SCHEMA_VERSION,
            "width": self.width,
            "height": self.height,
            "tileset": "kenney_rpg",
            "layers": [
                {
                    "name": layer.name,
                    "tiles": layer.tiles
                }
                for layer in self.layers
            ],
            "spawns": self.spawns
        }

    @classmethod
    def from_dict(cls, data):
        m = cls(data["width"], data["height"])
        for i, layer_data in enumerate(data["layers"]):
            if i < len(m.layers):
                m.layers[i].name = layer_data["name"]
                m.layers[i].tiles = layer_data["tiles"]
            else:
                layer = MapLayer(layer_data["name"], m.width, m.height)
                layer.tiles = layer_data["tiles"]
                m.layers.append(layer)
        m.spawns = data.get("spawns", [])
        m.extra = {k: v for k, v in data.items()
                   if k not in ("width", "height", "tileset", "layers", "spawns", "schema_version")}
        return m


# === UNDO SYSTEM ===
class UndoStack:
    def __init__(self, max_size=200):
        self.undo_stack = []
        self.redo_stack = []
        self.max_size = max_size

    def push(self, action):
        """action = {"layer": int, "x": int, "y": int, "old": tile_or_None, "new": tile_or_None}"""
        self.undo_stack.append(action)
        if len(self.undo_stack) > self.max_size:
            self.undo_stack.pop(0)
        self.redo_stack.clear()

    def push_batch(self, actions):
        """Push a batch of actions as one undo step."""
        if actions:
            self.undo_stack.append(actions)
            if len(self.undo_stack) > self.max_size:
                self.undo_stack.pop(0)
            self.redo_stack.clear()

    def undo(self, map_data):
        if not self.undo_stack:
            return
        action = self.undo_stack.pop()
        if isinstance(action, list):
            for a in reversed(action):
                map_data.layers[a["layer"]].tiles[a["y"]][a["x"]] = a["old"]
            self.redo_stack.append(action)
        else:
            map_data.layers[action["layer"]].tiles[action["y"]][action["x"]] = action["old"]
            self.redo_stack.append(action)

    def redo(self, map_data):
        if not self.redo_stack:
            return
        action = self.redo_stack.pop()
        if isinstance(action, list):
            for a in action:
                map_data.layers[a["layer"]].tiles[a["y"]][a["x"]] = a["new"]
            self.undo_stack.append(action)
        else:
            map_data.layers[action["layer"]].tiles[action["y"]][action["x"]] = action["new"]
            self.undo_stack.append(action)


# === FILL TOOL ===
def flood_fill(map_data, layer_idx, start_x, start_y, new_tile):
    """Flood fill from (start_x, start_y) with new_tile. Returns list of actions."""
    layer = map_data.layers[layer_idx]
    target = deepcopy(layer.get_tile(start_x, start_y))
    new_t = deepcopy(new_tile)

    # Don't fill if same
    if target == new_t:
        return []

    actions = []
    stack = [(start_x, start_y)]
    visited = set()

    while stack:
        x, y = stack.pop()
        if (x, y) in visited:
            continue
        if x < 0 or x >= layer.width or y < 0 or y >= layer.height:
            continue
        current = layer.get_tile(x, y)
        if current != target:
            continue

        visited.add((x, y))
        old = deepcopy(current)
        layer.tiles[y][x] = deepcopy(new_t)
        actions.append({"layer": layer_idx, "x": x, "y": y, "old": old, "new": deepcopy(new_t)})

        stack.extend([(x+1, y), (x-1, y), (x, y+1), (x, y-1)])

    return actions


# === EDITOR STATE ===
map_data = MapData()
undo_stack = UndoStack()

# View state
cam_x, cam_y = 0.0, 0.0  # Camera offset in pixels
zoom = 2.0  # Tile render scale
min_zoom, max_zoom = 0.5, 6.0


def reset_camera_to_top_left():
    """Position camera so map top-left aligns with canvas top-left."""
    global cam_x, cam_y
    canvas_w = SCREEN_W - PALETTE_W
    canvas_h = SCREEN_H - TOOLBAR_H
    # The rendering formula is: sx = canvas_cx + (tx * tile_render_size) - cam_x * zoom
    # For tile (0,0) to appear at the canvas top-left (PALETTE_W, TOOLBAR_H):
    #   canvas_cx + 0 - cam_x * zoom = 0  (relative to canvas start)
    # canvas_cx is canvas_w / 2, so cam_x * zoom = canvas_w / 2
    # cam_x = canvas_w / (2 * zoom)
    cam_x = canvas_w / (2.0 * zoom)
    cam_y = canvas_h / (2.0 * zoom)


reset_camera_to_top_left()

# Tool state
selected_tile = (8, 10)  # Default brush (the floor tile you liked)
current_layer = 0
show_walkability = False
fill_mode = False
sample_mode = False  # Eyedropper: click tile on canvas to select it
spawn_mode = False     # When true, palette shows spawn types (monsters) instead of tiles
location_mode = False  # When true, palette shows location types (hero_start, connections)
painting = False  # Is left mouse held down?
erasing = False   # Is right mouse held down?
panning = False   # Is middle mouse held down?
walk_painting = False  # Walkability drag mode
walk_paint_value = False  # Target walkability value during drag
pan_start = (0, 0)
cam_start = (0, 0)

# Spawn types
LOCATION_TYPES = [
    # Special markers
    {"id": "hero_start", "name": "Hero Start", "color": (0, 200, 255)},
    {"id": "chest", "name": "Chest", "color": (255, 200, 0)},
    {"id": "npc", "name": "NPC", "color": (100, 255, 100)},
    # Connection points (map transitions)
] + [{"id": f"connection_{chr(97+i)}", "name": f"Connection {chr(65+i)}", "color": (255, 255, 0)} for i in range(26)]

SPAWN_TYPES = []   # built from the game's monster types (+ custom ones): refresh_spawn_types()


def refresh_spawn_types():
    """The spawn palette: every monster type in data/monsters.json (the Monsters screen, M, edits them). Rebuilt in
    place, so code holding SPAWN_TYPES / ALL_SPAWN_TYPES sees the change."""
    SPAWN_TYPES[:] = monster_panel.spawn_palette(defs)
    ALL_SPAWN_TYPES[:] = LOCATION_TYPES + SPAWN_TYPES
    KNOWN_SPAWN_TYPES.clear()
    KNOWN_SPAWN_TYPES.update(defs)


defs = monster_defs.load()      # every monster type (data/monsters.json)
monster_art = monster_panel.Art()

# Combined list for rendering (lookup by id)
ALL_SPAWN_TYPES = []
refresh_spawn_types()

selected_spawn = 0  # Index into active palette (SPAWN_TYPES or LOCATION_TYPES)

# Palette state
palette_scroll = 0
palette_tile_size = 20  # Display size in palette

# Current stroke batch (for undo grouping)
current_stroke = []

# Save/load
save_dir = "data/maps"
os.makedirs(save_dir, exist_ok=True)


# === RENDERING ===
def draw_toolbar():
    """Draw top toolbar with buttons."""
    pygame.draw.rect(screen, COL_TOOLBAR, (0, 0, SCREEN_W, TOOLBAR_H))

    buttons = []
    bx = 10
    btn_labels = [
        ("Save (Ctrl+S)", "save"),
        ("Load (Ctrl+O)", "load"),
        ("Undo (Ctrl+Z)", "undo"),
        ("Redo (Ctrl+Shift+Z)", "redo"),
        ("Fill (F)", "fill"),
        ("Sample (E)", "sample"),
        ("Walkability (W)", "walk"),
        ("Spawns (3)", "spawns"),
        ("Locations (4)", "locations"),
        ("Monsters (M)", "monsters"),
        ("Quests & NPCs (Q)", "story"),
    ]
    for label, action in btn_labels:
        tw = font.size(label)[0] + 16
        rect = pygame.Rect(bx, 6, tw, 28)
        active = (action == "fill" and fill_mode) or (action == "walk" and show_walkability) or (action == "spawns" and spawn_mode) or (action == "locations" and location_mode) or (action == "sample" and sample_mode)
        hovered = rect.collidepoint(pygame.mouse.get_pos())
        color = COL_BUTTON_ACTIVE if active else (COL_BUTTON_HOVER if hovered else COL_BUTTON)
        pygame.draw.rect(screen, color, rect, border_radius=4)
        txt = font.render(label, True, COL_TEXT)
        screen.blit(txt, (bx + 8, 12))
        buttons.append((rect, action))
        bx += tw + 6

    # Mode indicator
    if sample_mode:
        mode_text = "SAMPLE MODE — Click a tile to pick it"
    elif spawn_mode:
        mode_text = f"SPAWN MODE — {SPAWN_TYPES[selected_spawn]['name']}"
    elif location_mode:
        mode_text = f"LOCATION MODE — {LOCATION_TYPES[selected_spawn]['name']}"
    elif placing_npc:
        npc = next((n for n in map_data.extra.get("npcs", []) if n["npc_id"] == placing_npc), None)
        mode_text = f"PLACING {npc['name'] if npc else placing_npc} - click a tile (Esc cancels)"
    else:
        mode_text = f"Layer: {map_data.layers[current_layer].name} [{current_layer+1}/{len(map_data.layers)}]"
    lt = font.render(mode_text, True, COL_TEXT)
    screen.blit(lt, (SCREEN_W - lt.get_width() - 10, 12))

    return buttons


def draw_palette():
    """Draw tile palette or spawn palette on the left panel."""
    panel_rect = pygame.Rect(0, TOOLBAR_H, PALETTE_W, SCREEN_H - TOOLBAR_H)
    pygame.draw.rect(screen, COL_PANEL, panel_rect)
    mx, my = pygame.mouse.get_pos()

    if spawn_mode or location_mode:
        # === SPAWN / LOCATION PALETTE ===
        active_list = SPAWN_TYPES if spawn_mode else LOCATION_TYPES
        title_text = "Spawn Palette" if spawn_mode else "Location Palette"
        title = font.render(title_text, True, COL_TEXT)
        screen.blit(title, (8, TOOLBAR_H + 5))

        # Selected item preview
        sp = active_list[selected_spawn]
        if sp.get("art"):
            screen.blit(monster_art.monster(sp["art"], 28), (16, TOOLBAR_H + 31))
        else:
            pygame.draw.circle(screen, sp["color"], (30, TOOLBAR_H + 45), 12)
        name_text = font_sm.render(sp["name"], True, COL_TEXT)
        screen.blit(name_text, (50, TOOLBAR_H + 38))
        if spawn_mode:
            hint = font_sm.render("M: edit monster types", True, (150, 150, 150))
            screen.blit(hint, (8, TOOLBAR_H + 56))

        # List all types
        list_top = TOOLBAR_H + 70
        clicked_spawn = None
        for i, sp in enumerate(active_list):
            iy = list_top + i * 26
            if iy + 24 > SCREEN_H:
                break
            rect = pygame.Rect(8, iy, PALETTE_W - 16, 24)
            hovered = rect.collidepoint(mx, my)
            if i == selected_spawn:
                pygame.draw.rect(screen, (70, 90, 70), rect, border_radius=3)
            elif hovered:
                pygame.draw.rect(screen, (60, 60, 70), rect, border_radius=3)
            # Picture (monsters) or colour dot (locations)
            if sp.get("art"):
                screen.blit(monster_art.monster(sp["art"], 20), (12, iy + 2))
            else:
                pygame.draw.circle(screen, sp["color"], (22, iy + 12), 7)
            # Name
            nt = font_sm.render(sp["name"], True, COL_TEXT)
            screen.blit(nt, (36, iy + 5))
            # Check click
            if hovered and panel_rect.collidepoint(mx, my):
                clicked_spawn = i

        return clicked_spawn, 0, 0
    else:
        # === TILE PALETTE ===
        title = font.render("Tile Palette", True, COL_TEXT)
        screen.blit(title, (8, TOOLBAR_H + 5))

        # Selected tile preview
        preview_size = 48
        preview = pygame.transform.scale(tile_cache[selected_tile], (preview_size, preview_size))
        px, py = 8, TOOLBAR_H + 25
        screen.blit(preview, (px, py))
        pygame.draw.rect(screen, COL_SELECTED, (px-1, py-1, preview_size+2, preview_size+2), 2)
        coord_text = font_sm.render(f"({selected_tile[0]}, {selected_tile[1]})", True, COL_TEXT)
        screen.blit(coord_text, (px + preview_size + 8, py + 16))

        # Tile grid
        grid_top = TOOLBAR_H + 80
        cols_fit = (PALETTE_W - 16) // (palette_tile_size + 2)
        rows_visible = (SCREEN_H - grid_top - 10) // (palette_tile_size + 2)

        total_tiles = SHEET_COLS * SHEET_ROWS
        total_rows = (total_tiles + cols_fit - 1) // cols_fit

        clicked_tile = None

        for vis_row in range(rows_visible + 1):
            actual_row = vis_row + palette_scroll
            if actual_row >= total_rows:
                break
            for col in range(cols_fit):
                tile_idx = actual_row * cols_fit + col
                if tile_idx >= total_tiles:
                    break
                tc = tile_idx % SHEET_COLS
                tr = tile_idx // SHEET_COLS

                tx = 8 + col * (palette_tile_size + 2)
                ty = grid_top + vis_row * (palette_tile_size + 2)

                if ty + palette_tile_size > SCREEN_H:
                    break

                scaled = pygame.transform.scale(tile_cache[(tc, tr)], (palette_tile_size, palette_tile_size))
                screen.blit(scaled, (tx, ty))

                if (tc, tr) == selected_tile:
                    pygame.draw.rect(screen, COL_SELECTED, (tx-1, ty-1, palette_tile_size+2, palette_tile_size+2), 2)

                if panel_rect.collidepoint(mx, my):
                    tile_rect = pygame.Rect(tx, ty, palette_tile_size, palette_tile_size)
                    if tile_rect.collidepoint(mx, my):
                        pygame.draw.rect(screen, (255, 255, 255), (tx-1, ty-1, palette_tile_size+2, palette_tile_size+2), 1)
                        clicked_tile = (tc, tr)

        return clicked_tile, total_rows, rows_visible


def draw_canvas():
    """Draw the map canvas with current tiles."""
    canvas_rect = pygame.Rect(PALETTE_W, TOOLBAR_H, SCREEN_W - PALETTE_W, SCREEN_H - TOOLBAR_H)
    pygame.draw.rect(screen, COL_BG, canvas_rect)

    tile_render_size = int(TILE_SRC * zoom)

    # Visible range
    canvas_cx = canvas_rect.x + canvas_rect.width // 2
    canvas_cy = canvas_rect.y + canvas_rect.height // 2

    for ty in range(map_data.height):
        for tx in range(map_data.width):
            # Screen position
            sx = int(canvas_cx + (tx * tile_render_size) - cam_x * zoom)
            sy = int(canvas_cy + (ty * tile_render_size) - cam_y * zoom)

            # Cull off-screen
            if sx + tile_render_size < canvas_rect.x or sx > canvas_rect.right:
                continue
            if sy + tile_render_size < canvas_rect.y or sy > canvas_rect.bottom:
                continue

            # Draw each visible layer
            has_tile = False
            for li, layer in enumerate(map_data.layers):
                if li > current_layer and not show_walkability:
                    break  # Only show up to current layer (or all in walkability mode)
                cell = layer.tiles[ty][tx]
                if cell:
                    tile_surf = tile_cache.get((cell["col"], cell["row"]))
                    if tile_surf:
                        scaled = pygame.transform.scale(tile_surf, (tile_render_size, tile_render_size))
                        screen.blit(scaled, (sx, sy))
                        has_tile = True

            # Grid lines
            if zoom >= 1.5:
                pygame.draw.rect(screen, COL_GRID, (sx, sy, tile_render_size, tile_render_size), 1)

            # Walkability overlay
            if show_walkability and has_tile:
                # Check the topmost tile's walkability
                walkable = True
                for layer in reversed(map_data.layers):
                    cell = layer.tiles[ty][tx]
                    if cell:
                        walkable = cell.get("walkable", True)
                        break
                overlay = pygame.Surface((tile_render_size, tile_render_size), pygame.SRCALPHA)
                overlay.fill(COL_WALKABLE if walkable else COL_BLOCKED)
                screen.blit(overlay, (sx, sy))

    # Draw spawn markers
    for spawn in map_data.spawns:
        sx = int(canvas_cx + (spawn["x"] * tile_render_size) - cam_x * zoom)
        sy = int(canvas_cy + (spawn["y"] * tile_render_size) - cam_y * zoom)
        if sx + tile_render_size < canvas_rect.x or sx > canvas_rect.right:
            continue
        if sy + tile_render_size < canvas_rect.y or sy > canvas_rect.bottom:
            continue
        # Find color for this spawn type
        sp_color = (255, 255, 255)
        sp_name = spawn["type"]
        for sp in ALL_SPAWN_TYPES:
            if sp["id"] == spawn["type"]:
                sp_color = sp["color"]
                sp_name = sp["name"]
                break
        # Draw colored diamond marker (monsters: their picture)
        center_x = sx + tile_render_size // 2
        center_y = sy + tile_render_size // 2
        r = max(6, tile_render_size // 3)
        sp_art = next((sp.get("art") for sp in ALL_SPAWN_TYPES if sp["id"] == spawn["type"]), None)
        if sp_art and tile_render_size >= 12:
            screen.blit(monster_art.monster(sp_art, tile_render_size), (sx, sy))
            continue
        points = [(center_x, center_y - r), (center_x + r, center_y),
                  (center_x, center_y + r), (center_x - r, center_y)]
        pygame.draw.polygon(screen, sp_color, points)
        pygame.draw.polygon(screen, (255, 255, 255), points, 1)
        # Show letter on connection points and "H" on hero_start (always visible)
        spawn_id = spawn["type"]
        if isinstance(spawn_id, str) and spawn_id.startswith("connection_"):
            letter = spawn_id[-1].upper()
            letter_surf = font_sm.render(letter, True, (0, 0, 0))
            lr = letter_surf.get_rect(center=(center_x, center_y))
            screen.blit(letter_surf, lr)
        elif spawn_id == "hero_start":
            letter_surf = font_sm.render("H", True, (0, 0, 0))
            lr = letter_surf.get_rect(center=(center_x, center_y))
            screen.blit(letter_surf, lr)
        # Label (only if zoomed in enough)
        if zoom >= 2.0:
            label = font_sm.render(sp_name[:10], True, (255, 255, 255))
            screen.blit(label, (sx + 2, sy + tile_render_size - 12))

    # NPCs (their picture; the one being placed is outlined)
    for npc in map_data.extra.get("npcs", []):
        sx = int(canvas_cx + (npc["x"] * tile_render_size) - cam_x * zoom)
        sy = int(canvas_cy + (npc["y"] * tile_render_size) - cam_y * zoom)
        if not canvas_rect.colliderect(pygame.Rect(sx, sy, tile_render_size, tile_render_size)):
            continue
        art = {"sheet": "dungeon", "col": npc.get("sprite_col", 0), "row": npc.get("sprite_row", 0)}
        screen.blit(monster_art.monster(art, max(8, tile_render_size)), (sx, sy))
        pygame.draw.rect(screen, (100, 255, 100) if npc["npc_id"] != placing_npc else (255, 220, 0),
                         (sx, sy, tile_render_size, tile_render_size), 1)
        if tile_render_size >= 20:
            screen.blit(font_sm.render(npc["name"][:14], True, (200, 255, 200)), (sx, sy - 12))

    # Highlight hovered tile
    mx, my = pygame.mouse.get_pos()
    if canvas_rect.collidepoint(mx, my):
        # Convert mouse to tile coords
        rel_x = (mx - canvas_cx) / zoom + cam_x
        rel_y = (my - canvas_cy) / zoom + cam_y
        hover_tx = int(rel_x // TILE_SRC)
        hover_ty = int(rel_y // TILE_SRC)
        if 0 <= hover_tx < map_data.width and 0 <= hover_ty < map_data.height:
            hsx = int(canvas_cx + (hover_tx * tile_render_size) - cam_x * zoom)
            hsy = int(canvas_cy + (hover_ty * tile_render_size) - cam_y * zoom)
            pygame.draw.rect(screen, (255, 255, 255), (hsx, hsy, tile_render_size, tile_render_size), 2)

            # Status bar info
            info = f"Tile: ({hover_tx}, {hover_ty})"
            cell = map_data.layers[current_layer].tiles[hover_ty][hover_tx]
            if cell:
                info += f"  Sprite: ({cell['col']}, {cell['row']})  Walk: {cell.get('walkable', True)}"
            spawn_here = map_data.get_spawn_at(hover_tx, hover_ty)
            if spawn_here:
                info += f"  SPAWN: {spawn_here['type']}"
            info_surf = font_sm.render(info, True, COL_TEXT)
            screen.blit(info_surf, (PALETTE_W + 10, SCREEN_H - 20))


def screen_to_tile(mx, my):
    """Convert screen coords to map tile coords."""
    canvas_rect = pygame.Rect(PALETTE_W, TOOLBAR_H, SCREEN_W - PALETTE_W, SCREEN_H - TOOLBAR_H)
    if not canvas_rect.collidepoint(mx, my):
        return None, None
    canvas_cx = canvas_rect.x + canvas_rect.width // 2
    canvas_cy = canvas_rect.y + canvas_rect.height // 2
    rel_x = (mx - canvas_cx) / zoom + cam_x
    rel_y = (my - canvas_cy) / zoom + cam_y
    tx = int(rel_x // TILE_SRC)
    ty = int(rel_y // TILE_SRC)
    if 0 <= tx < map_data.width and 0 <= ty < map_data.height:
        return tx, ty
    return None, None


def paint_tile(tx, ty):
    """Paint current selected tile at position. Returns action or None."""
    layer = map_data.layers[current_layer]
    old = deepcopy(layer.get_tile(tx, ty))
    new_tile = {"col": selected_tile[0], "row": selected_tile[1], "walkable": True}
    if old == new_tile:
        return None
    layer.tiles[ty][tx] = new_tile
    return {"layer": current_layer, "x": tx, "y": ty, "old": old, "new": deepcopy(new_tile)}


def erase_tile(tx, ty):
    """Erase tile at position. Returns action or None."""
    layer = map_data.layers[current_layer]
    old = deepcopy(layer.get_tile(tx, ty))
    if old is None:
        return None
    layer.tiles[ty][tx] = None
    return {"layer": current_layer, "x": tx, "y": ty, "old": old, "new": None}


def text_input_prompt(title="Filename:", default="", allow_click_select=False, list_files=True, max_len=40):
    """Show a text input dialog in the center of screen. Returns string or None if cancelled.
    If allow_click_select=True, existing files are clickable to auto-select. list_files=False: a plain prompt (no
    map files listed)."""
    input_text = default
    cursor_blink = 0
    prompt_font = pygame.font.SysFont("monospace", 18)
    title_font = pygame.font.SysFont("monospace", 14)
    existing = (sorted([f for f in os.listdir(save_dir) if f.endswith(".json")])
                if list_files and os.path.exists(save_dir) else [])
    hovered_file = None

    while True:
        hovered_file = None
        mx, my = pygame.mouse.get_pos()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return None
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_RETURN:
                    return input_text if input_text else None
                elif event.key == pygame.K_ESCAPE:
                    return None
                elif event.key == pygame.K_BACKSPACE:
                    input_text = input_text[:-1]
                else:
                    ch = event.unicode
                    if ch and ch.isprintable() and len(input_text) < max_len:
                        input_text += ch
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and allow_click_select:
                # Check if a file entry was clicked
                if existing:
                    box_w = 450
                    box_h = min(200 + len(existing) * 28, 500)
                    box_x = (SCREEN_W - box_w) // 2
                    box_y = (SCREEN_H - box_h) // 2
                    list_y = box_y + 110 + 20
                    for fname in existing[:14]:
                        frect = pygame.Rect(box_x + 16, list_y, box_w - 32, 26)
                        if frect.collidepoint(event.pos):
                            return fname.replace(".json", "")
                        list_y += 28

        overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 150))
        screen.blit(overlay, (0, 0))

        box_w = 450
        box_h = min(200 + len(existing) * 28, 500)
        box_x = (SCREEN_W - box_w) // 2
        box_y = (SCREEN_H - box_h) // 2
        pygame.draw.rect(screen, (50, 50, 55), (box_x, box_y, box_w, box_h), border_radius=8)
        pygame.draw.rect(screen, (100, 100, 110), (box_x, box_y, box_w, box_h), 2, border_radius=8)

        t = title_font.render(title, True, COL_TEXT)
        screen.blit(t, (box_x + 20, box_y + 15))

        cursor_blink = (cursor_blink + 1) % 60
        field_rect = pygame.Rect(box_x + 20, box_y + 45, box_w - 40, 32)
        pygame.draw.rect(screen, (30, 30, 35), field_rect, border_radius=4)
        pygame.draw.rect(screen, (120, 120, 130), field_rect, 1, border_radius=4)
        display_text = (input_text[-38:] if len(input_text) > 38 else input_text) + ("|" if cursor_blink < 30 else "")
        txt = prompt_font.render(display_text, True, (255, 255, 255))
        screen.blit(txt, (field_rect.x + 8, field_rect.y + 6))

        hint = font_sm.render("Enter=confirm  ESC=cancel" + ("  (.json added auto)" if list_files else ""),
                              True, (140, 140, 140))
        screen.blit(hint, (box_x + 20, box_y + 85))

        if existing:
            list_y = box_y + 110
            header_text = "Click to load:" if allow_click_select else "Existing maps:"
            header = font_sm.render(header_text, True, (180, 180, 180))
            screen.blit(header, (box_x + 20, list_y))
            list_y += 20
            for fname in existing[:14]:
                frect = pygame.Rect(box_x + 16, list_y, box_w - 32, 26)
                is_hovered = frect.collidepoint(mx, my)
                if is_hovered and allow_click_select:
                    pygame.draw.rect(screen, (70, 90, 70), frect, border_radius=4)
                    hovered_file = fname
                elif allow_click_select:
                    pygame.draw.rect(screen, (55, 55, 60), frect, border_radius=4)
                ft_color = (180, 220, 180) if is_hovered and allow_click_select else (130, 160, 130)
                ft = font_sm.render(f"  {fname}", True, ft_color)
                screen.blit(ft, (box_x + 24, list_y + 5))
                list_y += 28

        pygame.display.flip()
        clock.tick(30)


def message_box(title, lines):
    """A modal message in the middle of the screen; any key or click closes it."""
    title_font = pygame.font.SysFont("monospace", 16, bold=True)
    body_font = pygame.font.SysFont("monospace", 14)
    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return
            if event.type in (pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN):
                return
        box_w = max(420, max((body_font.size(l)[0] for l in lines), default=0) + 40)
        box_h = 90 + len(lines) * 20
        box_x, box_y = (SCREEN_W - box_w) // 2, (SCREEN_H - box_h) // 2
        overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 150))
        screen.blit(overlay, (0, 0))
        pygame.draw.rect(screen, (50, 50, 55), (box_x, box_y, box_w, box_h), border_radius=8)
        pygame.draw.rect(screen, (230, 190, 80), (box_x, box_y, box_w, box_h), 2, border_radius=8)
        screen.blit(title_font.render(title, True, (255, 215, 90)), (box_x + 20, box_y + 15))
        for i, line in enumerate(lines):
            screen.blit(body_font.render(line, True, COL_TEXT), (box_x + 20, box_y + 45 + i * 20))
        screen.blit(font_sm.render("Press any key or click to continue", True, (140, 140, 140)),
                    (box_x + 20, box_y + box_h - 28))
        pygame.display.flip()
        clock.tick(30)


placing_npc = None   # npc_id waiting for a click on the map (set by the Quests & NPCs screen)


def open_story():
    """The Quests & NPCs screen (Q): this map's NPCs and the game's quests (data/quests.json)."""
    global placing_npc
    data = quests_mod.load_quest_data()
    npcs = map_data.extra.setdefault("npcs", [])
    others = {i: d for i, d in quests_mod.npc_directory(refresh=True).items() if d["map"] != last_filename}
    saved, place = story_panel.run(
        screen, clock, npcs, data, defs,
        ask=lambda title, default, long=False: text_input_prompt(title, default, list_files=False,
                                                                 max_len=1200 if long else 40),
        art=monster_art, map_size=(map_data.width, map_data.height),
        quest_save=lambda d: quests_mod.save_quest_data(d), other_npcs=others)
    if saved:
        print("Saved the quests (save the map too, to keep its NPCs)")
        placing_npc = place


def open_monster_types():
    """The Monsters screen (M): create / edit / duplicate / delete any monster type (levels and drops included)."""
    other_maps = {name: m for name, m in monster_defs.map_files().items() if name != last_filename}

    def on_this_map():
        return {s["type"] for s in map_data.spawns}

    def used_by(tid):                        # this map as it is now (unsaved edits too) + the other maps' files
        names = monster_defs.maps_using(tid, other_maps)
        return (["this map"] if tid in on_this_map() else []) + names

    saved = monster_panel.run(screen, clock, defs,
                              ask=lambda title, default: text_input_prompt(title, default, list_files=False),
                              map_types=on_this_map, usage=used_by)
    if saved:
        print(f"Saved {len(defs)} monster type(s) to {monster_defs.PATH} "
              )
    refresh_spawn_types()
    global selected_spawn
    selected_spawn = min(selected_spawn, len(SPAWN_TYPES) - 1)


last_filename = ""


def save_map():
    """Save current map to JSON with filename prompt."""
    global last_filename
    filename = text_input_prompt("Save map as:", last_filename)
    if filename is None:
        return
    if not filename.endswith(".json"):
        filename += ".json"
    last_filename = filename.replace(".json", "")
    path = os.path.join(save_dir, filename)
    data = map_data.to_dict()
    # Walls that touch only at a corner let players walk diagonally through them: block one open tile of each
    # such 2x2 block (the editor's own tiles are patched too, so you see the result right away)
    patched, unfixable = patch_diagonal_gaps(data)
    errors, warnings = validate_map(data, KNOWN_SPAWN_TYPES)
    with open(path, "w") as f:   # always save, so work in progress is never lost
        json.dump(data, f, indent=2)
    print(f"Saved: {path}")
    if patched or unfixable:
        lines = [f"Your walls had {len(patched) + len(unfixable)} diagonal gap(s) players could walk through."]
        if patched:
            lines.append(f"We patched {len(patched)} (made these tiles unwalkable) and saved:")
            lines.append("  " + ", ".join(f"({x},{y})" for x, y in patched[:12]) + (" ..." if len(patched) > 12 else ""))
        if unfixable:
            lines.append(f"{len(unfixable)} could not be patched (a spawn or NPC stands on every open tile):")
            lines.append("  " + ", ".join(f"({x},{y})" for x, y in unfixable[:12]))
        print("  " + "\n  ".join(lines))
        message_box("Map saved — wall gaps patched", lines)
    for w in warnings[:10]:
        print(f"  warning: {w}")
    if errors:
        print("  NOT PLAYABLE YET — fix these before playing or hosting this map:")
        for e in errors[:10]:
            print(f"   - {e}")


def load_map():
    """Load map from JSON with filename prompt. Files are clickable."""
    global map_data, last_filename
    filename = text_input_prompt("Load map:", last_filename, allow_click_select=True)
    if filename is None:
        return
    if not filename.endswith(".json"):
        filename += ".json"
    path = os.path.join(save_dir, filename)
    if os.path.exists(path):
        with open(path, "r") as f:
            data = json.load(f)
        map_data = MapData.from_dict(data)
        last_filename = filename.replace(".json", "")
        reset_camera_to_top_left()
        print(f"Loaded: {path}")
    else:
        print(f"File not found: {path}")


# === MAIN LOOP ===
running = True
toolbar_buttons = []

while running:
    dt = clock.tick(60) / 1000.0

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

        elif event.type == pygame.KEYDOWN:
            mods = pygame.key.get_mods()
            ctrl = mods & pygame.KMOD_CTRL
            shift = mods & pygame.KMOD_SHIFT

            if ctrl and event.key == pygame.K_s:
                save_map()
            elif ctrl and event.key == pygame.K_o:
                load_map()
            elif ctrl and shift and event.key == pygame.K_z:
                undo_stack.redo(map_data)
            elif ctrl and event.key == pygame.K_z:
                undo_stack.undo(map_data)
            elif event.key == pygame.K_f:
                fill_mode = not fill_mode
                if fill_mode:
                    sample_mode = False
            elif event.key == pygame.K_e:
                sample_mode = not sample_mode
                if sample_mode:
                    fill_mode = False
            elif event.key == pygame.K_w:
                show_walkability = not show_walkability
            elif event.key == pygame.K_1:
                current_layer = 0
                spawn_mode = False
                location_mode = False
            elif event.key == pygame.K_2:
                current_layer = 1
                spawn_mode = False
                location_mode = False
            elif event.key == pygame.K_3:
                spawn_mode = not spawn_mode
                if spawn_mode:
                    location_mode = False
                    selected_spawn = 0
            elif event.key == pygame.K_4:
                location_mode = not location_mode
                if location_mode:
                    spawn_mode = False
                    selected_spawn = 0
            elif event.key == pygame.K_ESCAPE:
                if placing_npc:
                    placing_npc = None
                else:
                    running = False
            elif event.key == pygame.K_m:
                open_monster_types()
            elif event.key == pygame.K_q:
                open_story()
            elif event.key == pygame.K_PLUS or event.key == pygame.K_EQUALS:
                zoom = min(max_zoom, zoom + 0.5)
            elif event.key == pygame.K_MINUS:
                zoom = max(min_zoom, zoom - 0.5)

        elif event.type == pygame.MOUSEBUTTONDOWN:
            mx, my = event.pos

            # Toolbar clicks
            for rect, action in toolbar_buttons:
                if rect.collidepoint(mx, my):
                    if action == "save":
                        save_map()
                    elif action == "load":
                        load_map()
                    elif action == "undo":
                        undo_stack.undo(map_data)
                    elif action == "redo":
                        undo_stack.redo(map_data)
                    elif action == "fill":
                        fill_mode = not fill_mode
                        if fill_mode:
                            sample_mode = False
                    elif action == "sample":
                        sample_mode = not sample_mode
                        if sample_mode:
                            fill_mode = False
                    elif action == "walk":
                        show_walkability = not show_walkability
                    elif action == "spawns":
                        spawn_mode = not spawn_mode
                        if spawn_mode:
                            location_mode = False
                            selected_spawn = 0
                    elif action == "locations":
                        location_mode = not location_mode
                        if location_mode:
                            spawn_mode = False
                            selected_spawn = 0
                    elif action == "monsters":
                        open_monster_types()
                    elif action == "story":
                        open_story()
                    break

            # Palette click
            if mx < PALETTE_W and my > TOOLBAR_H:
                # Handled via draw_palette return
                pass

            # Canvas interactions
            elif mx >= PALETTE_W and my >= TOOLBAR_H:
                if event.button == 1:  # Left click
                    tx, ty = screen_to_tile(mx, my)
                    if tx is not None:
                        if placing_npc:
                            for npc in map_data.extra.get("npcs", []):
                                if npc["npc_id"] == placing_npc:
                                    npc["x"], npc["y"] = tx, ty
                            placing_npc = None
                        elif sample_mode:
                            # Eyedropper: pick tile from canvas
                            # Check current layer first, then fall through layers
                            sampled = None
                            for li in range(len(map_data.layers) - 1, -1, -1):
                                cell = map_data.layers[li].get_tile(tx, ty)
                                if cell:
                                    sampled = (cell["col"], cell["row"])
                                    break
                            if sampled:
                                selected_tile = sampled
                                # Auto-scroll palette to show selected tile
                                tile_idx = sampled[1] * SHEET_COLS + sampled[0]
                                cols_fit = (PALETTE_W - 16) // (palette_tile_size + 2)
                                palette_scroll = tile_idx // cols_fit
                                sample_mode = False
                        elif spawn_mode:
                            # Place spawn
                            map_data.add_spawn(SPAWN_TYPES[selected_spawn]["id"], tx, ty)
                        elif location_mode:
                            # Place location marker
                            map_data.add_spawn(LOCATION_TYPES[selected_spawn]["id"], tx, ty)
                        elif fill_mode:
                            new_tile = {"col": selected_tile[0], "row": selected_tile[1], "walkable": True}
                            actions = flood_fill(map_data, current_layer, tx, ty, new_tile)
                            if actions:
                                undo_stack.push_batch(actions)
                        elif show_walkability:
                            # Toggle walkability — start drag stroke
                            cell = map_data.layers[current_layer].get_tile(tx, ty)
                            if cell:
                                old = deepcopy(cell)
                                walk_paint_value = not cell.get("walkable", True)
                                cell["walkable"] = walk_paint_value
                                new = deepcopy(cell)
                                walk_painting = True
                                current_stroke = [{"layer": current_layer, "x": tx, "y": ty, "old": old, "new": new}]
                        else:
                            painting = True
                            current_stroke = []
                            action = paint_tile(tx, ty)
                            if action:
                                current_stroke.append(action)

                elif event.button == 3:  # Right click
                    tx, ty = screen_to_tile(mx, my)
                    if tx is not None:
                        if spawn_mode or location_mode:
                            # Remove spawn/location
                            map_data.remove_spawn(tx, ty)
                        else:
                            erasing = True
                            current_stroke = []
                            action = erase_tile(tx, ty)
                            if action:
                                current_stroke.append(action)

                elif event.button == 2:  # Middle click
                    panning = True
                    pan_start = (mx, my)
                    cam_start = (cam_x, cam_y)

        elif event.type == pygame.MOUSEBUTTONUP:
            if event.button == 1:
                if painting and current_stroke:
                    undo_stack.push_batch(current_stroke)
                    current_stroke = []
                painting = False
                if walk_painting and current_stroke:
                    undo_stack.push_batch(current_stroke)
                    current_stroke = []
                walk_painting = False
            elif event.button == 3:
                if erasing and current_stroke:
                    undo_stack.push_batch(current_stroke)
                    current_stroke = []
                erasing = False
            elif event.button == 2:
                panning = False

        elif event.type == pygame.MOUSEMOTION:
            mx, my = event.pos
            if panning:
                dx = mx - pan_start[0]
                dy = my - pan_start[1]
                cam_x = cam_start[0] - dx / zoom
                cam_y = cam_start[1] - dy / zoom
            elif walk_painting:
                tx, ty = screen_to_tile(mx, my)
                if tx is not None:
                    cell = map_data.layers[current_layer].get_tile(tx, ty)
                    if cell and cell.get("walkable", True) != walk_paint_value:
                        old = deepcopy(cell)
                        cell["walkable"] = walk_paint_value
                        new = deepcopy(cell)
                        current_stroke.append({"layer": current_layer, "x": tx, "y": ty, "old": old, "new": new})
            elif painting:
                tx, ty = screen_to_tile(mx, my)
                if tx is not None:
                    action = paint_tile(tx, ty)
                    if action:
                        current_stroke.append(action)
            elif erasing:
                tx, ty = screen_to_tile(mx, my)
                if tx is not None:
                    action = erase_tile(tx, ty)
                    if action:
                        current_stroke.append(action)

        elif event.type == pygame.MOUSEWHEEL:
            mx, my = pygame.mouse.get_pos()
            if mx < PALETTE_W and my > TOOLBAR_H:
                # Scroll palette
                palette_scroll = max(0, palette_scroll - event.y * 3)
            else:
                # Zoom canvas
                old_zoom = zoom
                zoom += event.y * 0.25
                zoom = max(min_zoom, min(max_zoom, zoom))

        elif event.type == pygame.VIDEORESIZE:
            SCREEN_W, SCREEN_H = event.w, event.h
            screen = pygame.display.set_mode((SCREEN_W, SCREEN_H), pygame.RESIZABLE)

    # Arrow keys pan
    keys = pygame.key.get_pressed()
    pan_speed = 300 / zoom
    if keys[pygame.K_LEFT]:
        cam_x -= pan_speed * dt
    if keys[pygame.K_RIGHT]:
        cam_x += pan_speed * dt
    if keys[pygame.K_UP]:
        cam_y -= pan_speed * dt
    if keys[pygame.K_DOWN]:
        cam_y += pan_speed * dt

    # === DRAW ===
    screen.fill(COL_BG)
    draw_canvas()
    toolbar_buttons = draw_toolbar()
    palette_result = draw_palette()[0]

    # Handle palette selection (from draw_palette)
    if pygame.mouse.get_pressed()[0] and palette_result is not None:
        if spawn_mode or location_mode:
            selected_spawn = palette_result
        else:
            selected_tile = palette_result

    pygame.display.flip()

pygame.quit()
