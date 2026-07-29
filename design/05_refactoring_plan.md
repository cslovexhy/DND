# Refactoring Plan — v2 Architecture (Fresh Repo)

> **Decision**: The current repo's architecture is too entangled to incrementally refactor.
> We will create a **new repo** alongside the current one, porting gameplay forward with clean architecture.
> The current repo remains as reference for behavior/visuals/balance numbers.

---

## Problems (current repo)

1. **`_cast_ability` god function**: 26 per-ability if-branches (13 player + 13 companion)
2. **Hardcoded to player**: abilities reference global `hero`, can't run for arbitrary characters
3. **AI is per-class**: FighterAI, ClericAI, RogueAI — duplicate logic, doesn't scale
4. **Heroes ≠ Monsters**: completely different entity types with different code paths
5. **Timing chaos**: GCD/swing/channel/cooldown inconsistently managed per-branch
6. **Ad-hoc buffs**: hand-written per-buff logic in a dict
7. **Rendering coupled to logic**: visual effects spawned inside ability execution

---

## Core Design Principles (v2)

1. **Characters are characters** — heroes and monsters share the same base class, same stat system, same skill system
2. **Skills are standalone** — not tied to any character. Any character can equip any skill.
3. **Skill AI lives on the skill** — each skill knows when it's smart to use itself (`ai_score`). No per-character AI classes.
4. **One generic combat AI** — evaluates all equipped skills by score, picks the best one. Works for heroes AND monsters.
5. **AI operates at human-intent level** — AI does NOT call low-level executor APIs directly. AI produces the same "intents" as human input (e.g., "cast R-slot on target"), resolved through identical controller logic (range checks, walk-to, queuing, cancels). This ensures zero behavioral divergence between human play and AI play. A bug in one is a bug in both.
6. **Same resolution path for everyone** — player input, hero AI, companion AI, monster AI all produce intents → same controller resolves them → same executor processes them.
7. **Event-driven** — skills produce GameEvents, renderer consumes them. Logic and visuals fully decoupled.
8. **MVC strict boundaries** — Model has zero pygame imports, View never mutates state, Controller translates both human input AND AI decisions into the same intent format.

---

## Architecture Overview

```
┌────────────────────┐         ┌─────────────────────┐
│   Player Input     │         │   CombatAI          │
│   (click/key)      │         │   (generic, shared) │
└────────┬───────────┘         └──────────┬──────────┘
         │                                │
         │  "use slot Q"                  │  "use highest ai_score skill"
         ▼                                ▼
┌─────────────────────────────────────────────────────┐
│                  SkillExecutor                       │
│                                                     │
│  1. skill.can_use(caster, target, state)           │
│  2. timing_rule.check(caster)                      │
│  3. skill.execute(caster, target, state)           │
│  4. → list[GameEvent]                              │
│  5. process events (damage, projectiles, buffs)    │
└─────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────┐
│                  GameState                           │
│  characters[], projectiles[], statuses, dungeon     │
└─────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────┐
│                  Renderer                            │
│  Consumes GameEvents → sprites, particles, text     │
└─────────────────────────────────────────────────────┘
```

---

## Skill Design

### Skill = Base class with composed components + ai_score

```python
class Skill:
    name: str
    slot: str                        # Q, R, E, F
    cooldown: float
    color: tuple
    
    # Components (each is a dimension)
    timing: TimingRule               # Instant, SwingGated, Channeled, Dash
    targeting: TargetingRule         # Self, SingleEnemy, SingleAlly, AoESelf, etc.
    delivery: DeliveryRule           # Immediate, Projectile, DashDelivery
    effects: list[Effect]            # DealDamage, Heal, Shield, Debuff, Stealth...
    preconditions: list[Precondition]# RequiresStealth, RequiresTarget, etc.
    
    # AI knowledge (lives on the skill, not on the character)
    def ai_score(self, caster, enemies, allies, state) -> float:
        """0-1 priority. How good is using this right now?"""
        
    def ai_pick_target(self, caster, enemies, allies, state) -> Entity:
        """Who should I use this on?"""
    
    # Core interface
    def can_use(self, caster, target, state) -> (bool, str): ...
    def execute(self, caster, target, state) -> list[GameEvent]: ...
```

### Simple skills = compose, no subclass

```python
fire_blast = Skill(
    name="Fire Blast", cooldown=8.0,
    timing=Instant(),
    targeting=SingleEnemy(range=260),
    delivery=Immediate(),
    effects=[DealDamage(Multiplier(1.0))],
    ai_score=lambda c, e, a, s: 0.8 if e else 0,  # always use when enemies exist
)
```

### Complex skills = subclass, override execute() and/or ai_score()

