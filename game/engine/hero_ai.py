"""
Hero AI — automated player behavior for testing and AI companions.

Each hero class gets a behavior that:
- Picks targets intelligently (path distance, not Euclidean)
- Uses abilities optimally (cooldown management)
- Positions properly (melee stays close, ranged keeps distance)
- Uses potions when low HP
- Respects line of sight (moves to get LOS before casting)

This enables:
1. Automated playtesting (watch AI clear dungeons to tune difficulty)
2. AI companions in multiplayer (invite AI heroes to help)
"""
import math
import time
from game.engine.entities import Hero, Monster, Condition
from game.engine.pathfinding import astar, has_line_of_sight


class HeroAI:
    """Base class for hero AI behaviors."""

    def __init__(self, hero: Hero):
        self.hero = hero
        self.target: Monster = None
        self.dash_request = None  # (target_x, target_y, target_monster, damage, stun_dur)
        self._nav_dungeon = None  # Set externally after creation
        self._path_cache = {}     # monster_id -> (path_len, timestamp)
        self._path_cache_ttl = 0.5  # Recalculate path distances every 0.5s

    def set_nav_dungeon(self, dungeon):
        """Set the navigation dungeon reference for pathfinding and LOS."""
        self._nav_dungeon = dungeon

    def get_engaged_monsters(self, monsters: list[Monster]) -> list[Monster]:
        """Return only monsters that are currently aggroed (engaged in combat).
        AI should only target these and avoid pulling new monsters until the
        current engagement is cleared."""
        from game.engine.ai import AggroState
        engaged = [m for m in monsters if m.alive and
                   hasattr(m, 'aggro_state') and m.aggro_state == AggroState.AGGROED]
        if engaged:
            return engaged
        # Nothing engaged — allow targeting any alive monster (start new pull)
        return [m for m in monsters if m.alive]

    def has_los(self, target) -> bool:
        """Check if hero has line of sight to target."""
        if not self._nav_dungeon:
            return True  # No dungeon reference, assume clear
        return has_line_of_sight(self._nav_dungeon, self.hero.x, self.hero.y, target.x, target.y)

    def path_distance(self, target) -> float:
        """Get path distance to target (cached, refreshed every 0.5s).
        Returns euclidean distance if no dungeon, or path length in pixels.
        Falls back to large value if no path found."""
        if not self._nav_dungeon:
            return self.hero.distance_to(target)

        mid = id(target)
        now = time.monotonic()
        cached = self._path_cache.get(mid)
        if cached and (now - cached[1]) < self._path_cache_ttl:
            return cached[0]

        # If LOS exists, use euclidean (cheaper, and we know path is clear)
        if has_line_of_sight(self._nav_dungeon, self.hero.x, self.hero.y, target.x, target.y):
            dist = self.hero.distance_to(target)
            self._path_cache[mid] = (dist, now)
            return dist

        # No LOS — compute A* path length
        path = astar(self._nav_dungeon, self.hero.x, self.hero.y, target.x, target.y, max_steps=80)
        if path:
            # Sum path segment lengths
            dist = 0.0
            px, py = self.hero.x, self.hero.y
            for wx, wy in path:
                dist += math.sqrt((wx - px)**2 + (wy - py)**2)
                px, py = wx, wy
            self._path_cache[mid] = (dist, now)
            return dist
        else:
            # No path found — very far / unreachable
            self._path_cache[mid] = (99999.0, now)
            return 99999.0

    def pick_target(self, monsters: list[Monster]) -> Monster:
        """Pick best target by path distance, preferring engaged monsters."""
        candidates = self.get_engaged_monsters(monsters)
        if not candidates:
            return None
        return min(candidates, key=lambda m: self.path_distance(m))

    def should_use_potion(self, potions: int) -> bool:
        """Use potion when below 40% HP."""
        return potions > 0 and self.hero.hp < self.hero.max_hp * 0.4

    def count_enemies_in_range(self, monsters, radius):
        """Count enemies within euclidean radius (still useful for AoE decisions)."""
        return sum(1 for m in monsters if m.alive and self.hero.distance_to(m) <= radius)

    def update(self, monsters: list[Monster], dt: float, collision_fn=None) -> dict:
        """
        Run one AI tick. Returns an action dict:
        {
            "move_to": (x, y) or None,
            "use_ability": ability_key or None,
            "ability_target_pos": (x, y) or None,
            "ability_target_monster": Monster or None,
            "use_potion": bool,
            "dash": (target_x, target_y, monster, damage, stun) or None,
        }
        """
        return {"move_to": None, "use_ability": None, "ability_target_pos": None,
                "ability_target_monster": None, "use_potion": False, "dash": None}


