#!/usr/bin/env python3
"""Skill playground: try a monster skill on 1 or 2 monsters in a small arena (pure sim, or the real game window).

The arena is the boss test room (data/maps/bossTestRoom.json) with its spawns replaced: your hero at the start and
1 monster (2 for support skills such as Renew / Wall: a caster and a friend it can heal / shield) a few tiles away,
already fighting you. The skill comes from content/skill_library.py through the monster's "kit" (spawn "stats"),
so it has the hero's damage formula, cooldown and mana cost; the monster casts it with engine/monster_casting.py.

    .venv/bin/python3 tools/skill_playground.py --list
    .venv/bin/python3 tools/skill_playground.py --skill "Poison Dagger"
    .venv/bin/python3 tools/skill_playground.py --skill Renew --mob human_cultist --mob-level 8 --secs 40
    .venv/bin/python3 tools/skill_playground.py --kit "Fire Blast,Poison Dagger" --passive
    .venv/bin/python3 tools/skill_playground.py --skill Wall --window      # play it yourself (TAB: autopilot off)

Headless prints every cast (time, caster, skill, target, caster mana left) and a summary per monster: casts, mana
spent, when it first could not pay for a ready skill (out of mana), damage it did to the hero (hits / poison / Fire
Blast), healing and shields it gave. --passive: the hero never attacks (to watch damage skills without the monster
dying); by default the hero fights on autopilot (support skills need someone to heal).
"""
import argparse
import contextlib
import io
import json
import os
import random
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from game import saves                                   # noqa: E402
saves.SAVE_DIR = tempfile.mkdtemp()                      # never touch real saves
from game.content.heroes import HERO_CLASSES             # noqa: E402
from game.content.monsters import SPAWN_STATS            # noqa: E402
from game.content.skill_library import SKILLS            # noqa: E402
from game.engine import abilities                        # noqa: E402
from game.engine.ai import aggro_monster                 # noqa: E402
from game.engine.bootstrap import create_world           # noqa: E402
from game.engine.entities import Monster                 # noqa: E402
from game.engine.events import SkillCast                 # noqa: E402
from game.engine.monster_casting import CASTABLE         # noqa: E402

BASE_MAP = "data/maps/bossTestRoom.json"
HERO_TILE = (4, 14)
MOB_TILES = [(10, 14), (11, 16)]
SUPPORT_SKILLS = ("Renew", "Wall")      # cast on a friend: the arena gets 2 monsters
DT = 1 / 30


def build_map(mob_type, mob_level, kits, path):
    """Write the arena: the boss room with the hero start and one monster per kit in `kits`."""
    with open(BASE_MAP) as f:
        data = json.load(f)
    spawns = [{"type": "hero_start", "x": HERO_TILE[0], "y": HERO_TILE[1]}]
    for (x, y), kit in zip(MOB_TILES, kits):
        spawns.append({"type": mob_type, "x": x, "y": y, "stats": {"kit": list(kit)}})
    data["spawns"] = spawns
    data["monster_levels"] = {mob_type: [mob_level, mob_level]}
    with open(path, "w") as f:
        json.dump(data, f)
    return path


class Recorder:
    """Tallies what the monsters did, by wrapping the shared skill effects for the run."""

    def __init__(self):
        self.fire_blast = {}     # caster -> damage dealt
        self.shield = {}         # caster -> shield given
        self.healed = {}         # healed monster -> HP from heal-over-time
        self.patches = []

    def _wrap(self, obj, name, after):
        orig = getattr(obj, name)

        def wrapper(*a, **kw):
            out = orig(*a, **kw)
            after(out, *a, **kw)
            return out
        setattr(obj, name, wrapper)
        self.patches.append((obj, name, orig))

    def __enter__(self):
        self._wrap(abilities, "fire_blast",
                   lambda out, world, caster, target, ab: self._add(self.fire_blast, caster, out))
        self._wrap(abilities, "wall", lambda out, world, caster, target, ab: self._add(self.shield, caster, out))
        self._wrap(Monster, "heal", lambda out, mon, amount: self._add(self.healed, mon, out))
        return self

    def __exit__(self, *exc):
        for obj, name, orig in reversed(self.patches):
            setattr(obj, name, orig)

    @staticmethod
    def _add(d, key, amount):
        if isinstance(key, Monster) and amount:
            d[key] = d.get(key, 0.0) + amount


