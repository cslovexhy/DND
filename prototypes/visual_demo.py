"""
ARPG Visual Demo — Playable Prototype
Controls:
  WASD / Arrow Keys = Move
  Q = Cleave (2s cooldown, AoE around hero)
  W = Sweeping Attack (9s cooldown, big AoE)
  E = Fireball (6s cooldown, ranged AoE at mouse)
  SPACE = Basic attack (closest enemy)
  
Run: python3 visual_demo.py
"""
import pygame
import math
import random
import sys

# === INIT ===
pygame.init()
WIDTH, HEIGHT = 1024, 768
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("D&D ARPG — Combat Demo")
clock = pygame.time.Clock()
font = pygame.font.Font(None, 24)
big_font = pygame.font.Font(None, 36)

# Colors
BG = (30, 30, 40)
FLOOR = (50, 45, 55)
HERO_COLOR = (80, 180, 255)
MONSTER_COLOR = (220, 60, 60)
ELITE_COLOR = (200, 50, 200)
HP_GREEN = (80, 220, 80)
HP_RED = (220, 60, 60)
GOLD = (255, 215, 0)
COOLDOWN_GRAY = (100, 100, 100)
ABILITY_READY = (60, 180, 60)
WHITE = (255, 255, 255)
DAMAGE_COLOR = (255, 100, 100)
HEAL_COLOR = (100, 255, 100)

