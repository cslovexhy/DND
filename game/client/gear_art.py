"""In-hand gear art (client only; pygame): small hand-drawn weapon / shield sprites put on the 16 px hero tiles.

Each item is drawn once as a pixel grid in the dungeon sheet's colours, with a grip point (the pixel that sits in
the hand). A hero is composed at native 16 px size (hero tile, then the off-hand item, then the main-hand item) and
cached per (hero tile, main, off); the caller scales the result like any sprite, so it stays pixel-crisp.
"""
import pygame

PAL = {
    "o": (63, 38, 49),      # outline (the sheet's)
    "B": (192, 203, 220),   # light metal
    "C": (139, 155, 180),   # mid metal
    "D": (82, 96, 124),     # dark metal
    "E": (189, 108, 74),    # wood
    "F": (118, 59, 54),     # dark wood
    "G": (247, 194, 130),   # skin
    "K": (155, 76, 163),    # purple dark
    "L": (209, 118, 208),   # purple light
    "N": (99, 199, 233),    # cyan gem
    "M": (214, 245, 255),   # gem highlight
}

# item -> (pixel rows, grip (x, y)). Weapons point up; the grip is the pixel held in the hand.
SPRITES = {
    "dagger": ([
        "..o..",
        ".oBo.",
        ".oBo.",
        ".oCo.",
        "ooooo",
        "oCDCo",
        "ooooo",
        ".oFo.",
        ".ooo.",
    ], (2, 7)),
    "wooden_sword": ([
        "..o..",
        ".oEo.",
        ".oEo.",
        ".oEo.",
        ".oEo.",
        ".oFo.",
        "ooooo",
        "oFFFo",
        "ooooo",
        ".oFo.",
        ".ooo.",
    ], (2, 9)),
    "short_sword": ([
        "..o..",
        ".oBo.",
        ".oBo.",
        ".oBo.",
        ".oBo.",
        ".oCo.",
        "ooooo",
        "oCDCo",
        "ooooo",
        ".oFo.",
        ".oFo.",
        ".ooo.",
    ], (2, 10)),
    "cleaver": ([
        "..oo.",
        ".oBBo",
        "oBBCo",
        "oBCCo",
        "oBCCo",
        "ooCoo",
        ".oDo.",
        ".oFo.",
        ".oFo.",
        ".ooo.",
    ], (2, 8)),
    "broadsword": ([
        "..o..",
        ".oBo.",
        "oBBCo",
        "oBBCo",
        "oBBCo",
        "oBBCo",
        "oBBCo",
        "oBCCo",
        "ooooo",
        "oCDCo",
        "ooooo",
        ".oFo.",
        ".oFo.",
        ".ooo.",
    ], (2, 12)),
    "axe": ([
        "...oo.",
        "..oBBo",
        "ooCCBo",
        "oEDCBo",
        "ooCCBo",
        ".oEoo.",
        ".oEo..",
        ".oFo..",
        ".oEo..",
        ".oFo..",
        ".ooo..",
    ], (2, 9)),
    "double_axe": ([
        ".oo.....oo.",
        "oBBo...oBBo",
        "oBCCoooCCBo",
        "oBCCDEDCCBo",
        "oBCCoEoCCBo",
        "oBBo.E.oBBo",
        ".oo.oEo.oo.",
        "....oEo....",
        "....oFo....",
        "....oEo....",
        "....oFo....",
        "....oEo....",
        "....oEo....",
        "....ooo....",
    ], (5, 11)),
    "warhammer": ([
        "ooooooo",
        "oBBBBCo",
        "oBCCCDo",
        "oBCCCDo",
        "ooooooo",
        "..oEo..",
        "..oFo..",
        "..oEo..",
        "..oFo..",
        "..oEo..",
        "..oEo..",
        "..ooo..",
    ], (3, 10)),
    "spear": ([
        "..o..",
        ".oBo.",
        "oBBCo",
        ".oCo.",
        ".oDo.",
        ".oEo.",
        ".oEo.",
        ".oFo.",
        ".oEo.",
        ".oEo.",
        ".oFo.",
        ".oEo.",
        ".oEo.",
        ".oEo.",
        ".ooo.",
    ], (2, 11)),
    "wand": ([
        ".o.",
        "oLo",
        "oKo",
        "oEo",
        "oEo",
        "oFo",
        "oEo",
        "ooo",
    ], (1, 5)),
    "staff": ([
        ".ooo.",
        "oMNNo",
        "oNNNo",
        ".oNo.",
        ".oEo.",
        ".oFo.",
        ".oEo.",
        ".oEo.",
        ".oFo.",
        ".oEo.",
        ".oEo.",
        ".oFo.",
        ".oEo.",
        ".oEo.",
        ".oEo.",
        ".ooo.",
    ], (2, 11)),
    "buckler": ([
        "..ooo..",
        ".oCCCo.",
        "oCBBBCo",
        "oCBDBCo",
        "oCBBBCo",
        ".oCCCo.",
        "..ooo..",
    ], (3, 3)),
    "round_shield": ([
        "..ooo..",
        ".oEEEo.",
        "oEFFFEo",
        "oEFBFEo",
        "oEFFFEo",
        ".oEEEo.",
        "..ooo..",
    ], (3, 3)),
}
SHIELDS = {"buckler", "round_shield"}

