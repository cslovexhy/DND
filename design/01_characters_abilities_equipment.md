# Character Stats, Abilities & Equipment System

## 1. HERO STATS

### Primary Stats (Derived from Board Game)

| Stat | Board Game Source | ARPG Range | Description |
|------|-----------------|------------|-------------|
| **Health (HP)** | HP (6-12) | 300-600 at Lv1 | Scaled ×50 for granularity. Lv1 Wizard=300, Fighter=500 |
| **Armor** | AC (14-17) | 25%-40% DR | Damage reduction percentage |
| **Move Speed** | Speed (5-7) | 3.5-4.5 m/s | Base movement speed |
| **Attack Speed** | 1/turn | 0.8-1.5 atk/s | How fast basic attacks swing |
| **Surge Value** | Surge (3-6) | 150-300 HP | HP restored when using a Life Token |
| **Crit Chance** | Nat 20 | 5% | Chance to deal double damage |

### Secondary Stats (from equipment/advancement)
| Stat | Effect |
|------|--------|
| **Cooldown Reduction** | Reduces ability cooldowns (max 40%) |
| **Life Steal** | % of damage returned as HP |
| **Bonus Damage** | Flat added to all attacks |
| **Magic Resist** | Reduces magic damage specifically |
| **Thorns** | Reflects X damage to melee attackers |

---

## 2. HERO CLASSES

### Design Philosophy
Each class maps to a board game hero with distinct role:
- **Tank** — High HP, high Armor, crowd control (Fighter, Paladin)
- **Healer/Support** — Party sustain, buffs (Cleric, Druid, Bard)
- **Ranged DPS** — High damage from distance (Wizard, Sorcerer, Ranger)
- **Melee DPS** — High burst, mobility (Rogue, Barbarian)

---

### FIGHTER (Tank / Melee DPS)
*Based on: Allisa, Alaeros, Vistra, Atka*

| Stat | Value |
|------|-------|
| HP | 500 |
| Armor | 38% DR |
| Move Speed | 3.5 m/s |
| Attack Speed | 1.0/s |
| Surge Value | 250 |

**Abilities:**
| Slot | Name | Cooldown | Effect |
|------|------|----------|--------|
| At-Will 1 | **Cleave** | 2s | Swing in arc, hit all enemies in front. 100% weapon damage |
| At-Will 2 | **Tide of Iron** | 3s | Shield bash. Deals 80% damage, pushes target back 2m |
| Utility 1 | **Unstoppable** | 20s | Remove all conditions, +30% move speed for 4s |
| Utility 2 | **Challenging Shout** | 25s | Taunt all enemies within 6m for 4 seconds |
| Daily | **Sweeping Attack** | 90s | Massive whirlwind. 200% weapon damage to all within 4m, stuns 2s |

**Special Ability: Dwarven Resilience / Action Surge**
- Passive: Regenerate 1% HP per second while below 30% health

---

### CLERIC (Healer / Support)
*Based on: Thorgrim, Quinn, Barrowin, Cormac*

| Stat | Value |
|------|-------|
| HP | 400 |
| Armor | 35% DR |
| Move Speed | 3.5 m/s |
| Attack Speed | 0.8/s |
| Surge Value | 200 |

**Abilities:**
| Slot | Name | Cooldown | Effect |
|------|------|----------|--------|
| At-Will 1 | **Lance of Faith** | 2.5s | Ranged bolt, 1 tile range. 90% weapon damage + target takes 10% more damage for 3s |
| At-Will 2 | **Healing Strike** | 3s | Melee attack. 80% damage, heals nearest ally for 50 HP |
| Utility 1 | **Healing Word** | 18s | Heal target ally for 150 HP (= surge value) |
| Utility 2 | **Shield of Faith** | 25s | Target ally gains +15% Armor for 8 seconds |
| Daily | **Beacon of Hope** | 90s | All allies within 2 tiles heal 200 HP over 10 seconds, cures conditions |

**Special Ability: Healer**
- Passive: When using any Daily/Utility power, closest ally on same "tile" regains 50 HP

---

### WIZARD (Ranged DPS / Control)
*Based on: Immeril, Heskan, Nymmestra, Asharra, Marcon*

| Stat | Value |
|------|-------|
| HP | 300 |
| Armor | 25% DR |
| Move Speed | 4.0 m/s |
| Attack Speed | 0.8/s |
| Surge Value | 150 |

**Abilities:**
| Slot | Name | Cooldown | Effect |
|------|------|----------|--------|
| At-Will 1 | **Magic Missile** | 1.5s | Ranged bolt, auto-hit, 2 tile range. 70% weapon damage |
| At-Will 2 | **Thunderwave** | 4s | AoE blast around self. 90% damage, pushes enemies 3m back |
| Utility 1 | **Shield** | 15s | Block next incoming attack completely. Lasts 5s or until triggered |
| Utility 2 | **Fey Step** (Teleport) | 20s | Instantly teleport up to 6m in any direction |
| Daily | **Fireball** | 80s | Massive AoE at target location. 250% damage to all in 5m radius |

