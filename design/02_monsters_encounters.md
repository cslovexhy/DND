# Monster AI & Encounter System

## 1. MONSTER AI (Tactic Cards → Behavior Trees)

### Board Game Monster Tactics
In the board game, each monster has a scripted priority list:
```
IF on same tile as Hero → move adjacent and attack with [Ability]
IF within 1 tile of Hero → use [Ranged Attack]
OTHERWISE → move 1 tile toward closest Hero
```

### ARPG Translation: Behavior Trees

Each monster type has a simple behavior tree matching its board game tactics:

```
BEHAVIOR TREE: [Monster Name]
├── IF in_attack_range(target)
│   └── ATTACK with [primary_ability]
├── ELSE IF in_ability_range(target)  
│   └── USE [special_ability]
├── ELSE
│   └── MOVE toward closest_hero
```

### Targeting Priority (derived from board game "closest Hero" rule)
1. **Closest hero** (default for most monsters)
2. **Lowest HP hero** (for smart monsters: Drow Wizard, Cultists)
3. **Highest threat/aggro** (when taunted by Fighter/Paladin)
4. **Random** (for chaotic monsters: Gibbering Mouther)

---

## 2. MONSTER CATEGORIES

### Tier 1: Minions (1-2 HP in board game → 50-150 HP in ARPG)
Die quickly, come in groups of 3-5 per spawn point.

| Monster | HP | Armor | Speed | Attack | Damage | Behavior |
|---------|-----|-------|-------|--------|--------|----------|
| Skeleton | 80 | 15% | 3.0 | Melee slash | 20 | Rush closest hero, attack |
| Zombie | 100 | 10% | 2.0 | Melee slam | 30 | Slow, relentless advance to closest |
| Kobold | 50 | 10% | 4.0 | Melee dagger | 15 | Rush in packs, flee at 20% HP |
| Rat Swarm | 60 | 5% | 3.5 | Melee bite | 10 | Swarm closest, apply Poison (5/s for 4s) |
| Goblin Cutter | 60 | 12% | 3.8 | Melee short sword | 18 | Flank — try to attack from behind |

### Tier 2: Standard (2-3 HP in board game → 150-400 HP in ARPG)
Dangerous individually, spawn 1-3 per room.

| Monster | HP | Armor | Speed | Attack | Damage | Behavior |
|---------|-----|-------|-------|--------|--------|----------|
| Blazing Skeleton | 180 | 15% | 3.0 | Ranged fire bolt (1.5 tile) | 35 | Stay at range, kite if approached |
| Ghoul | 200 | 20% | 3.5 | Melee claw | 25 | Attack closest; hit applies Immobilize 2s |
| Orc Smasher | 300 | 25% | 3.2 | Melee greataxe | 45 | Charge closest hero, slow heavy swings |
| Drow Duelist | 250 | 22% | 4.0 | Melee dual swords | 30×2 | Target lowest HP, dodge-roll away if focused |
| Bugbear | 350 | 28% | 2.8 | Melee morningstar | 55 | Ambush — invisible until hero enters room |
| Air Cultist | 200 | 18% | 3.5 | Ranged wind bolt | 30 | Stay at max range, apply Disadvantage (slow) |
| Fire Cultist | 180 | 15% | 3.5 | Ranged fire bolt | 40 | Stay at range, AoE fire burst if 2+ heroes close |
| Hobgoblin | 280 | 30% | 3.0 | Melee longsword + shield | 35 | Form shield wall with other hobgoblins, block |

### Tier 3: Elites (3-5 HP in board game → 400-800 HP in ARPG)
Mini-bosses, spawn 1 per dangerous room or as quest targets.

| Monster | HP | Armor | Speed | Attack | Damage | Behavior |
|---------|-----|-------|-------|--------|--------|----------|
| Drider | 600 | 28% | 3.5 | Ranged web + Melee bite | 40/60 | Web (immobilize 3s) at range, close for bite |
| Feral Troll | 700 | 22% | 3.0 | Melee claw ×2 | 35×2 | Regen 20 HP/s unless hit by fire. Rushes lowest HP |
| Beholder Gauth | 500 | 20% | 2.5 (float) | Ranged eye beams | 50 | Hover, rotate beams between heroes, anti-magic zone |
| Ettin | 750 | 30% | 2.5 | Melee dual clubs | 60 | Slam AoE (2 heads attack different targets) |
| Water Elemental | 550 | 25% | 3.0 | Melee engulf | 40 | Engulf (suppress hero for 3s), reform when killed |

### Tier 4: Villains/Bosses (8-15 HP in board game → 1500-5000 HP)
Major encounters, 1 per adventure. Multi-phase, special mechanics.

| Boss | HP | Armor | Phases | Signature |
|------|-----|-------|--------|-----------|
| **Count Strahd** | 3000 | 30% | 2 | Teleport, life drain, charm (fear), summon bat swarms |
| **Ashardalon** (Red Dragon) | 5000 | 35% | 3 | Fire breath cone, tail sweep, fly + divebomb, summon drakes |
| **Gravestorm** (Dracolich) | 4000 | 35% | 2 | Necrotic breath, raise killed monsters as undead, bone storm AoE |
| **Earth Elemental** | 2000 | 40% | 1 | Earthquake stun, slam, throw boulders, enrage at 30% |
| **Acererak** (Lich) | 4500 | 25% | 3 | Soul drain, finger of death, summon undead waves, time stop (freeze all 3s) |
| **Halaster Blackcloak** | 3500 | 28% | 3 | Random school spells, teleport party to random rooms, clone self |

