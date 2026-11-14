"""Custom monster types made in the map editor (pure; no pygame).

They live in data/custom_monsters.json ({"version": 1, "monsters": {type_id: definition}}) and are merged into the built-in
tables (content/monsters.py SPAWN_STATS / MONSTER_CATEGORY / MONSTER_DROPS) when the game starts, so a map can spawn
them like any other type. A definition holds only what needs a designer's input; everything else has a default:

  name      "Murloc Raider"                        shown over the monster
  sprite    {"sheet": "creatures", "col": 9, "row": 4}   (content/monster_art.py; any tile of the two sheets)
  category  "humanoid" / "beast" / "demon"          humanoids carry money (content/monsters.humanoid_money)
  attack    "melee" / "ranged"                      ranged ones keep their distance and shoot
  boss      false                                   boss AI, drawn 1.5x, immune to slow/freeze, slow respawn
  unique    false                                   one of a kind: name always shown
  ac 14, speed 5, hp_mult 1.0                       armor, move speed (board units: 5 = 75 px/s), HP multiplier
  skills    ["Poison Dagger", ...]                  castable skills (content/skill_library.py) the AI uses
  drops     [["bread", 0.03], ["wine", 0.01, 5, 10]]  item, chance per kill, optional monster-level range

The monster's LEVEL (which sets its HP, damage and XP) is per map: the map's "monster_levels" {type_id: [min, max]}.
"""
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CUSTOM_PATH = os.path.join(ROOT, "data", "custom_monsters.json")
CATEGORIES = ("humanoid", "beast", "demon")
ATTACKS = ("melee", "ranged")
DEFAULTS = {"category": "humanoid", "attack": "melee", "boss": False, "unique": False,
            "ac": 14, "speed": 5, "hp_mult": 1.0, "skills": [], "drops": []}
LIMITS = {"ac": (8, 25), "speed": (1, 12), "hp_mult": (0.1, 20.0)}
MAX_NAME = 32


def new_definition(name):
    """A fresh custom type with the defaults (sprite: the first creature tile)."""
    return {"name": name, "sprite": {"sheet": "creatures", "col": 0, "row": 0}, **json.loads(json.dumps(DEFAULTS))}


def type_id_for(name, taken):
    """A spawn-type id from a name ("Murloc Raider" -> "murloc_raider"), unique among `taken`."""
    base = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "monster"
    tid, n = base, 2
    while tid in taken:
        tid, n = f"{base}_{n}", n + 1
    return tid


def validate(type_id, d, known_skills, known_items, builtin_ids=()):
    """Problems with one definition (empty list = fine)."""
    from game.content.monster_art import SHEET_SIZE
    errs = []
    if not re.fullmatch(r"[a-z0-9_]{1,40}", str(type_id)):
        errs.append("id must be lowercase letters, digits and _")
    if type_id in builtin_ids:
        errs.append(f"{type_id!r} is a built-in monster type")
    if not isinstance(d, dict):
        return errs + ["definition must be an object"]
    name = d.get("name")
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= MAX_NAME:
        errs.append(f"name must be 1-{MAX_NAME} characters")
    sp = d.get("sprite")
    if not (isinstance(sp, dict) and sp.get("sheet") in SHEET_SIZE
            and isinstance(sp.get("col"), int) and isinstance(sp.get("row"), int)
            and 0 <= sp["col"] < SHEET_SIZE[sp["sheet"]][0] and 0 <= sp["row"] < SHEET_SIZE[sp["sheet"]][1]):
        errs.append("sprite must be a tile of the creatures or dungeon sheet")
    if d.get("category", DEFAULTS["category"]) not in CATEGORIES:
        errs.append(f"category must be one of {', '.join(CATEGORIES)}")
    if d.get("attack", DEFAULTS["attack"]) not in ATTACKS:
        errs.append("attack must be melee or ranged")
    for flag in ("boss", "unique"):
        if not isinstance(d.get(flag, False), bool):
            errs.append(f"{flag} must be true or false")
    for key, (lo, hi) in LIMITS.items():
        v = d.get(key, DEFAULTS[key])
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not lo <= v <= hi:
            errs.append(f"{key} must be a number from {lo} to {hi}")
    skills = d.get("skills", [])
    if not isinstance(skills, list) or any(s not in known_skills for s in skills) or len(set(skills)) != len(skills):
        errs.append("skills must be a list of known skills (no repeats)")
    drops = d.get("drops", [])
    if not isinstance(drops, list) or len(drops) > 40:
        errs.append("drops must be a list (at most 40)")
        drops = []
    for i, e in enumerate(drops):
        ok = (isinstance(e, list) and len(e) in (2, 4) and e[0] in known_items
              and isinstance(e[1], (int, float)) and not isinstance(e[1], bool) and 0 < e[1] <= 1)
        if ok and len(e) == 4:
            ok = all(isinstance(v, int) and not isinstance(v, bool) and 1 <= v <= 30 for v in e[2:]) and e[2] <= e[3]
        if not ok:
            errs.append(f"drop {i + 1}: [item, chance 0-1] or [item, chance, min level, max level]")
    return errs


def to_spawn_stats(d):
    """The SPAWN_STATS entry of a custom type. hp / dmg / xp are only used on maps that give no level range."""
    stats = {"name": d["name"].strip(), "hp": 2, "ac": d.get("ac", DEFAULTS["ac"]),
             "speed": d.get("speed", DEFAULTS["speed"]), "atk": 8, "dmg": 1, "xp": 10,
             "category": d.get("category", DEFAULTS["category"]),
             "drops": [tuple(e) for e in d.get("drops", [])],
             "sprite": dict(d["sprite"], **({"big": True} if d.get("boss") else {})),
             "custom": True}
    if d.get("boss"):
        stats["boss"] = True
    if d.get("unique"):
        stats["unique"] = True
    if d.get("attack") == "ranged":
        stats["ranged"] = True
    if d.get("hp_mult", 1.0) != 1.0:
        stats["hp_mult"] = d["hp_mult"]
    if d.get("skills"):
        stats["kit"] = list(d["skills"])
    return stats


def load(path=CUSTOM_PATH):
    """{type_id: definition} from the file ({} if there is none). Raises ValueError on a malformed file."""
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict) or not isinstance(data.get("monsters"), dict):
        raise ValueError(f"{path}: expected {{\"version\": 1, \"monsters\": {{...}}}}")
    return data["monsters"]


def save(defs, path=CUSTOM_PATH):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"version": 1, "monsters": defs}, f, indent=2, sort_keys=True)
