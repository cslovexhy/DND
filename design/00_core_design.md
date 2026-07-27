# Core Game Design Document
## Multiplayer ARPG — D&D Adventure System Adapted

### Vision
A cooperative real-time Action RPG for 1-5 players, inspired by Warcraft 3's RPG campaigns (Founding of Durotar) and Diablo-style gameplay, built on the mechanical foundation of the D&D Adventure System board games. Players explore procedurally-generated dungeons, fight monsters with cooldown-based abilities, collect loot, and progress through campaigns together.

### Reference Games
- **Warcraft 3: Founding of Durotar** — Hero-focused RPG campaign, real-time, small party
- **Diablo II/III** — ARPG loot grind, abilities with cooldowns, procedural dungeons
- **D&D Adventure System** — Source mechanics (stats, powers, monsters, dungeon generation)

---

## 1. CORE TRANSLATION: Board Game → Real-Time

### Time Scale Conversion
The board game is turn-based with each turn representing ~6 seconds of "narrative time" (matching D&D combat rounds). We use this as our baseline:

| Board Game Concept | ARPG Equivalent |
|-------------------|-----------------|
| 1 Turn (3 phases) | ~6 seconds real-time |
| 1 Square | 1 meter (game unit) |
| 1 Tile (4×4 squares) | 4×4m room/corridor section |
| Speed 5 = 5 squares/turn | 5 m / 6s ≈ 0.83 m/s base walk → scaled to **~3.5 m/s** for feel |
| Speed 6 | ~4.0 m/s |
| Speed 7 | ~4.5 m/s |

> **Design Note:** Raw conversion (5 squares per 6 sec) feels too slow for an ARPG. We multiply by ~4x for responsiveness, matching Diablo/WC3 feel. Relative differences between heroes preserved.

### The Tile System → Room System
Instead of drawing tiles one at a time, rooms are pre-generated chunks that connect procedurally:
- Board game tiles = 4×4 squares → ARPG rooms = 16×16 to 32×32 unit areas
- White triangle tiles = standard rooms (no extra spawns)
- Black triangle tiles = dangerous rooms (extra encounter/ambush on entry)
- Named/quest tiles = scripted objective rooms placed at specific depths

### Fog of War
Board game: unexplored tiles are unknown. ARPG: rooms beyond the current area are hidden. Fog lifts as players explore, matching the progressive dungeon reveal.

---

## 2. COMBAT SYSTEM

### From d20 Rolls to Real-Time Hit Resolution

**Board game:** Roll 1d20 + Attack Bonus ≥ AC → hit, deal fixed damage.

**ARPG adaptation:**

| Mechanic | Board Game | ARPG |
|----------|-----------|------|
| Hit/Miss | d20 + bonus ≥ AC | Every attack hits, but **damage reduction** from Armor (derived from AC) |
| Attack Speed | 1 attack per turn (6s) | Attack speed stat (e.g., 1.0-2.0 attacks/sec) |
| Damage | Fixed (1-3) | Base damage range + scaling |
| Critical Hits | Natural 20 | % chance (5% base, matching d20 nat-20 probability) |

**Why remove hit/miss?** In real-time, missing feels bad and removes player agency. Instead, AC becomes damage reduction (armor), preserving the defensive value without the frustration.

### Damage Formula
```
Damage Dealt = (Base Damage × Ability Multiplier) - Damage Reduction
Damage Reduction = Armor Rating / (Armor Rating + K)
```
Where K is a constant that makes the AC-equivalent scale properly:
- AC 14 (light armor) → ~25% reduction
- AC 16 (medium) → ~35% reduction  
- AC 17 (heavy) → ~40% reduction

### Critical Hits
- Base crit chance: 5% (= rolling nat 20 on d20)
- Crit damage: +100% (base) — can be modified by items
- Board game's "+1 damage on crit" → scales to double damage

---

## 3. ABILITY SYSTEM (Power Cards → Cooldowns)

The board game has three power tiers. We map them to cooldown categories:

| Power Type | Board Game | ARPG Cooldown | Design Intent |
|-----------|-----------|---------------|---------------|
| At-Will | Use every turn, no flip | **0-3 sec cooldown** | Bread-and-butter spam abilities |
| Utility | Flip face-down, recharge via treasure | **15-30 sec cooldown** | Tactical/defensive moves |
| Daily | Flip face-down, strongest | **60-120 sec cooldown** (or "ultimate") | Big moment abilities |

### Ability Slots
Each hero gets (matching board game card counts):
- **2 At-Will slots** — always available, short cooldowns
- **1-2 Utility slots** — medium cooldowns, defensive/support
- **1 Daily slot** — long cooldown "ultimate" ability
- **1 Basic Attack** — auto-attack (no cooldown, lower damage)

