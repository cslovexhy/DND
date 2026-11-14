"""Boss tuning simulation (pure; no pygame): a party on autopilot fights ONE boss in bossTestRoom.

One fight = `run_fight(party, level, boss_stats, seed, target_time)`. The boss' stats are the three knobs, given in
board-game units and converted to the real numbers the engine uses (pp = 1):

    real HP     = hp  * HP_SCALE          (HP_SCALE = 50)
    real damage = dmg * HP_SCALE / 2      (= 25 per board point, before the target's armor)
    AC          = ac                      (hits are reduced by (ac-10)/(ac-10+12))

The clock starts when the boss first aggroes. A fight is a WIN if the boss dies within `target_time` seconds of that;
otherwise (time up, or the party never engages) it is a LOSS. Heroes that fall respawn at the start (the game has no
game over), so deaths only cost time; they are counted in the result.

`score` makes results comparable and continuous: kill_time / target_time for a win (< 1), and 1 + boss HP fraction left
for a loss (>= 1). Lower is easier for the party.
"""
import contextlib
import io
import random
from dataclasses import dataclass

from game import saves
from game.engine.bootstrap import create_world, join_player
from game.engine.commands import ToggleCompanion
from game.engine.entities import HP_SCALE
from game.engine.ai import AggroState
from game.engine.world_map import SpawnPoint

PARTY_CLASSES = ("Fighter", "Paladin", "Cleric", "Rogue", "Wizard")
MAP = "data/maps/bossTestRoom.json"
DT = 1 / 30
DMG_SCALE = HP_SCALE / 2
APPROACH_LIMIT = 90.0   # a party that has not pulled the boss after this many seconds has lost


@dataclass(frozen=True)
class BossStats:
    """The knobs, in board units. See the module docstring for the conversion to real numbers."""
    ac: float
    dmg: float
    hp: float

    @property
    def real_hp(self):
        return self.hp * HP_SCALE

    @property
    def real_dmg(self):
        return self.dmg * DMG_SCALE

    @classmethod
    def from_real(cls, ac, real_dmg, real_hp):
        return cls(ac, real_dmg / DMG_SCALE, real_hp / HP_SCALE)


@dataclass
class FightResult:
    win: bool
    kill_time: float        # seconds from first aggro to the kill (None for a loss)
    fight_time: float       # seconds from first aggro to the end of the fight (kill or deadline)
    hp_left_frac: float     # fraction of the boss' HP left at the end
    damage_dealt: float     # HP the party took off the boss
    deaths: int             # hero deaths during the fight (each respawns at the start)
    engaged: bool           # did the boss ever aggro

    @property
    def dps(self):
        """Average damage per second the party actually dealt (after the boss' armor)."""
        return self.damage_dealt / self.fight_time if self.fight_time > 0 else 0.0


def score_of(result: FightResult, target_time: float) -> float:
    if result.win:
        return result.kill_time / target_time
    return 1.0 + result.hp_left_frac


def build_fight(classes, level, boss_stats: BossStats, seed, boss_type=16, boss_attrs=None,
                as_companions=False):
    """A ready-to-step world: `classes` (one hero each, all on autopilot, `level`) and one boss with `boss_stats`.
    as_companions: only classes[0] is a joined player; the others are summoned as AI companions of that player."""
    random.seed(seed)

    def char(i, cls):
        c = saves.blank_character(f"{cls.lower()}{i}", cls)
        c["level"] = level
        return c

    world, p0 = create_world(MAP, char(0, classes[0]), autopilot=True)
    if as_companions:
        for cls in classes[1:]:
            world.submit(ToggleCompanion(cls), 0)
        world.step(0)                      # applies the summon commands; the companions copy player 0's level
    else:
        for i, cls in enumerate(classes[1:], start=1):
            join_player(world, i, char(i, cls), MAP, autopilot=True)
    gs = world.game_state
    # exactly one boss in the room: the map's, or `boss_type` spawned where the map's boss stands
    old = [m for m in gs.monsters if m.is_boss]
    spot = old[0].spawn_point if old else SpawnPoint(boss_type, 26, 15)
    for m in list(gs.monsters):
        world.unregister(m)
    gs.monsters.clear()
    boss = world.spawn_single_world_monster(SpawnPoint(boss_type, spot.x, spot.y))
    gs.monsters.append(boss)
    boss.ac = boss_stats.ac
    boss.max_hp = boss_stats.real_hp
    boss.hp = boss.max_hp
    boss.base_damage = boss_stats.real_dmg
    for name, value in (boss_attrs or {}).items():     # experiments: any attribute of the boss
        setattr(boss, name, value)
    return world, boss


def run_fight(classes, level, boss_stats: BossStats, seed=1, target_time=120.0, boss_type=16,
              boss_attrs=None, as_companions=False) -> FightResult:
    with contextlib.redirect_stdout(io.StringIO()):          # the hero AIs print debug lines; keep the output clean
        return _run_fight(classes, level, boss_stats, seed, target_time, boss_type, boss_attrs, as_companions)


def _run_fight(classes, level, boss_stats, seed, target_time, boss_type, boss_attrs, as_companions) -> FightResult:
    world, boss = build_fight(classes, level, boss_stats, seed, boss_type, boss_attrs, as_companions)
    gs = world.game_state
    t_aggro = None
    t = 0.0
    while True:
        world.step(DT)
        t += DT
        if t_aggro is None and (boss.aggro_state == AggroState.AGGROED or not boss.alive):
            t_aggro = t                    # (a boss killed in the frame it was pulled was fought too)
        if not boss.alive:
            break
        if t_aggro is None and t > APPROACH_LIMIT:
            break
        if t_aggro is not None and t - t_aggro >= target_time:
            break
    deaths = sum(getattr(h, "deaths", 0) for h in gs.heroes)
    engaged = t_aggro is not None
    fight_time = (t - t_aggro) if engaged else 0.0
    won = (not boss.alive) and engaged and fight_time <= target_time + 1e-9
    return FightResult(
        win=won, kill_time=fight_time if won else None, fight_time=fight_time,
        hp_left_frac=max(0.0, boss.hp) / boss.max_hp if boss.max_hp else 0.0,
        damage_dealt=boss.max_hp - max(0.0, boss.hp), deaths=deaths, engaged=engaged)
