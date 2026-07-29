"""
Zone Explorer — walk around an open-world zone map.
Standalone demo: python3 game/zone_explorer.py
"""
import pygame
import sys
import os
import math
import random

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game.engine.zone_map import ZoneMap, TILE_SIZE
from game.engine.pathfinding import astar

# === INIT ===
pygame.init()
WIDTH, HEIGHT = 1024, 768
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Elwynn Forest — Zone Explorer")
clock = pygame.time.Clock()
font = pygame.font.Font(None, 20)
big_font = pygame.font.Font(None, 28)

# === LOAD ZONE ===
zone = ZoneMap("data/zones/elwynn_forest.json")
print(f"Loaded zone: {zone.name} ({zone.width}x{zone.height} tiles, {zone.world_width}x{zone.world_height}px)")

# === LOAD SPRITES ===
TILE_SRC = 16
dungeon_img = pygame.image.load("assets/kenney_dungeon/Tilemap/tilemap.png").convert_alpha()
creature_img = pygame.image.load("assets/tiny_creatures/tiny-creatures/Tilemap/tilemap.png").convert_alpha()

def get_dungeon_tile(col, row, scale=TILE_SIZE):
    x, y = col * (TILE_SRC + 1), row * (TILE_SRC + 1)
    s = pygame.Surface((TILE_SRC, TILE_SRC), pygame.SRCALPHA)
    s.blit(dungeon_img, (0, 0), (x, y, TILE_SRC, TILE_SRC))
    return pygame.transform.scale(s, (scale, scale))

def get_creature(col, row, scale=TILE_SIZE):
    x, y = col * (TILE_SRC + 1), row * (TILE_SRC + 1)
    s = pygame.Surface((TILE_SRC, TILE_SRC), pygame.SRCALPHA)
    s.blit(creature_img, (0, 0), (x, y, TILE_SRC, TILE_SRC))
    return pygame.transform.scale(s, (scale, scale))

hero_sprite = get_dungeon_tile(0, 8)  # Vistra
monster_sprites = {
    "Kobold": get_creature(9, 7),
    "Wolf": get_creature(0, 4),
}

# Terrain colors for zone tiles (since we don't have terrain-specific sprites yet)
TERRAIN_COLORS = {
    "grass": (80, 160, 60),
    "dirt": (150, 120, 60),
    "forest": (30, 80, 30),
    "mountain": (70, 65, 55),
    "water": (40, 80, 180),
    "cave": (50, 20, 50),
    "city": (140, 120, 90),
}

# === HERO ===
spawn = zone.get_spawn("player_start")
hero_x, hero_y = float(spawn[0]), float(spawn[1])
hero_speed = 180.0  # pixels per second
facing_left = False
move_path = []

# === MOBS ===
mobs = []
# Kobolds near Echo Ridge Mine
mine_pos = zone.get_spawn("echo_ridge_mine")
for i in range(6):
    mx = mine_pos[0] + random.randint(-80, 80)
    my = mine_pos[1] + random.randint(-60, 60)
    if not zone.is_wall(mx, my):
        mobs.append({"name": "Kobold", "x": mx, "y": my, "sprite": monster_sprites["Kobold"]})

# Wolves in Northshire area
abbey_pos = zone.get_spawn("northshire_abbey")
for i in range(5):
    mx = abbey_pos[0] + random.randint(-150, 150)
    my = abbey_pos[1] + random.randint(-80, 150)
    if not zone.is_wall(mx, my):
        mobs.append({"name": "Wolf", "x": mx, "y": my, "sprite": monster_sprites["Wolf"]})

# More wolves near Eastvale
east_pos = zone.get_spawn("eastvale_logging_camp")
for i in range(6):
    mx = east_pos[0] + random.randint(-200, 100)
    my = east_pos[1] + random.randint(-100, 100)
    if not zone.is_wall(mx, my):
        mobs.append({"name": "Wolf", "x": mx, "y": my, "sprite": monster_sprites["Wolf"]})

# Kobolds near Fargodeep Mine
fargo_pos = zone.get_spawn("fargodeep_mine")
for i in range(5):
    mx = fargo_pos[0] + random.randint(-80, 80)
    my = fargo_pos[1] + random.randint(-60, 60)
    if not zone.is_wall(mx, my):
        mobs.append({"name": "Kobold", "x": mx, "y": my, "sprite": monster_sprites["Kobold"]})


# === PATHFINDING ADAPTER (zone_map uses same interface as dungeon for astar) ===
class ZonePathAdapter:
    """Adapter so astar() works with ZoneMap."""
    def __init__(self, zone_map):
        self.grid_w = zone_map.width
        self.grid_h = zone_map.height
        self.zone = zone_map

    def is_floor(self, tx, ty):
        return self.zone.is_floor(tx, ty)


zone_adapter = ZonePathAdapter(zone)


def is_wall(wx, wy):
    return zone.is_wall(wx, wy)


