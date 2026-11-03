"""
Wrath of Ashardalon — ARPG
Flow: character select -> map select -> game. ESC steps back one level (game -> character
select, map select -> character select, character select -> quit).
Controls (WoW-style):
  Right-click = Move to location
  Left-click = Select target / Cast ability at location
  1, 2, 3 = Abilities
  F = Health potion
  ESC = Back to character select (progress is saved)
"""
import pygame
import math
import random
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from game.engine.entities import Entity, Hero, Monster, Ability, Condition, GameState, Projectile
from game.engine.world_map import TILE_SIZE
from game.engine.world_map import WorldMap
from game.engine.ai import run_monster_ai, setup_monster_aggro, call_for_help, generate_patrol_route
from game.engine.pathfinding import astar, has_line_of_sight
from game.content.heroes import HERO_CLASSES, HERO_CLASS_BY_NAME
from game.progression import (MAX_LEVEL, xp_to_next_level, apply_level_growth, set_hero_level, growth_for)
from game.quests import load_quest_log
from game import saves
from game.menus import MenuContext, run_menus
from game.client import SessionAbort
from game.content.difficulty import clamp_pp
import game.engine.entities as _entities
from game import headless as _headless

os.chdir(os.path.dirname(os.path.dirname(__file__)))

# === CLI ARGS ===
USE_MAP = None  # Path to world map JSON. If given on the CLI the map-select screen is skipped.
DEBUG = "--debug" in sys.argv  # Pass --debug to enable frame/AI logging
for i, arg in enumerate(sys.argv):
    if arg == "--map" and i + 1 < len(sys.argv):
        USE_MAP = sys.argv[i + 1]

# Headless mode (automated testing): no window/audio, simulated fixed-step time, seeded RNG.
HEADLESS = _headless.parse_args(sys.argv)
if HEADLESS.enabled:
    _headless.apply_sdl_env()   # must happen before pygame.init()
    random.seed(HEADLESS.seed)

# === INIT ===
pygame.init()
_audio_available = False
try:
    pygame.mixer.init()
    _audio_available = True
except Exception as e:
    print(f"[AUDIO] Audio unavailable: {e}. Music disabled.")

# === MUSIC ===
_music_playlist = []
_music_index = 0

def start_map_music(music_list):
    """Start playing a map's music playlist. Loops through tracks in order."""
    global _music_playlist, _music_index
    if HEADLESS.enabled:
        return
    _music_playlist = [t for t in music_list if os.path.exists(t)]
    _music_index = 0
    if not _music_playlist:
        return
    try:
        pygame.mixer.music.load(_music_playlist[0])
        pygame.mixer.music.set_volume(0.6)
        pygame.mixer.music.play()
        pygame.mixer.music.set_endevent(pygame.USEREVENT + 1)
    except Exception as e:
        print(f"[MUSIC] Failed to load {_music_playlist[0]}: {e}")

def advance_music():
    """Play the next track in the playlist (called on MUSIC_END event)."""
    global _music_index
    if not _music_playlist:
        return
    _music_index = (_music_index + 1) % len(_music_playlist)
    try:
        pygame.mixer.music.load(_music_playlist[_music_index])
        pygame.mixer.music.play()
    except Exception as e:
        print(f"[MUSIC] Failed to load {_music_playlist[_music_index]}: {e}")

MUSIC_END = pygame.USEREVENT + 1

# Start maximized — get display size, then create resizable window
_info = pygame.display.Info()
WIDTH, HEIGHT = _info.current_w, _info.current_h - 50  # leave room for title bar
screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.RESIZABLE)
pygame.display.set_caption("Wrath of Ashardalon")


