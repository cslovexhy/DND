"""
Quest system.

Quest *definitions* are data: one file, data/quests.json, for the whole game. A quest is not tied to a map:
it names three NPCs (any maps): who GIVES it, who it is TURNED IN to (the kills / items are handed over there) and who
pays the REWARD. Usually all three are the same NPC. Which quests exist for a character depends only on its progress:
a quest is offered once its prerequisite quests are done and the hero's level is high enough.

Quest *progress* belongs to a character (the "quests" entry of its save, see game/saves.py). A QuestLog holds one
character's quests. Pure logic (no pygame) so it can be unit tested.
"""
import json
import os

QUEST_PATH = os.path.join("data", "quests.json")

# Saves written before monsters had numeric ids keyed kill progress by monster name.
LEGACY_NAME_IDS = {
    "Kobold Dragonshield": 1, "Snake": 2, "Orc Smasher": 3, "Orc Archer": 4, "Grey Wolf": 5,
    "Duergar Guard": 6, "Gibbering Mouther": 7, "Grell": 8, "Human Cultist": 9, "Legion Devil": 10,
    "Demogorgon": 11, "Demodog": 12, "Demobat": 13, "Vecna": 14, "Meerak": 15, "Ashardalon": 16,
    "Bellax": 17, "Karash": 18, "Margrath": 19, "Rage Drake": 20, "Otyugh": 21,
    "Garrick Padfoot": 22,
}


def _progress_key(key):
    """A saved progress key (JSON: str) -> monster id (int); old name keys are migrated."""
    if isinstance(key, int):
        return key
    key = str(key)
    if key.lstrip("-").isdigit():
        return int(key)
    return LEGACY_NAME_IDS.get(key)


def monster_label(monster_id):
    """Current display name of a monster id (falls back to '#id')."""
    try:
        from game.content import monsters
        return monsters.monster_name(monster_id)
    except Exception:
        return f"#{monster_id}"


class Quest:
    """A quest definition plus its runtime state for one character."""

    def __init__(self, quest_id, title, description, objectives, rewards_xp, rewards_gold,
                 giver=None, level_req=1, prerequisites=None, turn_in=None, reward_npc=None):
        self.quest_id = quest_id
        self.title = title
        self.description = description
        # list of {"monster": monster_id, "count": N} (kill) and / or {"item": item_id, "count": N} (have in the backpack)
        self.objectives = objectives
        self.rewards_xp = rewards_xp
        self.rewards_gold = rewards_gold
        self.giver = giver                         # the NPC that offers it (npc_id)
        self.turn_in = turn_in or giver            # the NPC the kills / items are handed over to
        self.reward_npc = reward_npc or self.turn_in   # the NPC that pays the reward
        self.level_req = level_req  # minimum hero level to accept
        self.prerequisites = prerequisites or []  # quest_ids that must be done first
        # Runtime state
        self.progress = {}  # {monster_id: kills_so_far}
        self.inventory = None   # the character's backpack (set by the QuestLog): item objectives count from it
        self.accepted = False
        self.completed = False  # objectives met
        self.delivered = False  # handed over at the turn-in NPC, the reward is still to be collected
        self.turned_in = False  # rewards claimed

    @property
    def npc_id(self):
        return self.giver

    def objective_count(self, o):
        """How far one objective is: kills so far, or the items in the backpack."""
        if "item" in o:
            return self.inventory.count(o["item"]) if self.inventory is not None else 0
        return self.progress.get(o["monster"], 0)

    def is_complete(self):
        return all(self.objective_count(o) >= o["count"] for o in self.objectives)

    def record_kill(self, monster_id):
        """Record a kill. Returns True if this kill progressed the quest."""
        for obj in self.objectives:
            if obj.get("monster") == monster_id:
                current = self.progress.get(monster_id, 0)
                if current < obj["count"]:
                    self.progress[monster_id] = current + 1
                    return True
        return False

    def get_progress_text(self):
        parts = []
        for o in self.objectives:
            have = min(self.objective_count(o), o["count"])
            parts.append(f"{objective_label(o)}: {have}/{o['count']}")
        return "  ".join(parts)


