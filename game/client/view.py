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

    TELEPORT_DISTANCE = 300   # px: jumps bigger than this (respawn, companion teleport) are not smoothed

    def __init__(self, on_new_entity=None, interpolate=False, tick_rate=30):
        self.on_new_entity = on_new_entity   # callback(view) to attach art for new entities
        # Remote play: snapshots arrive ~30x/s; draw entities gliding between the last two positions
        # instead of jumping, so movement looks smooth at 60 fps. Off for local play (exact positions).
        self.interpolate = interpolate
        self.interval = 1.0 / tick_rate
        self._elapsed = 0.0
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
        self.pp = 1

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
                v._fx = v._tx = v.x
                v._fy = v._ty = v.y
            elif self.interpolate:
                shown_x, shown_y = v.x, v.y
                v.update(d)
                v._tx, v._ty = v.x, v.y
                if math.hypot(v._tx - shown_x, v._ty - shown_y) > self.TELEPORT_DISTANCE:
                    v._fx, v._fy = v._tx, v._ty
                else:
                    v._fx, v._fy = shown_x, shown_y
                    v.x, v.y = shown_x, shown_y
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
        self._elapsed = 0.0
        self.tick = snap["tick"]
        self.game_time = snap["game_time"]
        self.objective_text = snap["objective_text"]
        self.pp = snap.get("pp", 1)
        self.adventure_failed = snap["adventure_failed"]

    def advance(self, dt):
        """Move interpolated entities toward their latest snapshot position (call once per rendered frame)."""
        if not self.interpolate:
            return
        self._elapsed += dt
        a = min(1.0, self._elapsed / self.interval)
        for v in self.entities.values():
            v.x = v._fx + (v._tx - v._fx) * a
            v.y = v._fy + (v._ty - v._fy) * a

    def is_mine(self, event):
        """Personal events (with a player_id) are only for that player's client."""
        pid = getattr(event, "player_id", None)
        return pid is None or self.you is None or pid == self.you.player_id

    @property
    def alive_monsters(self):
        return [m for m in self.monsters if m.alive]
