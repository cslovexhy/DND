"""Listen-server host: runs the authoritative World and streams frames to connected clients (no pygame).

    python3 -m game.net.server --map data/maps/northshire.json --hero 4 [--port 5577] [--seed N]

Where it listens (never on all interfaces):
  lan=False (default, "H" in map select): 127.0.0.1 — this computer only.
  lan=True  ("L" in map select): this computer's home-network address only (e.g. 192.168.1.23), so devices
            on the same home network can join. Decided with the owner: anyone on the home network who finds
            the game may join without approval (co-op with family); not reachable from the internet (no router
            or UPnP changes). Joiners are limited by max_players, sanitized characters and the message caps.

Players: the world is created with the host player's character as player 0.
  local_host=True (hosting from the game): player 0 belongs to the host's own game, which talks to the server
            in-process via local_client() — no socket. No network connection can ever get player 0, even a
            second game window on the same computer.
  local_host=False (standalone `python -m game.net.server`, tests): the first client to say hello controls
            player 0.
Every other client brings its own character (validated) and joins as a new player, up to max_players.
A joiner who leaves is removed. Before saying hello, anyone may ask {"t": "info"} for the one-line game
description used by the Join screen.
"""
import collections
import os
import random
import selectors
import socket
import sys
import threading
import time

from game import saves
from game.content.heroes import HERO_CLASSES
from game.engine import commands, events as ev_mod
from game.engine.bootstrap import create_world, join_player, sanitize_character
from game.engine.snapshot import make_snapshot
from game.engine.map_schema import content_hash
from game.headless import FIXED_DT
from game.net.protocol import PROTOCOL_VERSION, LineBuffer, encode
from game.net.delta import DeltaEncoder
from game.net.discovery import lan_address

LOOPBACK = "127.0.0.1"
DEFAULT_PORT = 5577


class _Conn:
    def __init__(self, sock, addr):
        self.sock = sock
        self.addr = addr
        self.buf = LineBuffer()
        self.player_id = None
        self.out = b""             # bytes not yet accepted by the socket
        self.pending_events = []   # events not yet delivered (held while the client is backlogged)
        self.delta = DeltaEncoder()  # entity changes relative to the last frame sent to this client


