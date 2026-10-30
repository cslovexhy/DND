"""Client-side connection to a remote host (no pygame). Same interface as client/local_host.LocalHost:

    host = RemoteHost("127.0.0.1", 5577, name="me", class_name="Wizard")
    snap = host.snapshot()            # latest snapshot (blocks for the first one)
    host.send(commands.MoveTo(...))
    snap, events = host.step(dt)      # non-blocking: newest snapshot received (or None) + all events since
"""
import selectors
import socket
import time

from game.engine import commands, events as ev_mod
from game.net.protocol import PROTOCOL_VERSION, LineBuffer, encode
from game.net.delta import DeltaDecoder


class ConnectionRejected(Exception):
    pass


class RemoteHost:
    def __init__(self, host, port, name="player", class_name="Fighter", timeout=10.0, character=None):
        self.sock = socket.create_connection((host, port), timeout=timeout)
        self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.buf = LineBuffer()
        self.sel = selectors.DefaultSelector()
        self.sel.register(self.sock, selectors.EVENT_READ)
        self._latest = None
        self._events = []
        self._delta = DeltaDecoder()
        self.bytes_received = 0
        self.closed = False
        hello = {"t": "hello", "v": PROTOCOL_VERSION, "name": name, "class_name": class_name}
        if character is not None:
            hello["character"] = character   # joiners bring their own saved character
        self.sock.sendall(encode(hello))
        welcome = self._wait_for(lambda: self.welcome is not None, timeout)
        if not welcome:
            raise ConnectionRejected(self.reject_reason or "no welcome from host")
        self.sock.setblocking(False)

    welcome = None
    reject_reason = None

    # --- interface shared with LocalHost ---
    def send(self, command):
        if not self.closed:
            try:
                self.sock.sendall(encode({"t": "cmd", "cmd": commands.to_dict(command)}))
            except OSError:
                self.closed = True

    def step(self, dt=None):
        self._pump(0)
        snap, self._latest = self._latest, None
        events, self._events = self._events, []
        return snap, events

    def snapshot(self, timeout=10.0):
        """Block until a snapshot is available and return it."""
        self._wait_for(lambda: self._latest is not None, timeout)
        snap, self._latest = self._latest, None
        return snap

    def close(self):
        if not self.closed:
            try:
                self.sock.sendall(encode({"t": "bye"}))
            except OSError:
                pass
            self.closed = True
        self.sock.close()

    # --- internals ---
    def _wait_for(self, cond, timeout):
        deadline = time.monotonic() + timeout
        while not cond():
            left = deadline - time.monotonic()
            if left <= 0 or self.closed:
                return False
            self._pump(left)
        return True

    def _pump(self, timeout):
        while self.sel.select(timeout):
            timeout = 0
            try:
                data = self.sock.recv(1 << 20)
            except (BlockingIOError, InterruptedError):
                break
            except OSError:
                data = b""
            if not data:
                self.closed = True
                break
            self.bytes_received += len(data)
            for msg in self.buf.feed(data):
                t = msg["t"]
                if t == "welcome":
                    self.welcome = msg
                elif t == "reject":
                    self.reject_reason = msg.get("reason")
                    self.closed = True
                elif t == "frame":
                    snap = msg["snap"]
                    snap["entities"] = self._delta.decode(msg["ents"])   # decode every frame, in order
                    self._latest = snap                  # only the newest snapshot matters
                    self._events.extend(ev_mod.from_dict(e) for e in msg["events"])
