"""Item definitions: data/items.json (pure data; no pygame). Every item the game knows lives here, edited in the map
editor's Items screen (I). An item's ID is a permanent number (backpacks, equipment, drops, shops and quests refer to
it); its NAME and everything it does can be changed freely.

File:  {"version": 1, "next_id": N, "items": [{"id": 1, "name": "Health Potion", "kind": "potion", ...}, ...]}

An item (name, icon and kind are required):
  name       "Health Potion"
  icon       ["dungeon" | "rpg", col, row]: a tile of assets/kenney_dungeon (12 x 11) or the roguelike sheet (57 x 31)
  kind       "potion" | "drink" | "food" | "weapon" | "shield" | "misc" (misc: no use, e.g. quest items)
  price      bronze a vendor charges (empty = not sold); which vendor sells it follows the kind (content/shop.py)
  description  extra tooltip text (the whole tooltip of a misc item)
  potion     heal, mana: restored at once (potions share one cooldown)
  drink      heal and / or mana restored over 10 s; optional buff {"hp_regen_pct", "mana_regen_pct"} + buff_duration
  food       heal over 20 s; optional buff {"damage_pct", "max_hp_pct"} + buff_duration
  art        optional: which hand-drawn picture it is held as (default: its weapon_type; see client/gear_art.py)
  weapon     weapon_type, hands ("1h" | "2h"), swing (s), a, b (damage = a x class damage + b), weight
  shield     weapon_type (its art), block (extra block chance), weight
weapon_type is the item's subtype: skills check it (Stab needs a dagger-like type, ...), not the item. A new dagger
with weapon_type "dagger" works with every dagger skill and is drawn like one; see content/equipment.py.
"""
import json
import os

from game.content.monster_defs import Definitions, ROOT

PATH = os.path.join(ROOT, "data", "items.json")
VERSION = 1
KINDS = ("potion", "drink", "food", "weapon", "shield", "misc")
HANDS = ("1h", "2h")
MAX_NAME = 32
SHEET_SIZES = {"dungeon": (12, 11), "rpg": (57, 31)}      # (cols, rows) of the item icon sheets
MAX_PRICE = 10 ** 7
BUFF_KEYS = {"drink": ("hp_regen_pct", "mana_regen_pct"), "food": ("damage_pct", "max_hp_pct")}

# Saves written before items had numeric ids stored their names (backpacks, equipment, trade offers).
LEGACY_NAME_IDS = {
    "health_potion": 1, "minor_mana_potion": 2, "mana_potion": 3, "water": 4, "coffee": 5, "wine": 6,
    "elven_nectar": 7, "bread": 8, "drumstick": 9, "roast_chicken": 10, "sushi_plate": 11, "dagger": 12,
    "wooden_sword": 13, "short_sword": 14, "wand": 15, "cleaver": 16, "axe": 17, "broadsword": 18, "spear": 19,
    "staff": 20, "double_axe": 21, "warhammer": 22, "round_shield": 23, "buckler": 24,
}


