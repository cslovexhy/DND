"""Find boss stats that fit a party (pure; no pygame). Built on game.boss_sim.

The question: for a party (`group` of classes, all at `level`) and a `target_time`, which boss AC / damage / HP makes
the fight "just right"?  Right means ALL of:

  1. the full group wins every seed, taking between FULL_MIN_SCORE and 1.0 of the target time (not a pushover),
  2. removing ANY one member (each distinct class) loses every seed,
  3. dropping every member one level loses every seed.

Search (cheap: a fight takes ~0.1 s):
  * boss HP is found by bisection (in log space) for each candidate damage, so the full group's score hits
    `aim` (default 0.95 = it kills the boss at 95% of the target time). The score rises monotonically with HP.
  * damage is scanned over a geometric grid, then refined by bisection on the smallest damage that still
    separates the full group from every weaker variant.
  * AC stays at the value given (HP and AC both just scale how long the boss lives).
"""
from dataclasses import dataclass, field

from game.boss_sim import BossStats, FightResult, run_fight, score_of

FULL_MIN_SCORE = 0.85       # the full group must need at least this much of the target time (else too easy)
LOSS_MARGIN = 0.01          # a weaker group must lose with at least this much boss HP left (score >= 1 + margin)
HP_MIN, HP_MAX = 0.5, 20000.0   # board-HP search range


@dataclass
class Eval:
    """One group (classes + level) fought once per seed against one boss."""
    results: list
    scores: list

    @property
    def wins(self):
        return sum(r.win for r in self.results)

    @property
    def all_win(self):
        return all(r.win for r in self.results)

    @property
    def all_lose(self):
        return not any(r.win for r in self.results)

    @property
    def mean_score(self):
        return sum(self.scores) / len(self.scores)

    @property
    def deaths(self):
        return sum(r.deaths for r in self.results) / len(self.results)


@dataclass
class Assessment:
    stats: BossStats
    full: Eval
    variants: dict = field(default_factory=dict)   # name -> Eval (every one of these groups must lose)

    @property
    def weakest_loss(self):
        """Lowest score among the groups that must lose (the closest any of them came to winning); >= 1 means all lose."""
        return min(min(e.scores) for e in self.variants.values())

    @property
    def margin(self):
        """Worst-case separation: how far the full group is from losing, and the closest variant from winning.
        > 0 means every requirement holds (on these seeds)."""
        return min(1.0 - max(self.full.scores), self.weakest_loss - 1.0)

    @property
    def feasible(self):
        return (self.full.all_win and self.full.mean_score >= FULL_MIN_SCORE
                and all(e.all_lose for e in self.variants.values())
                and self.weakest_loss >= 1.0 + LOSS_MARGIN)


