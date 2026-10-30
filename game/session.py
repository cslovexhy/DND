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
from game.input_script import InputScript
from game.engine.world import World
from game.engine.bootstrap import create_world, map_id_for
from game.client.local_host import LocalHost
from game.client.view import ClientView
from game.net.client import RemoteHost
from types import SimpleNamespace
from game.engine.player import PlayerState
from game.engine.commands import (MoveTo, SelectTarget, Cast, InteractNpc, AmbushTarget, UsePotion,
                                  ToggleAutopilot, ToggleCompanion, CancelChannel, BindLeftSkill, HoldPosition)
from game.engine import abilities
from game.engine.events import FloatText, Ring, LevelUp, QuestReady, BindRightSkill, NpcDialogue

# === EFFECTS ===
floating_texts = []
effects = []

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

def drain_events(events):
    """Turn the simulation's view events into on-screen effects / popups / saves."""
    global quest_popup_text, quest_popup_timer, quest_popup_color, right_skill_idx, quest_popup_panel
    for ev in events:
        if not view.is_mine(ev):
            continue   # another player's level-up / quest dialogue
        if isinstance(ev, FloatText):
            floating_texts.append(FloatingText(ev.x, ev.y, ev.text, ev.color))
        elif isinstance(ev, Ring):
            effects.append(AoeRing(ev.x, ev.y, ev.radius, ev.color))
        elif isinstance(ev, LevelUp):
            effects.append(LevelUpEffect(ev.x, ev.y))
            save_game()
        elif isinstance(ev, BindRightSkill):
            if ev.ability_key in ability_keys:
                right_skill_idx = ability_keys.index(ev.ability_key)
        elif isinstance(ev, NpcDialogue):
            quest_popup_panel = QuestPopupPanel(SimpleNamespace(**ev.quest), mode=ev.mode, npc_name=ev.npc_name)
            speak_text(ev.speech, ev.voice)
            save_game()
        elif isinstance(ev, QuestReady):
            quest_popup_text = f"Quest Complete: {ev.title} — Return to NPC"
            quest_popup_timer = 3.0
            quest_popup_color = (100, 255, 100)
            save_game()


# === GAME SETUP ===
# The simulation is built by engine/bootstrap.py (shared with pygame-free tools). Art is attached through hooks.
if CONNECT_PORT:
    # Remote host on this machine: no simulation here, the client only sees snapshots + events.
    host = RemoteHost("127.0.0.1", CONNECT_PORT, name=char_data["name"], class_name=char_data["class_name"])
    USE_MAP = host.welcome["map"]
    world = game_state = None
    companions = []
    world_map = WorldMap.load(USE_MAP)
else:
    try:
        world, player = create_world(USE_MAP, char_data, debug=DEBUG, autopilot=auto_mode,
                                     auto_companion=auto_mode and "--no-companion" not in sys.argv)
    except ValueError as e:
        print(f"ERROR: {e}")
        print("Please open the map in the map editor and place a 'Hero Start' marker.")
        pygame.quit()
        sys.exit(1)
    # Client <-> host. Single player: the host is in-process (LocalHost). The client reads only `view`.
    host = LocalHost(world)
    world_map = world.world_map    # static map data (tiles); the client draws it directly
    game_state = world.game_state  # host-side state: only used for the headless RESULT line and debug logs
    companions = world.companions  # host-side: debug logs only
MAP_ID = map_id_for(USE_MAP)  # key for per-map quest progress


def _attach_sprite(v):
    """Art for an entity the client just learned about (the simulation never deals with sprites)."""
    if v.kind in ("hero", "ally", "companion"):
        v.sprite = HERO_SPRITES[HERO_CLASS_BY_NAME[v.class_name]["sprite_key"]]
    elif v.kind == "monster":
        v.sprite = BOSS_SPRITES.get(v.name) or (BOSS_SPRITE if v.is_boss else MONSTER_SPRITES.get(v.name))
    elif v.kind == "npc" and v.sprite_tile:
        v.sprite = get_dungeon_tile(*v.sprite_tile)


view = ClientView(on_new_entity=_attach_sprite)
view.apply(host.snapshot())
hero = view.hero          # the local player's hero, as seen by the client
# F1-F4 summon one AI companion per class other than the player's own
available_companions = [c for c in HERO_CLASSES if c["class"] != hero.class_name]
if _audio_available:
    pygame.mixer.music.stop()
start_map_music(world_map.music)


def save_game():
    """Persist this character's progress (level/xp/gold/kills + this map's quest state). Host-side."""
    if not SAVING or world is None:
        return
    h = world.hero
    char_data.update({"level": h.level, "xp": h.xp, "gold": h.gold, "kills": h.kills})
    char_data.setdefault("quests", {})[MAP_ID] = world.quests.to_state()
    saves.save_character(char_data)


