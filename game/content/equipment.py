"""Equipment (pure data and rules; no pygame): weapons and shields, and what a hero's gear does to its stats.

Gear items are defined in data/items.json like every item and live in content/items.ITEMS too (kind "weapon" / "shield"), so they go in the backpack, drop on the
ground and trade like any other item. A hero has two slots, "main" and "off" (hero.equipment).

Hands (user rules):
  1h       main hand; a Rogue or Fighter (DUAL_WIELD_CLASSES) may also put one in the off hand
  2h       main hand, and the off hand must be empty
  offhand  shields: off hand only

Stats a hero gets from its gear (gear_stats):
  base damage  = a x (class base damage) + b; before any skill's own a / b. 1h weapons have a = 1. A 1h weapon in
                 the off hand (dual wield) adds only half its b.
  swing        = the slower of (class swing, weapon swing); dual wield uses (main + off) / 2 as the weapon swing.
  move speed   = base speed x (100 - total gear weight) / 100
  block        = SHIELD_BASE_BLOCK + the shield's bonus while a shield is in the off hand: that share of monster basic
                 attacks (melee swings and arrows) does no damage.
Bare hands change nothing, so a hero with no gear has exactly its class numbers.
"""

from game.content import item_defs

SLOTS = ("main", "off")
SHIELD_BASE_BLOCK = 0.05
DUAL_WIELD_CLASSES = {"Rogue", "Fighter"}

GEAR = {}      # {item id: item}: every weapon and shield (filled from data/items.json by load_gear)
ICONIC = {}    # class name -> the item id of its iconic weapon (the lowest id of its weapon type)

# Each class's iconic weapon type: its swing matches the class swing (no speed cost).
ICONIC_TYPE = {"Rogue": "dagger", "Fighter": "axe", "Paladin": "warhammer", "Cleric": "wand", "Wizard": "staff"}


def load_gear(defs):
    """(Re)fill GEAR and ICONIC in place from item definitions (content/item_defs.py). Invalid ones are skipped."""
    from game.content import item_defs
    GEAR.clear()
    for iid, d in defs.items():
        if d.get("kind") in ("weapon", "shield") and not item_defs.validate(iid, d):
            GEAR[iid] = item_defs.to_item(d)
    ICONIC.clear()
    for cls, wtype in ICONIC_TYPE.items():
        ids = [iid for iid, g in GEAR.items() if g.get("weapon_type") == wtype and g["kind"] == "weapon"]
        if ids:
            ICONIC[cls] = min(ids)


def type_of(item):
    """The weapon type (subtype) of an equipment item id, or None."""
    g = GEAR.get(item)
    return g.get("weapon_type") if g else None


def weapon_types():
    """Every weapon type a skill rule or an item mentions, in a stable order."""
    seen = []
    for t in [*DEFAULT_TYPES, *(g.get("weapon_type") for g in GEAR.values())]:
        if t and t not in seen:
            seen.append(t)
    return seen


DEFAULT_TYPES = ("dagger", "1h_sword", "wand", "axe", "spear", "staff", "double_axe", "warhammer", "round_shield",
                 "buckler")

