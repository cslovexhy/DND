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