**Special Ability: Arcane Mastery**
- Passive: Critical hits reduce all cooldowns by 2 seconds

---

### ROGUE (Melee DPS / Mobility)
*Based on: Kat, Tarak, Ratshadow, Trosper*

| Stat | Value |
|------|-------|
| HP | 400 |
| Armor | 28% DR |
| Move Speed | 4.2 m/s |
| Attack Speed | 1.5/s |
| Surge Value | 200 |

**Abilities:**
| Slot | Name | Cooldown | Effect |
|------|------|----------|--------|
| At-Will 1 | **Sneak Attack** | 3s | If behind target or target attacking ally: 180% damage |
| At-Will 2 | **Deft Strike** | 2s | Dash 3m toward target, deal 100% damage |
| Utility 1 | **Stealth** | 20s | Become invisible for 5s. Next attack from stealth: guaranteed crit |
| Utility 2 | **Unbalancing Parry** | 15s | Next enemy attack misses, attacker is stunned 1.5s |
| Daily | **Dagger Barrage** | 75s | Throw 8 daggers in a cone. Each deals 80% damage. Total=640% |

**Special Ability: Nimble**
- Passive: +15% move speed. Dodge chance 10% (attacks pass through)

---

### RANGER (Ranged DPS / Hybrid)
*Based on: Arjhan, Talon, Drizzt, Artus Cimber*

| Stat | Value |
|------|-------|
| HP | 400 |
| Armor | 30% DR |
| Move Speed | 4.0 m/s |
| Attack Speed | 1.2/s |
| Surge Value | 200 |

**Abilities:**
| Slot | Name | Cooldown | Effect |
|------|------|----------|--------|
| At-Will 1 | **Careful Shot** | 2s | Long range (3 tiles). 120% weapon damage, high accuracy |
| At-Will 2 | **Twin Strike** | 2.5s | Two quick melee attacks, 70% damage each |
| Utility 1 | **Hunter's Mark** | 18s | Mark target: all party members deal +20% damage to it for 10s |
| Utility 2 | **Goodberry** | 25s | Create 3 berries. Each heals 50 HP when consumed by any ally |
| Daily | **Frenetic Archery** | 85s | Fire 6 arrows rapidly at different targets. Each 100% damage |

**Special Ability: Favored Enemy**
- Passive: Deal +15% damage to the last monster type you killed

---

### PALADIN (Tank / Off-Healer)
*Based on: Keyleth, Dragonbait, Nayeli Goldflower*

| Stat | Value |
|------|-------|
| HP | 500 |
| Armor | 38% DR |
| Move Speed | 3.5 m/s |
| Attack Speed | 0.9/s |
| Surge Value | 250 |

**Abilities:**
| Slot | Name | Cooldown | Effect |
|------|------|----------|--------|
| At-Will 1 | **Holy Avenger** | 2.5s | Melee strike with radiant damage. 110% + heals self for 20% of damage dealt |
| At-Will 2 | **Swift Strikes** | 2s | Two quick hits, 60% damage each |
| Utility 1 | **Divine Health** | 20s | Cure all conditions on self + heal 100 HP |
| Utility 2 | **Champion Challenge** | 22s | Taunt single target for 6s + reduce its damage by 20% |
| Daily | **Grievous Strike** | 90s | Single target massive hit. 350% damage. If target dies, heal party for 150 HP |

**Special Ability: Lay on Hands**
- Passive: Basic attacks heal the lowest-HP ally within 8m for 5% of damage dealt

---

### BARD (Support / Utility)
*Based on: Birdsong*

| Stat | Value |
|------|-------|
| HP | 400 |
| Armor | 28% DR |
| Move Speed | 4.0 m/s |
| Attack Speed | 1.0/s |
| Surge Value | 200 |

**Abilities:**
| Slot | Name | Cooldown | Effect |
|------|------|----------|--------|
| At-Will 1 | **Flashing Blade** | 2s | Melee attack, 100% damage. If it kills, reset cooldown |
| At-Will 2 | **Bardic Inspiration** | 5s | Grant target ally +15% damage and +10% move speed for 6s |
| Utility 1 | **Song of Rest** | 25s | All allies in range heal 100 HP over 5 seconds |
| Utility 2 | **Dispel Magic** | 20s | Remove all buffs from target enemy OR remove debuffs from ally |
| Daily | **Bardic Lore** | 80s | For 15s: all ally cooldowns reduced by 30%, all ally damage +20% |

