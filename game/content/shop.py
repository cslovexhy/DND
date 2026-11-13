"""Vendors and class trainers (pure data; no pygame). Money is in bronze (content/money.py: 100 bronze = 1 silver).

Prices are set against what a character earns: questing Northshire from level 1 to 6 brings in only about 150-200
bronze (31-35 kills at ~5 bronze, plus the quest rewards; measured with the quest bot). So gear costs several times
that (save up / grind for it), cheap food stays cheap, and training a skill costs TRAIN_COST_PER_LEVEL_SQ x (level it
unlocks at)^2: 5 bronze at level 2, 45 at 6, 125 at 10, 500 at 20, 1125 at 30.
"""
from game.content.equipment import GEAR
from game.content.items import ITEMS

PRICES = {
    # --- general goods: food and drink ---
    "bread": 10, "water": 10, "drumstick": 20, "wine": 40, "coffee": 60,
    "roast_chicken": 100, "sushi_plate": 100, "elven_nectar": 500,
    # --- weapons ---
    "wooden_sword": 50, "dagger": 100, "wand": 100, "short_sword": 150, "cleaver": 200, "axe": 300,
    "spear": 300, "staff": 350, "broadsword": 400, "double_axe": 600, "warhammer": 800,
    # --- armor ---
    "round_shield": 200, "buckler": 400,
}

SHOPS = {  # shop kind -> what it sells, cheapest first
    "general": sorted((k for k, it in ITEMS.items() if it["kind"] in ("food", "drink")), key=lambda k: PRICES[k]),
    "weapons": sorted((k for k, g in GEAR.items() if g["kind"] == "weapon"), key=lambda k: PRICES[k]),
    "armor": sorted((k for k, g in GEAR.items() if g["kind"] == "shield"), key=lambda k: PRICES[k]),
}
SHOP_TITLES = {"general": "General Goods", "weapons": "Weaponsmith", "armor": "Armorer"}

TRAIN_COST_PER_LEVEL_SQ = 1.25


def train_cost(unlock_level):
    """Bronze to learn a skill level that becomes available at this character level."""
    return int(round(TRAIN_COST_PER_LEVEL_SQ * unlock_level ** 2))
