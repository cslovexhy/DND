"""
Wrath of Ashardalon - Sprite Showcase
Shows all actual monster/hero sprites from the Tiny Creatures + Tiny Dungeon packs.

Controls: WASD=Move, Q/R/E=Abilities, SPACE=Attack, F=Potion, ESC=Quit
"""
import pygame
import math
import random
import os

pygame.init()
SCALE = 3
TILE_SRC = 16
TILE_SIZE = TILE_SRC * SCALE
WIDTH, HEIGHT = 1024, 768
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Wrath of Ashardalon — All Sprites")
clock = pygame.time.Clock()
font = pygame.font.Font(None, 20)
big_font = pygame.font.Font(None, 32)

# === LOAD TILEMAPS ===
DUNGEON_PATH = os.path.join(os.path.dirname(__file__), "assets", "kenney_dungeon", "Tilemap", "tilemap.png")
CREATURE_PATH = os.path.join(os.path.dirname(__file__), "assets", "tiny_creatures", "tiny-creatures", "Tilemap", "tilemap.png")

dungeon_img = pygame.image.load(DUNGEON_PATH).convert_alpha()
creature_img = pygame.image.load(CREATURE_PATH).convert_alpha()

def get_dungeon_tile(col, row):
    x = col * (TILE_SRC + 1)
    y = row * (TILE_SRC + 1)
    surf = pygame.Surface((TILE_SRC, TILE_SRC), pygame.SRCALPHA)
    surf.blit(dungeon_img, (0, 0), (x, y, TILE_SRC, TILE_SRC))
    return pygame.transform.scale(surf, (TILE_SIZE, TILE_SIZE))

def get_creature(col, row):
    x = col * (TILE_SRC + 1)
    y = row * (TILE_SRC + 1)
    surf = pygame.Surface((TILE_SRC, TILE_SRC), pygame.SRCALPHA)
    surf.blit(creature_img, (0, 0), (x, y, TILE_SRC, TILE_SRC))
    return pygame.transform.scale(surf, (TILE_SIZE, TILE_SIZE))

# === SPRITES ===
# Dungeon tiles
SPR_FLOOR_1 = get_dungeon_tile(0, 0)
SPR_FLOOR_2 = get_dungeon_tile(1, 0)
SPR_WALL = get_dungeon_tile(3, 0)

# Heroes (from Kenney Tiny Dungeon, row 7-8)
SPR_VISTRA = get_dungeon_tile(0, 8)    # Helmeted knight = Dwarf Fighter
SPR_QUINN = get_dungeon_tile(3, 8)     # Blonde = Human Cleric
SPR_KEYLETH = get_dungeon_tile(4, 7)   # Armored = Elf Paladin
SPR_TARAK = get_dungeon_tile(2, 7)     # Dark warrior = Half-Orc Rogue
SPR_HESKAN = get_dungeon_tile(0, 7)    # Purple wizard = Dragonborn Wizard

# Monsters (from Tiny Creatures tilemap - 10 cols × 18 rows)
SPR_ORC_SMASHER = get_creature(1, 1)       # Orc
SPR_ORC_ARCHER = get_creature(0, 1)        # Goblin/orc variant
SPR_KOBOLD = get_creature(9, 7)            # Kobold (small lizard rider)
SPR_SNAKE = get_creature(0, 4)             # Green asp/snake (row 4, not row 14!)
SPR_CAVE_BEAR = get_creature(3, 17)        # Brown bear
SPR_DUERGAR = get_creature(4, 12)          # Hobgoblin w/ chainmail = armored guard
SPR_CULTIST = get_creature(5, 7)           # Dark wizard
SPR_LEGION_DEVIL = get_creature(8, 3)      # BIG RED DEVIL (not the imp/bee!)
SPR_GIBBERING = get_creature(4, 8)         # Gelatinous/blob
SPR_GRELL = get_creature(5, 0)             # Floating eye