# === MAIN LOOP ===
running = True
while running:
    dt = clock.tick(60) / 1000.0

    # === INPUT ===
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                running = False
        if event.type == pygame.MOUSEBUTTONDOWN:
            mx, my = event.pos
            wx = mx + hero_x - WIDTH // 2
            wy = my + hero_y - HEIGHT // 2
            if event.button == 1 or event.button == 3:
                # Click to move
                move_path = astar(zone_adapter, hero_x, hero_y, wx, wy)

    # === MOVEMENT ===
    if move_path:
        tx, ty = move_path[0]
        dx, dy = tx - hero_x, ty - hero_y
        dist = math.sqrt(dx * dx + dy * dy)
        if dist < 8:
            move_path.pop(0)
        else:
            spd = hero_speed * dt
            hero_x += (dx / dist) * min(spd, dist)
            hero_y += (dy / dist) * min(spd, dist)
            facing_left = dx < 0

    # === RENDER ===
    screen.fill((15, 12, 20))
    cx, cy = hero_x, hero_y

    # Draw terrain tiles
    view_left = int((cx - WIDTH // 2) // TILE_SIZE) - 1
    view_top = int((cy - HEIGHT // 2) // TILE_SIZE) - 1
    view_right = view_left + WIDTH // TILE_SIZE + 3
    view_bottom = view_top + HEIGHT // TILE_SIZE + 3

    for ty in range(max(0, view_top), min(zone.height, view_bottom)):
        for tx in range(max(0, view_left), min(zone.width, view_right)):
            terrain_type = zone.terrain[ty][tx]
            color = TERRAIN_COLORS.get(terrain_type, (100, 100, 100))
            sx = int(tx * TILE_SIZE - cx + WIDTH // 2)
            sy = int(ty * TILE_SIZE - cy + HEIGHT // 2)
            pygame.draw.rect(screen, color, (sx, sy, TILE_SIZE, TILE_SIZE))
            # Grid lines (subtle)
            pygame.draw.rect(screen, (color[0]//2, color[1]//2, color[2]//2), (sx, sy, TILE_SIZE, TILE_SIZE), 1)

    # Draw path dots
    for wp in move_path[:15]:
        psx = int(wp[0] - cx + WIDTH // 2)
        psy = int(wp[1] - cy + HEIGHT // 2)
        pygame.draw.circle(screen, (200, 200, 100), (psx, psy), 3)

    # Draw mobs
    for mob in mobs:
        msx = int(mob["x"] - cx + WIDTH // 2)
        msy = int(mob["y"] - cy + HEIGHT // 2)
        if -50 < msx < WIDTH + 50 and -50 < msy < HEIGHT + 50:
            if mob["sprite"]:
                screen.blit(mob["sprite"], (msx - TILE_SIZE // 2, msy - TILE_SIZE // 2))
            else:
                pygame.draw.circle(screen, (200, 50, 50), (msx, msy), 10)
            # Name
            t = font.render(mob["name"], True, (200, 100, 100))
            screen.blit(t, (msx - t.get_width() // 2, msy - 30))

    # Draw hero
    spr = hero_sprite
    sw, sh = spr.get_size()
    hsx = int(hero_x - cx + WIDTH // 2 - sw // 2)
    hsy = int(hero_y - cy + HEIGHT // 2 - sh // 2)
    s = pygame.transform.flip(spr, True, False) if facing_left else spr
    screen.blit(s, (hsx, hsy))

    # HUD
    tile_x = int(hero_x // TILE_SIZE)
    tile_y = int(hero_y // TILE_SIZE)
    terrain_here = zone.get_terrain(tile_x, tile_y)
    screen.blit(font.render(f"Elwynn Forest  ({tile_x},{tile_y})  terrain: {terrain_here}", True, (200, 200, 200)), (10, 10))
    screen.blit(font.render("Click to move | ESC to quit", True, (100, 100, 100)), (10, HEIGHT - 20))

    # Minimap
    mm_x, mm_y = WIDTH - 160, 10
    mm_scale = 2
    pygame.draw.rect(screen, (20, 20, 30), (mm_x - 2, mm_y - 2, zone.width * mm_scale + 4, zone.height * mm_scale + 4))
    for my_t in range(zone.height):
        for mx_t in range(zone.width):
            color = TERRAIN_COLORS.get(zone.terrain[my_t][mx_t], (50, 50, 50))
            # Dim it for minimap
            color = (color[0] // 2, color[1] // 2, color[2] // 2)
            screen.set_at((mm_x + mx_t * mm_scale, mm_y + my_t * mm_scale), color)
            if mm_scale > 1:
                screen.set_at((mm_x + mx_t * mm_scale + 1, mm_y + my_t * mm_scale), color)
    # Hero dot on minimap
    hmx = mm_x + int(tile_x * mm_scale)
    hmy = mm_y + int(tile_y * mm_scale)
    pygame.draw.circle(screen, (255, 255, 0), (hmx, hmy), 3)

    pygame.display.flip()

pygame.quit()
