# Work Log — D&D ARPG (Wrath of Ashardalon)

## Session 1 — 2026-07-26

### Phase 1: Research & Source Material
- Downloaded all 18 PDFs from drushomebrew.com (D&D Adventure System rulebooks + adventure books)
- Extracted and analyzed rules from Castle Ravenloft, Temple of Elemental Evil, and Ghosts of Saltmarsh
- Built complete game reference (`game_reference.md`) covering all heroes, powers, monsters, conditions, mechanics across all 7 games
- Created `PRINCIPLES.md` — project rules (research first, verifiable by AI, free tools, faithful to source, iterative)

### Phase 2: Game Design Documents
Created full design docs in `/design/`:
- `00_core_design.md` — Vision, board-game-to-ARPG translation, time/space conversion, camera, multiplayer architecture
- `01_characters_abilities_equipment.md` — 8 hero classes, abilities, items, advancement, leveling
- `02_monsters_encounters.md` — 4 monster tiers, boss phases, AI behaviors, conditions, loot tables
- `03_dungeon_generation_progression.md` — Room generation, campaign structure, town phase, corruption timer
- `04_wrath_of_ashardalon_roadmap.md` — Specific implementation plan for Wrath of Ashardalon campaign

### Phase 3: Tech Stack Decision
- Evaluated Godot, Python+Pygame, TypeScript+Colyseus, Rust+Bevy
- Chose **Python (game logic, headless-testable) + Pygame (rendering)**
- Built headless combat demo (`demo.py`) proving AI can verify all game logic without GUI
- Installed pygame 2.6.1

### Phase 4: Visual Prototype
- Built first visual demo with colored circles (`visual_demo.py`)
- Downloaded **Kenney Tiny Dungeon** pack (dungeon tiles, hero sprites) — CC0
- Downloaded **Tiny Creatures** by Clint Bellanger (180 monster/animal sprites, CC0, same style as Kenney)
- Identified correct sprite positions for all Wrath of Ashardalon entities
- Fixed multiple wrong sprite mappings (bee→snake, furniture→characters, imp→devil)
- Final working demo: `sprite_demo.py` with proper DnD sprites

### Phase 5: Data Collection (Wrath of Ashardalon)
Scraped the D&D Adventure System Wiki (ddadventuresystem.fandom.com) for complete card data:
- `/data/monsters.json` — All 10 monsters with AC, HP, attack bonus, damage, tactics, XP
- `/data/villains_and_heroes.json` — 7 villains + 5 heroes with full stats, abilities, powers
- `/data/powers.json` — 47 power cards across 5 classes with attack bonus, damage, range, effects

### Current State: Demo Complete, Ready for Implementation

---

## Project Structure
```
/Users/schenam/Projects/DND/
├── PRINCIPLES.md              # Project rules
├── WORKLOG.md                 # Session log, pick-up point
├── assets/                    # Art assets (CC0)
│   ├── kenney_dungeon/        #   Dungeon tiles, hero sprites (Kenney Tiny Dungeon)
│   ├── kenney_rpg/            #   Town/environment tiles (not used yet)
│   └── tiny_creatures/        #   180 monster/animal sprites (Clint Bellanger)
├── data/                      # Game card data (scraped from wiki)
│   ├── monsters.json          #   10 monsters: AC, HP, attack, damage, tactics, XP
│   ├── powers.json            #   47 powers: attack, damage, range, effects
│   └── villains_and_heroes.json  # 7 villains + 5 heroes: full card data
├── design/                    # Design documents
│   ├── 00_core_design.md
│   ├── 01_characters_abilities_equipment.md
│   ├── 02_monsters_encounters.md
│   ├── 03_dungeon_generation_progression.md
│   └── 04_wrath_of_ashardalon_roadmap.md
├── docs/                      # Reference material
│   └── game_reference.md      #   Extracted board game data (all 7 games)
├── game/                      # Actual implementation
│   ├── __init__.py
│   ├── main.py                #   Entry point — hero select + game loop + rendering
│   ├── engine/
│   │   ├── entities.py        #   Entity/Hero/Monster classes, abilities, conditions
│   │   ├── dungeon.py         #   Unified tile grid generator (rooms + corridors)
│   │   ├── ai.py              #   Monster AI with aggro system (sense/call/leash)
│   │   └── pathfinding.py     #   A* pathfinding on unified grid
│   ├── content/
│   │   └── heroes.py          #   All 5 heroes with stats and abilities
│   └── rendering/             #   (future: separate renderer module)
├── pdfs/                      # Source PDFs (18 rulebooks + adventure books)
├── prototypes/                # Working demos/POCs
│   ├── demo.py                #   Headless combat test
│   ├── visual_demo.py         #   First visual demo (circles)
│   └── sprite_demo.py         #   Current playable demo (Wrath of Ashardalon sprites)
└── scratch/                   # Temp debug images (safe to delete)
```