def objective_label(o):
    """Display name of an objective's target (a monster or an item)."""
    if "item" in o:
        try:
            from game.content.items import ITEMS
            return ITEMS[o["item"]]["name"]
        except Exception:
            return f"item #{o['item']}"
    return monster_label(o["monster"])


def topo_order(quests):
    """Quests (dicts or Quest objects) in dependency order: prerequisites first, ties in file order.
    Returns (ordered, cyclic): quests that wait on each other forever come back in `cyclic`, not in `ordered`."""
    def qid(q):
        return q["id"] if isinstance(q, dict) else q.quest_id

    def pre(q):
        return (q.get("prerequisites", []) if isinstance(q, dict) else q.prerequisites)
    ids = {qid(q) for q in quests}
    done, ordered = set(), []
    remaining = list(quests)
    while remaining:
        ready = [q for q in remaining if all(p in done or p not in ids for p in pre(q))]
        if not ready:
            return ordered, remaining
        for q in ready:
            done.add(qid(q))
        ordered.extend(ready)
        remaining = [q for q in remaining if qid(q) not in done]
    return ordered, []


class QuestLog:
    """One character's quests."""

    def __init__(self, quests=None, inventory=None):
        ordered, _ = topo_order(list(quests or []))
        self.quests = {q.quest_id: q for q in ordered}      # in dependency order
        self.active = []     # quest_ids accepted and in progress (incl. delivered, waiting for the reward)
        self.completed = []  # quest_ids turned in
        self.set_inventory(inventory)

    def set_inventory(self, inventory):
        self.inventory = inventory
        for q in self.quests.values():
            q.inventory = inventory

    # --- queries ---
    def prerequisites_met(self, quest):
        return all(p in self.completed for p in quest.prerequisites)

    def _offerable(self, q, level):
        return (not q.accepted and not q.turned_in and q.quest_id not in self.active
                and self.prerequisites_met(q) and level >= q.level_req)

    def available_for_npc(self, npc_id, level):
        """quest_ids this NPC can offer right now."""
        return [qid for qid, q in self.quests.items() if q.giver == npc_id and self._offerable(q, level)]

    def available(self, level):
        """quest_ids that can be offered across all NPCs."""
        return [qid for qid, q in self.quests.items() if self._offerable(q, level)]

    def turn_ins_for_npc(self, npc_id):
        """quest_ids whose objectives are met and that are handed in at this NPC."""
        return [qid for qid in self.active if self.quests[qid].turn_in == npc_id and not self.quests[qid].delivered
                and self.quests[qid].is_complete()] if self.active else []

    def rewards_for_npc(self, npc_id):
        """quest_ids already handed in whose reward this NPC pays."""
        return [qid for qid in self.active if self.quests[qid].delivered and self.quests[qid].reward_npc == npc_id]

    def active_objects(self):
        return [self.quests[qid] for qid in self.active if qid in self.quests]

    # --- mutations (callers apply XP/gold rewards themselves) ---
    def accept(self, qid):
        """Accept a quest. A quest with no objectives that is given, handed in and paid by one NPC completes right
        away. Returns True if the quest was auto-completed (i.e. rewards are due now)."""
        q = self.quests[qid]
        q.accepted = True
        if not q.objectives and q.turn_in == q.giver and q.reward_npc == q.giver:
            q.completed = True
            q.turned_in = True
            self.completed.append(qid)
            return True
        self.active.append(qid)
        return False

    def hand_in(self, qid):
        """Hand the objectives over at the turn-in NPC: items leave the backpack. If the same NPC also pays the
        reward the quest is finished (returns the quest and True); otherwise it waits for its reward NPC (False)."""
        q = self.quests[qid]
        for o in q.objectives:
            if "item" in o and self.inventory is not None:
                self.inventory.remove(o["item"], o["count"])
        q.completed = True
        if q.reward_npc == q.turn_in:
            return self.turn_in(qid), True
        q.delivered = True
        return q, False

    def turn_in(self, qid):
        """Finish the quest (the reward is due now)."""
        q = self.quests[qid]
        q.turned_in = True
        q.delivered = False
        self.completed.append(qid)
        if qid in self.active:
            self.active.remove(qid)
        return q

    def record_kill(self, monster_id):
        """Credit a kill to every active quest. Returns [(quest, just_completed)] for quests that progressed."""
        results = []
        for q in self.active_objects():
            if q.accepted and not q.turned_in and not q.delivered and q.record_kill(monster_id):
                just_done = q.is_complete() and not q.completed
                if just_done:
                    q.completed = True
                results.append((q, just_done))
        return results

    # --- persistence ---
    def to_state(self):
        return {
            "completed": list(self.completed),
            "active": list(self.active),
            "delivered": [qid for qid in self.active if self.quests[qid].delivered],
            "progress": {qid: {str(k): v for k, v in self.quests[qid].progress.items()}
                         for qid in self.active if qid in self.quests},
        }

    def load_state(self, state):
        """Restore saved state. Unknown quest ids (removed from data) are ignored."""
        state = normalize_state(state)
        for qid in state.get("completed", []):
            q = self.quests.get(qid)
            if q and qid not in self.completed:
                q.accepted = q.completed = q.turned_in = True
                self.completed.append(qid)
        for qid in state.get("active", []):
            q = self.quests.get(qid)
            if q and qid not in self.completed and qid not in self.active:
                q.accepted = True
                q.progress = {}
                for key, n in state.get("progress", {}).get(qid, {}).items():
                    mid = _progress_key(key)
                    if mid is not None:
                        q.progress[mid] = n
                q.delivered = qid in state.get("delivered", [])
                q.completed = q.delivered or q.is_complete()
                self.active.append(qid)


