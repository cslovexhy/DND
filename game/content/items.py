"""Items (pure data; no pygame): what each item does, its icon and which monsters drop it.

Icons are (sheet, col, row) references the client turns into art: "dungeon" = assets/kenney_dungeon tilemap,
"rpg" = assets/kenney_rpg roguelike sheet (both 16 px tiles with a 1 px gap in the copies main.py loads).

Food heals `heal` HP spread over FOOD_DURATION seconds (a new meal replaces the meal still being eaten). Food with a
`buff` also gives the "Well Fed" buff for `buff_duration` seconds; only one food buff exists at a time, a new one
replaces the old. Potions (health and mana) restore `heal` HP / `mana` mana instantly and share one POTION_COOLDOWN.

Drinks restore `heal` HP and/or `mana` mana over DRINK_DURATION seconds (separate from eating: you can eat and drink
at once; a new drink replaces the drink still being drunk). A drink with a `buff` gives the "Refreshed" buff
(hp_regen_pct / mana_regen_pct: +100% = regeneration doubled) for `buff_duration` seconds; one drink buff at a time.
"""

FOOD_DURATION = 20.0      # seconds a meal takes to heal its full amount
DRINK_DURATION = 10.0     # seconds a drink takes to restore its full amount
POTION_COOLDOWN = 30.0    # seconds between two potions (health and mana potions share it)
FOOD_BUFF = "Well Fed"    # hero.buffs key of the (single) food buff
FOOD_HOT = "Eating"       # hero.buffs key of the meal being eaten (heal over time)
DRINK_BUFF = "Refreshed"  # hero.buffs key of the (single) drink buff
DRINK_HOT = "Drinking"    # hero.buffs key of the drink being drunk (HP / mana over time)

ITEMS = {
    "health_potion": {"name": "Health Potion", "icon": ("dungeon", 7, 9), "kind": "potion", "heal": 120},
    "minor_mana_potion": {"name": "Minor Mana Potion", "icon": ("dungeon", 8, 10), "kind": "potion", "mana": 200},
    "mana_potion":   {"name": "Mana Potion", "icon": ("dungeon", 8, 9), "kind": "potion", "mana": 400},
    "water":         {"name": "Water", "icon": ("rpg", 54, 17), "kind": "drink", "mana": 300},
    "coffee":        {"name": "Coffee", "icon": ("rpg", 56, 15), "kind": "drink", "mana": 600,
                      "buff": {"mana_regen_pct": 1.0}, "buff_duration": 600.0},
    "wine":          {"name": "Wine", "icon": ("rpg", 56, 14), "kind": "drink", "heal": 300, "mana": 300},
    "elven_nectar":  {"name": "Elven Nectar", "icon": ("rpg", 55, 15), "kind": "drink", "heal": 500, "mana": 500,
                      "buff": {"hp_regen_pct": 1.0, "mana_regen_pct": 1.0}, "buff_duration": 600.0},
    "bread":         {"name": "Bread", "icon": ("rpg", 56, 12), "kind": "food", "heal": 120},
    "drumstick":     {"name": "Drumstick", "icon": ("rpg", 55, 13), "kind": "food", "heal": 200},
    "roast_chicken": {"name": "Roast Chicken", "icon": ("rpg", 54, 15), "kind": "food", "heal": 300,
                      "buff": {"damage_pct": 0.05, "max_hp_pct": 0.05}, "buff_duration": 600.0},
    "sushi_plate":   {"name": "Sushi Plate", "icon": ("rpg", 56, 13), "kind": "food", "heal": 200,
                      "buff": {"damage_pct": 0.10}, "buff_duration": 600.0},
}

# (item, chance per kill, lowest monster level, highest monster level). Every row rolls separately on each kill.
DROP_TABLE = [
    ("health_potion", 0.01, 1, 9),     # "any mob lower than level 10"
    ("bread",         0.01, 1, 10),
    ("drumstick",     0.01, 3, 10),
    ("roast_chicken", 0.01, 4, 10),
    ("sushi_plate",   0.01, 4, 10),
]

BEAST_FOOD_MULT = 3      # beasts (monsters.MONSTER_CATEGORY) drop food 3x as often (they carry no money)

STARTING_INVENTORY = [{"slot": 0, "item": "health_potion", "count": 3}]


def drop_chance(item, base_chance, category):
    return base_chance * BEAST_FOOD_MULT if category == "beast" and ITEMS[item]["kind"] == "food" else base_chance


def roll_drops(monster_level, rng, category=None):
    """Items a monster of this level and category drops (each DROP_TABLE row rolls once with `rng`, e.g. the
    random module)."""
    return [item for item, chance, lo, hi in DROP_TABLE
            if lo <= monster_level <= hi and rng.random() < drop_chance(item, chance, category)]


def _restores(it):
    parts = []
    if it.get("heal"):
        parts.append(f"{it['heal']} HP")
    if it.get("mana"):
        parts.append(f"{it['mana']} mana")
    return " and ".join(parts)


def describe(item_id):
    """What the item does, in the player's words (backpack tooltip)."""
    it = ITEMS[item_id]
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
