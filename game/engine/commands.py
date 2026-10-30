"""Player commands: the only way a client changes the simulation (pure data; no pygame).

A client turns raw input (mouse/keyboard) into these intents and submits them with World.submit().
They reference entities by id (never by object) and carry only plain values, so they can be
logged, replayed in tests, and later sent over the network to the host (design/06, phases 2 and 4).
The host validates every command; the client never decides the outcome.
"""
from dataclasses import dataclass
from typing import Optional


@dataclass
class MoveTo:
    """Walk to a world position (ground click). Cancels channels, targets and queued casts."""
    x: float
    y: float


@dataclass
class SelectTarget:
    """Select an enemy: walk into range and auto-attack. Needs line of sight."""
    target_id: int


@dataclass
class Cast:
    """Cast the ability bound to `ab_key` at a position and/or target.
    `fallback_move`: if the skill is on cooldown, walk to (x, y) instead (right-click behaviour)."""
    ab_key: str
    x: float
    y: float
    target_id: Optional[int] = None
    fallback_move: bool = False


@dataclass
class InteractNpc:
    """Talk to an NPC if in range, otherwise walk to it."""
    npc_id: int


@dataclass
class AmbushTarget:
    """Stealthed: queue a walk-to-target Ambush on this monster."""
    target_id: int


@dataclass
class UsePotion:
    pass


@dataclass
class ToggleAutopilot:
    pass


@dataclass
class ToggleCompanion:
    """Summon the AI companion of this class, or dismiss it if already summoned."""
    class_name: str


@dataclass
class CancelChannel:
    """Cancel a channeled spell (ESC while channeling)."""
    pass


@dataclass
class BindLeftSkill:
    """Which ability the left-click auto-attack uses (the client's skill-slot choice)."""
    ab_key: str


@dataclass
class HoldPosition:
    """Shift held: auto-attack does not walk toward an out-of-range target."""
    on: bool
