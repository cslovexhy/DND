"""
Quest system.

Quest *definitions* are data: data/quests/<map_id>.json, where <map_id> is the map file name
without extension (data/maps/northshire.json -> "northshire"). Maps without a quest file simply
have no quests.

Quest *progress* belongs to a character, per map. A QuestLog holds one character's quests for one
map and can be loaded from / dumped to the "quests"[map_id] entry of that character's save
(see game/saves.py). Pure logic (no pygame) so it can be unit tested.
"""
import json
import os

QUEST_DIR = os.path.join("data", "quests")

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
                 npc_id=None, level_req=1, prerequisites=None):
        self.quest_id = quest_id
        self.title = title
        self.description = description
        self.objectives = objectives  # list of {"monster": monster_id, "count": N}
        self.rewards_xp = rewards_xp
        self.rewards_gold = rewards_gold
        self.npc_id = npc_id  # which NPC offers/accepts this quest
        self.level_req = level_req  # minimum hero level to accept
        self.prerequisites = prerequisites or []  # quest_ids that must be turned in first
        # Runtime state
        self.progress = {}  # {monster_id: kills_so_far}
        self.accepted = False
        self.completed = False  # objectives met
        self.turned_in = False  # rewards claimed

    def is_complete(self):
        return all(self.progress.get(o["monster"], 0) >= o["count"] for o in self.objectives)

    def record_kill(self, monster_id):
        """Record a kill. Returns True if this kill progressed the quest."""
        for obj in self.objectives:
            if obj["monster"] == monster_id:
                current = self.progress.get(obj["monster"], 0)
                if current < obj["count"]:
                    self.progress[obj["monster"]] = current + 1
                    return True
        return False

    def get_progress_text(self):
        return "  ".join(f"{monster_label(o['monster'])}: {self.progress.get(o['monster'], 0)}/{o['count']}"
                         for o in self.objectives)


class QuestLog:
    """One character's quests on one map."""

    def __init__(self, quests=None, questlines=None):
        self.quests = {q.quest_id: q for q in (quests or [])}
        # Each questline is an ordered list of quest_ids; only the next quest in a line is offered.
        self.questlines = questlines or []
        self.active = []     # quest_ids accepted and in progress
        self.completed = []  # quest_ids turned in

    # --- queries ---
    def prerequisites_met(self, quest):
        return all(p in self.completed for p in quest.prerequisites)

    def available_for_npc(self, npc_id, level):
        """quest_ids this NPC can offer right now."""
        available = []
        for chain in self.questlines:
            for qid in chain:
                q = self.quests[qid]
                if q.npc_id != npc_id:
                    continue
                if q.turned_in:
                    continue  # done, check next in chain
                if q.accepted:
                    break  # in progress - no more from this chain
                if self.prerequisites_met(q) and level >= q.level_req and qid not in self.active:
                    available.append(qid)
                break  # only one quest per chain per NPC at a time
        return available

    def available(self, level):
        """quest_ids that can be offered across all NPCs."""
        available = []
        for chain in self.questlines:
            for qid in chain:
                q = self.quests[qid]
                if q.turned_in:
                    continue
                if q.accepted:
                    break
                if self.prerequisites_met(q) and level >= q.level_req and qid not in self.active:
                    available.append(qid)
                break
        return available

    def turn_ins_for_npc(self, npc_id):
        """quest_ids that can be turned in at this NPC."""
        out = []
        for qid in self.active:
            q = self.quests.get(qid)
            if q and q.npc_id == npc_id and q.accepted and q.is_complete() and not q.turned_in:
                out.append(qid)
        return out

    def active_objects(self):
        return [self.quests[qid] for qid in self.active if qid in self.quests]

    # --- mutations (callers apply XP/gold rewards themselves) ---
    def accept(self, qid):
        """Accept a quest. No-objective quests complete and turn in immediately.
        Returns True if the quest was auto-completed (i.e. rewards are due now)."""
        q = self.quests[qid]
        q.accepted = True
        if not q.objectives:
            q.completed = True
            q.turned_in = True
            self.completed.append(qid)
            return True
        self.active.append(qid)
        return False

    def turn_in(self, qid):
        q = self.quests[qid]
        q.turned_in = True
        self.completed.append(qid)
        self.active.remove(qid)
        return q

    def record_kill(self, monster_id):
        """Credit a kill to every active quest. Returns [(quest, just_completed)] for quests that progressed."""
        results = []
        for q in self.active_objects():
            if q.accepted and not q.turned_in and q.record_kill(monster_id):
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
            "progress": {qid: {str(k): v for k, v in self.quests[qid].progress.items()}
                         for qid in self.active if qid in self.quests},
        }

    def load_state(self, state):
        """Restore saved state. Unknown quest ids (removed from data) are ignored."""
        state = state or {}
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
                q.completed = q.is_complete()
                self.active.append(qid)


