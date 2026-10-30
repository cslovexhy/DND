"""In-process host: the client's connection to a World running in the same process (pure; no pygame).

The client only ever calls send() (commands), step() (advance the shared clock) and reads the
snapshot + events it returns. A network host (design/06 phase 4) offers the same interface.
"""
from game.engine.snapshot import make_snapshot


class LocalHost:
    def __init__(self, world, player_id=0):
        self.world = world
        self.player_id = player_id

    def send(self, command):
        self.world.submit(command, self.player_id)

    def step(self, dt):
        """Advance the simulation one step. Returns (snapshot, events) for this client."""
        self.world.step(dt)
        return self.snapshot(), self.take_events()

    def snapshot(self):
        return make_snapshot(self.world, self.player_id)

    def take_events(self):
        events, self.world.events = self.world.events, []
        return events