def normalize_state(state):
    """A character's saved quest state in the current shape. Older saves kept one state per map
    ({"northshire": {"completed": [...], ...}}): those are merged (quest ids are unique across the game)."""
    state = state or {}
    if any(k in state for k in ("completed", "active", "progress", "delivered")):
        return state
    merged = {"completed": [], "active": [], "delivered": [], "progress": {}}
    for per_map in state.values():
        if not isinstance(per_map, dict):
            continue
        for key in ("completed", "active", "delivered"):
            merged[key] += [q for q in per_map.get(key, []) if q not in merged[key]]
        merged["progress"].update(per_map.get("progress", {}))
    return merged


def _quest_from_dict(q):
    return Quest(q["id"], q["title"], q.get("description", ""), q.get("objectives", []),
                 q.get("rewards_xp", 0), q.get("rewards_gold", 0), giver=q.get("giver"),
                 level_req=q.get("level_req", 1), prerequisites=q.get("prerequisites", []),
                 turn_in=q.get("turn_in"), reward_npc=q.get("reward_npc"))


def load_quest_log(map_id=None, path=None):
    """An empty QuestLog from data/quests.json (every quest of the game; `map_id` is accepted and ignored: quests do not
    belong to maps)."""
    path = path or QUEST_PATH
    if not os.path.exists(path):
        return QuestLog()
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return QuestLog([_quest_from_dict(q) for q in data.get("quests", [])])


# --- editing (the map editor's Quests screen) ----------------------------------------------------------------------
MAX_QUEST_TEXT = 1200


def load_quest_data(path=None):
    """The raw quest file as a dict {"quests": [...]} (empty if there is none)."""
    path = path or QUEST_PATH
    if not os.path.exists(path):
        return {"version": 2, "quests": []}
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    data.setdefault("quests", [])
    return data


def save_quest_data(data, path=None):
    path = path or QUEST_PATH
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"version": 2, **{k: v for k, v in data.items() if k != "version"}}, f, indent=2,
                  ensure_ascii=False)
        f.write("\n")


def quest_slug(title, taken):
    """A permanent quest id from its title ('Kobold Camp Cleanup' -> 'kobold_camp_cleanup'), unique among `taken`."""
    base = "".join(c if c.isalnum() else "_" for c in title.lower()).strip("_")
    base = "_".join(p for p in base.split("_") if p) or "quest"
    qid, n = base, 2
    while qid in taken:
        qid, n = f"{base}_{n}", n + 1
    return qid


