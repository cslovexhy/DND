"""Companion benchmark (pure sim, no window): how well does each AI companion fight and support?

    .venv/bin/python3 tools/bench_companions.py [--seeds 6] [--seconds 90] [--map PATH] [--only Cleric,Paladin] [--json OUT]

For every companion class, a player hero on autopilot (a class different from the companion) plays
a seeded session with that one companion. Reported per companion class, summed over seeds:
party kills, player/companion deaths, damage dealt by the companion, support casts that landed on the player (Renew/Wall/Holy Light),
and how many times it used each ability. Used to compare behaviour before/after AI refactors.
"""
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game import saves                                   # noqa: E402
from game.content.heroes import HERO_CLASSES             # noqa: E402
from game.engine import entities                         # noqa: E402
from game.engine.bootstrap import create_world           # noqa: E402

MAP = "data/maps/northshire.json"
DT = 1 / 30
PARTNER = {"Fighter": "Wizard", "Cleric": "Fighter", "Paladin": "Fighter", "Rogue": "Fighter", "Wizard": "Fighter"}


def run(comp_class, seed, seconds, map_path=MAP):
    random.seed(seed)
    player_class = PARTNER[comp_class]
    world, player = create_world(map_path, saves.blank_character("p", player_class), autopilot=True)
    info = next(c for c in HERO_CLASSES if c["class"] == comp_class)
    comp = world.spawn_companion(info)
    stats = {"kills": 0, "player_deaths": 0, "comp_deaths": 0, "comp_damage": 0.0, "support_on_player": 0,
             "uses": {}}
    # instrument: who used what, damage taken by monsters from the companion, heals landing on others
    orig_use = entities.Ability.use
    owner_of = {}
    for h in (player.hero, comp):
        for ab in h.abilities.values():
            owner_of[id(ab)] = h

    def use(ab):
        if owner_of.get(id(ab)) is comp:
            stats["uses"][ab.name] = stats["uses"].get(ab.name, 0) + 1
        return orig_use(ab)
    entities.Ability.use = use
    try:
        prev_alive = {"p": True, "c": True}
        had = {"renew": False, "wall": False, "potions": player.potions, "level": player.hero.level}
        hp_before = {}
        while world.game_state.game_time < seconds and not world.game_state.adventure_failed:
            hp_before = {id(m): m.hp for m in world.game_state.monsters}
            others_hp = {id(h): h.hp for h in world.game_state.heroes if h is not comp}
            world.step(DT)
            world.events.clear()
            # damage dealt by the companion this tick: approximate via monsters whose aggro target is the companion
            for m in world.game_state.monsters:
                if id(m) in hp_before and m.hp < hp_before[id(m)] and getattr(m, "aggro_target", None) is comp:
                    stats["comp_damage"] += hp_before[id(m)] - m.hp
            # support landing on the player: a new Renew/Wall buff, or a big heal that wasn't a potion
            ph = player.hero
            if "Renew" in ph.buffs and not had["renew"]:
                stats["support_on_player"] += 1
            if "Wall" in ph.buffs and not had["wall"]:
                stats["support_on_player"] += 1
            if (ph.hp - others_hp.get(id(ph), ph.hp) >= 100 and player.potions == had["potions"]
                    and ph.level == had["level"]):           # not a potion, not a level-up full heal
                stats["support_on_player"] += 1
            had = {"renew": "Renew" in ph.buffs, "wall": "Wall" in ph.buffs, "potions": player.potions,
                   "level": ph.level}
            for key, h in (("p", player.hero), ("c", comp)):
                if prev_alive[key] and not h.alive:
                    stats["player_deaths" if key == "p" else "comp_deaths"] += 1
                prev_alive[key] = h.alive
        stats["kills"] = player.hero.kills
    finally:
        entities.Ability.use = orig_use
    return stats


def main(argv):
    def arg(name, cast, default):
        return cast(argv[argv.index(name) + 1]) if name in argv else default
    seeds, seconds = arg("--seeds", int, 6), arg("--seconds", float, 90)
    map_path = arg("--map", str, MAP)
    only = arg("--only", str, None)
    out = {}
    for comp_class in PARTNER:
        if only and comp_class not in only.split(","):
            continue
        tot = {"kills": 0, "player_deaths": 0, "comp_deaths": 0, "comp_damage": 0.0, "support_on_player": 0,
               "uses": {}}
        for seed in range(1, seeds + 1):
            s = run(comp_class, seed, seconds, map_path)
            for k in ("kills", "player_deaths", "comp_deaths", "comp_damage", "support_on_player"):
                tot[k] += s[k]
            for k, v in s["uses"].items():
                tot["uses"][k] = tot["uses"].get(k, 0) + v
        tot["comp_damage"] = round(tot["comp_damage"])
        out[comp_class] = tot
        print(f"{comp_class:8s} kills={tot['kills']:4d} p_deaths={tot['player_deaths']:2d} "
              f"c_deaths={tot['comp_deaths']:2d} comp_dmg~{tot['comp_damage']:6d} "
              f"support_on_player={tot['support_on_player']:3d} uses={dict(sorted(tot['uses'].items()))}", flush=True)
    path = arg("--json", str, None)
    if path:
        with open(path, "w") as f:
            json.dump(out, f, indent=1)


if __name__ == "__main__":
    main(sys.argv)