# Hand anchors on the 16x16 hero tiles (all front-facing): weapons sit just outside the body, shields on the hand.
RIGHT_HAND, LEFT_HAND = (14, 12), (1, 12)
HAND_COLOR = {"fighter": "D", "paladin": "G", "cleric": "G", "wizard": "G", "rogue": "G"}   # fist over the grip

# Room around the 16 px tile so weapons can stick out (the body stays at (PAD_X, PAD_TOP) in the composed image).
PAD_X, PAD_TOP, PAD_BOTTOM = 6, 10, 2

_item_cache = {}
_hero_cache = {}


def _item_surface(item):
    if item not in _item_cache:
        rows, _ = SPRITES[item]
        s = pygame.Surface((max(len(r) for r in rows), len(rows)), pygame.SRCALPHA)
        for y, row in enumerate(rows):
            for x, ch in enumerate(row):
                if ch != ".":
                    s.set_at((x, y), PAL[ch])
        _item_cache[item] = s
    return _item_cache[item]


def _place(canvas, item, hand, hand_color):
    rows, (gx, gy) = SPRITES[item]
    hx, hy = hand
    canvas.blit(_item_surface(item), (PAD_X + hx - gx, PAD_TOP + hy - gy))
    if item not in SHIELDS and hand_color:
        for dy in (0, 1):                     # the fist wrapped around the grip
            canvas.set_at((PAD_X + hx, PAD_TOP + hy + dy), PAL[hand_color])


def compose(hero_tile, sprite_key, main=None, off=None):
    """The 16 px hero tile with its gear, at native size: a (16 + 2*PAD_X) x (16 + PAD_TOP + PAD_BOTTOM) surface,
    the body at (PAD_X, PAD_TOP). `hero_tile` is the 16x16 tile; cached per (sprite_key, main, off)."""
    key = (sprite_key, main, off)
    if key not in _hero_cache:
        canvas = pygame.Surface((16 + 2 * PAD_X, 16 + PAD_TOP + PAD_BOTTOM), pygame.SRCALPHA)
        canvas.blit(hero_tile, (PAD_X, PAD_TOP))
        fist = HAND_COLOR.get(sprite_key, "G")
        if off in SPRITES:
            _place(canvas, off, LEFT_HAND, fist)
        if main in SPRITES:
            _place(canvas, main, RIGHT_HAND, fist)
        _hero_cache[key] = canvas
    return _hero_cache[key]


def body_offset(scale):
    """Where the 16 px body starts inside a composed image scaled by `scale` (px per source pixel)."""
    return PAD_X * scale, PAD_TOP * scale


# --- attack / cast poses ------------------------------------------------------------------------------------------
# A pose redraws the right arm as one straight 2 px line from a fixed shoulder (so it never bends), with the weapon at
# the hand turned to an angle (0 = up; 90s are lossless, 45s pixel-snapped). The sprite's own arm is painted over
# with the outline colour first. Poses use a bigger canvas (POSE_PAD_*) so swung weapons have room.
import math

