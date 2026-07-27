# Wrath of Ashardalon — ARPG Adaptation Roadmap

## What We Have Now (Demo)
- ✅ Real-time movement with WASD
- ✅ 3 abilities with cooldowns (Cleave, Sweeping Attack, Fireball)
- ✅ Basic attack
- ✅ Monster AI (chase + attack)
- ✅ Health potions
- ✅ Wave spawning
- ✅ Proper sprites (hero knight, skeletons, zombies, ghosts, orcs, demon/dragon bosses)
- ✅ Dungeon room with walls and collision
- ✅ Damage numbers, HP bars, HUD

## What We Need to Build

### Phase 1: Core Systems (make it a real game)
1. **Multiple Rooms + Dungeon Navigation**
   - Generate 8-12 connected rooms
   - Doorways/corridors between rooms
   - Fog of war (rooms hidden until entered)
   - Minimap

2. **Hero Selection (5 Wrath of Ashardalon heroes)**
   - Tarak (Half-Orc Rogue) — fast, backstab
   - Keyleth (Elf Paladin) — tank, divine
   - Quinn (Human Cleric) — healer
   - Heskan (Dragonborn Wizard) — ranged AoE
   - Vistra (Dwarf Fighter) — heavy tank
   - Each with unique abilities matching board game powers

3. **Proper Monster Roster (Wrath of Ashardalon)**
   - Kobold Skirmisher (minion, fast)
   - Orc Smasher (standard, heavy hits)
   - Orc Archer (standard, ranged)
   - Duergar Guard (standard, armored)
   - Legion Devil (spawns in groups)
   - Cave Bear (elite, high HP)
   - Gibbering Mouther (elite, Daze condition)
   - Grell (elite, grab + poison)
   - Snake (minion, poison)
   - Cultist (standard, summons)

4. **Boss Villains**
   - Kobold Dragonlord (Adventure 1 boss)
   - Orc Storm Shaman (Campaign boss)
   - Duergar Captain (Campaign boss)
   - Rage Drake (mid-campaign boss)
   - Gauth (Beholder variant — eye beams)
   - **Ashardalon** (Final boss — RED DRAGON, multi-phase)

### Phase 2: Adventure Structure
5. **Adventure System (13 adventures from the book)**
   - Adventure 1: Escape the Tunnel (solo tutorial, defeat Kobold Dragonlord)
   - Adventure 2: Monster Hunt (defeat 11 monsters)
   - Adventure 3: Roghar's Gear (find item + escape)
   - Adventure 4: Mysterious Chamber (random boss)
   - Adventure 5: Closed Doors (keys/doors mechanic)
   - Adventure 6: Campaign Against the Clans (3-part linked)
   - Adventures 7-11: Various dungeon challenges
   - Adventure 12: The Wrath of Ashardalon (dragon boss fight!)
   - Adventure 13: Full Campaign (all chambers linked)

6. **Win/Lose Conditions**
   - Victory: complete adventure objective
   - Defeat: hero at 0 HP + no shared Life Tokens left
   - Shared Life Tokens (2-3 per adventure)

7. **Encounter Pressure (Corruption Timer)**
   - 30s without exploring new room → bad events start
   - Ambient spawns, traps, damage over time

### Phase 3: Progression & Loot
8. **Treasure/Loot System**
   - Drop from monsters (gold + chance of item)
   - Treasure chests in rooms
   - Item rarities (Common → Legendary)
   - Equipment slots (weapon, armor, boots, accessory)

9. **Experience & Leveling**
   - XP from killing monsters
   - Level 1 → 2 (stat boost + new ability)

10. **Encounter Cards → Random Events**
    - Environment effects (bats, mist, tremors)
    - Traps (dart walls, pit falls)
    - Ambush spawns
    - Rare positive events (healing spring)

### Phase 4: Multiplayer
11. **Co-op Networking**
    - Host-based (one player hosts)
    - WebSocket or UDP for real-time sync
    - Shared dungeon state
    - Drop-in/drop-out

### Phase 5: Polish
12. **Animations** — walk/attack/death frames
13. **Sound effects** — hits, abilities, ambient dungeon
14. **Particle effects** — better fire, ice, magic visuals
15. **Campaign save/load**
16. **Between-adventure town** — buy/sell, respec

---

## Immediate Next Steps (what to build first)

### Step 1: Multi-room dungeon with doors
Turn the single room into a connected dungeon you explore.

### Step 2: Hero select screen
Pick from 5 heroes with different abilities.

### Step 3: Adventure 1 complete
Full playthrough: start → explore rooms → find boss room → defeat Kobold Dragonlord → win screen.

### Step 4: Monster variety
Add 4-5 distinct monster types with different AI behaviors.

### Step 5: Loot drops + equipment
Items drop, equip to get stronger.

---

## File Structure (target)

```
/Users/schenam/Projects/DND/
├── game/
│   ├── engine/
│   │   ├── entities.py       # Hero, Monster, Entity base
│   │   ├── abilities.py      # Ability system, cooldowns, effects
│   │   ├── ai.py             # Monster behavior trees
│   │   ├── combat.py         # Damage calc, conditions, death
│   │   ├── dungeon.py        # Room generation, connections, fog
│   │   └── simulation.py     # Game tick loop, state management
│   ├── content/
│   │   ├── heroes.py         # All 5 hero definitions + abilities
│   │   ├── monsters.py       # All monster types + stats
│   │   ├── adventures.py     # Adventure configs (objectives, rooms, bosses)
│   │   ├── items.py          # Equipment + treasure definitions
│   │   └── encounters.py     # Random event pool
│   ├── rendering/
│   │   ├── renderer.py       # Main draw loop
│   │   ├── sprites.py        # Sprite loading + management
│   │   ├── effects.py        # Particles, floating text, AoE rings
│   │   ├── hud.py            # Health bar, abilities, minimap
│   │   └── menus.py          # Hero select, pause, victory/defeat
│   ├── network/              # Future: multiplayer
│   │   ├── server.py
│   │   └── client.py
│   └── main.py               # Entry point
├── assets/
│   ├── kenney_dungeon/       # Tilemap for environment
│   └── sprites/              # Generated monster/hero sprites
├── tests/                    # Headless tests for game logic
└── design/                   # Design docs (already done)
```