# === GAME ENTITIES ===
class Entity:
    def __init__(self, name, x, y, hp, armor, speed, atk_dmg, atk_range, atk_cd, radius=12, color=MONSTER_COLOR):
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
        self.radius = radius
        self.color = color
        self.flash_timer = 0
        self.xp_value = 1

    def dist(self, other):
        return math.sqrt((self.x - other.x)**2 + (self.y - other.y)**2)

    def move_toward(self, tx, ty, dt):
        dx, dy = tx - self.x, ty - self.y
        d = math.sqrt(dx*dx + dy*dy)
        if d < 1:
            return
        spd = min(self.speed * dt, d)
        self.x += (dx/d) * spd
        self.y += (dy/d) * spd

    def take_damage(self, raw):
        dmg = raw * (1.0 - self.armor)
        self.hp -= dmg
        self.flash_timer = 0.15
        if self.hp <= 0:
            self.hp = 0
            self.alive = False
        return dmg

    def draw(self, surface, camera_x, camera_y):
        sx = int(self.x - camera_x + WIDTH//2)
        sy = int(self.y - camera_y + HEIGHT//2)
        color = (255, 255, 255) if self.flash_timer > 0 else self.color
        pygame.draw.circle(surface, color, (sx, sy), self.radius)
        # HP bar
        bar_w = self.radius * 2 + 4
        bar_h = 4
        bx = sx - bar_w//2
        by = sy - self.radius - 10
        hp_pct = self.hp / self.max_hp
        pygame.draw.rect(surface, HP_RED, (bx, by, bar_w, bar_h))
        pygame.draw.rect(surface, HP_GREEN, (bx, by, int(bar_w * hp_pct), bar_h))


class Hero(Entity):
    def __init__(self):
        super().__init__("Fighter", 400, 400, hp=500, armor=0.35, speed=200,
                         atk_dmg=45, atk_range=50, atk_cd=0.6, radius=16, color=HERO_COLOR)
        self.abilities = {
            "Q": {"name": "Cleave", "cd": 2.0, "remaining": 0, "damage": 60, "radius": 70, "range": 70, "type": "aoe_self"},
            "W": {"name": "Sweeping Attack", "cd": 9.0, "remaining": 0, "damage": 120, "radius": 120, "range": 120, "type": "aoe_self"},
            "E": {"name": "Fireball", "cd": 6.0, "remaining": 0, "damage": 90, "radius": 80, "range": 300, "type": "aoe_target"},
        }
        self.xp = 0
        self.gold = 0
        self.kills = 0

    def update_cooldowns(self, dt):
        for ab in self.abilities.values():
            ab["remaining"] = max(0, ab["remaining"] - dt)
        self.cd_remaining = max(0, self.cd_remaining - dt)


# === FLOATING TEXT ===
class FloatingText:
    def __init__(self, x, y, text, color, duration=1.0):
        self.x, self.y = x, y
        self.text = text
        self.color = color
        self.timer = duration
        self.duration = duration

    def update(self, dt):
        self.timer -= dt
        self.y -= 40 * dt

    def draw(self, surface, cx, cy):
        alpha = int(255 * (self.timer / self.duration))
        sx = int(self.x - cx + WIDTH//2)
        sy = int(self.y - cy + HEIGHT//2)
        txt = font.render(self.text, True, self.color)
        surface.blit(txt, (sx - txt.get_width()//2, sy))


# === AOE EFFECT ===
class AoeEffect:
    def __init__(self, x, y, radius, color, duration=0.3):
        self.x, self.y = x, y
        self.radius = radius
        self.color = color
        self.timer = duration
        self.duration = duration

    def update(self, dt):
        self.timer -= dt

    def draw(self, surface, cx, cy):
        sx = int(self.x - cx + WIDTH//2)
        sy = int(self.y - cy + HEIGHT//2)
        alpha = self.timer / self.duration
        r = int(self.radius * (2.0 - alpha))
        s = pygame.Surface((r*2, r*2), pygame.SRCALPHA)
        pygame.draw.circle(s, (*self.color, int(80*alpha)), (r, r), r)
        surface.blit(s, (sx - r, sy - r))


# === GAME STATE ===
hero = Hero()
monsters = []
floating_texts = []
effects = []
wave = 0
spawn_timer = 0
game_time = 0

def spawn_wave():
    global wave, monsters
    wave += 1
    count = 3 + wave
    for i in range(count):
        angle = random.uniform(0, 2 * math.pi)
        dist = random.uniform(300, 500)
        mx = hero.x + math.cos(angle) * dist
        my = hero.y + math.sin(angle) * dist
        if wave % 4 == 0 and i == 0:
            # Elite every 4 waves
            m = Entity(f"Elite_{wave}", mx, my, hp=400, armor=0.28, speed=120,
                       atk_dmg=40, atk_range=45, atk_cd=1.2, radius=20, color=ELITE_COLOR)
            m.xp_value = 5
        else:
            hp = 60 + wave * 10
            m = Entity(f"Skeleton_{wave}_{i}", mx, my, hp=hp, armor=0.12,
                       speed=130 + wave*5, atk_dmg=15 + wave*2, atk_range=40,
                       atk_cd=1.5, radius=11, color=MONSTER_COLOR)
            m.xp_value = 1
        monsters.append(m)

spawn_wave()

# === MAIN LOOP ===
running = True
while running:
    dt = clock.tick(60) / 1000.0
    game_time += dt
    spawn_timer += dt

    # === INPUT ===
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                running = False

    keys = pygame.key.get_pressed()
    mx, my = pygame.mouse.get_pos()
    # World position of mouse
    mouse_wx = mx + hero.x - WIDTH//2
    mouse_wy = my + hero.y - HEIGHT//2

    # Movement (WASD + arrows)
    move_x, move_y = 0, 0
    if keys[pygame.K_a] or keys[pygame.K_LEFT]: move_x -= 1
    if keys[pygame.K_d] or keys[pygame.K_RIGHT]: move_x += 1
    if keys[pygame.K_w] or keys[pygame.K_UP]: move_y -= 1
    if keys[pygame.K_s] or keys[pygame.K_DOWN]: move_y += 1
    if move_x or move_y:
        mag = math.sqrt(move_x**2 + move_y**2)
        hero.x += (move_x/mag) * hero.speed * dt
        hero.y += (move_y/mag) * hero.speed * dt

    # Abilities
    hero.update_cooldowns(dt)
    alive_monsters = [m for m in monsters if m.alive]

    # Q - Cleave (AoE around self)
    if keys[pygame.K_q]:
        ab = hero.abilities["Q"]
        if ab["remaining"] <= 0 and alive_monsters:
            ab["remaining"] = ab["cd"]
            effects.append(AoeEffect(hero.x, hero.y, ab["radius"], (100, 200, 255)))
            for m in alive_monsters:
                if hero.dist(m) <= ab["radius"]:
                    dmg = m.take_damage(ab["damage"])
                    floating_texts.append(FloatingText(m.x, m.y - 20, f"-{dmg:.0f}", DAMAGE_COLOR))

    # W - Sweeping Attack (big AoE around self)
    if keys[pygame.K_w] and not (move_y < 0):  # avoid conflict with W-move
        pass  # W is used for movement, use R instead
    if keys[pygame.K_r]:
        ab = hero.abilities["W"]
        if ab["remaining"] <= 0 and alive_monsters:
            ab["remaining"] = ab["cd"]
            effects.append(AoeEffect(hero.x, hero.y, ab["radius"], (255, 150, 50)))
            for m in alive_monsters:
                if hero.dist(m) <= ab["radius"]:
                    dmg = m.take_damage(ab["damage"])
                    floating_texts.append(FloatingText(m.x, m.y - 20, f"-{dmg:.0f}", GOLD))

    # E - Fireball (AoE at mouse position)
    if keys[pygame.K_e]:
        ab = hero.abilities["E"]
        if ab["remaining"] <= 0 and alive_monsters:
            ab["remaining"] = ab["cd"]
            effects.append(AoeEffect(mouse_wx, mouse_wy, ab["radius"], (255, 80, 0)))
            for m in alive_monsters:
                dx = m.x - mouse_wx
                dy = m.y - mouse_wy
                if math.sqrt(dx*dx + dy*dy) <= ab["radius"]:
                    dmg = m.take_damage(ab["damage"])
                    floating_texts.append(FloatingText(m.x, m.y - 20, f"-{dmg:.0f}", (255, 150, 0)))

    # SPACE - basic attack closest
    if keys[pygame.K_SPACE] and hero.cd_remaining <= 0 and alive_monsters:
        closest = min(alive_monsters, key=lambda m: hero.dist(m))
        if hero.dist(closest) <= hero.atk_range:
            hero.cd_remaining = hero.atk_cd
            dmg = closest.take_damage(hero.atk_dmg)
            floating_texts.append(FloatingText(closest.x, closest.y - 20, f"-{dmg:.0f}", WHITE))

    # === MONSTER AI ===
    for m in alive_monsters:
        m.flash_timer = max(0, m.flash_timer - dt)
        m.move_toward(hero.x, hero.y, dt)
        m.cd_remaining = max(0, m.cd_remaining - dt)
        if m.dist(hero) <= m.atk_range and m.cd_remaining <= 0:
            dmg = hero.take_damage(m.atk_dmg)
            m.cd_remaining = m.atk_cd
            floating_texts.append(FloatingText(hero.x, hero.y - 30, f"-{dmg:.0f}", DAMAGE_COLOR, 0.8))

    # Check kills
    for m in monsters:
        if not m.alive and m.xp_value > 0:
            hero.xp += m.xp_value
            hero.gold += random.randint(10, 30) * m.xp_value
            hero.kills += 1
            floating_texts.append(FloatingText(m.x, m.y, f"+{m.xp_value} XP", GOLD, 1.2))
            m.xp_value = 0  # don't double count

    # Remove dead monsters after 2s
    monsters = [m for m in monsters if m.alive or m.flash_timer > 0]

    # Spawn next wave when all dead
    if not any(m.alive for m in monsters):
        if spawn_timer > 1.5:
            spawn_wave()
            spawn_timer = 0

    # Hero death → reset
    if not hero.alive:
        floating_texts.append(FloatingText(hero.x, hero.y, "DEFEATED! Respawning...", (255, 0, 0), 2.0))
        hero.hp = hero.max_hp
        hero.alive = True
        monsters.clear()
        wave = max(0, wave - 2)
        spawn_wave()

    # Update floating texts & effects
    floating_texts = [ft for ft in floating_texts if ft.timer > 0]
    for ft in floating_texts:
        ft.update(dt)
    effects = [e for e in effects if e.timer > 0]
    for e in effects:
        e.update(dt)

    # === RENDER ===
    screen.fill(BG)

    # Floor grid
    cam_x, cam_y = hero.x, hero.y
    for gx in range(-10, 11):
        for gy in range(-8, 9):
            wx = (gx * 64) + int(cam_x // 64) * 64
            wy = (gy * 64) + int(cam_y // 64) * 64
            sx = int(wx - cam_x + WIDTH//2)
            sy = int(wy - cam_y + HEIGHT//2)
            pygame.draw.rect(screen, FLOOR, (sx, sy, 62, 62))

    # Effects
    for e in effects:
        e.draw(screen, cam_x, cam_y)

    # Monsters
    for m in monsters:
        if m.alive or m.flash_timer > 0:
            m.draw(screen, cam_x, cam_y)

    # Hero
    hero.flash_timer = max(0, hero.flash_timer - dt)
    hero.draw(screen, cam_x, cam_y)

    # Floating texts
    for ft in floating_texts:
        ft.draw(screen, cam_x, cam_y)

    # === HUD ===
    # HP bar
    hp_pct = hero.hp / hero.max_hp
    pygame.draw.rect(screen, (40, 40, 40), (20, 20, 204, 24))
    pygame.draw.rect(screen, HP_RED, (22, 22, 200, 20))
    pygame.draw.rect(screen, HP_GREEN, (22, 22, int(200 * hp_pct), 20))
    hp_txt = font.render(f"HP: {hero.hp:.0f}/{hero.max_hp}", True, WHITE)
    screen.blit(hp_txt, (25, 24))

    # Abilities
    ab_y = 60
    for key, ab in [("Q", hero.abilities["Q"]), ("R", hero.abilities["W"]), ("E", hero.abilities["E"])]:
        ready = ab["remaining"] <= 0
        color = ABILITY_READY if ready else COOLDOWN_GRAY
        pygame.draw.rect(screen, color, (20, ab_y, 180, 22))
        cd_text = "READY" if ready else f"{ab['remaining']:.1f}s"
        txt = font.render(f"[{key}] {ab['name']} — {cd_text}", True, WHITE)
        screen.blit(txt, (25, ab_y + 3))
        ab_y += 28
    # Basic attack
    ready = hero.cd_remaining <= 0
    color = ABILITY_READY if ready else COOLDOWN_GRAY
    pygame.draw.rect(screen, color, (20, ab_y, 180, 22))
    txt = font.render(f"[SPACE] Attack — {'READY' if ready else f'{hero.cd_remaining:.1f}s'}", True, WHITE)
    screen.blit(txt, (25, ab_y + 3))

    # Stats
    stats_txt = font.render(f"Wave: {wave}  Kills: {hero.kills}  Gold: {hero.gold}  XP: {hero.xp}", True, GOLD)
    screen.blit(stats_txt, (WIDTH - stats_txt.get_width() - 20, 20))

    # Controls reminder
    ctrl = font.render("WASD=Move  Q=Cleave  R=Sweep  E=Fireball(mouse)  SPACE=Attack  ESC=Quit", True, (150, 150, 150))
    screen.blit(ctrl, (WIDTH//2 - ctrl.get_width()//2, HEIGHT - 30))

    pygame.display.flip()

pygame.quit()