```python
class Judgement(Skill):
    """Consumes Seal buff for bonus damage."""
    def execute(self, caster, target, state):
        damage = caster.base_damage * 0.8
        if caster.has_buff("righteous_seal"):
            damage += caster.base_damage
            caster.remove_buff("righteous_seal")
        return [DamageEvent(caster, target, damage)]
    
    def ai_score(self, caster, enemies, allies, state):
        if not enemies: return 0
        # High priority if seal about to expire (consume it for value)
        if caster.buff_remaining("righteous_seal") < 2.0:
            return 0.9
        # Medium priority for ranged damage
        return 0.5
```

---

## Character Design

### ONE base class for heroes AND monsters

```python
class Character:
    name: str
    x, y: float
    hp, max_hp: float
    ac: int
    base_speed: float
    base_damage: float
    weapon_speed: float
    attack_range: float
    
    skills: dict[str, Skill]      # slot → Skill instance
    status: StatusManager         # buffs, debuffs, shields, stealth
    sprite: Surface
    
    # AI (same for heroes and monsters)
    ai: CombatAI                  # generic — just scores skills
    is_player_controlled: bool    # if True, AI doesn't run
```

### Hero = Character with more skills, higher stats
### Monster = Character with 1-2 skills, lower stats, aggro behavior

```python
# Hero definition
vistra = Character(
    name="Vistra", hp=400, ac=17, base_damage=40, weapon_speed=1.6,
    skills={"Q": reaping_strike, "R": charge, "E": whirlwind},
)

# Monster definition  
kobold = Character(
    name="Kobold Dragonshield", hp=50, ac=16, base_damage=25, weapon_speed=1.0,
    skills={"Q": basic_melee_attack},
)

# Give a monster stealth? It just works:
shadow_lurker = Character(
    name="Shadow Lurker", hp=80, ac=13, base_damage=30, weapon_speed=0.6,
    skills={"Q": stab, "R": stealth, "E": ambush},  # plays like a rogue automatically
)
```

---

## Generic AI

```python
class CombatAI:
    """One AI for ALL characters. Scores each skill, picks best."""
    
    def decide(self, caster: Character, state: GameState) -> Optional[str]:
        """Returns skill slot to use, or None (move/idle)."""
        best_slot = None
        best_score = 0.1  # minimum threshold to act
        
        for slot, skill in caster.skills.items():
            if not skill.can_use(caster, None, state)[0]:
                continue
            score = skill.ai_score(caster, state.enemies_of(caster), 
                                   state.allies_of(caster), state)
            if score > best_score:
                best_score = score
                best_slot = slot
        
        return best_slot

class ExplorationAI:
    """Movement when not in combat. Pathfinding, explore, follow."""
    def decide_move(self, caster, state) -> Optional[tuple[float, float]]: ...
```

---

## Project Structure (new repo)

```
dnd_arpg/                            # NEW REPO
├── README.md
├── PRINCIPLES.md                    # Copied from current
├── WORKLOG.md                       # Fresh
│
├── game/
│   ├── __init__.py
│   ├── main.py                      # Input + game loop + render (slim)
│   │
│   ├── engine/
│   │   ├── __init__.py
│   │   ├── game_state.py           # GameState (characters, projectiles, dungeon, time)
│   │   ├── game_events.py          # GameEvent dataclasses
│   │   ├── skill_executor.py       # Validates + executes skills + processes events
│   │   ├── status.py               # StatusManager (buffs/debuffs/shields/stealth)
│   │   ├── projectiles.py          # Projectile (carries skill effects)
│   │   ├── dungeon.py              # Ported from current
│   │   └── pathfinding.py          # Ported from current
│   │
│   ├── characters/
│   │   ├── __init__.py
│   │   ├── base.py                 # Character class (shared by heroes + monsters)
│   │   ├── heroes/
│   │   │   ├── __init__.py
│   │   │   ├── vistra.py          # Fighter stats + skill loadout
│   │   │   ├── quinn.py           # Cleric stats + skill loadout
│   │   │   ├── keyleth.py         # Paladin stats + skill loadout
│   │   │   ├── tarak.py           # Rogue stats + skill loadout
│   │   │   └── heskan.py          # Wizard stats + skill loadout
│   │   └── monsters/
│   │       ├── __init__.py
│   │       └── wrath_of_ashardalon.py  # All monster definitions for this campaign
│   │
│   ├── skills/
│   │   ├── __init__.py
│   │   ├── base.py                 # Skill class (can_use, execute, ai_score)
│   │   ├── components/
│   │   │   ├── __init__.py
│   │   │   ├── timing.py          # Instant, SwingGated, Channeled, Dash
│   │   │   ├── targeting.py       # SelfTarget, SingleEnemy, SingleAlly, AoESelf
│   │   │   ├── delivery.py        # Immediate, Projectile, DashDelivery
│   │   │   ├── effects.py         # DealDamage, Heal, Shield, Debuff, Stealth...
│   │   │   ├── damage.py          # Multiplier, MultPlusFlat, MultPlusPercentHP
│   │   │   └── preconditions.py   # RequiresStealth, RequiresTarget, RequiresBuff
│   │   ├── melee.py               # Stab, Smite, ReapingStrike, Whirlwind, BasicBite
│   │   ├── ranged.py              # Wanding, Frostbolt, FireBlast, Judgement, PoisonSpit
│   │   ├── buffs.py               # Wall, Renew, RighteousSeal, HolyLight, Enrage
│   │   └── mobility.py            # Charge, Stealth, Ambush
│   │
│   ├── ai/
│   │   ├── __init__.py
│   │   ├── combat_ai.py           # Generic: score skills, pick best
│   │   └── exploration_ai.py      # Movement: pathfind, explore, follow
│   │
│   └── rendering/
│       ├── __init__.py
│       ├── renderer.py            # Consumes GameEvents → sprites, particles, text
│       └── sprites.py             # Sprite loading + mapping
│
├── assets/                          # Ported from current
├── data/                            # Ported from current
├── design/                          # Ported from current + this plan
└── tests/
    ├── test_skills.py              # Headless skill tests
    ├── test_combat_ai.py           # AI scoring tests
    └── test_status.py              # Buff/debuff tests
```

