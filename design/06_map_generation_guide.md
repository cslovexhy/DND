# Map Generation Guide

## Tile Palette (Kenney Roguelike RPG Spritesheet)

Source: `assets/kenney_rpg/Spritesheet/roguelikeSheet_transparent.png`
- Sheet size: 968×526 pixels
- Tile size: 16×16 with 1px spacing
- Grid: 57 columns × 31 rows
- Extraction formula: `x = col * 17, y = row * 17`

### Terrain Tiles

| Tile (col, row) | Terrain Type | Walkable | RGB Sample | Usage |
|-----------------|-------------|----------|------------|-------|
| **(0, 16)** | Grass | ✓ | (123, 173, 44) | Main ground — open fields, meadows |
| **(5, 10)** | Dirt road | ✓/✗ | (180, 131, 85) | Paths, roads — sometimes blocked for variation |
| **(7, 12)** | Dirt path | ✓ | (180, 131, 85) | Secondary paths, clearings |
| **(3, 7)** | Dense grass/bush | ✓ | (99, 149, 53) | Thick vegetation — walkable undergrowth |
| **(23, 11)** | Tree/bush | ✗ | (123, 173, 44) | Blocked vegetation obstacles |
| **(21, 13)** | Mountain/stone | ✗ | (169, 169, 169) | Border walls, impassable cliffs |
| **(6, 3)** | Stone block | ✗ | (194, 194, 194) | Structures, large rocks |
| **(28, 12)** | Grey stone | ✗ | (163, 168, 179) | Rock formations, ruins |
| **(13, 9)** | Wall/structure | ✗ | (123, 173, 44)* | Building walls, barriers |
| **(3, 1)** | Water | ✓ | (99, 197, 207) | Rivers, lakes, ponds |
| **(3, 19)** | Building floor | ✓ | (198, 101, 39) | Interior floors, camps |

*Note: (13,9) has grass-colored pixels but is used as a structural wall tile*

### Terrain Color Legend (for visualization)

```
Bright green  = Grass (walkable open ground)
Dark green    = Dense vegetation (walkable but thick)
Tan/brown     = Dirt roads and paths
Grey (dark)   = Mountain/stone borders (blocked)
Blue          = Water features
Orange-brown  = Building floors / camps
```

---

## Northshire Valley Map (Reference)

- File: `data/maps/northshire.json`
- Size: 80×60 tiles
- Layers: ground (terrain), objects (unused currently)

### Layout Summary

```
┌─────────────────────────────────────────────────────────────┐
│  MOUNTAIN BORDER (grey stone, blocked all around edges)      │
│                                                              │
│  ┌─ NORTHWEST ──────┐    ┌── NORTHEAST ──────────────────┐  │
│  │ Forest + wolves   │    │ Grass + snakes (green dots)   │  │
│  │ (grey dots)       │    │                               │  │
│  │ Dense trees       │    │                               │  │
│  └───────────────────┘    └───────────────────────────────┘  │
│                                                              │
│  ┌─ WEST ──────┐  ║RIVER║  ┌── EAST (across river) ─────┐  │
│  │ Kobolds     │  ║(blue)║  │ Human Cultists (red dots)  │  │
│  │ (orange)    │  ║  N→S ║  │ Vineyard/camp area         │  │
│  │             │  ║      ║  │ Building (orange square)   │  │
│  │ Church/Abbey│  ║      ║  │                            │  │
│  │ (stone)     │  ║      ║  │                            │  │
│  └─────────────┘  ╚══════╝  └────────────────────────────┘  │
│                                                              │
│  ┌─ SOUTH ───────────────────────────────────────────────┐  │
│  │ Dirt roads heading south                               │  │
│  │ (future: path to Goldshire)                            │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  MOUNTAIN BORDER                                             │
└─────────────────────────────────────────────────────────────┘
```

### Key Positions
- **Hero start**: tile (26, 24) — center-left, near church
- **NPC Marshal McBride**: tile (26, 27) — south of hero start
- **Church/Abbey**: stone walls around (22-25, 18-22) area
- **River**: runs roughly north-south through center (col ~35-40)
- **Mountain border**: 2-4 tiles thick around all edges

### Spawn Zones
| Zone | Mob Type | Count | Area |
|------|----------|-------|------|
| Northwest forest | Grey Wolf | 18 | Top-left, among trees |
| North/central | Kobold Dragonshield | 21 | North of church |
| Northeast (across river) | Snake | 10 | Scattered in grass |
| East (across river) | Human Cultist | 62 | Large camp, vineyard |

---

## WoW Elwynn Forest Reference (WorldMap-Elwynn-old.webp)

### Geography (north to south)
1. **Mountains** (top) — Burning Steppes border, grey/brown ridges
2. **Northshire Valley** — enclosed valley, abbey, small starting area
3. **River** — flows from mountains through center
4. **Goldshire** — central town, crossroads
5. **Farms** — Stonefield Farm (west), Maclure Vineyards (east)
6. **Forests** — scattered throughout, denser in east
7. **Eastvale Logging Camp** — far east
8. **Stonecairn Lake** — large lake, northeast
9. **Westbrook Garrison** — southwest, border to Westfall
10. **Forest's Edge** — south, transition to Westfall/Duskwood

