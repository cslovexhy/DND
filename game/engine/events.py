"""Simulation -> view events (pure data; no pygame).

Events with a `player_id` concern only that player (their level-up, quest dialogue, skill rebind);
clients ignore other players' personal events. Events without one (FloatText, Ring) are for everyone.

The simulation never draws anything. When something happens that the player should see or hear
(damage numbers, rings, level-ups) it appends one of these to World.events; the client turns them
into floating text / effects / sounds. Over the network (design/06 phase 4) these are the messages
the host sends to clients.
"""
from dataclasses import dataclass


@dataclass
class FloatText:
    x: float
    y: float
    text: str
    color: tuple


@dataclass
class Ring:
    """Expanding AoE ring effect."""
    x: float
    y: float
    radius: float
    color: tuple


@dataclass
class LevelUp:
    x: float
    y: float
    player_id: int = 0


@dataclass
class SkillUp:
    """The player's hero unlocked a new skill (is_new) or raised one to its next level at `hero_level`."""
    hero_level: int
    key: str
    name: str
    skill_level: int
    max_level: int
    is_new: bool
    text: str          # what the skill does at this level, with real numbers
    player_id: int = 0


@dataclass
class QuestReady:
    """A quest objective was just completed (client shows a popup; host persists progress)."""
    title: str
    player_id: int = 0


@dataclass
class BindRightSkill:
    """The client should switch the player's right-click skill slot to this ability key."""
    ability_key: str
    player_id: int = 0


@dataclass
class NpcDialogue:
    """An NPC conversation: the client shows a quest panel, speaks the text and saves progress."""
    quest: dict        # snapshot.quest_info(): title, description, objectives, rewards
    mode: str          # "accept" or "turnin"
    npc_name: str
    speech: str
    voice: str
    player_id: int = 0


GOLD = (255, 215, 0)
HP_RED = (200, 50, 50)


# --- (de)serialization for the network (design/06 phase 4) ---
_BY_NAME = {cls.__name__: cls for cls in (FloatText, Ring, LevelUp, SkillUp, QuestReady, BindRightSkill, NpcDialogue)}


def to_dict(ev):
    import dataclasses
    return {"type": type(ev).__name__, **dataclasses.asdict(ev)}


def from_dict(d):
    d = dict(d)
    cls = _BY_NAME[d.pop("type")]
    if "color" in d:
        d["color"] = tuple(d["color"])
    return cls(**d)