---

## What Gets Ported vs Rewritten

| From current repo | Action |
|-------------------|--------|
| `assets/`, `data/` | Copy as-is |
| `design/`, `PRINCIPLES.md` | Copy as-is |
| `game/engine/dungeon.py` | Port (minor cleanup) |
| `game/engine/pathfinding.py` | Port (unchanged) |
| Sprite loading code from main.py | Extract to `rendering/sprites.py` |
| Hero stats/numbers from heroes.py | Port to `characters/heroes/*.py` |
| Monster stats from main.py | Port to `characters/monsters/` |
| Ability behavior (from _cast_ability) | Rewrite as Skill classes |
| AI (hero_ai.py) | Rewrite as skill-level `ai_score()` + generic CombatAI |
| Monster AI (ai.py aggro system) | Port aggro logic, rewrite combat to use CombatAI |
| Rendering (from main.py) | Extract to `rendering/renderer.py` |
| Game loop (from main.py) | Rewrite (much simpler with executor) |
| Buff/condition system | Rewrite as StatusManager |

---

## MVC Separation

The new repo enforces strict MVC boundaries:

```
MODEL (game/engine/ + game/skills/ + game/characters/)
│   • Zero pygame imports
│   • Pure Python logic: damage, buffs, AI decisions, state transitions
│   • Fully testable headlessly — no window, no sprites, instant
│   • A model bug = fix model code only, view untouched
│
CONTROLLER (game/controller/)
│   • Translates input → actions: click → "use slot Q on target"
│   • Translates AI decisions → actions: ai_score → "use slot R"
│   • Both produce same output format
│   • Never touches rendering
│
VIEW (game/rendering/)
│   • Reads GameState, consumes GameEvents
│   • Draws sprites, floating text, health bars, cast bars, particles
│   • A visual bug = fix view code only, model untouched
│   • ONLY place with pygame imports (besides main.py init)
```

### Boundary Rules

| Layer | Can import from | Cannot import from |
|-------|----------------|-------------------|
| Model | Python stdlib only | Controller, View, pygame |
| Controller | Model | View, pygame |
| View | Model (read-only) | Controller |
| main.py | All (wiring) | — |

### Auto-Testing Strategy

With strict MVC, the Model is a pure state machine testable without pygame:

```python
# tests/test_skills.py — runs in <1 second, no window

def test_frostbolt_applies_slow():
    state = GameState()
    wizard = create_heskan(100, 100)
    mob = create_kobold(300, 100)
    state.add_characters(wizard, mob)
    
    # Channel completes → projectile spawns
    executor.use_skill(wizard, "Q", target=mob, state=state)
    state.tick(1.2)  # channel time
    
    # Projectile arrives
    state.tick(0.5)
    
    assert mob.status.has("slow")
    assert mob.status.get("slow").value == 0.25

def test_stealth_drops_aggro():
    state = GameState()
    rogue = create_tarak(100, 100)
    mob = create_kobold(120, 100)
    state.add_characters(rogue, mob)
    
    # Mob aggros
    mob.aggro_target = rogue
    
    # Stealth
    executor.use_skill(rogue, "R", state=state)
    
    assert rogue.status.has("stealth")
    assert mob.aggro_target is None

def test_ai_clears_dungeon():
    """Full integration: AI plays a hero through 7 rooms."""
    state = create_adventure("wrath_of_ashardalon", hero=create_vistra())
    
    for _ in range(20000):
        state.tick(0.016)
        if state.victory or state.defeat:
            break
    
    assert state.victory, f"Hero died at room {state.current_room}"

def test_all_heroes_can_clear():
    """Balance test: every hero should win >60% of the time."""
    for create_fn in [create_vistra, create_quinn, create_keyleth, create_tarak, create_heskan]:
        wins = sum(1 for _ in range(50) if simulate_run(create_fn()))
        assert wins >= 30, f"{create_fn.__name__} only won {wins}/50"
```