class FighterAI(HeroAI):
    """
    Fighter AI strategy:
    - Charge into ranged enemies or distant packs
    - Use Whirlwind when surrounded (3+ enemies in melee)
    - Use Reaping Strike as bread-and-butter
    - Stay in melee range of target
    - Pop potion below 40% HP
    """

    def pick_target(self, monsters):
        candidates = self.get_engaged_monsters(monsters)
        if not candidates:
            return None

        # Prioritize: low HP enemies in melee range (secure kills)
        in_melee = [m for m in candidates if self.hero.distance_to(m) < 80 and self.has_los(m)]
        if in_melee:
            return min(in_melee, key=lambda m: m.hp)

        # Otherwise closest by path distance
        return min(candidates, key=lambda m: self.path_distance(m))

    def update(self, monsters: list[Monster], dt: float, collision_fn=None) -> dict:
        action = {"move_to": None, "use_ability": None, "ability_target_pos": None,
                  "ability_target_monster": None, "use_potion": False, "dash": None}

        alive = [m for m in monsters if m.alive]
        if not alive:
            return action

        # GCD check
        if self.hero.gcd > 0:
            self.target = self.pick_target(alive)
            if self.target:
                dist = self.hero.distance_to(self.target)
                if dist > 60:
                    action["move_to"] = (self.target.x, self.target.y)
                else:
                    action["basic_attack"] = self.target
            return action

        # Pick target
        self.target = self.pick_target(alive)
        if not self.target:
            return action

        dist = self.hero.distance_to(self.target)
        enemies_in_melee = self.count_enemies_in_range(alive, 80)

        # Decision priority:

        # 1. Potion if low HP
        if self.should_use_potion(3):  # AI always "has" potions conceptually
            action["use_potion"] = True

        # 2. Demoralizing Shout (E) if 2+ enemies in melee range
        ab_e = self.hero.abilities.get("E")
        if ab_e and ab_e.is_ready() and enemies_in_melee >= 2:
            action["use_ability"] = "E"
            action["ability_target_pos"] = (self.hero.x, self.hero.y)
            return action

        # 3. Charge (R) if CD ready and LOS — use as gap closer or damage nuke
        ab_r = self.hero.abilities.get("R")
        if ab_r and ab_r.is_ready() and self.target and self.has_los(self.target):
            action["use_ability"] = "R"
            action["ability_target_monster"] = self.target
            # Request dash
            dx = self.target.x - self.hero.x
            dy = self.target.y - self.hero.y
            d = math.sqrt(dx*dx + dy*dy)
            if d > 0:
                action["dash"] = (
                    self.target.x - (dx/d) * 50,
                    self.target.y - (dy/d) * 50,
                    self.target,
                    ab_r.calc_damage(self.hero.base_damage),
                    ab_r.stun_duration
                )
            return action

        # 4. Reaping Strike (Q) if in melee range and 2+ enemies nearby and LOS
        ab_q = self.hero.abilities.get("Q")
        if ab_q and ab_q.is_ready() and dist <= ab_q.range and enemies_in_melee >= 2 and self.has_los(self.target):
            action["use_ability"] = "Q"
            action["ability_target_pos"] = (self.hero.x, self.hero.y)
            return action

        # 5. Reaping Strike on single target in range and LOS
        if ab_q and ab_q.is_ready() and dist <= ab_q.range and self.has_los(self.target):
            action["use_ability"] = "Q"
            action["ability_target_pos"] = (self.hero.x, self.hero.y)
            return action

        # 6. Move toward target (to get in range or get LOS)
        action["move_to"] = (self.target.x, self.target.y)

        return action