### Recharging Powers
Board game uses Treasure Cards to flip Daily/Utility powers back up.
ARPG: Cooldowns reset naturally over time. "Recharge" advancement token → reduces all cooldowns by X%.

---

## 4. MULTIPLAYER & COOPERATION

### Party Size: 1-5 players (same as board game)

### Cooperative Design Pillars (from board game):
1. **Shared resources** — Healing potions are limited party-wide (like Healing Surges)
2. **Threat management** — Monsters target based on proximity/aggro (from tactic scripts)
3. **Role synergy** — Tank/Healer/DPS/Support roles preserved from class design
4. **Shared XP/Loot** — Party experience pool (like shared Experience Pile)

### Scaling
- Monster HP and damage scale with player count
- Board game: designed for fixed 2-5 heroes
- ARPG: dynamic scaling (solo = easier monsters, 5-player = tougher)

---

## 5. DEATH & HEALING

### Board Game System:
- 0 HP → knocked down, must spend shared Healing Surge next turn or ALL lose
- Only 2 surges for entire adventure

### ARPG Adaptation:
- 0 HP → **downed state** (can be revived by allies within 10 seconds)
- If not revived → must spend a **Life Token** (= Healing Surge) to respawn
- Party starts with **2-3 Life Tokens** shared
- 0 Life Tokens + hero downed + no revive = **party wipe / adventure failed**
- This preserves the board game's "shared resource tension" in real-time

### Health Recovery:
- **Health Potions** (limited per adventure, shared pool) — instant burst heal
- **Healer abilities** (Cleric/Paladin/Druid) — cooldown-based
- **Health Regeneration** — very slow passive (1% per 5 sec out of combat)
- **Surge Value** equivalent → amount healed when using a Life Token

---

## 6. EXPLORATION & ENCOUNTER PRESSURE

### The Encounter Timer (Board Game's Smartest Mechanic)
In the board game: if you DON'T explore a new tile, you draw an Encounter Card (bad things happen). This pressures players forward.

**ARPG Adaptation: Creeping Darkness / Corruption Timer**
- A visible timer or encroaching effect builds when players stay too long in cleared areas
- Every X seconds without entering a new room: trigger a random encounter event
- Events: ambush spawns, environmental hazards, debuffs, trap activation
- This prevents camping/farming and maintains forward momentum

### Room Reveal Events
When entering a new room:
- **Standard room (white):** Monsters spawn from designated points, fight begins
- **Dangerous room (black):** Monsters + an Encounter event triggers (trap, environment, extra wave)
- **Quest room (named):** Scripted boss/objective encounter

---

## 7. PROGRESSION & CAMPAIGN

### Single Adventure (= one dungeon run)
- Duration: 20-40 minutes (matching board game session length)
- 8-15 rooms to clear
- 1-2 boss encounters
- Loot collected during run

### Campaign Structure (Temple of Elemental Evil model)
- 8-13 linked adventures with escalating difficulty
- Between adventures: **Town Phase**
  - Swap abilities (respec)
  - Buy/sell items (shop)
  - Trade with party members
  - Level up (spend gold)
  - Buy advancement tokens

### Leveling
- Level 1 → Level 2 (matching board game's single level-up)
- Cost: 1000-2000 gold (earned over several adventures)
- Benefits: +2 HP, +1 Armor, +1 Surge Value, unlock new Daily ability
- Expansion: Can extend to levels 3-5+ for longer campaigns

### Gold Economy
- Monsters drop gold on death (50-200 per monster)
- Treasure chests in rooms (200-500)
- Adventure completion bonus (100-500)
- Items have buy/sell values

---

## 8. CAMERA & CONTROLS

### Perspective: Isometric Top-Down (WC3 / Diablo style)
- Fixed or slightly rotatable camera
- Click-to-move OR WASD movement (player preference)
- Ability keys: Q, W, E, R (matching MOBA/ARPG standard)
- Basic attack: right-click or auto-attack toggle
- Potion: dedicated key (limited uses)

---

## 9. TECHNICAL TARGETS

### Session Architecture
- **Host-based multiplayer** (one player hosts, others join)
- **Authoritative host** for anti-cheat (or dedicated server for competitive)
- **Drop-in/drop-out** — players can join mid-adventure

### Performance Targets
- Support up to 30-50 active enemies on screen
- Smooth at 60 FPS
- Network: playable at <150ms latency

---

## 10. WHAT MAKES THIS UNIQUE vs PURE DIABLO CLONE

1. **Shared Life Tokens** — party survival resource creates tension (not just individual death)
2. **Encounter pressure timer** — can't camp, must push forward
3. **Procedural but structured** — rooms aren't random noise; they follow tile-stack logic with guaranteed boss placement
4. **Campaign persistence** — between-run town phase with meaningful choices
5. **D&D flavor** — familiar classes, monsters, spells, and dungeon aesthetics
6. **Compact sessions** — 20-40 min runs, not 4-hour grind sessions