### Batch Testing for Balance

```bash
# Run 100 simulations per hero, report win rates — no window, <30 seconds
python3 -m pytest tests/ -v

# Or direct:
python3 tests/test_balance.py
# Output:
#   Vistra:  72/100 wins (avg time 45s, avg HP remaining 180)
#   Quinn:   68/100 wins (avg time 52s, avg HP remaining 210)
#   Keyleth: 65/100 wins (avg time 48s, avg HP remaining 150)
#   Tarak:   70/100 wins (avg time 38s, avg HP remaining 120)
#   Heskan:  66/100 wins (avg time 50s, avg HP remaining 195)
```

---

## Updated Project Structure

```
dnd_arpg/                            # NEW REPO
├── README.md
├── PRINCIPLES.md
├── WORKLOG.md
│
├── game/
│   ├── __init__.py
│   ├── main.py                      # Init pygame + wire MVC + game loop
│   │
│   ├── engine/                      # MODEL: pure logic, no pygame
│   │   ├── __init__.py
│   │   ├── game_state.py           # GameState (characters, projectiles, dungeon, time)
│   │   ├── game_events.py          # GameEvent dataclasses
│   │   ├── skill_executor.py       # Validates + executes skills + processes events
│   │   ├── status.py               # StatusManager (buffs/debuffs/shields/stealth)
│   │   ├── projectiles.py          # Projectile (carries skill effects)
│   │   ├── combat.py               # Damage calculation, armor, crit
│   │   ├── dungeon.py              # Dungeon generation
│   │   └── pathfinding.py          # A* pathfinding
│   │
│   ├── characters/                  # MODEL: character definitions
│   │   ├── __init__.py
│   │   ├── base.py                 # Character class (heroes + monsters share this)
│   │   ├── heroes/
│   │   │   ├── __init__.py
│   │   │   ├── vistra.py
│   │   │   ├── quinn.py
│   │   │   ├── keyleth.py
│   │   │   ├── tarak.py
│   │   │   └── heskan.py
│   │   └── monsters/
│   │       ├── __init__.py
│   │       └── wrath_of_ashardalon.py
│   │
│   ├── skills/                      # MODEL: skill definitions + components
│   │   ├── __init__.py
│   │   ├── base.py                 # Skill class (can_use, execute, ai_score)
│   │   ├── components/
│   │   │   ├── __init__.py
│   │   │   ├── timing.py          # Instant, SwingGated, Channeled, Dash
│   │   │   ├── targeting.py       # SelfTarget, SingleEnemy, SingleAlly, AoESelf
│   │   │   ├── delivery.py        # Immediate, Projectile, DashDelivery
│   │   │   ├── effects.py         # DealDamage, Heal, Shield, Debuff, Stealth...
│   │   │   ├── damage.py          # Multiplier, MultPlusFlat, MultPlusPercentHP
│   │   │   └── preconditions.py   # RequiresStealth, RequiresTarget, RequiresBuff
│   │   ├── melee.py               # Stab, Smite, ReapingStrike, Whirlwind, BasicBite
│   │   ├── ranged.py              # Wanding, Frostbolt, FireBlast, Judgement
│   │   ├── buffs.py               # Wall, Renew, RighteousSeal, HolyLight, Enrage
│   │   └── mobility.py            # Charge, Stealth, Ambush
│   │
│   ├── ai/                          # CONTROLLER: decision making
│   │   ├── __init__.py
│   │   ├── combat_ai.py           # Generic: score skills, pick best
│   │   └── exploration_ai.py      # Pathfind, explore rooms, follow
│   │
│   ├── controller/                  # CONTROLLER: input handling
│   │   ├── __init__.py
│   │   └── input_handler.py       # Mouse/keyboard → action commands
│   │
│   └── rendering/                   # VIEW: all pygame/visual code
│       ├── __init__.py
│       ├── renderer.py            # Main render loop (consumes state + events)
│       ├── sprites.py             # Sprite loading + character sprite mapping
│       ├── effects.py             # AoE rings, projectile trails, cast bars
│       ├── hud.py                 # Health bars, skill bar, minimap
│       └── hero_select.py         # Hero selection screen
│
├── assets/                          # Sprites (ported)
├── data/                            # Card data JSON (ported)
├── design/                          # Design docs (ported + this plan)
├── tests/                           # Headless tests (no pygame)
│   ├── test_skills.py
│   ├── test_combat_ai.py
│   ├── test_status.py
│   ├── test_balance.py            # Win rate simulations
│   └── conftest.py                # Shared fixtures (create_hero, create_state)
└── shared_skill/                    # Dev utility skills (preview_markdown, etc.)
```

---

## Map System — WoW-Style Zone Maps

### Vision

Replace the current linear dungeon (chain of rooms connected by corridors) with **open 2D zone maps** inspired by WoW Vanilla zones (Elwynn Forest, Westfall, Deadmines). Each zone is a large continuous map with regions, points of interest, mob territories, and quest objectives.

