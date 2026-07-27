"""
Wrath of Ashardalon — Adventure 1: Escape the Tunnel
Uses the real game engine (entities, dungeon, AI).

Controls: WASD=Move, Q/R/E=Abilities, SPACE=Attack, F=Potion, ESC=Quit
Objective: Explore the dungeon, find the Tunnel Exit, defeat the Kobold Dragonlord!
"""
import pygame
import math
import random
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from game.engine.entities import Hero, Monster, Ability, Condition, GameState
from game.engine.dungeon import Dungeon, RoomType, TILE_SIZE, Direction
from game.engine.ai import run_monster_ai

# Change working dir to project root for asset loading
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

# === LOAD SPRITES ===
SCALE = 3
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
SPR_DOOR = get_dungeon_tile(9, 1)

# Hero
SPR_HERO = get_dungeon_tile(0, 8)  # Vistra

# Monsters
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
BOSS_SPRITE = get_creature(9, 7, int(TILE_SIZE * 1.5))  # Kobold Dragonlord (boss sized)

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

# === GAME SETUP ===
# Generate dungeon
dungeon = Dungeon()
dungeon.generate(num_rooms=7, quest_room_name="Tunnel Exit")

# Create hero (Vistra, Dwarf Fighter)
start_room = dungeon.rooms[0]
hero_x = start_room.world_x + start_room.width//2 * TILE_SIZE
hero_y = start_room.world_y + start_room.height//2 * TILE_SIZE

hero = Hero("Vistra", "Dwarf", "Fighter", hero_x, hero_y, hp=8, ac=17, speed=5, surge_value=4)
hero.attack_damage = 30
hero.attack_range = 55
hero.attack_cooldown = 0.5
hero.sprite = SPR_HERO
hero.add_ability("Q", Ability("Reaping Strike", cooldown=2.0, damage=50, radius=80, color=(180,200,255)))
hero.add_ability("R", Ability("Charge", cooldown=8.0, damage=100, radius=120, color=(255,160,50)))
hero.add_ability("E", Ability("Flaming Sphere", cooldown=6.0, damage=75, radius=90, range=300, color=(255,80,0)))

# Game state
game_state = GameState()
game_state.heroes.append(hero)
game_state.life_tokens = 2
game_state.objective_text = "Find the Tunnel Exit and defeat the Kobold Dragonlord!"

# Monster pool for this adventure
MONSTER_POOL = [
    {"name": "Kobold Dragonshield", "hp": 1, "ac": 16, "speed": 5, "atk": 7, "dmg": 1, "xp": 1},
    {"name": "Snake", "hp": 1, "ac": 13, "speed": 6, "atk": 7, "dmg": 0, "xp": 1, "condition": (Condition.POISONED, 3.0)},
    {"name": "Orc Smasher", "hp": 2, "ac": 15, "speed": 4, "atk": 9, "dmg": 1, "xp": 2},
    {"name": "Orc Archer", "hp": 1, "ac": 13, "speed": 4, "atk": 6, "dmg": 1, "xp": 1, "ranged": True},
]

def spawn_monsters_for_room(room):
    """Spawn monsters at room's spawn points."""
    if room.monsters_spawned or room.room_type == RoomType.START:
        return
    room.monsters_spawned = True

    if room.room_type == RoomType.QUEST:
        # Boss room: spawn Kobold Dragonlord
        sx = room.world_x + room.width//2 * TILE_SIZE
        sy = room.world_y + room.height//2 * TILE_SIZE
        boss = Monster("Meerak", "Reptile", sx, sy, hp=6, ac=17, speed=5,
                       attack_bonus=8, attack_damage=1, experience=5, is_boss=True)
        boss.sprite = BOSS_SPRITE
        game_state.monsters.append(boss)
        return

    for spawn_pos in room.monster_spawns:
        mt = random.choice(MONSTER_POOL)
        mx = room.world_x + spawn_pos[0] * TILE_SIZE
        my = room.world_y + spawn_pos[1] * TILE_SIZE
        m = Monster(mt["name"], "Monster", mx, my,
                    hp=mt["hp"], ac=mt["ac"], speed=mt["speed"],
                    attack_bonus=mt["atk"], attack_damage=mt["dmg"], experience=mt["xp"])
        m.sprite = MONSTER_SPRITES.get(mt["name"])
        if mt.get("condition"):
            m.on_hit_condition = mt["condition"]
        if mt.get("ranged"):
            m.ranged_attack_range = 250
            m.ranged_attack_damage = m.attack_damage
        game_state.monsters.append(m)

