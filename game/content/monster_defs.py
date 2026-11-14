"""Monster definitions (pure; no pygame): the ONE place every monster type is defined, in data/monsters.json
({"version": 3, "next_id": n, "monsters": [{"id": 7, ...definition...}, ...]}). The map editor's Monsters screen
creates, edits and deletes them; content/monsters.py loads the file into the tables the game uses (SPAWN_STATS,
MONSTER_CATEGORY, MONSTER_DROPS).

A monster's ID is a permanent number (maps, quests and hive minds refer to it); its NAME can be changed freely.
Ids are never reused: next_id keeps counting up even after a monster is deleted. A map's spawn point is
{"type": <monster id>, "x": .., "y": ..}. Everything about a monster is defined here, once, for every map: if the
same monster should be tougher somewhere else or drop other things, make a second monster type (Duplicate).

A definition (only name, sprite, level and drops have no default):
  name, sprite           "Murloc Raider"; {"sheet": "creatures"|"dungeon", "col", "row", "big"?: true (drawn 1.5x)}
                         or {"file": png, "scale": n} (content/monster_art.py)
  level                  [min, max] monster level (1-30), required: each spawn rolls one; it sets HP, damage and XP
  category               "humanoid" / "beast" / "demon"; humanoids carry money
  attack                 "melee" / "ranged" (ranged ones keep their distance and shoot)
  boss, unique           boss AI + immune to slow/freeze + slow respawn; one-of-a-kind (name shown)
  stealthy               hides when it has not fought for a while (the Demogorgon)
  ac, speed, hp_mult     armor; speed in board units (5 = 75 px/s); max HP multiplier
  swing                  seconds between attacks (default 2.0; bosses 20% faster)
  sense_range            px: how far it notices heroes (default 170)
  attack_range           px: how close it fights from (default 50 melee / 220 ranged)
  respawn_mult           x the 60 s respawn time (default 1; bosses 10)
  relentless             never gives up the chase
  hive_mind              {"range": px, "types": [monster ids]} aggros when one of those is attacked in range
  skills                 castable skills the AI uses (content/skill_library.py)
  boss_skills            HP-triggered boss skills: {"deep_breath": {...}, "enrage": {...}} (engine/skills.py)
  drops                  [[item, chance 0-1], [item, chance, min monster level, max monster level]]: this type's own
                         list, nothing is shared or inherited
"""
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PATH = os.path.join(ROOT, "data", "monsters.json")
VERSION = 3
CATEGORIES = ("humanoid", "beast", "demon")
ATTACKS = ("melee", "ranged")
MAX_NAME = 32

DEFAULTS = {"category": "humanoid", "attack": "melee", "boss": False, "unique": False, "ac": 14, "speed": 5,
            "hp_mult": 1.0, "sense_range": 170, "skills": [], "drops": []}
LIMITS = {"ac": (8, 25), "speed": (1, 12), "hp_mult": (0.1, 20.0),
          "swing": (0.2, 10.0), "sense_range": (30, 1000), "attack_range": (20, 400),
          "respawn_mult": (0.1, 50.0)}
INTEGERS = {"ac", "speed", "sense_range", "attack_range"}
FLAGS = ("boss", "unique", "relentless", "stealthy")

# the HP-triggered boss skills and their settings (engine/skills.py); new ones start from these
BOSS_SKILL_DEFAULTS = {
    "deep_breath": {"radius": 200, "duration": 3.0, "cycles": 3, "dps": 100, "windup": 1.5, "at_hp_pct": [0.5, 0.2]},
    "enrage": {"at_hp_pct": [0.5], "damage_mult": 1.5},
}


class Definitions(dict):
    """{monster id: definition} that also remembers the next id to hand out (ids are never reused)."""
    next_id = 1

    def add(self, definition):
        """Add a new monster; returns its new id."""
        mid = self.next_id
        self[mid] = definition
        self.next_id = mid + 1
        return mid

    def take(self, other):
        """Become a copy of `other` (the editor's Done)."""
        self.clear()
        self.update(other)
        self.next_id = other.next_id


