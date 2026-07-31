"""
Wrath of Ashardalon — Adventure 1: Escape the Tunnel
Controls (WoW-style):
  Right-click = Move to location
  Left-click = Select target / Cast ability at location
  1, 2, 3 = Abilities
  F = Health potion
  ESC = Quit
"""
import pygame
import math
import random
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from game.engine.entities import Hero, Monster, Ability, Condition, GameState, Projectile
from game.engine.dungeon import UnifiedDungeon, RoomType, TILE_SIZE
from game.engine.world_map import WorldMap
from game.engine.ai import run_monster_ai, setup_monster_aggro, call_for_help, generate_patrol_route
from game.engine.pathfinding import astar
from game.content.heroes import ALL_HEROES
import game.engine.entities as _entities

os.chdir(os.path.dirname(os.path.dirname(__file__)))

# === CLI ARGS ===
USE_MAP = None  # Path to world map JSON, or None for dungeon mode
DEBUG = "--debug" in sys.argv  # Pass --debug to enable frame/AI logging
for i, arg in enumerate(sys.argv):
    if arg == "--map" and i + 1 < len(sys.argv):
        USE_MAP = sys.argv[i + 1]
    elif arg == "--map" and i + 1 >= len(sys.argv):
        USE_MAP = "data/maps/northshire.json"
if "--map" in sys.argv and USE_MAP is None:
    USE_MAP = "data/maps/northshire.json"

# === INIT ===
pygame.init()
WIDTH, HEIGHT = 1024, 768
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Wrath of Ashardalon — Adventure 1: Escape the Tunnel")
clock = pygame.time.Clock()
font = pygame.font.Font(None, 20)
big_font = pygame.font.Font(None, 32)
title_font = pygame.font.Font(None, 48)

# Colors
BG = (15, 12, 20)
HP_GREEN = (80, 220, 80)
HP_RED = (200, 50, 50)
HP_BG = (40, 20, 20)
GOLD = (255, 215, 0)
WHITE = (255, 255, 255)
GRAY = (80, 80, 80)
BLUE = (100, 150, 255)
ABILITY_READY = (40, 120, 40)
DOOR_COLOR = (180, 140, 60)

# === LOAD SPRITES ===
TILE_SRC = 16

# Character scale: 1.0 = same size as map tile, 0.5 = half size.
# Also scales movement speed proportionally so the map feels bigger.
CHAR_SCALE = 0.5
CHAR_SIZE = int(TILE_SIZE * CHAR_SCALE)
BOSS_SCALE = CHAR_SCALE * 1.5  # Bosses are 1.5x character size

# Scale movement speed to match character size
_entities.SPEED_SCALE = int(30 * CHAR_SCALE)

dungeon_img = pygame.image.load("assets/kenney_dungeon/Tilemap/tilemap.png").convert_alpha()
rpg_img = pygame.image.load("assets/kenney_rpg/Spritesheet/roguelikeSheet_transparent.png").convert_alpha()
creature_img = pygame.image.load("assets/tiny_creatures/tiny-creatures/Tilemap/tilemap.png").convert_alpha()

def get_dungeon_tile(col, row):
    x, y = col*(TILE_SRC+1), row*(TILE_SRC+1)
    s = pygame.Surface((TILE_SRC, TILE_SRC), pygame.SRCALPHA)
    s.blit(dungeon_img, (0,0), (x,y,TILE_SRC,TILE_SRC))
    return pygame.transform.scale(s, (CHAR_SIZE, CHAR_SIZE))

def get_rpg_tile(col, row):
    x, y = col*(TILE_SRC+1), row*(TILE_SRC+1)
    s = pygame.Surface((TILE_SRC, TILE_SRC), pygame.SRCALPHA)
    s.blit(rpg_img, (0,0), (x,y,TILE_SRC,TILE_SRC))
    return pygame.transform.scale(s, (TILE_SIZE, TILE_SIZE))

def get_rpg_tile_raw(col, row):
    """Get a raw 16x16 tile surface (not scaled) for caching."""
    x, y = col*(TILE_SRC+1), row*(TILE_SRC+1)
    s = pygame.Surface((TILE_SRC, TILE_SRC), pygame.SRCALPHA)
    s.blit(rpg_img, (0,0), (x,y,TILE_SRC,TILE_SRC))
    return s

# Cache for world map tile surfaces (scaled to TILE_SIZE)
rpg_tile_cache = {}

def get_creature(col, row, scale=None):
    if scale is None:
        scale = CHAR_SIZE
    x, y = col*(TILE_SRC+1), row*(TILE_SRC+1)
    s = pygame.Surface((TILE_SRC, TILE_SRC), pygame.SRCALPHA)
    s.blit(creature_img, (0,0), (x,y,TILE_SRC,TILE_SRC))
    return pygame.transform.scale(s, (scale, scale))

# Environment (from Kenney Roguelike RPG)
SPR_FLOOR = get_rpg_tile(8, 10)   # stone floor
SPR_FLOOR2 = get_rpg_tile(8, 10)  # same for now
SPR_WALL = get_rpg_tile(13, 9)    # wall

# Hero sprites
HERO_SPRITES = {
    "vistra": get_dungeon_tile(0, 8),
    "quinn": get_dungeon_tile(3, 8),
    "keyleth": get_dungeon_tile(4, 7),
    "tarak": get_dungeon_tile(2, 7),
    "heskan": get_dungeon_tile(0, 7),
}

# Monster sprites
MONSTER_SPRITES = {
    "Kobold Dragonshield": get_creature(9, 7),
    "Snake": get_creature(0, 4),
    "Orc Smasher": get_creature(1, 1),
    "Orc Archer": get_creature(0, 1),
    "Human Cultist": get_creature(7, 6),
    "Duergar Guard": get_creature(4, 12),
    "Legion Devil": get_creature(8, 3),
    "Grey Wolf": get_creature(3, 2),
    "Grell": get_creature(5, 0),
    "Gibbering Mouther": get_creature(4, 8),
}
BOSS_SPRITE = get_creature(9, 7, int(TILE_SIZE * BOSS_SCALE))

# === EFFECTS ===
floating_texts = []
effects = []
projectiles = []  # Active projectiles (Wanding etc.)

