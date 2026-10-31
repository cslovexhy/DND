# 06 — Multiplayer Architecture Plan

Goal: co-op multiplayer across machines (play with kids on custom maps). Any player can host
(Counterstrike-style listen server), not a dedicated WoW-style backend. Single-player must keep working.

## Target architecture

Authoritative host + clients. Host is also a player. Single-player = host with one local client over
an in-process loopback transport, so every test covers both modes.

```
Client (per player)               Host (any player's machine)
 input -> Commands  ──transport──>  validate -> Sim (fixed tick, seeded RNG)
 render <- Snapshots <─transport──  snapshots + events out
 UI / audio / TTS / camera          saves, quests, map authority
```

Layers (dependencies point one way: client/server -> protocol -> sim):
1. sim: pure Python, no pygame, no wall-clock, injected RNG, fixed tick (~30 Hz). Commands in, state + events out.
2. protocol: versioned serializable messages. Commands (MoveTo, Cast, Interact, UsePotion) / Snapshots / Events.
3. server: tick loop, command validation, per-player quest/XP, map + save authority.
4. client: input mapping, rendering, interpolation, UI, music, TTS. Reads snapshots only.
5. transport: loopback -> LAN TCP/WebSocket with join code -> optional relay later.

Why not lockstep: needs bit-exact determinism across machines; hard with Python floats, A*, many monsters.

## Phases (one small CR per step; each has a gate)

- Phase 0 — safety net: headless mode (fixed dt, no window, as fast as possible, `--max-time`, `--seed`,
  `RESULT:` line), golden runs per map, architecture-fitness tests (engine must not import pygame).
  Gate: golden tests pass on current code.
- Phase 1 — extract sim from session.py, no behavior change: `World` object, move systems out one at a time,
  remove runpy/globals handoff, fixed timestep. Gate: golden runs match.
- Phase 2 — commands and events: input produces Commands; UI effects driven by Events. Gate: recorded command
  logs replay to the same final state hash.
- Phase 3 — separate view: renderer takes read-only snapshot. Gate: sim runs with pygame uninstalled.
- Phase 4 — wire format + loopback: schemas, protocol version in handshake, host/client in separate processes,
  fake-network harness (latency, jitter, loss). Gate: client state converges under bad network.
- Phase 5 — multiplayer gameplay: N heroes per world, per-player quest log/XP/loot, lobby (host/join/character
  select), per-machine character saves, host-owned world state. Gate: AI-bot clients play together in sync.
- Phase 6 — custom maps: schema version, validator, content hash, host sends map to joiners; maps are
  untrusted JSON (never code), bounds-checked.
- Phase 7 — netcode polish: interpolation, own-movement prediction, reconnect, state-hash desync checks,
  optional relay/NAT help.

## Backward compatibility

- `run.sh`, `--auto`, `--map`, `--debug` keep working throughout.
- Saves: add schema version, extend `_migrate`, keep real old saves as test fixtures.
- Maps: `schema_version` + upgrade step. Protocol: versioned from first release.

## Testing

Unit (headless, <1s), golden/replay, property tests (pathfinding, damage math, serialization round-trip),
bot soak tests (hero_ai as clients), network chaos tests, one command (`./test.sh`) for everything.

## Risks / open questions

- Python+pygame is fine for 2-4 player co-op; sim is the part to port if scale grows.
- Hosting binds to LAN only by default, with a join code; internet exposure only via an explicit relay step.
- Assumed 2-4 players on a home LAN; characters stay per machine.

## Status

- Phase 0 — done (headless deterministic mode, golden + architecture tests, `./test.sh`).
- Phase 1 — done: simulation extracted from session.py into `game/engine/` (`World`, `PlayerState`, `abilities`,
  `npc`, `events`, `content/monsters`). session.py went from ~2130 to ~1000 lines and is now input + rendering +
  a thin frame loop. Golden runs (5 heroes, 5 maps, 200 s respawn run) are identical to pre-refactor.
  Deferred to phase 3: removing the `runpy`/init_globals handoff (it is a client concern).
  Known leftover: cosmetic randomness (floating-text jitter) still draws from the global sim RNG; it moves to a
  view-only RNG in phase 3 (one deliberate golden regeneration).
