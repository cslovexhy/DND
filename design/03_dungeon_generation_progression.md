# Dungeon Generation & Progression System

## 1. PROCEDURAL DUNGEON GENERATION

### Board Game → ARPG Translation

The board game uses a "tile stack" — a shuffled deck of tiles drawn one at a time as players explore. Quest tiles are inserted at specific positions to guarantee pacing.

**ARPG Equivalent:** A **room graph** generated at adventure start with:
- Fixed structure (linear path with branches)
- Randomized room types/contents
- Guaranteed boss placement at the end
- Guaranteed quest objectives at specific depths

### Room Graph Structure

```
[START] → [Room] → [Room] → [BRANCH] → [Room] → [Room] → [BOSS]
                                 ↓
                              [Room] → [Treasure Room]
```

Each adventure generates 8-15 rooms arranged in a semi-linear graph:
- **Critical path:** 6-10 rooms from start to boss (must traverse to win)
- **Side branches:** 2-5 optional rooms with extra loot/challenge
- **Dead ends:** 0-2 rooms that loop back (small penalty for exploring)

### Room Types (from Tile Types)

| Room Type | Board Game Source | Frequency | Contents |
|-----------|-----------------|-----------|----------|
| **Standard** | White triangle tile | 50% | 1 spawn wave of minions + standards |
| **Dangerous** | Black triangle tile | 25% | Spawn wave + encounter event |
| **Treasure** | Tiles with chest symbol | 10% | Light resistance + treasure chest |
| **Trap Corridor** | Trap tiles | 10% | Environmental hazards + few monsters |
| **Quest Room** | Named tiles | Fixed | Scripted encounter (boss, objective, NPC) |

### Generation Algorithm

```
1. Determine adventure length: SHORT (8 rooms), MEDIUM (12), LONG (15)
2. Place START room and BOSS room at opposite ends
3. Generate critical path between them:
   - Alternate Standard/Dangerous rooms
   - Insert 1-2 Trap Corridors along path
   - Place quest objective room at 60-75% depth
4. Add side branches (1-3):
   - Branch from critical path rooms
   - 1-3 rooms per branch
   - End with Treasure room or dead end
5. Assign monster populations per room (see spawn scaling)
6. Place treasure chests, trap tokens, environmental features
7. Connect rooms with corridors (short connecting passages)
```

### Named Room Templates (Quest Tiles)

These are hand-designed rooms used for specific adventure objectives:

| Room Name | Source | Contents |
|-----------|--------|----------|
| Chapel | Castle Ravenloft | Altar objective, heavy monster guard |
| Laboratory | Castle Ravenloft | Artifact to destroy, villain spawns here |
| Dragon's Lair | Wrath of Ashardalon | Large open room, pillars for cover, boss arena |
| Underground River | Legend of Drizzt | Water hazard, bridge crossing under fire |
| Elemental Node | Temple of Elemental | Elemental boss arena, elemental hazards |
| Guard Room | Temple of Elemental | Final room before exit, ambush encounter |
| Mushroom Grove | Tomb of Annihilation | Interaction objective (harvest), poison hazards |
| Entry Well | Waterdeep | Starting room variant, vertical descent |

---

## 2. ROOM LAYOUT DESIGN

### Room Sizes (from 4×4 tile grid → ARPG scale)

| Size | Dimensions | Use |
|------|-----------|-----|
| Small | 16×16 m | Corridors, trap passages, dead ends |
| Medium | 24×24 m | Standard combat rooms |
| Large | 32×32 m | Boss arenas, treasure rooms |
| Double | 32×48 m | Start rooms, major quest rooms |

### Room Features

Each room contains a randomized selection of:
- **Spawn points** (2-4 per room, along walls/corners)
- **Cover objects** (pillars, crates, rubble) — block line of sight / provide tactical options
- **Hazards** (lava pools, spike floor, poison gas vents)
- **Interactables** (treasure chests, levers, breakable walls, shrines)
- **Entrance/Exit points** (1-3 connections to other rooms)

### Corridor Connections
Rooms connect via short corridors (8-16m long, 4-6m wide):
- Some corridors have traps (triggered when walking through)
- Corridors serve as "safe" transition zones for regrouping
- No monster spawns in corridors (but pursuing monsters follow)

---

