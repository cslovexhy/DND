"""
One play session: set up the chosen character on the chosen map and run the game loop.

This file is executed by game/main.py via runpy.run_module(), once per session, so every
module-level variable below is fresh each time (that is how ESC can go back to character select
without restarting the process). It expects these names from main.py (passed as init_globals):
screen, clock, fonts, colors, sprite helpers/dicts, music helpers, TILE_SIZE/CHAR_SIZE...,
plus the session inputs  char_data, USE_MAP, auto_mode, SAVING, auto_hero_idx, DEBUG, HEADLESS.
When the player presses ESC (non-auto mode) `return_to_menu` ends up True.
"""
import pygame
import math
import random
import sys
import os
import subprocess

from game.engine.entities import Entity, Hero, Monster, Ability, Condition, GameState, Projectile
from game.engine.world_map import WorldMap, TILE_SIZE
from game.engine.ai import run_monster_ai, setup_monster_aggro, call_for_help, generate_patrol_route
from game.engine.pathfinding import astar, has_line_of_sight
from game.content.heroes import HERO_CLASSES, HERO_CLASS_BY_NAME
from game.progression import (MAX_LEVEL, xp_to_next_level, apply_level_growth, set_hero_level, growth_for)
from game.quests import load_quest_log
from game import saves
from game.headless import format_result

# === EFFECTS ===
floating_texts = []
effects = []
projectiles = []  # Active projectiles (Wanding etc.)

# Leveling rules live in game/progression.py


