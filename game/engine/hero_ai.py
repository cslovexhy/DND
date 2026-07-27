"""
Hero AI — automated player behavior for testing and AI companions.

Each hero class gets a behavior that:
- Picks targets intelligently
- Uses abilities optimally (cooldown management)
- Positions properly (melee stays close, ranged keeps distance)
- Uses potions when low HP

This enables:
1. Automated playtesting (watch AI clear dungeons to tune difficulty)
2. AI companions in multiplayer (invite AI heroes to help)
"""
import math
from game.engine.entities import Hero, Monster, Condition


class HeroAI:
    """Base class for hero AI behaviors."""

    def __init__(self, hero: Hero):
        self.hero = hero
        self.target: Monster = None
        self.dash_request = None  # (target_x, target_y, target_monster, damage, stun_dur)

    def pick_target(self, monsters: list[Monster]) -> Monster:
        """Pick best target. Override per class."""
        alive = [m for m in monsters if m.alive]
        if not alive:
            return None
        # Default: closest enemy
        return min(alive, key=lambda m: self.hero.distance_to(m))

    def should_use_potion(self, potions: int) -> bool:
        """Use potion when below 40% HP."""
        return potions > 0 and self.hero.hp < self.hero.max_hp * 0.4

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
        alive = [m for m in monsters if m.alive]
        if not alive:
            return None

        # Prioritize: low HP enemies first (secure kills), then closest
        in_melee = [m for m in alive if self.hero.distance_to(m) < 80]
        if in_melee:
            # Kill the lowest HP one in melee range
            return min(in_melee, key=lambda m: m.hp)

        # Otherwise closest
        return min(alive, key=lambda m: self.hero.distance_to(m))

    def count_enemies_in_range(self, monsters, radius):
        return sum(1 for m in monsters if m.alive and self.hero.distance_to(m) <= radius)

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

        # 2. Whirlwind (E) if 3+ enemies in melee range
        ab_e = self.hero.abilities.get("E")
        if ab_e and ab_e.is_ready() and enemies_in_melee >= 3:
            action["use_ability"] = "E"
            action["ability_target_pos"] = (self.hero.x, self.hero.y)
            return action

        # 3. Charge (R) if target is far away (>150px) or target is ranged
        ab_r = self.hero.abilities.get("R")
        if ab_r and ab_r.is_ready() and dist > 150:
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

        # 4. Reaping Strike (Q) if in melee range and 2+ enemies nearby
        ab_q = self.hero.abilities.get("Q")
        if ab_q and ab_q.is_ready() and dist <= ab_q.range and enemies_in_melee >= 2:
            action["use_ability"] = "Q"
            action["ability_target_pos"] = (self.hero.x, self.hero.y)
            return action

        # 5. Reaping Strike on single target in range
        if ab_q and ab_q.is_ready() and dist <= ab_q.range:
            action["use_ability"] = "Q"
            action["ability_target_pos"] = (self.hero.x, self.hero.y)
            return action

        # 6. Move toward target if not in melee range
        if dist > 60:
            action["move_to"] = (self.target.x, self.target.y)
        else:
            # 7. In range but abilities on cooldown — basic attack (stay in place)
            action["basic_attack"] = self.target

        return action


class ClericAI(HeroAI):
    """
    Quinn (Cleric) AI — Seal/Smite/Judgement rotation:
    - Keep Righteous Seal up (buff uptime)
    - Smite as bread-and-butter (boosted by Seal)
    - Judgement on distant targets or to consume Seal before expiry
    - Holy Light when below 30% HP
    """

    def pick_target(self, monsters):
        alive = [m for m in monsters if m.alive]
        if not alive:
            return None
        in_melee = [m for m in alive if self.hero.distance_to(m) < 70]
        if in_melee:
            return min(in_melee, key=lambda m: m.hp)
        return min(alive, key=lambda m: self.hero.distance_to(m))

    def update(self, monsters: list[Monster], dt: float, collision_fn=None) -> dict:
        action = {"move_to": None, "use_ability": None, "ability_target_pos": None,
                  "ability_target_monster": None, "use_potion": False, "dash": None}

        alive = [m for m in monsters if m.alive]
        if not alive:
            return action

        # GCD check — don't try abilities if on GCD
        if self.hero.gcd > 0:
            # Just move toward target while waiting
            self.target = self.pick_target(alive)
            if self.target and self.hero.distance_to(self.target) > 50:
                action["move_to"] = (self.target.x, self.target.y)
            return action

        self.target = self.pick_target(alive)
        if not self.target:
            return action

        dist = self.hero.distance_to(self.target)
        hp_pct = self.hero.hp / self.hero.max_hp

        # 1. Holy Light if below 50% HP (use before potions since it's free)
        ab_f = self.hero.abilities.get("F")
        if ab_f and ab_f.is_ready() and hp_pct < 0.50:
            action["use_ability"] = "F"
            return action

        # 2. Potion if below 30% and Holy Light not ready
        if hp_pct < 0.30:
            action["use_potion"] = True

        # 3. Righteous Seal if not active
        ab_r = self.hero.abilities.get("R")
        has_seal = "Righteous Seal" in self.hero.buffs
        if ab_r and ab_r.is_ready() and not has_seal:
            action["use_ability"] = "R"
            return action

        # 4. Judgement if target is far or Seal about to expire
        ab_e = self.hero.abilities.get("E")
        seal_expiring = has_seal and self.hero.buffs["Righteous Seal"]["remaining"] < 2.0
        if ab_e and ab_e.is_ready() and dist <= 250:
            if dist > 120 or seal_expiring:
                action["use_ability"] = "E"
                action["ability_target_monster"] = self.target
                return action

        # 5. Smite if in melee range
        ab_q = self.hero.abilities.get("Q")
        if ab_q and ab_q.is_ready() and dist <= 70:
            action["use_ability"] = "Q"
            action["ability_target_monster"] = self.target
            return action

        # 6. Move toward target
        if dist > 50:
            action["move_to"] = (self.target.x, self.target.y)
        else:
            action["basic_attack"] = self.target

        return action


# Registry
HERO_AI_CLASSES = {
    "Fighter": FighterAI,
    "Cleric": ClericAI,
    "Paladin": HeroAI,  # TODO
    "Rogue": HeroAI,    # TODO
    "Wizard": HeroAI,   # TODO
}


def create_hero_ai(hero: Hero) -> HeroAI:
    """Create the appropriate AI for a hero based on class."""
    ai_class = HERO_AI_CLASSES.get(hero.class_name, HeroAI)
    return ai_class(hero)
