"""
ARPG Combat Demo - Headless Prototype
Proves: movement, cooldowns, combat, monster AI, all verifiable via CLI output.
Run: python3 demo.py
"""
import math
import random

# === GAME TICK ===
TICK_RATE = 10  # 10 ticks per second (100ms per tick)
TICK_DURATION = 1.0 / TICK_RATE

# === ENTITIES ===
class Entity:
    def __init__(self, name, x, y, hp, armor_pct, speed, attack_damage, attack_range, attack_cooldown):
        self.name = name
        self.x = x
        self.y = y
        self.max_hp = hp
        self.hp = hp
        self.armor_pct = armor_pct  # damage reduction 0.0-1.0
        self.speed = speed  # meters per second
        self.attack_damage = attack_damage
        self.attack_range = attack_range  # meters
        self.attack_cooldown = attack_cooldown  # seconds
        self.cooldown_remaining = 0.0
        self.target = None
        self.alive = True

    def distance_to(self, other):
        return math.sqrt((self.x - other.x)**2 + (self.y - other.y)**2)

    def move_toward(self, target, dt):
        dx = target.x - self.x
        dy = target.y - self.y
        dist = math.sqrt(dx*dx + dy*dy)
        if dist < 0.1:
            return
        move_dist = self.speed * dt
        if move_dist > dist:
            move_dist = dist
        self.x += (dx / dist) * move_dist
        self.y += (dy / dist) * move_dist

    def take_damage(self, raw_damage):
        reduced = raw_damage * (1.0 - self.armor_pct)
        self.hp -= reduced
        if self.hp <= 0:
            self.hp = 0
            self.alive = False
        return reduced

    def try_attack(self, target, dt):
        self.cooldown_remaining -= dt
        if self.cooldown_remaining <= 0 and self.distance_to(target) <= self.attack_range:
            actual = target.take_damage(self.attack_damage)
            self.cooldown_remaining = self.attack_cooldown
            return actual
        return None

    def status(self):
        return f"{self.name}: HP={self.hp:.0f}/{self.max_hp} pos=({self.x:.1f},{self.y:.1f})"


# === HERO WITH ABILITIES ===
class Hero(Entity):
    def __init__(self, name, x, y, hp, armor_pct, speed, attack_damage, attack_range, attack_cooldown):
        super().__init__(name, x, y, hp, armor_pct, speed, attack_damage, attack_range, attack_cooldown)
        self.abilities = {}

    def add_ability(self, name, cooldown, damage, aoe_radius, ability_range):
        self.abilities[name] = {
            "cooldown": cooldown, "remaining": 0.0,
            "damage": damage, "aoe_radius": aoe_radius, "range": ability_range
        }

    def use_ability(self, name, targets, dt):
        ab = self.abilities.get(name)
        if not ab:
            return []
        ab["remaining"] -= dt
        if ab["remaining"] > 0:
            return []
        # Find targets in range + AoE
        hits = []
        for t in targets:
            if not t.alive:
                continue
            if self.distance_to(t) <= ab["range"] + ab["aoe_radius"]:
                actual = t.take_damage(ab["damage"])
                hits.append((t.name, actual))
        if hits:
            ab["remaining"] = ab["cooldown"]
        return hits


# === MONSTER AI (Behavior Tree from design doc) ===
def monster_ai(monster, heroes, dt):
    """Simple behavior: move to closest alive hero, attack when in range."""
    if not monster.alive:
        return None
    # Find closest alive hero
    closest = None
    closest_dist = float('inf')
    for h in heroes:
        if h.alive:
            d = monster.distance_to(h)
            if d < closest_dist:
                closest_dist = d
                closest = h
    if not closest:
        return None
    # If in range, attack
    dmg = monster.try_attack(closest, dt)
    if dmg is not None:
        return f"  {monster.name} attacks {closest.name} for {dmg:.0f} damage"
    # Otherwise move toward
    monster.move_toward(closest, dt)
    return None


