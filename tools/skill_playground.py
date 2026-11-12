#!/usr/bin/env python3
"""Skill playground: try a monster skill on 1 or 2 monsters in a small arena (pure sim, or the real game window).

The arena is the boss test room (data/maps/bossTestRoom.json) with its spawns replaced: your hero at the start and
1 monster (2 for support skills such as Renew / Wall: a caster and a friend it can heal / shield) a few tiles away,
already fighting you. The skill comes from content/skill_library.py through the monster's "kit" (spawn "stats"),
so it has the hero's damage formula, cooldown and mana cost; the monster casts it through the same cast path as a
hero (engine/casting.py: try_cast, with the skill's AI hint deciding when).

    .venv/bin/python3 tools/skill_playground.py --list
    .venv/bin/python3 tools/skill_playground.py --skill "Poison Dagger"
    .venv/bin/python3 tools/skill_playground.py --skill Renew --mob human_cultist --mob-level 8 --secs 40
    .venv/bin/python3 tools/skill_playground.py --kit "Fire Blast,Poison Dagger" --passive
    .venv/bin/python3 tools/skill_playground.py --skill Charge --passive
    .venv/bin/python3 tools/skill_playground.py --skill Wall --window      # play it yourself (TAB: autopilot off)

Headless prints every cast (time, caster, skill, target, caster mana left) and a summary: per monster its casts,
mana spent and when it first could not pay for a ready skill (out of mana); healing and shields it gave; what reached
the hero (damage, of which damage over time; conditions such as STUNNED / FROZEN / SLOWED; debuffs such as
Demoralized). --passive: the hero never attacks (to watch damage skills without the monster dying); by default the
hero fights on autopilot (support skills need someone to heal).
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
from game.engine import casting                          # noqa: E402
from game.engine.ai import aggro_monster                 # noqa: E402
from game.engine.bootstrap import create_world           # noqa: E402
from game.engine.entities import Entity                  # noqa: E402
from game.engine.events import SkillCast                 # noqa: E402

CASTABLE = casting.AI_CASTABLE                           # skills a monster brain uses from its kit

BASE_MAP = "data/maps/bossTestRoom.json"
HERO_TILE = (4, 14)
MOB_TILES = [(10, 14), (11, 16)]
SUPPORT_SKILLS = tuple(n for n, sp in casting.SKILLS.items() if sp.targeting == "ally")   # 2 monsters
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
    """Tallies what reached whom during the run, by wrapping the shared entry points (nothing skill-specific)."""

    def __init__(self, hero, mobs):
        self.hero, self.mobs = hero, mobs
        self.damage = self.dot = 0.0       # to the hero, from monsters
        self.conditions = {}               # condition name -> times applied to the hero
        self.debuffs = set()               # buffs a monster put on the hero (e.g. Demoralized)
        self.healed = {}                   # monster -> HP healed on it (Renew ticks, Holy Light)
        self.shields = 0.0
        self.patches = []

    def _patch(self, obj, name, make):
        orig = getattr(obj, name)
        setattr(obj, name, make(orig))
        self.patches.append((obj, name, orig))

    def __enter__(self):
        rec, hero = self, self.hero

        def take_damage(orig):
            def f(raw, ignore_armor=False, source=None, threat=1.0, flash=True):
                dealt = orig(raw, ignore_armor, source, threat, flash)
                if source in rec.mobs:
                    rec.damage += dealt
                    rec.dot += 0.0 if flash else dealt
                return dealt
            return f

        def apply_condition(orig):
            def f(condition, duration, *a, **kw):
                ok = orig(condition, duration, *a, **kw)
                if ok:
                    rec.conditions[condition.name] = rec.conditions.get(condition.name, 0) + 1
                return ok
            return f

        def heal(orig):
            def f(self_, amount):
                got = orig(self_, amount)
                if self_ in rec.mobs and got:
                    rec.healed[self_] = rec.healed.get(self_, 0.0) + got
                return got
            return f

        self._patch(hero, "take_damage", take_damage)
        self._patch(hero, "apply_condition", apply_condition)
        self._patch(Entity, "heal", heal)
        return self

    def note_frame(self):
        self.debuffs |= {b for b in self.hero.buffs if b == "Demoralized"}
        for m in self.mobs:
            if m.absorb_shield > getattr(m, "_pg_shield", 0.0):
                self.shields += m.absorb_shield - getattr(m, "_pg_shield", 0.0)
            m._pg_shield = m.absorb_shield

    def __exit__(self, *exc):
        for obj, name, orig in reversed(self.patches):
            setattr(obj, name, orig)


def run(args, kits):
    path = build_map(args.mob, args.mob_level, kits, os.path.join(tempfile.mkdtemp(), "skill_playground.json"))
    random.seed(args.seed)
    world, player = create_world(path, saves.blank_character("hero", args.hero, level=args.hero_level),
                                 autopilot=not args.passive)
    hero = player.hero
    others = [c for c in HERO_CLASSES if c["class"] != args.hero][:args.party]
    party = [world.spawn_companion(c, owner=player) for c in others]   # more heroes (e.g. for Cleave)
    for comp in party:
        comp.x, comp.y = hero.x + 20, hero.y + 20 * (party.index(comp) + 1)
        if args.passive:
            next(p for p in world.companions if p.hero is comp).ai_enabled = False
    mobs = [m for m in world.game_state.monsters]
    for m in mobs:
        aggro_monster(m, hero, world.game_state.monsters)
    names = {m.eid: f"{m.name} #{i + 1}" for i, m in enumerate(mobs)}
    names[hero.eid] = f"{hero.name} ({args.hero})"
    for comp in party:
        names[comp.eid] = f"{comp.name} ({comp.class_name})"
    party_txt = f" + {len(party)} companion(s)" if party else ""

    print(f"Arena: {args.hero} L{args.hero_level}{party_txt} ({hero.max_hp} HP) vs {len(mobs)} x {SPAWN_STATS[args.mob]['name']} "
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
    t = 0.0
    print("\nCasts:", flush=True)
    with Recorder(hero, mobs) as rec:
        while t < args.secs:
            mana_before = {m: m.mana for m in mobs}
            with contextlib.redirect_stdout(io.StringIO()):       # the hero AI prints debug lines
                world.step(DT)
            t += DT
            for ev in world.events:
                m = next((x for x in mobs if x.eid == ev.caster_id), None) if isinstance(ev, SkillCast) else None
                if m is not None:                       # (heroes' and companions' casts are not listed)
                    casts[m][ev.skill] = casts[m].get(ev.skill, 0) + 1
                    spent[m] += max(0.0, mana_before[m] - m.mana)
                    target = names.get(ev.target_id, "?") if ev.target_id != ev.caster_id else "self"
                    print(f"  t={t:6.1f}s  {names[m.eid]:<20} {ev.skill:<14} -> {target:<20} "
                          f"mana {m.mana:6.1f}/{m.max_mana}", flush=True)
            world.events.clear()
            rec.note_frame()
            for m in mobs:
                if m not in oom_at and m.alive and any(ab.remaining <= 0 and not ab.has_mana()
                                                       for ab in m.abilities.values()):
                    oom_at[m] = t
            if not any(m.alive for m in mobs):
                print(f"  t={t:6.1f}s  every monster is dead", flush=True)
                break
    if not any(casts.values()):
        print("  (none)", flush=True)

    print("\nSummary:", flush=True)
    for m in mobs:
        c = ", ".join(f"{k} x{v}" for k, v in casts[m].items()) or "nothing"
        oom = f"out of mana at {oom_at[m]:.1f}s" if m in oom_at else "never out of mana"
        extra = f"; healed {rec.healed[m]:.0f}" if rec.healed.get(m) else ""
        state = "alive" if m.alive else "dead"
        print(f"  {names[m.eid]} ({state}, {m.hp:.0f}/{m.max_hp:.0f} HP): cast {c}; mana spent {spent[m]:.0f}; "
              f"{oom}{extra}", flush=True)
    if rec.shields:
        print(f"  Shields put on monsters: {rec.shields:.0f}", flush=True)
    conds = ", ".join(f"{k} x{v}" for k, v in sorted(rec.conditions.items())) or "none"
    print(f"  To the hero: {rec.damage:.0f} damage ({rec.dot:.0f} of it over time); conditions {conds}; "
          f"debuffs {', '.join(sorted(rec.debuffs)) or 'none'} (hero {hero.hp:.0f}/{hero.max_hp} HP, "
          f"{hero.deaths} deaths)", flush=True)
    return {"casts": {names[m.eid]: casts[m] for m in mobs}, "oom": {names[m.eid]: oom_at.get(m) for m in mobs},
            "damage": rec.damage, "dot": rec.dot, "conditions": dict(rec.conditions), "debuffs": sorted(rec.debuffs),
            "healed": sum(rec.healed.values()), "shields": rec.shields}


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
    ap.add_argument("--passive", action="store_true", help="the hero (and companions) never attack")
    ap.add_argument("--party", type=int, help="AI companions with the hero (default 0, 1 for sweeps such as Cleave)")
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
    if args.party is None:
        args.party = 1 if any(casting.SKILLS[s].targeting == "sweep" for s in kit if s in casting.SKILLS) else 0
    kits = [kit] + [[]] * (n - 1)         # the second monster is the friend: no skills
    return window(args, kits) if args.window else run(args, kits)


if __name__ == "__main__":
    main()
