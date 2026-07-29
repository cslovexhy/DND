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