### Key Landmarks for Future Maps
| Zone | Level Range | Key Features |
|------|------------|--------------|
| Northshire Valley | 1-5 | Abbey, wolves, kobolds, defias |
| Goldshire | 5-8 | Inn, shops, crossroads, marshals |
| Fargodeep Mine | 7-9 | Kobold cave system |
| Eastvale Logging Camp | 9-11 | Murlocs, wolves, lumber |
| Westbrook Garrison | 10-11 | Gnolls, Hogger |
| Stone Cairn Lake | 8-10 | Murlocs |

### Road Network
- Main road: Northshire → Goldshire → splits east/west/south
- East fork: Goldshire → Eastvale Logging Camp
- West fork: Goldshire → Westbrook Garrison → Westfall
- South fork: Goldshire → Duskwood (Forest's Edge)

---

## Map JSON Format

```json
{
  "width": 80,
  "height": 60,
  "tile_size": 48,
  "layers": [
    {
      "name": "ground",
      "tiles": [
        [{"col": 0, "row": 16, "walkable": true}, null, ...],
        ...
      ]
    },
    {
      "name": "objects",
      "tiles": [[null, ...], ...]
    }
  ],
  "spawns": [
    {"type": "hero_start", "x": 26, "y": 24},
    {"type": "npc_mcbride", "x": 26, "y": 27},
    {"type": "grey_wolf", "x": 10, "y": 5},
    ...
  ],
  "music": ["assets/music/elwynn_forest.mp3"]
}
```

### Spawn Types Available
- `hero_start` — player spawn (exactly 1 per map)
- `npc_<name>` — quest NPCs
- Monster types: `kobold_dragonshield`, `snake`, `orc_smasher`, `orc_archer`, `grey_wolf`, `duergar_guard`, `gibbering_mouther`, `grell`, `human_cultist`, `legion_devil`
- Boss types: `meerak`, `ashardalon`, `bellax`, `karash`, `margrath`, `rage_drake`, `otyugh`

---

## Design Principles for Map Generation

1. **Mountain borders**: Always surround the playable area (2-4 tiles thick, blocked)
2. **Roads connect landmarks**: Dirt paths between important locations
3. **Water as natural dividers**: Rivers/lakes separate mob zones
4. **Mob density**: ~1 spawn per 20-30 walkable tiles in their zone
5. **Trees for cover**: Scatter blocked vegetation tiles for visual interest + tactical cover
6. **Progressive zones**: Lower-level mobs closer to spawn, harder mobs further out
7. **Clear paths**: Roads should always be walkable (no blocked dirt tiles on main paths)
8. **Transition zones**: Map edges should have road tiles pointing toward adjacent zone connections

---

## Zone Transition System (World Map Architecture)

### Concept
- Each zone is an 80×60 tile map (same size as Northshire)
- Roads at map edges connect to adjacent zones
- Walking off the edge of the map triggers a transition to the neighbor
- Player appears on the corresponding edge of the new map

### Zone Grid Layout (Elwynn Forest)

```
         NORTH
          ↑
    ┌─────┬─────┐
    │     │     │
    │ NW  │ NE  │
    │     │     │
WEST├─────┼─────┤EAST
    │     │     │
    │ SW  │ SE  │
    │     │     │
    └─────┴─────┘
          ↓
        SOUTH
```

Planned zone adjacency for Elwynn Forest:

```
┌──────────────┬──────────────┐
│  Northshire  │  (mountains) │
│  Valley      │              │
│  Lv 1-5     │              │
├──────────────┼──────────────┤
│  Goldshire   │  Eastvale    │
│  Lv 5-8     │  Lv 9-11    │
├──────────────┼──────────────┤
│  Westbrook   │  Stone Cairn │
│  Lv 10-11   │  Lake Lv 8-10│
└──────────────┴──────────────┘
```

### Edge Connection Rules
1. **Matching edges**: If Northshire has a road exiting at the bottom at col 30-35, Goldshire must have a road entering at the top at col 30-35
2. **Mountain continuity**: Mountain borders on shared edges should match (no jarring terrain cuts)
3. **Transition trigger**: When hero.y > map_height * tile_size (walked past south edge), load south neighbor and place hero at y=0 + small offset
4. **Preloading**: Load adjacent maps in background when player enters the edge-most 20% of current map

### Map Naming Convention
```
data/maps/northshire.json      # (row 0, col 0)
data/maps/goldshire.json       # (row 1, col 0) — south of northshire
data/maps/eastvale.json        # (row 1, col 1) — southeast
data/maps/westbrook.json       # (row 2, col 0) — south of goldshire
data/maps/stonecairn.json      # (row 2, col 1) — south of eastvale
```

### Adjacency Metadata (in each map JSON)
```json
{
  "zone_name": "Northshire Valley",
  "zone_level": [1, 5],
  "adjacent": {
    "south": "goldshire",
    "east": null,
    "north": null,
    "west": null
  },
  "exits": {
    "south": {"col_start": 28, "col_end": 35, "target_col_start": 28}
  }
}
```

### Implementation Priority
1. ✅ Northshire (done)
2. 🔲 Goldshire — south of Northshire, central hub
3. 🔲 Zone transition logic in game loop
4. 🔲 Eastvale — east of Goldshire
5. 🔲 Westbrook — south of Goldshire
6. 🔲 Preloading system
