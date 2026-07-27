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
from game.engine.entities import Hero, Monster, Ability, Condition, GameState
from game.engine.dungeon import UnifiedDungeon, RoomType, TILE_SIZE
from game.engine.ai import run_monster_ai, setup_monster_aggro, call_for_help
from game.engine.pathfinding import astar
from game.content.heroes import ALL_HEROES

os.chdir(os.path.dirname(os.path.dirname(__file__)))

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
dungeon_img = pygame.image.load("assets/kenney_dungeon/Tilemap/tilemap.png").convert_alpha()
creature_img = pygame.image.load("assets/tiny_creatures/tiny-creatures/Tilemap/tilemap.png").convert_alpha()

def get_dungeon_tile(col, row):
    x, y = col*(TILE_SRC+1), row*(TILE_SRC+1)
    s = pygame.Surface((TILE_SRC, TILE_SRC), pygame.SRCALPHA)
    s.blit(dungeon_img, (0,0), (x,y,TILE_SRC,TILE_SRC))
    return pygame.transform.scale(s, (TILE_SIZE, TILE_SIZE))

def get_creature(col, row, scale=TILE_SIZE):
    x, y = col*(TILE_SRC+1), row*(TILE_SRC+1)
    s = pygame.Surface((TILE_SRC, TILE_SRC), pygame.SRCALPHA)
    s.blit(creature_img, (0,0), (x,y,TILE_SRC,TILE_SRC))
    return pygame.transform.scale(s, (scale, scale))

# Environment
SPR_FLOOR = get_dungeon_tile(0, 0)
SPR_FLOOR2 = get_dungeon_tile(1, 0)
SPR_WALL = get_dungeon_tile(3, 0)

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
    "Human Cultist": get_creature(5, 7),
    "Duergar Guard": get_creature(4, 12),
    "Legion Devil": get_creature(8, 3),
    "Cave Bear": get_creature(3, 17),
    "Grell": get_creature(5, 0),
    "Gibbering Mouther": get_creature(4, 8),
}
BOSS_SPRITE = get_creature(9, 7, int(TILE_SIZE * 1.5))

# === EFFECTS ===
floating_texts = []
effects = []