- Phase 2 — done: all player input goes through `engine/commands.py` (MoveTo, SelectTarget, Cast, InteractNpc,
  AmbushTarget, UsePotion, ToggleAutopilot, ToggleCompanion, CancelChannel, BindLeftSkill, HoldPosition), submitted
  with `World.submit()` and applied at the start of `World.step()`. Entities have stable ids (`eid`).
  `engine/bootstrap.create_world()` builds the world for both client and tools. `--record-commands` writes a
  command log; `engine/replay.py` replays it with no pygame and reproduces the pygame session's final state
  digest exactly (tests/test_replay.py). Found and fixed on the way: movement speed depended on a render
  constant patched in by main.py (`CHAR_SCALE`); it is now owned by `engine/entities.py`.
- Phase 3 — done: the client renders only from snapshots. `engine/snapshot.py` builds a JSON-able per-player
  snapshot; `client/view.py` mirrors it (entity views persist by id so sprites attach once); `client/local_host.py`
  is the in-process host. Rendering verified pixel-identical to before on 33 frames; a fitness test forbids sim
  access in the render code.
- Phase 4 — done (single player across processes, loopback only): `net/protocol.py` (JSON lines over TCP, versioned
  hello/welcome/reject/frame/cmd), `net/server.py` (authoritative host, fixed 30 Hz real-time tick, flow control:
  a backlogged client skips stale snapshots but keeps every event), `net/client.py` (`RemoteHost`, same interface as
  `LocalHost`). `python3 -m game.net.server --map M --hero H [--auto]` + `python3 -m game.main --connect PORT`.
  Tests: TCP streaming, version/garbage rejection, exact convergence of the client view to host state, the same
  over a 150 ms ±60 ms latency proxy, and a real host process + headless pygame client process.
  Security: the host binds 127.0.0.1 only. Cross-machine play (phase 5) needs a decision on LAN exposure and
  how players are admitted before any non-loopback bind is added.
- Phase 5 (this computer only) — done: several players per World (party XP/kill/quest credit, per-player quest log,
  companions follow their owner, game over when all players are down), host admits up to 4 players with their own
  validated saved characters, personal events routed per player, co-op clients save their own progress from the
  host's snapshots. Map select: H = host, J = join. Not done: playing across machines (see "Open decision").
- Phase 6 — done: `engine/map_schema.py` (schema_version + upgrade, validation with bounds checks, unknown monsters
  are warnings, music restricted to assets/music/, content hash). Every map load is validated; the host sends the map
  to joiners in the welcome message and joiners validate it as untrusted data. The map editor now writes
  schema_version, reports problems on save, and keeps fields it doesn't edit (it used to drop NPCs and music).

- Phase 7 — done (except cross-machine): entity delta compression per client (~850 KB/s -> ~125 KB/s per player at
  30 Hz, protocol v2), client-side interpolation between snapshots for remote play (local play stays exact), and
  joiners auto-reconnect with their saved progress if the host drops. Desync checks are not needed: clients apply
  the host's full authoritative state (deltas are exact, TCP is ordered). Own-movement prediction deferred: on a
  home LAN the delay is ~1 snapshot (33 ms).

## Playing across machines (home network) — done

Decided with the owner: hosting on the home network is opt-in per session (L in map select; H stays
this-computer-only); anyone on the home network who finds the game may join without approval (family play),
up to 4 players; nothing is exposed to the internet (no router/UPnP changes).

- The host binds exactly one interface: 127.0.0.1 (H) or this computer's private home-network IPv4 (L) — never
  0.0.0.0. Only a connection from the host machine itself can take player 0 (the host's own hero).
- Discovery without broadcasting: the joiner scans its own /24 block on the game port and asks `{"t": "info"}`;
  hosts answer with "Name (Lv N) - Map (Xpp) (LAN ip) · players" and close. Typing an address is the fallback.
- Same version everywhere: protocol version in hello/info; pygame-ce pinned to 2.5.7 in run.sh and run.bat, and
  run.sh now sets up .venv on a fresh download like run.bat. How-to: docs/playing_together.md.
- Not tested here: a second physical machine, Windows (run.bat path), guest/isolated Wi-Fi networks.
