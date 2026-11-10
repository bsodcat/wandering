"""Wolf fever: what a bad wolf bite can leave you with.

Most bites are only bites. Now and then (BITE_CHANCE) one goes bad:

- For half a day nothing shows. Then the fever comes on: you stop healing, and lose a little
  health every hour (about six a day).
- Left alone for a week from the bite, it takes hold: you lose health quickly, every hour,
  until you die of it.
- A bowl of hot soup from an innkeeper treats it. You start to feel better at once: no more
  losing health, and you heal again, but only so far (TREATED_CAP) until you've slept it off.
  That takes two or three days of good sleep: a night's rest (z) of six hours or more, or a
  bed at an inn, on two or three different days. Then the fever breaks and you're well.

`hour` runs each hour of the clock; `slept` is told when you've slept.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from .climate import MINUTES_PER_DAY, MINUTES_PER_HOUR

NAME = "wolf fever"
BITE_CHANCE = 0.03            # a wolf bite that lands
SHOWS_AFTER = 12 * MINUTES_PER_HOUR
TAKES_HOLD = 7 * MINUTES_PER_DAY
EARLY_LOSS = 0.25             # health an hour, the first week
LATE_LOSS = 1.5               # and after
TREATED_CAP = 75.0            # health you can heal to after soup, before the fever breaks
GOOD_SLEEP = 6.0              # hours of sleep that count as a night's rest


@dataclass
class Sickness:
    caught: float                       # the clock when you were bitten
    nights_needed: int = 2              # days of good sleep it takes, once treated
    shown: bool = False                 # the fever has come on
    treated: bool = False               # you've had the soup
    taken_hold: bool = False
    nights: set = field(default_factory=set)   # the days you've slept well since


def bitten(p, minutes: float, rng: random.Random) -> bool:
    """A wolf's bite landed: does it go bad? Returns whether you caught it (you don't know yet)."""
    if p.sickness is not None or rng.random() >= BITE_CHANCE:
        return False
    p.sickness = Sickness(minutes, nights_needed=rng.choice((2, 3)))
    return True


def hour(p, minutes: float, hours: float, health_before: float) -> list[str]:
    """`hours` of the fever, ending at `minutes`. `health_before` is your health before this
    stretch's healing, which the fever takes away. Returns what you notice."""
    s = p.sickness
    if s is None or not p.alive:
        return []
    out = []
    if not s.shown and minutes - s.caught >= SHOWS_AFTER:
        s.shown = True
        if not s.treated:
            out.append("You feel feverish and weak. That wolf bite has gone bad.")
    if s.treated:
        p.health = min(p.health, max(TREATED_CAP, health_before))    # heals, but only so far
        return out
    if not s.shown:
        return out
    p.health = min(p.health, health_before)          # no healing while the fever has you
    if not s.taken_hold and minutes - s.caught >= TAKES_HOLD:
        s.taken_hold = True
        out.append("The fever has taken hold. You're getting worse by the hour: find hot soup at an inn.")
    p.health -= (LATE_LOSS if s.taken_hold else EARLY_LOSS) * hours
    if p.health <= 0:
        p.health, p.alive = 0.0, False
        p.cause = f"died of {NAME}"
        out.append(f"You {p.cause}.")
    return out


def soup(p) -> str:
    """A bowl of hot soup: it treats the fever, if you have it."""
    s = p.sickness
    if s is None:
        return "The hot soup warms you through."
    if s.treated:
        return "The hot soup warms you through. Now you need sleep to shake off the fever."
    s.treated = True
    return (f"The hot soup warms you through, and you start to feel better. It'll take "
            f"{'two' if s.nights_needed == 2 else 'three'} days of good sleep to shake off the fever.")


def slept(p, minutes: float, hours: float) -> list[str]:
    """You've slept `hours`, waking at `minutes`."""
    s = p.sickness
    if s is None or not s.treated or hours < GOOD_SLEEP:
        return []
    s.nights.add(int(minutes // MINUTES_PER_DAY))
    if len(s.nights) >= s.nights_needed:
        p.sickness = None
        return ["The fever has broken. You're well again."]
    left = s.nights_needed - len(s.nights)
    return [f"You feel stronger. {'Another day' if left == 1 else f'{left} more days'} of good sleep should see the fever off."]


def status(p) -> str:
    """For the stats panel: "" if you're well (or don't know yet)."""
    s = p.sickness
    if s is None or not s.shown and not s.treated:
        return ""
    if s.treated:
        return "Recovering"
    return "Gravely ill" if s.taken_hold else "Feverish"