# Villains/Bosses (scaled up 1.5x to differentiate from regular versions)
def make_boss_sprite(col, row, tint=None):
    """Get creature sprite scaled larger for bosses."""
    x, y = col*(TILE_SRC+1), row*(TILE_SRC+1)
    surf = pygame.Surface((TILE_SRC, TILE_SRC), pygame.SRCALPHA)
    surf.blit(creature_img, (0,0), (x, y, TILE_SRC, TILE_SRC))
    if tint:
        surf.fill(tint, special_flags=pygame.BLEND_RGB_ADD)
    big_size = int(TILE_SIZE * 1.5)
    return pygame.transform.scale(surf, (big_size, big_size))

SPR_ASHARDALON = make_boss_sprite(3, 3)              # RED DRAGON (big!)
SPR_GAUTH = make_boss_sprite(5, 0)                   # Floating eye / beholder (big!)
SPR_RAGE_DRAKE = make_boss_sprite(8, 7)              # Dragonkin (big!)
SPR_KOBOLD_LORD = make_boss_sprite(9, 7, tint=(60, 30, 0))  # Kobold but bigger + gold tint
SPR_ORC_SHAMAN = make_boss_sprite(1, 1, tint=(40, 0, 60))   # Orc but bigger + purple tint (magic)
SPR_DUERGAR_CAPTAIN = make_boss_sprite(4, 12, tint=(50, 20, 0))  # Duergar bigger + bronze tint
SPR_OTYUGH = make_boss_sprite(2, 12)                 # Tentacle creature (big!)

# Colors
BG = (20, 15, 25)
HP_GREEN = (80, 220, 80)
HP_RED = (200, 50, 50)
HP_BG = (40, 20, 20)
GOLD_COLOR = (255, 215, 0)
WHITE = (255, 255, 255)
GRAY = (80, 80, 80)
ABILITY_READY = (40, 120, 40)

# === ROOM ===
ROOM_W, ROOM_H = 17, 13

def generate_room():
    tiles = []
    for ry in range(ROOM_H):
        row = []
        for rx in range(ROOM_W):
            if rx == 0 or rx == ROOM_W-1 or ry == 0 or ry == ROOM_H-1:
                row.append("wall")
            else:
                row.append("floor")
        tiles.append(row)
    for _ in range(random.randint(2, 4)):
        tiles[random.randint(2, ROOM_H-3)][random.randint(2, ROOM_W-3)] = "wall"
    return tiles

room = generate_room()