class Tuner:
    def __init__(self, group, level, target_time=120.0, ac=16, seeds=(1, 2, 3), boss_type=16,
                 boss_attrs=None, aim=0.95):
        self.group = tuple(group)
        self.level = level
        self.target_time = target_time
        self.ac = ac
        self.seeds = tuple(seeds)
        self.boss_type = boss_type
        self.boss_attrs = dict(boss_attrs or {})
        self.aim = aim
        self.fights = 0                 # simulations actually run (cache misses)
        self._cache = {}

    # --- the groups to test -------------------------------------------------------------------------------
    def variants(self):
        """name -> (classes, level) for every group that must LOSE."""
        out = {}
        for cls in dict.fromkeys(self.group):                  # each distinct class once
            rest = list(self.group)
            rest.remove(cls)
            out[f"without {cls}"] = (tuple(rest), self.level)
        out[f"level {self.level - 1}"] = (self.group, self.level - 1)
        return out

    # --- fights ---------------------------------------------------------------------------------------------
    def fight(self, classes, level, stats, seed) -> FightResult:
        key = (classes, level, stats, seed)
        if key not in self._cache:
            self.fights += 1
            self._cache[key] = run_fight(classes, level, stats, seed=seed, target_time=self.target_time,
                                         boss_type=self.boss_type, boss_attrs=self.boss_attrs)
        return self._cache[key]

    def evaluate(self, classes, level, stats, seeds=None) -> Eval:
        results = [self.fight(classes, level, stats, s) for s in (seeds or self.seeds)]
        return Eval(results, [score_of(r, self.target_time) for r in results])

    def assess(self, stats, seeds=None) -> Assessment:
        a = Assessment(stats, self.evaluate(self.group, self.level, stats, seeds))
        for name, (classes, level) in self.variants().items():
            a.variants[name] = self.evaluate(classes, level, stats, seeds)
        return a

    # --- search ---------------------------------------------------------------------------------------------
    def full_score(self, hp, dmg):
        return self.evaluate(self.group, self.level, BossStats(self.ac, dmg, hp)).mean_score

    def tune_hp(self, dmg, hint=None, tol=0.01, max_iter=14):
        """Board HP at which the full group's mean score is `aim`. The score rises with HP, so this is a bracketed
        root find: regula falsi (the score is nearly linear in HP locally) with a bisection step whenever it stalls.
        `hint` (the answer for a neighbouring damage) gives a tight starting bracket. Returns HP_MAX / HP_MIN if
        even that is too easy / too hard."""
        f = lambda hp: self.full_score(hp, dmg) - self.aim            # noqa: E731  (increasing in hp)
        lo, hi = (hint / 1.25, hint * 1.25) if hint else (HP_MIN, 4.0)
        f_lo, f_hi = f(lo), f(hi)
        while f_lo > 0 and lo > HP_MIN:                               # lo is already too hard: walk down
            lo, hi, f_hi = max(HP_MIN, lo / 1.5), lo, f_lo
            f_lo = f(lo)
        if f_lo > 0:
            return lo
        while f_hi < 0 and hi < HP_MAX:                               # hi is still too easy: walk up
            lo, f_lo, hi = hi, f_hi, min(HP_MAX, hi * 1.5)
            f_hi = f(hi)
        if f_hi < 0:
            return hi
        best = (abs(f_lo), lo) if abs(f_lo) < abs(f_hi) else (abs(f_hi), hi)
        stalls = 0
        for _ in range(max_iter):
            x = lo - f_lo * (hi - lo) / (f_hi - f_lo) if f_hi != f_lo else (lo + hi) / 2
            if stalls >= 2 or not lo < x < hi:
                x, stalls = (lo + hi) / 2, 0
            x = round(x, 2)
            if x in (lo, hi):
                break
            fx = f(x)
            best = min(best, (abs(fx), x))
            if abs(fx) <= tol:
                return x
            stalls = stalls + 1 if (hi - lo) > 0.5 * (hi - lo) and abs(fx) > 0.5 * min(abs(f_lo), abs(f_hi)) else 0
            if fx < 0:
                lo, f_lo = x, fx
            else:
                hi, f_hi = x, fx
        return best[1]

    def assess_dmg(self, dmg, hint=None):
        """Tune HP for this damage, then assess every requirement."""
        return self.assess(BossStats(self.ac, dmg, self.tune_hp(dmg, hint)))

    def search(self, dmg_grid=None, refine=6, log=print):
        """Scan damage values (board units), then bisect the lower edge of the feasible region.
        Returns dict: rows (every assessment, by damage), lowest (smallest feasible damage) and robust (largest
        margin among the feasible ones); lowest/robust are None when nothing is feasible."""
        grid = dmg_grid or [0.5, 1, 2, 3, 5, 8, 12, 20]                          # board damage
        rows = []

        def line(a):
            log(f"  dmg {a.stats.dmg:>6}: hp {a.stats.hp:>8}  full {a.full.mean_score:.2f}  "
                f"closest variant {a.weakest_loss:.2f}  margin {a.margin:+.2f}  full-group deaths {a.full.deaths:4.1f}  "
                f"{'OK' if a.feasible else '--'}  ({self.fights} fights)")

        hint = None
        for d in grid:
            a = self.assess_dmg(d, hint)
            hint = a.stats.hp                      # HP barely moves between neighbouring damages: start there
            rows.append(a)
            line(a)
        feasible = [a for a in rows if a.feasible]
        if not feasible:
            return {"rows": rows, "lowest": None, "robust": None}
        lowest = min(feasible, key=lambda a: a.stats.dmg)
        below = [a.stats.dmg for a in rows if a.stats.dmg < lowest.stats.dmg]
        if below:                                    # the true edge lies between the last infeasible point and `lowest`
            lo, hi = max(below), lowest.stats.dmg
            for _ in range(refine):
                mid = round((lo + hi) / 2, 2)
                if mid in (lo, hi):
                    break
                a = self.assess_dmg(mid, lowest.stats.hp)
                rows.append(a)
                line(a)
                if a.feasible:
                    hi, lowest = mid, a
                else:
                    lo = mid
        feasible = [a for a in rows if a.feasible]
        rows.sort(key=lambda a: a.stats.dmg)
        return {"rows": rows, "lowest": lowest, "robust": max(feasible, key=lambda a: a.margin)}
