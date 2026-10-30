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