**Special Ability: Jack of All Trades**
- Passive: +5% to all secondary stats (crit, CDR, speed, etc.)

---

### DRUID (Healer / Flexible)
*Based on: Qawasha*

| Stat | Value |
|------|-------|
| HP | 400 |
| Armor | 28% DR |
| Move Speed | 3.8 m/s |
| Attack Speed | 0.9/s |
| Surge Value | 200 |

**Abilities:**
| Slot | Name | Cooldown | Effect |
|------|------|----------|--------|
| At-Will 1 | **Shillelagh** | 2s | Melee staff strike enhanced with nature magic. 110% damage |
| At-Will 2 | **Produce Flame** | 2.5s | Ranged fire bolt, 1.5 tile range. 90% damage, small AoE |
| Utility 1 | **Barkskin** | 22s | Target ally gains +20% Armor for 10 seconds |
| Utility 2 | **Longstrider** | 18s | Target ally gains +25% move speed for 12 seconds |
| Daily | **Call Lightning** | 85s | Channel: strike target area every 2s for 10s. Each hit: 120% damage, 3m AoE |

**Special Ability: Wild Shape**
- Passive: When below 25% HP, transform to bear form: +200 HP, +15% Armor, melee only, lasts 10s, 120s internal CD

---

## 3. EQUIPMENT SYSTEM

### Equipment Slots (WC3/Diablo hybrid)
| Slot | Stat Focus |
|------|-----------|
| **Weapon** | Base Damage, Attack Speed, special effects |
| **Armor (Chest)** | Armor rating, HP |
| **Helmet** | HP, Magic Resist, CDR |
| **Boots** | Move Speed, Dodge |
| **Gloves** | Attack Speed, Crit Chance |
| **Accessory (Ring/Amulet)** | Any secondary stat |

### Item Rarities
| Rarity | Color | Stat Bonuses | Drop Rate |
|--------|-------|-------------|-----------|
| Common | White | 0-1 bonus stats | 60% |
| Uncommon | Green | 1-2 bonus stats | 25% |
| Rare | Blue | 2-3 bonus stats | 10% |
| Epic | Purple | 3-4 bonus stats + special effect | 4% |
| Legendary | Orange | Named item, unique passive/active | 1% |

### Example Items (from Board Game Treasures)
| Name | Rarity | Slot | Effect |
|------|--------|------|--------|
| Vorpal Sword | Legendary | Weapon | +30% damage, crits deal 3× instead of 2× |
| Ring of Protection | Rare | Accessory | +8% Armor, +50 HP |
| Boots of Speed | Epic | Boots | +20% move speed, leave fire trail on dash |
| Cloak of Protection | Rare | Armor | +5% Armor, +10% Magic Resist |
| Wand of Fireballs | Epic | Weapon (Wizard) | Fireball cooldown -20s, Fireball radius +2m |
| Thieves' Tools | Uncommon | Accessory (Rogue) | Treasure chests give double gold |
| Potion of Healing | Consumable | — | Restore 200 HP instantly |

### Item Economy (from Temple of Elemental Evil town system)
- **Drop from monsters:** Common/Uncommon frequently, Rare occasionally
- **Treasure chests in rooms:** Guaranteed Uncommon+
- **Town shop between adventures:** Buy with gold, rotating stock of 4-6 items
- **Sell items:** Half of buy price
- **Trade between players:** Free trading within party

---

## 4. ADVANCEMENT TOKENS (Passive Upgrades)

Persistent upgrades bought with gold between adventures (from board game):

| Token | Cost (escalating) | Effect |
|-------|------------------|--------|
| **Reroll** → **Lucky** | 400/500/600/700/800/900 GP | +2% Crit Chance per purchase |
| **+1 Damage** → **Power** | 500/600/700/800/900/1000 GP | +5% damage per purchase |
| **Regain 2 HP** → **Vitality** | 600/700/800/900/1000/1100 GP | +50 HP per purchase |
| **Recharge** → **Haste** | 700/800/900/1000/1100/1200 GP | +5% CDR per purchase |
| **+2 Attack** → **Precision** | 500/600/700/800/900/1000 GP | +3% Attack Speed per purchase |

Max 6 purchases each. Permanent for the campaign.

---

## 5. LEVELING

| Level | Cost | HP Bonus | Armor Bonus | Surge Bonus | Unlock |
|-------|------|----------|-------------|-------------|--------|
| 1→2 | 1000 GP | +100 | +5% | +50 | New Daily power option |
| 2→3 | 2000 GP | +100 | +5% | +50 | New Utility slot |
| 3→4 | 3500 GP | +100 | +5% | +50 | New At-Will option |
| 4→5 | 5000 GP | +150 | +5% | +75 | Second Daily power slot |

> Level cap kept low (5) to match D&D Adventure System's compact design. Power comes more from items and advancement tokens.