class ClericAI(HeroAI):
    """
    Quinn (Cleric) AI — Ranged wand attacker with ally support:
    - Wall and Renew target lowest HP ally (including self)
    - Stay at range (~150-200px) and cast Wanding as auto-attack
    - Kite away from melee enemies if they get too close
    - Pop potion below 30% HP
    """

    def __init__(self, hero):
        super().__init__(hero)
        self.allies = []  # Set externally to list of all hero entities

    def _find_lowest_hp_ally(self):
        """Find the ally (including self) with lowest HP percentage."""
        candidates = [h for h in self.allies if h.alive] if self.allies else [self.hero]
        if not candidates:
            return self.hero
        return min(candidates, key=lambda h: h.hp / h.max_hp)

    def pick_target(self, monsters):
        candidates = self.get_engaged_monsters(monsters)
        if not candidates:
            return None
        # Prioritize low HP targets to secure kills
        low_hp = [m for m in candidates if m.hp <= m.max_hp * 0.3]
        if low_hp:
            return min(low_hp, key=lambda m: self.path_distance(m))
        return min(candidates, key=lambda m: self.path_distance(m))

    def update(self, monsters: list[Monster], dt: float, collision_fn=None) -> dict:
        action = {"move_to": None, "use_ability": None, "ability_target_pos": None,
                  "ability_target_monster": None, "use_potion": False, "dash": None}

        alive = [m for m in monsters if m.alive]
        if not alive:
            return action

        # GCD check
        if self.hero.gcd > 0:
            self.target = self.pick_target(alive)
            # Kite if enemy too close
            if self.target:
                dist = self.hero.distance_to(self.target)
                if dist < 80:
                    # Move away from target
                    dx = self.hero.x - self.target.x
                    dy = self.hero.y - self.target.y
                    d = math.sqrt(dx * dx + dy * dy)
                    if d > 0:
                        action["move_to"] = (self.hero.x + (dx / d) * 100, self.hero.y + (dy / d) * 100)
            return action

        self.target = self.pick_target(alive)
        if not self.target:
            return action

        dist = self.hero.distance_to(self.target)
        hp_pct = self.hero.hp / self.hero.max_hp

        # 1. Potion if critically low
        if hp_pct < 0.30:
            action["use_potion"] = True

        # 2. Wall on lowest HP ally (or self) if no shield on them
        ab_r = self.hero.abilities.get("R")
        if ab_r and ab_r.is_ready():
            # Find lowest HP ally (including self) that doesn't have a shield
            wall_target = self._find_lowest_hp_ally()
            if wall_target and wall_target.absorb_shield <= 0 and wall_target.hp < wall_target.max_hp * 0.8:
                action["use_ability"] = "R"
                action["ability_target_ally"] = wall_target
                return action

        # 3. Renew on lowest HP ally if below 70% and not already ticking
        ab_e = self.hero.abilities.get("E")
        if ab_e and ab_e.is_ready():
            renew_target = self._find_lowest_hp_ally()
            if renew_target and renew_target.hp < renew_target.max_hp * 0.70 and "Renew" not in renew_target.buffs:
                action["use_ability"] = "E"
                action["ability_target_ally"] = renew_target
                return action

        # 4. Wanding (ranged auto-attack) if in range and LOS
        ab_q = self.hero.abilities.get("Q")
        if ab_q and ab_q.is_ready() and dist <= 200 and self.has_los(self.target):
            action["use_ability"] = "Q"
            action["ability_target_monster"] = self.target
            return action

        # 5. Kite if too close
        if dist < 80:
            dx = self.hero.x - self.target.x
            dy = self.hero.y - self.target.y
            d = math.sqrt(dx * dx + dy * dy)
            if d > 0:
                action["move_to"] = (self.hero.x + (dx / d) * 100, self.hero.y + (dy / d) * 100)
            return action

        # 6. Move toward target (to get in range or get LOS)
        action["move_to"] = (self.target.x, self.target.y)

        return action


