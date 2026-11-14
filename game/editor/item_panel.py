"""The map editor's Items screen (press I): create, edit, duplicate and delete every item of the game.

Items live in data/items.json (content/item_defs.py). Each has a permanent number; the name and everything the item does
can change. Left: every item (button: filter by kind), "+ New", "Duplicate", "Delete". Right: the selected item. Its
fields depend on its kind:
  potion / drink / food   heal and mana, and the buff a drink or a meal gives (regen % / damage % / max HP %, minutes)
  weapon                  weapon type (what skills check: a new dagger is a "dagger"), hands, swing, damage a x + b, weight
  shield                  weapon type (its picture), block chance, weight
  misc                    nothing: quest items; set a description
Every kind: name, picture (any tile of the dungeon or roguelike sheets), price (vendors sell what has one) and a
description for the tooltip.

Done saves data/items.json; Esc discards everything done in this screen. Click-driven like the Monsters screen:
click(pos, button) and draw(surface, font, big); text goes through ask(title, default, long=False).
"""
import copy

import pygame

from game.content import item_defs
from game.editor.widgets import Widgets, BG, PANEL, LINE, TEXT, DIM, GOLD, RED, GREEN

LIST_W, ROW = 300, 26
PROTECTED = {1}          # the Health Potion: characters start with it and the potion key (Q) uses it

# (label, key, how it is edited, help) per kind. Edits: text / long / cycle / int / float / pct / minutes / optint
COMMON = [
    ("Name", "name", "text", "Shown in the backpack, vendors and quest lists. The id never changes."),
    ("Kind", "kind", "cycle", "Changing the kind resets what the item does. misc = plain items with no use."),
    ("Price", "price", "optint", "Bronze a vendor charges. Empty = not sold. Which vendor follows the kind."),
]
EFFECT = {
    "potion": [("Heal HP", "heal", "optint", "Restored at once. Potions share one 30 s cooldown."),
               ("Restore mana", "mana", "optint", "Restored at once.")],
    "drink": [("Heal HP", "heal", "optint", "Restored over 10 s."),
              ("Restore mana", "mana", "optint", "Restored over 10 s."),
              ("HP regen +%", "buff.hp_regen_pct", "pct", "Buff while it lasts: +100% = regeneration doubled."),
              ("Mana regen +%", "buff.mana_regen_pct", "pct", "Buff while it lasts."),
              ("Buff minutes", "buff_duration", "minutes", "How long the buff lasts.")],
    "food": [("Heal HP", "heal", "optint", "Restored over 20 s."),
             ("Damage +%", "buff.damage_pct", "pct", "Well Fed buff: +10% damage."),
             ("Max HP +%", "buff.max_hp_pct", "pct", "Well Fed buff."),
             ("Buff minutes", "buff_duration", "minutes", "How long the buff lasts.")],
    "weapon": [("Weapon type", "weapon_type", "cycle", "What skills check (Stab needs a dagger-like type...)."),
               ("Hands", "hands", "cycle", "2h weapons take the off hand too."),
               ("Swing (s)", "swing", "float", "Seconds between swings (the slower of class and weapon)."),
               ("Damage x", "a", "float", "Damage = this x the class's damage + the flat bonus."),
               ("Damage +", "b", "float", "Flat damage bonus."),
               ("Weight", "weight", "float", "Move speed - weight %.")],
    "shield": [("Weapon type", "weapon_type", "cycle", "Which picture it is held as."),
               ("Block +%", "block", "pct", "On top of the 5% every shield gives."),
               ("Weight", "weight", "float", "Move speed - weight %.")],
    "misc": [],
}
LIMITS = {"heal": (0, 100000), "mana": (0, 100000), "price": (1, item_defs.MAX_PRICE), "swing": (0.2, 10),
          "a": (0.1, 10), "b": (0, 1000), "weight": (0, 50), "block": (0, 0.9)}


def fields_for(kind):
    return COMMON + EFFECT.get(kind, [])


