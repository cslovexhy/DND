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