## 3. ADVENTURE STRUCTURE

### Single Adventure Flow (One Session = 20-40 min)

```
1. BRIEFING — Read adventure intro, understand objective
2. START ROOM — Party spawns, buffs up, enters first exit
3. EXPLORATION — Clear rooms, fight monsters, collect loot
4. OBJECTIVE — Reach quest room, complete special task
5. BOSS — Final encounter (may be same as objective)
6. ESCAPE (optional) — Some adventures require returning to start
7. AFTERMATH — Loot summary, gold earned, adventure complete
```

### Adventure Types (from board game adventure designs)

| Type | Objective | Example |
|------|-----------|---------|
| **Slay the Boss** | Reach and defeat the villain | "Defeat Count Strahd" |
| **Retrieve Object** | Find item and escape | "Find the Icon of Ravenloft" |
| **Survive/Escape** | Reach exit before time/threats overwhelm | "Escape the Tomb" |
| **Destroy Artifact** | Find and destroy a dangerous object | "Destroy Klak's Artifact" |
| **Rescue** | Find and protect an NPC | "Rescue the Prisoner" |
| **Clear Area** | Defeat all enemies in specific rooms | "Defeat 4 Humans" |
| **Gather** | Collect X items from environment | "Harvest 4 Mushrooms" |

---

## 4. CAMPAIGN PROGRESSION

### Campaign Structure (13 Adventures, matching Temple of Elemental Evil)

```
ACT 1: Introduction (Adventures 1-3)
  - Tutorial mechanics
  - Level 1 heroes, basic monsters
  - Earn first 500-1000 GP
  - Cancel encounters costs 5 XP
  
ACT 2: Rising Threat (Adventures 4-7)
  - Harder monsters, first Elites
  - Level up to 2, buy first Advancement Tokens
  - Encounter cancel costs 6 XP
  - New monster types added to pool after each adventure
  
ACT 3: Deep Dungeons (Adventures 8-10)
  - Elite monsters common
  - Level 3 available
  - Environmental hazards escalate
  - Encounter cancel costs 7 XP
  
ACT 4: Final Confrontation (Adventures 11-13)
  - Boss gauntlet
  - Level 4-5 achievable
  - Toughest encounters
  - Encounter cancel costs 8+ XP
  - Final boss: campaign villain
```

### Between-Adventure: Town Phase

After each adventure (success or failure), players enter the Town:

| Action | Description |
|--------|-------------|
| **Swap Powers** | Change ability loadout (free respec) |
| **Buy Items** | Shop shows 4-6 random items for purchase |
| **Sell Items** | Sell unwanted gear for half buy price |
| **Trade** | Give items/gold to party members |
| **Level Up** | Spend GP to gain a level |
| **Buy Advancement** | Purchase permanent stat upgrades |
| **Repair** | (Future: equipment durability system) |

### Difficulty Scaling Across Campaign

| Adventure # | Monster HP Scale | Gold Reward | New Monsters Added |
|-------------|-----------------|-------------|-------------------|
| 1 | 100% | 200 each | Skeletons, Kobolds |
| 2-3 | 110% | 250 each | Zombies, Rats, Goblins |
| 4-5 | 125% | 300 each | Orcs, Cultists, Spiders |
| 6-7 | 140% | 400 each | Drow, Elementals, Trolls |
| 8-10 | 160% | 500 each | Driders, Beholders, Ettins |
| 11-12 | 180% | 600 each | All monster types available |
| 13 (Final) | 200% | 1000 each | Final boss + all elites |

### Aftermath System (from board game)
After completing an adventure, the result determines what happens:
- **Flawless (0 surges used):** Bonus 200 GP + add beneficial encounter card to deck
- **Standard (1+ surges used):** Standard GP reward
- **Failed:** Keep loot found so far, can retry, gain 1 extra Life Token next attempt

---

## 5. ENCOUNTER DECK EVOLUTION

### How It Works in Real-Time
The "Encounter Deck" becomes a **Room Event Pool** that evolves during campaign:
- Each adventure starts with a base pool of events
- Completing/failing adventures adds/removes events from the pool
- Creates narrative progression: early = mild events, late = deadly events