def item_id(value):
    """An item reference as stored anywhere (an int, a digit string from JSON keys, or a pre-id item name) -> its
    numeric id, or None if it is none of those."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        if value.isdigit():
            return int(value)
        return LEGACY_NAME_IDS.get(value)
    return None


def new_definition(name, kind="misc"):
    d = {"name": name, "icon": ["dungeon", 0, 0], "kind": kind}
    if kind in ("weapon", "shield"):
        d["weapon_type"] = "dagger" if kind == "weapon" else "round_shield"
        d["weight"] = 1
        if kind == "weapon":
            d.update(hands="1h", swing=1.0, a=1.0, b=1)
        else:
            d["block"] = 0.03
    elif kind == "potion":
        d["heal"] = 100
    elif kind == "food":
        d["heal"] = 100
    elif kind == "drink":
        d["mana"] = 100
    return d


def duplicate(d, name):
    c = json.loads(json.dumps(d))
    c["name"] = name
    return c


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def validate(iid, d):
    """Problems with one item definition (empty list = fine)."""
    errs = []
    if not (isinstance(iid, int) and not isinstance(iid, bool) and iid >= 1):
        errs.append("id must be a whole number from 1")
    if not isinstance(d, dict):
        return errs + ["definition must be an object"]
    name = d.get("name")
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= MAX_NAME:
        errs.append(f"name must be 1-{MAX_NAME} characters")
    icon = d.get("icon")
    if not (isinstance(icon, list) and len(icon) == 3 and icon[0] in SHEET_SIZES
            and all(isinstance(v, int) and not isinstance(v, bool) for v in icon[1:])
            and 0 <= icon[1] < SHEET_SIZES[icon[0]][0] and 0 <= icon[2] < SHEET_SIZES[icon[0]][1]):
        errs.append("icon must be a tile of the dungeon or roguelike sheet")
    kind = d.get("kind")
    if kind not in KINDS:
        errs.append(f"kind must be one of {', '.join(KINDS)}")
    price = d.get("price")
    if price is not None and not (isinstance(price, int) and not isinstance(price, bool) and 1 <= price <= MAX_PRICE):
        errs.append("price must be a whole number of bronze (or empty)")
    if not isinstance(d.get("description", ""), str) or len(d.get("description", "")) > 300:
        errs.append("description is too long")
    for key in ("heal", "mana"):
        if key in d and not (_num(d[key]) and 0 <= d[key] <= 100000):
            errs.append(f"{key} must be a number from 0 to 100000")
    if kind in ("potion", "drink", "food") and not (d.get("heal") or d.get("mana")):
        errs.append("needs a heal or mana amount")
    if kind == "food" and d.get("mana"):
        errs.append("food heals HP only")
    buff = d.get("buff")
    if buff is not None:
        allowed = BUFF_KEYS.get(kind, ())
        if not (isinstance(buff, dict) and buff and set(buff) <= set(allowed)
                and all(_num(v) and 0 < v <= 10 for v in buff.values())):
            errs.append(f"buff must be {' / '.join(allowed) or 'nothing'} (a fraction, e.g. 0.1 = +10%)"
                        if allowed else "only food and drinks can have a buff")
        elif not (_num(d.get("buff_duration")) and 1 <= d["buff_duration"] <= 86400):
            errs.append("a buff needs buff_duration (seconds)")
    if kind in ("weapon", "shield"):
        if not isinstance(d.get("art", ""), str):
            errs.append("art must be a picture name")
        wt = d.get("weapon_type")
        if not (isinstance(wt, str) and wt.strip() and len(wt) <= 24):
            errs.append("needs a weapon type")
        if not (_num(d.get("weight")) and 0 <= d["weight"] <= 50):
            errs.append("weight must be 0-50")
    if kind == "weapon":
        if d.get("hands") not in HANDS:
            errs.append("hands must be 1h or 2h")
        if not (_num(d.get("swing")) and 0.2 <= d["swing"] <= 10):
            errs.append("swing must be 0.2-10 seconds")
        if not (_num(d.get("a")) and 0.1 <= d["a"] <= 10):
            errs.append("a (damage multiplier) must be 0.1-10")
        if not (_num(d.get("b")) and 0 <= d["b"] <= 1000):
            errs.append("b (flat damage) must be 0-1000")
    if kind == "shield":
        if not (_num(d.get("block")) and 0 <= d["block"] <= 0.9):
            errs.append("block must be 0-0.9")
    return errs


def to_item(d):
    """The ITEMS entry (what the game reads) of a definition: the file's fields, icon as a tuple, shields get
    hands 'offhand'."""
    it = json.loads(json.dumps(d))
    it["icon"] = tuple(it["icon"])
    if it["kind"] == "shield":
        it["hands"] = "offhand"
    return it


def load(path=PATH):
    """The definitions as Definitions {id: definition}. Raises OSError / ValueError if missing or malformed."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not (isinstance(data, dict) and data.get("version") == VERSION and isinstance(data.get("items"), list)):
        raise ValueError(f"{path}: expected {{\"version\": {VERSION}, \"next_id\": n, \"items\": [...]}}")
    defs = Definitions()
    for entry in data["items"]:
        if not (isinstance(entry, dict) and isinstance(entry.get("id"), int) and not isinstance(entry["id"], bool)):
            raise ValueError(f"{path}: every item needs a whole-number \"id\"")
        entry = dict(entry)
        iid = entry.pop("id")
        if iid in defs:
            raise ValueError(f"{path}: id {iid} is used twice")
        defs[iid] = entry
    defs.next_id = max([data.get("next_id", 1)] + [i + 1 for i in defs])
    return defs


def save(defs, path=PATH):
    """Write the file, one item per line (items keep their order)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    next_id = max([getattr(defs, "next_id", 1)] + [i + 1 for i in defs])
    lines = [json.dumps({"id": iid, **d}, ensure_ascii=False) for iid, d in defs.items()]
    with open(path, "w", encoding="utf-8") as f:
        f.write(f'{{"version": {VERSION}, "next_id": {next_id}, "items": [\n')
        f.write(",\n".join("  " + ln for ln in lines))
        f.write("\n]}\n")


def items_used_by(iid, monsters, quests, maps=()):
    """Where an item is referred to (deleting it is refused while there is any): monster drop lists, quest
    objectives and item spawns on maps. Returns a list of readable places."""
    out = []
    for mid, m in monsters.items():
        if any(e[0] == iid for e in m.get("drops", [])):
            out.append(f"drops of {m.get('name', mid)}")
    for q in quests:
        if any(o.get("item") == iid for o in q.get("objectives", [])):
            out.append(f"quest {q.get('title', q.get('id'))}")
    for name, data in dict(maps).items():
        if any(s.get("item") == iid for s in data.get("item_spawns", [])):
            out.append(f"item spawns on {name}")
    return out
