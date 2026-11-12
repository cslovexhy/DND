# 07 — Skills for every entity: factions, one damage pipeline, one cast path

Goal: any skill can be used by any entity (hero or monster) and affects entities by **relation** (hostile /
friendly / self) and **shape** (single target / AoE / sweep / dash / channel), never by "is this a hero or a
monster". Heroes and monsters differ only in their *brain* (player input / hero AI / monster AI) and in data
(stats, kit, faction).

## Before (the gaps)

| Concern | Heroes | Monsters |
|---|---|---|
| Who are my enemies? | skill code hard-codes `gs.alive_monsters` | hero list |
| Casting | ~400 lines of per-skill branches in `PlayerState.cast_ability` (targeting + validation + effect + player UI mixed) | `monster_casting.RULES`, 4 skills |
| Damage modifiers | food buff applied on the *target* side (`Monster.take_damage`) | Demoralized only in monster basic attacks |
| Being hit | each skill branch calls `aggro_monster` / `call_for_help` (inconsistently) | — |
| Dash, channel | `PlayerState.dash_*`, `frostbolt_*`, Holy Light as a buff completed in `World.begin_frame` | none |
| Conditions | hero path walking ignores stun / freeze / slow; casting checks none | AI respects them |

## After

**Factions** (`Entity.faction`: `"heroes"` / `"monsters"`). `combat.enemies_of(world, e)` / `friends_of(world, e)`
answer "who". Stealthed enemies are not valid targets.

**One damage pipeline** — `combat.hit(world, source, target, amount, threat=, ignore_armor=, flash=)`:
the source's outgoing multiplier (`Entity.damage_mult`: food buff x Demoralized x ...) applies to every hit from
any source (basic attacks, skills, projectiles, damage over time). The target records hate if it keeps a hate
table. If the target has an aggro brain (monsters) and the source is hostile, it **engages**: aggro + call for help.
One rule for every skill.

**One cast path** — `casting.SKILLS[name] = SkillSpec(targeting, effect, gates..., ai)`;
`casting.try_cast(world, caster, ab, target) -> CastResult` (ok / out of range / no line of sight / no target /
gated "reason") validates and runs the effect for any caster. `PlayerState.cast_ability` only adds player concerns
(walk into range and fire, keep auto-attacking, right-click binding) around it.

Targeting kinds: `enemy` (one hostile in range + LOS), `ally` (a friend within SUPPORT_RANGE, self included),
`self`, `nova` (hostiles within `radius` of the caster), `sweep` (Cleave: target + nearest hostiles), `dash`
(Charge: walk-path dash to a hostile, hit + stun on arrival).

**Actions live on the entity** (`actions.py`): `entity.dash` (Charge) and `entity.channel` (Frostbolt, Holy Light)
are advanced for every entity; a channel shows as a cast bar for anyone (snapshot `channel`).

**Conditions for everyone**: `Entity.can_act` (not stunned / frozen), `can_move` (+ not immobilized),
`move_speed` (slow, stealth). Hero walking, casting and auto-attack obey them like monster AI does.

**Brains**: a skill's `ai(world, caster, ab)` hint says when it is worth casting and on whom. Monster casting
(`casting.monster_turn`) is generic over the kit; hero AIs keep their class tactics for now and could adopt the
hints later.

## Status (implemented)

- `engine/combat.py` (factions, `enemies_of` / `friends_of`, `in_combat`, `hit`, `engage`), `engine/actions.py`
  (dash, channel, `walk_path`, `step_toward`), `engine/casting.py` (`SkillSpec`, `SKILLS`, `try_cast`,
  `monster_turn`), `engine/abilities.py` (one effect per skill, caster-independent). `PlayerState.cast_ability`
  is a thin player wrapper; `engine/monster_casting.py` is gone.
- Rules unified on purpose (goldens regenerated): weapon attacks (Strike, Stab, Smite, Wanding, Frostbolt) are paced
  by the swing and don't start the global cooldown; every damaging hit engages; a channel blocks only another
  channel / dash (instant skills can be cast while channelling); conditions and slows hold for heroes too.
- Monster-castable (have an AI hint): Frostbolt, Fire Blast, Judgement, Cleave, Charge, Frost Nova, Demoralizing
  Shout, Heroic Strike, Righteous Seal, Poison Dagger, Renew, Wall, Holy Light. Not (no hint): weapon attacks
  (monsters have their own), Stealth, Ambush. A monster's basic attack spends an armed Heroic Strike / Poison
  Dagger and uses an active Righteous Seal.
- Found while comparing old vs new: the old Strike path started the global cooldown even when the swing was not
  ready, which (by accident) made the Fighter AI close in between swings. The Fighter AI now does that explicitly,
  only when its target is after someone else (Fighter-led parties: +8% kills, fewer deaths; Wizard-led: -6% kills,
  0 vs 6 deaths over 12 seeds).

## Out of scope (next)
Boss HP-triggered skills (Deep Breath, Enrage) and the Demogorgon's stealth / aura still use their own systems;
they can become kit skills with HP-threshold AI hints.