---

## Sprite Mapping (Confirmed Working)

### Heroes (from Kenney Tiny Dungeon tilemap)
| Hero | Position (col, row) |
|------|-------------------|
| Vistra (Dwarf Fighter) | dungeon (0, 8) |
| Quinn (Human Cleric) | dungeon (3, 8) |
| Keyleth (Elf Paladin) | dungeon (4, 7) |
| Tarak (Half-Orc Rogue) | dungeon (2, 7) |
| Heskan (Dragonborn Wizard) | dungeon (0, 7) |

### Monsters (from Tiny Creatures tilemap)
| Monster | Position (col, row) |
|---------|-------------------|
| Kobold Dragonshield | creature (9, 7) |
| Snake | creature (0, 4) |
| Orc Smasher | creature (1, 1) |
| Orc Archer | creature (0, 1) |
| Human Cultist | creature (5, 7) |
| Duergar Guard | creature (4, 12) |
| Legion Devil | creature (8, 3) |
| Cave Bear | creature (3, 17) |
| Grell | creature (5, 0) — needs better match |
| Gibbering Mouther | creature (4, 8) |

### Villains (from Tiny Creatures, 1.5× scaled, some tinted)
| Villain | Position | Tint |
|---------|----------|------|
| Ashardalon (Red Dragon) | creature (3, 3) | none |
| Gauth (Beholder) | creature (5, 0) | none |
| Meerak (Kobold Lord) | creature (9, 7) | gold tint |
| Karash (Orc Shaman) | creature (1, 1) | purple tint |
| Margrath (Duergar Captain) | creature (4, 12) | bronze tint |
| Rage Drake | creature (8, 7) | none |
| Otyugh | creature (2, 12) | none |

---

## Next Steps (Implementation)
1. **Play-test and fix/tweak the other 4 heroes** (Quinn, Keyleth, Tarak, Heskan) — balance abilities, ensure dash/range/healing all work
2. **Polish Adventure 1** — boss room feel, victory screen, maybe add more monster variety per room
3. **Loot & equipment system** — items drop, equip for stat boosts
4. **Campaign progression** — town phase, level up, advancement tokens
5. **More adventures** — Adventures 2-13 from Wrath of Ashardalon
6. **Multiplayer** — WebSocket co-op

---

## Session 2 — 2026-07-26 (continued)

### What was built:
- **Unified dungeon system** — single tile grid, rooms connected by corridors, seamless movement
- **Diablo 2 control scheme** — left/right click skill slots, 1/2/3 quick-switch, shift+click for left skill
- **Aggro system** — sense range, call-for-help on attack, leash range, linked groups
- **Proper attack ranges** — monsters stop at attack range (not 0), ranged monsters have cast time (0.5s freeze)
- **Charge skill rework** — smooth dash animation over frames, damage + stun on arrival (not instant)
- **Whirlwind skill** — true AoE melee hitting all enemies in range
- **Range checking** — "Too far!" / "No target!" feedback on all abilities
- **Hero select with mouse** — click panels to select, double-click to confirm
- **Pathfinding click-to-move** — A* on unified grid

### Key design decisions:
- Left-click enemy = select only (no auto-walk). Auto-attack only if already in range.
- Skills cast on right-click (primary combat action). Left-click is for movement/selection.
- Dash abilities (Charge) deal damage ON ARRIVAL, not on cast — creates satisfying gap-closing moment.
- Ranged monsters freeze 0.5s when shooting — gives player counterplay window to close gap.
- Monsters don't aggro until hero enters sense range — allows careful pulling.

### Commits:
- `d5f205a` — Initial commit (all source material, design docs, prototypes, data)
- `fbdd54a` — Playable Adventure 1 with Diablo 2 controls
- `b4c4ae4` — Update worklog
- `ec79353` — Hero AI + automated testing infrastructure
- `80490a0` — 1s GCD, Quinn Seal/Smite/Judgement rework, ClericAI
- `0627bfd` — Holy Light delayed heal, AI stops during combat, Smite range fix
- `e817cc9` — Weapon-based damage system, remove hidden auto-attack
- `a799249` — Keyleth Paladin kit, WIP hero gating, game speed control, boss crash fix