### MVC for Maps

```
MODEL: game/engine/map_model.py
│   • Zone data: terrain grid, collision, elevation, region boundaries
│   • Mob spawn points + respawn rules
│   • Quest objective locations
│   • Portals/transitions between zones
│   • Zero rendering logic — just data
│
CONTROLLER: game/controller/map_editor.py (dev tool)
│   • Load/save zone files
│   • Place terrain, spawn points, regions
│   • Auto-generate from source image
│
VIEW: game/rendering/map_renderer.py
│   • Tile rendering from terrain grid
│   • Fog of war / visibility
│   • Minimap generation
│   • Smooth camera scrolling
```

### Zone Map Data Model

```python
@dataclass
class ZoneMap:
    """A single zone (like Elwynn Forest or The Deadmines)."""
    name: str
    width: int                    # tiles
    height: int                   # tiles
    tile_size: int = 48           # pixels per tile
    
    # Terrain layers
    terrain: list[list[str]]     # 2D grid: "grass", "dirt", "water", "stone", "wall", etc.
    collision: list[list[bool]]  # 2D grid: True = blocked
    elevation: list[list[int]]   # 2D grid: height level (0=ground, 1=raised, -1=water)
    
    # Regions (named areas within the zone)
    regions: list[Region]        # "Northshire Abbey", "Crystal Lake", etc.
    
    # Spawn data
    spawn_groups: list[SpawnGroup]  # mob clusters with respawn timers
    
    # Points of interest
    quest_points: list[QuestPoint]  # objectives, NPCs, portals
    portals: list[Portal]           # connections to other zones

@dataclass
class Region:
    name: str
    bounds: tuple[int, int, int, int]  # x, y, w, h in tiles
    level_range: tuple[int, int]       # suggested player level
    ambient: str                        # mood/music hint

@dataclass
class SpawnGroup:
    region: str                    # which region this belongs to
    monster_types: list[str]       # which monsters can spawn here
    count: int                     # how many at once
    positions: list[tuple[int,int]] # tile positions
    respawn_time: float            # seconds to respawn after killed
    patrol_path: list[tuple[int,int]] = None  # optional patrol route

@dataclass
class QuestPoint:
    name: str
    position: tuple[int, int]
    quest_id: str
    type: str                      # "objective", "npc", "chest", "boss"

@dataclass
class Portal:
    position: tuple[int, int]
    target_zone: str
    target_position: tuple[int, int]
```

### Auto-Generation from Zone Images

The workflow: take a WoW zone map image → auto-generate terrain data.

```
Source Image (zone_map.png)
    │
    ▼
Image Analyzer (tools/map_generator.py)
    │  • Color sampling: green=grass, brown=dirt, blue=water, grey=stone
    │  • Edge detection: coastlines, cliff edges → collision boundaries
    │  • Region detection: connected color areas → named regions
    │  • Path detection: lighter trails → walkable paths through forests
    │
    ▼
ZoneMap JSON (data/zones/elwynn_forest.json)
    │  • terrain grid
    │  • collision grid
    │  • region boundaries (auto-detected, manually named)
    │
    ▼
Map Editor (manual refinement)
    │  • Adjust collision, place spawns, set patrol paths
    │  • Name regions, set level ranges
    │  • Place quest points, portals
    │
    ▼
Final Zone File (data/zones/elwynn_forest.json)
```

### Image-to-Map Pipeline

```python
# tools/map_generator.py — dev tool, not runtime code

class MapGenerator:
    """Generate ZoneMap from a source image."""
    
    # Color → terrain mapping (configurable per zone style)
    COLOR_MAP = {
        (34, 139, 34):   "grass",      # forest green
        (0, 100, 0):     "dense_tree",  # dark green → blocked
        (139, 119, 101): "dirt",        # brown
        (65, 105, 225):  "water",       # blue → blocked
        (128, 128, 128): "stone",       # grey
        (169, 169, 169): "road",        # light grey → path
        (0, 0, 0):       "wall",        # black → hard boundary
    }
    
    def generate(self, image_path: str, tile_scale: int = 4) -> ZoneMap:
        """
        Convert image to zone map.
        tile_scale: how many pixels per terrain tile (4 = 4x4 pixel area → 1 tile)
        """
        img = load_image(image_path)
        width = img.width // tile_scale
        height = img.height // tile_scale
        
        terrain = []
        collision = []
        for ty in range(height):
            terrain_row = []
            collision_row = []
            for tx in range(width):
                # Sample dominant color in this tile_scale × tile_scale area
                color = self._sample_area(img, tx * tile_scale, ty * tile_scale, tile_scale)
                terrain_type = self._match_color(color)
                terrain_row.append(terrain_type)
                collision_row.append(terrain_type in ("water", "wall", "dense_tree"))
            terrain.append(terrain_row)
            collision.append(collision_row)
        
        # Auto-detect regions (connected components of same terrain)
        regions = self._detect_regions(terrain)
        
        return ZoneMap(
            name="auto_generated",
            width=width, height=height,
            terrain=terrain,
            collision=collision,
            elevation=self._estimate_elevation(terrain),
            regions=regions,
            spawn_groups=[],  # manual step
            quest_points=[],
            portals=[],
        )
    
    def _sample_area(self, img, x, y, size) -> tuple:
        """Average color in a pixel area."""
        ...
    
    def _match_color(self, color) -> str:
        """Find closest terrain type by color distance."""
        ...
    
    def _detect_regions(self, terrain) -> list[Region]:
        """Flood-fill connected terrain areas → regions."""
        ...
    
    def _estimate_elevation(self, terrain) -> list[list[int]]:
        """Water = -1, stone/mountain = 1, else 0."""
        ...
```