class PaladinAI(HeroAI):
    """
    Keyleth (Paladin) AI — Seal/Smite/Judgement rotation:
    - Keep Righteous Seal up (buff uptime)
    - Smite as bread-and-butter (boosted by Seal)
    - Judgement on distant targets or to consume Seal before expiry
    - Holy Light when below 50% HP
    """

    def pick_target(self, monsters):
        candidates = self.get_engaged_monsters(monsters)
        if not candidates:
            return None
        in_melee = [m for m in candidates if self.hero.distance_to(m) < 70 and self.has_los(m)]
        if in_melee:
            return min(in_melee, key=lambda m: m.hp)
        return min(candidates, key=lambda m: self.path_distance(m))

    def update(self, monsters: list[Monster], dt: float, collision_fn=None) -> dict:
        action = {"move_to": None, "use_ability": None, "ability_target_pos": None,
                  "ability_target_monster": None, "use_potion": False, "dash": None}

        alive = [m for m in monsters if m.alive]
        if not alive:
            return action

        # GCD check — don't try abilities if on GCD
        if self.hero.gcd > 0:
            self.target = self.pick_target(alive)
            if self.target and self.hero.distance_to(self.target) > 50:
                action["move_to"] = (self.target.x, self.target.y)
            return action

        self.target = self.pick_target(alive)
        if not self.target:
            return action

        dist = self.hero.distance_to(self.target)
        hp_pct = self.hero.hp / self.hero.max_hp

        # 1. Holy Light if below 50% HP
        ab_f = self.hero.abilities.get("F")
        if ab_f and ab_f.is_ready() and hp_pct < 0.50:
            action["use_ability"] = "F"
            return action

        # 2. Potion if below 30%
        if hp_pct < 0.30:
            action["use_potion"] = True

        # 3. Righteous Seal if not active
        ab_r = self.hero.abilities.get("R")
        has_seal = "Righteous Seal" in self.hero.buffs
        if ab_r and ab_r.is_ready() and not has_seal:
            action["use_ability"] = "R"
            return action

        # 4. Judgement if target is far or Seal about to expire (ranged — needs LOS)
        ab_e = self.hero.abilities.get("E")
        seal_expiring = has_seal and self.hero.buffs["Righteous Seal"]["remaining"] < 2.0
        if ab_e and ab_e.is_ready() and dist <= 250 and self.has_los(self.target):
            if dist > 120 or seal_expiring:
                action["use_ability"] = "E"
                action["ability_target_monster"] = self.target
                return action

        # 5. Smite if in melee range and LOS
        ab_q = self.hero.abilities.get("Q")
        if ab_q and ab_q.is_ready() and dist <= 70 and self.has_los(self.target):
            action["use_ability"] = "Q"
            action["ability_target_monster"] = self.target
            return action

        # 6. Move toward target (to get in range or get LOS)
        action["move_to"] = (self.target.x, self.target.y)

        return action