def bring_window_to_front():
    """Raise the game window above other apps. run.sh starts the game in the background, and on macOS
    a process launched that way opens behind the terminal. Skipped for --auto so AI playtests
    don't steal focus while you work."""
    try:
        pygame._sdl2.video.Window.from_display_module().focus()
    except Exception:
        pass
    if sys.platform == "darwin":
        import subprocess
        try:
            subprocess.Popen(
                ["osascript", "-e",
                 f'tell application "System Events" to set frontmost of '
                 f'(first process whose unix id is {os.getpid()}) to true'],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            pass


if "--auto" not in sys.argv and not HEADLESS.enabled:
    bring_window_to_front()
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

# Character scale (1.0 = same size as map tile) is a gameplay constant owned by the sim; sprites use it too.
CHAR_SCALE = _entities.CHAR_SCALE
CHAR_SIZE = int(TILE_SIZE * CHAR_SCALE)
BOSS_SCALE = CHAR_SCALE * 1.5  # Bosses are 1.5x character size

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
HERO_SPRITES = {  # keyed by HERO_CLASSES[...]["sprite_key"]
    "fighter": get_dungeon_tile(0, 8),
    "cleric": get_dungeon_tile(3, 8),
    "paladin": get_dungeon_tile(4, 7),
    "rogue": get_dungeon_tile(2, 7),
    "wizard": get_dungeon_tile(0, 7),
}

# Monster sprites
def load_sprite_file(path, scale=None):
    """Load an external PNG sprite (e.g. custom 24x24 art) scaled to CHAR_SIZE."""
    if scale is None:
        scale = CHAR_SIZE
    img = pygame.image.load(path).convert_alpha()
    return pygame.transform.scale(img, (scale, scale))

MONSTER_SPRITES = {
    "Kobold Dragonshield": get_creature(9, 7),
    "Snake": get_creature(0, 4),
    "Orc Smasher": get_creature(1, 1),
    "Orc Archer": get_creature(0, 1),
    "Human Cultist": get_creature(7, 6),
    "Duergar Guard": get_creature(4, 12),
    "Legion Devil": get_creature(8, 3),
    "Grey Wolf": get_creature(3, 2),
    "Grell": get_creature(0, 12),
    "Gibbering Mouther": get_creature(4, 8),
    "Demodog": get_creature(2, 10),  # Hellhound (CC0 Tiny Creatures)
    "Demobat": get_creature(8, 13),  # Bat (CC0 Tiny Creatures)
    "Vecna": get_creature(6, 9),     # Lich (CC0 Tiny Creatures)
    # Demogorgon: original art, rendered 200% size so it looms over regular mobs
    "Demogorgon": load_sprite_file("assets/stranger_things/sprites/demogorgon.png", CHAR_SIZE * 2),
}
BOSS_SPRITE = get_creature(9, 7, int(TILE_SIZE * BOSS_SCALE))
GARRICK_SPRITE = get_creature(7, 6, int(TILE_SIZE * BOSS_SCALE))  # Scaled-up Human Cultist
VECNA_SPRITE = get_creature(6, 9, int(TILE_SIZE * BOSS_SCALE))    # Scaled-up Lich

def _boss_creature(col, row):
    return get_creature(col, row, int(TILE_SIZE * BOSS_SCALE))

# Bosses without an entry here fall back to BOSS_SPRITE (the scaled-up kobold).
BOSS_SPRITES = {
    "Ashardalon": _boss_creature(3, 3),
    "Rage Drake": _boss_creature(8, 7),
    "Garrick Padfoot": GARRICK_SPRITE,
    "Vecna": VECNA_SPRITE,
    "Otyugh": _boss_creature(5, 7),
    "Bellax": _boss_creature(5, 0),
    "Meerak": _boss_creature(8, 7),
    "Karash": _boss_creature(5, 12),
    "Margrath": _boss_creature(7, 2),
}

# === AUTO MODE (AI playtesting) ===
# --auto [--hero CLASS_IDX] [--map PATH] runs a throwaway level-1 hero with the AI on.
# It NEVER reads or writes real character saves.
auto_mode = "--auto" in sys.argv or HEADLESS.enabled  # headless implies auto
auto_hero_idx = 0  # index into HERO_CLASSES (0=Fighter, 1=Cleric, 2=Paladin, 3=Rogue, 4=Wizard)
if auto_mode:
    for i, arg in enumerate(sys.argv):
        if arg == "--hero" and i + 1 < len(sys.argv):
            auto_hero_idx = int(sys.argv[i + 1])
    if USE_MAP is None:
        USE_MAP = "data/maps/northshire.json"
# --connect [ADDRESS:]PORT: join a co-op host (default address 127.0.0.1) instead of running the
# simulation here; throwaway session, nothing saved locally.
# --host-game [--lan] [--port P]: host a co-op game of --map (with --auto/--headless) — mainly for tests;
# --lan listens on this computer's home-network address instead of this-computer-only.
CONNECT_PORT = None
NET_PORT = None
NET_ADDRESS = "127.0.0.1"
NET_LAN = "--lan" in sys.argv
for i, arg in enumerate(sys.argv):
    if arg == "--connect" and i + 1 < len(sys.argv):
        _target = sys.argv[i + 1]
        if ":" in _target:
            NET_ADDRESS, _target = _target.rsplit(":", 1)
        CONNECT_PORT = NET_PORT = int(_target)
    if arg == "--port" and i + 1 < len(sys.argv):
        NET_PORT = int(sys.argv[i + 1])
CLI_NET_MODE = "join" if CONNECT_PORT else ("host" if "--host-game" in sys.argv else None)
# --pp N (1..8): map difficulty for --map / --auto / --headless / --host-game runs (menus have a dropdown)
CLI_PP = 1
for i, arg in enumerate(sys.argv):
    if arg == "--pp" and i + 1 < len(sys.argv):
        CLI_PP = clamp_pp(int(sys.argv[i + 1]))
if CONNECT_PORT:
    auto_mode = True   # skip the menus; behave like a throwaway session
SAVING = not auto_mode

TITLE_MUSIC = ["assets/music/01. Legends of Azeroth.mp3"]


def run():
    """Character select -> map select -> play session; ESC in a session loops back to character select.
    Each session is game/session.py executed fresh (runpy), so no game state leaks between sessions."""
    import runpy
    preset_map = USE_MAP  # --map from the command line applies to the first pass only
    while True:
        # Title music plays through the character and map select screens
        start_map_music(TITLE_MUSIC)
        if auto_mode:
            cls = HERO_CLASSES[auto_hero_idx]["class"]
            char_data, map_path = saves.blank_character(cls.lower(), cls), preset_map
        else:
            result = run_menus(MenuContext(clock=clock, font=font, big_font=big_font,
                                           title_font=title_font, hero_sprites=HERO_SPRITES),
                               preset_map=preset_map)
            if result is None:
                break
            char_data, map_path = result
        net_mode = CLI_NET_MODE               # None = solo; "host" / "join" = co-op over the network
        pp = CLI_PP                           # map difficulty (1..8 "players")
        net_lan, net_address = NET_LAN, NET_ADDRESS
        if isinstance(map_path, dict):        # from map select: {"map"|"host": path, "pp": n, "lan": bool}
            pp = map_path.get("pp", pp)       #   or {"join": True, "address": "192.168.1.23"}
            net_mode = "host" if "host" in map_path else ("join" if "join" in map_path else None)
            net_lan = map_path.get("lan", False)
            net_address = map_path.get("address", NET_ADDRESS)
            map_path = map_path.get("host") or map_path.get("map")
        surface = pygame.display.get_surface()  # menus may have resized the window
        session_globals = {k: v for k, v in globals().items() if not (k.startswith("__") and k.endswith("__"))}
        session_globals.update(char_data=char_data, USE_MAP=map_path, screen=surface, NET_MODE=net_mode, PP=pp,
                               NET_LAN=net_lan, NET_ADDRESS=net_address,
                               WIDTH=surface.get_width(), HEIGHT=surface.get_height())
        try:
            result_ns = runpy.run_module("game.session", init_globals=session_globals, run_name="game.session")
        except SessionAbort:
            result_ns = {"return_to_menu": True}   # e.g. co-op host/join failed: back to the menus
        if auto_mode or not result_ns.get("return_to_menu"):
            break
        preset_map = None
    pygame.quit()


if __name__ == "__main__":
    run()