# === SIMULATION ===
def run_simulation():
    print("=" * 60)
    print("ARPG COMBAT DEMO — Headless Simulation")
    print("=" * 60)

    # Create a Fighter hero
    hero = Hero("Fighter", x=0, y=0, hp=500, armor_pct=0.38, speed=3.5,
                attack_damage=45, attack_range=1.5, attack_cooldown=1.0)
    hero.add_ability("Cleave", cooldown=2.0, damage=50, aoe_radius=2.0, ability_range=1.5)
    hero.add_ability("Sweeping Attack", cooldown=9.0, damage=100, aoe_radius=4.0, ability_range=1.5)

    # Create monsters (3 skeletons approaching from different angles)
    monsters = [
        Entity("Skeleton_A", x=8, y=0, hp=80, armor_pct=0.15, speed=3.0, attack_damage=20, attack_range=1.5, attack_cooldown=1.5),
        Entity("Skeleton_B", x=6, y=4, hp=80, armor_pct=0.15, speed=3.0, attack_damage=20, attack_range=1.5, attack_cooldown=1.5),
        Entity("Skeleton_C", x=7, y=-3, hp=80, armor_pct=0.15, speed=3.0, attack_damage=20, attack_range=1.5, attack_cooldown=1.5),
    ]

    print(f"\nINITIAL STATE:")
    print(f"  {hero.status()}")
    for m in monsters:
        print(f"  {m.status()}")
    print(f"\nHero abilities: Cleave (2s CD, 50 dmg, 2m AoE), Sweeping Attack (9s CD, 100 dmg, 4m AoE)")
    print(f"\nSIMULATION START (tick rate={TICK_RATE}/s)")
    print("-" * 60)

    tick = 0
    max_ticks = 150  # 15 seconds max

    while tick < max_ticks:
        t = tick * TICK_DURATION
        alive_monsters = [m for m in monsters if m.alive]

        if not alive_monsters:
            print(f"\n[t={t:.1f}s] ALL MONSTERS DEFEATED!")
            break
        if not hero.alive:
            print(f"\n[t={t:.1f}s] HERO DIED!")
            break

        # Hero AI: move toward closest monster, use abilities when available
        closest_monster = min(alive_monsters, key=lambda m: hero.distance_to(m))
        hero.move_toward(closest_monster, TICK_DURATION)

        # Try Sweeping Attack first (big CD, big damage)
        hits = hero.use_ability("Sweeping Attack", alive_monsters, TICK_DURATION)
        if hits:
            print(f"[t={t:.1f}s] ⚔ {hero.name} uses SWEEPING ATTACK!")
            for name, dmg in hits:
                print(f"         → {name} takes {dmg:.0f} damage")

        # Try Cleave
        if not hits:
            hits = hero.use_ability("Cleave", alive_monsters, TICK_DURATION)
            if hits:
                print(f"[t={t:.1f}s] ⚔ {hero.name} uses CLEAVE!")
                for name, dmg in hits:
                    print(f"         → {name} takes {dmg:.0f} damage")

        # Try basic attack
        if not hits:
            dmg = hero.try_attack(closest_monster, TICK_DURATION)
            if dmg is not None:
                print(f"[t={t:.1f}s] {hero.name} basic attacks {closest_monster.name} for {dmg:.0f}")

        # Monster AI
        for m in alive_monsters:
            msg = monster_ai(m, [hero], TICK_DURATION)
            if msg:
                print(f"[t={t:.1f}s]{msg}")

        # Check for deaths this tick
        for m in monsters:
            if not m.alive and m.hp == 0:
                print(f"[t={t:.1f}s] 💀 {m.name} DEFEATED!")
                m.hp = -1  # mark as reported

        tick += 1

    # Final state
    print("-" * 60)
    print(f"\nFINAL STATE (t={tick * TICK_DURATION:.1f}s):")
    print(f"  {hero.status()}")
    for m in monsters:
        state = "DEAD" if not m.alive else f"HP={m.hp:.0f}"
        print(f"  {m.name}: {state} pos=({m.x:.1f},{m.y:.1f})")

    print(f"\n{'='*60}")
    print("VERIFICATION: This entire simulation ran headlessly.")
    print("All state is inspectable. No GUI needed.")
    print(f"{'='*60}")


if __name__ == "__main__":
    random.seed(42)
    run_simulation()