def draw_room(surface, cam_x, cam_y):
    for ry, row in enumerate(room):
        for rx, cell in enumerate(row):
            wx, wy = rx * TILE_SIZE, ry * TILE_SIZE
            sx = int(wx - cam_x + WIDTH//2)
            sy = int(wy - cam_y + HEIGHT//2)
            if -TILE_SIZE < sx < WIDTH+TILE_SIZE and -TILE_SIZE < sy < HEIGHT+TILE_SIZE:
                if cell == "wall":
                    surface.blit(SPR_WALL, (sx, sy))
                else:
                    surface.blit(SPR_FLOOR_1 if (rx+ry)%5 != 0 else SPR_FLOOR_2, (sx, sy))

def is_wall(x, y):
    tx, ty = int(x // TILE_SIZE), int(y // TILE_SIZE)
    if 0 <= ty < ROOM_H and 0 <= tx < ROOM_W:
        return room[ty][tx] == "wall"
    return True

# === ENTITIES ===
class Entity:
    def __init__(self, name, x, y, hp, armor, speed, atk_dmg, atk_range, atk_cd, sprite, is_boss=False):
        self.name = name
        self.x, self.y = x, y
        self.max_hp, self.hp = hp, hp
        self.armor = armor
        self.speed = speed
        self.atk_dmg = atk_dmg
        self.atk_range = atk_range
        self.atk_cd = atk_cd
        self.cd_remaining = 0.0
        self.alive = True
        self.sprite = sprite
        self.is_boss = is_boss
        self.flash_timer = 0
        self.xp_value = 5 if is_boss else 1
        self.facing_left = False

    def dist(self, o): return math.sqrt((self.x-o.x)**2 + (self.y-o.y)**2)

    def move_toward(self, tx, ty, dt):
        dx, dy = tx - self.x, ty - self.y
        d = math.sqrt(dx*dx + dy*dy)
        if d < 2: return
        spd = min(self.speed * dt, d)
        nx, ny = self.x + (dx/d)*spd, self.y + (dy/d)*spd
        if not is_wall(nx, self.y): self.x = nx
        if not is_wall(self.x, ny): self.y = ny
        self.facing_left = dx < 0

    def take_damage(self, raw):
        dmg = raw * (1.0 - self.armor)
        self.hp -= dmg
        self.flash_timer = 0.12
        if self.hp <= 0: self.hp = 0; self.alive = False
        return dmg

    def draw(self, surface, cam_x, cam_y):
        spr = pygame.transform.flip(self.sprite, True, False) if self.facing_left else self.sprite
        sw, sh = spr.get_size()
        sx = int(self.x - cam_x + WIDTH//2 - sw//2)
        sy = int(self.y - cam_y + HEIGHT//2 - sh//2)
        if self.flash_timer > 0:
            f = spr.copy(); f.fill((255,255,255,200), special_flags=pygame.BLEND_RGBA_ADD)
            surface.blit(f, (sx, sy))
        else:
            surface.blit(spr, (sx, sy))
        if self.hp < self.max_hp:
            bw = sw; bx, by = sx, sy - 8
            pygame.draw.rect(surface, HP_BG, (bx-1, by-1, bw+2, 6))
            pygame.draw.rect(surface, HP_RED, (bx, by, bw, 4))
            pygame.draw.rect(surface, HP_GREEN, (bx, by, int(bw * self.hp/self.max_hp), 4))
        if self.is_boss:
            txt = font.render(self.name, True, (255, 100, 100))
            surface.blit(txt, (sx + sw//2 - txt.get_width()//2, sy - 18))

class Hero(Entity):
    def __init__(self):
        sx, sy = ROOM_W//2 * TILE_SIZE, ROOM_H//2 * TILE_SIZE
        super().__init__("Vistra", sx, sy, hp=500, armor=0.35, speed=180,
                         atk_dmg=45, atk_range=55, atk_cd=0.5, sprite=SPR_VISTRA)
        self.abilities = {
            "Q": {"name": "Reaping Strike", "cd": 2.0, "remaining": 0, "damage": 65, "radius": 80, "color": (200, 200, 255)},
            "R": {"name": "Charge", "cd": 8.0, "remaining": 0, "damage": 130, "radius": 130, "color": (255, 160, 50)},
            "E": {"name": "Flaming Sphere", "cd": 6.0, "remaining": 0, "damage": 95, "radius": 90, "color": (255, 80, 0)},
        }
        self.xp, self.gold, self.kills, self.potions = 0, 0, 0, 3

    def update_cooldowns(self, dt):
        for ab in self.abilities.values(): ab["remaining"] = max(0, ab["remaining"] - dt)
        self.cd_remaining = max(0, self.cd_remaining - dt)
        self.flash_timer = max(0, self.flash_timer - dt)

# === EFFECTS ===
class FloatingText:
    def __init__(self, x, y, text, color):
        self.x, self.y, self.text, self.color = x, y, text, color
        self.timer = 0.8
    def update(self, dt): self.timer -= dt; self.y -= 50*dt
    def draw(self, s, cx, cy):
        txt = font.render(self.text, True, self.color)
        s.blit(txt, (int(self.x-cx+WIDTH//2)-txt.get_width()//2, int(self.y-cy+HEIGHT//2)))

class AoeRing:
    def __init__(self, x, y, radius, color):
        self.x, self.y, self.max_r, self.color = x, y, radius, color
        self.timer = 0.35
    def update(self, dt): self.timer -= dt
    def draw(self, s, cx, cy):
        sx, sy = int(self.x-cx+WIDTH//2), int(self.y-cy+HEIGHT//2)
        p = 1.0 - self.timer/0.35
        r = int(self.max_r * p)
        a = int(150 * (self.timer/0.35))
        if a > 0 and r > 0:
            surf = pygame.Surface((r*2, r*2), pygame.SRCALPHA)
            pygame.draw.circle(surf, (*self.color, a), (r, r), r, 3)
            pygame.draw.circle(surf, (*self.color, a//4), (r, r), r)
            s.blit(surf, (sx-r, sy-r))

# === GAME STATE ===
hero = Hero()
monsters = []
texts = []
effects = []
wave = 0
spawn_timer = 0

# All Wrath of Ashardalon monsters with correct sprites
MONSTER_TYPES = [
    {"name": "Kobold", "sprite": SPR_KOBOLD, "hp": 60, "armor": 0.1, "speed": 135, "dmg": 12},
    {"name": "Snake", "sprite": SPR_SNAKE, "hp": 40, "armor": 0.05, "speed": 145, "dmg": 10},
    {"name": "Orc Smasher", "sprite": SPR_ORC_SMASHER, "hp": 120, "armor": 0.18, "speed": 100, "dmg": 25},
    {"name": "Orc Archer", "sprite": SPR_ORC_ARCHER, "hp": 70, "armor": 0.10, "speed": 90, "dmg": 20},
    {"name": "Cultist", "sprite": SPR_CULTIST, "hp": 60, "armor": 0.08, "speed": 110, "dmg": 15},
    {"name": "Duergar", "sprite": SPR_DUERGAR, "hp": 130, "armor": 0.22, "speed": 90, "dmg": 22},
    {"name": "Legion Devil", "sprite": SPR_LEGION_DEVIL, "hp": 80, "armor": 0.15, "speed": 130, "dmg": 18},
    {"name": "Cave Bear", "sprite": SPR_CAVE_BEAR, "hp": 160, "armor": 0.20, "speed": 95, "dmg": 30},
    {"name": "Grell", "sprite": SPR_GRELL, "hp": 100, "armor": 0.12, "speed": 120, "dmg": 20},
    {"name": "Gibbering Mouther", "sprite": SPR_GIBBERING, "hp": 110, "armor": 0.12, "speed": 80, "dmg": 22},
]

BOSS_TYPES = [
    {"name": "Ashardalon", "sprite": SPR_ASHARDALON, "hp": 800, "armor": 0.30, "speed": 80, "dmg": 55},
    {"name": "Gauth", "sprite": SPR_GAUTH, "hp": 500, "armor": 0.25, "speed": 70, "dmg": 40},
    {"name": "Rage Drake", "sprite": SPR_RAGE_DRAKE, "hp": 400, "armor": 0.22, "speed": 110, "dmg": 35},
    {"name": "Otyugh", "sprite": SPR_OTYUGH, "hp": 600, "armor": 0.25, "speed": 65, "dmg": 45},
]

def spawn_wave():
    global wave, room
    wave += 1
    if wave % 6 == 0: room = generate_room()
    count = min(3 + wave, 8)
    for i in range(count):
        edge = random.choice(["top","bottom","left","right"])
        if edge == "top": mx, my = random.randint(2,ROOM_W-3)*TILE_SIZE, 1.5*TILE_SIZE
        elif edge == "bottom": mx, my = random.randint(2,ROOM_W-3)*TILE_SIZE, (ROOM_H-2)*TILE_SIZE
        elif edge == "left": mx, my = 1.5*TILE_SIZE, random.randint(2,ROOM_H-3)*TILE_SIZE
        else: mx, my = (ROOM_W-2)*TILE_SIZE, random.randint(2,ROOM_H-3)*TILE_SIZE

        if wave % 5 == 0 and i == 0:
            b = random.choice(BOSS_TYPES)
            m = Entity(b["name"], mx, my, b["hp"]+wave*15, b["armor"], b["speed"], b["dmg"], 55, 1.5, b["sprite"], True)
            m.xp_value = 10
        else:
            pool = MONSTER_TYPES[:min(len(MONSTER_TYPES), 2 + wave//2)]
            mt = random.choice(pool)
            m = Entity(mt["name"], mx, my, mt["hp"]+wave*3, mt["armor"], mt["speed"]+wave*2, mt["dmg"]+wave, 45, 1.3, mt["sprite"])
        monsters.append(m)

spawn_wave()

# === MAIN LOOP ===
running = True
while running:
    dt = clock.tick(60) / 1000.0
    spawn_timer += dt

    for event in pygame.event.get():
        if event.type == pygame.QUIT: running = False
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE: running = False
            if event.key == pygame.K_f and hero.potions > 0 and hero.hp < hero.max_hp:
                hero.potions -= 1; heal = min(150, hero.max_hp-hero.hp); hero.hp += heal
                texts.append(FloatingText(hero.x, hero.y-30, f"+{heal:.0f}", (100,255,100)))

    keys = pygame.key.get_pressed()
    mx_s, my_s = pygame.mouse.get_pos()
    mwx, mwy = mx_s + hero.x - WIDTH//2, my_s + hero.y - HEIGHT//2

    # Movement
    mvx, mvy = 0, 0
    if keys[pygame.K_a] or keys[pygame.K_LEFT]: mvx -= 1
    if keys[pygame.K_d] or keys[pygame.K_RIGHT]: mvx += 1
    if keys[pygame.K_w] or keys[pygame.K_UP]: mvy -= 1
    if keys[pygame.K_s] or keys[pygame.K_DOWN]: mvy += 1
    if mvx or mvy:
        mag = math.sqrt(mvx**2+mvy**2)
        nx, ny = hero.x+(mvx/mag)*hero.speed*dt, hero.y+(mvy/mag)*hero.speed*dt
        if not is_wall(nx, hero.y): hero.x = nx; hero.facing_left = mvx < 0
        if not is_wall(hero.x, ny): hero.y = ny

    hero.update_cooldowns(dt)
    alive = [m for m in monsters if m.alive]

    # Abilities
    if keys[pygame.K_q]:
        ab = hero.abilities["Q"]
        if ab["remaining"] <= 0 and alive:
            ab["remaining"] = ab["cd"]
            effects.append(AoeRing(hero.x, hero.y, ab["radius"], ab["color"]))
            for m in alive:
                if hero.dist(m) <= ab["radius"]:
                    d = m.take_damage(ab["damage"]); texts.append(FloatingText(m.x, m.y-20, f"{d:.0f}", (180,220,255)))

    if keys[pygame.K_r]:
        ab = hero.abilities["R"]
        if ab["remaining"] <= 0 and alive:
            ab["remaining"] = ab["cd"]
            effects.append(AoeRing(hero.x, hero.y, ab["radius"], ab["color"]))
            for m in alive:
                if hero.dist(m) <= ab["radius"]:
                    d = m.take_damage(ab["damage"]); texts.append(FloatingText(m.x, m.y-20, f"{d:.0f}", GOLD_COLOR))

    if keys[pygame.K_e]:
        ab = hero.abilities["E"]
        if ab["remaining"] <= 0:
            ab["remaining"] = ab["cd"]
            effects.append(AoeRing(mwx, mwy, ab["radius"], ab["color"]))
            for m in alive:
                if math.sqrt((m.x-mwx)**2+(m.y-mwy)**2) <= ab["radius"]:
                    d = m.take_damage(ab["damage"]); texts.append(FloatingText(m.x, m.y-20, f"{d:.0f}", (255,130,0)))

    if keys[pygame.K_SPACE] and hero.cd_remaining <= 0 and alive:
        c = min(alive, key=lambda m: hero.dist(m))
        if hero.dist(c) <= hero.atk_range:
            hero.cd_remaining = hero.atk_cd
            d = c.take_damage(hero.atk_dmg); texts.append(FloatingText(c.x, c.y-15, f"{d:.0f}", WHITE))

    # Monster AI
    for m in alive:
        m.flash_timer = max(0, m.flash_timer-dt)
        m.move_toward(hero.x, hero.y, dt)
        m.cd_remaining = max(0, m.cd_remaining-dt)
        if m.dist(hero) <= m.atk_range and m.cd_remaining <= 0:
            d = hero.take_damage(m.atk_dmg); m.cd_remaining = m.atk_cd
            texts.append(FloatingText(hero.x+random.randint(-10,10), hero.y-30, f"{d:.0f}", HP_RED))

    # Kills
    for m in list(monsters):
        if not m.alive and m.xp_value > 0:
            hero.xp += m.xp_value; g = random.randint(10,30)*m.xp_value; hero.gold += g; hero.kills += 1
            texts.append(FloatingText(m.x, m.y+10, f"+{g}g", GOLD_COLOR)); m.xp_value = 0
    monsters = [m for m in monsters if m.alive]

    if not monsters and spawn_timer > 1.5: spawn_wave(); spawn_timer = 0

    if not hero.alive:
        hero.hp = hero.max_hp; hero.alive = True
        hero.x, hero.y = ROOM_W//2*TILE_SIZE, ROOM_H//2*TILE_SIZE
        monsters.clear(); wave = max(0, wave-2); spawn_wave()

    texts = [t for t in texts if t.timer > 0]
    for t in texts: t.update(dt)
    effects = [e for e in effects if e.timer > 0]
    for e in effects: e.update(dt)

    # === RENDER ===
    screen.fill(BG)
    cx, cy = hero.x, hero.y
    draw_room(screen, cx, cy)
    for e in effects: e.draw(screen, cx, cy)
    for m in monsters: m.draw(screen, cx, cy)
    hero.draw(screen, cx, cy)
    for t in texts: t.draw(screen, cx, cy)

    # HUD
    hp_pct = hero.hp / hero.max_hp
    pygame.draw.rect(screen, HP_BG, (18,18,206,22))
    pygame.draw.rect(screen, HP_RED, (20,20,202,18))
    pygame.draw.rect(screen, HP_GREEN, (20,20,int(202*hp_pct),18))
    screen.blit(font.render(f"HP {hero.hp:.0f}/{hero.max_hp}", True, WHITE), (25,23))
    screen.blit(font.render(f"[F] Potions: {hero.potions}", True, (220,120,120)), (20,44))

    ab_y = 66
    for key, ab in [("Q", hero.abilities["Q"]), ("R", hero.abilities["R"]), ("E", hero.abilities["E"])]:
        ready = ab["remaining"] <= 0
        pygame.draw.rect(screen, ABILITY_READY if ready else GRAY, (20, ab_y, 180, 20))
        cd_val = ab["remaining"]
        cd_txt = "READY" if ready else f"{cd_val:.1f}s"
        screen.blit(font.render(f"[{key}] {ab['name']} {cd_txt}", True, WHITE), (24, ab_y+3))
        ab_y += 24

    for i, s in enumerate([f"Wave: {wave}", f"Kills: {hero.kills}", f"Gold: {hero.gold}", f"XP: {hero.xp}"]):
        screen.blit(font.render(s, True, GOLD_COLOR), (WIDTH-120, 20+i*20))

    if spawn_timer < 1.5 and wave > 1:
        boss = wave % 5 == 0
        t = big_font.render(f"{'⚠ BOSS ' if boss else ''}WAVE {wave}!", True, (255,50,50) if boss else (255,200,50))
        screen.blit(t, (WIDTH//2-t.get_width()//2, 80))

    screen.blit(font.render("WASD=Move Q/R/E=Abilities SPACE=Attack F=Potion ESC=Quit", True, (100,100,100)), (WIDTH//2-220, HEIGHT-22))
    pygame.display.flip()

pygame.quit()