### Late session progress (weapon rework + hero kits):
- **Weapon-based damage system**: All damage from weapon swings. Skills use `multiplier × base_damage + flat_bonus`. No hidden auto-attack.
- **Attack speed**: `weapon_speed` is the single swing timer. Skills fire on swings (cooldown=0 for basic skills, real CD for big ones).
- **Fighter (Vistra)**: 1H Sword+Shield, 40 base, 1.6s. Reaping Strike (120% AoE), Charge (200% dash+stun), Whirlwind (80% AoE).
- **Paladin (Keyleth)**: 2H Mace, 55 base, 2.2s. Smite (100%+30 holy), Seal (+25% buff), Judgement (ranged, consumes seal), Holy Light (2s channel heal).
- **WIP heroes**: Quinn (Cleric), Tarak (Rogue), Heskan (Wizard) — dimmed in hero select, can't be chosen.
- **Game speed**: +/- keys cycle 1x/2x/4x for fast AI observation.
- **Walk-to-attack**: Left-click enemy = walk to + auto-attack. Shift+click = attack in place. No more "Too far!" — queues ability and walks.
- **Boss crash fixed**: Last room no longer crashes (weapon_speed reference fix).

### Key design decisions (this session):
- Basic skills (Smite, Reaping Strike) have cooldown=0 — gated by weapon_speed only.
- Big skills (Charge 8s, Whirlwind 10s, Judgement 10s, Holy Light 30s) have real cooldowns.
- GCD (1s) prevents double-casting but allows weapon swings between CDs.
- Holy Light: 2s channel (immobilized), heal lands AFTER cast — real tradeoff.
- Seal/Judgement combo: Seal buffs Smite +25%, consumed by Judgement for bonus damage.
- AI uses same _cast_ability path as player — consistent behavior.
- Game speed multiplies dt — everything runs faster at 2x/4x, logs still consistent.

### Automated Testing Approach (documented in docs/automated_testing.md):
- `python3 game/main.py --auto` runs the game with AI controlling the hero
- Logs printed to stdout with flush (can capture to file)
- Next steps: add --headless, --max-time, --seed, structured JSON logs, batch runner
- Goal: run 100 simulations per hero, auto-tune difficulty to 60-80% win rate

---

## Key Decisions Made
- **2D top-down** (not isometric, not 3D) — simplest, fastest, sprites look good
- **Python + Pygame** — free, headless-testable, fast iteration
- **Wrath of Ashardalon** as first campaign — complete data collected
- **CC0 sprite packs** — Kenney Tiny Dungeon + Clint Bellanger Tiny Creatures
- **Bosses = 1.5× size + color tint** to differentiate from regular monsters
- **Research first, build second** — always gather all info before implementing

---

## Session 3 — 2026-07-27/28

### All 5 Heroes Completed
- **Quinn (Cleric)**: Wanding (ranged projectile auto, 200px, 25 DPS), Wall (absorb shield 200HP, 15s CD), Renew (HoT 100HP/8s, 16s CD). First projectile system with travel time + on-hit aggro.
- **Heskan (Wizard)**: Frostbolt (channeled 1.2s, immobile, 260px range, 30 DPS = 120% base, 25% slow 3s), Fire Blast (instant nuke 8s CD), Frost Nova (AoE 120px freeze 4s + 25% dmg, 12s CD). Cast bar visual.
- **Tarak (Rogue)**: Stab (0.5s fast melee, 37.5 DPS = 1.5x fighter), Stealth (6s CD, drops aggro, 60% move speed, mobs 10% sense range), Ambush (stealth-only, 5x dmg + 20% mob max HP, 0 CD gated by stealth). Right-click walk-to-ambush. 10% crit (2x).

### New Systems
- **Projectile system**: `Projectile` class in entities.py — travels source→target, damage on arrival, aggro on hit
- **Absorb shield**: Entity.take_damage checks shield before HP, visual blue bubble
- **HoT (heal over time)**: `hot_per_sec` in buffs, ticks each frame
- **FROZEN condition**: Blocks move + attack, blue tint + ice ring visual
- **SLOWED**: Variable `slow_factor` via ActiveCondition (Frostbolt = 0.25)
- **Crit system**: 5% base all heroes, 2x damage. Tarak 10%.
- **Monster ranged projectiles**: Visible red projectiles from ranged mobs
- **AI Companions**: F1-F4 summons other heroes as AI-controlled allies. Full ability handlers for all classes. Monsters target all heroes. Companions explore/fight independently.

### Combat System Changes
- **GCD**: Restored at 0.5s (was removed then added back — needed to prevent ability spam)
- **Removed hidden auto-attack**: All damage through skill 1 abilities only
- **Smite swing_timer gate**: Fixed infinite-cast bug when GCD was removed
- **AoE ring fix**: Only shows when damage actually lands (was spawning every frame)
- **Monsters no longer heal on aggro reset**
- **Frostbolt**: Channel can't be interrupted by movement, ESC/click cancels, bolt chases target regardless of range post-cast
- **Holy Light**: Fixed heal not firing (buff expired before check)
- **Judgement**: Fixed not triggering aggro
- **Stealth**: Breaks when mob detects via stealth_sense_range, breaks on aggro