class FloatingText:
    def __init__(self, x, y, text, color):
        self.x, self.y, self.text, self.color = x, y, text, color
        self.timer = 0.8
    def update(self, dt): self.timer -= dt; self.y -= 50*dt
    def draw(self, s, cx, cy):
        t = font.render(self.text, True, self.color)
        s.blit(t, (int((self.x-cx)*cam_zoom+WIDTH//2)-t.get_width()//2, int((self.y-cy)*cam_zoom+HEIGHT//2)))

class AoeRing:
    def __init__(self, x, y, radius, color):
        self.x, self.y, self.max_r, self.color = x, y, radius, color
        self.timer = 0.3
    def update(self, dt): self.timer -= dt
    def draw(self, s, cx, cy):
        sx, sy = int((self.x-cx)*cam_zoom+WIDTH//2), int((self.y-cy)*cam_zoom+HEIGHT//2)
        p = 1.0 - self.timer/0.3
        r = max(1, int(self.max_r * p * cam_zoom))
        a = int(150*(self.timer/0.3))
        if a > 0 and r > 0:
            surf = pygame.Surface((r*2,r*2), pygame.SRCALPHA)
            pygame.draw.circle(surf, (*self.color,a), (r,r), r, 3)
            pygame.draw.circle(surf, (*self.color,a//4), (r,r), r)
            s.blit(surf, (sx-r, sy-r))

# === AUTO MODE (for testing) ===
auto_mode = "--auto" in sys.argv
auto_hero_idx = 0  # Default to Fighter for auto mode
if auto_mode:
    for i, arg in enumerate(sys.argv):
        if arg == "--hero" and i + 1 < len(sys.argv):
            auto_hero_idx = int(sys.argv[i + 1])

# === HERO SELECT SCREEN ===
def wrap_text(text, fnt, max_width):
    """Wrap text to fit within max_width pixels."""
    words = text.split(' ')
    lines = []
    current = ""
    for word in words:
        test = current + (" " if current else "") + word
        if fnt.size(test)[0] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines

selected_hero_idx = 0
selecting = True
PANEL_W = 160
PANEL_H = 300

if auto_mode:
    selected_hero_idx = auto_hero_idx
    selecting = False

while selecting:
    for event in pygame.event.get():
        if event.type == pygame.QUIT: pygame.quit(); sys.exit()
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE: pygame.quit(); sys.exit()
            if event.key in (pygame.K_LEFT, pygame.K_a):
                for _ in range(len(ALL_HEROES)):
                    selected_hero_idx = (selected_hero_idx - 1) % len(ALL_HEROES)
                    if not ALL_HEROES[selected_hero_idx].get("wip"):
                        break
            if event.key in (pygame.K_RIGHT, pygame.K_d):
                for _ in range(len(ALL_HEROES)):
                    selected_hero_idx = (selected_hero_idx + 1) % len(ALL_HEROES)
                    if not ALL_HEROES[selected_hero_idx].get("wip"):
                        break
            if event.key in (pygame.K_RETURN, pygame.K_SPACE):
                if not ALL_HEROES[selected_hero_idx].get("wip"):
                    selecting = False
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mx_click, my_click = event.pos
            for i in range(len(ALL_HEROES)):
                px = 30 + i * (PANEL_W + 20)
                py = 160
                if px <= mx_click <= px + PANEL_W and py <= my_click <= py + PANEL_H:
                    if ALL_HEROES[i].get("wip"):
                        pass  # Can't select WIP heroes
                    elif selected_hero_idx == i:
                        # Double-click same hero = confirm
                        selecting = False
                    else:
                        selected_hero_idx = i

    screen.fill(BG)
    t = title_font.render("CHOOSE YOUR HERO", True, GOLD)
    screen.blit(t, (WIDTH//2 - t.get_width()//2, 50))

    for i, h_info in enumerate(ALL_HEROES):
        x = 30 + i * (PANEL_W + 20)
        y = 160
        is_wip = h_info.get("wip", False)
        # Panel background
        if is_wip:
            pygame.draw.rect(screen, (25, 25, 30), (x, y, PANEL_W, PANEL_H), 0, 6)
            pygame.draw.rect(screen, (60, 60, 60), (x, y, PANEL_W, PANEL_H), 1, 6)
        elif i == selected_hero_idx:
            pygame.draw.rect(screen, (60, 60, 100), (x, y, PANEL_W, PANEL_H), 0, 6)
            pygame.draw.rect(screen, GOLD, (x, y, PANEL_W, PANEL_H), 2, 6)
        else:
            pygame.draw.rect(screen, (35, 35, 50), (x, y, PANEL_W, PANEL_H), 0, 6)

        # Sprite centered
        spr = HERO_SPRITES[h_info["sprite_key"]]
        big_spr = pygame.transform.scale(spr, (64, 64))
        if is_wip:
            big_spr.set_alpha(80)
        screen.blit(big_spr, (x + PANEL_W//2 - 32, y + 15))

        # WIP banner
        if is_wip:
            wip_txt = big_font.render("WIP", True, (255, 100, 100))
            screen.blit(wip_txt, (x + PANEL_W//2 - wip_txt.get_width()//2, y + 140))

        # Name
        name_color = (100, 100, 100) if is_wip else WHITE
        nt = big_font.render(h_info["name"], True, name_color)
        screen.blit(nt, (x + PANEL_W//2 - nt.get_width()//2, y + 85))

        # Race/Class
        rc = font.render(f"{h_info['race']} {h_info['class']}", True, (160, 160, 190))
        screen.blit(rc, (x + PANEL_W//2 - rc.get_width()//2, y + 112))

        # Description (wrapped)
        desc_lines = wrap_text(h_info["desc"], font, PANEL_W - 16)
        for li, line in enumerate(desc_lines):
            lt = font.render(line, True, (140, 140, 160))
            screen.blit(lt, (x + 8, y + 140 + li * 18))

    # Instructions
    inst = font.render("A/D or Arrows = select    ENTER = confirm", True, (100, 100, 100))
    screen.blit(inst, (WIDTH//2 - inst.get_width()//2, HEIGHT - 50))

    # Controls preview
    ctrl = font.render("Controls: Right-click=Move  Left-click=Target  1/2/3=Abilities", True, (80,80,100))
    screen.blit(ctrl, (WIDTH//2 - ctrl.get_width()//2, HEIGHT - 75))

    pygame.display.flip()
    clock.tick(30)


# === GAME SETUP ===
if USE_MAP:
    world_map = WorldMap.load(USE_MAP)
    dungeon = world_map  # Duck-type compatible (is_wall, is_floor, get_start_pos)
    hero_wx, hero_wy = world_map.get_start_pos()
else:
    world_map = None
    dungeon = UnifiedDungeon()
    dungeon.generate(num_rooms=7, quest_room_name="Tunnel Exit")
    hero_wx, hero_wy = dungeon.get_start_pos()
hero_info = ALL_HEROES[selected_hero_idx]
hero = hero_info["create"](hero_wx, hero_wy)
hero.sprite = HERO_SPRITES[hero_info["sprite_key"]]

game_state = GameState()
game_state.heroes.append(hero)
game_state.life_tokens = 2
if USE_MAP:
    game_state.objective_text = "Explore Northshire and clear the area of monsters!"
else:
    game_state.objective_text = "Find the Tunnel Exit and defeat the Kobold Dragonlord!"

# Movement state
move_path = []
selected_target = None
potions = 3
victory = False

# Queued ability cast (walk to range then fire)
pending_cast = None  # (ab_key, ab, target_monster) or None

# Game speed (for AI observation)
game_speed = 1.0  # 1x, 2x, 4x

# Camera zoom (scroll wheel to adjust)
cam_zoom = 1.0       # 1.0 = default view, 2.0 = zoomed in 200%
CAM_ZOOM_MIN = 0.5   # Zoomed out (see more map)
CAM_ZOOM_MAX = 2.0   # Zoomed in (characters look bigger)
CAM_ZOOM_STEP = 0.1

# Skill slots (Diablo 2 style)
ability_keys = list(hero.abilities.keys())  # ["Q", "R", "E"]
left_skill_idx = 0    # Index into ability_keys for left-click skill
right_skill_idx = 1   # Index into ability_keys for right-click skill

# Dash animation state
dash_target_x = 0.0
dash_target_y = 0.0
dash_active = False
dash_speed = 800.0  # pixels per second (very fast)
dash_stun_target = None
dash_stun_duration = 0.0
dash_damage = 0.0  # damage dealt on arrival

# Frostbolt channel state (Heskan)
frostbolt_channeling = False
frostbolt_channel_timer = 0.0
frostbolt_target = None  # Monster being targeted

# Ambush walk-to state (Tarak)
ambush_target = None  # Monster to ambush (walk toward, execute when in range)

# Hero AI (toggle with TAB)
from game.engine.hero_ai import create_hero_ai
hero_ai = create_hero_ai(hero)
ai_enabled = auto_mode  # Auto mode starts with AI on

# AI Companions (summon with F1-F4)
companions = []  # list of (hero_obj, ai_obj) tuples
available_companions = [h for i, h in enumerate(ALL_HEROES) if i != selected_hero_idx]

# Auto-mode: summon first available companion and set 4x speed
if auto_mode and available_companions:
    # Pick Heskan if available, else first
    comp_info = next((c for c in available_companions if c["name"] == "Heskan"), available_companions[0])
    cx, cy = find_walkable_nearby(hero.x, hero.y, radius=40)
    comp = comp_info["create"](cx, cy)
    comp.sprite = HERO_SPRITES[comp_info["sprite_key"]]
    comp_ai = create_hero_ai(comp)
    if hasattr(comp_ai, 'allies'):
        comp_ai.allies = game_state.heroes
    companions.append((comp, comp_ai))
    game_state.heroes.append(comp)
    game_speed = 4.0

# Monster pool
MONSTER_POOL = [
    {"name": "Kobold Dragonshield", "hp": 1, "ac": 16, "speed": 5, "atk": 7, "dmg": 1, "xp": 1},
    {"name": "Snake", "hp": 1, "ac": 13, "speed": 6, "atk": 7, "dmg": 0, "xp": 1, "condition": (Condition.POISONED, 3.0)},
    {"name": "Orc Smasher", "hp": 2, "ac": 15, "speed": 4, "atk": 9, "dmg": 1, "xp": 2},
    {"name": "Orc Archer", "hp": 1, "ac": 13, "speed": 4, "atk": 6, "dmg": 1, "xp": 1, "ranged": True},
]

def spawn_monsters_for_room(room):
    if room.monsters_spawned or room.room_type == RoomType.START:
        return
    room.monsters_spawned = True
    if room.room_type == RoomType.QUEST:
        wx, wy = dungeon.get_spawn_world_pos(room.center_x, room.center_y)
        for offset in [(-60, 0), (0, 0), (60, 0)]:
            boss = Monster("Meerak", "Reptile", wx + offset[0], wy + offset[1], hp=6, ac=17, speed=5,
                           attack_bonus=8, attack_damage=1, experience=5, is_boss=True)
            boss.sprite = BOSS_SPRITE
            setup_monster_aggro(boss, nav_dungeon=dungeon)
            generate_patrol_route(boss, patrol_radius=60)
            game_state.monsters.append(boss)
        return
    for sx, sy in room.monster_spawns:
        mt = random.choice(MONSTER_POOL)
        wx, wy = dungeon.get_spawn_world_pos(sx, sy)
        m = Monster(mt["name"], "Monster", wx, wy,
                    hp=mt["hp"], ac=mt["ac"], speed=mt["speed"],
                    attack_bonus=mt["atk"], attack_damage=mt["dmg"], experience=mt["xp"])
        m.sprite = MONSTER_SPRITES.get(mt["name"])
        if mt.get("condition"):
            m.on_hit_condition = mt["condition"]
        if mt.get("ranged"):
            m.ranged_attack_range = 250
            m.ranged_attack_damage = m.base_damage
        setup_monster_aggro(m, nav_dungeon=dungeon)
        generate_patrol_route(m, patrol_radius=80, collision_fn=is_wall)
        game_state.monsters.append(m)

def is_wall(wx, wy):
    return dungeon.is_wall(wx, wy)


def find_walkable_nearby(x, y, radius=60, attempts=20):
    """Find a walkable position near (x, y). Returns (wx, wy) or (x, y) as fallback."""
    for _ in range(attempts):
        nx = x + random.randint(-radius, radius)
        ny = y + random.randint(-radius, radius)
        if not is_wall(nx, ny):
            return nx, ny
    # Fallback: try the exact point
    if not is_wall(x, y):
        return x, y
    # Last resort: spiral outward to find any walkable tile
    for r in range(1, radius // TILE_SIZE + 3):
        for dx in range(-r, r + 1):
            for dy in range(-r, r + 1):
                tx = x + dx * TILE_SIZE
                ty = y + dy * TILE_SIZE
                if not is_wall(tx, ty):
                    return tx, ty
    return x, y


# World map monster stats lookup
SPAWN_STATS = {
    "kobold_dragonshield": {"name": "Kobold Dragonshield", "hp": 1, "ac": 16, "speed": 5, "atk": 7, "dmg": 1, "xp": 1},
    "snake": {"name": "Snake", "hp": 1, "ac": 13, "speed": 6, "atk": 7, "dmg": 0, "xp": 1, "condition": (Condition.POISONED, 3.0)},
    "orc_smasher": {"name": "Orc Smasher", "hp": 2, "ac": 15, "speed": 4, "atk": 9, "dmg": 1, "xp": 2},
    "orc_archer": {"name": "Orc Archer", "hp": 1, "ac": 13, "speed": 4, "atk": 6, "dmg": 1, "xp": 1, "ranged": True},
    "grey_wolf": {"name": "Grey Wolf", "hp": 2, "ac": 14, "speed": 5, "atk": 8, "dmg": 2, "xp": 2},
    "duergar_guard": {"name": "Duergar Guard", "hp": 2, "ac": 16, "speed": 4, "atk": 8, "dmg": 1, "xp": 2},
    "gibbering_mouther": {"name": "Gibbering Mouther", "hp": 2, "ac": 14, "speed": 3, "atk": 8, "dmg": 1, "xp": 3},
    "grell": {"name": "Grell", "hp": 2, "ac": 15, "speed": 5, "atk": 7, "dmg": 1, "xp": 2, "condition": (Condition.POISONED, 3.0)},
    "human_cultist": {"name": "Human Cultist", "hp": 1, "ac": 14, "speed": 5, "atk": 6, "dmg": 1, "xp": 1, "condition": (Condition.POISONED, 3.0)},
    "legion_devil": {"name": "Legion Devil", "hp": 1, "ac": 16, "speed": 5, "atk": 11, "dmg": 1, "xp": 3},
    "meerak": {"name": "Meerak", "hp": 6, "ac": 17, "speed": 5, "atk": 8, "dmg": 1, "xp": 5, "boss": True},
    "ashardalon": {"name": "Ashardalon", "hp": 12, "ac": 16, "speed": 4, "atk": 10, "dmg": 2, "xp": 10, "boss": True},
    "bellax": {"name": "Bellax", "hp": 9, "ac": 17, "speed": 4, "atk": 8, "dmg": 2, "xp": 8, "boss": True},
    "karash": {"name": "Karash", "hp": 5, "ac": 15, "speed": 5, "atk": 7, "dmg": 1, "xp": 5, "boss": True},
    "margrath": {"name": "Margrath", "hp": 5, "ac": 16, "speed": 4, "atk": 8, "dmg": 1, "xp": 5, "boss": True},
    "rage_drake": {"name": "Rage Drake", "hp": 5, "ac": 15, "speed": 6, "atk": 9, "dmg": 2, "xp": 5, "boss": True},
    "otyugh": {"name": "Otyugh", "hp": 5, "ac": 14, "speed": 3, "atk": 8, "dmg": 2, "xp": 5, "boss": True},
}

def spawn_world_map_monsters():
    """Spawn all monsters from world map spawn data."""
    for sp in world_map.get_monster_spawns():
        mt = SPAWN_STATS.get(sp.type)
        if mt is None:
            continue
        wx, wy = world_map.get_spawn_world_pos(sp.x, sp.y)
        is_boss = mt.get("boss", False)
        m = Monster(mt["name"], "Monster", wx, wy,
                    hp=mt["hp"], ac=mt["ac"], speed=mt["speed"],
                    attack_bonus=mt["atk"], attack_damage=mt["dmg"],
                    experience=mt["xp"], is_boss=is_boss)
        m.sprite = BOSS_SPRITE if is_boss else MONSTER_SPRITES.get(mt["name"])
        if mt.get("condition"):
            m.on_hit_condition = mt["condition"]
        if mt.get("ranged"):
            m.ranged_attack_range = 250
            m.ranged_attack_damage = m.base_damage
        setup_monster_aggro(m, nav_dungeon=dungeon)
        generate_patrol_route(m, patrol_radius=100, collision_fn=is_wall)
        game_state.monsters.append(m)

# Spawn monsters for world map mode at start
if USE_MAP:
    spawn_world_map_monsters()

def get_monster_at_screen(sx, sy):
    wx = (sx - WIDTH//2) / cam_zoom + hero.x
    wy = (sy - HEIGHT//2) / cam_zoom + hero.y
    for m in game_state.alive_monsters:
        if abs(m.x - wx) < TILE_SIZE and abs(m.y - wy) < TILE_SIZE:
            return m
    return None

def _cast_ability(ab_key, ab, wx, wy, clicked_monster):
    """Cast an ability — handles AoE, single target, dash, stun, call-for-help, and Quinn's Seal system."""
    global move_path, selected_target, dash_active, dash_target_x, dash_target_y, dash_stun_target, dash_stun_duration, dash_damage, frostbolt_channeling, frostbolt_channel_timer, frostbolt_target, ambush_target

    # Global Cooldown check
    if hero.gcd > 0:
        return  # Can't cast anything during GCD

    # === Tarak special: Stab (fast melee, breaks stealth) ===
    if ab.name == "Stab":
        if not clicked_monster:
            floating_texts.append(FloatingText(hero.x, hero.y - 30, "No target!", (255, 150, 100)))
            return
        dist_to_target = hero.distance_to(clicked_monster)
        if dist_to_target > ab.range:
            selected_target = clicked_monster
            move_path = []
            return
        if hero.swing_timer > 0:
            return  # Gated by weapon speed
        ab.use()
        hero.swing_timer = hero.weapon_speed
        # Break stealth on attack
        if hero.stealthed:
            hero.stealthed = False
            floating_texts.append(FloatingText(hero.x, hero.y - 40, "Stealth broken!", (200, 200, 200)))
        dmg_amount = ab.calc_damage(hero.base_damage)
        # Crit roll
        hero.last_crit = random.random() < hero.crit_chance
        if hero.last_crit:
            dmg_amount *= hero.crit_multiplier
        dmg = clicked_monster.take_damage(dmg_amount)
        color = (255, 255, 50) if hero.last_crit else (180, 255, 180)
        text = f"{dmg:.0f}!" if hero.last_crit else f"{dmg:.0f}"
        floating_texts.append(FloatingText(clicked_monster.x, clicked_monster.y - 20, text, color))
        call_for_help(clicked_monster, game_state.monsters, hero)
        if hasattr(clicked_monster, 'aggro_state') and clicked_monster.aggro_state != "aggroed":
            from game.engine.ai import aggro_monster as _aggro
            _aggro(clicked_monster, hero, game_state.monsters)
        hero.gcd = hero.GCD_DURATION
        move_path = []
        selected_target = clicked_monster  # Keep target for auto-attack
        return

    # === Tarak special: Stealth (go invisible) ===
    if ab.name == "Stealth":
        ab.use()
        hero.stealthed = True
        selected_target = None  # Stop auto-attack
        # Drop aggro from all monsters targeting hero (except bosses)
        for m in game_state.alive_monsters:
            if hasattr(m, 'aggro_target') and m.aggro_target == hero and not m.is_boss:
                from game.engine.ai import AggroState
                m.aggro_state = AggroState.RESETTING
                m.aggro_target = None
        floating_texts.append(FloatingText(hero.x, hero.y - 30, "Stealth!", (100, 200, 100)))
        hero.gcd = hero.GCD_DURATION
        move_path = []
        return

    # === Tarak special: Ambush (stealth-only burst) ===
    if ab.name == "Ambush":
        if not hero.stealthed:
            floating_texts.append(FloatingText(hero.x, hero.y - 30, "Must be stealthed!", (255, 150, 100)))
            return
        if not clicked_monster:
            floating_texts.append(FloatingText(hero.x, hero.y - 30, "No target!", (255, 150, 100)))
            return
        dist_to_target = hero.distance_to(clicked_monster)
        if dist_to_target > ab.range:
            selected_target = clicked_monster
            move_path = []
            return
        ab.use()
        hero.swing_timer = hero.weapon_speed
        # Break stealth
        hero.stealthed = False
        # Damage: 3x weapon + 20% target max HP
        dmg_amount = ab.calc_damage(hero.base_damage) + clicked_monster.max_hp * 0.2
        dmg = clicked_monster.take_damage(dmg_amount)
        floating_texts.append(FloatingText(clicked_monster.x, clicked_monster.y - 20, f"{dmg:.0f}", (255, 50, 50)))
        floating_texts.append(FloatingText(clicked_monster.x, clicked_monster.y - 40, "AMBUSH!", (255, 50, 50)))
        effects.append(AoeRing(clicked_monster.x, clicked_monster.y, 40, (255, 50, 50)))
        call_for_help(clicked_monster, game_state.monsters, hero)
        if hasattr(clicked_monster, 'aggro_state') and clicked_monster.aggro_state != "aggroed":
            from game.engine.ai import aggro_monster as _aggro
            _aggro(clicked_monster, hero, game_state.monsters)
        hero.gcd = hero.GCD_DURATION
        move_path = []
        selected_target = clicked_monster
        return

    # === Heskan special: Fire Blast (instant ranged single target) ===
    if ab.name == "Fire Blast":
        if not clicked_monster:
            floating_texts.append(FloatingText(hero.x, hero.y - 30, "No target!", (255, 150, 100)))
            return
        dist_to_target = hero.distance_to(clicked_monster)
        if dist_to_target > ab.range:
            floating_texts.append(FloatingText(hero.x, hero.y - 30, "Too far!", (255, 150, 100)))
            return
        ab.use()
        dmg_amount = ab.calc_damage(hero.base_damage)
        dmg = clicked_monster.take_damage(dmg_amount)
        floating_texts.append(FloatingText(clicked_monster.x, clicked_monster.y - 20, f"{dmg:.0f}", (255, 130, 50)))
        # Fire hit effect
        effects.append(AoeRing(clicked_monster.x, clicked_monster.y, 30, (255, 100, 0)))
        call_for_help(clicked_monster, game_state.monsters, hero)
        if hasattr(clicked_monster, 'aggro_state') and clicked_monster.aggro_state != "aggroed":
            from game.engine.ai import aggro_monster as _aggro
            _aggro(clicked_monster, hero, game_state.monsters)
        hero.gcd = hero.GCD_DURATION
        move_path = []
        return

    # === Heskan special: Frost Nova (AoE freeze around self) ===
    if ab.name == "Frost Nova":
        ab.use()
        dmg_amount = ab.calc_damage(hero.base_damage)  # 25% weapon
        hit_count = 0
        for m in game_state.alive_monsters:
            if hero.distance_to(m) <= ab.radius:
                dmg = m.take_damage(dmg_amount)
                m.apply_condition(Condition.FROZEN, 4.0)
                floating_texts.append(FloatingText(m.x, m.y - 20, f"{dmg:.0f}", (180, 220, 255)))
                floating_texts.append(FloatingText(m.x, m.y - 35, "FROZEN", (150, 220, 255)))
                hit_count += 1
        effects.append(AoeRing(hero.x, hero.y, ab.radius, (150, 200, 255)))
        if hit_count == 0:
            floating_texts.append(FloatingText(hero.x, hero.y - 30, "No enemies in range!", (200, 200, 200)))
        hero.gcd = hero.GCD_DURATION
        move_path = []
        return

    # === Heskan special: Frostbolt (start channel — fires on completion) ===
    if ab.name == "Frostbolt":
        if frostbolt_channeling:
            return  # Already channeling, wait for completion
        if not clicked_monster:
            floating_texts.append(FloatingText(hero.x, hero.y - 30, "No target!", (255, 150, 100)))
            return
        dist_to_target = hero.distance_to(clicked_monster)
        if dist_to_target > ab.range:
            # Walk into range, then start channeling
            selected_target = clicked_monster
            move_path = []
            return
        # Start channeling (immobilize self for weapon_speed duration)
        frostbolt_channeling = True
        frostbolt_channel_timer = hero.weapon_speed
        frostbolt_target = clicked_monster
        selected_target = clicked_monster
        hero.apply_condition(Condition.IMMOBILIZED, hero.weapon_speed)
        ab.use()  # Put on cooldown at start of channel (expires when channel ends)
        move_path = []
        return

    # === Quinn special: Wanding (ranged projectile auto-attack) ===
    if ab.name == "Wanding":
        if not clicked_monster:
            floating_texts.append(FloatingText(hero.x, hero.y - 30, "No target!", (255, 150, 100)))
            return
        dist_to_target = hero.distance_to(clicked_monster)
        if dist_to_target > ab.range:
            pending_cast = (ab_key, ab, clicked_monster); selected_target = clicked_monster
            return
        if hero.swing_timer > 0:
            return  # Gated by weapon speed
        ab.use()
        hero.swing_timer = hero.weapon_speed
        proj_damage = ab.calc_damage(hero.base_damage)
        proj = Projectile(x=hero.x, y=hero.y, target=clicked_monster,
                          speed=500.0, damage=proj_damage,
                          color=(255, 220, 100), source=hero)
        projectiles.append(proj)
        hero.gcd = hero.GCD_DURATION
        # Don't clear selected_target — keep auto-attacking
        move_path = []
        return

    # === Quinn special: Wall (absorb shield on self) ===
    if ab.name == "Wall":
        ab.use()
        shield_amount = hero.surge_value  # Same as potion amount (200)
        hero.absorb_shield = shield_amount
        hero.buffs["Wall"] = {"remaining": 15.0}
        floating_texts.append(FloatingText(hero.x, hero.y - 30, f"Wall +{shield_amount:.0f}!", (100, 200, 255)))
        hero.gcd = hero.GCD_DURATION
        move_path = []
        return

    # === Quinn special: Renew (HoT on self) ===
    if ab.name == "Renew":
        ab.use()
        hot_total = hero.surge_value * 0.5  # 50% of potion amount (100)
        hot_duration = 8.0
        hero.buffs["Renew"] = {"remaining": hot_duration, "hot_per_sec": hot_total / hot_duration}
        floating_texts.append(FloatingText(hero.x, hero.y - 30, "Renew!", (100, 255, 150)))
        hero.gcd = hero.GCD_DURATION
        move_path = []
        return

    # === Quinn special: Righteous Seal (self-buff, no target needed) ===
    if ab.name == "Righteous Seal":
        ab.use()
        hero.buffs["Righteous Seal"] = {"remaining": 10.0, "bonus": 0.25}
        floating_texts.append(FloatingText(hero.x, hero.y - 30, "Seal Active!", (255, 220, 80)))
        hero.gcd = hero.GCD_DURATION
        move_path = []
        return

    # === Quinn special: Holy Light (self-heal + immobilize self) ===
    if ab.name == "Holy Light":
        ab.use()
        # Start casting — immobilize for 2s, heal lands after cast finishes
        hero.apply_condition(Condition.IMMOBILIZED, 2.0)
        hero.buffs["Holy Light Casting"] = {"remaining": 2.0, "heal": 150}
        floating_texts.append(FloatingText(hero.x, hero.y - 30, "Casting...", (255, 255, 150)))
        hero.gcd = hero.GCD_DURATION
        move_path = []
        return

    # === Quinn special: Judgement (ranged, consumes Seal for bonus damage) ===
    if ab.name == "Judgement":
        if not clicked_monster:
            floating_texts.append(FloatingText(hero.x, hero.y - 30, "No target!", (255, 150, 100)))
            return
        dist_to_target = hero.distance_to(clicked_monster)
        if dist_to_target > ab.range:
            pending_cast = (ab_key, ab, clicked_monster); selected_target = clicked_monster
            return
        ab.use()
        total_damage = ab.calc_damage(hero.base_damage)
        # Consume Seal for bonus damage (doubles the damage)
        if "Righteous Seal" in hero.buffs:
            total_damage += hero.base_damage  # Bonus full weapon damage
            del hero.buffs["Righteous Seal"]
            floating_texts.append(FloatingText(clicked_monster.x, clicked_monster.y - 40, "Seal Consumed!", (255, 200, 50)))
        dmg = clicked_monster.take_damage(total_damage)
        floating_texts.append(FloatingText(clicked_monster.x, clicked_monster.y - 20, f"{dmg:.0f}", (255, 255, 150)))
        # Aggro the hit target + call for help
        if hasattr(clicked_monster, 'aggro_state') and clicked_monster.aggro_state != "aggroed":
            from game.engine.ai import aggro_monster as _aggro
            _aggro(clicked_monster, hero, game_state.monsters)
        call_for_help(clicked_monster, game_state.monsters, hero)
        hero.gcd = hero.GCD_DURATION
        move_path = []
        selected_target = None
        return

    # === Quinn special: Smite (boosted by Seal) ===
    if ab.name == "Smite":
        if not clicked_monster:
            floating_texts.append(FloatingText(hero.x, hero.y - 30, "No target!", (255, 150, 100)))
            return
        dist_to_target = hero.distance_to(clicked_monster)
        if dist_to_target > ab.range:
            pending_cast = (ab_key, ab, clicked_monster); selected_target = clicked_monster
            return
        if hero.swing_timer > 0:
            return  # Gated by weapon speed
        ab.use()
        hero.swing_timer = hero.weapon_speed
        bonus = 1.0 + (hero.buffs.get("Righteous Seal", {}).get("bonus", 0))
        skill_dmg = ab.calc_damage(hero.base_damage) * bonus
        dmg = clicked_monster.take_damage(skill_dmg)
        color = (255, 230, 100) if bonus > 1.0 else WHITE
        floating_texts.append(FloatingText(clicked_monster.x, clicked_monster.y - 20, f"{dmg:.0f}", color))
        call_for_help(clicked_monster, game_state.monsters, hero)
        hero.gcd = hero.GCD_DURATION
        move_path = []
        selected_target = None
        return

    # === Standard ability handling ===
    if ab.radius > 0:
        # AoE — check if click location is within ability range
        dist_to_click = math.sqrt((wx - hero.x)**2 + (wy - hero.y)**2)
        if dist_to_click > ab.range and ab.range > 0:
            pending_cast = (ab_key, ab, clicked_monster); selected_target = clicked_monster
            return
        hits = hero.use_ability(ab_key, game_state.alive_monsters, target_pos=(wx, wy))
        if hits:
            effects.append(AoeRing(wx, wy, ab.radius, ab.color))
            for name, dmg in hits:
                floating_texts.append(FloatingText(wx, wy-20, f"{dmg:.0f}", GOLD))
    elif clicked_monster:
        # Single target — check range
        dist_to_target = hero.distance_to(clicked_monster)
        if dist_to_target > ab.range:
            pending_cast = (ab_key, ab, clicked_monster); selected_target = clicked_monster
            return
        # Dash abilities: delay damage until arrival
        if ab.is_dash:
            ab.use()  # Put on cooldown
            dx = clicked_monster.x - hero.x
            dy = clicked_monster.y - hero.y
            d = math.sqrt(dx*dx + dy*dy)
            if d > 0:
                dash_target_x = clicked_monster.x - (dx/d) * 50
                dash_target_y = clicked_monster.y - (dy/d) * 50
                dash_active = True
                dash_stun_target = clicked_monster
                dash_stun_duration = ab.stun_duration
                # Store damage to apply on arrival
                dash_damage = ab.calc_damage(hero.base_damage)
            call_for_help(clicked_monster, game_state.monsters, hero)
        else:
            # Non-dash single target: deal damage immediately
            hits = hero.use_ability(ab_key, [clicked_monster])
            for name, dmg in hits:
                floating_texts.append(FloatingText(clicked_monster.x, clicked_monster.y-20, f"{dmg:.0f}", WHITE))
            if ab.stun_duration > 0 and clicked_monster.alive:
                clicked_monster.apply_condition(Condition.STUNNED, ab.stun_duration)
                floating_texts.append(FloatingText(clicked_monster.x, clicked_monster.y-35, "STUNNED", (255,255,100)))
            call_for_help(clicked_monster, game_state.monsters, hero)
    else:
        # No target clicked for single-target skill
        floating_texts.append(FloatingText(hero.x, hero.y - 30, "No target!", (255, 150, 100)))
        return
    hero.gcd = hero.GCD_DURATION
    move_path = []
    selected_target = None

# === MAIN GAME LOOP ===
running = True
while running:
    dt = clock.tick(60) / 1000.0 * game_speed

    for event in pygame.event.get():
        if event.type == pygame.QUIT: running = False
        if event.type == pygame.MOUSEWHEEL:
            cam_zoom = max(CAM_ZOOM_MIN, min(CAM_ZOOM_MAX, cam_zoom + event.y * CAM_ZOOM_STEP))
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                if frostbolt_channeling:
                    # Cancel channel and stop auto-attack
                    frostbolt_channeling = False
                    frostbolt_channel_timer = 0
                    frostbolt_target = None
                    selected_target = None
                    hero.conditions = [c for c in hero.conditions if c.condition != Condition.IMMOBILIZED]
                else:
                    running = False
            if event.key == pygame.K_TAB:
                ai_enabled = not ai_enabled
            # Game speed: +/- to cycle 1x/2x/4x
            if event.key == pygame.K_EQUALS or event.key == pygame.K_PLUS:
                game_speed = min(game_speed * 2, 4.0)
            if event.key == pygame.K_MINUS:
                game_speed = max(game_speed / 2, 1.0)
            # 1,2,3 = switch right-click skill
            if event.key == pygame.K_1: right_skill_idx = 0
            if event.key == pygame.K_2: right_skill_idx = 1
            if event.key == pygame.K_3: right_skill_idx = 2 if len(ability_keys) > 2 else right_skill_idx
            if event.key == pygame.K_4: right_skill_idx = 3 if len(ability_keys) > 3 else right_skill_idx
            # Shift+1,2,3 = switch left-click skill
            mods = pygame.key.get_mods()
            if mods & pygame.KMOD_CTRL:
                if event.key == pygame.K_1: left_skill_idx = 0
                if event.key == pygame.K_2: left_skill_idx = 1
                if event.key == pygame.K_3: left_skill_idx = 2 if len(ability_keys) > 2 else left_skill_idx
            # Potion
            if event.key == pygame.K_f and potions > 0 and hero.hp < hero.max_hp:
                potions -= 1
                heal = hero.heal(150)
                floating_texts.append(FloatingText(hero.x, hero.y-30, f"+{heal:.0f}", (100,255,100)))
            # Summon AI companions (F1-F4)
            summon_keys = [pygame.K_F1, pygame.K_F2, pygame.K_F3, pygame.K_F4]
            for ki, sk in enumerate(summon_keys):
                if event.key == sk and ki < len(available_companions):
                    comp_info = available_companions[ki]
                    # Check not already summoned
                    already = any(c.name == comp_info["name"] for c, _ in companions)
                    if not already:
                        cx, cy = find_walkable_nearby(hero.x, hero.y, radius=60)
                        comp = comp_info["create"](cx, cy)
                        comp.sprite = HERO_SPRITES[comp_info["sprite_key"]]
                        comp_ai = create_hero_ai(comp)
                        # Give AI access to all heroes for ally-targeting abilities
                        if hasattr(comp_ai, 'allies'):
                            comp_ai.allies = game_state.heroes
                        companions.append((comp, comp_ai))
                        game_state.heroes.append(comp)
                        floating_texts.append(FloatingText(cx, cy - 30, f"{comp.name} joined!", GOLD))
                    break

        if event.type == pygame.MOUSEBUTTONDOWN and not victory and not game_state.adventure_failed:
            mx_s, my_s = event.pos
            wx = (mx_s - WIDTH//2) / cam_zoom + hero.x
            wy = (my_s - HEIGHT//2) / cam_zoom + hero.y
            clicked_monster = get_monster_at_screen(mx_s, my_s)
            shift_held = pygame.key.get_mods() & pygame.KMOD_SHIFT

            if event.button == 1:  # Left-click
                if shift_held:
                    # Shift+Left = cast LEFT skill
                    ab_key = ability_keys[left_skill_idx]
                    ab = hero.abilities[ab_key]
                    if ab.is_ready():
                        _cast_ability(ab_key, ab, wx, wy, clicked_monster)
                elif my_s >= HEIGHT - 55:
                    # Clicked on skill bar area — switch skills
                    if mx_s < WIDTH//2:
                        # Clicked left skill box — cycle left skill
                        left_skill_idx = (left_skill_idx + 1) % len(ability_keys)
                    else:
                        # Clicked right skill box — cycle right skill
                        right_skill_idx = (right_skill_idx + 1) % len(ability_keys)
                elif clicked_monster:
                    # Click enemy = select + walk to attack range
                    # Cancel any active channel
                    if frostbolt_channeling:
                        frostbolt_channeling = False
                        frostbolt_target = None
                        hero.conditions = [c for c in hero.conditions if c.condition != Condition.IMMOBILIZED]
                        hero.swing_timer = 0.5  # Brief delay after cancel
                    selected_target = clicked_monster
                    move_path = []
                else:
                    # Click ground = move (cancel channel)
                    if frostbolt_channeling:
                        frostbolt_channeling = False
                        frostbolt_target = None
                        hero.conditions = [c for c in hero.conditions if c.condition != Condition.IMMOBILIZED]
                    move_path = astar(dungeon, hero.x, hero.y, wx, wy)
                    selected_target = None

            elif event.button == 3:  # Right-click = cast RIGHT skill
                # Stealth + right-click enemy + Ambush on right slot = queue ambush walk-to
                if hero.stealthed and clicked_monster and ability_keys[right_skill_idx] == "E":
                    ab_ambush = hero.abilities.get("E")
                    if ab_ambush and ab_ambush.is_ready():
                        ambush_target = clicked_monster
                        selected_target = None
                        move_path = []
                    else:
                        floating_texts.append(FloatingText(hero.x, hero.y - 30, "Ambush on CD!", (255, 150, 100)))
                else:
                    ab_key = ability_keys[right_skill_idx]
                    ab = hero.abilities[ab_key]
                    if ab.is_ready():
                        _cast_ability(ab_key, ab, wx, wy, clicked_monster)
                    else:
                        # Skill on cooldown — just move instead
                        move_path = astar(dungeon, hero.x, hero.y, wx, wy)
                        selected_target = None

    # --- End screen ---
    if victory or game_state.adventure_failed:
        screen.fill(BG)
        msg = "VICTORY! You escaped the tunnel!" if victory else "DEFEATED..."
        t = title_font.render(msg, True, GOLD if victory else HP_RED)
        screen.blit(t, (WIDTH//2-t.get_width()//2, HEIGHT//2-20))
        stats = f"Time: {game_state.game_time:.1f}s  HP: {hero.hp:.0f}/{hero.max_hp}  Kills: {hero.kills}"
        screen.blit(big_font.render(stats, True, WHITE), (WIDTH//2-150, HEIGHT//2+20))
        screen.blit(font.render("Press ESC to quit (auto-closing in 5s)", True, GRAY), (WIDTH//2-100, HEIGHT//2+55))
        pygame.display.flip()
        if auto_mode:
            print(f"RESULT: {'VICTORY' if victory else 'DEFEATED'} time={game_state.game_time:.1f}s hp={hero.hp:.0f}/{hero.max_hp} kills={hero.kills}", flush=True)
            pygame.time.wait(5000)
            running = False
        continue

    # --- UPDATE ---
    # Check Holy Light cast completion BEFORE update (buff gets removed during update)
    if "Holy Light Casting" in hero.buffs and hero.buffs["Holy Light Casting"]["remaining"] <= dt:
        heal_amount = hero.buffs["Holy Light Casting"]["heal"]
        heal = hero.heal(heal_amount)
        floating_texts.append(FloatingText(hero.x, hero.y - 30, f"+{heal:.0f} HP", (100, 255, 100)))
        del hero.buffs["Holy Light Casting"]

    game_state.update(dt)
    alive = game_state.alive_monsters

    # Frostbolt channel completion
    if frostbolt_channeling:
        frostbolt_channel_timer -= dt
        if frostbolt_channel_timer <= 0:
            frostbolt_channeling = False
            # Fire projectile if target still alive (range doesn't matter — bolt chases)
            if frostbolt_target and frostbolt_target.alive:
                proj_damage = hero.base_damage  # 100% weapon
                proj = Projectile(x=hero.x, y=hero.y, target=frostbolt_target,
                                  speed=500.0, damage=proj_damage,
                                  color=(150, 200, 255), source=hero)
                proj.apply_slow = True  # Flag for slow on hit
                projectiles.append(proj)
            else:
                # Target dead — stop
                frostbolt_target = None
                selected_target = None
        # If target died mid-channel, cancel
        elif frostbolt_target and not frostbolt_target.alive:
            frostbolt_channeling = False
            frostbolt_target = None
            selected_target = None
            # Remove immobilize early
            hero.conditions = [c for c in hero.conditions if c.condition != Condition.IMMOBILIZED]

    # Smooth movement along path
    # Clear exploration path if AI is in combat
    if ai_enabled and game_state.alive_monsters and move_path:
        move_path = []

    if move_path and not dash_active and not hero.has_condition(Condition.IMMOBILIZED):
        tx, ty = move_path[0]
        dx, dy = tx - hero.x, ty - hero.y
        dist = math.sqrt(dx*dx + dy*dy)
        if dist < 8:
            move_path.pop(0)
        else:
            spd = hero.base_speed * dt
            if hero.stealthed:
                spd *= 0.6  # 60% move speed while stealthed
            hero.x += (dx/dist) * min(spd, dist)
            hero.y += (dy/dist) * min(spd, dist)
            hero.facing_left = dx < 0

    # Dash animation (Charge skill)
    if dash_active:
        dx = dash_target_x - hero.x
        dy = dash_target_y - hero.y
        dist = math.sqrt(dx*dx + dy*dy)
        if dist < 10:
            # Arrived — deal damage + apply stun
            dash_active = False
            hero.x = dash_target_x
            hero.y = dash_target_y
            if dash_stun_target and dash_stun_target.alive:
                dmg = dash_stun_target.take_damage(dash_damage)
                floating_texts.append(FloatingText(dash_stun_target.x, dash_stun_target.y-20, f"{dmg:.0f}", (255, 200, 50)))
                if dash_stun_duration > 0 and dash_stun_target.alive:
                    dash_stun_target.apply_condition(Condition.STUNNED, dash_stun_duration)
                    floating_texts.append(FloatingText(dash_stun_target.x, dash_stun_target.y-35, "STUNNED", (255,255,100)))
            dash_stun_target = None
            dash_damage = 0
        else:
            spd = dash_speed * dt
            hero.x += (dx/dist) * min(spd, dist)
            hero.y += (dy/dist) * min(spd, dist)
            hero.facing_left = dx < 0

    # === HERO AI (when enabled) ===
    if ai_enabled and not dash_active:
        ai_action = hero_ai.update(game_state.alive_monsters, dt, is_wall)
        
        # Debug log
        if DEBUG and int(game_state.game_time * 2) != int((game_state.game_time - dt) * 2):  # Log every 0.5s
            alive_count = len(game_state.alive_monsters)
            target_dist = f" target_dist={hero.distance_to(hero_ai.target):.0f}" if hero_ai.target and hero_ai.target.alive else ""
            target_hp = f" boss_hp={hero_ai.target.hp:.0f}/{hero_ai.target.max_hp}" if hero_ai.target and hero_ai.target.alive else ""
            action_name = ai_action['use_ability'] or ('DASH' if ai_action.get('dash') else ('MOVE' if ai_action.get('move_to') else ('BASIC_ATK' if ai_action.get('basic_attack') else ('EXPLORE' if not alive_count else 'IDLE'))))
            print(f"[AI t={game_state.game_time:.1f}s] monsters={alive_count} hp={hero.hp:.0f}/{hero.max_hp} pos=({hero.x:.0f},{hero.y:.0f}) action={action_name}{target_dist}{target_hp}", flush=True)
            # Log all alive units
            for m in game_state.alive_monsters:
                dist_to_hero = hero.distance_to(m)
                print(f"  [MOB] {m.name} pos=({m.x:.0f},{m.y:.0f}) hp={m.hp:.0f}/{m.max_hp} dist={dist_to_hero:.0f} aggro={getattr(m, 'aggro_state', '?')}", flush=True)
            for comp, _ in companions:
                if comp.alive:
                    print(f"  [COMP] {comp.name} pos=({comp.x:.0f},{comp.y:.0f}) hp={comp.hp:.0f}/{comp.max_hp} dist_to_hero={hero.distance_to(comp):.0f}", flush=True)

        if ai_action["use_potion"] and potions > 0 and hero.hp < hero.max_hp:
            potions -= 1
            heal = hero.heal(150)
            floating_texts.append(FloatingText(hero.x, hero.y-30, f"+{heal:.0f}", (100,255,100)))

        if ai_action["dash"]:
            # Charge ability
            tx, ty, target_m, dmg, stun = ai_action["dash"]
            ab = hero.abilities.get("R")
            if ab and ab.is_ready():
                ab.use()
                dash_target_x, dash_target_y = tx, ty
                dash_active = True
                dash_stun_target = target_m
                dash_stun_duration = stun
                dash_damage = dmg
                call_for_help(target_m, game_state.monsters, hero)

        elif ai_action["use_ability"]:
            ab_key = ai_action["use_ability"]
            ab = hero.abilities.get(ab_key)
            if ab and ab.is_ready():
                target_m = ai_action.get("ability_target_monster")
                # Route through _cast_ability for consistent handling (Quinn specials, etc.)
                wx = target_m.x if target_m else hero.x
                wy = target_m.y if target_m else hero.y
                _cast_ability(ab_key, ab, wx, wy, target_m)

        elif ai_action["move_to"] and not move_path:
            tx, ty = ai_action["move_to"]
            # Try direct movement first
            old_x, old_y = hero.x, hero.y
            hero.move_toward(tx, ty, dt, is_wall)
            hero.facing_left = (tx - hero.x) < 0
            # If stuck (didn't move), use pathfinding
            if abs(hero.x - old_x) < 0.5 and abs(hero.y - old_y) < 0.5:
                move_path = astar(dungeon, hero.x, hero.y, tx, ty)

        else:
            # No enemies and no action — explore! Move toward next unexplored room
            if not USE_MAP:
                for r in dungeon.rooms:
                    if not r.explored:
                        target_x = r.center_x * TILE_SIZE
                        target_y = r.center_y * TILE_SIZE
                        # Use pathfinding for exploration
                        if not move_path:
                            move_path = astar(dungeon, hero.x, hero.y, target_x, target_y)
                        break

    # Ambush walk-to: walk toward target in stealth, execute Ambush when in range
    if ambush_target and not ai_enabled:
        if not ambush_target.alive or not hero.stealthed:
            ambush_target = None
        else:
            dist = hero.distance_to(ambush_target)
            ab_ambush = hero.abilities.get("E")
            if dist <= 55 and ab_ambush and ab_ambush.is_ready():
                # In range — execute Ambush
                _cast_ability("E", ab_ambush, ambush_target.x, ambush_target.y, ambush_target)
                ambush_target = None
            else:
                # Walk toward target at stealth speed
                hero.move_toward(ambush_target.x, ambush_target.y, dt, is_wall)

    # Auto-attack selected target (walk to range, attack when close)
    if selected_target and not ai_enabled and not frostbolt_channeling and not hero.stealthed and not hero.has_condition(Condition.IMMOBILIZED):
        if not selected_target.alive:
            selected_target = None
            pending_cast = None
        else:
            dist = hero.distance_to(selected_target)
            # Check if we have a queued ability to fire
            if pending_cast and dist <= pending_cast[1].range:
                ab_key, ab, target_m = pending_cast
                pending_cast = None
                if ab.is_ready() and hero.gcd <= 0:
                    _cast_ability(ab_key, ab, target_m.x, target_m.y, target_m)
            elif dist <= hero.attack_range:
                # In range — use left-click skill
                ab_key = ability_keys[left_skill_idx]
                ab = hero.abilities[ab_key]
                if ab.is_ready() and hero.gcd <= 0 and hero.swing_timer <= 0:
                    _cast_ability(ab_key, ab, selected_target.x, selected_target.y, selected_target)
            elif not (pygame.key.get_mods() & pygame.KMOD_SHIFT):
                # Out of range and shift NOT held — walk toward target
                hero.move_toward(selected_target.x, selected_target.y, dt, is_wall)

    # === COMPANION AI ===
    for comp, comp_ai in companions:
        if not comp.alive:
            continue
        # Track stealth duration
        if comp.stealthed:
            comp._stealth_time = getattr(comp, '_stealth_time', 0) + dt
        comp_action = comp_ai.update(game_state.alive_monsters, dt, is_wall)

        if comp_action.get("use_potion") and comp.hp < comp.max_hp * 0.4:
            heal = comp.heal(150)
            if heal:
                floating_texts.append(FloatingText(comp.x, comp.y - 30, f"+{heal:.0f}", (100, 255, 100)))

        if comp_action.get("use_ability"):
            ab_key = comp_action["use_ability"]
            ab = comp.abilities.get(ab_key)
            if ab and ab.is_ready() and comp.gcd <= 0:
                target_m = comp_action.get("ability_target_monster")

                # Handle dash abilities (Charge) — just teleport + damage for companions
                if comp_action.get("dash"):
                    tx, ty, dash_target, dash_dmg, dash_stun = comp_action["dash"]
                    if dash_target and dash_target.alive and comp.distance_to(dash_target) <= 300:
                        ab.use()
                        comp.x, comp.y = tx, ty
                        dmg = dash_target.take_damage(dash_dmg)
                        floating_texts.append(FloatingText(dash_target.x, dash_target.y - 20, f"{dmg:.0f}", (255, 200, 50)))
                        if dash_stun > 0 and dash_target.alive:
                            dash_target.apply_condition(Condition.STUNNED, dash_stun)
                        call_for_help(dash_target, game_state.monsters, hero)
                elif ab.name == "Frost Nova":
                    # Heskan's AoE freeze — specific handler (bypasses swing_timer)
                    ab.use()
                    comp.gcd = comp.GCD_DURATION
                    dmg_amount = ab.calc_damage(comp.base_damage)
                    hit_count = 0
                    for m in game_state.alive_monsters:
                        if comp.distance_to(m) <= ab.radius:
                            dmg = m.take_damage(dmg_amount)
                            m.apply_condition(Condition.FROZEN, 4.0)
                            floating_texts.append(FloatingText(m.x, m.y - 20, f"{dmg:.0f}", (180, 220, 255)))
                            hit_count += 1
                    print(f"[COMP_SKILL] {comp.name} Frost Nova hit {hit_count} targets", flush=True) if DEBUG else None
                    effects.append(AoeRing(comp.x, comp.y, ab.radius, (150, 200, 255)))
                elif ab.radius > 0:
                    # AoE (generic)
                    hits = comp.use_ability(ab_key, game_state.alive_monsters, target_pos=(comp.x, comp.y))
                    if hits:
                        effects.append(AoeRing(comp.x, comp.y, ab.radius, ab.color))
                        for name, dmg in hits:
                            floating_texts.append(FloatingText(comp.x, comp.y - 20, f"{dmg:.0f}", GOLD))
                elif ab.name == "Wanding" and target_m and target_m.alive:
                    # Quinn's ranged projectile
                    if comp.swing_timer <= 0 and comp.distance_to(target_m) <= ab.range:
                        ab.use()
                        comp.swing_timer = comp.weapon_speed
                        proj_damage = ab.calc_damage(comp.base_damage)
                        proj = Projectile(x=comp.x, y=comp.y, target=target_m,
                                          speed=500.0, damage=proj_damage,
                                          color=(255, 220, 100), source=comp)
                        projectiles.append(proj)
                elif ab.name == "Wall":
                    # Quinn's shield — on target ally
                    ab.use()
                    wall_target = comp_action.get("ability_target_ally", comp)
                    wall_target.absorb_shield = comp.surge_value
                    wall_target.buffs["Wall"] = {"remaining": 15.0}
                    floating_texts.append(FloatingText(wall_target.x, wall_target.y - 30, f"Wall!", (100, 180, 255)))
                elif ab.name == "Renew":
                    # Quinn's HoT — on target ally
                    ab.use()
                    renew_target = comp_action.get("ability_target_ally", comp)
                    hot_total = comp.surge_value * 0.5
                    renew_target.buffs["Renew"] = {"remaining": 8.0, "hot_per_sec": hot_total / 8.0}
                    floating_texts.append(FloatingText(renew_target.x, renew_target.y - 30, "Renew!", (100, 255, 150)))
                elif ab.name == "Frostbolt" and target_m and target_m.alive:
                    # Heskan's channeled bolt — simplified for companion (instant projectile)
                    if comp.swing_timer <= 0 and comp.distance_to(target_m) <= ab.range:
                        ab.use()
                        comp.swing_timer = comp.weapon_speed
                        proj_damage = ab.calc_damage(comp.base_damage)
                        proj = Projectile(x=comp.x, y=comp.y, target=target_m,
                                          speed=500.0, damage=proj_damage,
                                          color=(150, 200, 255), source=comp)
                        proj.apply_slow = True
                        projectiles.append(proj)
                elif ab.name == "Fire Blast" and target_m and target_m.alive:
                    # Heskan's instant nuke
                    if comp.distance_to(target_m) <= ab.range:
                        ab.use()
                        dmg_amount = ab.calc_damage(comp.base_damage)
                        dmg = target_m.take_damage(dmg_amount)
                        print(f"[COMP_SKILL] {comp.name} Fire Blast -> {target_m.name} for {dmg:.0f}", flush=True) if DEBUG else None
                        floating_texts.append(FloatingText(target_m.x, target_m.y - 20, f"{dmg:.0f}", (255, 130, 50)))
                        effects.append(AoeRing(target_m.x, target_m.y, 30, (255, 100, 0)))
                        # Aggro
                        if hasattr(target_m, 'aggro_state') and target_m.aggro_state != "aggroed":
                            from game.engine.ai import aggro_monster as _aggro
                            _aggro(target_m, comp, game_state.monsters)
                        call_for_help(target_m, game_state.monsters, comp)
                elif ab.name == "Stealth":
                    # Tarak's stealth
                    ab.use()
                    comp.stealthed = True
                    comp.gcd = comp.GCD_DURATION
                    comp._stealth_time = 0.0  # Track how long stealthed
                    # Drop aggro (except bosses)
                    for m in game_state.alive_monsters:
                        if hasattr(m, 'aggro_target') and m.aggro_target == comp and not m.is_boss:
                            from game.engine.ai import AggroState
                            m.aggro_state = AggroState.RESETTING
                            m.aggro_target = None
                elif ab.name == "Ambush" and target_m and target_m.alive:
                    # Tarak's stealth burst — need at least 0.5s in stealth
                    stealth_time = getattr(comp, '_stealth_time', 0)
                    if comp.stealthed and stealth_time >= 0.5 and comp.distance_to(target_m) <= ab.range:
                        ab.use()
                        comp.stealthed = False
                        dmg_amount = ab.calc_damage(comp.base_damage) + target_m.max_hp * 0.2
                        dmg = target_m.take_damage(dmg_amount)
                        floating_texts.append(FloatingText(target_m.x, target_m.y - 20, f"{dmg:.0f}", (255, 50, 50)))
                        floating_texts.append(FloatingText(target_m.x, target_m.y - 40, "AMBUSH!", (255, 50, 50)))
                        call_for_help(target_m, game_state.monsters, hero)
                elif ab.name == "Stab" and target_m and target_m.alive:
                    # Tarak's fast melee
                    if comp.swing_timer <= 0 and comp.distance_to(target_m) <= ab.range:
                        ab.use()
                        comp.swing_timer = comp.weapon_speed
                        if comp.stealthed:
                            comp.stealthed = False
                        dmg_amount = ab.calc_damage(comp.base_damage)
                        dmg = target_m.take_damage(dmg_amount)
                        floating_texts.append(FloatingText(target_m.x, target_m.y - 20, f"{dmg:.0f}", (180, 255, 180)))
                        call_for_help(target_m, game_state.monsters, comp)
                        if hasattr(target_m, 'aggro_state') and target_m.aggro_state != "aggroed":
                            from game.engine.ai import aggro_monster as _aggro
                            _aggro(target_m, comp, game_state.monsters)
                        call_for_help(target_m, game_state.monsters, hero)
                elif ab.name == "Smite" and target_m and target_m.alive:
                    # Keyleth's melee
                    if comp.swing_timer <= 0 and comp.distance_to(target_m) <= ab.range:
                        ab.use()
                        comp.swing_timer = comp.weapon_speed
                        bonus = 1.0 + (comp.buffs.get("Righteous Seal", {}).get("bonus", 0))
                        dmg_amount = ab.calc_damage(comp.base_damage) * bonus
                        dmg = target_m.take_damage(dmg_amount)
                        floating_texts.append(FloatingText(target_m.x, target_m.y - 20, f"{dmg:.0f}", WHITE))
                        call_for_help(target_m, game_state.monsters, comp)
                        if hasattr(target_m, 'aggro_state') and target_m.aggro_state != "aggroed":
                            from game.engine.ai import aggro_monster as _aggro
                            _aggro(target_m, comp, game_state.monsters)
                elif ab.name == "Righteous Seal":
                    # Keyleth's self-buff
                    ab.use()
                    comp.buffs["Righteous Seal"] = {"remaining": 10.0, "bonus": 0.25}
                elif ab.name == "Judgement" and target_m and target_m.alive:
                    # Keyleth's ranged holy bolt
                    if comp.distance_to(target_m) <= ab.range:
                        ab.use()
                        total_damage = ab.calc_damage(comp.base_damage)
                        if "Righteous Seal" in comp.buffs:
                            total_damage += comp.base_damage
                            del comp.buffs["Righteous Seal"]
                        dmg = target_m.take_damage(total_damage)
                        floating_texts.append(FloatingText(target_m.x, target_m.y - 20, f"{dmg:.0f}", (255, 255, 150)))
                        call_for_help(target_m, game_state.monsters, hero)
                elif ab.name == "Holy Light":
                    # Keyleth's self-heal
                    ab.use()
                    heal = comp.heal(150)
                    if heal:
                        floating_texts.append(FloatingText(comp.x, comp.y - 30, f"+{heal:.0f}", (100, 255, 100)))
                elif target_m and target_m.alive:
                    # Generic fallback
                    if comp.distance_to(target_m) <= ab.range and comp.swing_timer <= 0:
                        hits = comp.use_ability(ab_key, [target_m])
                        for name, dmg in hits:
                            floating_texts.append(FloatingText(target_m.x, target_m.y - 20, f"{dmg:.0f}", WHITE))
                            call_for_help(target_m, game_state.monsters, hero)

        elif comp_action.get("move_to"):
            tx, ty = comp_action["move_to"]
            old_x, old_y = comp.x, comp.y
            comp.move_toward(tx, ty, dt, is_wall)
            # If stuck, pathfind
            if abs(comp.x - old_x) < 0.5 and abs(comp.y - old_y) < 0.5:
                path = astar(dungeon, comp.x, comp.y, tx, ty)
                if path:
                    comp.move_toward(path[0][0], path[0][1], dt, is_wall)

        else:
            # No combat action — follow the hero
            dist_to_hero = comp.distance_to(hero)
            if dist_to_hero > 600:
                # Too far — teleport to hero (walkable position)
                comp.x, comp.y = find_walkable_nearby(hero.x, hero.y, radius=60)
                comp._follow_path = None
            elif dist_to_hero > 80:
                # Recalculate path every time (hero moves)
                comp._follow_path = astar(dungeon, comp.x, comp.y, hero.x, hero.y)
            else:
                comp._follow_path = None

            # Walk along path
            if hasattr(comp, '_follow_path') and comp._follow_path:
                tx, ty = comp._follow_path[0]
                d = math.sqrt((tx - comp.x)**2 + (ty - comp.y)**2)
                if d < 12:
                    comp._follow_path.pop(0)
                else:
                    spd = comp.base_speed * dt
                    nx = comp.x + ((tx - comp.x) / d) * min(spd, d)
                    ny = comp.y + ((ty - comp.y) / d) * min(spd, d)
                    if not is_wall(nx, ny):
                        comp.x = nx
                        comp.y = ny
                    elif not is_wall(nx, comp.y):
                        comp.x = nx
                    elif not is_wall(comp.x, ny):
                        comp.y = ny
                    else:
                        comp._follow_path = None
                    comp.facing_left = (tx - comp.x) < 0

    # Room exploration — spawn monsters when hero enters new room (dungeon mode only)
    if not USE_MAP:
        new_room = dungeon.update_exploration(hero.x, hero.y)
        if new_room:
            spawn_monsters_for_room(new_room)

    # Monster AI — all alive monsters with aggro system
    all_heroes = [h for h in game_state.heroes if h.alive]
    for m in alive:
        result = run_monster_ai(m, all_heroes, dt, is_wall, all_monsters=game_state.monsters)
        if result and result[0] in ("attack", "ranged_attack", "aoe_attack"):
            hit_hero = result[1]
            floating_texts.append(FloatingText(hit_hero.x+random.randint(-10,10), hit_hero.y-30, f"{result[2]:.0f}", HP_RED))
        elif result and result[0] == "ranged_attack_projectile":
            target_hero = result[1]
            proj_damage = result[2]
            proj = Projectile(x=m.x, y=m.y, target=target_hero,
                              speed=350.0, damage=proj_damage,
                              color=(255, 80, 80), source=m)
            proj.on_hit_condition = m.on_hit_condition
            projectiles.append(proj)

    # Kills
    for m in game_state.monsters:
        if not m.alive and m.experience > 0:
            hero.xp += m.experience
            hero.gold += random.randint(10,30) * m.experience
            hero.kills += 1
            floating_texts.append(FloatingText(m.x, m.y+10, f"+{m.experience}xp", GOLD))
            m.experience = 0
            if m.is_boss:
                # Victory only when ALL bosses are dead
                all_bosses_dead = all(not b.alive for b in game_state.monsters if b.is_boss)
                if all_bosses_dead:
                    victory = True

    if not hero.alive:
        game_state.check_hero_death(hero)

    floating_texts = [t for t in floating_texts if t.timer > 0]
    for t in floating_texts: t.update(dt)
    effects = [e for e in effects if e.timer > 0]
    for e in effects: e.update(dt)

    # Update projectiles
    for proj in projectiles:
        result = proj.update(dt)
        if result is not None:
            dmg, hit_target = result
            # Determine color based on who fired
            # Determine if source is a hero (player or companion)
            source_is_hero = (proj.source == hero) or any(proj.source == c for c, _ in companions)
            if source_is_hero:
                floating_texts.append(FloatingText(hit_target.x, hit_target.y - 20, f"{dmg:.0f}", proj.color))
                # Aggro on hit: directly aggro the hit monster + call for help
                if hasattr(hit_target, 'aggro_state'):
                    from game.engine.ai import aggro_monster, call_for_help as cfh
                    if hit_target.aggro_state != "aggroed":
                        aggro_monster(hit_target, proj.source, game_state.monsters)
                    cfh(hit_target, game_state.monsters, proj.source)
                # Frostbolt slow
                if getattr(proj, 'apply_slow', False) and hit_target.alive:
                    hit_target.apply_condition(Condition.SLOWED, 3.0, slow_factor=0.25)
                    floating_texts.append(FloatingText(hit_target.x, hit_target.y - 35, "SLOWED", (150, 200, 255)))
            else:
                # Monster projectile hitting hero
                floating_texts.append(FloatingText(hit_target.x + random.randint(-10, 10), hit_target.y - 30, f"{dmg:.0f}", HP_RED))
                # Apply on-hit condition if any
                on_hit = getattr(proj, 'on_hit_condition', None)
                if on_hit and hit_target.alive:
                    cond, dur = on_hit
                    hit_target.apply_condition(cond, dur,
                                              tick_damage=10.0 if cond == Condition.POISONED else 0)
    projectiles = [p for p in projectiles if p.alive]

    # Expire Wall shield when buff expires
    if "Wall" not in hero.buffs and hero.absorb_shield > 0:
        hero.absorb_shield = 0

    # --- FRAME LOG ---
    if DEBUG:
        print(f"[FRAME t={game_state.game_time:.2f}s] hero=({hero.x:.0f},{hero.y:.0f}) hp={hero.hp:.0f}/{hero.max_hp} monsters={len(game_state.alive_monsters)}", flush=True)
        for m in game_state.alive_monsters:
            print(f"  [MOB] {m.name} pos=({m.x:.0f},{m.y:.0f}) hp={m.hp:.0f}/{m.max_hp} dist={hero.distance_to(m):.0f} aggro={getattr(m, 'aggro_state', '?')}", flush=True)
        for comp, _ in companions:
            if comp.alive:
                print(f"  [COMP] {comp.name} pos=({comp.x:.0f},{comp.y:.0f}) hp={comp.hp:.0f}/{comp.max_hp} dist={hero.distance_to(comp):.0f}", flush=True)

    # --- RENDER ---
    screen.fill(BG)
    cx, cy = hero.x, hero.y

    # Draw visible tiles
    ztile = int(TILE_SIZE * cam_zoom)  # Tile size on screen after zoom
    view_left = int((cx - WIDTH//2 / cam_zoom) // TILE_SIZE) - 1
    view_top = int((cy - HEIGHT//2 / cam_zoom) // TILE_SIZE) - 1
    view_right = view_left + int(WIDTH / ztile) + 3
    view_bottom = view_top + int(HEIGHT / ztile) + 3

    if USE_MAP:
        # World map rendering — draw tiles from spritesheet data
        for ty in range(max(0, view_top), min(world_map.height, view_bottom)):
            for tx in range(max(0, view_left), min(world_map.width, view_right)):
                sx = int((tx * TILE_SIZE - cx) * cam_zoom + WIDTH//2)
                sy = int((ty * TILE_SIZE - cy) * cam_zoom + HEIGHT//2)
                # Ground layer
                ground_tile = world_map.ground[ty][tx] if world_map.ground else None
                if ground_tile:
                    key = (ground_tile.col, ground_tile.row, ztile)
                    if key not in rpg_tile_cache:
                        rpg_tile_cache[key] = pygame.transform.scale(
                            get_rpg_tile_raw(ground_tile.col, ground_tile.row), (ztile, ztile))
                    screen.blit(rpg_tile_cache[key], (sx, sy))
                # Objects layer
                obj_tile = world_map.objects[ty][tx] if world_map.objects else None
                if obj_tile:
                    key = (obj_tile.col, obj_tile.row, ztile)
                    if key not in rpg_tile_cache:
                        rpg_tile_cache[key] = pygame.transform.scale(
                            get_rpg_tile_raw(obj_tile.col, obj_tile.row), (ztile, ztile))
                    screen.blit(rpg_tile_cache[key], (sx, sy))
    else:
        # Dungeon rendering (original fog-of-war system)
        for ty in range(max(0, view_top), min(dungeon.grid_h, view_bottom)):
            for tx in range(max(0, view_left), min(dungeon.grid_w, view_right)):
                tile = dungeon.tiles[ty][tx]
                if tile == "wall":
                    visible = False
                    for ddy in range(-1, 2):
                        for ddx in range(-1, 2):
                            ntx, nty = tx+ddx, ty+ddy
                            if 0 <= nty < dungeon.grid_h and 0 <= ntx < dungeon.grid_w:
                                if dungeon.tiles[nty][ntx] == "floor":
                                    for r in dungeon.rooms:
                                        if r.explored and r.contains_tile(ntx, nty):
                                            visible = True
                                            break
                                    if not visible:
                                        for r in dungeon.rooms:
                                            if r.explored:
                                                if abs(ntx - r.center_x) < r.width and abs(nty - r.center_y) < r.height + 5:
                                                    visible = True
                                                    break
                        if visible: break
                    if not visible:
                        continue
                    sx = int((tx * TILE_SIZE - cx) * cam_zoom + WIDTH//2)
                    sy = int((ty * TILE_SIZE - cy) * cam_zoom + HEIGHT//2)
                    screen.blit(SPR_WALL, (sx, sy))
                else:
                    visible = False
                    for r in dungeon.rooms:
                        if r.explored and r.contains_tile(tx, ty):
                            visible = True
                            break
                    if not visible:
                        for r in dungeon.rooms:
                            if r.explored:
                                if abs(tx - r.center_x) < r.width + 8 and abs(ty - r.center_y) < r.height + 4:
                                    visible = True
                                    break
                    if not visible:
                        continue
                    sx = int((tx * TILE_SIZE - cx) * cam_zoom + WIDTH//2)
                    sy = int((ty * TILE_SIZE - cy) * cam_zoom + HEIGHT//2)
                    screen.blit(SPR_FLOOR if (tx+ty) % 5 != 0 else SPR_FLOOR2, (sx, sy))

    # Move path dots
    for wp in move_path[:8]:
        sx = int((wp[0] - cx) * cam_zoom + WIDTH//2)
        sy = int((wp[1] - cy) * cam_zoom + HEIGHT//2)
        pygame.draw.circle(screen, (60, 120, 60), (sx, sy), max(2, int(3 * cam_zoom)))

    # Effects
    for e in effects: e.draw(screen, cx, cy)

    # Monsters
    for m in game_state.monsters:
        if not m.alive: continue
        spr = m.sprite
        if not spr: continue
        sw, sh = int(spr.get_width() * cam_zoom), int(spr.get_height() * cam_zoom)
        sx = int((m.x - cx) * cam_zoom + WIDTH//2 - sw//2)
        sy = int((m.y - cy) * cam_zoom + HEIGHT//2 - sh//2)
        if sx < -sw or sx > WIDTH or sy < -sh or sy > HEIGHT: continue
        s = pygame.transform.flip(spr, True, False) if m.facing_left else spr
        s = pygame.transform.scale(s, (sw, sh))
        if m.flash_timer > 0:
            f = s.copy(); f.fill((255,255,255,200), special_flags=pygame.BLEND_RGBA_ADD)
            screen.blit(f, (sx, sy))
        elif m.has_condition(Condition.FROZEN):
            f = s.copy(); f.fill((100,150,255,150), special_flags=pygame.BLEND_RGBA_ADD)
            screen.blit(f, (sx, sy))
            # Ice crystal indicator
            ice_surf = pygame.Surface((sw + 8, sh + 8), pygame.SRCALPHA)
            pygame.draw.circle(ice_surf, (150, 200, 255, 80), (sw//2 + 4, sh//2 + 4), sw//2 + 4, 2)
            screen.blit(ice_surf, (sx - 4, sy - 4))
        else:
            screen.blit(s, (sx, sy))
        if m.hp < m.max_hp:
            pygame.draw.rect(screen, HP_BG, (sx-1, sy-9, sw+2, 6))
            pygame.draw.rect(screen, HP_RED, (sx, sy-8, sw, 4))
            pygame.draw.rect(screen, HP_GREEN, (sx, sy-8, int(sw*m.hp/m.max_hp), 4))
        if m.is_boss:
            t = font.render(m.name, True, (255,100,100))
            screen.blit(t, (sx+sw//2-t.get_width()//2, sy-20))
        if m == selected_target:
            pygame.draw.circle(screen, GOLD, (sx+sw//2, sy+sh//2), sw//2+4, 2)

    # Companions
    for comp, _ in companions:
        if not comp.alive:
            continue
        cspr = comp.sprite
        if not cspr:
            continue
        csw, csh = int(cspr.get_width() * cam_zoom), int(cspr.get_height() * cam_zoom)
        csx = int((comp.x - cx) * cam_zoom + WIDTH//2 - csw//2)
        csy = int((comp.y - cy) * cam_zoom + HEIGHT//2 - csh//2)
        if csx < -csw or csx > WIDTH or csy < -csh or csy > HEIGHT:
            continue
        cs = pygame.transform.flip(cspr, True, False) if comp.facing_left else cspr
        cs = pygame.transform.scale(cs, (csw, csh))
        if comp.stealthed:
            cs = cs.copy()
            cs.set_alpha(100)
        if comp.flash_timer > 0:
            f = cs.copy(); f.fill((200,50,50,100), special_flags=pygame.BLEND_RGBA_ADD)
            screen.blit(f, (csx, csy))
        else:
            screen.blit(cs, (csx, csy))
        # HP bar for companions
        if comp.hp < comp.max_hp:
            pygame.draw.rect(screen, HP_BG, (csx-1, csy-9, csw+2, 6))
            pygame.draw.rect(screen, (50, 50, 200), (csx, csy-8, csw, 4))
            pygame.draw.rect(screen, (100, 150, 255), (csx, csy-8, int(csw*comp.hp/comp.max_hp), 4))
        # Name tag
        nt = font.render(comp.name, True, (150, 180, 255))
        screen.blit(nt, (csx + csw//2 - nt.get_width()//2, csy - 20))

    # Projectiles
    for proj in projectiles:
        psx = int((proj.x - cx) * cam_zoom + WIDTH//2)
        psy = int((proj.y - cy) * cam_zoom + HEIGHT//2)
        # Monster arrows: draw as a rotated arrow shape
        if proj.color == (255, 80, 80) and proj.target and proj.target.alive:
            import math as _math
            dx = proj.target.x - proj.x
            dy = proj.target.y - proj.y
            dist = _math.sqrt(dx*dx + dy*dy)
            if dist > 0:
                # Arrow direction
                nx, ny = dx/dist, dy/dist
                # Perpendicular
                px, py = -ny, nx
                # Arrow shaft (line)
                length = int(14 * cam_zoom)
                shaft_start = (psx - nx*length//2, psy - ny*length//2)
                shaft_end = (psx + nx*length//2, psy + ny*length//2)
                pygame.draw.line(screen, (139, 90, 43), shaft_start, shaft_end, max(1, int(2 * cam_zoom)))
                # Arrowhead (small triangle at front)
                tip = (int(psx + nx*length//2 + nx*4*cam_zoom), int(psy + ny*length//2 + ny*4*cam_zoom))
                left = (int(shaft_end[0] + px*3*cam_zoom), int(shaft_end[1] + py*3*cam_zoom))
                right = (int(shaft_end[0] - px*3*cam_zoom), int(shaft_end[1] - py*3*cam_zoom))
                pygame.draw.polygon(screen, (180, 180, 180), [tip, left, right])
            else:
                pygame.draw.circle(screen, proj.color, (psx, psy), max(2, int(proj.radius * cam_zoom)))
        else:
            pygame.draw.circle(screen, proj.color, (psx, psy), max(2, int(proj.radius * cam_zoom)))
            # Glow trail
            pygame.draw.circle(screen, (*proj.color[:3], 100) if len(proj.color) == 4 else proj.color, (psx, psy), max(3, int(proj.radius * cam_zoom) + 3), 1)

    # Hero
    spr = hero.sprite
    sw, sh = int(spr.get_width() * cam_zoom), int(spr.get_height() * cam_zoom)
    sx = int((hero.x - cx) * cam_zoom + WIDTH//2 - sw//2)
    sy = int((hero.y - cy) * cam_zoom + HEIGHT//2 - sh//2)
    s = pygame.transform.flip(spr, True, False) if hero.facing_left else spr
    s = pygame.transform.scale(s, (sw, sh))
    if hero.stealthed:
        s = s.copy()
        s.set_alpha(100)  # Semi-transparent when stealthed
    elif hero.has_condition(Condition.POISONED):
        s = s.copy()
        s.fill((0, 80, 0, 0), special_flags=pygame.BLEND_RGBA_ADD)  # Green tint
    screen.blit(s, (sx, sy))

    # Poison drip visual
    if hero.has_condition(Condition.POISONED):
        pulse_p = int(60 + 30 * math.sin(game_state.game_time * 5))
        poison_surf = pygame.Surface((sw + 6, sh + 6), pygame.SRCALPHA)
        pygame.draw.circle(poison_surf, (50, 200, 50, pulse_p), (sw//2 + 3, sh//2 + 3), sw//2 + 3, 2)
        screen.blit(poison_surf, (sx - 3, sy - 3))

    # Wall bubble shield visual
    if hero.absorb_shield > 0:
        bubble_r = sw // 2 + 8
        bubble_cx = sx + sw // 2
        bubble_cy = sy + sh // 2
        # Pulsing alpha
        pulse = int(80 + 40 * math.sin(game_state.game_time * 4))
        bubble_surf = pygame.Surface((bubble_r * 2 + 4, bubble_r * 2 + 4), pygame.SRCALPHA)
        pygame.draw.circle(bubble_surf, (100, 180, 255, pulse), (bubble_r + 2, bubble_r + 2), bubble_r, 3)
        pygame.draw.circle(bubble_surf, (100, 180, 255, pulse // 3), (bubble_r + 2, bubble_r + 2), bubble_r)
        screen.blit(bubble_surf, (bubble_cx - bubble_r - 2, bubble_cy - bubble_r - 2))

    # Renew visual (green sparkle indicator)
    if "Renew" in hero.buffs:
        renew_r = sw // 2 + 4
        renew_cx = sx + sw // 2
        renew_cy = sy + sh // 2
        pulse_g = int(60 + 30 * math.sin(game_state.game_time * 6))
        renew_surf = pygame.Surface((renew_r * 2 + 4, renew_r * 2 + 4), pygame.SRCALPHA)
        pygame.draw.circle(renew_surf, (80, 255, 120, pulse_g), (renew_r + 2, renew_r + 2), renew_r, 2)
        screen.blit(renew_surf, (renew_cx - renew_r - 2, renew_cy - renew_r - 2))

    # Frostbolt channeling bar
    if frostbolt_channeling:
        bar_w = 40
        bar_h = 5
        bar_x = sx + sw // 2 - bar_w // 2
        bar_y = sy - 14
        progress = 1.0 - (frostbolt_channel_timer / hero.weapon_speed)
        pygame.draw.rect(screen, (30, 30, 60), (bar_x - 1, bar_y - 1, bar_w + 2, bar_h + 2))
        pygame.draw.rect(screen, (60, 60, 80), (bar_x, bar_y, bar_w, bar_h))
        pygame.draw.rect(screen, (150, 200, 255), (bar_x, bar_y, int(bar_w * progress), bar_h))

    # Floating text
    for t in floating_texts: t.draw(screen, cx, cy)

    # --- HUD ---
    hp_pct = hero.hp / hero.max_hp
    pygame.draw.rect(screen, HP_BG, (18,18,206,22))
    pygame.draw.rect(screen, HP_RED, (20,20,202,18))
    pygame.draw.rect(screen, HP_GREEN, (20,20,int(202*hp_pct),18))
    screen.blit(font.render(f"HP {hero.hp:.0f}/{hero.max_hp}", True, WHITE), (25,23))
    screen.blit(font.render(f"[F] Potions: {potions}  Lives: {game_state.life_tokens}", True, (200,150,150)), (20,44))

    # Skill list (left side)
    ab_y = 66
    for i, key in enumerate(ability_keys):
        ab = hero.abilities[key]
        ready = ab.is_ready()
        is_left = (i == left_skill_idx)
        is_right = (i == right_skill_idx)
        if is_right:
            bg_c = (60, 60, 140)
        elif is_left:
            bg_c = (140, 100, 40)
        else:
            bg_c = ABILITY_READY if ready else GRAY
        pygame.draw.rect(screen, bg_c, (20, ab_y, 200, 20))
        cd = "READY" if ready else f"{ab.remaining:.1f}s"
        slot_label = ""
        if is_left: slot_label = "[L] "
        if is_right: slot_label = "[R] "
        screen.blit(font.render(f"{slot_label}[{i+1}] {ab.name} {cd}", True, WHITE), (24, ab_y+3))
        ab_y += 24

    # Skill bar at bottom
    bar_y = HEIGHT - 50
    pygame.draw.rect(screen, (25, 25, 35), (0, bar_y - 5, WIDTH, 55))
    # Left skill
    left_ab = hero.abilities[ability_keys[left_skill_idx]]
    left_color = (180, 130, 50) if left_ab.is_ready() else (80, 60, 30)
    pygame.draw.rect(screen, left_color, (WIDTH//2 - 180, bar_y, 160, 30), 0, 4)
    pygame.draw.rect(screen, (220, 170, 60), (WIDTH//2 - 180, bar_y, 160, 30), 2, 4)
    screen.blit(font.render(f"L: {left_ab.name}", True, WHITE), (WIDTH//2 - 175, bar_y + 8))
    # Right skill
    right_ab = hero.abilities[ability_keys[right_skill_idx]]
    right_color = (50, 50, 140) if right_ab.is_ready() else (30, 30, 70)
    pygame.draw.rect(screen, right_color, (WIDTH//2 + 20, bar_y, 160, 30), 0, 4)
    pygame.draw.rect(screen, (80, 80, 200), (WIDTH//2 + 20, bar_y, 160, 30), 2, 4)
    screen.blit(font.render(f"R: {right_ab.name}", True, WHITE), (WIDTH//2 + 25, bar_y + 8))

    screen.blit(font.render(f"Kills: {hero.kills}  Gold: {hero.gold}", True, GOLD), (WIDTH-160, 20))
    if USE_MAP:
        screen.blit(font.render("Northshire", True, BLUE), (WIDTH-160, 40))
    else:
        screen.blit(font.render(f"Room: {dungeon.current_room.name}", True, BLUE), (WIDTH-160, 40))
    screen.blit(font.render(game_state.objective_text, True, (200,200,150)), (WIDTH//2-180, 10))

    # FPS counter
    fps = int(clock.get_fps())
    fps_color = HP_GREEN if fps >= 50 else (GOLD if fps >= 30 else HP_RED)
    screen.blit(font.render(f"FPS: {fps}", True, fps_color), (10, 10))

    # Minimap (dungeon mode only)
    mm_x, mm_y = WIDTH-120, HEIGHT-100
    if not USE_MAP:
        pygame.draw.rect(screen, (30,30,40), (mm_x-5, mm_y-5, 110, 90))
        for r in dungeon.rooms:
            rx = mm_x + (r.gx - dungeon.rooms[0].gx) // 2 + 10
            ry = mm_y + (r.gy - dungeon.rooms[0].gy) * 2 + 30
            color = (50,50,60) if not r.explored else (100,100,140)
            if r.room_type == RoomType.QUEST and r.explored: color = (200,50,50)
            if r.id == dungeon.current_room_id: color = (100,200,255)
            pygame.draw.rect(screen, color, (rx, ry, 10, 8))

    # Controls help
    ai_label = "AI: ON (TAB=off)" if ai_enabled else "TAB=AI"
    ai_color = (100, 255, 100) if ai_enabled else (80, 80, 80)
    speed_label = f" {game_speed:.0f}x (+/-)" if game_speed > 1 else ""
    screen.blit(font.render(ai_label + speed_label, True, ai_color), (WIDTH - 160, HEIGHT - 18))
    screen.blit(font.render("LClick=Move  Shift+L=LSkill  RClick=RSkill  1/2/3=Switch  F=Pot  F1-F4=Summon", True, (70,70,70)), (10, HEIGHT-18))
    pygame.display.flip()

pygame.quit()
