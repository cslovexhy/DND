"""Entity delta compression for network frames (pure; no pygame).

Most entities don't change every tick (idle monsters, NPCs), so the host sends each client only what
changed since the previous frame it sent to that client. TCP delivers frames in order and completely,
so "previous frame sent" is exactly what the client has.

  encode: {"order": [ids...], "set": [{"id": 5, "x": 1.0, ...changed fields}], "del": [ids]}
"""


class DeltaEncoder:
    """Host side, one per client."""

    def __init__(self):
        self.last = {}

    def encode(self, entities):
        out_set, seen = [], set()
        for e in entities:
            eid = e["id"]
            seen.add(eid)
            prev = self.last.get(eid)
            if prev is None or prev.get("kind") != e["kind"]:
                out_set.append(e)                       # new: everything
            else:
                changed = {k: v for k, v in e.items() if prev.get(k) != v}
                if changed:
                    changed["id"] = eid
                    out_set.append(changed)
            self.last[eid] = e
        gone = [eid for eid in self.last if eid not in seen]
        for eid in gone:
            del self.last[eid]
        return {"order": [e["id"] for e in entities], "set": out_set, "del": gone}


class DeltaDecoder:
    """Client side: rebuilds the full entity list."""

    def __init__(self):
        self.entities = {}

    def decode(self, delta):
        for eid in delta["del"]:
            self.entities.pop(eid, None)
        for d in delta["set"]:
            cur = self.entities.get(d["id"])
            if cur is None or ("kind" in d and cur.get("kind") != d["kind"]):
                self.entities[d["id"]] = dict(d)
            else:
                cur.update(d)
        return [dict(self.entities[eid]) for eid in delta["order"]]
