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

        # 2. Whirlwind (E) if 2+ enemies in melee range
        ab_e = self.hero.abilities.get("E")
        if ab_e and ab_e.is_ready() and enemies_in_melee >= 2:
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
    Quinn (Cleric) AI — Ranged wand attacker with self-sustain:
    - Stay at range (~150-200px) and cast Wanding as auto-attack
    - Use Wall (absorb shield) proactively when entering combat or taking damage
    - Use Renew when below 70% HP for sustained healing
    - Kite away from melee enemies if they get too close
    - Pop potion below 30% HP
    """

    def pick_target(self, monsters):
        alive = [m for m in monsters if m.alive]
        if not alive:
            return None
        # Prioritize low HP targets to secure kills
        low_hp = [m for m in alive if m.hp <= m.max_hp * 0.3]
        if low_hp:
            return min(low_hp, key=lambda m: self.hero.distance_to(m))
        return min(alive, key=lambda m: self.hero.distance_to(m))

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

        # 2. Wall if no shield active and enemies present
        ab_r = self.hero.abilities.get("R")
        if ab_r and ab_r.is_ready() and self.hero.absorb_shield <= 0:
            action["use_ability"] = "R"
            return action

        # 3. Renew if below 70% HP and not already ticking
        ab_e = self.hero.abilities.get("E")
        if ab_e and ab_e.is_ready() and hp_pct < 0.70 and "Renew" not in self.hero.buffs:
            action["use_ability"] = "E"
            return action

        # 4. Wanding (ranged auto-attack) if in range
        ab_q = self.hero.abilities.get("Q")
        if ab_q and ab_q.is_ready() and dist <= 200:
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

        # 6. Move into wand range if too far
        if dist > 190:
            action["move_to"] = (self.target.x, self.target.y)
        else:
            # In range but abilities on CD — basic attack
            action["basic_attack"] = self.target

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
        alive = [m for m in monsters if m.alive]
        if not alive:
            return None
        low_hp = [m for m in alive if m.hp <= m.max_hp * 0.3]
        if low_hp:
            return min(low_hp, key=lambda m: self.hero.distance_to(m))
        return min(alive, key=lambda m: self.hero.distance_to(m))

    def count_enemies_in_range(self, monsters, radius):
        return sum(1 for m in monsters if m.alive and self.hero.distance_to(m) <= radius)

    def update(self, monsters: list[Monster], dt: float, collision_fn=None) -> dict:
        action = {"move_to": None, "use_ability": None, "ability_target_pos": None,
                  "ability_target_monster": None, "use_potion": False, "dash": None}

        alive = [m for m in monsters if m.alive]
        if not alive:
            return action

        if self.hero.gcd > 0:
            return action

        # Don't act if channeling (immobilized)
        if self.hero.has_condition(Condition.IMMOBILIZED):
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
            action["use_ability"] = "E"
            action["ability_target_pos"] = (self.hero.x, self.hero.y)
            return action

        # 3. Frost Nova if 1 enemy close and low HP
        if ab_e and ab_e.is_ready() and enemies_close >= 1 and hp_pct < 0.50:
            action["use_ability"] = "E"
            action["ability_target_pos"] = (self.hero.x, self.hero.y)
            return action

        # 4. Fire Blast instant nuke when available
        ab_r = self.hero.abilities.get("R")
        if ab_r and ab_r.is_ready() and dist <= 260:
            action["use_ability"] = "R"
            action["ability_target_monster"] = self.target
            return action

        # 5. Frostbolt if in range
        ab_q = self.hero.abilities.get("Q")
        if ab_q and ab_q.is_ready() and dist <= 260:
            action["use_ability"] = "Q"
            action["ability_target_monster"] = self.target
            return action

        # 6. Kite if enemy too close
        if dist < 100:
            dx = self.hero.x - self.target.x
            dy = self.hero.y - self.target.y
            d = math.sqrt(dx * dx + dy * dy)
            if d > 0:
                action["move_to"] = (self.hero.x + (dx / d) * 120, self.hero.y + (dy / d) * 120)
            return action

        # 7. Move into range if too far
        if dist > 250:
            action["move_to"] = (self.target.x, self.target.y)

        return action


HERO_AI_CLASSES = {
    "Fighter": FighterAI,
    "Cleric": ClericAI,   # Quinn — ranged wand + sustain
    "Paladin": PaladinAI, # Keyleth — Seal/Smite/Judgement melee
    "Rogue": HeroAI,      # WIP
    "Wizard": WizardAI,   # Heskan — channeled frostbolt + burst
}


def create_hero_ai(hero: Hero) -> HeroAI:
    """Create the appropriate AI for a hero based on class."""
    ai_class = HERO_AI_CLASSES.get(hero.class_name, HeroAI)
    return ai_class(hero)
