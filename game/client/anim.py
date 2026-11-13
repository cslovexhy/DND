"""Which attack / cast pose a hero is drawn in right now (pure; no pygame).

The snapshot reports each hero's last attack as [style, seconds since it started, count, hand]:
  style  "thrust" / "chop" / "sweep" (melee: content/equipment.skill_anim picks it from the skill and the weapon),
         "raise" (an instant spell, buff or heal) or "release" (a channel just finished)
  hand   "main" or "off" (dual wielders alternate hands on melee attacks: content/equipment.attack_hand)
plus the current channel's progress and skill. This picks (style, frame); the art for each frame is in
client/gear_art.py. Cosmetic only: the simulation never reads any of it.
"""

STYLES = {  # art style -> frame names (frame 0 is always the plain idle composite)
    "chop": ("idle", "windup", "strike", "follow"),
    "sweep": ("idle", "windup", "strike", "follow"),
    "thrust": ("idle", "pull", "thrust", "recover"),
    "chop_l": ("idle", "windup", "strike", "follow"),       # off hand (left arm, across the body)
    "thrust_l": ("idle", "pull", "thrust", "recover"),
    "cast": ("idle", "half", "raised", "flash"),
}
# (frame, until seconds since the attack started); after the last one the hero is idle again.
TIMELINES = {
    "chop": (("windup", 0.10), ("strike", 0.20), ("follow", 0.38)),
    "sweep": (("windup", 0.10), ("strike", 0.22), ("follow", 0.38)),
    "thrust": (("pull", 0.08), ("thrust", 0.20), ("recover", 0.32)),
    "raise": (("half", 0.08), ("raised", 0.18), ("flash", 0.30)),
    "release": (("flash", 0.25),),
}
OFF_HAND = {"chop": "chop_l", "sweep": "chop_l", "thrust": "thrust_l"}
CHANNEL_HALF_RAISE = 0.15      # a channel's first 15% is the half raise, then raised + glowing until it ends
NO_POSE_CHANNELS = {"Charge"}  # a dash wind-up, not a spell


def pose_for(attack=None, channel_progress=None, channel_skill=None):
    """(art style, frame) the hero should be drawn in right now; (None, "idle") when not attacking."""
    if channel_progress is not None and channel_skill not in NO_POSE_CHANNELS:
        return "cast", ("half" if channel_progress < CHANNEL_HALF_RAISE else "raised")
    if not attack:
        return None, "idle"
    style, age = attack[0], attack[1]
    hand = attack[3] if len(attack) > 3 else "main"
    if style not in TIMELINES:
        return None, "idle"
    for frame, until in TIMELINES[style]:
        if age < until:
            if style in ("raise", "release"):
                return "cast", frame
            return (OFF_HAND[style] if hand == "off" else style), frame
    return None, "idle"
