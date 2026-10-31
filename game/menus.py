"""
Pre-game menus: character select / create / delete, then map select.

Navigation (ESC):
    map select       -> character select
    character select -> quit
    create screen    -> character select
"""
import glob
import os
from dataclasses import dataclass

import pygame

from game import saves
from game.content.heroes import HERO_CLASSES, HERO_CLASS_BY_NAME
from game.content.difficulty import (PP_MIN, PP_MAX, PP_DEFAULT, map_title, hp_multiplier,
                                     damage_multiplier)

CARD_W, CARD_H, CARD_GAP = 160, 300, 20
GOLD = (255, 215, 0)
WHITE = (255, 255, 255)
GRAY = (80, 80, 80)
LIGHT_GRAY = (140, 140, 160)
RED = (220, 80, 80)
BG = (15, 12, 20)


@dataclass
class MenuContext:
    """Resources the menus need from main.py."""
    clock: object
    font: object
    big_font: object
    title_font: object
    hero_sprites: dict  # sprite_key -> Surface


def _screen():
    return pygame.display.get_surface()


def _handle_common(event):
    """Handle window events shared by every menu. Returns 'quit' for window close."""
    if event.type == pygame.QUIT:
        return "quit"
    if event.type == pygame.VIDEORESIZE:
        pygame.display.set_mode((event.w, event.h), pygame.RESIZABLE)
    return None