### Map Editor (Dev Tool)

A simple pygame-based tool for refining auto-generated maps:

```python
# tools/map_editor.py — separate from game, dev-only

class MapEditor:
    """Visual editor for zone maps."""
    
    def __init__(self, zone_path: str):
        self.zone = load_zone(zone_path)
    
    # Features:
    # - Pan/zoom the map
    # - Paint terrain tiles (brush tool)
    # - Toggle collision
    # - Place spawn groups (click + configure)
    # - Draw patrol paths
    # - Place quest points / portals
    # - Name regions
    # - Save to JSON
    # - Load reference image as overlay (for tracing)
```

### Project Structure Addition

```
dnd_arpg/
├── game/
│   ├── engine/
│   │   ├── map_model.py            # ZoneMap, Region, SpawnGroup, Portal (MODEL)
│   │   └── ... (existing)
│   ├── rendering/
│   │   ├── map_renderer.py         # Tile rendering, fog of war, minimap (VIEW)
│   │   └── ... (existing)
│   └── ... (existing)
│
├── tools/                            # Dev tools (not shipped with game)
│   ├── map_generator.py            # Image → ZoneMap auto-generation
│   ├── map_editor.py               # Visual map editor (pygame dev tool)
│   └── balance_simulator.py        # Batch combat simulations
│
├── data/
│   ├── zones/                       # Zone map JSON files
│   │   ├── tutorial_cave.json      # First zone (replaces current dungeon)
│   │   ├── elwynn_forest.json      # Overworld zone
│   │   └── deadmines.json          # Instance/dungeon zone
│   └── zone_sources/                # Reference images for auto-generation
│       ├── elwynn_forest.png
│       └── deadmines.png
│
└── ... (existing)
```

### Transition from Current Dungeon

The current procedural dungeon (`dungeon.py`) becomes ONE type of zone generation:

| Current | New |
|---------|-----|
| Linear room chain | One possible zone layout (for instances) |
| 7 rooms + corridors | Could be auto-generated OR hand-crafted |
| Fog of war per room | Fog of war by vision radius (smooth) |
| One floor | Multiple zones connected by portals |

The model supports both:
- **Procedural instances**: generate `ZoneMap` at runtime (like current dungeon.py)
- **Hand-crafted zones**: load from JSON (for overworld, story areas)
- **Hybrid**: auto-generate base from image, hand-place spawns and quests

---

1. ✅ Finalize this design document
2. Create new repo with empty structure
3. Implement Model layer bottom-up:
   a. `engine/game_state.py` + `engine/game_events.py`
   b. `characters/base.py`
   c. `engine/status.py`
   d. `skills/base.py` + `skills/components/`
   e. `engine/skill_executor.py`
   f. All 15 skill definitions
   g. All hero + monster definitions
   h. `ai/combat_ai.py`
   i. Port `dungeon.py` + `pathfinding.py`
4. Write headless tests (verify all skills + AI without pygame)
5. Implement View layer:
   a. `rendering/sprites.py`
   b. `rendering/renderer.py` + `rendering/effects.py` + `rendering/hud.py`
6. Implement Controller:
   a. `controller/input_handler.py`
   b. Wire into `main.py`
7. Test: visual gameplay parity with current repo
8. Balance: run batch simulations, tune numbers

---

## Leveling & Progression System

### Core Loop

```
Monster killed → XP awarded (level-scaled)
    → XP exceeds threshold → LEVEL UP!
        → Stats auto-increase (class growth curve)
        → New skill unlocked? → Add to loadout
        → Existing skill ranks up? → Apply upgrade
        → Persist to save file
```

### XP & Levels

