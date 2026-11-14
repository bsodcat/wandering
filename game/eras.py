"""Eras: the world's history, and skipping ahead through it.

A world is its seed plus a history: a list of eras, each (how many years, what changed). The
land is made from the seed, then every era's change is laid on it (the climate warms or cools,
gets wetter or drier, the sea rises or falls, the ground lifts), and the whole history's years
of rain and frost wear it down (game/erosion.py). The same seed and history always make the
same world.

How much an era does grows with its length, quickly at first and then slowly: a century barely
shows, ten thousand years is plain to see, and a million remakes the land (`weight`).

You pick the world's age when you create it (its starting year), and in a game the time skip
(the T key) adds an era: the land is remade as it would be after that
long, and settlements that didn't last are left as ruins.
"""
from __future__ import annotations

from dataclasses import dataclass

# Starting years for a new world, and how far a time skip can go.
YEAR_STEP = 50                # Create a World: the start year goes up this much a step
YEAR_JUMP = 1000              # ... or this much with Shift held
START_YEARS = [1] + list(range(YEAR_STEP, 1_000_001, YEAR_STEP))
SKIP_YEARS = [100, 1000, 10_000, 100_000, 1_000_000]
FULL = 1_000_000              # years for an era's change to have its full effect
SHAPE = 0.35                  # how fast it builds: weight = (years / FULL) ** SHAPE
BASE_PASSES = 20              # erosion passes for a new world (game/erosion.py)
MORE_PASSES = 60              # and the most a history adds

# Each change at its full weight: rain, degrees C, metres of sea level, how much the land rises,
# and how much harder frost works on the rock.
@dataclass(frozen=True)
class Change:
    name: str
    blurb: str                 # what it does, for the menus
    told: str                  # what you find when you wake into it
    wet: float = 0.0
    warm: float = 0.0
    sea: float = 0.0
    lift: float = 0.0
    frost: float = 0.0


CHANGES = [
    Change("Steady", "the climate holds; rain and frost wear the land",
           "The land is much as the weather left it, only worn: valleys deeper, hills softer."),
    Change("Wetter", "more rain: rivers swell, lakes and forests spread",
           "The rains came more often. Rivers run fuller, and the forests and marshes have spread.",
           wet=0.25),
    Change("Drier", "less rain: deserts and steppe spread, rivers shrink",
           "The rains failed. Deserts and dry grassland have spread, and many rivers are gone.",
           wet=-0.25),
    Change("Ice age", "colder: ice and tundra spread, the sea falls",
           "The cold came down. Ice and tundra reach far south, and the sea has drawn back.",
           warm=-9.0, sea=-160.0, frost=1.0, wet=-0.05),
    Change("Warming", "warmer: the ice melts, jungles spread, the sea rises",
           "The world grew warm. The ice has melted back, jungles have spread, and the sea has risen.",
           warm=6.0, sea=70.0, wet=0.05),
    Change("Uplift", "the ground rises: mountains grow, rivers cut deep",
           "The ground has risen. The mountains stand higher, and the rivers have cut deep into them.",
           lift=0.4),
]
BY_NAME = {c.name: c for c in CHANGES}


def weight(years: float) -> float:
    return min(1.0, max(0.0, years / FULL) ** SHAPE) if years > 0 else 0.0


@dataclass(frozen=True)
class Effects:
    """The whole history laid together."""
    wet: float = 0.0
    warm: float = 0.0
    sea: float = 0.0
    lift: float = 0.0
    frost: float = 0.0
    passes: int = BASE_PASSES


def effects(history: tuple) -> Effects:
    wet = warm = sea = lift = frost = 0.0
    for years, name in history:
        c, k = BY_NAME[name], weight(years)
        wet += c.wet * k
        warm += c.warm * k
        sea += c.sea * k
        lift += c.lift * k
        frost += c.frost * k
    total = sum(years for years, _ in history)
    return Effects(max(-0.4, min(0.4, wet)), max(-14.0, min(10.0, warm)), max(-250.0, min(120.0, sea)),
                   min(1.0, lift), min(1.0, frost), BASE_PASSES + round(MORE_PASSES * weight(total)))


def years(history: tuple) -> int:
    return sum(y for y, _ in history)


def years_text(n: int) -> str:
    return f"{n:,} year{'s' if n != 1 else ''}"


def history_text(history: tuple) -> str:
    """The world's past in a few words: '10,000 years Wetter, then 100 years Steady'."""
    if not history:
        return "a new world"
    return ", then ".join(f"{years_text(y)} {name}" for y, name in history)


def start_history(start_year: int, change: str) -> tuple:
    """The history behind a world that starts in `start_year`."""
    return ((start_year - 1, change),) if start_year > 1 else ()


# ----------------------------------------------------------------- after a skip

LASTS = 1500   # years: a settlement has an even chance of lasting this long
KEPT = ("city", "town", "village", "inn", "fort", "tower", "ruins", "cave")


def survivors(old, years: int) -> list:
    """The places from before a skip that come through it (worldgen.generate keeps them where
    the land still allows): a settlement or tower lasts with a chance that halves every LASTS
    years, and one that doesn't is left as ruins where it stood. Ruins and caves keep."""
    import random
    from .worldgen import Site
    rng = random.Random((old.seed * 1_000_003 + years * 7919 + len(old.history)) & 0xFFFFFFFFFFFF)
    lasts = 0.5 ** (years / LASTS)
    out = []
    for s in old.sites:
        if s.kind not in KEPT:
            continue
        if s.kind in ("ruins", "cave") or rng.random() < lasts:
            out.append(Site(s.kind, s.name, s.x, s.y, s.port))
        else:
            out.append(Site("ruins", s.name if s.name.startswith("Ruins of ") else f"Ruins of {s.name}", s.x, s.y))
    return out


def carry_over(old, new) -> list[str]:
    """What to tell the player about the settlements from before a skip: which still stand,
    which are ruins, and which are gone (under the sea or the ice)."""
    now = {s.name: s for s in new.sites}
    lived, fell, gone = [], [], []
    for s in old.sites:
        if not s.settled:
            continue
        if s.name in now and now[s.name].kind == s.kind:
            lived.append(s.name)
        elif f"Ruins of {s.name}" in now:
            fell.append(s.name)
        else:
            gone.append(s.name)

    def listed(names):
        return f"{', '.join(names[:6])}{' and more' if len(names) > 6 else ''}"
    lines = []
    if lived:
        lines.append(f"Still standing: {listed(lived)}.")
    if fell:
        lines.append(f"In ruins: {listed(fell)}.")
    if gone:
        lines.append(f"Lost without a trace: {listed(gone)}.")
    return lines
