"""Monster skills (pure; no pygame): data-driven special attacks that monsters get from game/content/monsters.py.

A monster entry may carry  "skills": {"deep_breath": {"radius": 200, "duration": 3.0, "cycles": 3, "dps": 100,
"windup": 1.5, "at_hp_pct": (0.5, 0.2)}}.  The flow is:

  1. AI    -> check_skill_triggers(monster): when an aggroed monster's HP first falls to a listed percentage, the
              skill is queued (each percentage fires once per life).
  2. World -> cast_queued_skills(world): starts at most one queued skill per monster at a time. A second trigger
              waits until the first is over, so two breaths never overlap.
  3. World -> update_casts(world, dt): the wind-up. For `windup` seconds the monster shows a message
              ("<name> took a deep breath...") over its head; then the zone appears where it stands.
  4. World -> update_hazards(world, dt): the zone lasts `duration` seconds and pulses `cycles` times (its glow
              brightens and fades once per cycle). Each pulse peaks halfway through its cycle and hits every hero inside
              for  dps x duration / cycles  true damage (armor does not reduce it): 3 pulses x 100 = 300 damage.
              The zone goes away at the end, or when the monster that breathed it dies.

Deep Breath is the first skill. Enrage ("enrage": {"at_hp_pct": (0.5,), "damage_mult": 1.5}) is instant: at the
threshold the monster's melee/ranged attack damage is multiplied (the Deep Breath zone is not).
"""
from dataclasses import dataclass

from game.content.difficulty import damage_multiplier
from game.engine.events import FloatText, Ring

BREATH_COLOR = (255, 50, 30)


@dataclass
class Cast:
    """A skill in its wind-up: the zone appears when `remaining` reaches 0."""
    monster: object
    name: str
    remaining: float


@dataclass(eq=False)
class Hazard:
    """A damaging zone on the ground that pulses `cycles` times over `duration` seconds."""
    kind: str
    x: float
    y: float
    radius: float
    duration: float
    cycles: int
    pulse_damage: float
    source: object = None            # the monster that breathed it
    color: tuple = BREATH_COLOR
    elapsed: float = 0.0
    pulses_done: int = 0

    @property
    def remaining(self):
        return max(0.0, self.duration - self.elapsed)

    @property
    def cycle_length(self):
        return self.duration / self.cycles

    def next_pulse_at(self):
        """Seconds after the start at which the next pulse peaks (halfway through its cycle)."""
        return (self.pulses_done + 0.5) * self.cycle_length

    def contains(self, entity) -> bool:
        return (entity.x - self.x) ** 2 + (entity.y - self.y) ** 2 <= self.radius ** 2


def check_skill_triggers(monster):
    """Queue every HP-triggered skill whose threshold the (aggroed) monster has just reached."""
    skills = getattr(monster, "skills", None)
    if not skills or not monster.alive or monster.max_hp <= 0:
        return
    pct = monster.hp / monster.max_hp
    for name, cfg in skills.items():
        for threshold in cfg.get("at_hp_pct", ()):
            key = (name, threshold)
            if key not in monster.skills_fired and pct <= threshold:
                monster.skills_fired.add(key)
                monster.skill_queue.append(name)


def _busy(world, monster) -> bool:
    """Already winding up or breathing (a zone of its own is still on the ground)."""
    return (any(c.monster is monster for c in world.casts)
            or any(h.source is monster for h in world.hazards))


ENRAGE_COLOR = (255, 60, 20)


def apply_enrage(world, monster):
    """Enrage: the monster's attacks (melee and ranged) deal `damage_mult` times as much from now on. Instant, so it
    never waits behind a Deep Breath wind-up that triggers at the same HP."""
    mult = monster.skills["enrage"].get("damage_mult", 1.5)
    monster.base_damage *= mult
    monster.ranged_attack_damage *= mult
    monster.enraged = True
    world.events.append(FloatText(monster.x, monster.y - 60, "ENRAGED!", ENRAGE_COLOR))
    world.events.append(Ring(monster.x, monster.y, 120, ENRAGE_COLOR))


def cast_queued_skills(world):
    for m in world.game_state.monsters:
        if m.alive and "enrage" in m.skill_queue:
            m.skill_queue.remove("enrage")
            apply_enrage(world, m)
        if m.alive and m.skill_queue and not _busy(world, m):
            start_cast(world, m, m.skill_queue.pop(0))


def start_cast(world, monster, name):
    cfg = monster.skills[name]
    if name == "deep_breath":
        monster.say = f"{monster.name} took a deep breath..."
        world.casts.append(Cast(monster, name, cfg.get("windup", 1.5)))
        return
    raise KeyError(f"unknown monster skill {name!r}")


def update_casts(world, dt):
    """Count down every wind-up; when one ends, the zone appears where the monster is standing."""
    for c in world.casts:
        m = c.monster
        if not m.alive:
            m.say = ""
            c.remaining = None                     # cancelled: the monster died while winding up
            continue
        c.remaining -= dt
        if c.remaining > 0:
            continue
        cfg = m.skills[c.name]
        m.say = ""
        cycles = int(cfg.get("cycles", 1))
        dps = cfg["dps"] * damage_multiplier(world.pp)       # same scaling as every monster's damage at higher pp
        world.hazards.append(Hazard(c.name, m.x, m.y, cfg["radius"], cfg["duration"], cycles,
                                    dps * cfg["duration"] / cycles, source=m))
        world.events.append(Ring(m.x, m.y, cfg["radius"], BREATH_COLOR))
        c.remaining = None                          # done
    world.casts[:] = [c for c in world.casts if c.remaining is not None]


def update_hazards(world, dt):
    heroes = [h for h in world.game_state.heroes if h.alive]
    for z in world.hazards:
        z.elapsed += dt
        while z.pulses_done < z.cycles and z.elapsed >= z.next_pulse_at():
            for hero in heroes:
                if hero.alive and z.contains(hero):
                    dealt = hero.take_damage(z.pulse_damage, ignore_armor=True)
                    world.events.append(FloatText(hero.x, hero.y - 30, f"-{dealt:.0f}", z.color))
            z.pulses_done += 1
    world.hazards[:] = [z for z in world.hazards
                        if z.elapsed < z.duration and (z.source is None or z.source.alive)]
