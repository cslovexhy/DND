"""Client-side mirror of the world, rebuilt from snapshots (pure; no pygame).

The renderer and input code read only these view objects, never the simulation. View objects
keep the attribute names of the real entities (x, y, hp, facing_left, ...) so drawing code reads
naturally, and they persist across snapshots by entity id, so the client can attach sprites once.
"""
import math
from types import SimpleNamespace


class EntityView:
    def __init__(self, data):
        self.sprite = None
        self.update(data)

    def update(self, data):
        self.__dict__.update(data)
        self.eid = data["id"]

    # --- helpers the drawing / picking code uses ---
    def has_condition(self, condition):
        return condition.name in self.conditions

    def distance_to(self, other):
        return math.hypot(self.x - other.x, self.y - other.y)

    def has_turn_in(self):
        return self.turn_in

    def has_available_quest(self):
        return self.quest_available


class AbilityView:
    def __init__(self, data):
        self.__dict__.update(data)

    def is_ready(self):
        return self.ready


class ProjectileView:
    def __init__(self, data, target):
        self.__dict__.update(data)
        self.color = tuple(self.color)
        self.target = target


class ClientView:
    """Everything one client knows about the world, as of the last snapshot applied."""

    def __init__(self, on_new_entity=None):
        self.on_new_entity = on_new_entity   # callback(view) to attach art for new entities
        self.entities = {}
        self.hero = None
        self.companions = []
        self.allies = []          # other players' heroes (multiplayer)
        self.monsters = []
        self.npcs = []
        self.projectiles = []
        self.you = None
        self.tick = 0
        self.game_time = 0.0
        self.objective_text = ""
        self.adventure_failed = False

    def apply(self, snap):
        seen = set()
        hero, companions, monsters, npcs, allies = None, [], [], [], []
        for d in snap["entities"]:
            v = self.entities.get(d["id"])
            if v is None or v.kind != d["kind"]:
                v = EntityView(d)
                self.entities[d["id"]] = v
                if self.on_new_entity:
                    self.on_new_entity(v)
            else:
                v.update(d)
            seen.add(d["id"])
            if d["kind"] == "hero":
                hero = v
            elif d["kind"] == "companion":
                companions.append(v)
            elif d["kind"] == "ally":
                allies.append(v)
            elif d["kind"] == "monster":
                monsters.append(v)
            else:
                npcs.append(v)
        for eid in [e for e in self.entities if e not in seen]:
            del self.entities[eid]
        self.hero, self.companions, self.monsters, self.npcs = hero, companions, monsters, npcs
        self.allies = allies
        self.projectiles = [ProjectileView(p, self.entities.get(p["target_id"])) for p in snap["projectiles"]]
        you = dict(snap["you"])
        you["abilities"] = {a["key"]: AbilityView(a) for a in you["abilities"]}
        you["ability_keys"] = list(you["abilities"])
        you["selected_target"] = self.entities.get(you["selected_target_id"])
        q = you["quests"]
        you["quests"] = SimpleNamespace(active=[SimpleNamespace(**a) for a in q["active"]],
                                        any_available=q["any_available"], has_quests=q["has_quests"])
        self.you = SimpleNamespace(**you)
        self.tick = snap["tick"]
        self.game_time = snap["game_time"]
        self.objective_text = snap["objective_text"]
        self.adventure_failed = snap["adventure_failed"]

    def is_mine(self, event):
        """Personal events (with a player_id) are only for that player's client."""
        pid = getattr(event, "player_id", None)
        return pid is None or self.you is None or pid == self.you.player_id

    @property
    def alive_monsters(self):
        return [m for m in self.monsters if m.alive]
