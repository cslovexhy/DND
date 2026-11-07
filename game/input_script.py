"""Scripted player input for headless regression tests (client side; uses pygame events).

A script is a JSON list of events keyed by simulation tick (one tick = one headless loop iteration):

  {"tick": 5,  "type": "key",   "key": "p"}                        # pygame.K_p (toggle autopilot)
  {"tick": 6,  "type": "key",   "key": "w", "hold": 30}            # hold W for 30 ticks (KEYDOWN, then KEYUP)
  {"tick": 6,  "type": "mods",  "mods": ["shift"]}                 # held modifier keys from now on
  {"tick": 10, "type": "click", "button": 1, "at": "nearest_monster"}
  {"tick": 20, "type": "click", "button": 3, "at": {"dx": 100, "dy": 0}}   # offset from the hero (world px)
  {"tick": 30, "type": "click", "button": 3, "at": [1200, 900]}            # absolute world position

`at` may also be "nearest_npc", "nearest_ally" (other player / companion), "hero", "nearest_item" (a ground
item / monster drop), {"backpack_slot": N} (that slot of the open backpack panel, on screen) or {"hotbar_slot": N}
(slot N of the hotbar, 0 = the first). A drag presses the left button on one place and releases it on another:

  {"tick": 40, "type": "drag", "from": {"hotbar_slot": 4}, "to": {"hotbar_slot": 1}}   # swap hotbar slots 5 and 2 The events are posted as real pygame events, so the
normal input code path is exercised exactly as if a human had clicked.
"""
import json

import pygame


class InputScript:
    def __init__(self, path):
        with open(path, encoding="utf-8") as f:
            self.events = sorted(json.load(f), key=lambda e: e["tick"])
        self.next_idx = 0
        self.mods = 0   # pygame KMOD_* bits currently "held"

    def key_mods(self):
        return self.mods

    def _resolve(self, at, hero, game_state, npcs):
        if at == "hero":
            return hero.x, hero.y
        if at == "nearest_monster":
            cands = [m for m in game_state.alive_monsters if not getattr(m, "stealthed", False)]
            m = min(cands, key=lambda m: hero.distance_to(m)) if cands else None
            return (m.x, m.y) if m else (hero.x, hero.y)
        if at == "nearest_ally":   # another player's hero or a companion
            friends = [f for f in getattr(game_state, "allies", []) + getattr(game_state, "companions", []) if f.alive]
            f = min(friends, key=lambda f: hero.distance_to(f)) if friends else None
            return (f.x, f.y) if f else (hero.x, hero.y)
        if at == "nearest_item":
            items = getattr(game_state, "ground_items", [])
            g = min(items, key=lambda g: (g.x - hero.x) ** 2 + (g.y - hero.y) ** 2) if items else None
            return (g.x, g.y) if g else (hero.x, hero.y)
        if at == "nearest_npc":
            n = min(npcs, key=lambda n: hero.distance_to(n)) if npcs else None
            return (n.x, n.y) if n else (hero.x, hero.y)
        if isinstance(at, dict):
            return hero.x + at.get("dx", 0), hero.y + at.get("dy", 0)
        return at[0], at[1]

    def post_due(self, tick, hero, game_state, npcs, width, height, cam_zoom, slot_pos=None, hotbar_pos=None):
        """Post every event scheduled for this tick as pygame events. `slot_pos(i)` / `hotbar_pos(i)` -> screen
        (x, y) of backpack slot i / hotbar slot i (the client's layout)."""
        def screen_at(at):
            if isinstance(at, dict) and "backpack_slot" in at:
                return slot_pos(at["backpack_slot"])
            if isinstance(at, dict) and "hotbar_slot" in at:
                return hotbar_pos(at["hotbar_slot"])
            wx, wy = self._resolve(at, hero, game_state, npcs)
            return int((wx - hero.x) * cam_zoom + width // 2), int((wy - hero.y) * cam_zoom + height // 2)

        while self.next_idx < len(self.events) and self.events[self.next_idx]["tick"] <= tick:
            e = self.events[self.next_idx]
            self.next_idx += 1
            kind = e["type"]
            if kind == "mods":
                self.mods = 0
                for m in e["mods"]:
                    self.mods |= {"shift": pygame.KMOD_SHIFT, "ctrl": pygame.KMOD_CTRL}[m]
            elif kind == "key":
                key = getattr(pygame, "K_" + e["key"])
                pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=key))
                if e.get("hold"):
                    self.events.append({"tick": tick + e["hold"], "type": "keyup", "key": e["key"]})
                    self.events.sort(key=lambda ev: ev["tick"])
            elif kind == "keyup":
                pygame.event.post(pygame.event.Event(pygame.KEYUP, key=getattr(pygame, "K_" + e["key"])))
            elif kind == "click":
                pos = screen_at(e["at"])
                pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=pos, button=e["button"]))
                pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONUP, pos=pos, button=e["button"]))
            elif kind == "drag":
                pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=screen_at(e["from"]), button=1))
                pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONUP, pos=screen_at(e["to"]), button=1))
            else:
                raise ValueError(f"unknown input script event type: {kind}")