---

## 3. BOSS ENCOUNTER DESIGN

### Phase Transitions (new mechanic for ARPG)
Bosses change behavior at HP thresholds:
- **Phase 1** (100%-60% HP): Standard attack pattern
- **Phase 2** (60%-30% HP): New abilities, increased aggression
- **Phase 3** (30%-0% HP): Enrage, fastest attacks, desperation mechanics

### Example: Count Strahd
```
PHASE 1 (100%-60%):
  - Basic: Melee claw (30 damage, 1.2/s)
  - Every 8s: Charm — fear nearest hero (run away 3s)
  - Every 15s: Life Drain — channel on target, deal 40/s, heal self equal amount (3s)
  
PHASE 2 (60%-30%):
  - Teleport to furthest hero every 10s
  - Summon 4 Bat Swarms every 20s
  - Life Drain now targets 2 heroes
  
PHASE 3 (30%-0%):
  - Permanent mist form: takes 50% less damage
  - Attack speed doubled
  - Charm affects ALL heroes for 2s every 12s
  - Must be killed before party wipes from sustained pressure
```

### Boss Telegraphing
All dangerous abilities have a **1-2 second wind-up** with visual indicators:
- Red circles on ground = AoE incoming (move out!)
- Charging animation = big hit coming (dodge/block!)
- Glowing targets = focused ability on that hero (allies help/peel!)

---

## 4. ENCOUNTER EVENTS (from Encounter Deck)

### Ambient Events (replace Encounter Card draws)
Triggered by the **Corruption Timer** when players don't push forward:

| Event Type | ARPG Effect |
|-----------|-------------|
| **Ambush** | 3-5 monsters spawn behind the party |
| **Environment: Mist** | Vision reduced to 6m for 30 seconds |
| **Environment: Tremors** | Random squares crack, dealing damage if stood on |
| **Trap: Dart Wall** | Projectiles fire from walls across corridors (dodge or take 40 damage) |
| **Trap: Pit** | Floor gives way — fall deals 60 damage, must climb out (3s immobilize) |
| **Event-Attack: Shadowy Bolt** | All heroes take 30 magic damage |
| **Environment: Bats** | Bat swarm obscures vision + deals 10/s for 8s to all heroes |
| **Event: Healing Spring** | Rare positive — fountain appears, restore 100 HP to all heroes |

### Room-Entry Events (for Black Triangle / Dangerous Rooms)
When entering a dangerous room, in addition to monster spawns:
- Roll from event table above
- OR trigger room-specific hazard (lava, flooding, collapsing ceiling)
- These last for the duration of the room fight

---

## 5. SPAWN MECHANICS

### How Monsters Appear (from board game Exploration Phase)
- **On room reveal:** Fixed spawn points per room (matching tile's monster symbols)
- **Wave spawns:** Some rooms have 2-3 waves, next wave after clearing previous
- **Reinforcements:** Boss rooms may have adds spawn on a timer during the fight
- **Ambushes:** Invisible monsters revealed when hero enters trigger zone

### Spawn Scaling (by player count)
| Players | Minion Count | Standard Count | Elite Spawn |
|---------|-------------|----------------|-------------|
| 1 | 2-3 per room | 1 per room | Every 3rd room |
| 2 | 3-4 per room | 1-2 per room | Every 3rd room |
| 3 | 4-5 per room | 2 per room | Every 2nd room |
| 4 | 5-6 per room | 2-3 per room | Every 2nd room |
| 5 | 6-8 per room | 3 per room | Every room |

### Monster Health Scaling
- Base HP × (0.7 + 0.3 × player_count)
- Solo: monsters have 100% HP
- 5 players: monsters have 220% HP

---

## 6. LOOT DROPS

### Drop Table per Monster Tier
| Tier | Gold | Item Chance | Item Rarity |
|------|------|-------------|-------------|
| Minion | 10-30 | 5% | Common 80%, Uncommon 20% |
| Standard | 30-80 | 15% | Common 50%, Uncommon 35%, Rare 15% |
| Elite | 80-200 | 50% | Uncommon 40%, Rare 40%, Epic 20% |
| Boss | 300-500 | 100% (×2 items) | Rare 40%, Epic 40%, Legendary 20% |

### Treasure Chests (from board game treasure symbols on tiles)
- Found in ~30% of rooms
- Guaranteed drop: 1 item (Uncommon or better) + 50-200 gold
- Trapped chests (20% chance): must disarm or take 40 damage before opening

---

## 7. CONDITIONS (Applied by Monsters)

| Condition | Source Monsters | Duration | Effect |
|-----------|----------------|----------|--------|
| **Poisoned** | Rat Swarm, Snake, Troglodyte | 4-8s | 5-15 damage/second |
| **Slowed** | Spider (web), Water Elemental | 3-5s | -50% move speed |
| **Immobilized** | Ghoul, Drider (web), Pit Trap | 2-4s | Cannot move |
| **Stunned** | Ettin (slam), Earthquake | 1.5-3s | Cannot move or act |
| **Feared** | Strahd (charm), Wraith | 2-4s | Run away uncontrollably |
| **Blinded** | Beholder, Bat Swarm, Mist | 3-5s | Vision reduced, -30% accuracy to abilities |
| **Weakened** | Wight, Curse effects | 5-10s | -25% damage dealt |
| **Burning** | Fire Elemental, Fire Cultist | 3-6s | 10-20 damage/second |
