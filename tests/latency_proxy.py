"""Test helper: a loopback TCP proxy that delays traffic (latency + jitter) in both directions.

TCP keeps byte order, so jitter here means uneven delivery times (bursts and gaps), which is what a
real Wi-Fi link does to a TCP stream. Used by tests/test_net.py to check the game copes with a bad link.
"""
import random
import socket
import threading
import time
import heapq


class LatencyProxy:
    def __init__(self, target_port, latency=0.1, jitter=0.05, seed=0):
        self.target_port = target_port
        self.latency, self.jitter = latency, jitter
        self.rng = random.Random(seed)
        self.listener = socket.socket()
        self.listener.bind(("127.0.0.1", 0))
        self.listener.listen()
        self.port = self.listener.getsockname()[1]
        self._stop = threading.Event()
        threading.Thread(target=self._accept, daemon=True).start()

    def _accept(self):
        self.listener.settimeout(0.2)
        while not self._stop.is_set():
            try:
                client, _ = self.listener.accept()
            except OSError:
                continue
            upstream = socket.create_connection(("127.0.0.1", self.target_port))
            for a, b in ((client, upstream), (upstream, client)):
                threading.Thread(target=self._pipe, args=(a, b), daemon=True).start()

    def _pipe(self, src, dst):
        queue, lock, last = [], threading.Lock(), [0.0]
        done = threading.Event()

        def sender():
            while not (done.is_set() and not queue):
                with lock:
                    item = queue[0] if queue else None
                if item is None or item[0] > time.monotonic():
                    time.sleep(0.002)
                    continue
                with lock:
                    heapq.heappop(queue)
                try:
                    dst.sendall(item[2])
                except OSError:
                    return
            try:
                dst.shutdown(socket.SHUT_WR)
            except OSError:
                pass

        threading.Thread(target=sender, daemon=True).start()
        seq = 0
        while True:
            try:
                data = src.recv(65536)
            except OSError:
                data = b""
            if not data:
                done.set()
                return
            # delivery time never goes backwards (TCP is ordered)
            due = max(last[0], time.monotonic() + max(0.0, self.rng.gauss(self.latency, self.jitter)))
            last[0] = due
            seq += 1
            with lock:
                heapq.heappush(queue, (due, seq, data))

    def close(self):
        self._stop.set()
        self.listener.close()
