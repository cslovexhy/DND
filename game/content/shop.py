"""Vendors and class trainers (pure data; no pygame). Money is in bronze (content/money.py: 100 bronze = 1 silver).

Prices are set against what a character earns: questing Northshire from level 1 to 6 brings in only about 150-200
bronze (31-35 kills at ~5 bronze, plus the quest rewards; measured with the quest bot). So gear costs several times
that (save up / grind for it), cheap food stays cheap, and training a skill costs TRAIN_COST_PER_LEVEL_SQ x (level it
unlocks at)^2: 5 bronze at level 2, 45 at 6, 125 at 10, 500 at 20, 1125 at 30.
"""
PRICES = {}   # {item id: bronze}: every item with a "price" (data/items.json; set it in the editor's Items screen)
SHOPS = {}    # shop kind -> the item ids it sells, cheapest first: general = food and drink, weapons, armor = shields

SHOP_KINDS = {"general": ("food", "drink"), "weapons": ("weapon",), "armor": ("shield",)}


def rebuild():
    """Fill PRICES and SHOPS (in place) from content/items.ITEMS: an item is sold by the vendor of its kind if it has
    a price."""
    from game.content.items import ITEMS
    PRICES.clear()
    PRICES.update({iid: it["price"] for iid, it in ITEMS.items() if it.get("price")})
    for shop, kinds in SHOP_KINDS.items():
        SHOPS[shop] = sorted((iid for iid in PRICES if ITEMS[iid]["kind"] in kinds), key=lambda iid: PRICES[iid])


SHOP_TITLES = {"general": "General Goods", "weapons": "Weaponsmith", "armor": "Armorer"}

TRAIN_COST_PER_LEVEL_SQ = 1.25


def train_cost(unlock_level):
    """Bronze to learn a skill level that becomes available at this character level."""
    return int(round(TRAIN_COST_PER_LEVEL_SQ * unlock_level ** 2))
