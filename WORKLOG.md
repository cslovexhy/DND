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
├── game/                      # Actual implementation (TODO)
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
1. **Architect proper game engine** — separate engine/ from rendering/
2. **Multi-room dungeon generation** — connected rooms, doorways, fog of war, minimap
3. **Hero selection screen** — pick from 5 heroes with unique abilities
4. **Adventure 1: Escape the Tunnel** — full playthrough with objective, boss, win/lose
5. **Monster AI variety** — ranged attacks, conditions (Poison, Daze), different behaviors
6. **Loot & equipment system**
7. **Campaign progression** — town phase, level up, advancement tokens

---

## Key Decisions Made
- **2D top-down** (not isometric, not 3D) — simplest, fastest, sprites look good
- **Python + Pygame** — free, headless-testable, fast iteration
- **Wrath of Ashardalon** as first campaign — complete data collected
- **CC0 sprite packs** — Kenney Tiny Dungeon + Clint Bellanger Tiny Creatures
- **Bosses = 1.5× size + color tint** to differentiate from regular monsters
- **Research first, build second** — always gather all info before implementing
