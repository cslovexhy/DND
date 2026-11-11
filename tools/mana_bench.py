#!/usr/bin/env python3
"""Mana benchmark (pure sim, no window): how fast each class burns mana, when it goes out of mana (OOM), and how
much damage it still deals after that.

Per class and character level, a fresh hero on autopilot fights N training dummies (default 4): they chase and swing
like real mobs (never leashing home; 40% speed against the ranged Cleric and Wizard) but hit for 0 and can't die,
so the fight never ends and the hero stays in combat. Healers (Cleric,
Paladin) also take a steady `--incoming` share of their max HP per second (true damage, HP never drops below 40%, no
potions), so they use their heals. The run lasts --secs simulated seconds.

Columns:
  pool     max mana at that level
  burn/s   mana spent per second before OOM (absolute; the design goal: similar across classes at a level)
  x rate   burn/s / progression.mana_rate(level) (the most any class can spend per second at that level)
  OOM      seconds until an in-combat skill is off cooldown but can't be paid for ("-" = never: the class can't run
           dry). The dummies are aggroed from the start, so the Rogue's Stealth + Ambush opener never fires here.
  dps      damage per second to the dummies before OOM
  after    damage per second after OOM (from OOM + 5 s to the end) as % of `dps`
  combat   share of the time before OOM the hero was in combat (out of combat it regenerates 10x faster: Stealth
           makes mobs forget the Rogue, kited mobs may leash home)

    .venv/bin/python3 tools/mana_bench.py [--levels 1,5,10,20,30] [--only Wizard,Rogue] [--dummies 4]
                                          [--seeds 3] [--secs 240] [--incoming 0.02] [--json OUT]
"""
import argparse
import contextlib
import io
import json
import os
import random
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from game import saves                                  # noqa: E402
saves.SAVE_DIR = tempfile.mkdtemp()                     # never touch real saves
from game.engine.bootstrap import create_world          # noqa: E402
from game.engine.entities import Ability                # noqa: E402
from game.progression import mana_rate                  # noqa: E402

CLASSES = ["Fighter", "Cleric", "Paladin", "Rogue", "Wizard"]
LEVELS = [1, 5, 10, 20, 30]
MAP = "data/maps/northshire.json"
DT = 1 / 30
HP_FLOOR = 0.40
HEALERS = ("Cleric", "Paladin")
RANGED = ("Cleric", "Wizard")
DUMMY_SPEED = 0.4       # dummies chasing a ranged hero move at this share of normal speed (full speed: the caster kites
                        # nonstop and hardly casts; melee heroes get full-speed dummies: a solo melee hero backs off
                        # from a pack and slow dummies would never catch up)

_spent = {}                                             # id(hero) -> mana spent (counted in Ability.use)
_casts = {}                                             # id(hero) -> {skill name: casts}
_orig_use = Ability.use


def _counting_use(self):
    if self.caster is not None:
        if self.mana_cost:
            key = id(self.caster)
            _spent[key] = _spent.get(key, 0.0) + min(self.mana_cost, self.caster.mana)
        c = _casts.setdefault(id(self.caster), {})
        c[self.name] = c.get(self.name, 0) + 1
    _orig_use(self)


Ability.use = _counting_use


def setup(cls, level, dummies, seed=1):
    random.seed(seed)
    world, player = create_world(MAP, saves.blank_character(cls.lower(), cls, level=level), autopilot=True)
    hero = player.hero
    gs = world.game_state
    pack = gs.monsters[:dummies]
    del gs.monsters[dummies:]
    for i, m in enumerate(pack):
        # a loose arc 60-90 px in front of the hero (close enough for melee AoE and Frost Nova)
        m.x, m.y = world.find_walkable_nearby(hero.x + 70, hero.y + (i - (dummies - 1) / 2) * 25, radius=40)
        m.spawn_x, m.spawn_y = m.x, m.y
        m.hp = m.max_hp = 10 ** 7
        m.hit_damage = lambda: 0.0                     # they chase and swing like real mobs, but hit for 0
        m.base_damage = 0
        m.regen_rate_combat = m.regen_rate_ooc = 0.0
        m.relentless = True                            # never leash home (a kiting caster would drag them away)
        if cls in RANGED:
            m.speed = m.base_speed = m.base_speed * DUMMY_SPEED   # slow, so a kiting caster also gets to cast
    player._use_potion = lambda: None                  # potions would hide the HP pressure
    from game.engine.ai import aggro_monster
    for m in pack:
        aggro_monster(m, hero, gs.monsters)            # the fight starts right away
    return world, player, pack