# --- which skills a weapon allows, and how they animate (user rule: default = every weapon; spells just "raise") ---
# Weapon families are sets of weapon TYPES (an item's weapon_type, not the item: a new dagger is still a dagger).
# The main-hand weapon decides; bare hands are always allowed, so a character without gear can use every skill
# exactly as before.
LIGHT_BLADES = {"dagger", "1h_sword"}
SWORDS = {"1h_sword"}
EDGED = {"dagger", "1h_sword", "axe", "double_axe"}
MELEE = EDGED | {"warhammer", "spear", "staff"}            # everything but the wand
STAB_WEAPONS = LIGHT_BLADES | {"spear"}                     # things you can thrust a point with, quickly
SKILL_WEAPONS = {  # skill -> weapons allowed (missing = every weapon)
    "Stab": STAB_WEAPONS,                                   # no axes, hammers or staves
    "Ambush": LIGHT_BLADES,                                 # a hidden blade in the back
    "Poison Dagger": LIGHT_BLADES,
    "Strike": MELEE,                                        # any melee weapon (not a wand)
    "Smite": MELEE,
    "Cleave": EDGED - {"dagger"} | {"warhammer", "staff"},  # a wide sweep needs reach: no dagger, spear or wand
    "Heroic Strike": MELEE,                                 # empowers the next Strike / Cleave
}
# skill -> animation: "weapon" = the weapon's own basic move (chop, or thrust for daggers / spears / fists),
# "thrust", "chop", "sweep" (wide Cleave arc); missing = "raise" (spells, buffs, heals: the weapon goes up).
SKILL_ANIM = {
    "Strike": "weapon", "Smite": "chop", "Stab": "thrust", "Ambush": "thrust", "Cleave": "sweep",
}
NO_ANIM = {"Stealth", "Charge"}                             # stealth fades out, Charge dashes: no weapon pose


def skill_allows(skill, item):
    """Can `skill` be used with `item` (an item id) in the main hand (None = bare hands: always)?"""
    if item is None:
        return True
    allowed = SKILL_WEAPONS.get(skill)
    return allowed is None or type_of(item) in allowed


def weapon_move(item):
    """A weapon's own basic move: "thrust" for stabbing weapons and bare fists, else "chop"."""
    return "thrust" if item is None or type_of(item) in ("dagger", "spear") else "chop"


def skill_anim(skill, item):
    """How `skill` animates with `item` in hand: "thrust" / "chop" / "sweep" / "raise", or None (no pose)."""
    if skill in NO_ANIM:
        return None
    a = SKILL_ANIM.get(skill, "raise")
    return weapon_move(item) if a == "weapon" else a


def attack_hand(skill, equipment, count):
    """Which hand swings this time ("main" / "off"): dual wielders alternate on each melee attack, but only with an
    off-hand weapon the skill allows (a shield or a disallowed weapon just stays at the side)."""
    off = equipment.get("off")
    if (skill_anim(skill, equipment.get("main")) in ("thrust", "chop", "sweep") and off in GEAR
            and GEAR[off]["kind"] == "weapon" and skill_allows(skill, off) and count % 2 == 0):
        return "off"
    return "main"


def allowed_names(skill):
    """Player-facing list of the weapons a skill allows (None = any)."""
    allowed = SKILL_WEAPONS.get(skill)
    if allowed is None:
        return None
    return [t.replace("_", " ").title() for t in weapon_types() if t in allowed]

NO_GEAR = {"a": 1.0, "b": 0.0, "swing": 0.0, "weight": 0, "block": 0.0, "move_mult": 1.0}


def empty_equipment():
    return {slot: None for slot in SLOTS}


def is_gear(item):
    return item in GEAR


def gear_stats(equipment):
    """What this gear does (see the module doc): a, b, weapon swing (0 = bare hands), total weight, block chance,
    move-speed multiplier."""
    main, off = (equipment or {}).get("main"), (equipment or {}).get("off")
    if main is None and off is None:
        return dict(NO_GEAR)
    a, b, swings, weight, block = 1.0, 0.0, [], 0, 0.0
    if main is not None:
        g = GEAR[main]
        a, b = g["a"], g["b"]
        swings.append(g["swing"])
        weight += g["weight"]
    if off is not None:
        g = GEAR[off]
        weight += g["weight"]
        if g["kind"] == "shield":
            block = SHIELD_BASE_BLOCK + g["block"]
        else:                                   # dual wield: half the off-hand bonus, average the two swings
            b += g["b"] / 2
            swings.append(g["swing"])
    swing = sum(swings) / len(swings) if swings else 0.0
    return {"a": a, "b": b, "swing": swing, "weight": weight, "block": block,
            "move_mult": max(0.0, (100 - weight) / 100)}