# Spawn monsters in first connected room (not start)
spawn_monsters_for_room(dungeon.rooms[0])

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

# === COLLISION ===
def is_wall(wx, wy):
    room = dungeon.current_room
    return dungeon.is_wall(room, wx, wy)

# === MAIN LOOP ===
running = True
victory = False
potions = 3

while running:
    dt = clock.tick(60) / 1000.0

    for event in pygame.event.get():
        if event.type == pygame.QUIT: running = False
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE: running = False
            if event.key == pygame.K_f and potions > 0 and hero.hp < hero.max_hp:
                potions -= 1
                heal = hero.heal(150)
                floating_texts.append(FloatingText(hero.x, hero.y-30, f"+{heal:.0f}", (100,255,100)))

    if victory or game_state.adventure_failed:
        # Show end screen
        screen.fill(BG)
        msg = "VICTORY! You escaped the tunnel!" if victory else "DEFEATED... No life tokens remain."
        color = GOLD if victory else HP_RED
        t = title_font.render(msg, True, color)
        screen.blit(t, (WIDTH//2-t.get_width()//2, HEIGHT//2-20))
        t2 = font.render("Press ESC to quit", True, GRAY)
        screen.blit(t2, (WIDTH//2-t2.get_width()//2, HEIGHT//2+30))
        pygame.display.flip()
        continue

    keys = pygame.key.get_pressed()
    mx_s, my_s = pygame.mouse.get_pos()
    mwx = mx_s + hero.x - WIDTH//2
    mwy = my_s + hero.y - HEIGHT//2

    # === MOVEMENT ===
    mvx, mvy = 0, 0
    if keys[pygame.K_a] or keys[pygame.K_LEFT]: mvx -= 1
    if keys[pygame.K_d] or keys[pygame.K_RIGHT]: mvx += 1
    if keys[pygame.K_w] or keys[pygame.K_UP]: mvy -= 1
    if keys[pygame.K_s] or keys[pygame.K_DOWN]: mvy += 1
    if mvx or mvy:
        mag = math.sqrt(mvx**2+mvy**2)
        hero.move_toward(hero.x + (mvx/mag)*200, hero.y + (mvy/mag)*200, dt, is_wall)

    # === CHECK DOOR TRANSITIONS ===
    room = dungeon.current_room
    door = dungeon.get_door_at(room, hero.x, hero.y)
    if door:
        next_room = dungeon.get_room(door.target_room_id)
        if next_room and not next_room.explored:
            dungeon.enter_room(door.target_room_id)
            # Move hero to the entry door of new room
            for d in next_room.doors:
                if d.target_room_id == room.id:
                    hero.x = next_room.world_x + d.x * TILE_SIZE
                    hero.y = next_room.world_y + d.y * TILE_SIZE
                    break
            spawn_monsters_for_room(next_room)

    # === ABILITIES ===
    game_state.update(dt)
    alive = game_state.alive_monsters

    if keys[pygame.K_q]:
        ab = hero.abilities["Q"]
        if ab.is_ready() and alive:
            hits = hero.use_ability("Q", alive)
            effects.append(AoeRing(hero.x, hero.y, ab.radius, ab.color))
            for name, dmg in hits:
                floating_texts.append(FloatingText(hero.x, hero.y-20, f"{dmg:.0f}", (180,220,255)))

    if keys[pygame.K_r]:
        ab = hero.abilities["R"]
        if ab.is_ready() and alive:
            hits = hero.use_ability("R", alive)
            effects.append(AoeRing(hero.x, hero.y, ab.radius, ab.color))
            for name, dmg in hits: floating_texts.append(FloatingText(hero.x, hero.y-20, f"{dmg:.0f}", GOLD))

    if keys[pygame.K_e]:
        ab = hero.abilities["E"]
        if ab.is_ready():
            hits = hero.use_ability("E", alive, target_pos=(mwx, mwy))
            effects.append(AoeRing(mwx, mwy, ab.radius, ab.color))
            for name, dmg in hits: floating_texts.append(FloatingText(mwx, mwy-20, f"{dmg:.0f}", (255,130,0)))

    if keys[pygame.K_SPACE]:
        dmg = hero.try_basic_attack(min(alive, key=lambda m: hero.distance_to(m)) if alive else hero)
        if dmg: floating_texts.append(FloatingText(hero.x+30, hero.y-15, f"{dmg:.0f}", WHITE))

    # === MONSTER AI ===
    for m in alive:
        result = run_monster_ai(m, [hero], dt, is_wall)
        if result and result[0] in ("attack", "ranged_attack", "aoe_attack"):
            floating_texts.append(FloatingText(hero.x+random.randint(-10,10), hero.y-30, f"{result[2]:.0f}", HP_RED))

    # === KILLS ===
    for m in game_state.monsters:
        if not m.alive and m.experience > 0:
            hero.xp += m.experience
            hero.gold += random.randint(10, 30) * m.experience
            hero.kills += 1
            floating_texts.append(FloatingText(m.x, m.y+10, f"+{m.experience}xp", GOLD))
            m.experience = 0
            # Boss kill = victory
            if m.is_boss:
                victory = True

    # === HERO DEATH ===
    if not hero.alive:
        game_state.check_hero_death(hero)

    # === UPDATE EFFECTS ===
    floating_texts = [t for t in floating_texts if t.timer > 0]
    for t in floating_texts: t.update(dt)
    effects = [e for e in effects if e.timer > 0]
    for e in effects: e.update(dt)

    # === RENDER ===
    screen.fill(BG)
    cx, cy = hero.x, hero.y

    # Draw all explored rooms
    for r in dungeon.rooms:
        if not r.explored:
            continue
        for ry, row in enumerate(r.tiles):
            for rx, cell in enumerate(row):
                wx = r.world_x + rx * TILE_SIZE
                wy = r.world_y + ry * TILE_SIZE
                sx = int(wx - cx + WIDTH//2)
                sy = int(wy - cy + HEIGHT//2)
                if -TILE_SIZE < sx < WIDTH+TILE_SIZE and -TILE_SIZE < sy < HEIGHT+TILE_SIZE:
                    if cell == "wall":
                        screen.blit(SPR_WALL, (sx, sy))
                    else:
                        screen.blit(SPR_FLOOR if (rx+ry)%5 != 0 else SPR_FLOOR2, (sx, sy))

        # Draw doors
        for door in r.doors:
            wx = r.world_x + door.x * TILE_SIZE
            wy = r.world_y + door.y * TILE_SIZE
            sx, sy = int(wx-cx+WIDTH//2), int(wy-cy+HEIGHT//2)
            pygame.draw.rect(screen, DOOR_COLOR, (sx+10, sy+10, TILE_SIZE-20, TILE_SIZE-20), 2)

    # Draw effects
    for e in effects: e.draw(screen, cx, cy)

    # Draw monsters
    for m in game_state.monsters:
        if not m.alive: continue
        spr = m.sprite
        if not spr: continue
        sw, sh = spr.get_size()
        sx = int(m.x - cx + WIDTH//2 - sw//2)
        sy = int(m.y - cy + HEIGHT//2 - sh//2)
        s = pygame.transform.flip(spr, True, False) if m.facing_left else spr
        if m.flash_timer > 0:
            f = s.copy(); f.fill((255,255,255,200), special_flags=pygame.BLEND_RGBA_ADD)
            screen.blit(f, (sx, sy))
        else:
            screen.blit(s, (sx, sy))
        # HP bar
        if m.hp < m.max_hp:
            pygame.draw.rect(screen, HP_BG, (sx-1, sy-9, sw+2, 6))
            pygame.draw.rect(screen, HP_RED, (sx, sy-8, sw, 4))
            pygame.draw.rect(screen, HP_GREEN, (sx, sy-8, int(sw*m.hp/m.max_hp), 4))
        if m.is_boss:
            t = font.render(m.name, True, (255,100,100))
            screen.blit(t, (sx+sw//2-t.get_width()//2, sy-20))

    # Draw hero
    spr = hero.sprite
    sw, sh = spr.get_size()
    sx = int(hero.x - cx + WIDTH//2 - sw//2)
    sy = int(hero.y - cy + HEIGHT//2 - sh//2)
    s = pygame.transform.flip(spr, True, False) if hero.facing_left else spr
    screen.blit(s, (sx, sy))

    # Draw floating text
    for t in floating_texts: t.draw(screen, cx, cy)

    # === HUD ===
    hp_pct = hero.hp / hero.max_hp
    pygame.draw.rect(screen, HP_BG, (18,18,206,22))
    pygame.draw.rect(screen, HP_RED, (20,20,202,18))
    pygame.draw.rect(screen, HP_GREEN, (20,20,int(202*hp_pct),18))
    screen.blit(font.render(f"HP {hero.hp:.0f}/{hero.max_hp}", True, WHITE), (25,23))
    screen.blit(font.render(f"[F] Potions: {potions}  |  Life Tokens: {game_state.life_tokens}", True, (200,150,150)), (20,44))

    ab_y = 66
    for key, ab in hero.abilities.items():
        ready = ab.is_ready()
        pygame.draw.rect(screen, ABILITY_READY if ready else GRAY, (20, ab_y, 180, 20))
        cd = "READY" if ready else f"{ab.remaining:.1f}s"
        screen.blit(font.render(f"[{key.upper()}] {ab.name} {cd}", True, WHITE), (24, ab_y+3))
        ab_y += 24

    # Stats + objective
    screen.blit(font.render(f"Kills: {hero.kills}  Gold: {hero.gold}  XP: {hero.xp}", True, GOLD), (WIDTH-200, 20))
    screen.blit(font.render(f"Room: {dungeon.current_room.name}", True, BLUE), (WIDTH-200, 40))

    # Objective
    screen.blit(font.render(game_state.objective_text, True, (200, 200, 150)), (WIDTH//2-180, 10))

    # Minimap
    mm_x, mm_y = WIDTH - 130, HEIGHT - 130
    pygame.draw.rect(screen, (30,30,40), (mm_x-5, mm_y-5, 125, 125))
    for r in dungeon.rooms:
        rx = mm_x + (r.grid_x - dungeon.rooms[0].grid_x) * 18 + 50
        ry = mm_y + (r.grid_y - dungeon.rooms[0].grid_y) * 18 + 50
        color = (60,60,80) if not r.explored else (100,100,140)
        if r.room_type == RoomType.QUEST and r.explored: color = (200, 50, 50)
        if r.id == dungeon.current_room_id: color = (100, 200, 255)
        pygame.draw.rect(screen, color, (rx, ry, 14, 14))

    # Controls
    screen.blit(font.render("WASD=Move Q/R/E=Abilities SPACE=Atk F=Potion | Explore rooms → Find exit → Kill boss!", True, (90,90,90)), (20, HEIGHT-20))

    pygame.display.flip()

pygame.quit()