# Registry
class WizardAI(HeroAI):
    """
    Heskan (Wizard) AI — Channeled turret with burst and CC:
    - Stay at max range (~250px) and channel Frostbolt as primary
    - Fire Blast for instant damage when available
    - Frost Nova when 2+ enemies get close (emergency CC)
    - Kite away from enemies that are too close
    - Pop potion below 30% HP
    """

    def pick_target(self, monsters):
        candidates = self.get_engaged_monsters(monsters)
        if not candidates:
            return None
        low_hp = [m for m in candidates if m.hp <= m.max_hp * 0.3]
        if low_hp:
            return min(low_hp, key=lambda m: self.path_distance(m))
        return min(candidates, key=lambda m: self.path_distance(m))

    def _find_best_kite_position(self, monsters) -> tuple:
        """Evaluate 8 directions to find the safest retreat position.
        Returns (x, y) of best kite target, or None if no valid option.

        Algorithm:
        1. Generate 8 candidate positions (step_distance in each direction)
        2. Filter: must be walkable and have LOS from current position
        3. Score: sum of distances from candidate to all mobs within 500px
        4. Return highest-scoring (safest) position
        """
        step = 120  # How far to step in each direction
        hx, hy = self.hero.x, self.hero.y

        # 8 directions: N, NE, E, SE, S, SW, W, NW
        directions = [
            (0, -1), (0.707, -0.707), (1, 0), (0.707, 0.707),
            (0, 1), (-0.707, 0.707), (-1, 0), (-0.707, -0.707)
        ]

        # Mobs within threat radius
        threats = [m for m in monsters if m.alive and self.hero.distance_to(m) < 500]
        if not threats:
            return None

        best_pos = None
        best_score = -1

        for dx, dy in directions:
            cx = hx + dx * step
            cy = hy + dy * step

            # Filter: must be walkable
            if not self._nav_dungeon:
                continue
            if self._nav_dungeon.is_wall(cx, cy):
                continue

            # Filter: must have LOS from current position
            if not has_line_of_sight(self._nav_dungeon, hx, hy, cx, cy):
                continue

            # Score: minimum distance to any threat (higher = safer)
            # The closest mob is what kills you — maximize distance from nearest threat
            score = min(math.sqrt((cx - m.x)**2 + (cy - m.y)**2) for m in threats)

            if score > best_score:
                best_score = score
                best_pos = (cx, cy)

        return best_pos


    def update(self, monsters: list[Monster], dt: float, collision_fn=None) -> dict:
        action = {"move_to": None, "use_ability": None, "ability_target_pos": None,
                  "ability_target_monster": None, "use_potion": False, "dash": None}

        alive = [m for m in monsters if m.alive]
        if not alive:
            return action

        if self.hero.gcd > 0:
            # During GCD, smart kite or close gap
            self.target = self.pick_target(alive)
            if self.target:
                dist = self.hero.distance_to(self.target)
                if dist < 220:
                    kite_pos = self._find_best_kite_position(alive)
                    if kite_pos:
                        action["move_to"] = kite_pos
                elif dist > 260:
                    action["move_to"] = (self.target.x, self.target.y)
            return action

        # Don't act if channeling (immobilized)
        if self.hero.has_condition(Condition.IMMOBILIZED):
            return action

        # Kite-back: after Frost Nova, retreat for 0.5s
        if not hasattr(self, '_kite_timer'):
            self._kite_timer = 0.0
        if self._kite_timer > 0:
            self._kite_timer -= dt
            kite_pos = self._find_best_kite_position(alive)
            if kite_pos:
                action["move_to"] = kite_pos
            return action

        self.target = self.pick_target(alive)
        if not self.target:
            return action

        dist = self.hero.distance_to(self.target)
        hp_pct = self.hero.hp / self.hero.max_hp
        enemies_close = self.count_enemies_in_range(alive, 120)

        # 1. Potion if critically low
        if hp_pct < 0.30:
            action["use_potion"] = True

        # 2. Frost Nova if 2+ enemies within 120px
        ab_e = self.hero.abilities.get("E")
        if ab_e and ab_e.is_ready() and enemies_close >= 2:
            print(f"[WIZARD_AI] {self.hero.name} FROST NOVA! enemies_close={enemies_close} hp_pct={hp_pct:.0%}", flush=True)
            action["use_ability"] = "E"
            action["ability_target_pos"] = (self.hero.x, self.hero.y)
            if self.count_enemies_in_range(alive, 120) > 0:
                self._kite_timer = 0.5
            return action

        # 3. Frost Nova if 1 enemy close and low HP
        if ab_e and ab_e.is_ready() and enemies_close >= 1 and hp_pct < 0.50:
            print(f"[WIZARD_AI] {self.hero.name} FROST NOVA (low HP)! enemies_close={enemies_close} hp_pct={hp_pct:.0%}", flush=True)
            action["use_ability"] = "E"
            action["ability_target_pos"] = (self.hero.x, self.hero.y)
            if self.count_enemies_in_range(alive, 120) > 0:
                self._kite_timer = 0.5
            return action

        # 4. Fire Blast instant nuke when available (instant — safe at any range)
        ab_r = self.hero.abilities.get("R")
        if ab_r and ab_r.is_ready() and dist <= 260 and self.has_los(self.target):
            action["use_ability"] = "R"
            action["ability_target_monster"] = self.target
            return action

        # 5. Frostbolt if in range and LOS — but kite first if enemy is dangerously close
        ab_q = self.hero.abilities.get("Q")
        if ab_q and ab_q.is_ready() and dist <= 260 and self.has_los(self.target):
            # If enemy very close, try to kite first (one cycle) then cast
            if dist < 130:
                kite_pos = self._find_best_kite_position(alive)
                if kite_pos:
                    action["move_to"] = kite_pos
                    return action
            # Safe enough distance or no kite option — cast
            action["use_ability"] = "Q"
            action["ability_target_monster"] = self.target
            return action

        # 6. Kite if enemy too close AND abilities on CD (don't stand still waiting)
        if dist < 220 and not (ab_q and ab_q.is_ready()):
            kite_pos = self._find_best_kite_position(alive)
            if kite_pos:
                action["move_to"] = kite_pos
            return action

        # 7. Move toward target (to get in range or get LOS)
        action["move_to"] = (self.target.x, self.target.y)

        return action