def slot_for(class_name, item, equipment):
    """Where right-clicking `item` in the backpack equips it: "main" or "off".
    Shields: off hand. 2h: main hand. 1h: the main hand if it is empty or holds a 2h weapon; else the off hand if
    this class dual-wields and the off hand is free; else it replaces the main-hand weapon."""
    g = GEAR[item]
    if g["hands"] == "offhand":
        return "off"
    if g["hands"] == "2h":
        return "main"
    main, off = equipment.get("main"), equipment.get("off")
    if main is None or GEAR[main]["hands"] == "2h":
        return "main"
    if class_name in DUAL_WIELD_CLASSES and off is None:
        return "off"
    return "main"


def equip(class_name, equipment, item, slot):
    """Put `item` in `slot`. Returns (new_equipment, items_taken_off) or raises ValueError if not allowed.
    A 2h weapon also takes the off-hand item off; a shield or off-hand weapon takes a 2h main weapon off."""
    g = GEAR.get(item)
    if g is None:
        raise ValueError("not equipment")
    if slot not in SLOTS:
        raise ValueError("bad slot")
    if slot == "main" and g["hands"] == "offhand":
        raise ValueError("shields go in the off hand")
    if slot == "off":
        if g["hands"] == "2h":
            raise ValueError("two-handed weapons go in the main hand")
        if g["kind"] == "weapon" and class_name not in DUAL_WIELD_CLASSES:
            raise ValueError("only Rogues and Fighters can dual wield")
    new = dict(equipment)
    removed = []
    if new[slot] is not None:
        removed.append(new[slot])
    new[slot] = item
    if slot == "main" and g["hands"] == "2h" and new["off"] is not None:
        removed.append(new["off"])
        new["off"] = None
    if slot == "off" and new["main"] is not None and GEAR[new["main"]]["hands"] == "2h":
        removed.append(new["main"])
        new["main"] = None
    return new, removed


def validate_equipment(state, class_name):
    """Clean equipment from a save or a co-op client (None = nothing equipped). Raises ValueError if malformed or
    not allowed for the class."""
    if state is None:
        return empty_equipment()
    if not isinstance(state, dict) or set(state) - set(SLOTS):
        raise ValueError("bad equipment")
    eq = empty_equipment()
    for slot in SLOTS:                     # main first, so equip() sees it when checking the off hand
        item = state.get(slot)
        if item is None:
            continue
        from game.content.item_defs import item_id
        item = item_id(item)                    # (old saves stored the item's name)
        if item is None:
            raise ValueError("bad equipment item")
        if item not in GEAR:
            continue                            # an item that was deleted from items.json: it is just gone
        eq, removed = equip(class_name, eq, item, slot)
        if removed:
            raise ValueError("equipment does not fit together")
    return eq


def describe(item_id):
    """Tooltip text for a weapon or shield."""
    g = GEAR[item_id]
    if g["kind"] == "shield":
        return (f"Off hand. +{(SHIELD_BASE_BLOCK + g['block']) * 100:g}% block chance "
                f"({SHIELD_BASE_BLOCK * 100:g}% + {g['block'] * 100:g}%). Weight {g['weight']}.")
    hands = {"1h": "One-handed", "2h": "Two-handed"}[g["hands"]]
    dmg = f"+{g['b']:g} damage" if g["a"] == 1 else f"{g['a'] * 100:g}% damage +{g['b']:g}"
    text = f"{hands}. {dmg}. {g['swing']:g}s swing. Weight {g['weight']}."
    if g["hands"] == "1h":
        text += " Rogues and Fighters can dual wield it (off hand: half the bonus)."
    banned = [s for s in SKILL_WEAPONS if g.get("weapon_type") not in SKILL_WEAPONS[s]]
    if banned:
        text += f" Can't be used for: {', '.join(banned)}."
    return text


load_gear(item_defs.load())