def load_quest_log(map_id, quest_dir=None):
    """Build an empty QuestLog from data/quests/<map_id>.json (empty log if the map has no quests)."""
    path = os.path.join(quest_dir or QUEST_DIR, f"{map_id}.json")
    if not os.path.exists(path):
        return QuestLog()
    with open(path, "r") as f:
        data = json.load(f)
    quests = [Quest(q["id"], q["title"], q["description"], q.get("objectives", []),
                    q.get("rewards_xp", 0), q.get("rewards_gold", 0),
                    npc_id=q.get("npc_id"), level_req=q.get("level_req", 1),
                    prerequisites=q.get("prerequisites", []))
              for q in data.get("quests", [])]
    return QuestLog(quests, data.get("questlines", []))


# --- editing (the map editor's Quests screen) ----------------------------------------------------------------------
MAX_QUEST_TEXT = 1200


def quest_path(map_id, quest_dir=None):
    return os.path.join(quest_dir or QUEST_DIR, f"{map_id}.json")


def load_quest_data(map_id, quest_dir=None):
    """The raw quest file of a map as a dict {"map", "quests", "questlines"} (empty if the map has none)."""
    path = quest_path(map_id, quest_dir)
    if not os.path.exists(path):
        return {"map": map_id, "quests": [], "questlines": []}
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    data.setdefault("map", map_id)
    data.setdefault("quests", [])
    data.setdefault("questlines", [])
    return data


def save_quest_data(map_id, data, quest_dir=None):
    path = quest_path(map_id, quest_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def quest_slug(title, taken):
    """A permanent quest id from its title ('Kobold Camp Cleanup' -> 'kobold_camp_cleanup'), unique among `taken`."""
    base = "".join(c if c.isalnum() else "_" for c in title.lower()).strip("_")
    base = "_".join(p for p in base.split("_") if p) or "quest"
    qid, n = base, 2
    while qid in taken:
        qid, n = f"{base}_{n}", n + 1
    return qid


def validate_quest_data(data, npc_ids, monster_ids):
    """Problems with a map's quest file (empty list = fine). npc_ids: the NPCs on the map; monster_ids: every monster."""
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
        if q.get("npc_id") not in npc_ids:
            errs.append(f"{label}: the quest giver {q.get('npc_id')!r} is not an NPC on this map")
        for key, lo, hi in (("level_req", 1, 30), ("rewards_xp", 0, 10 ** 6), ("rewards_gold", 0, 10 ** 6)):
            v = q.get(key, lo)
            if not (isinstance(v, int) and not isinstance(v, bool) and lo <= v <= hi):
                errs.append(f"{label}: {key} must be a whole number {lo}-{hi}")
        seen = set()
        for o in q.get("objectives", []):
            if not (isinstance(o, dict) and o.get("monster") in monster_ids
                    and isinstance(o.get("count"), int) and not isinstance(o.get("count"), bool)
                    and 1 <= o["count"] <= 999):
                errs.append(f"{label}: every objective needs an existing monster and a count of 1-999")
            elif o["monster"] in seen:
                errs.append(f"{label}: the same monster is listed twice")
            else:
                seen.add(o["monster"])
        for p in q.get("prerequisites", []):
            if p not in ids or p == qid:
                errs.append(f"{label}: unknown prerequisite {p!r}")
    placed = [qid for line in data.get("questlines", []) for qid in line]
    for qid in placed:
        if qid not in ids:
            errs.append(f"questline lists unknown quest {qid!r}")
    for qid in set(placed):
        if placed.count(qid) > 1:
            errs.append(f"{qid} is in more than one questline")
    return errs
