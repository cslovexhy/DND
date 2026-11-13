"""Which attack / cast pose a hero is drawn in right now (pure; no pygame).

The snapshot reports each hero's last attack as [kind, seconds since it started, count] ("melee" swing, instant
"cast", channel "release") and the current channel's progress and skill. This picks (style, frame); the art for each
frame is in client/gear_art.py. Cosmetic only: the simulation never reads any of it.
"""

THRUST_WEAPONS = {"dagger", "spear"}         # stab forward; every other weapon chops
STYLES = {  # style -> frame names (frame 0 is always the plain idle composite)
    "chop": ("idle", "windup", "strike", "follow"),
    "thrust": ("idle", "pull", "thrust", "recover"),
    "dual": ("idle", "right", "left"),
    "cast": ("idle", "half", "raised", "flash"),
}
# (frame, until seconds since the attack started); after the last one the hero is idle again.
TIMELINES = {
    "chop": (("windup", 0.10), ("strike", 0.20), ("follow", 0.38)),
    "thrust": (("pull", 0.08), ("thrust", 0.20), ("recover", 0.32)),
    "cast": (("half", 0.08), ("raised", 0.18), ("flash", 0.30)),
    "release": (("flash", 0.25),),
}
DUAL_STAB_SECS = 0.20
CHANNEL_HALF_RAISE = 0.15      # a channel's first 15% is the half raise, then raised + glowing until it ends


def swing_style(main, off):
    """How this gear's basic attack animates: "dual" (two stabbing weapons), "thrust" or "chop"."""
    if main in THRUST_WEAPONS and off in THRUST_WEAPONS:
        return "dual"
    return "thrust" if main in THRUST_WEAPONS or main is None else "chop"


def pose_for(main, off, attack=None, channel_progress=None, channel_skill=None):
    """(style, frame) the hero should be drawn in right now; (None, "idle") when not attacking."""
    if channel_progress is not None and channel_skill != "Charge":
        return "cast", ("half" if channel_progress < CHANNEL_HALF_RAISE else "raised")
    if not attack:
        return None, "idle"
    kind, age, count = attack
    if kind == "melee":
        style = swing_style(main, off)
        if style == "dual":
            return ("dual", ("right" if count % 2 else "left")) if age < DUAL_STAB_SECS else (None, "idle")
    else:
        style = kind                                   # "cast" / "release"
    for frame, until in TIMELINES[style]:
        if age < until:
            return ("cast" if style == "release" else style), frame
    return None, "idle"
