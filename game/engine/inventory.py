"""Backpack (pure; no pygame): ROWS x COLS slots, each empty or one stack {item, count}. Same items stack in one
slot with no limit; a new item goes to the first empty slot.

Saved state (character JSON "inventory", snapshot "inventory") is a sparse list: [{"slot": 0, "item": "bread",
"count": 2}, ...]. from_state() is also used on data from a co-op client, so it validates everything.
"""
from game.content.items import ITEMS, STARTING_INVENTORY

ROWS, COLS = 4, 10
SIZE = ROWS * COLS
MAX_COUNT = 10 ** 6


class Inventory:
    def __init__(self):
        self.slots = [None] * SIZE      # None or {"item": id, "count": n}

    # --- queries ---
    def count(self, item):
        return sum(s["count"] for s in self.slots if s and s["item"] == item)

    def item_at(self, slot):
        return self.slots[slot]["item"] if 0 <= slot < SIZE and self.slots[slot] else None

    # --- changes ---
    def add(self, item, n=1):
        """Put n of `item` in the backpack: on its existing stack, else in the first empty slot.
        Returns False (and changes nothing) if there is no room."""
        for s in self.slots:
            if s and s["item"] == item:
                s["count"] = min(MAX_COUNT, s["count"] + n)
                return True
        for i, s in enumerate(self.slots):
            if s is None:
                self.slots[i] = {"item": item, "count": n}
                return True
        return False

    def take_from_slot(self, slot, n=1):
        """Remove n from the stack in `slot` (the slot empties at 0). Returns the item id, or None."""
        s = self.slots[slot] if 0 <= slot < SIZE else None
        if not s or s["count"] < n:
            return None
        s["count"] -= n
        if s["count"] == 0:
            self.slots[slot] = None
        return s["item"]

    def take(self, item, n=1):
        """Remove n of `item` from its first stack. Returns True if there were enough."""
        for i, s in enumerate(self.slots):
            if s and s["item"] == item and s["count"] >= n:
                self.take_from_slot(i, n)
                return True
        return False

    # --- (de)serialization ---
    def to_state(self):
        return [{"slot": i, "item": s["item"], "count": s["count"]} for i, s in enumerate(self.slots) if s]

    @classmethod
    def from_state(cls, state):
        """Build from saved / received state (None = a new character's starting backpack).
        Raises ValueError on malformed data."""
        inv = cls()
        if state is None:
            state = STARTING_INVENTORY
        if not isinstance(state, list) or len(state) > SIZE:
            raise ValueError("inventory must be a list of slots")
        for entry in state:
            if not isinstance(entry, dict):
                raise ValueError("bad inventory slot")
            slot, item, count = entry.get("slot"), entry.get("item"), entry.get("count")
            if (not isinstance(slot, int) or isinstance(slot, bool) or not 0 <= slot < SIZE
                    or item not in ITEMS or not isinstance(count, int) or isinstance(count, bool)
                    or not 1 <= count <= MAX_COUNT or inv.slots[slot] is not None):
                raise ValueError("bad inventory slot")
            inv.slots[slot] = {"item": item, "count": count}
        return inv