### Event Pool Progression Example
```
After Adventure 1 (success, no surges):
  ADD: "Elemental Blessing" (positive event, +10% damage for room)
  
After Adventure 1 (success, used surges):
  ADD: "Hidden Traps" (negative, more trap tokens in rooms)
  
After Adventure 3 (success):
  ADD: Advanced monster cards to spawn pool
  REMOVE: Weakest monster types from spawn pool
```

---

## 6. CORRUPTION TIMER (Encounter Pressure)

### Board Game Mechanic
If you don't explore (draw a new tile), you draw an Encounter Card. This punishes staying still.

### ARPG Implementation: The Corruption System

**Visual:** Dark tendrils/mist creep from the edges of cleared rooms.

**Mechanic:**
```
CORRUPTION TIMER:
  - Starts when party has been in fully-explored rooms for 30 seconds
  - Every 15 seconds after that:
    - Stage 1: Warning visual + audio cue
    - Stage 2: Ambient damage (5/s to all heroes)  
    - Stage 3: Monster wave spawns in current room
    - Stage 4: Stronger wave + environment hazard
  - RESETS when party enters a new (unexplored) room
```

**Purpose:** Prevents camping, grinding cleared rooms, or excessive caution. Push forward or suffer.

---

## 7. MULTIPLAYER SESSION FLOW

### Hosting & Joining
```
1. HOST creates campaign (selects adventure) OR continues saved campaign
2. Players JOIN lobby (1-4 additional players)
3. Each player selects their hero + loadout
4. Host starts adventure
5. Dungeon generates for all players simultaneously
6. Party spawns together in Start Room
```

### Drop-In/Drop-Out
- New player joining mid-adventure: spawns at party's current room
- Player disconnecting: hero becomes AI-controlled (follows party, basic attacks only)
- Rejoin: take over AI hero where it is

### End of Session
- Adventure complete OR party wipe → results screen
- All players see: loot earned, gold, XP from monsters
- Town phase: each player independently manages their hero
- Campaign state saved for next session

---

## 8. VISUAL THEMES (from board game settings)

### Dungeon Tilesets

| Campaign Setting | Source Game | Visual Theme | Hazards |
|-----------------|------------|--------------|---------|
| **Castle Ravenloft** | Castle Ravenloft | Gothic castle crypts, stone corridors, coffins | Undead ambushes, darkness |
| **Firestorm Peak** | Wrath of Ashardalon | Volcanic caves, magma rivers, scorched stone | Lava, fire, poison gas |
| **Underdark** | Legend of Drizzt | Caverns, mushroom forests, underground lakes | Darkness, spiders, drowning |
| **Elemental Temple** | Temple of Elemental | Elemental-themed rooms (fire/water/earth/air) | Elemental hazards per room |
| **Chult Jungle** | Tomb of Annihilation | Outdoor jungle + indoor tomb | Traps, poison, undead |
| **Undermountain** | Waterdeep | Classic dungeon, multi-level, varied rooms | Magical wards, runes |
| **Saltmarsh Coast** | Ghosts of Saltmarsh | Coastal caves, pirate ships, flooded tunnels | Flooding, sea creatures |

Each campaign uses a distinct tileset, monster pool, and boss roster.

---

## 9. QUICK REFERENCE: Full Adventure Example

### "Adventure 2: Find the Icon of Ravenloft"

**Objective:** Find the Chapel room and recover the Icon of Ravenloft.

**Dungeon Generation:**
```
Rooms: 12 total (9 critical path, 3 side)
[Start] → [Standard] → [Standard] → [Dangerous] → [Branch] → [Standard] → [Dangerous] → [Trap Corridor] → [Chapel (Quest)]
                                                        ↓
                                                   [Standard] → [Treasure Room] → [Dead End]
```

**Room Contents:**
- Rooms 1-3: Tier 1 minions (skeletons, zombies)
- Rooms 4-6: Mix of Tier 1 + Tier 2 (ghouls, blazing skeletons)
- Room 7 (Trap): Dart walls + pit traps + minimal monsters
- Chapel: ALL players draw monsters (heavy spawn) + Icon on altar
  - Special: Once Icon picked up, Encounter events trigger every 15s until party escapes

**Win:** Destroy all monsters in Chapel + pick up Icon
**Lose:** Any hero down + no Life Tokens remaining

**Aftermath:** 300 GP per hero. Add "Blessing of Ravenloft" treasure to shop.