def _wrap(text, fnt, max_width):
    lines, current = [], ""
    for word in text.split(" "):
        test = current + (" " if current else "") + word
        if fnt.size(test)[0] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _draw_card(ctx, screen, rect, selected, sprite_key=None, title="", subtitle="",
               lines=(), title_color=WHITE):
    pygame.draw.rect(screen, (60, 60, 100) if selected else (35, 35, 50), rect, 0, 6)
    if selected:
        pygame.draw.rect(screen, GOLD, rect, 2, 6)
    if sprite_key:
        spr = pygame.transform.scale(ctx.hero_sprites[sprite_key], (64, 64))
        screen.blit(spr, (rect.centerx - 32, rect.y + 15))
    nt = ctx.big_font.render(title, True, title_color)
    screen.blit(nt, (rect.centerx - nt.get_width() // 2, rect.y + 85))
    if subtitle:
        st = ctx.font.render(subtitle, True, (160, 160, 190))
        screen.blit(st, (rect.centerx - st.get_width() // 2, rect.y + 112))
    y = rect.y + 140
    for line in lines:
        lt = ctx.font.render(line, True, LIGHT_GRAY)
        screen.blit(lt, (rect.x + 8, y))
        y += 18


# ---------------------------------------------------------------- character select

def character_select(ctx):
    """Returns ('play', char_data) or ('quit', None)."""
    chars = saves.list_characters()
    sel = 0
    scroll = 0
    confirm_delete = None  # character name awaiting delete confirmation
    status = ""

    while True:
        items = chars + [None]  # None = "New Character" card
        sel = max(0, min(sel, len(items) - 1))
        screen = _screen()
        W, H = screen.get_size()
        visible = max(1, (W - 60 + CARD_GAP) // (CARD_W + CARD_GAP))
        total_w = min(len(items), visible) * (CARD_W + CARD_GAP) - CARD_GAP
        x0 = (W - total_w) // 2
        scroll = max(0, min(scroll, len(items) - visible))
        if sel < scroll:
            scroll = sel
        if sel >= scroll + visible:
            scroll = sel - visible + 1
        card_y = 160

        def card_rect(i):
            return pygame.Rect(x0 + (i - scroll) * (CARD_W + CARD_GAP), card_y, CARD_W, CARD_H)

        def delete_btn(i):
            r = card_rect(i)
            return pygame.Rect(r.x + 20, r.bottom - 40, r.w - 40, 28)

        for event in pygame.event.get():
            if _handle_common(event) == "quit":
                return "quit", None
            if confirm_delete:
                # Modal: Y / Enter confirms, N / ESC cancels
                if event.type == pygame.KEYDOWN:
                    if event.key in (pygame.K_y, pygame.K_RETURN):
                        saves.delete_character(confirm_delete)
                        status = f"Deleted {confirm_delete}"
                        chars = saves.list_characters()
                        confirm_delete = None
                    elif event.key in (pygame.K_n, pygame.K_ESCAPE):
                        confirm_delete = None
                continue
            if event.type == pygame.KEYDOWN:
                status = ""
                if event.key == pygame.K_ESCAPE:
                    return "quit", None
                if event.key in (pygame.K_LEFT, pygame.K_a):
                    sel = (sel - 1) % len(items)
                if event.key in (pygame.K_RIGHT, pygame.K_d):
                    sel = (sel + 1) % len(items)
                if event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    if items[sel] is None:
                        created = create_screen(ctx)
                        chars = saves.list_characters()
                        if created:
                            sel = next((i for i, c in enumerate(chars) if c["name"] == created["name"]), sel)
                    else:
                        return "play", items[sel]
                if event.key in (pygame.K_DELETE, pygame.K_BACKSPACE) and items[sel] is not None:
                    confirm_delete = items[sel]["name"]
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                status = ""
                for i in range(scroll, min(len(items), scroll + visible)):
                    if items[i] is not None and i == sel and delete_btn(i).collidepoint(event.pos):
                        confirm_delete = items[i]["name"]
                        break
                    if card_rect(i).collidepoint(event.pos):
                        if sel == i:
                            if items[i] is None:
                                created = create_screen(ctx)
                                chars = saves.list_characters()
                                if created:
                                    sel = next((j for j, c in enumerate(chars)
                                                if c["name"] == created["name"]), sel)
                            else:
                                return "play", items[i]
                        else:
                            sel = i
                        break
            if event.type == pygame.MOUSEWHEEL:
                scroll = max(0, min(scroll - event.y, max(0, len(items) - visible)))

        screen.fill(BG)
        t = ctx.title_font.render("CHOOSE YOUR CHARACTER", True, GOLD)
        screen.blit(t, (W // 2 - t.get_width() // 2, 50))

        for i in range(scroll, min(len(items), scroll + visible)):
            rect = card_rect(i)
            c = items[i]
            if c is None:
                pygame.draw.rect(screen, (60, 60, 100) if i == sel else (30, 30, 42), rect, 0, 6)
                pygame.draw.rect(screen, GOLD if i == sel else GRAY, rect, 2 if i == sel else 1, 6)
                plus = ctx.title_font.render("+", True, GOLD if i == sel else LIGHT_GRAY)
                screen.blit(plus, (rect.centerx - plus.get_width() // 2, rect.y + 90))
                nt = ctx.big_font.render("New Character", True, WHITE)
                screen.blit(nt, (rect.centerx - nt.get_width() // 2, rect.y + 150))
            else:
                cls = HERO_CLASS_BY_NAME.get(c["class_name"])
                _draw_card(ctx, screen, rect, i == sel,
                           sprite_key=cls["sprite_key"] if cls else None,
                           title=c["name"].capitalize(),
                           subtitle=f"Lv {c['level']} {c['class_name']}",
                           lines=[f"Gold: {c['gold']}", f"Kills: {c['kills']}"])
                if i == sel:
                    b = delete_btn(i)
                    hovered = b.collidepoint(pygame.mouse.get_pos())
                    pygame.draw.rect(screen, (110, 40, 40) if hovered else (70, 30, 30), b, 0, 4)
                    pygame.draw.rect(screen, RED, b, 1, 4)
                    dt_ = ctx.font.render("Delete", True, WHITE)
                    screen.blit(dt_, (b.centerx - dt_.get_width() // 2, b.centery - dt_.get_height() // 2))

        if scroll > 0:
            screen.blit(ctx.big_font.render("<", True, GOLD), (x0 - 30, card_y + CARD_H // 2))
        if scroll + visible < len(items):
            screen.blit(ctx.big_font.render(">", True, GOLD), (x0 + total_w + 12, card_y + CARD_H // 2))

        if status:
            st = ctx.font.render(status, True, (200, 200, 150))
            screen.blit(st, (W // 2 - st.get_width() // 2, card_y + CARD_H + 20))
        inst = ctx.font.render("A/D or Arrows = select    ENTER = play / create    DEL = delete    ESC = quit",
                               True, (100, 100, 100))
        screen.blit(inst, (W // 2 - inst.get_width() // 2, H - 50))

        if confirm_delete:
            _draw_delete_modal(ctx, screen, confirm_delete)

        pygame.display.flip()
        ctx.clock.tick(30)


def _draw_delete_modal(ctx, screen, name):
    W, H = screen.get_size()
    overlay = pygame.Surface((W, H), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 170))
    screen.blit(overlay, (0, 0))
    box = pygame.Rect(0, 0, 520, 150)
    box.center = (W // 2, H // 2)
    pygame.draw.rect(screen, (40, 25, 25), box, 0, 8)
    pygame.draw.rect(screen, RED, box, 2, 8)
    l1 = ctx.big_font.render(f"Permanently delete {name.capitalize()}?", True, WHITE)
    l2 = ctx.font.render("All level, gold and quest progress will be lost. This cannot be undone.", True, LIGHT_GRAY)
    l3 = ctx.font.render("Y / ENTER = delete        N / ESC = cancel", True, GOLD)
    screen.blit(l1, (box.centerx - l1.get_width() // 2, box.y + 25))
    screen.blit(l2, (box.centerx - l2.get_width() // 2, box.y + 65))
    screen.blit(l3, (box.centerx - l3.get_width() // 2, box.y + 100))


# ---------------------------------------------------------------- character creation

def create_screen(ctx):
    """Name + class entry. Returns the new character's data, or None if cancelled."""
    name = ""
    class_idx = 0
    error = ""

    def try_create():
        data, err = saves.create_character(name, HERO_CLASSES[class_idx]["class"])
        return data, err

    while True:
        screen = _screen()
        W, H = screen.get_size()
        n = len(HERO_CLASSES)
        total_w = n * (CARD_W + CARD_GAP) - CARD_GAP
        x0 = (W - total_w) // 2
        card_y = 230

        def card_rect(i):
            return pygame.Rect(x0 + i * (CARD_W + CARD_GAP), card_y, CARD_W, 250)

        for event in pygame.event.get():
            if _handle_common(event) == "quit":
                pygame.quit()
                raise SystemExit
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return None
                elif event.key == pygame.K_RETURN:
                    data, err = try_create()
                    if data:
                        return data
                    error = err
                elif event.key == pygame.K_BACKSPACE:
                    name = name[:-1]
                    error = ""
                elif event.key == pygame.K_LEFT:
                    class_idx = (class_idx - 1) % n
                elif event.key in (pygame.K_RIGHT, pygame.K_TAB):
                    class_idx = (class_idx + 1) % n
                elif event.unicode and event.unicode.isalpha() and event.unicode.isascii():
                    if len(name) < saves.MAX_NAME_LEN:
                        name += event.unicode.lower()
                    error = ""
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                for i in range(n):
                    if card_rect(i).collidepoint(event.pos):
                        class_idx = i

        screen.fill(BG)
        t = ctx.title_font.render("CREATE CHARACTER", True, GOLD)
        screen.blit(t, (W // 2 - t.get_width() // 2, 50))

        label = ctx.font.render(f"Name (a-z, max {saves.MAX_NAME_LEN})", True, LIGHT_GRAY)
        screen.blit(label, (W // 2 - label.get_width() // 2, 120))
        box = pygame.Rect(0, 0, 320, 44)
        box.center = (W // 2, 160)
        pygame.draw.rect(screen, (30, 30, 45), box, 0, 6)
        pygame.draw.rect(screen, GOLD, box, 2, 6)
        cursor = "_" if (pygame.time.get_ticks() // 500) % 2 == 0 else " "
        nt = ctx.big_font.render(name + cursor, True, WHITE)
        screen.blit(nt, (box.x + 12, box.centery - nt.get_height() // 2))
        if error:
            et = ctx.font.render(error, True, RED)
            screen.blit(et, (W // 2 - et.get_width() // 2, 192))

        for i, cls in enumerate(HERO_CLASSES):
            rect = card_rect(i)
            _draw_card(ctx, screen, rect, i == class_idx, sprite_key=cls["sprite_key"],
                       title=cls["class"], lines=_wrap(cls["desc"], ctx.font, CARD_W - 16))

        inst = ctx.font.render("Type a name    Left/Right = class    ENTER = create    ESC = cancel",
                               True, (100, 100, 100))
        screen.blit(inst, (W // 2 - inst.get_width() // 2, H - 50))
        pygame.display.flip()
        ctx.clock.tick(30)


# ---------------------------------------------------------------- map select

def available_maps():
    maps = []
    for mf in sorted(glob.glob("data/maps/*.json")):
        stem = os.path.splitext(os.path.basename(mf))[0]
        maps.append({"path": mf.replace(os.sep, "/"), "name": stem.replace("_", " ").title(), "desc": mf})
    return maps


MAP_LIST_TOP = 182   # map rows start below the difficulty row


def _pp_dropdown_rects(W):
    """(button, [option rects 1..8]) for the difficulty dropdown on the map-select screen (plain ASCII arrows:
    the default pygame font has no triangle glyphs)."""
    button = pygame.Rect(W // 2 + 10, 142, 110, 26)
    options = [pygame.Rect(button.x, button.bottom + 2 + i * 24, 230, 22) for i in range(PP_MAX - PP_MIN + 1)]
    return button, options


def map_select(ctx, char, pp=PP_DEFAULT):
    """Returns {"map": path, "pp": n} (Enter: solo), {"host": path, "pp": n} (H: host on this computer only),
    {"host": path, "pp": n, "lan": True} (L: host on the home network), {"join": True, "address": ip}
    (J: pick a game on the Join screen), None to go back, or 'quit'.
    The "Difficulty" dropdown (click it, or +/- keys) picks the map's pp: 1pp normal ... 8pp = monsters have
    8x HP and deal 4.5x damage for 4.5x XP (Diablo II /players)."""
    maps = available_maps()
    if not maps:
        return None
    sel = 0
    dropdown_open = False
    while True:
        screen = _screen()
        W, H = screen.get_size()
        button, options = _pp_dropdown_rects(W)
        for event in pygame.event.get():
            if _handle_common(event) == "quit":
                return "quit"
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    if dropdown_open:
                        dropdown_open = False
                        continue
                    return None
                if event.key in (pygame.K_UP, pygame.K_w):
                    sel = (sel - 1) % len(maps)
                if event.key in (pygame.K_DOWN, pygame.K_s):
                    sel = (sel + 1) % len(maps)
                if event.key in (pygame.K_PLUS, pygame.K_EQUALS, pygame.K_KP_PLUS, pygame.K_RIGHT):
                    pp = min(PP_MAX, pp + 1)
                if event.key in (pygame.K_MINUS, pygame.K_KP_MINUS, pygame.K_LEFT):
                    pp = max(PP_MIN, pp - 1)
                if event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    return {"map": maps[sel]["path"], "pp": pp}
                if event.key == pygame.K_h:
                    return {"host": maps[sel]["path"], "pp": pp}
                if event.key == pygame.K_l:
                    return {"host": maps[sel]["path"], "pp": pp, "lan": True}
                if event.key == pygame.K_j:
                    choice = join_select(ctx)
                    if choice == "quit":
                        return "quit"
                    if choice:
                        return choice
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if dropdown_open:
                    for i, r in enumerate(options):
                        if r.collidepoint(event.pos):
                            pp = PP_MIN + i
                    dropdown_open = False      # any click closes the list
                    continue
                if button.collidepoint(event.pos):
                    dropdown_open = True
                    continue
                for i in range(len(maps)):
                    rect = pygame.Rect(W // 2 - 250, MAP_LIST_TOP + i * 60, 500, 50)
                    if rect.collidepoint(event.pos):
                        if sel == i:
                            return {"map": maps[i]["path"], "pp": pp}
                        sel = i

        screen.fill(BG)
        t = ctx.title_font.render("CHOOSE YOUR MAP", True, GOLD)
        screen.blit(t, (W // 2 - t.get_width() // 2, 50))
        who = ctx.font.render(f"{char['name'].capitalize()} — Lv {char['level']} {char['class_name']}",
                              True, LIGHT_GRAY)
        screen.blit(who, (W // 2 - who.get_width() // 2, 100))
        hint = ctx.font.render("Arrow keys / click to select, Enter = play solo, ESC = back", True, GRAY)
        screen.blit(hint, (W // 2 - hint.get_width() // 2, 120))
        coop = ctx.font.render("Co-op:  L = host on home network    H = host on this computer only    J = join a game",
                               True, (150, 180, 255))
        screen.blit(coop, (W // 2 - coop.get_width() // 2, H - 40))

        for i, m in enumerate(maps):
            rect = pygame.Rect(W // 2 - 250, MAP_LIST_TOP + i * 60, 500, 50)
            if i == sel:
                pygame.draw.rect(screen, (40, 80, 40), rect, border_radius=6)
                pygame.draw.rect(screen, GOLD, rect, 2, border_radius=6)
            else:
                hovered = rect.collidepoint(pygame.mouse.get_pos())
                pygame.draw.rect(screen, (40, 40, 60) if hovered else (30, 30, 40), rect, border_radius=6)
                pygame.draw.rect(screen, GRAY, rect, 1, border_radius=6)
            name = map_title(m["name"], pp) if i == sel else m["name"]
            screen.blit(ctx.big_font.render(name, True, WHITE), (rect.x + 15, rect.y + 8))
            screen.blit(ctx.font.render(m["desc"], True, GRAY), (rect.x + 15, rect.y + 32))

        # Difficulty dropdown (drawn last so the open list covers the map rows)
        label = ctx.font.render("Difficulty (+/- or click):", True, LIGHT_GRAY)
        screen.blit(label, (button.x - label.get_width() - 10, button.y + 6))
        pygame.draw.rect(screen, (40, 40, 70), button, border_radius=4)
        pygame.draw.rect(screen, GOLD, button, 1, border_radius=4)
        screen.blit(ctx.font.render(f"{pp}pp   v" if not dropdown_open else f"{pp}pp   ^", True, WHITE),
                    (button.x + 10, button.y + 6))
        if dropdown_open:
            for i, r in enumerate(options):
                v = PP_MIN + i
                hovered = r.collidepoint(pygame.mouse.get_pos())
                pygame.draw.rect(screen, (70, 70, 110) if hovered or v == pp else (30, 30, 50), r)
                pygame.draw.rect(screen, GRAY, r, 1)
                txt = f"{v}pp" + ("  (normal)" if v == 1 else
                                  f"  HP x{hp_multiplier(v)}  dmg/XP x{damage_multiplier(v):g}")
                screen.blit(ctx.font.render(txt, True, WHITE), (r.x + 8, r.y + 4))

        pygame.display.flip()
        ctx.clock.tick(30)


# ---------------------------------------------------------------- join (find games on the home network)

def _scan_in_background(port):
    """Start a scan in a thread; returns a dict that gets {"done": True, "games": [...]} when finished."""
    import threading
    from game.net.discovery import scan
    state = {"done": False, "games": []}

    def work():
        try:
            state["games"] = scan(port)
        finally:
            state["done"] = True
    threading.Thread(target=work, daemon=True).start()
    return state


def join_select(ctx, port=None):
    """Find co-op games (this computer + home network) and pick one. Returns {"join": True, "address": ip},
    None to go back, or 'quit'. R = search again, T = type an address (if a game isn't found)."""
    from game.net.discovery import describe, lan_address
    from game.net.server import DEFAULT_PORT
    port = port or DEFAULT_PORT
    state = _scan_in_background(port)
    sel = 0
    typing, typed, msg = False, "", ""
    mine = lan_address()
    while True:
        screen = _screen()
        W, H = screen.get_size()
        games = state["games"]
        sel = min(sel, max(0, len(games) - 1))
        for event in pygame.event.get():
            if _handle_common(event) == "quit":
                return "quit"
            if event.type != pygame.KEYDOWN:
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and not typing:
                    for i in range(len(games)):
                        if pygame.Rect(W // 2 - 330, 170 + i * 50, 660, 42).collidepoint(event.pos):
                            if sel == i and games[i]["compatible"]:
                                return {"join": True, "address": games[i]["address"]}
                            sel = i
                continue
            if typing:
                if event.key == pygame.K_ESCAPE:
                    typing = False
                elif event.key == pygame.K_RETURN:
                    addr = typed.strip()
                    if _valid_ipv4(addr):
                        return {"join": True, "address": addr}
                    msg = f"'{addr}' is not an address like 192.168.1.23"
                elif event.key == pygame.K_BACKSPACE:
                    typed = typed[:-1]
                elif event.unicode and event.unicode in "0123456789." and len(typed) < 15:
                    typed += event.unicode
                continue
            if event.key == pygame.K_ESCAPE:
                return None
            if event.key in (pygame.K_UP, pygame.K_w) and games:
                sel = (sel - 1) % len(games)
            if event.key in (pygame.K_DOWN, pygame.K_s) and games:
                sel = (sel + 1) % len(games)
            if event.key == pygame.K_r and state["done"]:
                state, msg = _scan_in_background(port), ""
            if event.key == pygame.K_t:
                typing, typed, msg = True, "", ""
            if event.key in (pygame.K_RETURN, pygame.K_SPACE) and games:
                if games[sel]["compatible"]:
                    return {"join": True, "address": games[sel]["address"]}
                msg = "That game runs a different version — both computers need the same copy of the game."

        screen.fill(BG)
        t = ctx.title_font.render("JOIN A GAME", True, GOLD)
        screen.blit(t, (W // 2 - t.get_width() // 2, 50))
        net = f"Your computer: LAN {mine}" if mine else "This computer isn't on a home network"
        screen.blit(ctx.font.render(net, True, LIGHT_GRAY), (W // 2 - 330, 110))
        status = "Searching this computer and your home network..." if not state["done"] else \
            (f"Found {len(games)} game(s)." if games else "No games found. Is the host on the same Wi-Fi? (R = search again)")
        screen.blit(ctx.font.render(status, True, LIGHT_GRAY), (W // 2 - 330, 135))
        for i, g in enumerate(games):
            rect = pygame.Rect(W // 2 - 330, 170 + i * 50, 660, 42)
            pygame.draw.rect(screen, (40, 80, 40) if i == sel else (30, 30, 40), rect, border_radius=6)
            pygame.draw.rect(screen, GOLD if i == sel else GRAY, rect, 2 if i == sel else 1, border_radius=6)
            color = WHITE if g["compatible"] else RED
            label = describe(g) + ("" if g["compatible"] else "  (different game version)")
            screen.blit(ctx.font.render(label, True, color), (rect.x + 12, rect.y + 13))
        if typing:
            box = pygame.Rect(W // 2 - 330, H - 120, 660, 36)
            pygame.draw.rect(screen, (30, 30, 50), box)
            pygame.draw.rect(screen, GOLD, box, 2)
            screen.blit(ctx.big_font.render(f"Address: {typed}_", True, WHITE), (box.x + 10, box.y + 6))
        if msg:
            m = ctx.font.render(msg, True, RED)
            screen.blit(m, (W // 2 - m.get_width() // 2, H - 75))
        hint = ("Type the host's address, Enter = join, ESC = cancel" if typing else
                "Up/Down + Enter = join    R = search again    T = type an address    ESC = back")
        h = ctx.font.render(hint, True, GRAY)
        screen.blit(h, (W // 2 - h.get_width() // 2, H - 40))
        pygame.display.flip()
        ctx.clock.tick(30)


def _valid_ipv4(addr):
    import ipaddress
    try:
        ipaddress.IPv4Address(addr)
        return True
    except ValueError:
        return False


# ---------------------------------------------------------------- flow

def run_menus(ctx, preset_map=None):
    """Character select -> map select. Returns (char_data, choice) where choice is {"map": path, "pp": n} (solo),
    {"host": path, "pp": n[, "lan": True]} or {"join": True, "address": ip} — or a plain path if preset_map was
    given; None to quit the game.
    If preset_map is given (--map on the command line) the map screen is skipped."""
    while True:
        action, char = character_select(ctx)
        if action == "quit":
            return None
        if preset_map:
            return char, preset_map
        choice = map_select(ctx, char)
        if choice == "quit":
            return None
        if choice is None:
            continue  # ESC on map select -> back to character select
        return char, choice