### AI Improvements
- **ClericAI**: Targets lowest HP ally with Wall/Renew, kites at range
- **WizardAI**: Turret at range, Fire Blast on CD, Frost Nova when mobbed
- **RogueAI**: Stealth→walk→Ambush→Stab cycle, only stealths when meaningful
- **FighterAI**: Uses Charge on CD (not just gap close), always Reaping Strike in melee
- **PaladinAI**: Preserved as separate class from ClericAI
- **Companion AI**: Full ability routing for all 5 classes, pathfinding exploration, ally healing

### Visuals Added
- Frostbolt cast bar (blue progress bar above hero)
- Stealth semi-transparency (player + companions)
- Poison green tint + ring on affected hero
- Frozen blue tint + ice ring on monsters
- Companion HP bars (blue) + name tags
- Companion hit flash (subtle red instead of blinding white)

### Known Issues / Next Session
- **Refactor needed**: `_cast_ability` is player-only — companions duplicate ability logic. Should extract caster-agnostic ability execution function.
- **Companion Tarak**: Stealth→Ambush timing still slightly janky (0.5s GCD delay)
- **No Whirlwind handling** for companion Fighter (uses Reaping Strike + Charge only)
- **Loot & equipment system** still TODO
- **Campaign progression** (town phase, level up) still TODO

### Commits
- `0cb3267` — Quinn Cleric kit (Wanding, Wall, Renew)
- `789c7a1` — Heskan Wizard kit (Frostbolt, Fire Blast, Frost Nova)
- `e5ddb69` — Tarak Rogue kit + major combat fixes
- `(pending)` — AI companions + combat polish

---

## Session 4 — 2026-07-28

### v2 Architecture Design

Decided current repo is too entangled to incrementally refactor — will create a **new repo** with clean architecture, using current repo as reference.

### Key Design Decisions:
- **MVC strict separation**: Model (zero pygame), View (rendering only), Controller (input + AI intent)
- **Characters unified**: Heroes and monsters share same base class, same stat system, same skill system
- **Skills standalone**: Not tied to any character. Grouped by behavior (melee/ranged/buffs/mobility), not by hero class
- **Skill-level AI**: Each skill has `ai_score()` — knows when it's smart to use itself. No per-character AI classes.
- **One generic CombatAI**: Scores all equipped skills, picks best. Works for heroes AND monsters.
- **AI operates at human-intent level**: AI produces same "intents" as mouse clicks, resolved through identical controller logic. Zero divergence between human and AI play.
- **Flat skill composition**: ONE Skill base class + pluggable components (timing, targeting, delivery, effects). Subclass only for truly unique behavior.
- **Auto-testing**: Headless model tests, batch balance simulations (100 runs/hero in <30s)
- **Map system**: WoW-style zone maps, auto-generated from images, editable with dev tool
- **Leveling**: XP tiered curve (1.3x/1.2x/1.1x), level-up grants only HP + damage, armor/crit from gear
- **Input operations**: Carried forward from v1 (Diablo 2 scheme, walk-to-attack, ESC cancels, etc.)

### Deliverable:
- `design/05_refactoring_plan.md` — comprehensive architecture plan (500+ lines)
- `shared_skill/` — copied dev utility skills for future use

### Next Session:
- Create new repo
- Begin implementation: Model layer bottom-up

---

## Session 5 — 2026-07-29/30

### Map Editor Built
- Created full **map editor** (`map_editor.py`) using Kenney Roguelike RPG spritesheet
- Features: tile palette (scrollable), canvas with pan/zoom, 2 layers (ground + objects), walkability painting, flood fill, undo/redo, save/load with filename prompt
- Controls: left-click paint, right-click erase, middle-click pan, arrow keys scroll, scroll zoom
- Spawn system: press 3 for spawn mode, place hero start + monsters on map
- All 10 monster types + 7 bosses + special markers (hero_start, chest, npc) available

### First World Map: Northshire Church
- Created `data/maps/northshire_church.json` — 40×30 tile map
- Painted full ground layer using RPG tiles, marked walkability (1082 walkable, 118 blocked)
- Placed 51 spawns: 18 grey wolves (forest area), 22 kobold dragonshields (church guards), 10 snakes (overgrown area), 1 hero start

### Map Integrated with Game
- Created `game/engine/world_map.py` — WorldMap class loads JSON maps, provides tile data + walkability + spawns
- Duck-type compatible with UnifiedDungeon (is_wall, is_floor, get_start_pos) — pathfinding works unchanged
- `python3 -m game.main --map` launches world map mode; without flag = original dungeon mode
- RPG spritesheet tiles rendered with caching, all monsters spawned at game start
- No fog of war in map mode (full visibility)