def run(cls, level, dummies=4, secs=240, incoming=0.02, seed=1):
    world, player, pack = setup(cls, level, dummies, seed)
    hero = player.hero
    _spent[id(hero)] = 0.0
    _casts[id(hero)] = {}
    t, oom_t, spent_at_oom = 0.0, None, None
    combat_t = 0.0                                      # time in combat before OOM (in-combat regen is 10x slower)
    dmg_before = dmg_after = 0.0
    with contextlib.redirect_stdout(io.StringIO()):     # the hero AIs print debug lines
        while t < secs:
            world.step(DT)
            world.events.clear()
            t += DT
            # steady incoming damage (true damage) so healers heal; never below the floor. Only healers take it (it
            # is there to make them heal; others would just sit at the floor and rest whenever they lose aggro).
            if hero.class_name in HEALERS and hero.in_combat:
                hero.hp = max(hero.max_hp * HP_FLOOR, hero.hp - hero.max_hp * incoming * DT)
            hero.alive = True
            dealt = 0.0
            for m in pack:
                dealt += m.max_hp - m.hp
                m.hp = m.max_hp
                m.alive = True
            if oom_t is None:
                dmg_before += dealt
                combat_t += DT if hero.in_combat else 0.0
                if any(ab.remaining <= 0 and not ab.has_mana() and not ab.mana_secs   # (openers: not in combat)
                       for ab in hero.abilities.values()):
                    oom_t, spent_at_oom = t, _spent[id(hero)]
            elif t >= oom_t + 5:
                dmg_after += dealt
    before_t = oom_t if oom_t is not None else secs
    dps = dmg_before / before_t if before_t else 0.0
    after_t = secs - (oom_t + 5) if oom_t is not None else 0.0
    dps_after = dmg_after / after_t if after_t > 0 else None
    spent = spent_at_oom if spent_at_oom is not None else _spent[id(hero)]
    return {"class": cls, "level": level, "pool": hero.max_mana, "burn": spent / before_t,
            "oom": oom_t, "dps": dps, "combat_pct": combat_t / before_t * 100, "dps_after": dps_after,
            "after_pct": (dps_after / dps * 100) if (dps_after is not None and dps) else None,
            "casts": dict(_casts[id(hero)])}


def average(runs):
    """Mean of several seeds' results (OOM: mean over the seeds that went OOM, None if any never did)."""
    def mean(key):
        vals = [r[key] for r in runs]
        return None if any(v is None for v in vals) else sum(vals) / len(vals)
    out = dict(runs[0])
    for key in ("burn", "oom", "dps", "dps_after", "after_pct", "combat_pct"):
        out[key] = mean(key)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--levels", default=",".join(map(str, LEVELS)))
    ap.add_argument("--only", help="comma-separated classes")
    ap.add_argument("--dummies", type=int, default=4)
    ap.add_argument("--seeds", type=int, default=3, help="average over this many seeds")
    ap.add_argument("--secs", type=float, default=240)
    ap.add_argument("--incoming", type=float, default=0.02, help="incoming damage, share of max HP per second")
    ap.add_argument("--json", help="write all runs here")
    args = ap.parse_args(argv)
    classes = [c.strip().capitalize() for c in args.only.split(",")] if args.only else CLASSES
    levels = [int(x) for x in args.levels.split(",")]
    print(f"Mana bench: {args.dummies} dummies, {args.secs:g} s, incoming {args.incoming * 100:g}% max HP/s, "
          f"mean of {args.seeds} seed(s)",
          flush=True)
    print(f"{'class':8} {'lvl':>3} {'pool':>5} {'burn/s':>7} {'x rate':>6} {'OOM':>6} {'dps':>7} {'after':>6} {'combat':>6}",
          flush=True)
    runs = []
    for level in levels:
        for cls in classes:
            seeds = [run(cls, level, args.dummies, args.secs, args.incoming, seed=sd)
                     for sd in range(1, args.seeds + 1)]
            runs += seeds
            r = average(seeds)
            oom = f"{r['oom']:6.1f}" if r["oom"] is not None else "     -"
            after = f"{r['after_pct']:5.0f}%" if r["after_pct"] is not None else "     -"
            print(f"{cls:8} {level:3d} {r['pool']:5d} {r['burn']:7.2f} {r['burn'] / mana_rate(level):6.2f} {oom} "
                  f"{r['dps']:7.1f} {after} {r['combat_pct']:5.0f}%", flush=True)
    if args.json:
        with open(args.json, "w") as f:
            json.dump(runs, f, indent=1)
    return runs


if __name__ == "__main__":
    main()