class ItemPanel(Widgets):
    def __init__(self, defs, ask, art, usage=lambda iid: [], path=item_defs.PATH):
        """defs: item_defs.Definitions (edited in place); ask(title, default, long=False) -> str or None; art:
        monster_panel.Art; usage(item id) -> where it is used (deleting is refused while there is any)."""
        self.defs, self.ask, self.art, self.usage, self.path = defs, ask, art, usage, path
        self.selected = next(iter(defs), None)
        self.mode = "main"            # "main" / "icon" (picture picker)
        self.kind_filter = None
        self.message, self.message_ok = "", True
        self.hits, self.help = [], ""
        self.done = False
        self.list_scroll = 0

    # --- data helpers ---
    @property
    def d(self):
        return self.defs.get(self.selected)

    def shown(self):
        ids = [i for i, d in self.defs.items() if self.kind_filter in (None, d.get("kind"))]
        return sorted(ids, key=lambda i: (item_defs.KINDS.index(self.defs[i].get("kind", "misc")),
                                          self.defs[i].get("name", "").lower()))

    def errors(self):
        out = []
        for iid, d in self.defs.items():
            for e in item_defs.validate(iid, d):
                out.append(f"{d.get('name', iid)}: {e}")
        return out

    def _say(self, text, ok=True):
        self.message, self.message_ok = text, ok

    @staticmethod
    def types():
        from game.content.equipment import weapon_types
        return weapon_types()

    # --- actions ---
    def click(self, pos, button=1):
        hit = next(((a, arg) for r, a, arg in reversed(self.hits) if r.collidepoint(pos)), None)
        if hit is None:
            if self.mode != "main":
                self.mode = "main"
            return
        action, arg = hit
        getattr(self, f"_do_{action}")(arg, button)

    def _do_select(self, iid, button):
        self.selected, self.mode = iid, "main"
        self._say("")

    def _do_filter(self, _, button):
        order = [None, *item_defs.KINDS]
        self.kind_filter = order[(order.index(self.kind_filter) + 1) % len(order)]
        if self.selected not in self.shown() and self.shown():
            self.selected = self.shown()[0]

    def _do_scroll(self, delta, button):
        self.list_scroll = max(0, self.list_scroll + delta)

    def _do_new(self, _, button):
        name = self.ask("New item name:", "")
        if not name or not name.strip():
            return
        kind = self.kind_filter or "misc"
        self.selected = self.defs.add(item_defs.new_definition(name.strip()[:item_defs.MAX_NAME], kind))
        self.mode = "icon"
        self._say(f"Created {name.strip()} ({kind}). Pick a picture, then set what it does.")

    def _do_duplicate(self, _, button):
        if self.d is None:
            return
        name = self.ask("Name of the copy:", f"{self.d['name']} 2")
        if not name or not name.strip():
            return
        self.selected = self.defs.add(item_defs.duplicate(self.d, name.strip()[:item_defs.MAX_NAME]))
        self._say(f"Copied as {name.strip()}.")

    def _do_delete(self, _, button):
        d = self.d
        if d is None:
            return
        if self.selected in PROTECTED:
            self._say(f"{d['name']} can't be deleted: every character starts with it.", False)
            return
        used = self.usage(self.selected)
        if used:
            self._say(f"{d['name']} is used by: {', '.join(used[:4])}{'...' if len(used) > 4 else ''}. "
                      "Remove it there first.", False)
            return
        del self.defs[self.selected]
        self.selected = next(iter(self.shown()), None)
        self._say(f"Deleted {d['name']} (characters that carry it just lose it)")

    def _do_icon(self, _, button):
        self.mode = "icon"

    def _do_pick_icon(self, icon, button):
        self.d["icon"] = list(icon)
        self.mode = "main"

    def _do_field(self, key, button):
        d = self.d
        label, _, how, _ = next(f for f in fields_for(d["kind"]) if f[1] == key)
        if how == "text":
            raw = self.ask("Name:", d["name"])
            if raw and raw.strip():
                d["name"] = raw.strip()[:item_defs.MAX_NAME]
        elif how == "cycle":
            self._cycle(key)
        else:
            self._edit_number(key, label, how)

    def _cycle(self, key):
        d = self.d
        if key == "kind":
            kinds = item_defs.KINDS
            new = kinds[(kinds.index(d["kind"]) + 1) % len(kinds)]
            keep = {k: d[k] for k in ("name", "icon", "price", "description", "art") if k in d}
            d.clear()
            d.update(item_defs.new_definition(keep.pop("name"), new))
            d.update(keep)
        elif key == "hands":
            d["hands"] = "2h" if d.get("hands") == "1h" else "1h"
        elif key == "weapon_type":
            opts = self.types()
            cur = opts.index(d["weapon_type"]) if d.get("weapon_type") in opts else -1
            d["weapon_type"] = opts[(cur + 1) % len(opts)]
            d.pop("art", None)                           # (the picture follows the type again)

    def _edit_number(self, key, label, how):
        d = self.d
        if key.startswith("buff."):
            sub = key[5:]
            cur = d.get("buff", {}).get(sub, 0)
            raw = self.ask(f"{label} (percent, empty = none):", f"{cur * 100:g}" if cur else "")
        elif how == "minutes":
            cur = d.get("buff_duration", 600) / 60
            raw = self.ask(f"{label} (1-1440):", f"{cur:g}")
        elif how == "pct":
            cur = d.get(key, 0)
            raw = self.ask(f"{label} (percent):", f"{cur * 100:g}")
        else:
            cur = d.get(key, "")
            lo, hi = LIMITS[key]
            raw = self.ask(f"{label} ({lo:g}-{hi:g}{', empty = none' if how == 'optint' else ''}):", f"{cur:g}" if cur != "" else "")
        if raw is None:
            return
        raw = raw.strip()
        if not raw:
            if how == "optint" or key.startswith("buff."):
                self._set(key, None)
                return
            self._say("Type a number", False)
            return
        try:
            v = float(raw)
        except ValueError:
            self._say(f"Not a number: {raw}", False)
            return
        if how == "optint":
            v = int(v)
        elif how == "pct":
            v = v / 100
        elif how == "minutes":
            if not 1 <= v <= 1440:
                self._say("Minutes must be 1-1440", False)
                return
            d["buff_duration"] = v * 60
            return
        if key.startswith("buff."):
            if not 0 < v <= 10:
                self._say("Percent must be above 0 and at most 1000", False)
                return
            self._set(key, v)
            return
        lo, hi = LIMITS.get(key, (0, 0.9 if key == "block" else 100000))
        if not lo <= v <= hi:
            self._say(f"{label} must be {lo:g}-{hi:g}" if key in LIMITS else f"{label} out of range", False)
            return
        self._set(key, v)

    def _set(self, key, v):
        d = self.d
        if key.startswith("buff."):
            buff = d.setdefault("buff", {})
            if v is None:
                buff.pop(key[5:], None)
            else:
                buff[key[5:]] = v
            if not buff:
                d.pop("buff", None)
                d.pop("buff_duration", None)
            else:
                d.setdefault("buff_duration", 600.0)
        elif v is None or (key in ("heal", "mana") and v == 0):
            d.pop(key, None)
        else:
            d[key] = v

    def _do_description(self, _, button):
        raw = self.ask("Description (tooltip text):", self.d.get("description", ""), True)
        if raw is None:
            return
        if raw.strip():
            self.d["description"] = raw.strip()[:300]
        else:
            self.d.pop("description", None)

    def _do_done(self, _, button):
        errs = self.errors()
        if errs:
            self._say(errs[0], False)
            return
        item_defs.save(self.defs, self.path)
        self.done = True

    # --- drawing ---
    def draw(self, surf, font, big):
        self.hits, self.help = [], ""
        W, H = surf.get_size()
        surf.fill(BG)
        self._draw_list(surf, font, big, H)
        x0 = LIST_W + 30
        if self.d is None:
            surf.blit(big.render("No item selected - click \"+ New item\"", True, DIM), (x0, 40))
        elif self.mode == "icon":
            self._draw_icon_picker(surf, font, big, x0)
        else:
            self._draw_details(surf, font, big, x0, W, H)
        if self.help:
            surf.blit(font.render(self.help, True, DIM), (x0, H - 62))
        if self.message:
            surf.blit(font.render(self.message, True, GREEN if self.message_ok else RED), (x0, H - 44))
        self._button(surf, big, (W - 170, H - 46, 150, 32), "Done (save)", "done", color=(60, 100, 60))
        surf.blit(font.render("Esc = discard all changes made in this screen", True, DIM), (x0, H - 24))

    def _draw_list(self, surf, font, big, H):
        pygame.draw.rect(surf, PANEL, (0, 0, LIST_W, H))
        surf.blit(big.render("Items", True, GOLD), (12, 10))
        half = (LIST_W - 30) // 2
        self._button(surf, font, (12, 40, LIST_W - 24, 26), "+ New item", "new", color=(60, 90, 60))
        self._button(surf, font, (12, 70, half, 26), "Duplicate", "duplicate")
        self._button(surf, font, (18 + half, 70, half, 26), "Delete", "delete", color=(100, 55, 55))
        self._button(surf, font, (12, 100, LIST_W - 24, 26), f"Showing: {self.kind_filter or 'all kinds'}", "filter",
                     color=(70, 95, 120) if self.kind_filter else (70, 70, 82))
        y0, rows = 136, (H - 146) // ROW
        ids = self.shown()
        self.list_scroll = min(self.list_scroll, max(0, len(ids) - rows))
        for i, iid in enumerate(ids[self.list_scroll:self.list_scroll + rows]):
            y = y0 + i * ROW
            r = pygame.Rect(8, y, LIST_W - 16, ROW - 2)
            if iid == self.selected:
                pygame.draw.rect(surf, (70, 90, 70), r, border_radius=3)
            d = self.defs[iid]
            icon = d.get("icon") or ["dungeon", 0, 0]
            if icon[0] in item_defs.SHEET_SIZES:
                surf.blit(self.art.icon(icon[0], icon[1], icon[2], 20), (14, y + 2))
            surf.blit(font.render(f"{d.get('name', '?')} #{iid}"[:30], True, TEXT), (40, y + 5))
            self._hit(r, "select", iid)
        if len(ids) > rows:
            self._button(surf, font, (LIST_W - 60, 10, 22, 22), "^", "scroll", -5)
            self._button(surf, font, (LIST_W - 34, 10, 22, 22), "v", "scroll", 5)

    def _value_text(self, d, key, how):
        if key.startswith("buff."):
            v = d.get("buff", {}).get(key[5:])
            return f"+{v * 100:g}%" if v else "none"
        if how == "minutes":
            return f"{d.get('buff_duration', 600) / 60:g} min"
        if how == "pct":
            return f"+{d.get(key, 0) * 100:g}%"
        v = d.get(key)
        return "none" if v is None else (f"{v:g}" if isinstance(v, (int, float)) else str(v))

    def _draw_details(self, surf, font, big, x, W, H):
        d = self.d
        surf.blit(big.render(d["name"], True, GOLD), (x, 10))
        surf.blit(font.render(f"id #{self.selected}   (permanent: backpacks, drops, quests and spawns use it)",
                              True, DIM), (x, 38))
        pic = pygame.Rect(W - 150, 12, 128, 128)
        pygame.draw.rect(surf, PANEL, pic, border_radius=6)
        icon = d.get("icon") or ["dungeon", 0, 0]
        if icon[0] in item_defs.SHEET_SIZES:
            surf.blit(self.art.icon(icon[0], icon[1], icon[2], 112), (pic.x + 8, pic.y + 8))
        self._button(surf, font, (pic.x, pic.bottom + 6, pic.w, 24), "Change picture", "icon")
        y = 66
        for label, key, how, help_text in fields_for(d["kind"]):
            surf.blit(font.render(label, True, DIM), (x, y + 6))
            text = d["kind"] if key == "kind" else (d["name"] if key == "name" else self._value_text(d, key, how))
            self._box(surf, font, (x + 150, y, 260, 26), text, "field", key, False, help_text)
            y += 32
        surf.blit(font.render("Description", True, DIM), (x, y + 6))
        self._box(surf, font, (x + 150, y, W - x - 150 - 180, 26), (d.get("description") or "(none)")[:90],
                  "description", None, False, "Extra tooltip text. For a misc item it is the whole tooltip.")

    def _draw_icon_picker(self, surf, font, big, x):
        surf.blit(big.render(f"Pick a picture for {self.d['name']} (click a tile)", True, GOLD), (x, 10))
        cur = self.d.get("icon")
        oy = 44
        for sheet, size, gap in (("rpg", 17, 1), ("dungeon", 30, 2)):
            cols, rows = item_defs.SHEET_SIZES[sheet]
            surf.blit(font.render({"rpg": "Roguelike items", "dungeon": "Dungeon items and gear"}[sheet], True, DIM),
                      (x, oy))
            oy += 20
            for r in range(rows):
                for c in range(cols):
                    rect = pygame.Rect(x + c * (size + gap), oy + r * (size + gap), size, size)
                    pygame.draw.rect(surf, PANEL, rect)
                    surf.blit(self.art.icon(sheet, c, r, size), rect.topleft)
                    if cur == [sheet, c, r]:
                        pygame.draw.rect(surf, GOLD, rect.inflate(2, 2), 2)
                    self._hit(rect, "pick_icon", (sheet, c, r))
            oy += rows * (size + gap) + 14


def run(screen, clock, defs, ask, art, usage=lambda iid: [], path=item_defs.PATH):
    """The Items screen as a modal loop (the map editor's I key). Works on copies: Done saves `path` and copies the edits
    back into `defs` (returns True); Esc drops them (False)."""
    font = pygame.font.SysFont("monospace", 13)
    big = pygame.font.SysFont("monospace", 18, bold=True)
    panel = ItemPanel(copy.deepcopy(defs), ask, art, usage, path)
    while not panel.done:
        for event in pygame.event.get():
            if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
                if panel.mode != "main":
                    panel.mode = "main"
                    continue
                return False
            if event.type == pygame.MOUSEBUTTONDOWN and event.button in (1, 3):
                panel.click(event.pos, event.button)
            if event.type == pygame.MOUSEWHEEL and pygame.mouse.get_pos()[0] < LIST_W:
                panel.list_scroll = max(0, panel.list_scroll - event.y * 3)
        panel.draw(screen, font, big)
        pygame.display.flip()
        clock.tick(30)
    defs.take(panel.defs)
    return True