def new_definition(name):
    """A fresh type with the defaults (picture: the first creature tile)."""
    return {"name": name, "sprite": {"sheet": "creatures", "col": 0, "row": 0}, "level": [1, 1], **json.loads(json.dumps(DEFAULTS))}


def duplicate(d, name):
    """A copy under a new name (drops, skills and all): for "the same monster, but it drops different things"."""
    c = json.loads(json.dumps(d))
    c["name"] = name
    return c


def _number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def validate(type_id, d, known_skills, known_items):
    """Problems with one definition (empty list = fine)."""
    from game.content.monster_art import SHEET_SIZE
    errs = []
    if not (isinstance(type_id, int) and not isinstance(type_id, bool) and type_id >= 1):
        errs.append("id must be a whole number from 1")
    if not isinstance(d, dict):
        return errs + ["definition must be an object"]
    name = d.get("name")
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= MAX_NAME:
        errs.append(f"name must be 1-{MAX_NAME} characters")
    sp = d.get("sprite")
    if isinstance(sp, dict) and "file" in sp:
        if not (isinstance(sp["file"], str) and os.path.exists(os.path.join(ROOT, sp["file"]))
                and _number(sp.get("scale", 1))):
            errs.append("sprite file not found")
    elif not (isinstance(sp, dict) and sp.get("sheet") in SHEET_SIZE
              and isinstance(sp.get("col"), int) and isinstance(sp.get("row"), int)
              and 0 <= sp["col"] < SHEET_SIZE[sp["sheet"]][0] and 0 <= sp["row"] < SHEET_SIZE[sp["sheet"]][1]):
        errs.append("sprite must be a tile of the creatures or dungeon sheet")
    if d.get("category", DEFAULTS["category"]) not in CATEGORIES:
        errs.append(f"category must be one of {', '.join(CATEGORIES)}")
    if d.get("attack", DEFAULTS["attack"]) not in ATTACKS:
        errs.append("attack must be melee or ranged")
    for flag in FLAGS:
        if not isinstance(d.get(flag, False), bool):
            errs.append(f"{flag} must be true or false")
    for key, (lo, hi) in LIMITS.items():
        if key in d or key in DEFAULTS:
            v = d.get(key, DEFAULTS.get(key))
            if not _number(v) or not lo <= v <= hi or (key in INTEGERS and v != int(v)):
                errs.append(f"{key} must be {'a whole ' if key in INTEGERS else 'a '}number from {lo} to {hi}")
    skills = d.get("skills", [])
    if not isinstance(skills, list) or any(s not in known_skills for s in skills) or len(set(skills)) != len(skills):
        errs.append("skills must be a list of known skills (no repeats)")
    lv = d.get("level")
    if not (isinstance(lv, list) and len(lv) == 2
                               and all(isinstance(v, int) and not isinstance(v, bool) and 1 <= v <= 30 for v in lv)
                               and lv[0] <= lv[1]):
        errs.append("every monster needs a level: [min, max] with both 1-30")
    hm = d.get("hive_mind")
    if hm is not None and not (isinstance(hm, dict) and _number(hm.get("range")) and 50 <= hm["range"] <= 3000
                               and isinstance(hm.get("types"), list)
                               and all(isinstance(t, int) and not isinstance(t, bool) for t in hm["types"])):
        errs.append("hive_mind must be {\"range\": 50-3000, \"types\": [monster ids]}")
    bs = d.get("boss_skills", {})
    if not isinstance(bs, dict) or any(k not in BOSS_SKILL_DEFAULTS or not isinstance(v, dict) for k, v in bs.items()):
        errs.append("boss_skills must be a subset of " + ", ".join(BOSS_SKILL_DEFAULTS))
    else:
        for k, cfg in bs.items():
            if any(not (_number(v) or (isinstance(v, list) and all(_number(i) for i in v))) for v in cfg.values()):
                errs.append(f"boss skill {k}: every setting must be a number or a list of numbers")
    drops = d.get("drops", [])
    if not isinstance(drops, list) or len(drops) > 60:
        errs.append("drops must be a list (at most 60)")
        drops = []
    seen = set()
    for i, e in enumerate(drops):
        ok = (isinstance(e, list) and len(e) in (2, 4) and e[0] in known_items
              and _number(e[1]) and 0 < e[1] <= 1)
        if ok and len(e) == 4:
            ok = all(isinstance(v, int) and not isinstance(v, bool) and 1 <= v <= 30 for v in e[2:]) and e[2] <= e[3]
        if not ok:
            errs.append(f"drop {i + 1}: [item, chance 0-1] or [item, chance, min level, max level]")
        elif e[0] in seen:
            errs.append(f"drop {i + 1}: {e[0]} is listed twice")
        else:
            seen.add(e[0])
    return errs