class FloatingText:
    def __init__(self, x, y, text, color):
        self.x, self.y, self.text, self.color = x, y, text, color
        self.timer = 0.8
    def update(self, dt): self.timer -= dt; self.y -= 50*dt
    def draw(self, s, cx, cy):
        t = font.render(self.text, True, self.color)
        s.blit(t, (int(self.x-cx+WIDTH//2)-t.get_width()//2, int(self.y-cy+HEIGHT//2)))

class AoeRing:
    def __init__(self, x, y, radius, color):
        self.x, self.y, self.max_r, self.color = x, y, radius, color
        self.timer = 0.3
    def update(self, dt): self.timer -= dt
    def draw(self, s, cx, cy):
        sx, sy = int(self.x-cx+WIDTH//2), int(self.y-cy+HEIGHT//2)
        p = 1.0 - self.timer/0.3
        r = int(self.max_r * p)
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
                selected_hero_idx = (selected_hero_idx - 1) % len(ALL_HEROES)
            if event.key in (pygame.K_RIGHT, pygame.K_d):
                selected_hero_idx = (selected_hero_idx + 1) % len(ALL_HEROES)
            if event.key in (pygame.K_RETURN, pygame.K_SPACE):
                selecting = False
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mx_click, my_click = event.pos
            for i in range(len(ALL_HEROES)):
                px = 30 + i * (PANEL_W + 20)
                py = 160
                if px <= mx_click <= px + PANEL_W and py <= my_click <= py + PANEL_H:
                    if selected_hero_idx == i:
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
        # Panel background
        if i == selected_hero_idx:
            pygame.draw.rect(screen, (60, 60, 100), (x, y, PANEL_W, PANEL_H), 0, 6)
            pygame.draw.rect(screen, GOLD, (x, y, PANEL_W, PANEL_H), 2, 6)
        else:
            pygame.draw.rect(screen, (35, 35, 50), (x, y, PANEL_W, PANEL_H), 0, 6)

        # Sprite centered
        spr = HERO_SPRITES[h_info["sprite_key"]]
        big_spr = pygame.transform.scale(spr, (64, 64))
        screen.blit(big_spr, (x + PANEL_W//2 - 32, y + 15))

        # Name
        nt = big_font.render(h_info["name"], True, WHITE)
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
dungeon = UnifiedDungeon()
dungeon.generate(num_rooms=7, quest_room_name="Tunnel Exit")

hero_wx, hero_wy = dungeon.get_start_pos()
hero_info = ALL_HEROES[selected_hero_idx]
hero = hero_info["create"](hero_wx, hero_wy)
hero.sprite = HERO_SPRITES[hero_info["sprite_key"]]

game_state = GameState()
game_state.heroes.append(hero)
game_state.life_tokens = 2
game_state.objective_text = "Find the Tunnel Exit and defeat the Kobold Dragonlord!"

# Movement state
move_path = []
selected_target = None
potions = 3
victory = False

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

# Hero AI (toggle with TAB)
from game.engine.hero_ai import create_hero_ai
hero_ai = create_hero_ai(hero)
ai_enabled = auto_mode  # Auto mode starts with AI on

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
        boss = Monster("Meerak", "Reptile", wx, wy, hp=6, ac=17, speed=5,
                       attack_bonus=8, attack_damage=1, experience=5, is_boss=True)
        boss.sprite = BOSS_SPRITE
        setup_monster_aggro(boss)
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
            m.ranged_attack_damage = m.attack_damage
        setup_monster_aggro(m)
        game_state.monsters.append(m)

def is_wall(wx, wy):
    return dungeon.is_wall(wx, wy)

def get_monster_at_screen(sx, sy):
    wx = sx + hero.x - WIDTH//2
    wy = sy + hero.y - HEIGHT//2
    for m in game_state.alive_monsters:
        if abs(m.x - wx) < TILE_SIZE and abs(m.y - wy) < TILE_SIZE:
            return m
    return None

def _cast_ability(ab_key, ab, wx, wy, clicked_monster):
    """Cast an ability — handles AoE, single target, dash, stun, call-for-help."""
    global move_path, selected_target, dash_active, dash_target_x, dash_target_y, dash_stun_target, dash_stun_duration, dash_damage
    if ab.radius > 0:
        # AoE — check if click location is within ability range
        dist_to_click = math.sqrt((wx - hero.x)**2 + (wy - hero.y)**2)
        if dist_to_click > ab.range and ab.range > 0:
            floating_texts.append(FloatingText(hero.x, hero.y - 30, "Too far!", (255, 100, 100)))
            return
        hits = hero.use_ability(ab_key, game_state.alive_monsters, target_pos=(wx, wy))
        effects.append(AoeRing(wx, wy, ab.radius, ab.color))
        for name, dmg in hits:
            floating_texts.append(FloatingText(wx, wy-20, f"{dmg:.0f}", GOLD))
    elif clicked_monster:
        # Single target — check range
        dist_to_target = hero.distance_to(clicked_monster)
        if dist_to_target > ab.range:
            floating_texts.append(FloatingText(hero.x, hero.y - 30, "Too far!", (255, 100, 100)))
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
                dash_damage = ab.damage
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
    move_path = []
    selected_target = None

# === MAIN GAME LOOP ===
running = True
while running:
    dt = clock.tick(60) / 1000.0

    for event in pygame.event.get():
        if event.type == pygame.QUIT: running = False
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE: running = False
            if event.key == pygame.K_TAB:
                ai_enabled = not ai_enabled
            # 1,2,3 = switch right-click skill
            if event.key == pygame.K_1: right_skill_idx = 0
            if event.key == pygame.K_2: right_skill_idx = 1
            if event.key == pygame.K_3: right_skill_idx = 2 if len(ability_keys) > 2 else right_skill_idx
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

        if event.type == pygame.MOUSEBUTTONDOWN and not victory and not game_state.adventure_failed:
            mx_s, my_s = event.pos
            wx = mx_s + hero.x - WIDTH//2
            wy = my_s + hero.y - HEIGHT//2
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
                    # Click enemy = select only (no walk)
                    selected_target = clicked_monster
                    move_path = []
                else:
                    # Click ground = move
                    move_path = astar(dungeon, hero.x, hero.y, wx, wy)
                    selected_target = None

            elif event.button == 3:  # Right-click = cast RIGHT skill
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
        screen.blit(font.render("Press ESC to quit", True, GRAY), (WIDTH//2-50, HEIGHT//2+30))
        pygame.display.flip()
        continue

    # --- UPDATE ---
    game_state.update(dt)
    alive = game_state.alive_monsters

    # Smooth movement along path
    if move_path and not dash_active:
        tx, ty = move_path[0]
        dx, dy = tx - hero.x, ty - hero.y
        dist = math.sqrt(dx*dx + dy*dy)
        if dist < 8:
            move_path.pop(0)
        else:
            spd = hero.base_speed * dt
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
        if int(game_state.game_time * 2) != int((game_state.game_time - dt) * 2):  # Log every 0.5s
            alive_count = len(game_state.alive_monsters)
            target_dist = f" target_dist={hero.distance_to(hero_ai.target):.0f}" if hero_ai.target and hero_ai.target.alive else ""
            action_name = ai_action['use_ability'] or ('DASH' if ai_action.get('dash') else ('MOVE' if ai_action.get('move_to') else ('BASIC_ATK' if ai_action.get('basic_attack') else ('EXPLORE' if not alive_count else 'IDLE'))))
            print(f"[AI t={game_state.game_time:.1f}s] monsters={alive_count} hp={hero.hp:.0f}/{hero.max_hp} pos=({hero.x:.0f},{hero.y:.0f}) action={action_name}{target_dist}", flush=True)

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
                if ab.radius > 0:
                    pos = ai_action["ability_target_pos"] or (hero.x, hero.y)
                    hits = hero.use_ability(ab_key, game_state.alive_monsters, target_pos=pos)
                    effects.append(AoeRing(pos[0], pos[1], ab.radius, ab.color))
                    for name, dmg in hits:
                        floating_texts.append(FloatingText(pos[0], pos[1]-20, f"{dmg:.0f}", GOLD))
                elif ai_action["ability_target_monster"]:
                    target_m = ai_action["ability_target_monster"]
                    hits = hero.use_ability(ab_key, [target_m])
                    for name, dmg in hits:
                        floating_texts.append(FloatingText(target_m.x, target_m.y-20, f"{dmg:.0f}", WHITE))
                    call_for_help(target_m, game_state.monsters, hero)

        elif ai_action["move_to"] and not move_path:
            tx, ty = ai_action["move_to"]
            # Try direct movement first
            old_x, old_y = hero.x, hero.y
            hero.move_toward(tx, ty, dt, is_wall)
            hero.facing_left = (tx - hero.x) < 0
            # If stuck (didn't move), use pathfinding
            if abs(hero.x - old_x) < 0.5 and abs(hero.y - old_y) < 0.5:
                move_path = astar(dungeon, hero.x, hero.y, tx, ty)

        elif ai_action.get("basic_attack"):
            # Auto-attack when abilities on cooldown
            target_m = ai_action["basic_attack"]
            if target_m.alive and hero.distance_to(target_m) <= hero.attack_range:
                dmg = hero.try_basic_attack(target_m)
                if dmg:
                    floating_texts.append(FloatingText(target_m.x, target_m.y-15, f"{dmg:.0f}", WHITE))
                    call_for_help(target_m, game_state.monsters, hero)

        else:
            # No enemies and no action — explore! Move toward next unexplored room
            for r in dungeon.rooms:
                if not r.explored:
                    target_x = r.center_x * TILE_SIZE
                    target_y = r.center_y * TILE_SIZE
                    # Use pathfinding for exploration
                    if not move_path:
                        move_path = astar(dungeon, hero.x, hero.y, target_x, target_y)
                    break

    # Auto-attack selected target (only if in range — no auto-walk)
    if selected_target:
        if not selected_target.alive:
            selected_target = None
        else:
            dist = hero.distance_to(selected_target)
            if dist <= hero.attack_range:
                dmg = hero.try_basic_attack(selected_target)
                if dmg:
                    floating_texts.append(FloatingText(selected_target.x, selected_target.y-15, f"{dmg:.0f}", WHITE))
                    call_for_help(selected_target, game_state.monsters, hero)

    # Room exploration — spawn monsters when hero enters new room
    new_room = dungeon.update_exploration(hero.x, hero.y)
    if new_room:
        spawn_monsters_for_room(new_room)

    # Monster AI — all alive monsters with aggro system
    for m in alive:
        result = run_monster_ai(m, [hero], dt, is_wall, all_monsters=game_state.monsters)
        if result and result[0] in ("attack", "ranged_attack", "aoe_attack"):
            floating_texts.append(FloatingText(hero.x+random.randint(-10,10), hero.y-30, f"{result[2]:.0f}", HP_RED))

    # Kills
    for m in game_state.monsters:
        if not m.alive and m.experience > 0:
            hero.xp += m.experience
            hero.gold += random.randint(10,30) * m.experience
            hero.kills += 1
            floating_texts.append(FloatingText(m.x, m.y+10, f"+{m.experience}xp", GOLD))
            m.experience = 0
            if m.is_boss: victory = True

    if not hero.alive:
        game_state.check_hero_death(hero)

    floating_texts = [t for t in floating_texts if t.timer > 0]
    for t in floating_texts: t.update(dt)
    effects = [e for e in effects if e.timer > 0]
    for e in effects: e.update(dt)

    # --- RENDER ---
    screen.fill(BG)
    cx, cy = hero.x, hero.y

    # Draw visible tiles (only explored rooms + corridors between them)
    # Render window in tiles
    view_left = int((cx - WIDTH//2) // TILE_SIZE) - 1
    view_top = int((cy - HEIGHT//2) // TILE_SIZE) - 1
    view_right = view_left + WIDTH // TILE_SIZE + 3
    view_bottom = view_top + HEIGHT // TILE_SIZE + 3

    for ty in range(max(0, view_top), min(dungeon.grid_h, view_bottom)):
        for tx in range(max(0, view_left), min(dungeon.grid_w, view_right)):
            # Fog of war: only draw if in an explored room or corridor adjacent to explored room
            tile = dungeon.tiles[ty][tx]
            if tile == "wall":
                # Only draw walls adjacent to explored floor
                visible = False
                for ddy in range(-1, 2):
                    for ddx in range(-1, 2):
                        ntx, nty = tx+ddx, ty+ddy
                        if 0 <= nty < dungeon.grid_h and 0 <= ntx < dungeon.grid_w:
                            if dungeon.tiles[nty][ntx] == "floor":
                                # Check if any explored room contains this neighbor
                                for r in dungeon.rooms:
                                    if r.explored and r.contains_tile(ntx, nty):
                                        visible = True
                                        break
                                # Also show corridor walls if adjacent rooms explored
                                if not visible:
                                    for r in dungeon.rooms:
                                        if r.explored:
                                            # Show corridor region between explored rooms
                                            if abs(ntx - r.center_x) < r.width and abs(nty - r.center_y) < r.height + 5:
                                                visible = True
                                                break
                    if visible: break
                if not visible:
                    continue
                sx = int(tx * TILE_SIZE - cx + WIDTH//2)
                sy = int(ty * TILE_SIZE - cy + HEIGHT//2)
                screen.blit(SPR_WALL, (sx, sy))
            else:
                # Floor: show if in explored room or in corridor between explored rooms
                visible = False
                for r in dungeon.rooms:
                    if r.explored and r.contains_tile(tx, ty):
                        visible = True
                        break
                # Corridor visibility: show if between two explored rooms
                if not visible:
                    for r in dungeon.rooms:
                        if r.explored:
                            if abs(tx - r.center_x) < r.width + 8 and abs(ty - r.center_y) < r.height + 4:
                                visible = True
                                break
                if not visible:
                    continue
                sx = int(tx * TILE_SIZE - cx + WIDTH//2)
                sy = int(ty * TILE_SIZE - cy + HEIGHT//2)
                screen.blit(SPR_FLOOR if (tx+ty) % 5 != 0 else SPR_FLOOR2, (sx, sy))

    # Move path dots
    for wp in move_path[:8]:
        sx = int(wp[0] - cx + WIDTH//2)
        sy = int(wp[1] - cy + HEIGHT//2)
        pygame.draw.circle(screen, (60, 120, 60), (sx, sy), 3)

    # Effects
    for e in effects: e.draw(screen, cx, cy)

    # Monsters
    for m in game_state.monsters:
        if not m.alive: continue
        spr = m.sprite
        if not spr: continue
        sw, sh = spr.get_size()
        sx = int(m.x - cx + WIDTH//2 - sw//2)
        sy = int(m.y - cy + HEIGHT//2 - sh//2)
        if sx < -sw or sx > WIDTH or sy < -sh or sy > HEIGHT: continue
        s = pygame.transform.flip(spr, True, False) if m.facing_left else spr
        if m.flash_timer > 0:
            f = s.copy(); f.fill((255,255,255,200), special_flags=pygame.BLEND_RGBA_ADD)
            screen.blit(f, (sx, sy))
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

    # Hero
    spr = hero.sprite
    sw, sh = spr.get_size()
    sx = int(hero.x - cx + WIDTH//2 - sw//2)
    sy = int(hero.y - cy + HEIGHT//2 - sh//2)
    s = pygame.transform.flip(spr, True, False) if hero.facing_left else spr
    screen.blit(s, (sx, sy))

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
    screen.blit(font.render(f"Room: {dungeon.current_room.name}", True, BLUE), (WIDTH-160, 40))
    screen.blit(font.render(game_state.objective_text, True, (200,200,150)), (WIDTH//2-180, 10))

    # Minimap
    mm_x, mm_y = WIDTH-120, HEIGHT-100
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
    screen.blit(font.render(ai_label, True, ai_color), (WIDTH - 130, HEIGHT - 18))
    screen.blit(font.render("LClick=Move  Shift+L=LSkill  RClick=RSkill  1/2/3=Switch  F=Pot", True, (70,70,70)), (10, HEIGHT-18))
    pygame.display.flip()

pygame.quit()
