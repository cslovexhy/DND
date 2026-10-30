"""Simulation -> view events (pure data; no pygame).

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