def run(args, kits):
    path = build_map(args.mob, args.mob_level, kits, os.path.join(tempfile.mkdtemp(), "skill_playground.json"))
    random.seed(args.seed)
    world, player = create_world(path, saves.blank_character("hero", args.hero, level=args.hero_level),
                                 autopilot=not args.passive)
    hero = player.hero
    mobs = [m for m in world.game_state.monsters]
    for m in mobs:
        aggro_monster(m, hero, world.game_state.monsters)
    names = {m.eid: f"{m.name} #{i + 1}" for i, m in enumerate(mobs)}
    names[hero.eid] = f"{hero.name} ({args.hero})"

    print(f"Arena: {args.hero} L{args.hero_level} ({hero.max_hp} HP) vs {len(mobs)} x {SPAWN_STATS[args.mob]['name']} "
          f"L{args.mob_level}; {'hero does not attack' if args.passive else 'hero fights on autopilot'}; "
          f"{args.secs:g} s, seed {args.seed}", flush=True)
    for m in mobs:
        kit = ", ".join(f"{ab.name} (skill Lv{ab.level}: {ab.mana_cost:g} mana, {ab.cooldown:g}s CD"
                        + ("" if ab.name in CASTABLE else ", NOT castable by monsters yet") + ")"
                        for ab in m.abilities.values()) or "no skills"
        print(f"  {names[m.eid]}: {m.max_hp:.0f} HP, hits {m.base_damage:g} every {m.weapon_speed:g}s, "
              f"mana {m.max_mana}; {kit}", flush=True)

    casts = {m: {} for m in mobs}
    spent = {m: 0.0 for m in mobs}
    oom_at = {}
    hit_dmg = poison_dmg = 0.0
    orig_hero_damage = hero.take_damage

    def hero_take_damage(raw, ignore_armor=False, source=None, threat=1.0, flash=True):
        nonlocal hit_dmg, poison_dmg
        dealt = orig_hero_damage(raw, ignore_armor, source, threat, flash)
        if not flash:
            poison_dmg += dealt                  # damage over time (poison ticks don't flash)
        elif source in casts:
            hit_dmg += dealt                     # melee hits and Fire Blast (Fire Blast is split out below)
        return dealt
    hero.take_damage = hero_take_damage

    t = 0.0
    print("\nCasts:", flush=True)
    with Recorder() as rec:
        while t < args.secs:
            mana_before = {m: m.mana for m in mobs}
            with contextlib.redirect_stdout(io.StringIO()):       # the hero AI prints debug lines
                world.step(DT)
            t += DT
            for ev in world.events:
                if isinstance(ev, SkillCast):
                    m = next(x for x in mobs if x.eid == ev.caster_id)
                    casts[m][ev.skill] = casts[m].get(ev.skill, 0) + 1
                    spent[m] += max(0.0, mana_before[m] - m.mana)
                    target = names.get(ev.target_id, "?") if ev.target_id != ev.caster_id else "self"
                    print(f"  t={t:6.1f}s  {names[m.eid]:<20} {ev.skill:<14} -> {target:<20} "
                          f"mana {m.mana:6.1f}/{m.max_mana}", flush=True)
            world.events.clear()
            for m in mobs:
                if m not in oom_at and m.alive and any(ab.remaining <= 0 and not ab.has_mana()
                                                       for ab in m.abilities.values()):
                    oom_at[m] = t
            if not any(m.alive for m in mobs):
                print(f"  t={t:6.1f}s  every monster is dead", flush=True)
                break
    if not any(casts.values()):
        print("  (none)", flush=True)

    fire = sum(rec.fire_blast.values())
    print("\nSummary:", flush=True)
    for m in mobs:
        c = ", ".join(f"{k} x{v}" for k, v in casts[m].items()) or "nothing"
        oom = f"out of mana at {oom_at[m]:.1f}s" if m in oom_at else "never out of mana"
        extra = []
        if rec.shield.get(m):
            extra.append(f"shields given {rec.shield[m]:.0f}")
        if rec.healed.get(m):
            extra.append(f"healed by Renew {rec.healed[m]:.0f}")
        state = "alive" if m.alive else "dead"
        print(f"  {names[m.eid]} ({state}, {m.hp:.0f}/{m.max_hp:.0f} HP): cast {c}; mana spent {spent[m]:.0f}; "
              f"{oom}" + ("; " + ", ".join(extra) if extra else ""), flush=True)
    print(f"  Damage to the hero: hits {hit_dmg - fire:.0f}, Fire Blast {fire:.0f}, poison {poison_dmg:.0f} "
          f"(hero {hero.hp:.0f}/{hero.max_hp} HP, {hero.deaths} deaths)", flush=True)
    return {"casts": {names[m.eid]: casts[m] for m in mobs}, "oom": {names[m.eid]: oom_at.get(m) for m in mobs},
            "hit": hit_dmg - fire, "fire_blast": fire, "poison": poison_dmg,
            "shield": sum(rec.shield.values()), "healed": sum(rec.healed.values())}