_NPC_CACHE = {}


def npc_directory(maps_dir=None, refresh=False):
    """{npc_id: {"name", "map", "sprite_col", "sprite_row"}} of every NPC of every map in data/maps."""
    maps_dir = maps_dir or os.path.join("data", "maps")
    if refresh or maps_dir not in _NPC_CACHE:
        out = {}
        for fn in sorted(os.listdir(maps_dir)) if os.path.isdir(maps_dir) else []:
            if not fn.endswith(".json"):
                continue
            try:
                with open(os.path.join(maps_dir, fn), encoding="utf-8") as f:
                    npcs = json.load(f).get("npcs", [])
            except (OSError, ValueError):
                continue
            for n in npcs:
                if isinstance(n, dict) and "npc_id" in n:
                    out.setdefault(n["npc_id"], {"name": n.get("name", n["npc_id"]), "map": fn[:-5],
                                                 "sprite_col": n.get("sprite_col", 0),
                                                 "sprite_row": n.get("sprite_row", 0)})
        _NPC_CACHE[maps_dir] = out
    return _NPC_CACHE[maps_dir]


def npc_label(npc_id):
    """An NPC's display name for the player ('Marshal McBride'), or its id if no map has it."""
    n = npc_directory().get(npc_id)
    return n["name"] if n else str(npc_id)


def validate_quest_data(data, npc_ids, monster_ids, item_ids=()):
    """Problems with the quest file (empty list = fine). npc_ids: every NPC of every map; monster_ids / item_ids:
    what objectives may point at."""
    errs = []
    quests = data.get("quests", [])
    ids = [q.get("id") for q in quests]
    for q in quests:
        qid = q.get("id")
        label = f"{q.get('title') or qid}"
        if not (isinstance(qid, str) and qid) or ids.count(qid) > 1:
            errs.append(f"{label}: needs a unique id")
        if not (isinstance(q.get("title"), str) and q["title"].strip()):
            errs.append(f"{label}: needs a title")
        if not isinstance(q.get("description", ""), str) or len(q.get("description", "")) > MAX_QUEST_TEXT:
            errs.append(f"{label}: description is too long")
        for key, what in (("giver", "gives the quest"), ("turn_in", "takes the kills / items"),
                          ("reward_npc", "pays the reward")):
            v = q.get(key) if key == "giver" else (q.get(key) or q.get("giver"))
            if v not in npc_ids:
                errs.append(f"{label}: the NPC that {what} ({v!r}) is not on any map")
        for key, lo, hi in (("level_req", 1, 30), ("rewards_xp", 0, 10 ** 6), ("rewards_gold", 0, 10 ** 6)):
            v = q.get(key, lo)
            if not (isinstance(v, int) and not isinstance(v, bool) and lo <= v <= hi):
                errs.append(f"{label}: {key} must be a whole number {lo}-{hi}")
        seen = set()
        for o in q.get("objectives", []):
            ok = (isinstance(o, dict) and isinstance(o.get("count"), int) and not isinstance(o.get("count"), bool)
                  and 1 <= o["count"] <= 999 and (("monster" in o) != ("item" in o)))
            key = ("monster", o["monster"]) if ok and "monster" in o else (("item", o.get("item")) if ok else None)
            if ok and not (o["monster"] in monster_ids if "monster" in o else o["item"] in item_ids):
                ok = False
            if not ok:
                errs.append(f"{label}: every objective needs an existing monster or item and a count of 1-999")
            elif key in seen:
                errs.append(f"{label}: the same target is listed twice")
            else:
                seen.add(key)
        for p in q.get("prerequisites", []):
            if p not in ids or p == qid:
                errs.append(f"{label}: unknown prerequisite {p!r}")
    _, cyclic = topo_order(quests)
    if cyclic:
        errs.append("quests wait on each other in a circle: " + ", ".join(q.get("title") or q["id"] for q in cyclic))
    return errs