class HostServer:
    """Authoritative host. Call serve_forever() (blocking) or start() (background thread)."""

    MAX_COMMANDS_PER_TICK = 30   # per player; extra commands are dropped (flood protection)

    def __init__(self, map_path, class_name="Fighter", seed=1, port=DEFAULT_PORT, tick_rate=30,
                 autopilot=False, auto_companion=False, host_character=None, max_players=4, pp=1, lan=False,
                 local_host=False):
        random.seed(seed)
        self.map_path = map_path
        self.max_players = max_players
        char = host_character or saves.blank_character(class_name.lower(), class_name)
        # Co-op has no AI companions (World.companions_enabled), so auto_companion is ignored here.
        self.world, self.player = create_world(map_path, char, autopilot=autopilot, auto_companion=False, pp=pp)
        self.world.companions_enabled = False
        self._next_player_id = 1
        # Joiners get the map itself (custom maps don't need to be copied around by hand)
        self.map_hash = content_hash(self.world.world_map.data)
        self._cmd_count = {}
        self.tick_rate = tick_rate
        self.dt = FIXED_DT if tick_rate == 30 else 1.0 / tick_rate
        self.sel = selectors.DefaultSelector()
        self.listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if lan:
            self.address = lan_address()
            if self.address is None:
                raise OSError("this computer isn't on a home network (no private IPv4 address)")
        else:
            self.address = LOOPBACK
        self.listener.bind((self.address, port))   # one interface only — never 0.0.0.0
        self.local_host = local_host
        self._local = None   # the host's own in-process client (local_host=True)
        self.listener.listen()
        self.listener.setblocking(False)
        self.port = self.listener.getsockname()[1]
        self.sel.register(self.listener, selectors.EVENT_READ, None)
        self.conns = []
        self._stop = threading.Event()
        self._thread = None

    # --- lifecycle ---
    def start(self):
        self._thread = threading.Thread(target=self.serve_forever, daemon=True)
        self._thread.start()
        return self

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

    def serve_forever(self, max_ticks=None):
        next_t = time.monotonic()
        try:
            while not self._stop.is_set():
                self._poll(timeout=max(0.0, next_t - time.monotonic()))
                if time.monotonic() >= next_t:
                    self._tick()
                    next_t += self.dt
                    if max_ticks is not None and self.world.tick >= max_ticks:
                        break
        finally:
            # Deliver a final frame so clients end on the host's final state, then disconnect.
            for c in list(self.conns):
                if c.player_id is not None:
                    try:
                        c.sock.settimeout(2.0)
                        c.sock.sendall(c.out + self._frame(c))
                    except OSError:
                        pass
                c.out = b""
                self._close(c)
            self.sel.close()
            self.listener.close()

    # --- networking ---
    def _poll(self, timeout):
        for key, _mask in self.sel.select(timeout):
            if key.data is None:
                sock, addr = self.listener.accept()
                sock.setblocking(False)
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                c = _Conn(sock, addr)
                self.conns.append(c)
                self.sel.register(sock, selectors.EVENT_READ, c)
            else:
                self._read(key.data)

    def _read(self, c):
        try:
            data = c.sock.recv(65536)
        except (BlockingIOError, InterruptedError):
            return
        except OSError:
            data = b""
        if not data:
            self._close(c)
            return
        try:
            for msg in c.buf.feed(data):
                self._handle(c, msg)
        except (ValueError, KeyError, TypeError) as e:
            self._send(c, {"t": "reject", "reason": f"bad message: {e}"})
            self._close(c)

    def _handle(self, c, msg):
        t = msg["t"]
        if t == "info":
            self._send(c, {"t": "info", "v": PROTOCOL_VERSION, **self.info()})
            self._close(c)
        elif t == "hello":
            if msg.get("v") != PROTOCOL_VERSION:
                self._send(c, {"t": "reject", "reason": f"protocol version {msg.get('v')} != {PROTOCOL_VERSION}"})
                self._close(c)
            elif c.player_id is not None:
                return   # duplicate hello: ignore
            elif not self.local_host and not any(o.player_id == 0 for o in self.conns if o is not c):
                self._admit(c, 0)                    # standalone server: first client controls player 0
            elif self._player_count() >= self.max_players:
                self._send(c, {"t": "reject", "reason": f"game is full ({self.max_players} players)"})
                self._close(c)
            else:
                char = sanitize_character(msg.get("character")
                                          or saves.blank_character(str(msg.get("name", "player")),
                                                                   msg.get("class_name", "Fighter")))
                pid = self._next_player_id
                self._next_player_id += 1
                join_player(self.world, pid, char, self.map_path)
                self._admit(c, pid)
                print(f"[HOST] {char['name']} ({char['class_name']} Lv{char['level']}) joined as player {pid}",
                      flush=True)
        elif t == "cmd" and c.player_id is not None:
            n = self._cmd_count.get(c.player_id, 0)
            if n < self.MAX_COMMANDS_PER_TICK:
                self._cmd_count[c.player_id] = n + 1
                self.world.submit(commands.from_dict(msg["cmd"]), c.player_id)   # unknown types raise -> reject
        elif t == "bye":
            self._close(c)

    def local_client(self):
        """The host's own game: an in-process client that always controls player 0 (same interface as RemoteHost)."""
        if not self.local_host:
            raise RuntimeError("local_client() needs HostServer(local_host=True)")
        if self._local is None:
            self._local = LocalClient(self)
        return self._local

    def info(self):
        """Description for the Join screen: host's character, map and pp, player count."""
        host = self.world.players.get(0)
        hero = host.hero if host else self.world.hero
        name = os.path.splitext(os.path.basename(self.map_path))[0].replace("_", " ").title()
        return {"host_name": hero.name, "host_level": hero.level, "map_name": name, "pp": self.world.pp,
                "players": self._player_count(), "max_players": self.max_players}

    def _player_count(self):
        local = 1 if self._local is not None and not self._local.closed else 0
        return local + sum(1 for o in self.conns if o.player_id is not None)

    def _admit(self, c, pid):
        c.player_id = pid
        self._send(c, {"t": "welcome", "v": PROTOCOL_VERSION, "player_id": pid, "map": self.map_path,
                       "map_data": self.world.world_map.data, "map_hash": self.map_hash, "pp": self.world.pp,
                       "tick_rate": self.tick_rate})
        c.out += self._frame(c)
        self._flush(c)

    def _send(self, c, msg):
        c.out += encode(msg)
        self._flush(c)

    def _flush(self, c):
        while c.out:
            try:
                n = c.sock.send(c.out)
            except (BlockingIOError, InterruptedError):
                return
            except OSError:
                self._close(c)
                return
            c.out = c.out[n:]

    def _close(self, c):
        if c in self.conns:
            self.conns.remove(c)
            if c.player_id not in (None, 0):
                self.world.remove_player(c.player_id)   # a joiner left; player 0's slot stays reserved
            try:
                self.sel.unregister(c.sock)
            except (KeyError, ValueError):
                pass
            c.sock.close()

    # --- simulation ---
    def _frame(self, c):
        snap = make_snapshot(self.world, c.player_id)
        ents = c.delta.encode(snap.pop("entities"))
        msg = {"t": "frame", "snap": snap, "ents": ents, "events": c.pending_events}
        c.pending_events = []
        return encode(msg)

    def _tick(self):
        w = self.world
        if self._local is not None:                 # the host's own commands, queued from the game's main thread
            while self._local._commands:
                w.submit(self._local._commands.popleft(), 0)
        if not w.game_state.adventure_failed:
            w.step(self.dt)
        self._cmd_count.clear()
        evs, w.events = w.events, []
        if self._local is not None:
            self._local._deliver(make_snapshot(w, 0), [e for e in evs if getattr(e, "player_id", None) in (None, 0)])
        payload = [(getattr(e, "player_id", None), ev_mod.to_dict(e)) for e in evs]
        for c in list(self.conns):
            if c.player_id is None:
                continue
            # personal events (level-up, quest dialogue...) only go to their player
            c.pending_events.extend(d for pid, d in payload if pid is None or pid == c.player_id)
            self._flush(c)
            # Flow control: a client that hasn't drained the previous frame skips this snapshot
            # (only the newest one matters); its events are kept and sent with the next frame.
            if not c.out and c in self.conns:
                c.out = self._frame(c)
                self._flush(c)