### Art & Polish
- Evaluated Kenney Roguelike RPG pack for overworld tiles (grass, water, trees, roads, buildings)
- Swapped dungeon floor/wall to RPG tiles: (8,10) floor, (13,9) wall
- Fixed Orc Archer projectile: red fireball → brown arrow with grey arrowhead
- Renamed Cave Bear → **Grey Wolf** with new sprite (3,2) from Tiny Creatures
- Added `--debug` flag to centralize logging (off by default, `--debug` enables frame/AI logs)

### Commits
- (pending)

### Key Files Created/Modified
- `map_editor.py` — standalone map editor tool (new)
- `game/engine/world_map.py` — map loader for JSON maps (new)
- `game/main.py` — world map mode, RPG tiles, arrow projectile, debug flag
- `data/maps/northshire_church.json` — first hand-painted world map
- `scratch/rpg_tile_viewer.py` — interactive spritesheet browser (dev tool)

---

## Session 6 — 2026-07-30

### Map Editor Improvements
- **Click-to-load files**: Load dialog now shows clickable file list (no more typing filenames)
- **Top-left camera alignment**: Map aligns to top-left on startup and after loading (no manual scrolling)
- **Sample/Eyedropper tool (E)**: Click any tile on canvas to pick it as current brush; palette auto-scrolls to match
- **Walkability drag-paint**: Hold left-click in walkability mode to mass-apply (same as tile painting)

### Northshire v2 Map
- Duplicated `northshire_church.json` → `northshire.json` at 80×60 tiles (doubled width/height)
- Original content preserved in top-left quadrant, rest is empty canvas for expansion
- Game now defaults to `northshire.json`

### Character Scale System
- Added `CHAR_SCALE = 0.5` config in `game/main.py` — single knob controls character sprite size + movement speed
- Characters 50% smaller, move 50% slower → map feels bigger
- `BOSS_SCALE` derived from `CHAR_SCALE * 1.5`
- All sprite loading functions (`get_dungeon_tile`, `get_creature`) use `CHAR_SIZE` 

### Camera Zoom (scroll wheel)
- Mouse scroll zooms in/out (0.5x – 2.0x, default 1.0x)
- All rendering (tiles, characters, projectiles, effects, HP bars) scales with zoom
- Click targeting properly accounts for zoom (screen→world conversion)
- Configurable: `CAM_ZOOM_MIN`, `CAM_ZOOM_MAX`, `CAM_ZOOM_STEP`

