"""The map editor's Monsters screen (press M): create, edit, duplicate and delete every monster type.

All monsters live in data/monsters.json (content/monster_defs.py) and are edited here the same way:
  left    every monster type (button: only the ones on the map you are editing), "+ New", "Duplicate", "Delete"
  right   the selected type: name, picture (any tile of the creature / dungeon sheets), category, melee or ranged,
          boss / unique / relentless, armor, speed, HP multiplier, sense and attack range, attack speed, respawn,
          LEVEL RANGE (sets its HP / damage / XP; empty = the raw numbers), raw HP / damage / XP, hive mind,
          boss skills, the skills it casts, and its drops
  drops   every monster has its own handpicked list (item, chance, optional monster-level range); nothing is
          shared. "Drops table" shows every monster x every item at once and edits a chance with one click.

Every monster has a permanent numeric id (the maps and quests refer to it); only its name can change. Done saves
data/monsters.json; Esc discards everything done in this screen.

Everything is driven by click(pos, button) and draw(surface, font, big); text input goes through the ask(title,
default) callback the editor passes in, so tests can drive the panel without a real window.
"""
import copy
import json

import pygame

from game.content import monster_defs
from game.content.items import ITEMS
from game.content.monster_art import SHEETS, SHEET_SIZE

CATEGORY_COLORS = {"humanoid": (200, 150, 90), "beast": (110, 170, 80), "demon": (190, 70, 90)}
BG, PANEL, LINE, TEXT, DIM, GOLD, RED, GREEN = ((25, 25, 30), (45, 45, 52), (90, 90, 100), (225, 225, 225),
                                               (140, 140, 150), (255, 210, 90), (255, 110, 110), (120, 220, 130))

# (label, key, kind, help). kinds: levels / text / cycle / toggle / flag-on-sprite / number
FIELDS = [
    ("Level", "level", "levels", "Level range, e.g. 3-5: sets its HP, damage and XP. Empty = use the raw numbers."),
    ("Name", "name", "text", "Shown over the monster."),
    ("Category", "category", "cycle", "Humanoids carry money (bronze) when killed."),
    ("Attack", "attack", "cycle", "Ranged monsters keep their distance and shoot."),
    ("Boss", "boss", "toggle", "Boss AI (hate rules), immune to slow and freeze, long respawn."),
    ("Unique", "unique", "toggle", "One of a kind: its name is shown."),
    ("Relentless", "relentless", "toggle", "Never gives up the chase."),
    ("Stealthy", "stealthy", "toggle", "Invisible to heroes until close (the Demogorgon trick)."),
    ("Big picture", "big", "bigflag", "Draw the picture 1.5x bigger (bosses and uniques)."),
    ("Armor (AC)", "ac", "number", "Reduces damage taken: (AC-10) / (AC-10+12)."),
    ("Speed", "speed", "number", "Board units: 5 = 75 px/s (heroes 75-90)."),
    ("HP multiplier", "hp_mult", "number", "Max HP x this (after the level sets the base)."),
    ("Sense range", "sense_range", "number", "px: how far it notices heroes."),
    ("Attack range", "attack_range", "number", "px it fights from. Empty = 50 melee / 220 ranged."),
    ("Attack speed", "swing", "number", "Seconds between attacks. Empty = 2.0 (bosses 20% faster)."),
    ("Respawn x", "respawn_mult", "number", "x 60 s. Empty = 1 (bosses 10)."),
    ("Raw HP", "hp", "number", "Board-game HP (x50). Only used when no level range is set."),
    ("Raw damage", "dmg", "number", "Board-game damage. Only used when no level range is set."),
    ("Raw XP", "xp", "number", "Kill XP. Only used when no level range is set."),
]
OPTIONAL = {"swing", "respawn_mult", "attack_range"}        # empty = default (the key is removed)
FLOATS = {"hp_mult", "swing", "respawn_mult"}
FIELD_W, COL_W = 118, 330


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


def spawn_palette(defs):
    """The editor's spawn palette: every monster type, with name, colour and picture (bosses and uniques tagged)."""
    out = []
    for tid, d in sorted(defs.items(), key=lambda kv: (kv[1].get("boss", False), kv[1].get("name", kv[0]))):
        tag = " (Boss)" if d.get("boss") else (" (Unique)" if d.get("unique") else "")
        out.append({"id": tid, "name": f"{d.get('name', tid)}{tag}", "art": d.get("sprite"),
                    "color": CATEGORY_COLORS.get(d.get("category"), (200, 200, 200))})
    return out