POSE_PAD_X, POSE_PAD_TOP, POSE_PAD_BOTTOM = 18, 20, 6
POSE_W, POSE_H = 16 + 2 * POSE_PAD_X, 16 + POSE_PAD_TOP + POSE_PAD_BOTTOM
SHOULDER_R = (13, 9)
OUTLINE = PAL["o"]
ARM_COLORS = {  # sprite_key -> (sleeve, fist)
    "fighter": (PAL["B"], PAL["D"]), "paladin": (PAL["G"], (225, 154, 101)), "rogue": (PAL["B"], PAL["G"]),
    "wizard": (PAL["K"], PAL["G"]), "cleric": ((189, 108, 74), PAL["G"]),
}
from game.client.anim import THRUST_WEAPONS, STYLES, swing_style, pose_for   # noqa: F401 (re-exported)
_pose_cache = {}


class _Canvas:
    def __init__(self, hero_tile):
        self.s = pygame.Surface((POSE_W, POSE_H), pygame.SRCALPHA)
        self.s.blit(hero_tile, (POSE_PAD_X, POSE_PAD_TOP))

    def get(self, x, y):
        X, Y = POSE_PAD_X + x, POSE_PAD_TOP + y
        return self.s.get_at((X, Y)) if 0 <= X < POSE_W and 0 <= Y < POSE_H else pygame.Color(0, 0, 0, 0)

    def put(self, x, y, col):
        X, Y = POSE_PAD_X + x, POSE_PAD_TOP + y
        if 0 <= X < POSE_W and 0 <= Y < POSE_H:
            self.s.set_at((X, Y), col)

    def blit(self, surf, x, y):
        self.s.blit(surf, (POSE_PAD_X + x, POSE_PAD_TOP + y))

    def overlay(self):
        return pygame.Surface((POSE_W, POSE_H), pygame.SRCALPHA)

    def erase_arm(self, side):
        for y in (10, 11, 12, 13):
            for x in ((12, 13) if side == "R" else (2, 3)):
                if self.get(x, y).a:
                    self.put(x, y, OUTLINE)

    def arm(self, key, shoulder, hand):
        sleeve, fist = ARM_COLORS.get(key, (PAL["G"], PAL["G"]))
        (x0, y0), (x1, y1) = shoulder, hand
        n = max(abs(x1 - x0), abs(y1 - y0), 1)
        pix = {}
        for i in range(n):
            x, y = round(x0 + (x1 - x0) * i / n), round(y0 + (y1 - y0) * i / n)
            for dx, dy in ((0, 0), (0, 1), (1, 0)):
                pix[(x + dx, y + dy)] = sleeve
        for dx, dy in ((0, 0), (1, 0), (0, 1), (1, 1)):
            pix[(x1 + dx, y1 + dy)] = fist
        for (x, y) in list(pix):
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                q = (x + dx, y + dy)
                if q not in pix and self.get(*q).a == 0:
                    self.put(q[0], q[1], OUTLINE)
        for (x, y), col in pix.items():
            self.put(x, y, col)

    def weapon(self, item, grip, deg):
        if item not in SPRITES:
            return
        _, (gx, gy) = SPRITES[item]
        s = _item_surface(item)
        w, h = s.get_size()
        r = pygame.transform.rotate(s, -deg)
        a = math.radians(deg)
        vx, vy = gx - (w - 1) / 2, gy - (h - 1) / 2
        rx, ry = vx * math.cos(a) - vy * math.sin(a), vx * math.sin(a) + vy * math.cos(a)
        ngx = round((r.get_width() - 1) / 2 + rx)
        ngy = round((r.get_height() - 1) / 2 + ry)
        self.blit(r, grip[0] - ngx, grip[1] - ngy)

    def off_item(self, item):
        if item in SPRITES:
            _, (gx, gy) = SPRITES[item]
            self.blit(_item_surface(item), LEFT_HAND[0] - gx, LEFT_HAND[1] - gy)

    def smear(self, center, radius, a0, a1, thick=3):
        lay = self.overlay()
        steps = int(abs(a1 - a0) * radius / 20) + 8
        for i in range(steps + 1):
            t = i / steps
            ang = math.radians(a0 + (a1 - a0) * t)
            for k in range(thick):
                x = round(center[0] + (radius - k) * math.cos(ang))
                y = round(center[1] + (radius - k) * math.sin(ang))
                X, Y = POSE_PAD_X + x, POSE_PAD_TOP + y
                if 0 <= X < POSE_W and 0 <= Y < POSE_H:
                    lay.set_at((X, Y), (235, 245, 255, int(60 + 170 * t)))
        self.s.blit(lay, (0, 0))

    def speed_lines(self, rows):
        lay = self.overlay()
        for (x0, y), x1 in rows:
            for x in range(x0, x1 + 1):
                X, Y = POSE_PAD_X + x, POSE_PAD_TOP + y
                if 0 <= X < POSE_W and 0 <= Y < POSE_H:
                    lay.set_at((X, Y), (235, 245, 255, 90 + 20 * (x - x0)))
        self.s.blit(lay, (0, 0))

    def glow(self, center, r, alpha):
        lay = self.overlay()
        for rr, a in ((r, alpha // 3), (r - 1, alpha // 2), (max(1, r - 2), alpha)):
            pygame.draw.circle(lay, (140, 220, 255, a), (POSE_PAD_X + center[0], POSE_PAD_TOP + center[1]), rr)
        self.s.blit(lay, (0, 0))


def _idle_on_pose_canvas(hero_tile, key, main, off):
    c = _Canvas(hero_tile)
    c.s.fill((0, 0, 0, 0))
    c.s.blit(compose(hero_tile, key, main, off), (POSE_PAD_X - PAD_X, POSE_PAD_TOP - PAD_TOP))
    return c


def _draw_pose(hero_tile, key, main, off, style, frame):
    sx, sy = SHOULDER_R
    if style == "dual" and frame == "left":
        c = _idle_on_pose_canvas(hero_tile, key, main, None)       # right hand back at the side
        c.erase_arm("L")
        c.speed_lines([((-4, 11), 1), ((-6, 13), 0)])
        c.weapon(off, (15, 11), 90)
        c.arm(key, (2, 11), (15, 11))
        return c.s
    c = _Canvas(hero_tile)
    c.erase_arm("R")
    if style != "dual":
        c.off_item(off)
    if style == "chop":
        hand, deg = {"windup": ((sx, sy - 6), -45), "strike": ((sx + 4, sy), 90),
                     "follow": ((sx + 4, sy + 4), 135)}[frame]
        if frame == "strike" and main in SPRITES:
            gy = SPRITES[main][1][1]
            c.smear(SHOULDER_R, (hand[0] - sx) + gy, -100, -8)
        c.weapon(main, hand, deg)
        c.arm(key, SHOULDER_R, hand)
    elif style in ("thrust", "dual"):
        if style == "dual":
            c.off_item(off)
        reach = {"pull": 1, "thrust": 5, "recover": 3, "right": 5}[frame]
        if frame in ("thrust", "right"):
            c.speed_lines([((-6, sy - 1), -1), ((-8, sy + 1), -2), ((-5, sy + 3), 0)])
        hand = (sx + reach, sy)
        c.weapon(main, hand, 90)
        c.arm(key, SHOULDER_R, hand)
    elif style == "cast":
        hand = (sx + 3, sy - 3) if frame == "half" else (sx, sy - 6)
        c.weapon(main, hand, 0)
        c.arm(key, SHOULDER_R, hand)
        tip = (hand[0], hand[1] - (SPRITES[main][1][1] - 1 if main in SPRITES else 1))
        if frame == "raised":
            c.glow(tip, 4, 120)
        elif frame == "flash":
            c.glow(tip, 6, 200)
            for dx, dy in ((-4, -1), (4, 0), (-2, -4), (3, -4), (0, -6), (-5, 2), (5, 3)):
                c.put(tip[0] + dx, tip[1] + dy, PAL["M"])
    return c.s


def figure(hero_tile, sprite_key, main=None, off=None, style=None, frame="idle"):
    """The hero with its gear in a pose: (surface, (pad_x, pad_top)) — where the 16 px body starts inside it.
    style/frame from STYLES; frame "idle" (or no style) is the plain gear composite. Cached per pose."""
    if style is None or frame == "idle":
        return compose(hero_tile, sprite_key, main, off), (PAD_X, PAD_TOP)
    key = (sprite_key, main, off, style, frame)
    if key not in _pose_cache:
        _pose_cache[key] = _draw_pose(hero_tile, sprite_key, main, off, style, frame)
    return _pose_cache[key], (POSE_PAD_X, POSE_PAD_TOP)