if world is not None:
    print(f"[SAVE] {char_data['name']} Lv{hero.level} XP={hero.xp} Gold={hero.gold} Kills={hero.kills} "
          f"on {MAP_ID}: active={world.quests.active} done={len(world.quests.completed)}")


def result_line(outcome):
    """Headless RESULT line. With a local sim it includes the full-state digest; a remote client
    only knows what its snapshots told it."""
    if world is not None:
        return format_result(outcome, game_state, world.hero)
    return (f"RESULT: {outcome} time={view.game_time:.1f}s hp={hero.hp:.0f}/{hero.max_hp} "
            f"kills={hero.kills} client=remote")

# Game speed (for AI observation)
game_speed = 4.0 if auto_mode else 1.0  # 1x, 2x, 4x

# Camera zoom (scroll wheel to adjust)
cam_zoom = 1.0       # 1.0 = default view, 2.0 = zoomed in 200%
CAM_ZOOM_MIN = 0.5   # Zoomed out (see more map)
CAM_ZOOM_MAX = 2.0   # Zoomed in (characters look bigger)
CAM_ZOOM_STEP = 0.1

# Skill slots (Diablo 2 style)
ability_keys = view.you.ability_keys  # ["Q", "R", "E"]
left_skill_idx = 0    # Index into ability_keys for left-click skill
right_skill_idx = 1   # Index into ability_keys for right-click skill


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


# Quest interaction state
quest_popup_timer = 0.0  # How long to show quest accepted/completed popup
quest_popup_text = ""
quest_popup_color = GOLD