### Monster Patrol System
- Monsters now patrol when idle (3-5 random waypoints within patrol_radius of spawn)
- Walk at 40% speed, pause 1-3s at each waypoint
- On aggro: drops patrol, fights normally
- On leash reset: walks back to spawn, resumes patrol from nearest waypoint
- Stuck detection: if monster hasn't moved in 1s during patrol, skips to next waypoint
- Patrol waypoints validated against walkability (won't generate in trees)

### Monster Pathfinding (A*)
- Aggroed monsters now use A* pathfinding to chase (repaths every 0.5s)
- Navigate around trees and obstacles instead of getting stuck on corners
- `_nav_dungeon` reference stored on each monster for pathfinder access

### Companion Fixes
- Companions now spawn at walkable positions (`find_walkable_nearby` helper)
- Teleport (when >600px from hero) lands on valid ground
- No more spawning/teleporting into trees

### Other Fixes
- Human Cultist sprite changed from (5,7) tentacle to (7,6) green humanoid
- FPS counter displayed top-left (green ≥50, yellow ≥30, red <30)
- `run.sh` updated to use `--map` by default

### Key Files Modified
- `map_editor.py` — load click-select, top-left camera, sample tool, walkability drag
- `game/main.py` — CHAR_SCALE, cam_zoom, patrol integration, companion fixes, FPS
- `game/engine/ai.py` — patrol system, A* chase pathfinding, stuck detection
- `game/engine/entities.py` — SPEED_SCALE comment update
- `data/maps/northshire.json` — expanded 80×60 map (new)
- `run.sh` — updated launch command

---

## Session 7 — 2026-08-02

### Map System Fixes
- **Empty tiles now walkable**: `WorldMap.is_tile_walkable` returns `True` for unpainted tiles (walkability determined solely by explicit `walkable: False` flags)
- **Map select screen**: Game now shows map selection before hero select (Dungeon Mode + all maps in `data/maps/`). `--map <path>` skips it.
- **hero_start validation**: Game exits with clear error if map has no hero_start spawn
- **New map**: `haycock.json` (40×30, dungeon layout with bosses)

### Map Editor
- **Locations category (key 4)**: Separated hero_start, chest, NPC, and Connection A-Z into own "Locations" palette (yellow diamonds with letter labels)
- **Spawns category (key 3)**: Now only monsters/bosses (17 entries, no clutter)
- Connection points rendered with letter inside diamond at all zoom levels

### Line of Sight System
- **`has_line_of_sight()`**: Bresenham's tile raycast in `pathfinding.py` — O(n) where n ≈ 5-15 tiles
- **Monster aggro**: Can't detect hero through walls
- **Monster ranged AI**: Won't shoot without clear LOS
- **Player abilities**: Frostbolt, Fire Blast, Wanding, Judgement, Charge all gated by LOS ("No line of sight!")
- **Target selection**: Can't select enemies through walls; target drops if LOS is lost
- **Companion abilities**: Same LOS rules via shared helpers

### AI Overhaul (Pathfinding-Based)
- **Path distance targeting**: AI picks targets by A* path length (cached 0.5s), not euclidean distance
- **All AI movement uses A***: Hero AI, companions, and auto-attack walk all pathfind — no more wall bumping
- **Aggro list**: AI only targets currently-aggroed monsters. Won't pull new packs until current engagement is cleared. Falls back to all alive if nothing engaged.
- **LOS-aware casting**: AI moves toward target via A* until LOS is achieved, then casts
- **Repath every 0.5s**: Hero AI, companions, and monsters all refresh paths at same cadence

### Shared Ability Execution Helpers
- `_exec_fire_blast()`, `_exec_ranged_projectile()`, `_exec_judgement()`, `_exec_stab()`, `_exec_smite()`
- `_can_ranged_hit()`: Range + LOS in one call
- Used by both `_cast_ability` (player/AI) and companion dispatch — single source of truth

### Wizard AI Kiting
- After Frost Nova or Frostbolt, if enemies within 120px, wizard retreats for 0.5s
- Kite timer in `WizardAI._kite_timer` — applies to both hero-AI and companion

### Demoralizing Shout (Fighter E skill, replaces Whirlwind)
- AoE 120px radius (same as Frost Nova), 5s cooldown
- Reduces all nearby enemies damage by 50% for 10s
- Slows enemies 50% for 3s
- Debuff stored in monster `buffs["Demoralized"]` — affects melee and ranged damage
- Buff system moved to Entity base class (monsters now tick buffs too)

### Wall Sliding Fix
- `move_toward` now slides along walls at full speed instead of diagonal-component speed
- Diagonal corner handling: picks dominant axis if diagonal is blocked

### Companion AI Fix
- `move_to` no longer blocked by `elif` when ability fails to fire (cooldown/GCD)
- `comp_acted` flag ensures companions move when abilities can't execute

### Key Files Modified
- `game/engine/pathfinding.py` — `has_line_of_sight()` (Bresenham's)
- `game/engine/ai.py` — LOS in aggro + ranged AI, Demoralized on ranged damage
- `game/engine/hero_ai.py` — path_distance, has_los, get_engaged_monsters, kite timer, all pick_target overrides
- `game/engine/entities.py` — buffs moved to Entity, wall sliding fix, Demoralized in try_basic_attack
- `game/engine/world_map.py` — empty tiles walkable
- `game/content/heroes.py` — Demoralizing Shout replaces Whirlwind
- `game/main.py` — map select, LOS checks, shared helpers, AI dispatch fixes, A* movement
- `map_editor.py` — Locations/Spawns split, connection points A-Z
- `run.sh` — no longer forces `--map`
- `data/maps/haycock.json` — new map

### Commits
- (pending)

## MUST-DO Rules (Future Development)

1. **Hero AI and Companion AI must always use the same code path.** Any behavior that applies to one must apply to the other — targeting logic, LOS checks, pathfinding, ability execution. Never duplicate ability logic between the two; use shared helper functions (`_exec_*`, `_can_ranged_hit`, etc.).

2. **AI behavior must be validated on the Northshire map (solo, no companion).** After any AI change, run:
   ```
   .venv/bin/python3 -m game.main --auto --no-companion --hero <N> --map data/maps/northshire.json --debug > /tmp/ai_test.log 2>&1
   ```
   Acceptance criteria:
   - **No ping-pong**: A character must never reverse direction 4+ times without casting a skill. Detect with the reversal counter on the `[AI ]` log lines (X position changes direction without a Q/R/E action in between).
   - **Reasonable kill count**: The hero should kill multiple mobs within ~80s game-time (at 4x speed). Zero or near-zero kills indicates a stuck/broken AI.
   - **Survival**: The hero should not die (DEFEATED) unless intentionally testing difficulty. Reaching very low HP is acceptable.
   - **Cast activity**: The hero should be casting skills regularly, not spending long stretches only moving or idle.


---

## Session 8 — 2026-08-04

### Python/Environment Fix
- Python upgraded from 3.12 to 3.14 (Homebrew), broke pygame import
- Created `.venv` virtual environment, installed `pygame-ce` 2.5.7 (community edition, compatible with 3.14)
- Updated `run.sh` to use `.venv/bin/python3` directly with helpful error message
- Created `mapEditor.sh` launcher script

### Walk-to-Range Skill Queueing (Player QoL)
- **All targeted skills** now queue walk-to-range when out of range instead of doing nothing
- **Fire Blast**: no longer shows "Too far!" — queues walk + cast like other ranged skills
- **Ambush**: routes through `ambush_target` path (works while stealthed) with A* pathfinding instead of direct-line `move_toward`
- **Cancellation**: any click (ground, new enemy, new skill) cancels queued walk + pending cast
- **Ambush walk-to**: uses A* pathfinding, cancels on LOS loss or stealth break

### Rogue Improvements
- **Stealth cooldown**: 6s → 2s (much more frequent Stealth→Ambush cycling)
- **Auto-bind right-click**: entering stealth binds right-click to Ambush, breaking stealth binds back to Stealth
- **AI target lock**: Rogue locks `_ambush_target` while stealthed — no more ping-pong between equidistant mobs
- **AI waits for Stealth CD**: won't Stab if Stealth is <0.5s from ready, enabling immediate re-stealth→Ambush cycle

### Wizard AI Overhaul (Smart Kiting)
- **Frostbolt never wasted**: cast fires whenever ready + in range + LOS, regardless of enemy distance
- **Smart kite algorithm** (`_find_best_kite_position`):
  1. Evaluate 8 directional candidates (120px step)
  2. Filter by walkability + LOS from current position
  3. Score by **minimum distance** to nearest threat (within 500px radius)
  4. Pick direction that maximizes distance from closest mob
- **Kite priority**: enemies < 130px → kite first then cast; 130-260px → cast immediately; on CD + enemies < 220px → kite between casts
- **GCD kiting**: during GCD, actively repositions using smart kite (< 220px) or closes gap (> 260px)
- **Eliminated ping-pong**: wizard no longer oscillates when cornered — finds viable retreat paths around walls

### Map Data Fix
- Removed unreachable mob spawn on non-walkable tile (20,2) in `northshire.json`
- Root cause: Kobold Dragonshield spawned on `walkable=False` ground tile (kenney_rpg col=5 row=10)
- A* correctly found no path, but AI kept targeting the unreachable mob indefinitely

### Auto-mode Improvements
- Added `--no-companion` flag: test hero AI solo without companion skewing results
- Fixed `find_walkable_nearby` ordering bug (function used before defined in `--auto` mode)
- `game_speed = 4.0` now set outside companion block (works with `--no-companion`)

### Debug Logging
- Added `target_pos` and `path_len` to `[AI]` debug log lines for diagnosing stuck states

### AI Testing Protocol (added to MUST-DO Rules)
- Validate on Northshire map (open field) AND Haycock (dungeon corridors)
- Solo, no companion, 4x speed, ~20s wall-clock
- Check: 0 ping-pong, reasonable kills, survival, cast activity

### Key Files Modified
- `run.sh` — venv launcher
- `mapEditor.sh` — new map editor launcher
- `game/main.py` — skill queueing, auto-bind, debug logging, --no-companion, auto-mode fix
- `game/engine/hero_ai.py` — Rogue target lock, Wizard smart kite, ping-pong fixes
- `game/engine/world_map.py` — added `tile_size` attribute from JSON
- `game/content/heroes.py` — Stealth CD 6→2s
- `data/maps/northshire.json` — removed unreachable mob spawn
- `WORKLOG.md` — session log, AI testing rules

### Test Results (end of session)
| Hero | Map | Kills | Died | Ping-pong |
|------|-----|-------|------|-----------|
| Wizard | Haycock | 14 | 0 | 0 |
| Wizard | Northshire | 13 | 0 | 0 |
| Rogue | Northshire | 30 | 0 | 0 |

---

## Session 9 — 2026-08-05

### Development Strategy Change
- **Focus hero: Heskan (Wizard) only.** All gameplay optimization, AI tuning, and feature development uses Wizard as the sole test subject going forward. Other heroes will be reworked/rebalanced at a major milestone, not after every update. This reduces iteration overhead significantly.

### Changes
- **Removed extra lives system**: No more `life_tokens` / revive mechanic. 1 life — death = game over.
- **Maximized window**: Game now starts at full screen size (resizable). Handles `VIDEORESIZE` events in all loops (map select, hero select, game loop).
- **Health regeneration**: All entities regen HP passively.
  - In combat (monster aggroed): 0.5% max HP/sec
  - Out of combat: 2% max HP/sec
  - `in_combat` flag set per-frame based on aggro state

### Key Files Modified
- `game/engine/entities.py` — removed `life_tokens`, simplified `check_hero_death()`, added regen (`in_combat`, `regen_rate_combat`, `regen_rate_ooc`) to `Entity`
- `game/main.py` — removed lives HUD/init, maximized+resizable window, VIDEORESIZE handling, combat state update loop for regen
- `WORKLOG.md` — session log

---

## Session 10 — 2026-08-07

### Environment Setup (Windows)
- Cloned repo on Windows machine for the first time
- Installed Git 2.55.0 and Python 3.12.10 via winget (Windows Package Manager)
- Created `.venv` and installed `pygame-ce` 2.5.7
- Downloaded Kenney Roguelike RPG pack (CC0, OpenGameArt) — `roguelikeSheet_transparent.png` required by map editor
- Removed `assets/kenney_rpg/` from `.gitignore` and checked in the spritesheet so the map editor works out of the box on a fresh clone
- Verified map editor and game both launch successfully on Windows

### Music System
- Added `music` list field to `WorldMap` — maps can specify a playlist in their JSON
- `main.py` initializes `pygame.mixer` and plays/loops tracks when a map loads
- Downloaded `assets/music/elwynn_forest.mp3` (WoW Classic, 3:03, 6MB) — assigned to Northshire maps

### Important Asset Resources
- **WoW Classic full music gamerip**: https://downloads.khinsider.com/game-soundtracks/album/world-of-warcraft-direct-game-rip
  - All original in-game music tracks (~4-6MB each)
  - Tracks of interest: Elwynn Forest, Stormwind, Ironforge, Tavern, Combat, etc.
  - Download via browser → get lambda.vgmtreasurechest.com link → can wget/curl from there
- **WoW Alpha Ambience Tracks (0.5.3)**: https://downloads.khinsider.com/game-soundtracks/album/world-of-warcraft-053-ambience-tracks-macos-windows-gamerip-2003
  - Environmental ambience (chirps, wind, etc.) — 65 tracks, ~4.75MB each
  - Useful for layering on top of music

---

## Session 7 — 2026-08-07

### Mob Respawn System
- Killed mobs respawn after 60 seconds at their original spawn position
- Fresh HP, aggro, and patrol route on respawn
- Bosses never respawn
- Timer uses in-game time (affected by game speed multiplier)

### Leveling System
- XP curve: 100 base, tiered multiplier (1.3× levels 1-10, 1.2× 11-20, 1.1× 21-30)
- Max level 30
- On level-up: stat growth per class (Fighter +30HP/+3dmg, Wizard +18HP/+4dmg, etc.)
- Full health restore on level-up
- Gold expanding ring visual effect + floating "LEVEL UP!" text
- Purple XP bar in HUD below HP bar showing "Lv X  XP current/needed"

### Mob XP Values (5× base)
- Kobold/Snake/Cultist: 5 XP
- Wolf/Orc Smasher/Duergar/Grell: 10 XP
- Gibbering Mouther/Legion Devil: 15 XP
- Bosses: 25-50 XP

### Quest System (WoW Classic Northshire)
- Quest data structure with kill objectives, rewards, chaining
- 5-quest Northshire chain based on Classic WoW:
  1. A Threat Within (intro, talk to NPC)
  2. Kobold Camp Cleanup (kill 10 Kobold Dragonshields)
  3. Wolves Across the Border (kill 8 Grey Wolves)
  4. Brotherhood of Thieves (kill 12 Human Cultists)
  5. Northshire Secured (kill 5 of each type)
- NPC: Marshal McBride south of church with yellow !/? indicators
- Auto-interact: walk within range to accept/turn-in quests
- Quest HUD: title + objective progress at top center
- Quest popup notifications for accept/complete/turn-in
- Kill tracking with floating progress text

### Entity Refactor
- Moved `level`, `abilities`, `stealthed`, `gcd`, `add_ability()` from Hero up to Entity base class
- All entities (Hero/Monster/NPC) now share: level, abilities, stealth, combat stats
- NPC class now inherits Entity (with minimal combat stats: hp=5, ac=10, speed=0)
- Monster gets `level` attribute for future XP scaling
- Zero behavioral change — attribute access unchanged for existing code

### Save System
- Persists to `data/saves/<hero_name>.json`
- Saves: level, XP, gold, kills, completed quests, current quest ID
- Auto-saves on: level-up, quest turn-in, game exit
- Auto-loads on game start (applies level bonuses retroactively)

### Companion Improvements
- **Health bars in HUD**: Blue bars with name below potions (shows "(dead)" status)
- **F1-F4 toggle**: Press same key to dismiss companion (removes from party)
- Skill list auto-shifts down to make room for companion bars

### Key Files Modified
- `game/engine/entities.py` — Entity refactor (level, abilities, stealth, gcd moved up)
- `game/main.py` — Respawn, leveling, quests, NPC, save/load, companion HUD/dismiss
- `data/maps/northshire.json` — Added npc_mcbride spawn point
- `.gitignore` — Added data/saves/
