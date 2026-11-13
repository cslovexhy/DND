"""Player commands: the only way a client changes the simulation (pure data; no pygame).

A client turns raw input (mouse/keyboard) into these intents and submits them with World.submit().
They reference entities by id (never by object) and carry only plain values, so they can be
logged, replayed in tests, and later sent over the network to the host (design/06, phases 2 and 4).
The host validates every command; the client never decides the outcome.
"""
import dataclasses
from dataclasses import dataclass
from typing import Optional


@dataclass
class MoveTo:
    """Walk to a world position (ground click). Cancels channels, targets and queued casts."""
    x: float
    y: float


@dataclass
class SelectTarget:
    """Attack an enemy (right-click it): target it, walk into range and auto-attack. Needs line of sight."""
    target_id: int


@dataclass
class SetTarget:
    """Target an enemy or a friendly hero without moving (left-click, Tab); None clears the target (Esc).
    Hotbar skills go to the target. While auto-attacking, a newly targeted enemy becomes the one attacked."""
    target_id: Optional[int] = None


@dataclass
class MoveDir:
    """WASD: walk in this direction (each of dx, dy is -1, 0 or 1) until a new MoveDir; (0, 0) stops."""
    dx: int = 0
    dy: int = 0


@dataclass
class Cast:
    """Cast the ability bound to `ab_key` at a position and/or target.
    `fallback_move`: if the skill is on cooldown, walk to (x, y) instead (right-click behaviour).
    `ally_id`: friendly hero under the cursor (player, ally or companion); support skills
    (Wall, Renew, Holy Light) land on them instead of the caster."""
    ab_key: str
    x: float
    y: float
    target_id: Optional[int] = None
    fallback_move: bool = False
    ally_id: Optional[int] = None


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
class UseItem:
    """Use the item in this backpack slot (right-click it in the open backpack). Weapons and shields: equip it."""
    slot: int


@dataclass
class Unequip:
    """Take the item in this equipment slot ("main" / "off") off, back into the backpack (right-click the slot in
    the character window)."""
    slot: str


@dataclass
class Buy:
    """Buy one of `item` from vendor NPC `npc_id` (must be near it, with the money and backpack room)."""
    npc_id: int
    item: str


@dataclass
class Train:
    """Learn the next level of skill `ab_key` from class trainer NPC `npc_id` (must be near it, at the level, with
    the money)."""
    npc_id: int
    ab_key: str


@dataclass
class PickUp:
    """Pick up a ground item (click its icon): walk to it, then put it in the backpack."""
    item_id: int


@dataclass
class TradeOpen:
    """Start trading with another player (their hero's id): both get a trade window."""
    hero_id: int


@dataclass
class TradeOffer:
    """Offer 1 of the item in this backpack slot (drag it onto the trade window)."""
    slot: int


@dataclass
class TradeTake:
    """Take 1 of this item back out of your offer."""
    item: str


@dataclass
class TradeAccept:
    pass


@dataclass
class TradeCancel:
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


# --- (de)serialization: commands are plain data, so they can be logged and sent over a wire ---
_BY_NAME = {cls.__name__: cls for cls in (
    MoveTo, SelectTarget, Cast, InteractNpc, AmbushTarget, UsePotion, ToggleAutopilot, ToggleCompanion,
    CancelChannel, BindLeftSkill, HoldPosition, UseItem, Unequip, PickUp, SetTarget, MoveDir, TradeOpen,
    TradeOffer, TradeTake, TradeAccept, TradeCancel, Buy, Train)}


def to_dict(cmd):
    return {"type": type(cmd).__name__, **dataclasses.asdict(cmd)}


def from_dict(d):
    d = dict(d)
    return _BY_NAME[d.pop("type")](**d)
