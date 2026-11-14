"""The map editor's Quests & NPCs screen (press Q): edit the NPCs of the open map and its quest chains.

  NPCs tab    name, gender, picture (a dungeon-sheet tile), role (none / class trainer / vendor), where it stands
              ("Place on map" closes this screen and the next click on the map puts it there).
              The NPC's id is made from its name when it is created and never changes (quests refer to it).
  Quests tab  title, description, who gives it, level needed, XP and gold rewards, what must be killed
              (any monster of data/monsters.json + a count), which quests must be done first, and which questline
              it belongs to. A questline is an ordered chain: only its next quest is offered, so a quest that is in
              no questline is never offered (shown in red in the list).

Done writes data/quests/<map>.json and copies the NPCs into the map (save the map with Ctrl+S to keep them);
Esc discards everything done in this screen.

Everything is driven by click(pos, button) and draw(surface, font, big); text goes through the ask(title, default,
long=False) callback the editor passes in, so tests can drive the panel without a real window.
"""
import copy

import pygame

from game import quests as quest_data
from game.content.monster_art import SHEET_SIZE
from game.editor.widgets import Widgets, BG, PANEL, LINE, TEXT, DIM, GOLD, RED, GREEN

LIST_W = 310
ROW = 26
MAX_NAME = 32


def wrap(text, font, width):
    """Word-wrap `text` into lines no wider than `width` pixels."""
    lines, line = [], ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if line and font.size(trial)[0] > width:
            lines.append(line)
            line = word
        else:
            line = trial
    return lines + [line] if line or not lines else lines


def role_of(npc):
    return npc.get("role") or "none"