def to_spawn_stats(d):
    """The SPAWN_STATS entry (what the game reads) of a definition."""
    def get(key):
        return d.get(key, DEFAULTS.get(key))
    stats = {"name": d["name"].strip(), "ac": get("ac"), "speed": get("speed"), "category": get("category"),
             "level": list(d["level"]),
             "drops": [tuple(e) for e in d.get("drops", [])], "sprite": json.loads(json.dumps(d["sprite"])),
             "sense_range": get("sense_range"),
             "attack_range": d.get("attack_range", 220 if d.get("attack") == "ranged" else 50)}
    for flag in FLAGS:
        if d.get(flag):
            stats[flag] = True
    if d.get("attack") == "ranged":
        stats["ranged"] = True
    for key in ("hp_mult", "swing", "respawn_mult"):
        if key in d and not (key == "hp_mult" and d[key] == 1.0):
            stats[key] = d[key]
    if d.get("skills"):
        stats["kit"] = list(d["skills"])
    if d.get("hive_mind"):
        stats["hive_mind"] = (d["hive_mind"]["range"], list(d["hive_mind"]["types"]))
    if d.get("boss_skills"):
        stats["skills"] = {k: {kk: (tuple(vv) if isinstance(vv, list) else vv) for kk, vv in cfg.items()}
                           for k, cfg in d["boss_skills"].items()}
    return stats


def load(path=PATH):
    """The definitions as Definitions {id: definition}. Raises OSError / ValueError if the file is missing or
    malformed."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not (isinstance(data, dict) and data.get("version") == VERSION and isinstance(data.get("monsters"), list)):
        raise ValueError(f"{path}: expected {{\"version\": {VERSION}, \"next_id\": n, \"monsters\": [...]}}")
    defs = Definitions()
    for entry in data["monsters"]:
        if not (isinstance(entry, dict) and isinstance(entry.get("id"), int) and not isinstance(entry["id"], bool)):
            raise ValueError(f"{path}: every monster needs a whole-number \"id\"")
        entry = dict(entry)
        mid = entry.pop("id")
        if mid in defs:
            raise ValueError(f"{path}: id {mid} is used twice")
        defs[mid] = entry
    defs.next_id = max([data.get("next_id", 1)] + [m + 1 for m in defs])
    return defs


def save(defs, path=PATH):
    """Write the file (monsters keep their order)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    next_id = max([getattr(defs, "next_id", 1)] + [m + 1 for m in defs])
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"version": VERSION, "next_id": next_id,
                   "monsters": [{"id": mid, **d} for mid, d in defs.items()]}, f, indent=1)
        f.write("\n")


def map_files(maps_dir=None):
    """{map file name: parsed map} for every map in data/maps (for 'which maps use this monster')."""
    maps_dir = maps_dir or os.path.join(ROOT, "data", "maps")
    out = {}
    for fn in sorted(os.listdir(maps_dir)) if os.path.isdir(maps_dir) else []:
        if fn.endswith(".json"):
            try:
                with open(os.path.join(maps_dir, fn), encoding="utf-8") as f:
                    out[fn[:-5]] = json.load(f)
            except (OSError, ValueError):
                pass
    return out


def maps_using(monster_id, maps):
    """Names of the maps (from map_files) that spawn this monster."""
    return [name for name, m in maps.items() if any(s.get("type") == monster_id for s in m.get("spawns", []))]