def window(args, kits):
    """Open the real game on the arena (throwaway hero, autopilot on: TAB to play yourself)."""
    path = build_map(args.mob, args.mob_level, kits, os.path.join(tempfile.gettempdir(), "skill_playground.json"))
    idx = next(i for i, c in enumerate(HERO_CLASSES) if c["class"] == args.hero)
    print(f"Arena map: {path}", flush=True)
    return subprocess.call([sys.executable, "-m", "game.main", "--auto", "--hero", str(idx),
                            "--level", str(args.hero_level), "--map", path], cwd=ROOT)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--skill", help="one skill (2 monsters for support skills)")
    ap.add_argument("--kit", help="comma-separated skills for one monster (overrides --skill)")
    ap.add_argument("--mobs", type=int, choices=(1, 2), help="number of monsters (default 1, 2 for support skills)")
    ap.add_argument("--mob", default="human_cultist", help="spawn type (content/monsters.py SPAWN_STATS key)")
    ap.add_argument("--mob-level", type=int, default=5)
    ap.add_argument("--hero", default="Fighter", choices=[c["class"] for c in HERO_CLASSES])
    ap.add_argument("--hero-level", type=int, default=5)
    ap.add_argument("--secs", type=float, default=60)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--passive", action="store_true", help="the hero never attacks")
    ap.add_argument("--window", action="store_true", help="open the game on the arena instead")
    ap.add_argument("--list", action="store_true", help="list the skills")
    args = ap.parse_args(argv)
    if args.list:
        print("Castable by monsters:", ", ".join(CASTABLE))
        print("Not yet:", ", ".join(s for s in SKILLS if s not in CASTABLE))
        return None
    if args.mob not in SPAWN_STATS:
        ap.error(f"unknown --mob {args.mob!r}")
    kit = [s.strip() for s in args.kit.split(",")] if args.kit else [args.skill] if args.skill else None
    if not kit:
        ap.error("give --skill or --kit (see --list)")
    unknown = [s for s in kit if s not in SKILLS]
    if unknown:
        ap.error(f"unknown skill(s) {unknown} (see --list)")
    n = args.mobs or (2 if any(s in SUPPORT_SKILLS for s in kit) else 1)
    kits = [kit] + [[]] * (n - 1)         # the second monster is the friend: no skills
    return window(args, kits) if args.window else run(args, kits)


if __name__ == "__main__":
    main()