class RogueAI(HeroAI):
    """
    Tarak (Rogue) AI — Stealth assassin:
    - Stealth when no enemies aggroed on hero
    - Ambush opener from stealth (massive burst)
    - Stab as bread-and-butter melee
    - Stay in melee range of target
    - Pop potion below 35% HP
    """

    def __init__(self, hero):
        super().__init__(hero)
        self._ambush_target: Monster = None  # Locked target during stealth approach

    def pick_target(self, monsters):
        candidates = self.get_engaged_monsters(monsters)
        if not candidates:
            return None
        # Prioritize low HP targets to secure kills
        low_hp = [m for m in candidates if m.hp <= m.max_hp * 0.3]
        if low_hp:
            return min(low_hp, key=lambda m: self.path_distance(m))
        return min(candidates, key=lambda m: self.path_distance(m))

    def is_in_combat(self, monsters):
        """Check if any monster is targeting the hero."""
        for m in monsters:
            if m.alive and hasattr(m, 'aggro_target') and m.aggro_target == self.hero:
                return True
        return False

    def update(self, monsters: list[Monster], dt: float, collision_fn=None) -> dict:
        action = {"move_to": None, "use_ability": None, "ability_target_pos": None,
                  "ability_target_monster": None, "use_potion": False, "dash": None}

        alive = [m for m in monsters if m.alive]
        if not alive:
            self._ambush_target = None
            return action

        if self.hero.gcd > 0:
            self.target = self._ambush_target if self._ambush_target and self._ambush_target.alive else self.pick_target(alive)
            if self.target and self.hero.distance_to(self.target) > 50:
                action["move_to"] = (self.target.x, self.target.y)
            return action

        # Clear locked ambush target if invalid
        if self._ambush_target and (not self._ambush_target.alive or not self.hero.stealthed):
            self._ambush_target = None

        # While stealthed with ambush ready, use locked target
        ab_e = self.hero.abilities.get("E")
        if self.hero.stealthed and ab_e and ab_e.is_ready():
            # Lock target if not already locked
            if not self._ambush_target:
                self._ambush_target = self.pick_target(alive)
            self.target = self._ambush_target
        else:
            self._ambush_target = None
            self.target = self.pick_target(alive)

        if not self.target:
            return action

        dist = self.hero.distance_to(self.target)
        hp_pct = self.hero.hp / self.hero.max_hp

        # 1. Potion if low
        if hp_pct < 0.35:
            action["use_potion"] = True

        # 2. Stealth if not already stealthed and CD ready
        ab_r = self.hero.abilities.get("R")
        if ab_r and ab_r.is_ready() and not self.hero.stealthed:
            action["use_ability"] = "R"
            return action

        # 3. Ambush from stealth when in range and LOS
        if ab_e and ab_e.is_ready() and self.hero.stealthed and dist <= 55 and self.has_los(self.target):
            action["use_ability"] = "E"
            action["ability_target_monster"] = self.target
            self._ambush_target = None  # Ambush fired, unlock
            return action

        # 3b. Stealthed with Ambush ready but out of range or no LOS — walk to locked target
        if ab_e and ab_e.is_ready() and self.hero.stealthed and (dist > 55 or not self.has_los(self.target)):
            action["move_to"] = (self.target.x, self.target.y)
            return action

        # 4. Walk to target if out of range
        if dist > 50:
            action["move_to"] = (self.target.x, self.target.y)
            return action

        # 5. Stab in melee — but only if Stealth is on long cooldown
        #    If Stealth is almost ready (<0.5s), wait for it to cycle into Ambush
        ab_q = self.hero.abilities.get("Q")
        if ab_q and ab_q.is_ready() and not self.hero.stealthed and dist <= 55 and self.has_los(self.target):
            if not ab_r or ab_r.remaining > 0.5:
                # Stealth on CD — Stab while waiting
                action["use_ability"] = "Q"
                action["ability_target_monster"] = self.target
                return action
            # else: Stealth almost ready — don't Stab, let it cycle to Stealth→Ambush

        # 6. Basic attack fallback
        if not self.hero.stealthed:
            action["basic_attack"] = self.target

        return action


HERO_AI_CLASSES = {
    "Fighter": FighterAI,
    "Cleric": ClericAI,   # Quinn — ranged wand + sustain
    "Paladin": PaladinAI, # Keyleth — Seal/Smite/Judgement melee
    "Rogue": RogueAI,     # Tarak — stealth assassin
    "Wizard": WizardAI,   # Heskan — channeled frostbolt + burst
}


def create_hero_ai(hero: Hero) -> HeroAI:
    """Create the appropriate AI for a hero based on class."""
    ai_class = HERO_AI_CLASSES.get(hero.class_name, HeroAI)
    return ai_class(hero)