```python
@dataclass
class LevelConfig:
    max_level: int = 30
    xp_base: int = 100  # XP needed for level 2

    def xp_multiplier(self, level: int) -> float:
        """Tiered growth: 1.3x early, flattens later."""
        if level <= 10:
            return 1.3
        elif level <= 20:
            return 1.2
        else:
            return 1.1

    def xp_for_level(self, level: int) -> int:
        """Total XP needed to reach this level."""
        total = 0
        for lv in range(1, level):
            total += int(self.xp_base * (self.xp_multiplier(lv) ** (lv - 1)))
        return total

    def xp_to_next(self, level: int) -> int:
        """XP needed from current level to next."""
        return int(self.xp_base * (self.xp_multiplier(level) ** (level - 1)))

@dataclass
class XPReward:
    base_xp: int
    def calculate(self, killer_level: int, target_level: int) -> int:
        diff = killer_level - target_level
        if diff >= 5: return 0                    # grey/trivial
        elif diff >= 3: return int(self.base_xp * 0.25)
        elif diff >= 0: return self.base_xp
        else: return int(self.base_xp * 1.2)     # bonus for punching up
```

### Stat Growth Per Level

Level-up grants **only HP and base damage**. Armor and crit are fixed (come from gear/class baseline).

```python
@dataclass
class StatGrowth:
    hp_per_level: float
    damage_per_level: float

GROWTH_RATES = {
    "Fighter":  StatGrowth(hp=30, damage=3.0),
    "Cleric":   StatGrowth(hp=25, damage=2.0),
    "Paladin":  StatGrowth(hp=28, damage=2.5),
    "Rogue":    StatGrowth(hp=20, damage=3.5),
    "Wizard":   StatGrowth(hp=18, damage=4.0),
}

# Armor and crit do NOT scale with level.
# Armor comes from: base AC (class) + equipment
# Crit comes from: base (5%) + class bonus (Rogue 10%) + equipment
```

### Monster Level Scaling

```python
@dataclass
class MonsterTemplate:
    name: str
    base_level: int
    base_hp: float
    base_damage: float
    base_ac: int
    skills: list[str]
    xp_reward: int

    def create_at_level(self, level: int) -> Character:
        scale = 1.0 + (level - self.base_level) * 0.15  # +15% per level
        return Character(
            name=f"{self.name} (Lv{level})",
            level=level,
            hp=self.base_hp * scale,
            base_damage=self.base_damage * scale,
            ac=self.base_ac + int((level - self.base_level) * 0.3),
            skills=self.skills,
        )
```

### Skill Unlock & Rank-Up

```python
@dataclass
class SkillUnlock:
    skill_id: str
    unlock_level: int
    slot: str

@dataclass
class SkillRank:
    skill_id: str
    rank: int
    level_required: int
    changes: dict  # {"multiplier": 1.5, "cooldown": 6.0}

# Example: Rogue
ROGUE_PROGRESSION = [
    SkillUnlock("stab",       level=1,  slot="Q"),
    SkillUnlock("stealth",    level=1,  slot="R"),
    SkillUnlock("ambush",     level=3,  slot="E"),
    SkillUnlock("eviscerate", level=8,  slot="F"),   # new finisher
    SkillUnlock("shadowstep", level=15, slot="X"),   # blink to target

    SkillRank("stab",    rank=2, level=5,  changes={"multiplier": 1.3}),
    SkillRank("stab",    rank=3, level=12, changes={"multiplier": 1.6}),
    SkillRank("ambush",  rank=2, level=10, changes={"multiplier": 6.0, "pct_hp": 0.25}),
    SkillRank("stealth", rank=2, level=7,  changes={"cooldown": 4.0}),
]
```

### Zone Level Ranges

```python
ZONE_LEVELS = {
    "tutorial_cave":    (1, 3),
    "elwynn_forest":    (1, 10),
    "westfall":         (10, 18),
    "deadmines":        (15, 20),
    "redridge":         (18, 25),
}
```

### Persistence (Save/Load)

```python
@dataclass
class SaveData:
    hero_name: str
    hero_class: str
    level: int
    xp: int
    unlocked_skills: list[str]
    skill_ranks: dict[str, int]
    equipment: dict[str, str]    # future
    zone: str
    position: tuple[float, float]
    quest_progress: dict

    def save(self, path: str): ...

    @classmethod
    def load(cls, path: str) -> 'SaveData': ...
```

### UI Elements Needed

```
┌─── HUD Additions ─────────────────────────────────────────────────┐
│                                                                    │
│  [1] XP Bar — below HP bar, purple/gold, "1,250 / 2,000 XP"     │
│                                                                    │
│  [2] Level Badge — "Lv 7" next to hero name                      │
│                                                                    │
│  [3] Level-Up Effect — gold burst + "LEVEL UP!" + stat summary   │
│                                                                    │
│  [4] Skill Bar — locked skills greyed, "Unlocks Lv 3" tooltip    │
│       New unlock: glow + "NEW!" badge                             │
│                                                                    │
│  [5] Monster Level — "Lv 5" above name, color-coded:             │
│       Grey=trivial  Green=easy  White=normal  Yellow=hard  Red=!!  │
│                                                                    │
│  [6] Character Panel (press C)                                    │
│       Stats + level bonuses, skill list + ranks,                  │
│       XP progress, equipment slots                                │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
```