class LocalClient:
    """The host's own game talking to its HostServer in-process (thread-safe, no socket). Same interface as
    RemoteHost: welcome, send(), step(), snapshot(), close(), closed. Always player 0."""

    def __init__(self, server):
        self._server = server
        self._lock = threading.Lock()
        self._commands = collections.deque()   # main thread appends, server thread pops (both thread-safe)
        self._latest = None
        self._events = []
        self._have_snapshot = threading.Event()
        self.closed = False
        self.welcome = {"t": "welcome", "v": PROTOCOL_VERSION, "player_id": 0, "map": server.map_path,
                        "map_data": server.world.world_map.data, "map_hash": server.map_hash,
                        "pp": server.world.pp, "tick_rate": server.tick_rate}

    # called by the server thread
    def _deliver(self, snap, events):
        with self._lock:
            self._latest = snap
            self._events.extend(events)
        self._have_snapshot.set()

    # called by the game's main thread
    def send(self, command):
        if not self.closed:
            self._commands.append(command)          # the server thread submits it on its next tick

    def step(self, dt=None):
        with self._lock:
            snap, self._latest = self._latest, None
            events, self._events = self._events, []
        if not self._server._thread or not self._server._thread.is_alive():
            self.closed = True
        return snap, events

    def snapshot(self, timeout=10.0):
        self._have_snapshot.wait(timeout)
        with self._lock:
            snap, self._latest = self._latest, None
        return snap

    def close(self):
        self.closed = True


def main(argv):
    from game.headless import _arg_value
    map_path = _arg_value(argv, "--map", str, "data/maps/northshire.json")
    hero_idx = _arg_value(argv, "--hero", int, 0)
    srv = HostServer(map_path, HERO_CLASSES[hero_idx]["class"], seed=_arg_value(argv, "--seed", int, 1),
                     port=_arg_value(argv, "--port", int, DEFAULT_PORT),
                     autopilot="--auto" in argv, auto_companion="--auto" in argv,
                     pp=_arg_value(argv, "--pp", int, 1))
    print(f"[HOST] {map_path} ({srv.world.pp}pp) on {srv.address}:{srv.port} (this machine only). Ctrl+C to stop.",
          flush=True)
    try:
        srv.serve_forever(max_ticks=_arg_value(argv, "--max-ticks", int, None))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main(sys.argv)