def get_monster_at_screen(sx, sy):
    wx = (sx - WIDTH//2) / cam_zoom + hero.x
    wy = (sy - HEIGHT//2) / cam_zoom + hero.y
    for m in view.alive_monsters:
        if getattr(m, 'stealthed', False):
            continue  # stealthed monsters can't be clicked/targeted
        if abs(m.x - wx) < TILE_SIZE and abs(m.y - wy) < TILE_SIZE:
            return m
    return None


def get_npc_at_screen(sx, sy):
    """Check if a screen click hit an NPC sprite."""
    wx = (sx - WIDTH//2) / cam_zoom + hero.x
    wy = (sy - HEIGHT//2) / cam_zoom + hero.y
    for npc in view.npcs:
        if abs(npc.x - wx) < TILE_SIZE and abs(npc.y - wy) < TILE_SIZE:
            return npc
    return None


# === MAIN GAME LOOP ===
# Scripted input (headless regression tests): posts real pygame events on given ticks and fakes held modifiers.
_input_script = InputScript(HEADLESS.input_script) if HEADLESS.enabled and HEADLESS.input_script else None
key_mods = _input_script.key_mods if _input_script else pygame.key.get_mods
if world is not None:
    world.record_commands = bool(HEADLESS.enabled and HEADLESS.record_commands)
_tick = 0
_sent_hold = False                      # last HoldPosition / BindLeftSkill values sent to the sim
_sent_left = ability_keys[0]
running = True
return_to_menu = False
while running:
    if HEADLESS.enabled:
        dt = HEADLESS.fixed_dt   # simulated time: no sleeping, one fixed step per iteration
        if view.game_time >= HEADLESS.max_time or getattr(host, "closed", False):
            print(result_line("TIMEOUT"), flush=True)
            break
    else:
        dt = clock.tick(60) / 1000.0 * game_speed

    if _input_script:
        _input_script.post_due(_tick, hero, view, view.npcs, WIDTH, HEIGHT, cam_zoom)
    _tick += 1

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
                if view.you.frostbolt_channeling:
                    host.send(CancelChannel())  # cancel channel and stop auto-attack
                else:
                    running = False
                    return_to_menu = not auto_mode  # ESC -> back to character select
            if event.key == pygame.K_TAB:
                host.send(ToggleAutopilot())
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
            mods = key_mods()
            if mods & pygame.KMOD_CTRL:
                if event.key == pygame.K_1: left_skill_idx = 0
                if event.key == pygame.K_2: left_skill_idx = 1
                if event.key == pygame.K_3: left_skill_idx = 2 if len(ability_keys) > 2 else left_skill_idx
            # Potion
            if event.key == pygame.K_f:
                host.send(UsePotion())
            # Summon AI companions (F1-F4) — press again to dismiss
            summon_keys = [pygame.K_F1, pygame.K_F2, pygame.K_F3, pygame.K_F4]
            for ki, sk in enumerate(summon_keys):
                if event.key == sk and ki < len(available_companions):
                    host.send(ToggleCompanion(available_companions[ki]["class"]))
                    break

        if event.type == pygame.MOUSEBUTTONDOWN and not view.adventure_failed:
            mx_s, my_s = event.pos
            # If quest popup panel is open, intercept clicks
            if quest_popup_panel and quest_popup_panel.active:
                quest_popup_panel.handle_click(mx_s, my_s)
                continue
            wx = (mx_s - WIDTH//2) / cam_zoom + hero.x
            wy = (my_s - HEIGHT//2) / cam_zoom + hero.y
            clicked_monster = get_monster_at_screen(mx_s, my_s)
            shift_held = key_mods() & pygame.KMOD_SHIFT

            clicked_id = clicked_monster.eid if clicked_monster else None

            if event.button == 1:  # Left-click
                if shift_held:
                    # Shift+Left = cast LEFT skill
                    host.send(Cast(ability_keys[left_skill_idx], wx, wy, clicked_id))
                elif my_s >= HEIGHT - 55:
                    # Clicked on skill bar area — switch skills
                    if mx_s < WIDTH//2:
                        # Clicked left skill box — cycle left skill
                        left_skill_idx = (left_skill_idx + 1) % len(ability_keys)
                    else:
                        # Clicked right skill box — cycle right skill
                        right_skill_idx = (right_skill_idx + 1) % len(ability_keys)
                elif clicked_monster:
                    host.send(SelectTarget(clicked_id))   # select + walk to attack range
                else:
                    host.send(MoveTo(wx, wy))             # click ground = move

            elif event.button == 3:  # Right-click = cast RIGHT skill or interact with NPC
                # Check if clicking on an NPC first
                clicked_npc = get_npc_at_screen(mx_s, my_s)
                if clicked_npc:
                    host.send(InteractNpc(clicked_npc.eid))   # talk if in range, else walk to the NPC
                # Stealth + right-click enemy + Ambush on right slot = queue ambush walk-to
                elif hero.stealthed and clicked_monster and ability_keys[right_skill_idx] == "E":
                    host.send(AmbushTarget(clicked_id))
                else:
                    host.send(Cast(ability_keys[right_skill_idx], wx, wy, clicked_id, fallback_move=True))

    # --- End screen ---
    if view.adventure_failed:
        if world is not None:
            world.command_queue.clear()  # dead: input is ignored
        screen.fill(BG)
        msg = "DEFEATED..."
        t = title_font.render(msg, True, HP_RED)
        screen.blit(t, (WIDTH//2-t.get_width()//2, HEIGHT//2-20))
        stats = f"Time: {view.game_time:.1f}s  HP: {hero.hp:.0f}/{hero.max_hp}  Kills: {hero.kills}"
        screen.blit(big_font.render(stats, True, WHITE), (WIDTH//2-150, HEIGHT//2+20))
        screen.blit(font.render("Press ESC to return to character select", True, GRAY), (WIDTH//2-100, HEIGHT//2+55))
        pygame.display.flip()
        if auto_mode:
            print(result_line("DEFEATED"), flush=True)
            if not HEADLESS.enabled:
                pygame.time.wait(5000)
            running = False
        continue

    # --- UPDATE ---
    # Tell the sim about client choices that affect auto-attack (only when they change)
    _shift = bool(key_mods() & pygame.KMOD_SHIFT)
    if _shift != _sent_hold:
        host.send(HoldPosition(_shift)); _sent_hold = _shift
    if ability_keys[left_skill_idx] != _sent_left:
        _sent_left = ability_keys[left_skill_idx]; host.send(BindLeftSkill(_sent_left))

    snap, events = host.step(dt)   # the client only sees snapshots + events from the host
    if snap is not None:           # a remote host may not have sent a new frame yet
        view.apply(snap)
    drain_events(events)

    # Quest popup timer
    if quest_popup_timer > 0:
        quest_popup_timer -= dt
    # Quest popup panel update
    if quest_popup_panel and quest_popup_panel.active:
        quest_popup_panel.update(dt)

    floating_texts = [t for t in floating_texts if t.timer > 0]
    for t in floating_texts: t.update(dt)
    effects = [e for e in effects if e.timer > 0]
    for e in effects: e.update(dt)

    # --- FRAME LOG ---
    if DEBUG and world is not None:
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
    for wp in view.you.move_path[:8]:
        sx = int((wp[0] - cx) * cam_zoom + WIDTH//2)
        sy = int((wp[1] - cy) * cam_zoom + HEIGHT//2)
        pygame.draw.circle(screen, (60, 120, 60), (sx, sy), max(2, int(3 * cam_zoom)))

    # Effects
    for e in effects: e.draw(screen, cx, cy)

    # Monsters
    for m in view.monsters:
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
        if m is view.you.selected_target:
            pygame.draw.circle(screen, GOLD, (sx+sw//2, sy+sh//2), sw//2+4, 2)

    # Companions
    for comp in view.companions:
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

    # Other players (multiplayer)
    for ally in view.allies:
        if not ally.alive or not ally.sprite:
            continue
        asw, ash = int(ally.sprite.get_width() * cam_zoom), int(ally.sprite.get_height() * cam_zoom)
        asx = int((ally.x - cx) * cam_zoom + WIDTH//2 - asw//2)
        asy = int((ally.y - cy) * cam_zoom + HEIGHT//2 - ash//2)
        if asx < -asw or asx > WIDTH or asy < -ash or asy > HEIGHT:
            continue
        a_s = pygame.transform.flip(ally.sprite, True, False) if ally.facing_left else ally.sprite
        a_s = pygame.transform.scale(a_s, (asw, ash))
        if ally.stealthed:
            a_s = a_s.copy()
            a_s.set_alpha(100)
        screen.blit(a_s, (asx, asy))
        pygame.draw.rect(screen, HP_BG, (asx-1, asy-9, asw+2, 6))
        pygame.draw.rect(screen, HP_RED, (asx, asy-8, asw, 4))
        pygame.draw.rect(screen, HP_GREEN, (asx, asy-8, int(asw*ally.hp/ally.max_hp), 4))
        at = font.render(f"{ally.player_name} (Lv {ally.level})", True, GOLD)
        screen.blit(at, (asx + asw//2 - at.get_width()//2, asy - 22))

    # Projectiles
    for proj in view.projectiles:
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
        pulse_c = int(70 + 30 * math.sin(view.game_time * 6))
        chill_surf = pygame.Surface((sw + 8, sh + 8), pygame.SRCALPHA)
        pygame.draw.circle(chill_surf, (150, 200, 255, pulse_c), (sw//2 + 4, sh//2 + 4), sw//2 + 4, 2)
        screen.blit(chill_surf, (sx - 4, sy - 4))

    # Poison drip visual
    if hero.has_condition(Condition.POISONED):
        pulse_p = int(60 + 30 * math.sin(view.game_time * 5))
        poison_surf = pygame.Surface((sw + 6, sh + 6), pygame.SRCALPHA)
        pygame.draw.circle(poison_surf, (50, 200, 50, pulse_p), (sw//2 + 3, sh//2 + 3), sw//2 + 3, 2)
        screen.blit(poison_surf, (sx - 3, sy - 3))

    # Wall bubble shield visual
    if hero.absorb_shield > 0:
        bubble_r = sw // 2 + 8
        bubble_cx = sx + sw // 2
        bubble_cy = sy + sh // 2
        # Pulsing alpha
        pulse = int(80 + 40 * math.sin(view.game_time * 4))
        bubble_surf = pygame.Surface((bubble_r * 2 + 4, bubble_r * 2 + 4), pygame.SRCALPHA)
        pygame.draw.circle(bubble_surf, (100, 180, 255, pulse), (bubble_r + 2, bubble_r + 2), bubble_r, 3)
        pygame.draw.circle(bubble_surf, (100, 180, 255, pulse // 3), (bubble_r + 2, bubble_r + 2), bubble_r)
        screen.blit(bubble_surf, (bubble_cx - bubble_r - 2, bubble_cy - bubble_r - 2))

    # Renew visual (green sparkle indicator)
    if "Renew" in hero.buffs:
        renew_r = sw // 2 + 4
        renew_cx = sx + sw // 2
        renew_cy = sy + sh // 2
        pulse_g = int(60 + 30 * math.sin(view.game_time * 6))
        renew_surf = pygame.Surface((renew_r * 2 + 4, renew_r * 2 + 4), pygame.SRCALPHA)
        pygame.draw.circle(renew_surf, (80, 255, 120, pulse_g), (renew_r + 2, renew_r + 2), renew_r, 2)
        screen.blit(renew_surf, (renew_cx - renew_r - 2, renew_cy - renew_r - 2))

    # Frostbolt channeling bar
    if view.you.frostbolt_channeling:
        bar_w = 40
        bar_h = 5
        bar_x = sx + sw // 2 - bar_w // 2
        bar_y = sy - 14
        progress = 1.0 - (view.you.frostbolt_channel_timer / hero.weapon_speed)
        pygame.draw.rect(screen, (30, 30, 60), (bar_x - 1, bar_y - 1, bar_w + 2, bar_h + 2))
        pygame.draw.rect(screen, (60, 60, 80), (bar_x, bar_y, bar_w, bar_h))
        pygame.draw.rect(screen, (150, 200, 255), (bar_x, bar_y, int(bar_w * progress), bar_h))

    # NPC rendering
    for npc in view.npcs:
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

    screen.blit(font.render(f"[F] Potions: {view.you.potions}", True, (200,150,150)), (20,58))

    # Companion health bars (top HUD, below the potion count)
    comp_hud_y = 74
    for comp in view.companions:
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
        ab = view.you.abilities[key]
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
    left_ab = view.you.abilities[ability_keys[left_skill_idx]]
    left_color = (180, 130, 50) if left_ab.is_ready() else (80, 60, 30)
    pygame.draw.rect(screen, left_color, (WIDTH//2 - 180, bar_y, 160, 30), 0, 4)
    pygame.draw.rect(screen, (220, 170, 60), (WIDTH//2 - 180, bar_y, 160, 30), 2, 4)
    screen.blit(font.render(f"L: {left_ab.name}", True, WHITE), (WIDTH//2 - 175, bar_y + 8))
    # Right skill
    right_ab = view.you.abilities[ability_keys[right_skill_idx]]
    right_color = (50, 50, 140) if right_ab.is_ready() else (30, 30, 70)
    pygame.draw.rect(screen, right_color, (WIDTH//2 + 20, bar_y, 160, 30), 0, 4)
    pygame.draw.rect(screen, (80, 80, 200), (WIDTH//2 + 20, bar_y, 160, 30), 2, 4)
    screen.blit(font.render(f"R: {right_ab.name}", True, WHITE), (WIDTH//2 + 25, bar_y + 8))

    screen.blit(font.render(f"Kills: {hero.kills}  Gold: {hero.gold}", True, GOLD), (WIDTH-160, 20))
    screen.blit(font.render(MAP_ID.replace("_", " ").title(), True, BLUE), (WIDTH-160, 40))

    # Quest HUD (top center)
    quest_hud_y = 10
    vq = view.you.quests
    if vq.active:
        for aq in vq.active:
            if aq.accepted and not aq.turned_in:
                quest_title = f"[Quest] {aq.title}"
                screen.blit(font.render(quest_title, True, GOLD), (WIDTH//2 - 120, quest_hud_y))
                quest_hud_y += 16
                if aq.has_objectives:
                    prog_text = aq.progress_text
                    prog_color = (100, 255, 100) if aq.complete else (200, 200, 200)
                    screen.blit(font.render(prog_text, True, prog_color), (WIDTH//2 - 120, quest_hud_y))
                    quest_hud_y += 16
                    if aq.complete:
                        screen.blit(font.render("Return to NPC", True, (100, 255, 100)), (WIDTH//2 - 120, quest_hud_y))
                        quest_hud_y += 16
                quest_hud_y += 4  # spacing between quests
    elif vq.any_available:
        screen.blit(font.render("Visit an NPC for a new quest", True, (200, 200, 150)), (WIDTH//2 - 120, quest_hud_y))
    elif vq.has_quests:
        screen.blit(font.render(f"All quests completed! {MAP_ID.replace('_', ' ').title()} is safe.", True, (100, 255, 100)), (WIDTH//2 - 160, quest_hud_y))
    else:
        screen.blit(font.render(view.objective_text, True, (200,200,150)), (WIDTH//2-180, 10))

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
    ai_label = "AI: ON (TAB=off)" if view.you.ai_enabled else "TAB=AI"
    ai_color = (100, 255, 100) if view.you.ai_enabled else (80, 80, 80)
    speed_label = f" {game_speed:.0f}x (+/-)" if game_speed > 1 else ""
    screen.blit(font.render(ai_label + speed_label, True, ai_color), (WIDTH - 160, HEIGHT - 18))
    screen.blit(font.render("LClick=Move  Shift+L=LSkill  RClick=RSkill  1/2/3=Switch  F=Pot  F1-F4=Summon", True, (70,70,70)), (10, HEIGHT-18))
    pygame.display.flip()

if world is not None and world.record_commands:
    from game.engine.replay import save_recording
    save_recording(HEADLESS.record_commands,
                   {"map": USE_MAP, "class_name": hero.class_name, "seed": HEADLESS.seed,
                    "max_time": HEADLESS.max_time}, world)

save_game()

if CONNECT_PORT:
    host.close()

# Stop any quest speech still playing when the session ends
if _tts_process and _tts_process.poll() is None:
    _tts_process.terminate()
