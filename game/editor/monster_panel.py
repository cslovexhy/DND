"""The map editor's Monsters screen (press M): make new monster types and set the stats that need your input.

  left    every monster type; built-in ones (game/content/monsters.py) are read-only except their level range here
  right   the selected type: name, picture (pick any tile of the creature / dungeon sheets), category, melee or ranged,
          boss / unique, armor, speed, HP multiplier, its LEVEL RANGE ON THIS MAP, the skills it casts and its drops
          (item, chance, optional monster-level range)

Custom types are saved to data/custom_monsters.json (content/monster_defs.py) when you press Done; level ranges are
part of the map (its "monster_levels"), saved with the map (Ctrl+S).

Everything is driven by `click(pos, button)` and `draw(surface)`; text input goes through the `ask(title, default)`
callback the editor passes in, so tests can drive the panel without a real window.
"""
import json

import pygame

from game.content import monster_defs
from game.content.items import ITEMS
from game.content.monster_art import ART, SHEETS, SHEET_SIZE
from game.content.monsters import BUILTIN_TYPES, SPAWN_STATS, MONSTER_CATEGORY, MONSTER_DROPS

CATEGORY_COLORS = {"humanoid": (200, 150, 90), "beast": (110, 170, 80), "demon": (190, 70, 90)}
BG, PANEL, LINE, TEXT, DIM, GOLD, RED, GREEN = ((25, 25, 30), (45, 45, 52), (90, 90, 100), (225, 225, 225),
                                               (140, 140, 150), (255, 210, 90), (255, 110, 110), (120, 220, 130))


def castable_skills():
    """Skills a monster brain can use (engine/casting.py AI_CASTABLE), in a stable order."""
    from game.engine.casting import AI_CASTABLE
    return sorted(AI_CASTABLE)