### MVC Placement

| Component | Layer | File |
|-----------|-------|------|
| LevelConfig, StatGrowth, XPReward | Model | `engine/progression.py` |
| SkillUnlock, SkillRank, skill trees | Model | `skills/progression.py` |
| SaveData (save/load) | Model | `engine/persistence.py` |
| Level-up check + apply | Model | `engine/progression.py` |
| XP bar, level badge, char panel | View | `rendering/hud.py` |
| Level-up particles | View | `rendering/effects.py` |
| Monster level color coding | View | `rendering/map_renderer.py` |
| "Press C" input handling | Controller | `controller/input_handler.py` |

---

## Input Operations (carry forward from v1)

These interaction patterns were refined through extensive playtesting and should be preserved:

### Mouse Controls

| Input | Action |
|-------|--------|
| **Left-click ground** | Move to location (A* pathfinding) |
| **Left-click enemy** | Select target + walk into range + auto-attack with skill 1 |
| **Left-click ally** | Select ally (for targeted heals/buffs, future) |
| **Right-click enemy** | Cast active R-slot skill on target |
| **Right-click ground** | Cast R-slot skill at location (AoE) OR move if skill on CD |
| **Shift + Left-click** | Cast L-slot skill on target (without moving) |

### Keyboard Controls

| Key | Action |
|-----|--------|
| **1, 2, 3, 4** | Assign skill to R-slot (right-click) |
| **Ctrl+1, Ctrl+2, Ctrl+3** | Assign skill to L-slot (left-click auto-attack) |
| **F** | Use potion |
| **F1-F4** | Summon AI companion |
| **TAB** | Toggle AI mode on player hero |
| **+/-** | Game speed (1x/2x/4x) for AI observation |
| **ESC** | Cancel current action (channel, stealth walk-to) / Quit if idle |
| **C** | Character panel (future: stats, skills, equipment) |

### Core Interaction Principles

1. **Left-click = selection/movement, Right-click = primary combat action**
   - Follows Diablo 2 convention
   - Left-click is safe (never attacks without intent)
   - Right-click is offensive

2. **Walk-to-attack**: Left-clicking an enemy queues "walk into range, then auto-attack"
   - No "Too far!" messages — hero walks to target automatically
   - Once in range, skill 1 fires repeatedly (gated by weapon_speed)
   - Changing target = click new enemy (stops attacking old one)

3. **Skill-specific right-click overrides**:
   - Stealth + Right-click enemy (with Ambush on R-slot) = walk-to-ambush (auto-execute on arrival)
   - Channeled skill on R-slot = starts channel immediately if in range

4. **ESC cancels before quitting**:
   - If channeling → cancel channel
   - If in stealth walk-to → cancel and stop
   - If nothing active → quit game

5. **No hidden auto-attack**: ALL damage comes through skills. Skill 1 is the "auto-attack" — there is no separate basic attack system.

6. **Visual feedback for invalid actions**:
   - "No target!" floating text if skill needs target but none selected
   - "Must be stealthed!" if skill requires stealth
   - Locked skills greyed out with level requirement shown

### AI Observation Mode

- **TAB** toggles AI control of the player hero
- **+/-** speeds up game time (2x, 4x) for watching AI play faster
- AI uses the exact same skill execution path as the player
- Useful for balance testing, debugging, and entertainment

### Companion Summoning

- **F1-F4** summons available heroes as AI companions
- Each companion can only be summoned once
- Companions act independently (fight, explore, use skills)
- Same AI system as monsters (score skills, pick best)

### Controller Layer Responsibilities

```python
# controller/input_handler.py

class InputHandler:
    """Translates raw pygame events into game actions."""
    
    def process_event(self, event, state) -> Optional[Action]:
        """Returns an Action or None."""
        # Left-click ground → Action("move", target_pos=...)
        # Left-click enemy → Action("select_target", target=...)
        # Right-click enemy → Action("use_skill", slot="R", target=...)
        # Key press 1-4 → Action("assign_slot", slot="R", skill_index=...)
        # ESC → Action("cancel") or Action("quit")
        # F1-F4 → Action("summon_companion", index=...)
        ...
    
    def get_continuous_state(self, state) -> Optional[Action]:
        """Per-frame: auto-attack loop if target selected and in range."""
        if self.selected_target and self.selected_target.alive:
            if in_range(hero, self.selected_target, hero.skills["Q"].range):
                return Action("use_skill", slot="Q", target=self.selected_target)
        return None
```

### What Changed from v1 That We Keep

| Decision | Reason |
|----------|--------|
| Removed GCD=1.0s, restored at 0.5s | 1.0s felt sluggish, 0s caused spam bugs |
| Removed hidden basic attack | Confusing — all damage through visible skills |
| Walk-to-ambush on right-click | Manual positioning for stealth was too hard |
| ESC cancels channel first | Prevents accidental quit during combat |
| Companions explore independently | Following was buggy, independent feels like real party |
