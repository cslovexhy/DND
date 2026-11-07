"""Hotbar slot order (pure; no pygame). The hotbar is a list of the hero's ability keys in slot order (slot 1 first);
the player rearranges it by dragging one slot onto another (they swap). The order is saved with the character
("hotbar" in the save file) and only lives on this player's client: the simulation casts by ability key.
"""


def merge_order(saved, ability_keys):
    """The hotbar for `ability_keys` (the hero's unlocked skills): the saved order first (skills the hero has), then
    any skill not placed yet, in the game's order (a newly unlocked skill goes to the end)."""
    saved = [k for k in (saved or []) if k in ability_keys]
    seen = set()
    order = []
    for k in saved:
        if k not in seen:
            seen.add(k)
            order.append(k)
    return order + [k for k in ability_keys if k not in seen]


def swap(order, i, j):
    """Swap two slots (new list); out-of-range slots change nothing."""
    order = list(order)
    if 0 <= i < len(order) and 0 <= j < len(order):
        order[i], order[j] = order[j], order[i]
    return order