class StoryPanel(Widgets):
    def __init__(self, npcs, data, monsters, ask, art, map_size=(1000, 1000), quest_save=None):
        """npcs: the map's NPC list (edited in place); data: the map's quest file dict (edited in place);
        monsters: monster_defs.Definitions (read only); ask(title, default, long=False) -> str or None;
        art: monster_panel.Art; quest_save(data): writes the quest file on Done."""
        self.npcs, self.data, self.monsters, self.ask, self.art = npcs, data, monsters, ask, art
        self.map_size, self.quest_save = map_size, quest_save
        self.tab = "quests"
        self.mode = "main"                 # "main" / "monster" (objective picker) / "sprite" (NPC picture picker)
        self.selected = next((q["id"] for q in data["quests"]), None)    # quest id
        self.sel_npc = 0 if npcs else None                                # index into npcs
        self.message, self.message_ok = "", True
        self.hits, self.help = [], ""
        self.done = False
        self.place = None                  # npc_id to place on the map once the screen closes
        self.list_scroll = 0

    # --- data helpers ---
    @property
    def quests(self):
        return self.data["quests"]

    @property
    def q(self):
        return next((q for q in self.quests if q["id"] == self.selected), None)

    @property
    def npc(self):
        return self.npcs[self.sel_npc] if self.sel_npc is not None and self.sel_npc < len(self.npcs) else None

    def npc_name(self, npc_id):
        return next((n["name"] for n in self.npcs if n["npc_id"] == npc_id), f"? {npc_id}")

    def monster_name(self, mid):
        d = self.monsters.get(mid)
        return d["name"] if d else f"#{mid}"

    def ordered_quests(self):
        """Questline order first (chain 1, chain 2, ...), then the quests that are in no questline."""
        by_id = {q["id"]: q for q in self.quests}
        out, seen = [], set()
        for line in self.data["questlines"]:
            for qid in line:
                if qid in by_id and qid not in seen:
                    out.append(by_id[qid])
                    seen.add(qid)
        return out + [q for q in self.quests if q["id"] not in seen]

    def line_of(self, qid):
        for i, line in enumerate(self.data["questlines"]):
            if qid in line:
                return i
        return None

    def _tidy_lines(self):
        self.data["questlines"] = [line for line in self.data["questlines"] if line]

    def errors(self):
        out = quest_data.validate_quest_data(self.data, {n["npc_id"] for n in self.npcs}, set(self.monsters))
        w, h = self.map_size
        ids = [n["npc_id"] for n in self.npcs]
        for n in self.npcs:
            if not (isinstance(n.get("name"), str) and n["name"].strip()):
                out.append(f"{n['npc_id']}: needs a name")
            if ids.count(n["npc_id"]) > 1:
                out.append(f"{n['name']}: id used twice")
            if not (0 <= n["x"] < w and 0 <= n["y"] < h):
                out.append(f"{n['name']}: stands outside the map")
        return out

    def _say(self, text, ok=True):
        self.message, self.message_ok = text, ok

    # --- actions ---
    def click(self, pos, button=1):
        hit = next(((a, arg) for r, a, arg in reversed(self.hits) if r.collidepoint(pos)), None)
        if hit is None:
            if self.mode != "main":
                self.mode = "main"
            return
        action, arg = hit
        getattr(self, f"_do_{action}")(arg, button)

    def _do_tab(self, tab, button):
        self.tab, self.mode = tab, "main"
        self.list_scroll = 0
        self._say("")

    def _do_scroll(self, delta, button):
        self.list_scroll = max(0, self.list_scroll + delta)

    # quests
    def _do_q_select(self, qid, button):
        self.selected, self.mode = qid, "main"
        self._say("")

    def _do_q_new(self, _, button):
        title = self.ask("New quest title:", "")
        if not title or not title.strip():
            return
        title = title.strip()[:60]
        qid = quest_data.quest_slug(title, {q["id"] for q in self.quests})
        giver = self.npcs[0]["npc_id"] if self.npcs else None
        self.quests.append({"id": qid, "title": title, "description": "", "objectives": [], "rewards_xp": 0,
                            "rewards_gold": 0, "npc_id": giver, "level_req": 1, "prerequisites": []})
        self.data["questlines"].append([qid])             # its own questline, so that it can be offered
        self.selected = qid
        self._say(f"Created {title} in a new questline. Pick who gives it and what to kill.")

    def _do_q_delete(self, _, button):
        q = self.q
        if q is None:
            return
        qid = q["id"]
        self.quests.remove(q)
        for other in self.quests:
            if qid in other.get("prerequisites", []):
                other["prerequisites"].remove(qid)
        for line in self.data["questlines"]:
            if qid in line:
                line.remove(qid)
        self._tidy_lines()
        self.selected = next((x["id"] for x in self.ordered_quests()), None)
        self._say(f"Deleted {q['title']} (saved characters keep working: unknown quests are ignored)")

    def _do_q_field(self, key, button):
        q = self.q
        if key == "title":
            raw = self.ask("Title:", q["title"])
            if raw and raw.strip():
                q["title"] = raw.strip()[:60]
        elif key == "description":
            raw = self.ask("Description (what the NPC says):", q.get("description", ""), True)
            if raw is not None:
                q["description"] = raw.strip()[:quest_data.MAX_QUEST_TEXT]
        elif key == "npc_id":
            ids = [n["npc_id"] for n in self.npcs]
            if ids:
                cur = ids.index(q["npc_id"]) if q.get("npc_id") in ids else -1
                q["npc_id"] = ids[(cur + 1) % len(ids)]
        else:
            lo, hi = {"level_req": (1, 30), "rewards_xp": (0, 10 ** 6), "rewards_gold": (0, 10 ** 6)}[key]
            raw = self.ask(f"{key.replace('_', ' ')} ({lo}-{hi}):", str(q.get(key, lo)))
            if raw is None:
                return
            try:
                v = int(float(raw))
            except ValueError:
                self._say(f"Not a number: {raw}", False)
                return
            if not lo <= v <= hi:
                self._say(f"Must be {lo}-{hi}", False)
                return
            q[key] = v

    def _do_q_prereq(self, qid, button):
        pre = self.q.setdefault("prerequisites", [])
        if qid in pre:
            pre.remove(qid)
        else:
            pre.append(qid)

    def _do_q_line(self, _, button):
        """Cycle: no questline -> line 1 -> line 2 ... -> a new line -> none."""
        q = self.q
        qid, cur = q["id"], self.line_of(q["id"])
        lines = self.data["questlines"]
        if cur is not None:
            lines[cur].remove(qid)
        alone = cur is not None and not lines[cur]            # it was the only quest of its line
        options = [None] + list(range(len(lines))) + ([] if alone else ["new"])
        pos = options.index(cur) if cur in options else 0
        nxt = options[(pos + 1) % len(options)]
        if nxt == "new":
            lines.append([qid])
        elif nxt is not None:
            lines[nxt].append(qid)
        self._tidy_lines()

    def _do_q_move(self, delta, button):
        qid = self.selected
        i = self.line_of(qid)
        if i is None:
            return
        line = self.data["questlines"][i]
        j = line.index(qid)
        if 0 <= j + delta < len(line):
            line[j], line[j + delta] = line[j + delta], line[j]

    def _do_obj_add(self, _, button):
        self.mode = "monster"

    def _do_obj_pick(self, mid, button):
        objs = self.q.setdefault("objectives", [])
        if not any(o["monster"] == mid for o in objs):
            objs.append({"monster": mid, "count": 10})
            self._say(f"Added {self.monster_name(mid)} x10. Click its count to change it.")
        self.mode = "main"

    def _do_obj_count(self, i, button):
        o = self.q["objectives"][i]
        raw = self.ask(f"How many {self.monster_name(o['monster'])} (1-999):", str(o["count"]))
        if raw is None:
            return
        try:
            v = int(float(raw))
        except ValueError:
            self._say(f"Not a number: {raw}", False)
            return
        if not 1 <= v <= 999:
            self._say("Must be 1-999", False)
            return
        o["count"] = v

    def _do_obj_del(self, i, button):
        del self.q["objectives"][i]

    # NPCs
    def _do_n_select(self, i, button):
        self.sel_npc, self.mode = i, "main"
        self._say("")

    def _do_n_new(self, _, button):
        name = self.ask("New NPC name:", "")
        if not name or not name.strip():
            return
        name = name.strip()[:MAX_NAME]
        taken = {n["npc_id"] for n in self.npcs}
        npc_id = quest_data.quest_slug(name, taken)
        self.npcs.append({"name": name, "npc_id": npc_id, "gender": "male", "x": 1, "y": 1,
                          "sprite_col": 1, "sprite_row": 8})
        self.sel_npc, self.mode = len(self.npcs) - 1, "sprite"
        self._say(f"Created {name}. Pick a picture, then \"Place on map\".")

    def _do_n_delete(self, _, button):
        n = self.npc
        if n is None:
            return
        giving = [q["title"] for q in self.quests if q.get("npc_id") == n["npc_id"]]
        if giving:
            self._say(f"{n['name']} gives: {', '.join(giving)}. Give those quests to someone else first.", False)
            return
        self.npcs.remove(n)
        self.sel_npc = 0 if self.npcs else None
        self._say(f"Deleted {n['name']}")

    def _do_n_field(self, key, button):
        n = self.npc
        if key == "name":
            raw = self.ask("Name:", n["name"])
            if raw and raw.strip():
                n["name"] = raw.strip()[:MAX_NAME]
        elif key == "gender":
            n["gender"] = "female" if n.get("gender", "male") == "male" else "male"
        elif key == "role":
            order = [None, "trainer", "vendor"]
            nxt = order[(order.index(n.get("role")) + 1) % 3]
            for k in ("role", "trains", "shop"):
                n.pop(k, None)
            if nxt == "trainer":
                n.update(role="trainer", trains=self._classes()[0])
            elif nxt == "vendor":
                n.update(role="vendor", shop=self._shops()[0])
        elif key == "trains":
            opts = self._classes()
            n["trains"] = opts[(opts.index(n.get("trains")) + 1) % len(opts)] if n.get("trains") in opts else opts[0]
        elif key == "shop":
            opts = self._shops()
            n["shop"] = opts[(opts.index(n.get("shop")) + 1) % len(opts)] if n.get("shop") in opts else opts[0]
        elif key == "pos":
            raw = self.ask("Tile x,y:", f"{n['x']},{n['y']}")
            if raw is None:
                return
            try:
                x, y = (int(p) for p in raw.replace(" ", "").split(","))
            except ValueError:
                self._say(f"Type it like 26,28: {raw}", False)
                return
            n["x"], n["y"] = x, y

    @staticmethod
    def _classes():
        from game.content.heroes import HERO_CLASSES
        return [c["class"] for c in HERO_CLASSES]

    @staticmethod
    def _shops():
        from game.content.shop import SHOPS
        return list(SHOPS)

    def _do_n_picture(self, _, button):
        self.mode = "sprite"

    def _do_n_pick(self, art, button):
        self.npc["sprite_col"], self.npc["sprite_row"] = art["col"], art["row"]
        self.mode = "main"

    def _do_n_place(self, _, button):
        errs = self.errors()
        if errs:
            self._say(errs[0], False)
            return
        self.place = self.npc["npc_id"]
        self._do_done(None, 1)

    def _do_done(self, _, button):
        errs = self.errors()
        if errs:
            self._say(errs[0], False)
            return
        if self.quest_save:
            self.quest_save(self.data)
        self.done = True

    # --- drawing ---
    def draw(self, surf, font, big):
        self.hits, self.help = [], ""
        W, H = surf.get_size()
        surf.fill(BG)
        self._draw_list(surf, font, big, H)
        x0 = LIST_W + 30
        if self.mode == "monster" and self.q:
            self._draw_monster_picker(surf, font, big, x0, W)
        elif self.mode == "sprite" and self.npc:
            self._draw_sprite_picker(surf, font, big, x0)
        elif self.tab == "quests":
            if self.q:
                self._draw_quest(surf, font, big, x0, W, H)
            else:
                surf.blit(big.render("No quest selected - click \"+ New quest\"", True, DIM), (x0, 40))
        elif self.npc:
            self._draw_npc(surf, font, big, x0, W, H)
        else:
            surf.blit(big.render("No NPC selected - click \"+ New NPC\"", True, DIM), (x0, 40))
        if self.help:
            surf.blit(font.render(self.help, True, DIM), (x0, H - 62))
        if self.message:
            surf.blit(font.render(self.message, True, GREEN if self.message_ok else RED), (x0, H - 44))
        self._button(surf, big, (W - 170, H - 46, 150, 32), "Done (save)", "done", color=(60, 100, 60))
        surf.blit(font.render("Esc = discard all changes made in this screen", True, DIM), (x0, H - 24))

    def _draw_list(self, surf, font, big, H):
        pygame.draw.rect(surf, PANEL, (0, 0, LIST_W, H))
        half = (LIST_W - 30) // 2
        self._button(surf, font, (12, 10, half, 28), "Quests", "tab", "quests",
                     color=(70, 95, 120) if self.tab == "quests" else (70, 70, 82))
        self._button(surf, font, (18 + half, 10, half, 28), "NPCs", "tab", "npcs",
                     color=(70, 95, 120) if self.tab == "npcs" else (70, 70, 82))
        if self.tab == "quests":
            self._button(surf, font, (12, 44, half, 26), "+ New quest", "q_new", color=(60, 90, 60))
            self._button(surf, font, (18 + half, 44, half, 26), "Delete", "q_delete", color=(100, 55, 55))
            items = [(q["id"], q) for q in self.ordered_quests()]
        else:
            self._button(surf, font, (12, 44, half, 26), "+ New NPC", "n_new", color=(60, 90, 60))
            self._button(surf, font, (18 + half, 44, half, 26), "Delete", "n_delete", color=(100, 55, 55))
            items = list(enumerate(self.npcs))
        y0, rows = 80, (H - 90) // ROW
        self.list_scroll = min(self.list_scroll, max(0, len(items) - rows))
        for i, (key, item) in enumerate(items[self.list_scroll:self.list_scroll + rows]):
            y = y0 + i * ROW
            r = pygame.Rect(8, y, LIST_W - 16, ROW - 2)
            if self.tab == "quests":
                if key == self.selected:
                    pygame.draw.rect(surf, (70, 90, 70), r, border_radius=3)
                line = self.line_of(key)
                tag = f"{line + 1}." if line is not None else "-"
                surf.blit(font.render(f"{tag} {item['title']}"[:36], True, TEXT if line is not None else RED),
                          (14, y + 5))
                self._hit(r, "q_select", key)
            else:
                if key == self.sel_npc:
                    pygame.draw.rect(surf, (70, 90, 70), r, border_radius=3)
                surf.blit(self.art.monster({"sheet": "dungeon", "col": item["sprite_col"], "row": item["sprite_row"]},
                                           20), (14, y + 2))
                surf.blit(font.render(item["name"][:30], True, TEXT), (40, y + 5))
                self._hit(r, "n_select", key)
        if len(items) > rows:
            self._button(surf, font, (LIST_W - 60, 44, 22, 26), "^", "scroll", -5)
            self._button(surf, font, (LIST_W - 34, 44, 22, 26), "v", "scroll", 5)

    def _row(self, surf, font, x, y, label, text, action, arg=None, help_text="", width=420, active=False):
        surf.blit(font.render(label, True, DIM), (x, y + 6))
        self._box(surf, font, (x + 130, y, width, 26), text, action, arg, active, help_text)

    def _draw_quest(self, surf, font, big, x, W, H):
        q = self.q
        surf.blit(big.render(q["title"], True, GOLD), (x, 10))
        surf.blit(font.render(f"id: {q['id']}   (permanent: saved characters use it)", True, DIM), (x, 38))
        y = 64
        self._row(surf, font, x, y, "Title", q["title"], "q_field", "title", "Shown in the quest log.")
        y += 32
        self._row(surf, font, x, y, "Given by", self.npc_name(q.get("npc_id")), "q_field", "npc_id",
                  "Click to cycle through the NPCs of this map. This NPC offers it and takes it back.")
        y += 32
        self._row(surf, font, x, y, "Level needed", q.get("level_req", 1), "q_field", "level_req",
                  "The hero must be at least this level to be offered the quest.", 120)
        self._row(surf, font, x + 270, y, "XP reward", q.get("rewards_xp", 0), "q_field", "rewards_xp",
                  "XP when handing it in.", 120)
        y += 32
        self._row(surf, font, x, y, "Gold reward", q.get("rewards_gold", 0), "q_field", "rewards_gold",
                  "Bronze when handing it in.", 120)
        line = self.line_of(q["id"])
        if line is None:
            text = "none (never offered!)"
        else:
            chain = self.data["questlines"][line]
            text = f"#{line + 1}: step {chain.index(q['id']) + 1} of {len(chain)}"
        self._row(surf, font, x + 270, y, "Questline", text, "q_line", None,
                  "A chain of quests: only its next quest is offered. Click to cycle: none, each line, a new line.",
                  190, line is not None)
        self._button(surf, font, (x + 270 + 130 + 196, y, 26, 26), "<", "q_move", -1)
        self._button(surf, font, (x + 270 + 130 + 226, y, 26, 26), ">", "q_move", 1)
        y += 40
        surf.blit(font.render("Description (click to edit)", True, DIM), (x, y))
        y += 20
        box = pygame.Rect(x, y, W - x - 20, 96)
        hover = box.collidepoint(pygame.mouse.get_pos())
        pygame.draw.rect(surf, (66, 66, 78) if hover else (52, 52, 62), box, border_radius=4)
        pygame.draw.rect(surf, LINE, box, 1, border_radius=4)
        for i, ln in enumerate(wrap(q.get("description", "") or "(empty)", font, box.w - 14)[:5]):
            surf.blit(font.render(ln, True, TEXT), (box.x + 7, box.y + 6 + i * 17))
        self._hit(box, "q_field", "description")
        y += 108
        # objectives
        surf.blit(font.render("Kill (the monster type + how many):", True, GOLD), (x, y))
        y += 22
        for i, o in enumerate(q.get("objectives", [])):
            d = self.monsters.get(o["monster"])
            surf.blit(self.art.monster(d.get("sprite") if d else None, 24), (x, y))
            surf.blit(font.render(f"{self.monster_name(o['monster'])} #{o['monster']}", True, TEXT), (x + 32, y + 6))
            self._box(surf, font, (x + 280, y, 70, 26), f"x {o['count']}", "obj_count", i, False,
                      "How many must be killed.")
            self._button(surf, font, (x + 358, y, 26, 26), "x", "obj_del", i, color=(100, 55, 55))
            y += 30
        if not q.get("objectives"):
            surf.blit(font.render("(none: the quest is done as soon as it is accepted)", True, DIM), (x, y + 4))
            y += 30
        self._button(surf, font, (x, y, 170, 26), "+ Add monster", "obj_add", color=(60, 90, 60))
        y += 40
        # prerequisites
        surf.blit(font.render("Needs these quests done first (click to toggle):", True, GOLD), (x, y))
        y += 22
        cx = x
        for other in self.ordered_quests():
            if other["id"] == q["id"]:
                continue
            label = other["title"][:26]
            w = font.size(label)[0] + 16
            if cx + w > W - 20:
                cx, y = x, y + 30
            self._box(surf, font, (cx, y, w, 26), label, "q_prereq", other["id"],
                      other["id"] in q.get("prerequisites", []), "Green = must be handed in before this one.")
            cx += w + 6

    def _draw_monster_picker(self, surf, font, big, x, W):
        surf.blit(big.render(f"Add a monster to {self.q['title']} (click one)", True, GOLD), (x, 10))
        per_row = max(1, (W - x - 20) // 250)
        for i, (mid, d) in enumerate(sorted(self.monsters.items(), key=lambda kv: kv[1]["name"].lower())):
            r = pygame.Rect(x + (i % per_row) * 250, 44 + (i // per_row) * 32, 240, 28)
            pygame.draw.rect(surf, (52, 52, 62), r, border_radius=4)
            surf.blit(self.art.monster(d.get("sprite"), 24), (r.x + 2, r.y + 2))
            lv = d.get("level")
            surf.blit(font.render(f"{d['name']} #{mid}" + (f" L{lv[0]}-{lv[1]}" if lv else ""), True, TEXT),
                      (r.x + 32, r.y + 7))
            self._hit(r, "obj_pick", mid)

    def _draw_npc(self, surf, font, big, x, W, H):
        n = self.npc
        surf.blit(big.render(n["name"], True, GOLD), (x, 10))
        surf.blit(font.render(f"id: {n['npc_id']}   (permanent: quests refer to it)", True, DIM), (x, 38))
        pic = pygame.Rect(W - 150, 12, 128, 128)
        pygame.draw.rect(surf, PANEL, pic, border_radius=6)
        surf.blit(self.art.monster({"sheet": "dungeon", "col": n["sprite_col"], "row": n["sprite_row"]}, 112),
                  (pic.x + 8, pic.y + 8))
        self._button(surf, font, (pic.x, pic.bottom + 6, pic.w, 24), "Change picture", "n_picture")
        y = 64
        self._row(surf, font, x, y, "Name", n["name"], "n_field", "name", "Shown over the NPC.")
        y += 32
        self._row(surf, font, x, y, "Gender", n.get("gender", "male"), "n_field", "gender",
                  "Only changes how it is described.")
        y += 32
        self._row(surf, font, x, y, "Role", role_of(n), "n_field", "role",
                  "none = quest giver only; trainer = teaches a class's skills; vendor = sells things.")
        y += 32
        if n.get("role") == "trainer":
            self._row(surf, font, x, y, "Trains", n.get("trains"), "n_field", "trains", "Which class it teaches.")
        elif n.get("role") == "vendor":
            self._row(surf, font, x, y, "Sells", n.get("shop"), "n_field", "shop",
                      "general = food and drink; weapons; armor.")
        y += 32
        self._row(surf, font, x, y, "Stands at", f"{n['x']}, {n['y']}", "n_field", "pos", "Tile x,y on this map.")
        self._button(surf, font, (x + 560, y, 190, 26), "Place on map...", "n_place",
                     color=(70, 95, 120))
        y += 48
        gives = [q["title"] for q in self.quests if q.get("npc_id") == n["npc_id"]]
        surf.blit(font.render("Gives quests:", True, GOLD), (x, y))
        for i, t in enumerate(gives or ["(none)"]):
            surf.blit(font.render(f"  {t}", True, TEXT if gives else DIM), (x, y + 22 + i * 18))

    def _draw_sprite_picker(self, surf, font, big, x):
        surf.blit(big.render(f"Pick a picture for {self.npc['name']} (click a tile)", True, GOLD), (x, 10))
        cols, rows = SHEET_SIZE["dungeon"]
        size, gap = 40, 3
        for r in range(rows):
            for c in range(cols):
                art = {"sheet": "dungeon", "col": c, "row": r}
                rect = pygame.Rect(x + c * (size + gap), 50 + r * (size + gap), size, size)
                pygame.draw.rect(surf, PANEL, rect)
                surf.blit(self.art.monster(art, size), rect.topleft)
                if (c, r) == (self.npc["sprite_col"], self.npc["sprite_row"]):
                    pygame.draw.rect(surf, GOLD, rect.inflate(2, 2), 2)
                self._hit(rect, "n_pick", art)


def run(screen, clock, npcs, data, monsters, ask, art, map_size, quest_save):
    """The screen as a modal loop (the map editor's Q key). Works on copies: Done writes the quest file and copies the
    NPCs / quests back (returns (True, npc_id or None); npc_id = an NPC to place on the map); Esc discards (False, None)."""
    font = pygame.font.SysFont("monospace", 13)
    big = pygame.font.SysFont("monospace", 18, bold=True)
    panel = StoryPanel(copy.deepcopy(npcs), copy.deepcopy(data), monsters, ask, art, map_size, quest_save)
    while not panel.done:
        for event in pygame.event.get():
            if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
                if panel.mode != "main":
                    panel.mode = "main"
                    continue
                return False, None
            if event.type == pygame.MOUSEBUTTONDOWN and event.button in (1, 3):
                panel.click(event.pos, event.button)
            if event.type == pygame.MOUSEWHEEL and pygame.mouse.get_pos()[0] < LIST_W:
                panel.list_scroll = max(0, panel.list_scroll - event.y * 3)
        panel.draw(screen, font, big)
        pygame.display.flip()
        clock.tick(30)
    npcs[:] = panel.npcs
    data.clear()
    data.update(panel.data)
    return True, panel.place