class LevelUpEffect:
    """Gold expanding ring + floating 'LEVEL UP!' text for level-up celebration."""
    def __init__(self, x, y):
        self.x, self.y = x, y
        self.timer = 1.5  # total duration
        self.max_timer = 1.5
    def update(self, dt):
        self.timer -= dt
    def draw(self, s, cx, cy):
        sx = int((self.x - cx) * cam_zoom + WIDTH // 2)
        sy = int((self.y - cy) * cam_zoom + HEIGHT // 2)
        progress = 1.0 - self.timer / self.max_timer
        # Expanding gold ring
        ring_r = int(20 + 80 * progress)
        alpha = int(255 * (self.timer / self.max_timer))
        if alpha > 0 and ring_r > 0:
            surf = pygame.Surface((ring_r * 2, ring_r * 2), pygame.SRCALPHA)
            pygame.draw.circle(surf, (255, 215, 0, alpha), (ring_r, ring_r), ring_r, 4)
            pygame.draw.circle(surf, (255, 255, 100, alpha // 3), (ring_r, ring_r), ring_r)
            s.blit(surf, (sx - ring_r, sy - ring_r))
        # Floating "LEVEL UP!" text rising
        text_y = sy - 40 - int(30 * progress)
        if alpha > 0:
            txt = font.render("LEVEL UP!", True, (255, 215, 0))
            txt.set_alpha(alpha)
            s.blit(txt, (sx - txt.get_width() // 2, text_y))


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

# === GAME SETUP ===
world_map = WorldMap.load(USE_MAP)
if world_map.hero_start is None:
    print(f"ERROR: Map '{USE_MAP}' has no hero_start spawn point.")
    print("Please open the map in the map editor and place a 'Hero Start' marker.")
    pygame.quit()
    sys.exit(1)
dungeon = world_map  # Navigation duck-type (is_wall, is_floor, get_start_pos) used by AI/pathfinding
MAP_ID = os.path.splitext(os.path.basename(USE_MAP))[0]  # key for per-map quest progress
hero_wx, hero_wy = world_map.get_start_pos()
if _audio_available:
    pygame.mixer.music.stop()
start_map_music(world_map.music)

hero_class = HERO_CLASS_BY_NAME[char_data["class_name"]]
hero = hero_class["create"](char_data["name"].capitalize(), hero_wx, hero_wy)
hero.sprite = HERO_SPRITES[hero_class["sprite_key"]]
hero.xp = char_data["xp"]
hero.gold = char_data["gold"]
hero.kills = char_data["kills"]
set_hero_level(hero, char_data["level"])  # re-applies per-level stat growth

# Quest definitions come from data/quests/<map>.json; progress is per character AND per map.
quests = load_quest_log(MAP_ID)
quests.load_state(char_data.get("quests", {}).get(MAP_ID))


def save_game():
    """Persist this character's progress (level/xp/gold/kills + this map's quest state)."""
    if not SAVING:
        return
    char_data.update({"level": hero.level, "xp": hero.xp, "gold": hero.gold, "kills": hero.kills})
    char_data.setdefault("quests", {})[MAP_ID] = quests.to_state()
    saves.save_character(char_data)


print(f"[SAVE] {char_data['name']} Lv{hero.level} XP={hero.xp} Gold={hero.gold} Kills={hero.kills} "
      f"on {MAP_ID}: active={quests.active} done={len(quests.completed)}")

game_state = GameState()
game_state.heroes.append(hero)
game_state.objective_text = f"Explore {MAP_ID.replace('_', ' ').title()} and clear the area of monsters!"

# Movement state
move_path = []
selected_target = None
potions = 3
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
hero_ai.set_nav_dungeon(dungeon)
hero_ai.clock = lambda: game_state.game_time
ai_enabled = auto_mode  # Auto mode starts with AI on

# AI Companions (summon with F1-F4): one per class other than the player's own.
companions = []  # list of (hero_obj, ai_obj) tuples
available_companions = [c for c in HERO_CLASSES if c["class"] != hero.class_name]

def is_wall(wx, wy):
    return dungeon.is_wall(wx, wy)


def check_los(x1, y1, x2, y2):
    """Check line of sight between two world positions using the active dungeon."""
    return has_line_of_sight(dungeon, x1, y1, x2, y2)


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


def spawn_companion(comp_info):
    """Summon an AI companion of the given class. Its level is fixed at the player's CURRENT level
    when summoned (it does not level up afterwards). Returns the companion hero."""
    cx, cy = find_walkable_nearby(hero.x, hero.y, radius=60)
    comp = comp_info["create"](comp_info["companion_name"], cx, cy)
    comp.sprite = HERO_SPRITES[comp_info["sprite_key"]]
    set_hero_level(comp, hero.level)
    comp_ai = create_hero_ai(comp)
    comp_ai.set_nav_dungeon(dungeon)
    comp_ai.clock = lambda: game_state.game_time
    # Give AI access to all heroes for ally-targeting abilities
    if hasattr(comp_ai, 'allies'):
        comp_ai.allies = game_state.heroes
    companions.append((comp, comp_ai))
    game_state.heroes.append(comp)
    return comp


# Auto-mode: summon a companion (Wizard unless that's the hero's class) and set 4x speed
if auto_mode and available_companions and "--no-companion" not in sys.argv:
    spawn_companion(next((c for c in available_companions if c["class"] == "Wizard"), available_companions[0]))

if auto_mode:
    game_speed = 4.0


# World map monster stats lookup
SPAWN_STATS = {
    "kobold_dragonshield": {"name": "Kobold Dragonshield", "hp": 1, "ac": 16, "speed": 5, "atk": 7, "dmg": 1, "xp": 5},
    "snake": {"name": "Snake", "hp": 1, "ac": 13, "speed": 6, "atk": 7, "dmg": 0, "xp": 5, "condition": (Condition.POISONED, 3.0)},
    "orc_smasher": {"name": "Orc Smasher", "hp": 2, "ac": 15, "speed": 4, "atk": 9, "dmg": 1, "xp": 10},
    "orc_archer": {"name": "Orc Archer", "hp": 1, "ac": 13, "speed": 4, "atk": 6, "dmg": 1, "xp": 5, "ranged": True},
    "grey_wolf": {"name": "Grey Wolf", "hp": 2, "ac": 14, "speed": 5, "atk": 8, "dmg": 2, "xp": 10},
    "duergar_guard": {"name": "Duergar Guard", "hp": 2, "ac": 16, "speed": 4, "atk": 8, "dmg": 1, "xp": 10},
    "gibbering_mouther": {"name": "Gibbering Mouther", "hp": 2, "ac": 14, "speed": 3, "atk": 8, "dmg": 1, "xp": 15},
    "grell": {"name": "Grell", "hp": 2, "ac": 15, "speed": 5, "atk": 7, "dmg": 1, "xp": 10, "condition": (Condition.POISONED, 3.0)},
    "human_cultist": {"name": "Human Cultist", "hp": 1, "ac": 14, "speed": 5, "atk": 6, "dmg": 1, "xp": 5, "condition": (Condition.POISONED, 3.0)},
    "legion_devil": {"name": "Legion Devil", "hp": 1, "ac": 16, "speed": 5, "atk": 11, "dmg": 1, "xp": 15},
    # Stranger Things set (Upside Down). Demogorgon: fast (1.5x player speed 6 = 9) and hits hard.
    "demogorgon": {"name": "Demogorgon", "hp": 8, "ac": 16, "speed": 9, "atk": 10, "dmg": 3, "xp": 20, "relentless": True, "hive_mind": (1000, ["demogorgon", "vecna"])},
    "demodog": {"name": "Demodog", "hp": 2, "ac": 15, "speed": 7, "atk": 8, "dmg": 2, "xp": 10},
    "demobat": {"name": "Demobat", "hp": 1, "ac": 14, "speed": 8, "atk": 7, "dmg": 1, "xp": 5},
    "vecna": {"name": "Vecna", "hp": 10, "ac": 18, "speed": 5, "atk": 11, "dmg": 3, "xp": 50, "boss": True},
    "meerak": {"name": "Meerak", "hp": 6, "ac": 17, "speed": 5, "atk": 8, "dmg": 1, "xp": 25, "boss": True},
    "ashardalon": {"name": "Ashardalon", "hp": 12, "ac": 16, "speed": 4, "atk": 10, "dmg": 2, "xp": 50, "boss": True},
    "bellax": {"name": "Bellax", "hp": 9, "ac": 17, "speed": 4, "atk": 8, "dmg": 2, "xp": 40, "boss": True},
    "karash": {"name": "Karash", "hp": 5, "ac": 15, "speed": 5, "atk": 7, "dmg": 1, "xp": 25, "boss": True},
    "margrath": {"name": "Margrath", "hp": 5, "ac": 16, "speed": 4, "atk": 8, "dmg": 1, "xp": 25, "boss": True},
    "rage_drake": {"name": "Rage Drake", "hp": 5, "ac": 15, "speed": 6, "atk": 9, "dmg": 2, "xp": 25, "boss": True},
    "otyugh": {"name": "Otyugh", "hp": 5, "ac": 14, "speed": 3, "atk": 8, "dmg": 2, "xp": 25, "boss": True},
    "garrick_padfoot": {"name": "Garrick Padfoot", "hp": 4, "ac": 15, "speed": 5, "atk": 8, "dmg": 2, "xp": 30, "unique": True, "respawn_mult": 3},
}

def spawn_single_world_monster(sp):
    """Spawn a single monster from a SpawnPoint. Returns the Monster or None."""
    mt = SPAWN_STATS.get(sp.type)
    if mt is None:
        return None
    wx, wy = world_map.get_spawn_world_pos(sp.x, sp.y)
    is_boss = mt.get("boss", False)
    m = Monster(mt["name"], "Monster", wx, wy,
                hp=mt["hp"], ac=mt["ac"], speed=mt["speed"],
                attack_bonus=mt["atk"], attack_damage=mt["dmg"],
                experience=mt["xp"], is_boss=is_boss)
    # Named monsters (Garrick, Vecna) have their own enlarged sprite; other bosses share the generic one.
    m.sprite = BOSS_SPRITES.get(mt["name"]) or (BOSS_SPRITE if is_boss else MONSTER_SPRITES.get(mt["name"]))
    m.unique = mt.get("unique", False)  # one-of-a-kind minion: name shown, but respawns/leashes like a normal mob
    if mt.get("condition"):
        m.on_hit_condition = mt["condition"]
    if mt.get("ranged"):
        m.ranged_attack_range = 250
        m.ranged_attack_damage = m.base_damage
    if mt.get("relentless"):
        m.relentless = True  # never leash-resets aggro (set before setup_monster_aggro)
    if mt.get("hive_mind"):
        m.hive_mind = mt["hive_mind"]  # (range, [spawn_types]) — type-filtered aggro share
    m.spawn_type = sp.type  # spawn-type key (e.g. "demogorgon") for hive_mind matching
    # Track spawn origin for respawn system
    m.spawn_point = sp
    setup_monster_aggro(m, nav_dungeon=dungeon)
    generate_patrol_route(m, patrol_radius=100, collision_fn=is_wall)
    return m


def spawn_world_map_monsters():
    """Spawn all monsters from world map spawn data."""
    for sp in world_map.get_monster_spawns():
        m = spawn_single_world_monster(sp)
        if m:
            game_state.monsters.append(m)


# --- Demogorgon special skills ---
DEMOGORGON_STEALTH_DELAY = 6.0   # seconds since last attack before auto-stealth
DEMOGORGON_AURA_RADIUS = 90.0    # pixels; aura reaches this far
DEMOGORGON_AURA_SLOW = 0.8       # enemies move at 80% speed (20% slow) in aura


def update_demogorgon_skills(dt):
    """Per-frame skills for every Demogorgon:
    1. Auto-stealth: becomes invisible after DEMOGORGON_STEALTH_DELAY seconds have
       passed since its last attack; reveals the moment it attacks.
    2. Aura: slows nearby heroes by 20% (SLOWED) and shows a blue "chill" visual on
       the player (visual only — not a real freeze/movement lock).
    """
    from game.engine.entities import Condition
    # Decay the player's chill visual each frame (re-set to 0.3 while in an aura).
    if getattr(hero, 'chill_visual', 0.0) > 0:
        hero.chill_visual = max(0.0, hero.chill_visual - dt)
    for m in game_state.monsters:
        if not m.alive or m.name != "Demogorgon":
            continue

        # 1) Auto-stealth based purely on time since last attack.
        #    (_last_attack_time is stamped in the AI loop when it lands a hit.)
        #    Taking ANY damage (single-target or AoE) also counts as activity and
        #    reveals it, restarting the stealth timer.
        if getattr(m, 'was_hit', False):
            m._last_attack_time = game_state.game_time
            m.was_hit = False
        last_atk = getattr(m, '_last_attack_time', None)
        if last_atk is None:
            # Never attacked yet — start stealthed after the delay from spawn.
            m._last_attack_time = -DEMOGORGON_STEALTH_DELAY
            last_atk = m._last_attack_time
        if game_state.game_time - last_atk >= DEMOGORGON_STEALTH_DELAY:
            m.stealthed = True
        else:
            m.stealthed = False

        # 2) Slow / chill aura — affects heroes (player + companions) in radius.
        #    Gameplay effect is a 20% slow (NOT a movement lock). The player also
        #    gets a visual blue "chill" marker so the aura reads on-screen.
        targets = [hero] + [c for c, _ in companions]
        for t in targets:
            if not t.alive:
                continue
            if m.distance_to(t) <= DEMOGORGON_AURA_RADIUS:
                # 20% slow (refreshed each frame so it persists while in aura)
                t.apply_condition(Condition.SLOWED, 0.3, source="Demogorgon Aura",
                                  slow_factor=DEMOGORGON_AURA_SLOW)
                # Blue chill VISUAL on the player (not a real freeze) — timer-based
                # so it fades shortly after leaving the aura.
                if t is hero:
                    t.chill_visual = 0.3


# Respawn system — dead mobs respawn after RESPAWN_TIME seconds (x a per-monster multiplier)
import heapq
import itertools
RESPAWN_TIME = 60.0  # seconds before a killed regular mob respawns
BOSS_RESPAWN_MULT = 10  # bosses take 10x as long (600s) unless SPAWN_STATS sets "respawn_mult"
respawn_heap = []     # min-heap of (respawn_at_game_time, seq, SpawnPoint); earliest due time first
_respawn_seq = itertools.count()  # tiebreaker so equal times never compare SpawnPoint objects


def respawn_delay(m):
    """Seconds until a killed monster respawns: RESPAWN_TIME x its "respawn_mult" (default 1, bosses 10)."""
    stats = SPAWN_STATS.get(getattr(m, "spawn_type", None), {})
    return RESPAWN_TIME * stats.get("respawn_mult", BOSS_RESPAWN_MULT if m.is_boss else 1)

# Spawn the map's monsters at start
spawn_world_map_monsters()


# === QUEST POPUP PANEL ===
import subprocess
import textwrap

# TTS process handle (so we can kill it if a new quest is picked up)
_tts_process = None

def speak_text(text, voice="Daniel"):
    """Speak text aloud using macOS 'say' command (async, non-blocking)."""
    if HEADLESS.enabled:
        return
    global _tts_process
    # Kill any ongoing speech
    if _tts_process and _tts_process.poll() is None:
        _tts_process.terminate()
    try:
        _tts_process = subprocess.Popen(
            ["say", "-v", voice, "-r", "175", text],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
    except FileNotFoundError:
        pass  # 'say' not available (non-macOS) — silently skip


class QuestPopupPanel:
    """A centered popup panel showing quest details. Stays visible until dismissed."""
    def __init__(self, quest, mode="accept", npc_name="NPC"):
        self.quest = quest
        self.mode = mode  # "accept" or "turnin"
        self.npc_name = npc_name
        self.active = True
        # Panel dimensions — calculate height based on content
        self.width = 480
        self.padding = 16
        self.close_btn_size = 24
        self.close_btn_x = self.width - self.close_btn_size - 8
        self.close_btn_y = 8
        # Pre-calculate wrapped description lines
        self.desc_lines = textwrap.wrap(self.quest.description, width=56)
        # Calculate height: header(30) + npc(22) + title(28) + desc(16*lines) + gap(8)
        #   + objectives(16 + 16*n + 8) + rewards(16+16) + padding*2
        h = self.padding + 30 + 22 + 28  # header + npc + title
        h += len(self.desc_lines) * 16 + 8  # description
        if self.mode == "accept" and self.quest.objectives:
            h += 16 + len(self.quest.objectives) * 16 + 8  # objectives
        h += 16 + 16  # rewards header + line
        h += self.padding  # bottom padding
        self.height = max(200, h)

    def update(self, dt):
        pass  # No auto-dismiss — player must click close

    def dismiss(self):
        self.active = False

    def get_panel_rect(self):
        """Return the screen-space rect of the panel."""
        px = WIDTH // 2 - self.width // 2
        py = HEIGHT // 2 - self.height // 2
        return pygame.Rect(px, py, self.width, self.height)

    def handle_click(self, mx, my):
        """Handle a mouse click. Returns True if the popup consumed the click."""
        if not self.active:
            return False
        panel_rect = self.get_panel_rect()
        if not panel_rect.collidepoint(mx, my):
            # Clicked outside panel — dismiss
            self.dismiss()
            return True
        # Check close button
        close_rect = pygame.Rect(
            panel_rect.x + self.close_btn_x,
            panel_rect.y + self.close_btn_y,
            self.close_btn_size, self.close_btn_size
        )
        if close_rect.collidepoint(mx, my):
            self.dismiss()
            return True
        # Click inside panel but not on close — consume but don't dismiss
        return True

    def draw(self, screen):
        if not self.active:
            return
        # Semi-transparent dark panel centered on screen
        px = WIDTH // 2 - self.width // 2
        py = HEIGHT // 2 - self.height // 2
        panel_surf = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        panel_surf.fill((20, 20, 30, 230))
        # Border
        pygame.draw.rect(panel_surf, GOLD, (0, 0, self.width, self.height), 2, border_radius=6)

        # Close button [X]
        close_rect = pygame.Rect(self.close_btn_x, self.close_btn_y, self.close_btn_size, self.close_btn_size)
        pygame.draw.rect(panel_surf, (80, 80, 80), close_rect, border_radius=4)
        pygame.draw.rect(panel_surf, (200, 200, 200), close_rect, 1, border_radius=4)
        x_surf = font.render("X", True, (255, 255, 255))
        panel_surf.blit(x_surf, (self.close_btn_x + (self.close_btn_size - x_surf.get_width()) // 2,
                                  self.close_btn_y + (self.close_btn_size - x_surf.get_height()) // 2))

        y = self.padding
        # Header
        if self.mode == "accept":
            header = "Quest Accepted"
            header_color = GOLD
        else:
            header = "Quest Complete!"
            header_color = (100, 255, 100)
        hdr_surf = big_font.render(header, True, header_color)
        panel_surf.blit(hdr_surf, (self.width // 2 - hdr_surf.get_width() // 2, y))
        y += 30

        # NPC name
        npc_surf = font.render(f"— {self.npc_name} —", True, (180, 180, 180))
        panel_surf.blit(npc_surf, (self.width // 2 - npc_surf.get_width() // 2, y))
        y += 22

        # Quest title
        title_surf = big_font.render(self.quest.title, True, (255, 255, 255))
        panel_surf.blit(title_surf, (self.padding, y))
        y += 28

        # Description (word-wrapped)
        for line in self.desc_lines:
            line_surf = font.render(line, True, (200, 200, 200))
            panel_surf.blit(line_surf, (self.padding, y))
            y += 16
        y += 8

        # Objectives (for accept mode)
        if self.mode == "accept" and self.quest.objectives:
            obj_header = font.render("Objectives:", True, (180, 180, 255))
            panel_surf.blit(obj_header, (self.padding, y))
            y += 16
            for obj in self.quest.objectives:
                obj_text = f"  • Kill {obj['count']} {obj['target']}"
                obj_surf = font.render(obj_text, True, (220, 220, 220))
                panel_surf.blit(obj_surf, (self.padding, y))
                y += 16
            y += 8

        # Rewards
        rewards_header = font.render("Rewards:", True, (255, 215, 0))
        panel_surf.blit(rewards_header, (self.padding, y))
        y += 16
        reward_parts = []
        if self.quest.rewards_xp > 0:
            reward_parts.append(f"+{self.quest.rewards_xp} XP")
        if self.quest.rewards_gold > 0:
            reward_parts.append(f"+{self.quest.rewards_gold} Gold")
        if reward_parts:
            rew_surf = font.render("  " + "   ".join(reward_parts), True, (255, 255, 100))
            panel_surf.blit(rew_surf, (self.padding, y))

        # Blit panel to screen
        screen.blit(panel_surf, (px, py))


# Active quest popup (only one at a time)
quest_popup_panel = None


# === QUEST SYSTEM === (see game/quests.py; `quests` is this character's QuestLog for the current map)


class NPC(Entity):
    """A quest-giving NPC. Inherits all combat/entity attributes but doesn't fight by default."""
    def __init__(self, name, x, y, npc_id, gender="male", level=1, sprite=None):
        # NPC has minimal combat stats (hp=5 gives 250 HP, ac=10 no armor, speed=0 stationary)
        super().__init__(name, x, y, hp=5, ac=10, speed=0)
        self.npc_id = npc_id  # matches quest.npc_id
        self.gender = gender  # "male" or "female" — used for TTS voice
        self.level = level
        self.sprite = sprite
        self.interact_range = 80  # pixels — how close hero must be to interact

    def has_available_quest(self):
        """Does this NPC have a quest to offer?"""
        return len(quests.available_for_npc(self.npc_id, hero.level)) > 0

    def has_turn_in(self):
        """Does this NPC have a quest ready to turn in?"""
        return len(quests.turn_ins_for_npc(self.npc_id)) > 0

    def is_in_range(self, hx, hy):
        dx = self.x - hx
        dy = self.y - hy
        return (dx*dx + dy*dy) <= self.interact_range * self.interact_range


# Create NPCs from map data (each map defines its own NPCs in the JSON)
npcs = []
for npc_def in world_map.data.get("npcs", []):
    tx, ty = npc_def["x"], npc_def["y"]
    wx, wy = world_map.get_spawn_world_pos(tx, ty)
    npc = NPC(npc_def["name"], wx, wy, npc_id=npc_def["npc_id"], gender=npc_def.get("gender", "male"))
    npc.sprite = get_dungeon_tile(npc_def["sprite_col"], npc_def["sprite_row"])
    npcs.append(npc)

# Quest interaction state
quest_popup_timer = 0.0  # How long to show quest accepted/completed popup
quest_popup_text = ""
quest_popup_color = GOLD

def get_monster_at_screen(sx, sy):
    wx = (sx - WIDTH//2) / cam_zoom + hero.x
    wy = (sy - HEIGHT//2) / cam_zoom + hero.y
    for m in game_state.alive_monsters:
        if getattr(m, 'stealthed', False):
            continue  # stealthed monsters can't be clicked/targeted
        if abs(m.x - wx) < TILE_SIZE and abs(m.y - wy) < TILE_SIZE:
            return m
    return None


def get_npc_at_screen(sx, sy):
    """Check if a screen click hit an NPC sprite."""
    wx = (sx - WIDTH//2) / cam_zoom + hero.x
    wy = (sy - HEIGHT//2) / cam_zoom + hero.y
    for npc in npcs:
        if abs(npc.x - wx) < TILE_SIZE and abs(npc.y - wy) < TILE_SIZE:
            return npc
    return None


def interact_with_npc(npc):
    """Handle quest turn-in and acceptance for a specific NPC. Returns True if interaction happened."""
    global quest_popup_panel
    interacted = False

    voice = "Samantha" if npc.gender == "female" else "Daniel"

    # First: turn in any completed quests at this NPC
    for qid in quests.turn_ins_for_npc(npc.npc_id):
        q = quests.turn_in(qid)
        hero.xp += q.rewards_xp
        hero.gold += q.rewards_gold
        floating_texts.append(FloatingText(hero.x, hero.y - 40,
            f"+{q.rewards_xp}xp +{q.rewards_gold}g", GOLD))
        # Show turn-in popup panel
        quest_popup_panel = QuestPopupPanel(q, mode="turnin", npc_name=npc.name)
        speak_text(f"Well done! {q.title} complete. Here's your reward: {q.rewards_xp} experience and {q.rewards_gold} gold.", voice)
        save_game()
        interacted = True

    # Second: offer and accept an available quest from this NPC
    if not interacted:  # Don't pile accept on top of turn-in
        for qid in quests.available_for_npc(npc.npc_id, hero.level):
            q = quests.quests[qid]
            if quests.accept(qid):
                # No-objective quest (intro) — completed and turned in on the spot
                hero.xp += q.rewards_xp
                hero.gold += q.rewards_gold
                quest_popup_panel = QuestPopupPanel(q, mode="turnin", npc_name=npc.name)
            else:
                quest_popup_panel = QuestPopupPanel(q, mode="accept", npc_name=npc.name)
            speak_text(q.description, voice)
            save_game()
            interacted = True
            break  # One quest popup at a time

    return interacted


# === SHARED ABILITY EXECUTION HELPERS ===
# These are the "do the thing" functions called by both _cast_ability (player)
# and the companion AI loop. Validation (range, LOS, cooldown) is done by the caller.

def _exec_fire_blast(caster, target, ab):
    """Execute Fire Blast: instant ranged nuke. Returns damage dealt."""
    ab.use()
    dmg_amount = ab.calc_damage(caster.base_damage)
    dmg = target.take_damage(dmg_amount)
    floating_texts.append(FloatingText(target.x, target.y - 20, f"{dmg:.0f}", (255, 130, 50)))
    effects.append(AoeRing(target.x, target.y, 30, (255, 100, 0)))
    if hasattr(target, 'aggro_state') and target.aggro_state != "aggroed":
        from game.engine.ai import aggro_monster as _aggro
        _aggro(target, caster, game_state.monsters)
    call_for_help(target, game_state.monsters, caster)
    return dmg


def _exec_ranged_projectile(caster, target, ab, color, apply_slow=False):
    """Spawn a homing projectile (Wanding, Frostbolt). Returns the Projectile."""
    ab.use()
    caster.swing_timer = caster.weapon_speed
    proj_damage = ab.calc_damage(caster.base_damage)
    proj = Projectile(x=caster.x, y=caster.y, target=target,
                      speed=500.0, damage=proj_damage,
                      color=color, source=caster)
    if apply_slow:
        proj.apply_slow = True
    projectiles.append(proj)
    return proj


def _exec_judgement(caster, target, ab):
    """Execute Judgement: ranged holy damage, consumes Seal. Returns damage dealt."""
    ab.use()
    total_damage = ab.calc_damage(caster.base_damage)
    seal_consumed = False
    if "Righteous Seal" in caster.buffs:
        total_damage += caster.base_damage
        del caster.buffs["Righteous Seal"]
        seal_consumed = True
        floating_texts.append(FloatingText(target.x, target.y - 40, "Seal Consumed!", (255, 200, 50)))
    dmg = target.take_damage(total_damage)
    floating_texts.append(FloatingText(target.x, target.y - 20, f"{dmg:.0f}", (255, 255, 150)))
    if hasattr(target, 'aggro_state') and target.aggro_state != "aggroed":
        from game.engine.ai import aggro_monster as _aggro
        _aggro(target, caster, game_state.monsters)
    call_for_help(target, game_state.monsters, caster)
    return dmg


def _exec_stab(caster, target, ab):
    """Execute Stab: fast melee attack. Returns damage dealt."""
    global right_skill_idx
    ab.use()
    caster.swing_timer = caster.weapon_speed
    if getattr(caster, 'stealthed', False):
        caster.stealthed = False
        # Auto-bind right-click back to Stealth (main hero only)
        if caster is hero and "R" in ability_keys:
            right_skill_idx = ability_keys.index("R")
    dmg_amount = ab.calc_damage(caster.base_damage)
    # Crit check
    import random as _rng
    if _rng.random() < getattr(caster, 'crit_chance', 0.05):
        dmg_amount *= 2.0
        floating_texts.append(FloatingText(target.x, target.y - 40, "CRIT!", (255, 255, 0)))
    dmg = target.take_damage(dmg_amount)
    floating_texts.append(FloatingText(target.x, target.y - 20, f"{dmg:.0f}", (180, 255, 180)))
    if hasattr(target, 'aggro_state') and target.aggro_state != "aggroed":
        from game.engine.ai import aggro_monster as _aggro
        _aggro(target, caster, game_state.monsters)
    call_for_help(target, game_state.monsters, caster)
    return dmg


def _exec_smite(caster, target, ab):
    """Execute Smite: melee with Seal bonus. Returns damage dealt."""
    ab.use()
    caster.swing_timer = caster.weapon_speed
    bonus = 1.0 + (caster.buffs.get("Righteous Seal", {}).get("bonus", 0))
    dmg_amount = ab.calc_damage(caster.base_damage) * bonus
    dmg = target.take_damage(dmg_amount)
    floating_texts.append(FloatingText(target.x, target.y - 20, f"{dmg:.0f}", WHITE))
    if hasattr(target, 'aggro_state') and target.aggro_state != "aggroed":
        from game.engine.ai import aggro_monster as _aggro
        _aggro(target, caster, game_state.monsters)
    call_for_help(target, game_state.monsters, caster)
    return dmg


def _can_ranged_hit(caster, target, ab):
    """Check if a ranged ability can hit: in range + line of sight."""
    if caster.distance_to(target) > ab.range:
        return False
    return check_los(caster.x, caster.y, target.x, target.y)


def _cast_ability(ab_key, ab, wx, wy, clicked_monster):
    """Cast an ability — handles AoE, single target, dash, stun, call-for-help, and Quinn's Seal system."""
    global move_path, selected_target, dash_active, dash_target_x, dash_target_y, dash_stun_target, dash_stun_duration, dash_damage, frostbolt_channeling, frostbolt_channel_timer, frostbolt_target, ambush_target, right_skill_idx

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
            # Auto-bind right-click back to Stealth
            if "R" in ability_keys:
                right_skill_idx = ability_keys.index("R")
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
        # Auto-bind right-click to Ambush
        if "E" in ability_keys:
            right_skill_idx = ability_keys.index("E")
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
            # Queue walk-to via ambush_target (works while stealthed)
            ambush_target = clicked_monster
            selected_target = None
            move_path = []
            return
        ab.use()
        hero.swing_timer = hero.weapon_speed
        # Break stealth
        hero.stealthed = False
        # Auto-bind right-click back to Stealth
        if "R" in ability_keys:
            right_skill_idx = ability_keys.index("R")
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
        if hero.distance_to(clicked_monster) > ab.range:
            # Queue walk-to-range
            pending_cast = (ab_key, ab, clicked_monster); selected_target = clicked_monster
            move_path = []
            return
        if not check_los(hero.x, hero.y, clicked_monster.x, clicked_monster.y):
            floating_texts.append(FloatingText(hero.x, hero.y - 30, "No line of sight!", (255, 150, 100)))
            return
        _exec_fire_blast(hero, clicked_monster, ab)
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
        # Line of sight check
        if not check_los(hero.x, hero.y, clicked_monster.x, clicked_monster.y):
            floating_texts.append(FloatingText(hero.x, hero.y - 30, "No line of sight!", (255, 150, 100)))
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
        if not check_los(hero.x, hero.y, clicked_monster.x, clicked_monster.y):
            floating_texts.append(FloatingText(hero.x, hero.y - 30, "No line of sight!", (255, 150, 100)))
            return
        if hero.swing_timer > 0:
            return  # Gated by weapon speed
        _exec_ranged_projectile(hero, clicked_monster, ab, color=(255, 220, 100))
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
        if not check_los(hero.x, hero.y, clicked_monster.x, clicked_monster.y):
            floating_texts.append(FloatingText(hero.x, hero.y - 30, "No line of sight!", (255, 150, 100)))
            return
        _exec_judgement(hero, clicked_monster, ab)
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

    # === Vistra special: Demoralizing Shout (AoE debuff) ===
    if ab.name == "Demoralizing Shout":
        ab.use()
        hit_count = 0
        for m in game_state.alive_monsters:
            if hero.distance_to(m) <= ab.radius:
                # 50% damage reduction for 10s
                m.buffs["Demoralized"] = {"remaining": 10.0, "damage_mult": 0.5}
                # Slow for 3s
                m.apply_condition(Condition.SLOWED, 3.0, slow_factor=0.5)
                floating_texts.append(FloatingText(m.x, m.y - 20, "Demoralized!", (200, 150, 50)))
                hit_count += 1
        if hit_count > 0:
            effects.append(AoeRing(hero.x, hero.y, ab.radius, ab.color))
        hero.gcd = hero.GCD_DURATION
        move_path = []
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
            # Line of sight check — can't charge through walls
            if not check_los(hero.x, hero.y, clicked_monster.x, clicked_monster.y):
                floating_texts.append(FloatingText(hero.x, hero.y - 30, "No line of sight!", (255, 150, 100)))
                return
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
return_to_menu = False
while running:
    if HEADLESS.enabled:
        dt = HEADLESS.fixed_dt   # simulated time: no sleeping, one fixed step per iteration
        if game_state.game_time >= HEADLESS.max_time:
            print(format_result("TIMEOUT", game_state, hero), flush=True)
            break
    else:
        dt = clock.tick(60) / 1000.0 * game_speed

    for event in pygame.event.get():
        if event.type == pygame.QUIT: running = False
        if event.type == MUSIC_END: advance_music()
        if event.type == pygame.VIDEORESIZE:
            WIDTH, HEIGHT = event.w, event.h
            screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.RESIZABLE)
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
                    return_to_menu = not auto_mode  # ESC -> back to character select
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
            # Summon AI companions (F1-F4) — press again to dismiss
            summon_keys = [pygame.K_F1, pygame.K_F2, pygame.K_F3, pygame.K_F4]
            for ki, sk in enumerate(summon_keys):
                if event.key == sk and ki < len(available_companions):
                    comp_info = available_companions[ki]
                    # Check if already summoned — if so, dismiss
                    existing = [(i, c) for i, (c, _) in enumerate(companions) if c.class_name == comp_info["class"]]
                    if existing:
                        idx, comp = existing[0]
                        companions.pop(idx)
                        game_state.heroes.remove(comp)
                        floating_texts.append(FloatingText(comp.x, comp.y - 30, f"{comp.name} dismissed", (200, 150, 150)))
                    else:
                        comp = spawn_companion(comp_info)
                        floating_texts.append(FloatingText(comp.x, comp.y - 30, f"{comp.name} joined! (Lv {comp.level})", GOLD))
                    break

        if event.type == pygame.MOUSEBUTTONDOWN and not game_state.adventure_failed:
            mx_s, my_s = event.pos
            # If quest popup panel is open, intercept clicks
            if quest_popup_panel and quest_popup_panel.active:
                quest_popup_panel.handle_click(mx_s, my_s)
                continue
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
                    # LOS check — can't target what you can't see
                    if not check_los(hero.x, hero.y, clicked_monster.x, clicked_monster.y):
                        floating_texts.append(FloatingText(hero.x, hero.y - 30, "No line of sight!", (255, 150, 100)))
                    else:
                        # Cancel any active channel
                        if frostbolt_channeling:
                            frostbolt_channeling = False
                            frostbolt_target = None
                            hero.conditions = [c for c in hero.conditions if c.condition != Condition.IMMOBILIZED]
                            hero.swing_timer = 0.5  # Brief delay after cancel
                        selected_target = clicked_monster
                        ambush_target = None
                        pending_cast = None
                        move_path = []
                else:
                    # Click ground = move (cancel channel)
                    if frostbolt_channeling:
                        frostbolt_channeling = False
                        frostbolt_target = None
                        hero.conditions = [c for c in hero.conditions if c.condition != Condition.IMMOBILIZED]
                    move_path = astar(dungeon, hero.x, hero.y, wx, wy)
                    selected_target = None
                    ambush_target = None
                    pending_cast = None

            elif event.button == 3:  # Right-click = cast RIGHT skill or interact with NPC
                # Check if clicking on an NPC first
                clicked_npc = get_npc_at_screen(mx_s, my_s)
                if clicked_npc and clicked_npc.is_in_range(hero.x, hero.y):
                    interact_with_npc(clicked_npc)
                elif clicked_npc and not clicked_npc.is_in_range(hero.x, hero.y):
                    # Walk to NPC
                    move_path = astar(dungeon, hero.x, hero.y, clicked_npc.x, clicked_npc.y)
                    selected_target = None
                # Stealth + right-click enemy + Ambush on right slot = queue ambush walk-to
                elif hero.stealthed and clicked_monster and ability_keys[right_skill_idx] == "E":
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
    if game_state.adventure_failed:
        screen.fill(BG)
        msg = "DEFEATED..."
        t = title_font.render(msg, True, HP_RED)
        screen.blit(t, (WIDTH//2-t.get_width()//2, HEIGHT//2-20))
        stats = f"Time: {game_state.game_time:.1f}s  HP: {hero.hp:.0f}/{hero.max_hp}  Kills: {hero.kills}"
        screen.blit(big_font.render(stats, True, WHITE), (WIDTH//2-150, HEIGHT//2+20))
        screen.blit(font.render("Press ESC to return to character select", True, GRAY), (WIDTH//2-100, HEIGHT//2+55))
        pygame.display.flip()
        if auto_mode:
            print(format_result("DEFEATED", game_state, hero), flush=True)
            if not HEADLESS.enabled:
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

    # Update combat state for health regeneration
    hero.in_combat = any(m.alive and getattr(m, 'aggro_target', None) == hero
                         for m in game_state.monsters)
    for comp, _ in companions:
        if comp.alive:
            comp.in_combat = any(m.alive and getattr(m, 'aggro_target', None) == comp
                                 for m in game_state.monsters)
    for m in game_state.monsters:
        if m.alive:
            m.in_combat = getattr(m, 'aggro_state', '') == 'aggroed'

    # --- Demogorgon special skills (auto-stealth + slow/freeze aura) ---
    update_demogorgon_skills(dt)

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
            target_pos = f" target_pos=({hero_ai.target.x:.0f},{hero_ai.target.y:.0f})" if hero_ai.target and hero_ai.target.alive else ""
            path_len = f" path_len={len(move_path)}" if move_path else " path_len=0"
            print(f"[AI t={game_state.game_time:.1f}s] monsters={alive_count} hp={hero.hp:.0f}/{hero.max_hp} pos=({hero.x:.0f},{hero.y:.0f}) action={action_name}{target_dist}{target_pos}{target_hp}{path_len}", flush=True)
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
                if not check_los(hero.x, hero.y, target_m.x, target_m.y):
                    # No LOS — pathfind toward target
                    move_path = astar(dungeon, hero.x, hero.y, target_m.x, target_m.y)
                else:
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
                # Check LOS before casting — if blocked, pathfind toward target to get LOS
                if target_m and not check_los(hero.x, hero.y, target_m.x, target_m.y):
                    move_path = astar(dungeon, hero.x, hero.y, target_m.x, target_m.y)
                else:
                    # Route through _cast_ability for consistent handling
                    wx = target_m.x if target_m else hero.x
                    wy = target_m.y if target_m else hero.y
                    _cast_ability(ab_key, ab, wx, wy, target_m)

        elif ai_action["move_to"]:
            tx, ty = ai_action["move_to"]
            # Repath every 0.5s or if path empty
            if not hasattr(hero, '_ai_repath_timer'):
                hero._ai_repath_timer = 0
                hero._ai_unreachable = set()  # Track unreachable monster IDs
            hero._ai_repath_timer -= dt
            if hero._ai_repath_timer <= 0 or not move_path:
                move_path = astar(dungeon, hero.x, hero.y, tx, ty)
                hero._ai_repath_timer = 0.5
                # If path is empty and target is nearby, it's unreachable
                if not move_path and hero_ai.target and hero_ai.target.alive:
                    dist_to_target = hero.distance_to(hero_ai.target)
                    if dist_to_target < 300:
                        hero._ai_unreachable.add(id(hero_ai.target))
                        hero_ai.target = None  # Force retarget next frame

    # Ambush walk-to: walk toward target in stealth, execute Ambush when in range
    if ambush_target and not ai_enabled:
        if not ambush_target.alive or not hero.stealthed:
            ambush_target = None
            move_path = []
        elif not check_los(hero.x, hero.y, ambush_target.x, ambush_target.y):
            # Lost LOS — cancel
            ambush_target = None
            move_path = []
        else:
            dist = hero.distance_to(ambush_target)
            ab_ambush = hero.abilities.get("E")
            if dist <= ab_ambush.range and ab_ambush and ab_ambush.is_ready():
                # In range — execute Ambush
                _cast_ability("E", ab_ambush, ambush_target.x, ambush_target.y, ambush_target)
                ambush_target = None
            else:
                # Walk toward target using pathfinding
                if not move_path:
                    move_path = astar(dungeon, hero.x, hero.y, ambush_target.x, ambush_target.y)

    # Auto-attack selected target (walk to range, attack when close)
    if selected_target and not ai_enabled and not frostbolt_channeling and not hero.stealthed and not hero.has_condition(Condition.IMMOBILIZED):
        if not selected_target.alive:
            selected_target = None
            pending_cast = None
        elif not check_los(hero.x, hero.y, selected_target.x, selected_target.y):
            # Lost line of sight — drop target
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
                # Out of range and shift NOT held — pathfind toward target
                if not move_path:
                    move_path = astar(dungeon, hero.x, hero.y, selected_target.x, selected_target.y)

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

        comp_acted = False
        if comp_action.get("use_ability"):
            ab_key = comp_action["use_ability"]
            ab = comp.abilities.get(ab_key)
            if ab and ab.is_ready() and comp.gcd <= 0:
                comp_acted = True
                target_m = comp_action.get("ability_target_monster")

                # LOS check for targeted abilities — pathfind if blocked
                if target_m and not check_los(comp.x, comp.y, target_m.x, target_m.y):
                    path = astar(dungeon, comp.x, comp.y, target_m.x, target_m.y)
                    if path:
                        comp.move_toward(path[0][0], path[0][1], dt, is_wall)
                # Handle dash abilities (Charge) — just teleport + damage for companions
                elif comp_action.get("dash"):
                    tx, ty, dash_target, dash_dmg, dash_stun = comp_action["dash"]
                    if dash_target and dash_target.alive and comp.distance_to(dash_target) <= 300:
                        if not check_los(comp.x, comp.y, dash_target.x, dash_target.y):
                            path = astar(dungeon, comp.x, comp.y, dash_target.x, dash_target.y)
                            if path:
                                comp.move_toward(path[0][0], path[0][1], dt, is_wall)
                        else:
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
                elif ab.name == "Demoralizing Shout":
                    # Vistra's AoE debuff
                    ab.use()
                    comp.gcd = comp.GCD_DURATION
                    hit_count = 0
                    for m in game_state.alive_monsters:
                        if comp.distance_to(m) <= ab.radius:
                            m.buffs["Demoralized"] = {"remaining": 10.0, "damage_mult": 0.5}
                            m.apply_condition(Condition.SLOWED, 3.0, slow_factor=0.5)
                            floating_texts.append(FloatingText(m.x, m.y - 20, "Demoralized!", (200, 150, 50)))
                            hit_count += 1
                    if hit_count > 0:
                        effects.append(AoeRing(comp.x, comp.y, ab.radius, ab.color))
                elif ab.radius > 0:
                    # AoE (generic)
                    hits = comp.use_ability(ab_key, game_state.alive_monsters, target_pos=(comp.x, comp.y))
                    if hits:
                        effects.append(AoeRing(comp.x, comp.y, ab.radius, ab.color))
                        for name, dmg in hits:
                            floating_texts.append(FloatingText(comp.x, comp.y - 20, f"{dmg:.0f}", GOLD))
                elif ab.name == "Wanding" and target_m and target_m.alive:
                    # Quinn's ranged projectile
                    if comp.swing_timer <= 0 and _can_ranged_hit(comp, target_m, ab):
                        _exec_ranged_projectile(comp, target_m, ab, color=(255, 220, 100))
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
                    if comp.swing_timer <= 0 and _can_ranged_hit(comp, target_m, ab):
                        _exec_ranged_projectile(comp, target_m, ab, color=(150, 200, 255), apply_slow=True)
                elif ab.name == "Fire Blast" and target_m and target_m.alive:
                    # Heskan's instant nuke
                    if _can_ranged_hit(comp, target_m, ab):
                        _exec_fire_blast(comp, target_m, ab)
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
                        _exec_stab(comp, target_m, ab)
                elif ab.name == "Smite" and target_m and target_m.alive:
                    # Keyleth's melee
                    if comp.swing_timer <= 0 and comp.distance_to(target_m) <= ab.range:
                        _exec_smite(comp, target_m, ab)
                elif ab.name == "Righteous Seal":
                    # Keyleth's self-buff
                    ab.use()
                    comp.buffs["Righteous Seal"] = {"remaining": 10.0, "bonus": 0.25}
                elif ab.name == "Judgement" and target_m and target_m.alive:
                    # Keyleth's ranged holy bolt
                    if _can_ranged_hit(comp, target_m, ab):
                        _exec_judgement(comp, target_m, ab)
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

        if comp_action.get("move_to") and not comp_acted:
            tx, ty = comp_action["move_to"]
            # Repath periodically (every 0.5s) or if no cached path
            if not hasattr(comp, '_comp_path'):
                comp._comp_path = []
                comp._comp_repath_timer = 0
            comp._comp_repath_timer -= dt
            if comp._comp_repath_timer <= 0 or not comp._comp_path:
                comp._comp_path = astar(dungeon, comp.x, comp.y, tx, ty)
                comp._comp_repath_timer = 0.5
            if comp._comp_path:
                wx, wy = comp._comp_path[0]
                if math.sqrt((wx - comp.x)**2 + (wy - comp.y)**2) < 8:
                    comp._comp_path.pop(0)
                if comp._comp_path:
                    comp.move_toward(comp._comp_path[0][0], comp._comp_path[0][1], dt, is_wall)

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

    # Monster AI — all alive monsters with aggro system
    all_heroes = [h for h in game_state.heroes if h.alive]
    for m in alive:
        result = run_monster_ai(m, all_heroes, dt, is_wall, all_monsters=game_state.monsters)
        if result and result[0] in ("attack", "ranged_attack", "aoe_attack"):
            hit_hero = result[1]
            floating_texts.append(FloatingText(hit_hero.x+random.randint(-10,10), hit_hero.y-30, f"{result[2]:.0f}", HP_RED))
            # Demogorgon reveals when it attacks; stealth timer restarts from now.
            if m.name == "Demogorgon":
                m._last_attack_time = game_state.game_time
                m.stealthed = False
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
            # Quest kill tracking
            for aq, just_completed in quests.record_kill(m.name):
                floating_texts.append(FloatingText(hero.x, hero.y - 50, aq.get_progress_text(), (200, 200, 255)))
                if just_completed:
                    quest_popup_text = f"Quest Complete: {aq.title} — Return to NPC"
                    quest_popup_timer = 3.0
                    quest_popup_color = (100, 255, 100)
                    save_game()
            m.experience = 0
            # Queue for respawn (every monster that came from a spawn point; bosses just take much longer)
            if hasattr(m, 'spawn_point') and m.spawn_point:
                heapq.heappush(respawn_heap, (game_state.game_time + respawn_delay(m),
                                              next(_respawn_seq), m.spawn_point))

    # Level-up check
    while hero.level < MAX_LEVEL and hero.xp >= xp_to_next_level(hero.level):
        hero.xp -= xp_to_next_level(hero.level)
        hero.level += 1
        # Stat growth
        growth = growth_for(hero.class_name)
        apply_level_growth(hero)  # also full-heals on level-up
        # Visual celebration
        effects.append(LevelUpEffect(hero.x, hero.y))
        floating_texts.append(FloatingText(hero.x, hero.y - 30,
            f"Lv {hero.level}! +{growth['hp']:.0f}HP +{growth['damage']:.0f}dmg", GOLD))
        save_game()

    # Respawn system — check if any mobs are ready to respawn
    while respawn_heap and respawn_heap[0][0] <= game_state.game_time:
        _, _, sp = heapq.heappop(respawn_heap)
        m = spawn_single_world_monster(sp)
        if m:
            game_state.monsters.append(m)

    # Quest popup timer
    if quest_popup_timer > 0:
        quest_popup_timer -= dt
    # Quest popup panel update
    if quest_popup_panel and quest_popup_panel.active:
        quest_popup_panel.update(dt)

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
        if getattr(m, 'stealthed', False): continue  # fully invisible when stealthed
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
        if m.is_boss or getattr(m, 'unique', False):
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
    elif getattr(hero, 'chill_visual', 0.0) > 0:
        s = s.copy()
        s.fill((100, 150, 255, 0), special_flags=pygame.BLEND_RGBA_ADD)  # Blue chill tint
    screen.blit(s, (sx, sy))

    # Demogorgon chill aura visual (blue ring) — visual only, player is slowed not frozen
    if getattr(hero, 'chill_visual', 0.0) > 0:
        pulse_c = int(70 + 30 * math.sin(game_state.game_time * 6))
        chill_surf = pygame.Surface((sw + 8, sh + 8), pygame.SRCALPHA)
        pygame.draw.circle(chill_surf, (150, 200, 255, pulse_c), (sw//2 + 4, sh//2 + 4), sw//2 + 4, 2)
        screen.blit(chill_surf, (sx - 4, sy - 4))

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

    # NPC rendering
    for npc in npcs:
        npc_sx = int((npc.x - cx) * cam_zoom + WIDTH // 2)
        npc_sy = int((npc.y - cy) * cam_zoom + HEIGHT // 2)
        # Draw NPC sprite
        if npc.sprite:
            sz = int(TILE_SIZE * cam_zoom)
            scaled = pygame.transform.scale(npc.sprite, (sz, sz))
            screen.blit(scaled, (npc_sx - sz // 2, npc_sy - sz // 2))
        else:
            pygame.draw.circle(screen, (100, 200, 100), (npc_sx, npc_sy), int(12 * cam_zoom))
        # Quest indicator above NPC
        indicator_y = npc_sy - int(38 * cam_zoom)
        if npc.has_turn_in():
            # Yellow "?" for turn-in ready
            ind_surf = big_font.render("?", True, GOLD)
            screen.blit(ind_surf, (npc_sx - ind_surf.get_width() // 2, indicator_y))
        elif npc.has_available_quest():
            # Yellow "!" for available quest
            ind_surf = big_font.render("!", True, GOLD)
            screen.blit(ind_surf, (npc_sx - ind_surf.get_width() // 2, indicator_y))
        # NPC name
        name_surf = font.render(npc.name, True, (100, 255, 100))
        screen.blit(name_surf, (npc_sx - name_surf.get_width() // 2, npc_sy - int(22 * cam_zoom)))

    # Floating text
    for t in floating_texts: t.draw(screen, cx, cy)

    # --- HUD ---
    hp_pct = hero.hp / hero.max_hp
    pygame.draw.rect(screen, HP_BG, (18,18,206,22))
    pygame.draw.rect(screen, HP_RED, (20,20,202,18))
    pygame.draw.rect(screen, HP_GREEN, (20,20,int(202*hp_pct),18))
    screen.blit(font.render(f"HP {hero.hp:.0f}/{hero.max_hp}", True, WHITE), (25,23))

    # XP bar (below HP bar)
    xp_needed = xp_to_next_level(hero.level) if hero.level < MAX_LEVEL else 1
    xp_pct = min(1.0, hero.xp / xp_needed) if hero.level < MAX_LEVEL else 1.0
    pygame.draw.rect(screen, HP_BG, (18, 42, 206, 12))
    pygame.draw.rect(screen, (60, 20, 80), (20, 44, 202, 8))
    pygame.draw.rect(screen, (180, 130, 255), (20, 44, int(202 * xp_pct), 8))
    xp_text = f"Lv {hero.level}  XP {hero.xp}/{xp_needed}" if hero.level < MAX_LEVEL else f"Lv {hero.level} MAX"
    screen.blit(font.render(xp_text, True, (200, 180, 255)), (25, 43))

    screen.blit(font.render(f"[F] Potions: {potions}", True, (200,150,150)), (20,58))

    # Companion health bars (top HUD, below potions)
    comp_hud_y = 74
    for comp, _ in companions:
        comp_hp_pct = comp.hp / comp.max_hp if comp.max_hp > 0 else 0
        bar_color = (100, 150, 255) if comp.alive else (80, 80, 80)
        pygame.draw.rect(screen, HP_BG, (18, comp_hud_y, 156, 14))
        pygame.draw.rect(screen, (40, 40, 60), (20, comp_hud_y + 2, 152, 10))
        pygame.draw.rect(screen, bar_color, (20, comp_hud_y + 2, int(152 * comp_hp_pct), 10))
        status = "" if comp.alive else " (dead)"
        screen.blit(font.render(f"{comp.name}{status}", True, WHITE), (22, comp_hud_y + 1))
        comp_hud_y += 16

    # Skill list (left side)
    ab_y = max(78, comp_hud_y + 4)
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
    screen.blit(font.render(MAP_ID.replace("_", " ").title(), True, BLUE), (WIDTH-160, 40))

    # Quest HUD (top center)
    quest_hud_y = 10
    active_quest_objs = quests.active_objects()
    if active_quest_objs:
        for aq in active_quest_objs:
            if aq.accepted and not aq.turned_in:
                quest_title = f"[Quest] {aq.title}"
                screen.blit(font.render(quest_title, True, GOLD), (WIDTH//2 - 120, quest_hud_y))
                quest_hud_y += 16
                if aq.objectives:
                    prog_text = aq.get_progress_text()
                    prog_color = (100, 255, 100) if aq.is_complete() else (200, 200, 200)
                    screen.blit(font.render(prog_text, True, prog_color), (WIDTH//2 - 120, quest_hud_y))
                    quest_hud_y += 16
                    if aq.is_complete():
                        screen.blit(font.render("Return to NPC", True, (100, 255, 100)), (WIDTH//2 - 120, quest_hud_y))
                        quest_hud_y += 16
                quest_hud_y += 4  # spacing between quests
    elif quests.available(hero.level):
        screen.blit(font.render("Visit an NPC for a new quest", True, (200, 200, 150)), (WIDTH//2 - 120, quest_hud_y))
    elif quests.quests:
        screen.blit(font.render(f"All quests completed! {MAP_ID.replace('_', ' ').title()} is safe.", True, (100, 255, 100)), (WIDTH//2 - 160, quest_hud_y))
    else:
        screen.blit(font.render(game_state.objective_text, True, (200,200,150)), (WIDTH//2-180, 10))

    # Quest popup (center screen notification — for kill-tracking "Quest Complete" etc.)
    if quest_popup_timer > 0 and quest_popup_text:
        alpha = min(255, int(255 * quest_popup_timer / 0.5)) if quest_popup_timer < 0.5 else 255
        for i, line in enumerate(quest_popup_text.split("\n")):
            popup_surf = font.render(line.strip(), True, quest_popup_color)
            screen.blit(popup_surf, (WIDTH//2 - popup_surf.get_width()//2, HEIGHT//3 + i * 20))

    # Quest popup panel (detailed accept/turn-in panel)
    if quest_popup_panel and quest_popup_panel.active:
        quest_popup_panel.draw(screen)

    # FPS counter
    fps = int(clock.get_fps())
    fps_color = HP_GREEN if fps >= 50 else (GOLD if fps >= 30 else HP_RED)
    screen.blit(font.render(f"FPS: {fps}", True, fps_color), (10, 10))

    # Controls help
    ai_label = "AI: ON (TAB=off)" if ai_enabled else "TAB=AI"
    ai_color = (100, 255, 100) if ai_enabled else (80, 80, 80)
    speed_label = f" {game_speed:.0f}x (+/-)" if game_speed > 1 else ""
    screen.blit(font.render(ai_label + speed_label, True, ai_color), (WIDTH - 160, HEIGHT - 18))
    screen.blit(font.render("LClick=Move  Shift+L=LSkill  RClick=RSkill  1/2/3=Switch  F=Pot  F1-F4=Summon", True, (70,70,70)), (10, HEIGHT-18))
    pygame.display.flip()

save_game()

# Stop any quest speech still playing when the session ends
if _tts_process and _tts_process.poll() is None:
    _tts_process.terminate()
