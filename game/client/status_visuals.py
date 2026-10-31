"""Which status effects a hero shows on screen (pure; no pygame).

One definition for everyone: your own hero, other players and companions all go through this, so every
player's screen shows the same effects for the same hero (from the snapshot data the host sends).
"""


def status_visuals(e):
    """{effect: value} for an entity view. Effects: stealth, poison, chill, shield, renew, channel (0..1)."""
    fx = {}
    if getattr(e, "stealthed", False):
        fx["stealth"] = True
    if "POISONED" in getattr(e, "conditions", ()):
        fx["poison"] = True
    if getattr(e, "chill_visual", 0.0) > 0:
        fx["chill"] = True
    if getattr(e, "absorb_shield", 0) > 0:
        fx["shield"] = True
    if "Renew" in getattr(e, "buffs", ()):
        fx["renew"] = True
    if getattr(e, "channel", None) is not None:
        fx["channel"] = e.channel
    return fx
