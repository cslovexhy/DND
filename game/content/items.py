"""Items (pure data; no pygame): what each item does, its icon, and rolling a monster's drop table (the tables
themselves are per monster type: content/monsters.MONSTER_DROPS).

Icons are (sheet, col, row) references the client turns into art: "dungeon" = assets/kenney_dungeon tilemap,
"rpg" = assets/kenney_rpg roguelike sheet (both 16 px tiles with a 1 px gap in the copies main.py loads).

Food heals `heal` HP spread over FOOD_DURATION seconds (a new meal replaces the meal still being eaten). Food with a
`buff` also gives the "Well Fed" buff for `buff_duration` seconds; only one food buff exists at a time, a new one
replaces the old. Potions (health and mana) restore `heal` HP / `mana` mana instantly and share one POTION_COOLDOWN.

Drinks restore `heal` HP and/or `mana` mana over DRINK_DURATION seconds (separate from eating: you can eat and drink
at once; a new drink replaces the drink still being drunk). A drink with a `buff` gives the "Refreshed" buff
(hp_regen_pct / mana_regen_pct: +100% = regeneration doubled) for `buff_duration` seconds; one drink buff at a time.
"""

from game.content import item_defs
from game.content.equipment import GEAR, ICONIC, describe as describe_gear, load_gear

FOOD_DURATION = 20.0      # seconds a meal takes to heal its full amount
DRINK_DURATION = 10.0     # seconds a drink takes to restore its full amount
POTION_COOLDOWN = 30.0    # seconds between two potions (health and mana potions share it)
FOOD_BUFF = "Well Fed"    # hero.buffs key of the (single) food buff
FOOD_HOT = "Eating"       # hero.buffs key of the meal being eaten (heal over time)
DRINK_BUFF = "Refreshed"  # hero.buffs key of the (single) drink buff
DRINK_HOT = "Drinking"    # hero.buffs key of the drink being drunk (HP / mana over time)

HEALTH_POTION = 1         # the Health Potion every character starts with and the potion key (Q) uses (never deleted)

ITEMS = {}                # {item id: item}: every item, from data/items.json (gear entries are the content/equipment.GEAR ones)


def reload(defs):
    """(Re)fill ITEMS (and GEAR, the shops) in place from item definitions. Invalid definitions are skipped with a
    message; returns the ids that were loaded."""
    load_gear(defs)
    ITEMS.clear()
    for iid, d in defs.items():
        errs = item_defs.validate(iid, d)
        if errs:
            print(f"[ITEMS] skipping item {iid!r}: {'; '.join(errs)}")
            continue
        ITEMS[iid] = GEAR[iid] if iid in GEAR else item_defs.to_item(d)
    from game.content import shop            # (the shops follow the prices and kinds)
    shop.rebuild()
    return list(ITEMS)


DEFS = item_defs.load()   # the definitions as loaded (the editor works on copies)
reload(DEFS)

STARTING_INVENTORY = [{"slot": 0, "item": HEALTH_POTION, "count": 3}]


def starting_inventory(class_name):
    """A new character's backpack: 3 Health Potions and the class's iconic weapon (not equipped)."""
    inv = [dict(s) for s in STARTING_INVENTORY]
    if class_name in ICONIC:
        inv.append({"slot": 1, "item": ICONIC[class_name], "count": 1})
    return inv


def roll_drops(table, monster_level, rng):
    """Items a monster drops from its drop table (content/monsters.MONSTER_DROPS: (item, chance) or
    (item, chance, min_lv, max_lv)); each entry rolls once with `rng`, e.g. the random module."""
    out = []
    for entry in table:
        item, chance = entry[0], entry[1]
        if len(entry) > 2 and not entry[2] <= monster_level <= entry[3]:
            continue
        if rng.random() < chance:
            out.append(item)
    return out


def _restores(it):
    parts = []
    if it.get("heal"):
        parts.append(f"{it['heal']} HP")
    if it.get("mana"):
        parts.append(f"{it['mana']} mana")
    return " and ".join(parts)


def describe(item_id):
    """What the item does, in the player's words (backpack tooltip), plus its own description if it has one."""
    text = _effect_text(item_id)
    extra = ITEMS[item_id].get("description")
    return f"{text} {extra}".strip() if extra and ITEMS[item_id]["kind"] not in ("misc", "weapon", "shield") else text


def _effect_text(item_id):
    it = ITEMS[item_id]
    if it["kind"] in ("weapon", "shield"):
        text = describe_gear(item_id)
        return f"{it['description']} {text}".strip() if it.get("description") else text
    if it["kind"] == "misc":
        return it.get("description") or "A curiosity."
    if it["kind"] == "potion":
        return f"Instantly restores {_restores(it)}. {POTION_COOLDOWN:g}s cooldown (shared by all potions)."
    if it["kind"] == "drink":
        text = f"Restores {_restores(it)} over {DRINK_DURATION:g}s."
        buff = it.get("buff")
        if buff:
            parts = []
            if buff.get("hp_regen_pct"):
                parts.append(f"+{buff['hp_regen_pct'] * 100:g}% HP regen")
            if buff.get("mana_regen_pct"):
                parts.append(f"+{buff['mana_regen_pct'] * 100:g}% mana regen")
            text += (f" {DRINK_BUFF}: {' and '.join(parts)} for {it['buff_duration'] / 60:g} min"
                     " (replaces other drink buffs).")
        return text
    text = f"Restores {it['heal']} HP over {FOOD_DURATION:g}s."
    buff = it.get("buff")
    if buff:
        parts = []
        if buff.get("damage_pct"):
            parts.append(f"+{buff['damage_pct'] * 100:g}% damage")
        if buff.get("max_hp_pct"):
            parts.append(f"+{buff['max_hp_pct'] * 100:g}% max HP")
        text += f" Well Fed: {' and '.join(parts)} for {it['buff_duration'] / 60:g} min (replaces other food buffs)."
    return text
