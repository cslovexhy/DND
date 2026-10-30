"""Wire protocol between a host and its clients (pure; no pygame).

Transport: TCP, one JSON object per line (UTF-8). Small, debuggable, good enough for a few players.

client -> host
  {"t": "hello", "v": PROTOCOL_VERSION, "name": "...", "class_name": "Wizard"}
  {"t": "cmd", "cmd": <commands.to_dict>}
  {"t": "bye"}
host -> client
  {"t": "welcome", "v": PROTOCOL_VERSION, "player_id": 0, "map": "data/maps/x.json", "tick_rate": 30}
  {"t": "reject", "reason": "..."}
  {"t": "frame", "snap": <snapshot.make_snapshot>, "events": [<events.to_dict>, ...]}
"""
import json

PROTOCOL_VERSION = 1
MAX_LINE = 4 * 1024 * 1024   # refuse absurdly large messages (bytes)


def encode(msg):
    return (json.dumps(msg, separators=(",", ":")) + "\n").encode("utf-8")


class LineBuffer:
    """Accumulates bytes from a socket and yields complete decoded JSON messages."""

    def __init__(self):
        self._buf = b""

    def feed(self, data):
        self._buf += data
        if len(self._buf) > MAX_LINE and b"\n" not in self._buf:
            raise ValueError("message too large")
        out = []
        while b"\n" in self._buf:
            line, self._buf = self._buf.split(b"\n", 1)
            if line.strip():
                msg = json.loads(line.decode("utf-8"))
                if not isinstance(msg, dict) or "t" not in msg:
                    raise ValueError("malformed message")
                out.append(msg)
        return out