class MonsterPanel:
    LIST_W = 300
    ROW = 26

    def __init__(self, defs, ask, map_types=lambda: set(), usage=lambda tid: [], art=None,
                 path=monster_defs.PATH):
        """defs: monster_defs.Definitions {id: definition} (edited in place); ask(title, default) -> str or None: a text prompt; map_types() -> the type ids the open map spawns;
        usage(type_id) -> names of the maps that use it (deleting is refused while there are any)."""
        self.defs, self.ask = defs, ask
        self.map_types, self.usage = map_types, usage
        self.art, self.path = art or Art(), path
        self.selected = next(iter(defs), None)
        self.mode = "main"            # "main" / "sprite" (picture picker) / "item" (drop picker) / "matrix"
        self.only_map = False
        self.message, self.message_ok = "", True
        self.hits, self.help = [], ""
        self.done = False
        self.list_scroll = self.drop_scroll = 0
        self.skills = castable_skills()

    # --- data helpers ---
    def shown(self):
        types = sorted(self.defs, key=lambda t: self.defs[t].get("name", t).lower())
        if self.only_map:
            on = set(self.map_types())
            types = [t for t in types if t in on]
        return types

    @property
    def d(self):
        return self.defs.get(self.selected)

    def errors(self):
        from game.content.skill_library import SKILLS
        out = []
        for tid, d in self.defs.items():
            for e in monster_defs.validate(tid, d, SKILLS, ITEMS):
                out.append(f"{d.get('name', tid)}: {e}")
        return out

    def _say(self, text, ok=True):
        self.message, self.message_ok = text, ok

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

    @staticmethod
    def _parse_value(raw, like):
        """A boss-skill setting typed as text: a number, or a comma-separated list of numbers when `like` is one."""
        def num(t):
            v = float(t)
            return int(v) if v == int(v) and "." not in t else v
        if isinstance(like, list):
            return [num(t) for t in raw.replace(" ", "").split(",") if t]
        return num(raw.strip())

    # --- actions ---
    def click(self, pos, button=1):
        hit = next(((a, arg) for r, a, arg in reversed(self.hits) if r.collidepoint(pos)), None)
        if hit is None:
            if self.mode in ("sprite", "item"):
                self.mode = "main"        # clicked outside a picker: close it
            return
        action, arg = hit
        getattr(self, f"_do_{action}")(arg, button)

    def _do_select(self, tid, button):
        self.selected, self.mode, self.drop_scroll = tid, "main", 0
        self._say("")

    def _do_filter(self, _, button):
        self.only_map = not self.only_map
        if self.only_map and self.selected not in self.shown() and self.shown():
            self.selected = self.shown()[0]

    def _do_new(self, _, button):
        name = self.ask("New monster name:", "")
        if not name or not name.strip():
            return
        tid = self.defs.add(monster_defs.new_definition(name.strip()[:monster_defs.MAX_NAME]))
        self.selected, self.mode = tid, "sprite"        # pick its picture straight away
        self._say(f"Created {name.strip()}. Pick a picture.")

    def _do_duplicate(self, _, button):
        if self.d is None:
            return
        name = self.ask("Name of the copy:", f"{self.d['name']} 2")
        if not name or not name.strip():
            return
        tid = self.defs.add(monster_defs.duplicate(self.d, name.strip()[:monster_defs.MAX_NAME]))
        self.selected = tid
        self._say(f"Copied. {name.strip()} has its own copy of the drops: change them in its drop list.")

    def _do_delete(self, _, button):
        if self.d is None:
            return
        maps = self.usage(self.selected)
        if maps:
            self._say(f"{self.d['name']} is used by: {', '.join(maps)}. Remove its spawns there first.",
                      False)
            return
        name = self.d["name"]
        del self.defs[self.selected]
        self.selected = next(iter(self.shown()), None) or next(iter(self.defs), None)
        self._say(f"Deleted {name}")

    def _do_picture(self, _, button):
        self.mode = "sprite"

    def _do_pick_sprite(self, art, button):
        big = bool(self.d["sprite"].get("big"))
        self.d["sprite"] = dict(art, **({"big": True} if big else {}))
        self.mode = "main"
        self._say("")

    def _do_field(self, key, button):
        d = self.d
        label, _, kind, _ = next(f for f in FIELDS if f[1] == key)
        if kind == "levels":
            self._edit_levels(self.selected)
        elif kind == "text":
            name = self.ask("Name:", d["name"])
            if name and name.strip():
                d["name"] = name.strip()[:monster_defs.MAX_NAME]
        elif kind == "cycle":
            options = monster_defs.CATEGORIES if key == "category" else monster_defs.ATTACKS
            cur = d.get(key, monster_defs.DEFAULTS[key])
            d[key] = options[(options.index(cur) + 1) % len(options)]
        elif kind == "toggle":
            d[key] = not d.get(key, False)
            if key == "boss" and d[key]:
                d["sprite"]["big"] = True               # bosses are drawn big (untick "Big picture" to undo)
        elif kind == "bigflag":
            if d["sprite"].get("big"):
                d["sprite"].pop("big")
            else:
                d["sprite"]["big"] = True
        else:
            lo, hi = monster_defs.LIMITS[key]
            cur = d.get(key, monster_defs.DEFAULTS.get(key, ""))
            raw = self.ask(f"{label} ({lo}-{hi}{', empty = default' if key in OPTIONAL else ''}):", str(cur))
            if raw is None:
                return
            if not raw.strip() and key in OPTIONAL:
                d.pop(key, None)
                return
            try:
                v = float(raw) if key in FLOATS else int(float(raw))
            except ValueError:
                self._say(f"Not a number: {raw}", False)
                return
            if not lo <= v <= hi:
                self._say(f"{label} must be {lo}-{hi}", False)
                return
            d[key] = v

    def _edit_levels(self, tid):
        cur = self.defs[tid].get("level")
        raw = self.ask("Level range, e.g. 3-5 (empty = none, use the raw numbers):", f"{cur[0]}-{cur[1]}" if cur else "")
        if raw is None:
            return
        try:
            rng = self.parse_levels(raw)
        except ValueError:
            self._say(f"Levels must look like 3-5 (1-30): {raw}", False)
            return
        if rng is None:
            self.defs[tid].pop("level", None)
        else:
            self.defs[tid]["level"] = rng

    def _do_hive(self, _, button):
        d = self.d
        cur = d.get("hive_mind")
        raw = self.ask("Hive mind range in px (empty = off):", str(cur["range"]) if cur else "")
        if raw is None:
            return
        if not raw.strip():
            d.pop("hive_mind", None)
            return
        types = self.ask("Aggros when any of these monsters is attacked (ids or names, comma separated):",
                         ",".join(str(t) for t in cur["types"]) if cur else str(self.selected))
        if types is None:
            return
        try:
            ids = []
            for t in (t.strip() for t in types.split(",") if t.strip()):
                if t.isdigit():
                    ids.append(int(t))
                    continue
                found = [i for i, m in self.defs.items() if m.get("name", "").lower() == t.lower()]
                if not found:
                    self._say(f"No monster called {t}", False)
                    return
                ids.append(found[0])
            d["hive_mind"] = {"range": float(raw) if "." in raw else int(raw), "types": ids}
        except ValueError:
            self._say(f"Not a number: {raw}", False)

    def _do_boss_skill(self, name, button):
        skills = self.d.setdefault("boss_skills", {})
        if name in skills:
            del skills[name]
        else:
            skills[name] = copy.deepcopy(monster_defs.BOSS_SKILL_DEFAULTS[name])
        if not skills:
            self.d.pop("boss_skills")

    def _do_boss_param(self, arg, button):
        name, key = arg
        cfg = self.d["boss_skills"][name]
        raw = self.ask(f"{name.replace('_', ' ').title()}: {key} (e.g. 0.5,0.2 for a list):",
                       ",".join(str(v) for v in cfg[key]) if isinstance(cfg[key], list) else str(cfg[key]))
        if raw is None:
            return
        try:
            cfg[key] = self._parse_value(raw, cfg[key])
        except ValueError:
            self._say(f"Not a number: {raw}", False)

    def _do_skill(self, name, button):
        skills = self.d.setdefault("skills", [])
        if name in skills:
            skills.remove(name)
        else:
            skills.append(name)

    def _do_add_drop(self, _, button):
        self.mode = "item"

    def _do_pick_item(self, item, button):
        drops = self.d.setdefault("drops", [])
        if any(e[0] == item for e in drops):
            self._say(f"{ITEMS[item]['name']} is already in the drops", False)
        else:
            drops.append([item, 0.01])
            self.drop_scroll = 10 ** 6            # scroll to the new one
        self.mode = "main"

    def _do_drop_chance(self, i, button):
        drops = self.d["drops"]
        if button == 3:
            del drops[i]
            return
        raw = self.ask(f"{ITEMS[drops[i][0]]['name']} drop chance % (0.01-100, empty = remove):",
                       f"{drops[i][1] * 100:g}")
        if raw is None:
            return
        if not raw.strip():
            del drops[i]
            return
        try:
            v = float(raw)
        except ValueError:
            self._say(f"Not a number: {raw}", False)
            return
        if not 0.01 <= v <= 100:
            self._say("Chance must be 0.01-100 %", False)
            return
        drops[i][1] = round(v / 100, 6)

    def _do_drop_remove(self, i, button):
        del self.d["drops"][i]

    def _do_drop_levels(self, i, button):
        e = self.d["drops"][i]
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

    # the "all monsters x all items" table
    def _do_matrix(self, _, button):
        self.mode = "matrix"

    def _do_back(self, _, button):
        self.mode = "main"

    def _do_cell(self, arg, button):
        tid, item = arg
        drops = self.defs[tid].setdefault("drops", [])
        i = next((k for k, e in enumerate(drops) if e[0] == item), None)
        cur = f"{drops[i][1] * 100:g}" if i is not None else ""
        if button == 3:
            if i is not None:
                del drops[i]
            return
        raw = self.ask(f"{self.defs[tid]['name']}: {ITEMS[item]['name']} drop chance % (empty = none):", cur)
        if raw is None:
            return
        if not raw.strip() or raw.strip() in ("0", "0.0"):
            if i is not None:
                del drops[i]
            return
        try:
            v = float(raw)
        except ValueError:
            self._say(f"Not a number: {raw}", False)
            return
        if not 0.01 <= v <= 100:
            self._say("Chance must be 0.01-100 %", False)
            return
        if i is None:
            drops.append([item, round(v / 100, 6)])
        else:
            drops[i][1] = round(v / 100, 6)

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

    def _box(self, surf, font, rect, text, action, arg, active=False, help_text=""):
        rect = pygame.Rect(rect)
        hover = rect.collidepoint(pygame.mouse.get_pos())
        if hover and help_text:
            self.help = help_text
        pygame.draw.rect(surf, (60, 95, 60) if active else ((66, 66, 78) if hover else (52, 52, 62)), rect,
                         border_radius=4)
        pygame.draw.rect(surf, LINE, rect, 1, border_radius=4)
        surf.blit(font.render(str(text), True, TEXT), (rect.x + 6, rect.y + 5))
        self._hit(rect, action, arg)

    def draw(self, surf, font, big):
        self.hits, self.help = [], ""
        W, H = surf.get_size()
        surf.fill(BG)
        self._draw_list(surf, font, big, H)
        x0 = self.LIST_W + 30
        if self.mode == "sprite" and self.d:
            self._draw_sprite_picker(surf, font, big, x0)
        elif self.mode == "item" and self.d:
            self._draw_item_picker(surf, font, big, x0, W)
        elif self.mode == "matrix":
            self._draw_matrix(surf, font, big, x0, W, H)
        elif self.d:
            self._draw_details(surf, font, big, x0, W, H)
        else:
            surf.blit(big.render("No monster selected - click \"+ New monster type\"", True, DIM), (x0, 40))
        if self.help:
            surf.blit(font.render(self.help, True, DIM), (x0, H - 62))
        if self.message:
            surf.blit(font.render(self.message, True, GREEN if self.message_ok else RED), (x0, H - 44))
        self._button(surf, big, (W - 170, H - 46, 150, 32), "Done (save)", "done", color=(60, 100, 60))
        surf.blit(font.render("Esc = discard all changes made in this screen", True, DIM), (x0, H - 24))

    def _draw_list(self, surf, font, big, H):
        pygame.draw.rect(surf, PANEL, (0, 0, self.LIST_W, H))
        surf.blit(big.render("Monster types", True, GOLD), (12, 10))
        self._button(surf, font, (12, 40, self.LIST_W - 24, 26), "+ New monster type", "new", color=(60, 90, 60))
        self._button(surf, font, (12, 70, (self.LIST_W - 30) // 2, 26), "Duplicate", "duplicate")
        self._button(surf, font, (18 + (self.LIST_W - 30) // 2, 70, (self.LIST_W - 30) // 2, 26), "Delete", "delete",
                     color=(100, 55, 55))
        self._button(surf, font, (12, 100, self.LIST_W - 24, 26),
                     "Showing: only this map" if self.only_map else "Showing: all monsters", "filter",
                     color=(70, 95, 120) if self.only_map else (70, 70, 82))
        self._button(surf, font, (12, 130, self.LIST_W - 24, 26), "Drops table (all monsters)", "matrix")
        y0, rows = 166, (H - 176) // self.ROW
        types = self.shown()
        self.list_scroll = min(self.list_scroll, max(0, len(types) - rows))
        on_map = set(self.map_types())
        for i, tid in enumerate(types[self.list_scroll:self.list_scroll + rows]):
            y = y0 + i * self.ROW
            r = pygame.Rect(8, y, self.LIST_W - 16, self.ROW - 2)
            if tid == self.selected and self.mode != "matrix":
                pygame.draw.rect(surf, (70, 90, 70), r, border_radius=3)
            d = self.defs[tid]
            surf.blit(self.art.monster(d.get("sprite"), 20), (14, y + 2))
            lv = d.get("level")
            label = f"{d.get('name', tid)} #{tid}" + (f"  L{lv[0]}-{lv[1]}" if lv else "")
            surf.blit(font.render(label, True, TEXT if tid in on_map else DIM), (40, y + 5))
            self._hit(r, "select", tid)
        if len(types) > rows:
            self._button(surf, font, (self.LIST_W - 60, 10, 22, 22), "^", "scroll", -5)
            self._button(surf, font, (self.LIST_W - 34, 10, 22, 22), "v", "scroll", 5)

    def _draw_details(self, surf, font, big, x, W, H):
        d, tid = self.d, self.selected
        surf.blit(big.render(d["name"], True, GOLD), (x, 10))
        surf.blit(font.render(f"id #{tid}   (bright in the list = on this map)", True, DIM), (x, 38))
        pic = pygame.Rect(W - 150, 12, 128, 128)
        pygame.draw.rect(surf, PANEL, pic, border_radius=6)
        surf.blit(self.art.monster(d.get("sprite"), 112), (pic.x + 8, pic.y + 8))
        self._button(surf, font, (pic.x, pic.bottom + 6, pic.w, 24), "Change picture", "picture")
        # the field grid: 3 columns
        per_col = -(-len(FIELDS) // 3)
        for i, (label, key, kind, help_text) in enumerate(FIELDS):
            fx, fy = x + (i // per_col) * COL_W, 66 + (i % per_col) * 30
            surf.blit(font.render(label, True, DIM), (fx, fy + 6))
            if kind == "levels":
                lv = d.get("level")
                text, active = (f"{lv[0]} - {lv[1]}" if lv else "not set"), bool(lv)
            elif kind == "bigflag":
                text = "yes" if d["sprite"].get("big") else "no"
                active = text == "yes"
            elif kind == "toggle":
                text = "yes" if d.get(key) else "no"
                active = bool(d.get(key))
            elif kind == "number":
                text, active = d.get(key, "default" if key in OPTIONAL else monster_defs.DEFAULTS.get(key, "")), False
            else:
                text, active = d.get(key, monster_defs.DEFAULTS.get(key, "")), False
            self._box(surf, font, (fx + 112, fy, FIELD_W, 26), text, "field", key, active, help_text)
        y = 66 + per_col * 30 + 4
        # hive mind
        hm = d.get("hive_mind")
        surf.blit(font.render("Hive mind", True, DIM), (x, y + 6))
        self._box(surf, font, (x + 112, y, 520, 26),
                  f"{hm['range']} px: {', '.join(self.defs[t]['name'] if t in self.defs else '#' + str(t) for t in hm['types'])}" if hm else "off", "hive", None, bool(hm),
                  "Aggros (with its allies) when any listed type is attacked within this range.")
        y += 34
        # boss skills
        surf.blit(font.render("Boss skills", True, DIM), (x, y + 4))
        bs = d.get("boss_skills", {})
        for j, name in enumerate(monster_defs.BOSS_SKILL_DEFAULTS):
            on = name in bs
            self._box(surf, font, (x + 112 + j * 170, y, 160, 24), ("[x] " if on else "[ ] ") + name.replace("_", " "),
                      "boss_skill", name, on,
                      "HP-triggered boss skills: Deep Breath (a damage zone) and Enrage (more damage).")
        y += 28
        for name, cfg in bs.items():
            bx = x
            surf.blit(font.render(name.replace("_", " ") + ":", True, GOLD), (bx, y + 5))
            bx += 120
            for key, val in cfg.items():
                text = ",".join(f"{v:g}" for v in val) if isinstance(val, list) else f"{val:g}"
                surf.blit(font.render(key, True, DIM), (bx, y + 5))
                self._box(surf, font, (bx + len(key) * 8 + 6, y, 70, 24), text, "boss_param", (name, key), False,
                          "Click to change. Lists like 0.5,0.2 mean 'at 50% and at 20% HP'.")
                bx += len(key) * 8 + 86
            y += 28
        # castable skills
        y += 4
        surf.blit(big.render("Skills it casts", True, GOLD), (x, y)); y += 26
        cols = 4
        for i, sk in enumerate(self.skills):
            r = (x + (i % cols) * 190, y + (i // cols) * 26, 180, 22)
            on = sk in d.get("skills", [])
            self._box(surf, font, r, ("[x] " if on else "[ ] ") + sk, "skill", sk, on,
                      "Skills this monster's AI casts (the same skills heroes have).")
        y += ((len(self.skills) + cols - 1) // cols) * 26 + 8
        # drops
        surf.blit(big.render("Drops", True, GOLD), (x, y))
        self._button(surf, font, (x + 90, y, 110, 24), "+ Add drop", "add_drop", color=(60, 90, 60))
        surf.blit(font.render("its own list: chance per kill, optional monster-level range", True, DIM),
                  (x + 212, y + 5))
        y += 30
        drops = d.get("drops", [])
        rows = max(1, (H - y - 76) // 28)
        self.drop_scroll = max(0, min(self.drop_scroll, len(drops) - rows))
        for k, e in enumerate(drops[self.drop_scroll:self.drop_scroll + rows]):
            i = k + self.drop_scroll
            surf.blit(self.art.item(e[0], 20), (x, y + 2))
            surf.blit(font.render(ITEMS[e[0]]["name"], True, TEXT), (x + 28, y + 5))
            self._box(surf, font, (x + 230, y, 90, 24), f"{e[1] * 100:g}%", "drop_chance", i, False,
                      "Click to change the chance; right-click to remove the drop.")
            self._box(surf, font, (x + 330, y, 150, 24), f"levels {e[2]}-{e[3]}" if len(e) == 4 else "any level",
                      "drop_levels", i, len(e) == 4, "Only drops from monsters in this level range (empty = any).")
            self._button(surf, font, (x + 490, y, 24, 24), "x", "drop_remove", i, color=(100, 55, 55))
            y += 28
        if not drops:
            surf.blit(font.render("(drops nothing)", True, DIM), (x, y))
        elif len(drops) > rows:
            surf.blit(font.render(f"{len(drops)} drops - mouse wheel scrolls", True, DIM), (x + 530, y - 28))

    def _draw_sprite_picker(self, surf, font, big, x):
        surf.blit(big.render(f"Pick a picture for {self.d['name']} (click a tile)", True, GOLD), (x, 10))
        cur = self.d.get("sprite", {})
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
        surf.blit(big.render(f"Add a drop to {self.d['name']} (click an item)", True, GOLD), (x, 10))
        y = 44
        per_row = max(1, (W - x - 20) // 150)
        have = {e[0] for e in self.d.get("drops", [])}
        for kind in ("potion", "food", "drink", "weapon", "shield"):
            items = [k for k, it in ITEMS.items() if it["kind"] == kind]
            surf.blit(font.render(kind.title() + "s", True, DIM), (x, y))
            y += 18
            for i, item in enumerate(items):
                rect = pygame.Rect(x + (i % per_row) * 150, y + (i // per_row) * 36, 144, 30)
                pygame.draw.rect(surf, (55, 75, 55) if item in have else PANEL, rect, border_radius=4)
                surf.blit(self.art.item(item, 24), (rect.x + 4, rect.y + 3))
                surf.blit(font.render(ITEMS[item]["name"][:14], True, TEXT), (rect.x + 32, rect.y + 8))
                self._hit(rect, "pick_item", item)
            y += ((len(items) + per_row - 1) // per_row) * 36 + 6

    def _draw_matrix(self, surf, font, big, x, W, H):
        """Every monster (the filtered list) x every item: the drop chance in %, click a cell to change it."""
        surf.blit(big.render("Drops table: chance % per kill", True, GOLD), (x, 10))
        self._button(surf, font, (x + 440, 8, 150, 26), "Back to monster", "back")
        items = list(ITEMS)
        name_w, top = 170, 84
        cw = max(30, (W - x - name_w - 20) // len(items))
        for j, item in enumerate(items):
            cx = x + name_w + j * cw
            surf.blit(self.art.item(item, 22), (cx + (cw - 22) // 2, 40))
            tag = font.render(ITEMS[item]["name"][:4], True, DIM)
            surf.blit(tag, (cx + (cw - tag.get_width()) // 2, 64))
        rows = (H - top - 90) // 24
        types = self.shown()[:rows]
        for i, tid in enumerate(types):
            y = top + i * 24
            d = self.defs[tid]
            surf.blit(self.art.monster(d.get("sprite"), 20), (x, y + 1))
            surf.blit(font.render(d["name"][:18], True, TEXT), (x + 26, y + 5))
            lookup = {e[0]: e for e in d.get("drops", [])}
            for j, item in enumerate(items):
                cx = x + name_w + j * cw
                e = lookup.get(item)
                r = pygame.Rect(cx, y, cw - 2, 22)
                hover = r.collidepoint(pygame.mouse.get_pos())
                pygame.draw.rect(surf, (80, 110, 70) if e else ((58, 58, 70) if hover else (40, 40, 48)), r,
                                 border_radius=3)
                if e:
                    t = font.render(f"{e[1] * 100:g}", True, TEXT)
                    surf.blit(t, (r.centerx - t.get_width() // 2, r.y + 4))
                    if len(e) == 4:
                        pygame.draw.circle(surf, GOLD, (r.right - 4, r.y + 4), 2)        # has a level range
                if hover:
                    self.help = (f"{d['name']} / {ITEMS[item]['name']}: "
                                 + (f"{e[1] * 100:g}%" + (f", levels {e[2]}-{e[3]}" if len(e) == 4 else "")
                                    if e else "no drop") + "   (click = set chance, right-click = remove)")
                self._hit(r, "cell", (tid, item))
        if len(self.shown()) > rows:
            surf.blit(font.render(f"... {len(self.shown()) - rows} more monsters (turn on 'only this map')", True, DIM),
                      (x, top + rows * 24 + 6))


def run(screen, clock, defs, ask, map_types=lambda: set(), usage=lambda tid: [],
        path=monster_defs.PATH):
    """The Monsters screen as a modal loop (the map editor's M key). Works on copies: Done saves `path` and copies
    the edits back into `defs` (returns True); Esc drops them (False)."""
    font = pygame.font.SysFont("monospace", 13)
    big = pygame.font.SysFont("monospace", 18, bold=True)
    panel = MonsterPanel(copy.deepcopy(defs), ask, map_types, usage, path=path)
    while not panel.done:
        for event in pygame.event.get():
            if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
                if panel.mode != "main":
                    panel.mode = "main"
                    continue
                return False
            if event.type == pygame.MOUSEBUTTONDOWN and event.button in (1, 3):
                panel.click(event.pos, event.button)
            if event.type == pygame.MOUSEWHEEL:
                if pygame.mouse.get_pos()[0] < panel.LIST_W:
                    panel.list_scroll = max(0, panel.list_scroll - event.y * 3)
                else:
                    panel.drop_scroll = max(0, panel.drop_scroll - event.y * 2)
        panel.draw(screen, font, big)
        pygame.display.flip()
        clock.tick(30)
    defs.take(panel.defs)
    return True
