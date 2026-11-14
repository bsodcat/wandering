"""Guards and archers defending a fort or a city from wolves, goblins and bats.

While they're on duty, guards strike at anything hostile that comes within a couple of steps
of them, and archers shoot at anything they can see within ARCHER_RANGE tiles. Each gets a
blow or a shot about every half minute, so a pack that wanders up to a fort's gate doesn't last
long. A kill leaves its carcass like any other.
"""
from __future__ import annotations

import random

from . import wild
from .climate import hour_of_day
from .people import JOBS

GUARD_REACH = 2
ARCHER_RANGE = 9
SHOT_MINUTES = 0.5          # a blow or an arrow this often
MOST_SHOTS = 8              # at most this many each in one go
HIT = {"guard": 0.7, "archer": 0.6}
DAMAGE = {"guard": (3, 8), "archer": (3, 7)}


def on_duty(a, minutes: float) -> bool:
    job = JOBS[a.kind]
    hour = float(hour_of_day(minutes))
    return job.start <= hour < job.end


def defend(level, engine, rng: random.Random, elapsed: float) -> None:
    """`elapsed` minutes of the defenders on this level at work."""
    hostile = [c for c in level.creatures if c.kind in wild.HOSTILE and c.hp > 0]
    if not hostile:
        return
    defenders = [a for a in level.actors if a.kind in ("guard", "archer") and on_duty(a, engine.minutes)]
    if not defenders:
        return
    shots = max(1, min(MOST_SHOTS, round(elapsed / SHOT_MINUTES)))
    wilds = None
    seen = engine.local_visible if engine.local_visible.shape == level.tiles.shape else None
    for a in defenders:
        reach = GUARD_REACH if a.kind == "guard" else ARCHER_RANGE
        for _ in range(shots):
            targets = [c for c in hostile if c.hp > 0 and wild.dist(c, (a.x, a.y)) <= reach
                       and (a.kind == "guard" or wild.clear_line(level, (a.x, a.y), (c.x, c.y)))]
            if not targets:
                break
            c = min(targets, key=lambda t: wild.dist(t, (a.x, a.y)))
            visible = seen is not None and (bool(seen[c.x, c.y]) or bool(seen[a.x, a.y]))
            if rng.random() >= HIT[a.kind] - c.beast.dodge + 0.15:
                continue
            c.hp -= rng.randint(*DAMAGE[a.kind])
            c.provoked = engine.minutes
            if c.hp > 0:
                if visible and rng.random() < 0.35:
                    engine.say(f"An arrow from the archer strikes the {c.name}." if a.kind == "archer"
                               else f"The guard drives off the {c.name} with a spear.")
                continue
            if wilds is None:
                wilds = wild.Wilds(level, engine, rng, engine.minutes)
            wilds.kill(c)
            if visible:
                engine.say(f"The {a.kind} {'shoots' if a.kind == 'archer' else 'cuts down'} the {c.name}.")