class Art:
    """Tile images for pictures and item icons (16 px tiles, scaled on demand, cached)."""

    def __init__(self):
        self.sheets = {k: pygame.image.load(p).convert_alpha() for k, p in SHEETS.items()}
        self.item_sheets = {"dungeon": pygame.image.load("assets/kenney_dungeon/Tilemap/tilemap.png").convert_alpha(),
                            "rpg": pygame.image.load(
                                "assets/kenney_rpg/Spritesheet/roguelikeSheet_transparent.png").convert_alpha()}
        self.cache = {}

    def monster(self, art, size):
        key = ("m", json.dumps(art, sort_keys=True), size)
        if key not in self.cache:
            if art is None:
                s = pygame.Surface((size, size), pygame.SRCALPHA)
                pygame.draw.circle(s, DIM, (size // 2, size // 2), size // 3)
            elif "file" in art:
                s = pygame.transform.scale(pygame.image.load(art["file"]).convert_alpha(), (size, size))
            else:
                raw = self.sheets[art["sheet"]].subsurface((art["col"] * 16, art["row"] * 16, 16, 16))
                s = pygame.transform.scale(raw, (size, size))
            self.cache[key] = s
        return self.cache[key]

    def item(self, item, size):
        key = ("i", item, size)
        if key not in self.cache:
            sheet, col, row = ITEMS[item]["icon"]
            raw = pygame.Surface((16, 16), pygame.SRCALPHA)
            raw.blit(self.item_sheets[sheet], (0, 0), (col * 17, row * 17, 16, 16))
            self.cache[key] = pygame.transform.scale(raw, (size, size))
        return self.cache[key]


def spawn_palette(custom_defs):
    """The editor's spawn palette: every built-in type plus the custom ones, with name, colour and picture."""
    out = []
    for tid in sorted(BUILTIN_TYPES, key=lambda t: (SPAWN_STATS[t].get("boss", False), SPAWN_STATS[t]["name"])):
        s = SPAWN_STATS[tid]
        tag = " (Boss)" if s.get("boss") else (" (Unique)" if s.get("unique") else "")
        out.append({"id": tid, "name": s["name"] + tag, "color": CATEGORY_COLORS[MONSTER_CATEGORY[tid]],
                    "art": ART.get(tid)})
    for tid, d in sorted(custom_defs.items(), key=lambda kv: kv[1].get("name", "")):
        tag = " (Boss)" if d.get("boss") else ""
        out.append({"id": tid, "name": f"{d.get('name', tid)}{tag} *", "custom": True,
                    "color": CATEGORY_COLORS.get(d.get("category"), (200, 200, 200)), "art": d.get("sprite")})
    return out


class MonsterPanel:
    LIST_W = 300
    ROW = 26

    def __init__(self, custom_defs, monster_levels, ask, art=None, path=monster_defs.CUSTOM_PATH):
        """custom_defs: {type_id: definition} (edited in place); monster_levels: the map's {type_id: [min, max]}
        (edited in place); ask(title, default) -> str or None: a text prompt."""
        self.defs = custom_defs
        self.levels = monster_levels
        self.ask = ask
        self.art = art or Art()
        self.path = path
        self.selected = next(iter(sorted(custom_defs)), None) or "kobold_dragonshield"
        self.mode = "main"            # "main" / "sprite" (picture picker) / "item" (drop picker)
        self.message, self.message_ok = "", True
        self.hits = []                # [(rect, action, arg)] from the last draw
        self.done = False
        self.list_scroll = 0
        self.skills = castable_skills()

    # --- data helpers ---
    def types(self):
        return [tid for tid in sorted(BUILTIN_TYPES, key=lambda t: SPAWN_STATS[t]["name"])] + sorted(
            self.defs, key=lambda t: self.defs[t].get("name", t))

    def is_custom(self, tid=None):
        return (tid or self.selected) in self.defs

    def errors(self):
        from game.content.skill_library import SKILLS
        out = []
        for tid, d in self.defs.items():
            for e in monster_defs.validate(tid, d, SKILLS, ITEMS, BUILTIN_TYPES):
                out.append(f"{d.get('name', tid)}: {e}")
        return out

    def _say(self, text, ok=True):
        self.message, self.message_ok = text, ok

    def _ask_number(self, title, default, lo, hi, kind=float):
        raw = self.ask(f"{title} ({lo}-{hi}):", str(default))
        if raw is None:
            return None
        try:
            v = kind(raw)
        except ValueError:
            self._say(f"Not a number: {raw}", False)
            return None
        if not lo <= v <= hi:
            self._say(f"{title} must be {lo}-{hi}", False)
            return None
        return v

    @staticmethod
    def parse_levels(raw):
        """"3-5" / "4" -> [3, 5] / [4, 4]; "" -> None (no range); raises ValueError otherwise."""
        raw = raw.strip()
        if not raw:
            return None
        parts = [int(p) for p in raw.replace(" ", "").split("-")]
        if len(parts) == 1:
            parts *= 2
        if len(parts) != 2 or not 1 <= parts[0] <= parts[1] <= 30:
            raise ValueError(raw)
        return parts

    # --- actions ---
    def click(self, pos, button=1):
        hit = next(((a, arg) for r, a, arg in self.hits if r.collidepoint(pos)), None)
        if hit is None:
            if self.mode != "main":
                self.mode = "main"        # clicked outside a picker: close it
            return
        action, arg = hit
        getattr(self, f"_do_{action}")(arg, button)

    def _do_select(self, tid, button):
        self.selected, self.mode = tid, "main"
        self._say("")

    def _do_new(self, _, button):
        name = self.ask("New monster name:", "")
        if not name:
            return
        tid = monster_defs.type_id_for(name, set(SPAWN_STATS) | set(self.defs))
        self.defs[tid] = monster_defs.new_definition(name.strip()[:monster_defs.MAX_NAME])
        self.selected = tid
        self.mode = "sprite"          # pick its picture straight away
        self._say(f"Created {name}. Pick a picture.")

    def _do_delete(self, _, button):
        if not self.is_custom():
            return
        name = self.defs[self.selected]["name"]
        del self.defs[self.selected]
        self.levels.pop(self.selected, None)
        self.selected = next(iter(sorted(self.defs)), None) or "kobold_dragonshield"
        self._say(f"Deleted {name} (save the map to drop its spawn points too)")

    def _do_name(self, _, button):
        name = self.ask("Name:", self.defs[self.selected]["name"])
        if name and name.strip():
            self.defs[self.selected]["name"] = name.strip()[:monster_defs.MAX_NAME]

    def _do_picture(self, _, button):
        self.mode = "sprite"

    def _do_pick_sprite(self, art, button):
        self.defs[self.selected]["sprite"] = dict(art)
        self.mode = "main"
        self._say("")

    def _do_cycle(self, key, button):
        d = self.defs[self.selected]
        options = {"category": monster_defs.CATEGORIES, "attack": monster_defs.ATTACKS}[key]
        cur = d.get(key, monster_defs.DEFAULTS[key])
        d[key] = options[(options.index(cur) + 1) % len(options)]

    def _do_toggle(self, key, button):
        d = self.defs[self.selected]
        d[key] = not d.get(key, False)

    def _do_number(self, key, button):
        d = self.defs[self.selected]
        lo, hi = monster_defs.LIMITS[key]
        kind = float if key == "hp_mult" else int
        v = self._ask_number({"ac": "Armor (AC)", "speed": "Speed", "hp_mult": "HP multiplier"}[key],
                             d.get(key, monster_defs.DEFAULTS[key]), lo, hi, kind)
        if v is not None:
            d[key] = v

    def _do_levels(self, _, button):
        cur = self.levels.get(self.selected)
        raw = self.ask("Level range on this map, e.g. 3-5 (empty = none):", f"{cur[0]}-{cur[1]}" if cur else "")
        if raw is None:
            return
        try:
            rng = self.parse_levels(raw)
        except ValueError:
            self._say(f"Levels must look like 3-5 (1-30): {raw}", False)
            return
        if rng is None:
            self.levels.pop(self.selected, None)
        else:
            self.levels[self.selected] = rng

    def _do_skill(self, name, button):
        skills = self.defs[self.selected].setdefault("skills", [])
        if name in skills:
            skills.remove(name)
        else:
            skills.append(name)

    def _do_add_drop(self, _, button):
        self.mode = "item"

    def _do_pick_item(self, item, button):
        drops = self.defs[self.selected].setdefault("drops", [])
        if any(e[0] == item for e in drops):
            self._say(f"{ITEMS[item]['name']} is already in the drops", False)
        else:
            drops.append([item, 0.01])
        self.mode = "main"

    def _do_drop_chance(self, i, button):
        drops = self.defs[self.selected]["drops"]
        if button == 3:
            del drops[i]
            return
        v = self._ask_number(f"{ITEMS[drops[i][0]]['name']} drop chance %", round(drops[i][1] * 100, 3),
                             0.01, 100.0)
        if v is not None:
            drops[i][1] = round(v / 100, 6)

    def _do_drop_levels(self, i, button):
        e = self.defs[self.selected]["drops"][i]
        cur = f"{e[2]}-{e[3]}" if len(e) == 4 else ""
        raw = self.ask("Drops only from monster levels, e.g. 10-20 (empty = any level):", cur)
        if raw is None:
            return
        try:
            rng = self.parse_levels(raw)
        except ValueError:
            self._say(f"Levels must look like 10-20 (1-30): {raw}", False)
            return
        del e[2:]
        if rng:
            e.extend(rng)

    def _do_done(self, _, button):
        errs = self.errors()
        if errs:
            self._say(errs[0], False)
            return
        monster_defs.save(self.defs, self.path)
        self.done = True

    def _do_scroll(self, delta, button):
        self.list_scroll = max(0, self.list_scroll + delta)

    # --- drawing ---
    def _hit(self, rect, action, arg=None):
        self.hits.append((pygame.Rect(rect), action, arg))

    def _button(self, surf, font, rect, label, action, arg=None, color=(70, 70, 82), text=TEXT):
        rect = pygame.Rect(rect)
        hover = rect.collidepoint(pygame.mouse.get_pos())
        pygame.draw.rect(surf, tuple(min(255, c + 20) for c in color) if hover else color, rect, border_radius=4)
        pygame.draw.rect(surf, LINE, rect, 1, border_radius=4)
        t = font.render(label, True, text)
        surf.blit(t, (rect.centerx - t.get_width() // 2, rect.centery - t.get_height() // 2))
        self._hit(rect, action, arg)

    def draw(self, surf, font, big):
        self.hits = []
        W, H = surf.get_size()
        surf.fill(BG)
        self._draw_list(surf, font, big, H)
        x0 = self.LIST_W + 30
        if self.mode == "sprite":
            self._draw_sprite_picker(surf, font, big, x0)
        elif self.mode == "item":
            self._draw_item_picker(surf, font, big, x0, W)
        else:
            self._draw_details(surf, font, big, x0, W, H)
        if self.message:
            surf.blit(font.render(self.message, True, GREEN if self.message_ok else RED), (x0, H - 64))
        self._button(surf, big, (W - 170, H - 46, 150, 32), "Done (save)", "done", color=(60, 100, 60))
        surf.blit(font.render("Esc = close without saving custom types", True, DIM), (x0, H - 36))

    def _draw_list(self, surf, font, big, H):
        pygame.draw.rect(surf, PANEL, (0, 0, self.LIST_W, H))
        surf.blit(big.render("Monster types", True, GOLD), (12, 10))
        self._button(surf, font, (12, 40, self.LIST_W - 24, 28), "+ New monster type", "new", color=(60, 90, 60))
        y0, rows = 80, (H - 90) // self.ROW
        types = self.types()
        self.list_scroll = min(self.list_scroll, max(0, len(types) - rows))
        for i, tid in enumerate(types[self.list_scroll:self.list_scroll + rows]):
            y = y0 + i * self.ROW
            r = pygame.Rect(8, y, self.LIST_W - 16, self.ROW - 2)
            if tid == self.selected:
                pygame.draw.rect(surf, (70, 90, 70), r, border_radius=3)
            custom = self.is_custom(tid)
            stats = SPAWN_STATS.get(tid, {})
            art = self.defs[tid].get("sprite") if custom else ART.get(tid)
            surf.blit(self.art.monster(art, 20), (14, y + 2))
            name = self.defs[tid].get("name", tid) if custom else stats["name"]
            lv = self.levels.get(tid)
            label = f"{name}" + (f"  L{lv[0]}-{lv[1]}" if lv else "")
            surf.blit(font.render(label, True, TEXT if custom else DIM), (40, y + 5))
            if custom:
                surf.blit(font.render("custom", True, GOLD), (r.right - 52, y + 5))
            self._hit(r, "select", tid)
        if len(types) > rows:
            self._button(surf, font, (self.LIST_W - 60, 10, 22, 22), "^", "scroll", -5)
            self._button(surf, font, (self.LIST_W - 34, 10, 22, 22), "v", "scroll", 5)

    def _row(self, surf, font, x, y, label, value, action=None, arg=None, note=""):
        surf.blit(font.render(label, True, DIM), (x, y + 6))
        r = pygame.Rect(x + 170, y, 260, 26)
        if action:
            hover = r.collidepoint(pygame.mouse.get_pos())
            pygame.draw.rect(surf, (62, 62, 74) if hover else (52, 52, 62), r, border_radius=4)
            pygame.draw.rect(surf, LINE, r, 1, border_radius=4)
            self._hit(r, action, arg)
        surf.blit(font.render(str(value), True, TEXT), (r.x + 8, y + 6))
        if note:
            surf.blit(font.render(note, True, DIM), (r.right + 10, y + 6))

    def _draw_details(self, surf, font, big, x, W, H):
        tid = self.selected
        custom = self.is_custom()
        d = self.defs[tid] if custom else None
        s = SPAWN_STATS.get(tid, {})
        name = d["name"] if custom else s.get("name", tid)
        surf.blit(big.render(name, True, GOLD), (x, 10))
        sub = f"id: {tid}" + ("" if custom else "   (built-in: only its level range on this map can be set here)")
        surf.blit(font.render(sub, True, DIM), (x, 40))
        art = d["sprite"] if custom else ART.get(tid)
        pic = pygame.Rect(W - 150, 12, 128, 128)
        pygame.draw.rect(surf, PANEL, pic, border_radius=6)
        surf.blit(self.art.monster(art, 112), (pic.x + 8, pic.y + 8))
        if custom:
            self._button(surf, font, (pic.x, pic.bottom + 6, pic.w, 24), "Change picture", "picture")
        y = 72
        lv = self.levels.get(tid)
        self._row(surf, font, x, y, "Level on this map", f"{lv[0]} - {lv[1]}" if lv else "not set", "levels",
                  note="sets its HP, damage and XP"); y += 32
        if custom:
            self._row(surf, font, x, y, "Name", d["name"], "name"); y += 32
            self._row(surf, font, x, y, "Category", d.get("category", "humanoid"), "cycle", "category",
                      note="humanoids carry money"); y += 32
            self._row(surf, font, x, y, "Attack", d.get("attack", "melee"), "cycle", "attack"); y += 32
            self._row(surf, font, x, y, "Boss", "yes" if d.get("boss") else "no", "toggle", "boss",
                      note="boss AI, 1.5x size, CC immune"); y += 32
            self._row(surf, font, x, y, "Unique", "yes" if d.get("unique") else "no", "toggle", "unique"); y += 32
            self._row(surf, font, x, y, "Armor (AC)", d.get("ac", 14), "number", "ac"); y += 32
            self._row(surf, font, x, y, "Speed", d.get("speed", 5), "number", "speed",
                      note=f"{d.get('speed', 5) * 15} px/s (hero: 75-90)"); y += 32
            self._row(surf, font, x, y, "HP multiplier", d.get("hp_mult", 1.0), "number", "hp_mult"); y += 32
            skills, drops = d.get("skills", []), d.get("drops", [])
        else:
            for label, value in (("Category", MONSTER_CATEGORY.get(tid)),
                                 ("Attack", "ranged" if s.get("ranged") else "melee"),
                                 ("Boss", "yes" if s.get("boss") else "no"), ("Armor (AC)", s.get("ac")),
                                 ("Speed", s.get("speed"))):
                self._row(surf, font, x, y, label, value); y += 32
            skills, drops = s.get("kit", []), [list(e) for e in MONSTER_DROPS.get(tid, [])]
        # skills
        y += 6
        surf.blit(big.render("Skills it casts", True, GOLD), (x, y)); y += 28
        cols = 3
        for i, sk in enumerate(self.skills if custom else (skills or ["(none)"])):
            cx, cy = x + (i % cols) * 190, y + (i // cols) * 26
            on = sk in skills
            r = pygame.Rect(cx, cy, 180, 22)
            if custom:
                pygame.draw.rect(surf, (60, 95, 60) if on else (52, 52, 62), r, border_radius=4)
                pygame.draw.rect(surf, LINE, r, 1, border_radius=4)
                self._hit(r, "skill", sk)
                surf.blit(font.render(("[x] " if on else "[ ] ") + sk, True, TEXT), (r.x + 6, r.y + 4))
            else:
                surf.blit(font.render(sk, True, TEXT), (r.x, r.y + 4))
        n = len(self.skills) if custom else max(1, len(skills))
        y += ((n + cols - 1) // cols) * 26 + 10
        # drops
        surf.blit(big.render("Drops", True, GOLD), (x, y))
        if custom:
            self._button(surf, font, (x + 90, y, 110, 24), "+ Add drop", "add_drop", color=(60, 90, 60))
            surf.blit(font.render("click % to change, right-click to remove", True, DIM), (x + 214, y + 5))
        y += 30
        for i, e in enumerate(drops):
            if y > H - 90:
                surf.blit(font.render(f"... {len(drops) - i} more", True, DIM), (x, y))
                break
            surf.blit(self.art.item(e[0], 20), (x, y + 2))
            surf.blit(font.render(ITEMS[e[0]]["name"], True, TEXT), (x + 28, y + 5))
            chance = pygame.Rect(x + 220, y, 90, 24)
            lvl = pygame.Rect(x + 320, y, 150, 24)
            for r, label, act in ((chance, f"{e[1] * 100:g}%", "drop_chance"),
                                  (lvl, f"levels {e[2]}-{e[3]}" if len(e) == 4 else "any level", "drop_levels")):
                if custom:
                    pygame.draw.rect(surf, (52, 52, 62), r, border_radius=4)
                    pygame.draw.rect(surf, LINE, r, 1, border_radius=4)
                    self._hit(r, act, i)
                surf.blit(font.render(label, True, TEXT), (r.x + 6, r.y + 5))
            y += 28
        if not drops:
            surf.blit(font.render("(drops nothing)", True, DIM), (x, y))
        if custom:
            self._button(surf, font, (W - 170, H - 86, 150, 30), "Delete type", "delete", color=(110, 50, 50))

    def _draw_sprite_picker(self, surf, font, big, x):
        surf.blit(big.render("Pick a picture (click a tile)", True, GOLD), (x, 10))
        cur = self.defs[self.selected].get("sprite", {})
        size, gap = 32, 2
        ox = x
        for sheet in ("creatures", "dungeon"):
            cols, rows = SHEET_SIZE[sheet]
            surf.blit(font.render({"creatures": "Tiny Creatures", "dungeon": "Dungeon characters & items"}[sheet],
                                  True, DIM), (ox, 40))
            for r in range(rows):
                for c in range(cols):
                    art = {"sheet": sheet, "col": c, "row": r}
                    rect = pygame.Rect(ox + c * (size + gap), 60 + r * (size + gap), size, size)
                    pygame.draw.rect(surf, PANEL, rect)
                    surf.blit(self.art.monster(art, size), rect.topleft)
                    if cur.get("sheet") == sheet and cur.get("col") == c and cur.get("row") == r:
                        pygame.draw.rect(surf, GOLD, rect.inflate(2, 2), 2)
                    self._hit(rect, "pick_sprite", art)
            ox += cols * (size + gap) + 30

    def _draw_item_picker(self, surf, font, big, x, W):
        surf.blit(big.render("Add a drop (click an item)", True, GOLD), (x, 10))
        y = 44
        per_row = max(1, (W - x - 20) // 150)
        for kind in ("potion", "food", "drink", "weapon", "shield"):
            items = [k for k, it in ITEMS.items() if it["kind"] == kind]
            surf.blit(font.render(kind.title() + "s", True, DIM), (x, y))
            y += 18
            for i, item in enumerate(items):
                rect = pygame.Rect(x + (i % per_row) * 150, y + (i // per_row) * 36, 144, 30)
                pygame.draw.rect(surf, PANEL, rect, border_radius=4)
                surf.blit(self.art.item(item, 24), (rect.x + 4, rect.y + 3))
                surf.blit(font.render(ITEMS[item]["name"][:14], True, TEXT), (rect.x + 32, rect.y + 8))
                self._hit(rect, "pick_item", item)
            y += ((len(items) + per_row - 1) // per_row) * 36 + 6


def run(screen, clock, custom_defs, monster_levels, ask, path=monster_defs.CUSTOM_PATH):
    """The Monsters screen as a modal loop (the map editor's M key). Works on copies: Done saves the custom types to
    `path` and copies the edits back into `custom_defs` / `monster_levels` (returns True); Esc drops them (False)."""
    import copy
    font = pygame.font.SysFont("monospace", 13)
    big = pygame.font.SysFont("monospace", 18, bold=True)
    panel = MonsterPanel(copy.deepcopy(custom_defs), copy.deepcopy(monster_levels), ask, path=path)
    while not panel.done:
        for event in pygame.event.get():
            if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
                if panel.mode != "main":
                    panel.mode = "main"
                    continue
                return False
            if event.type == pygame.MOUSEBUTTONDOWN and event.button in (1, 3):
                panel.click(event.pos, event.button)
            if event.type == pygame.MOUSEWHEEL and pygame.mouse.get_pos()[0] < panel.LIST_W:
                panel.list_scroll = max(0, panel.list_scroll - event.y * 3)
        panel.draw(screen, font, big)
        pygame.display.flip()
        clock.tick(30)
    custom_defs.clear()
    custom_defs.update(panel.defs)
    monster_levels.clear()
    monster_levels.update(panel.levels)
    return True
