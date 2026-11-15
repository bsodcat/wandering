"""Locks: locked doors and chests, lockpicks, and picking a lock.

What's locked is worked out from where it is, the same every game, the first time anyone asks
(`difficulty`), so nothing has to be set up when a map is made:

- doors: about a third of the houses in a settlement keep theirs locked. Their people have
  keys, so they come and go as they like; you need a lockpick. From inside you can always
  unbar a door and walk out.
- chests: some of those at home and in shops, more and harder ones in crypts, and most in
  caves, harder the deeper they lie.

A lock is simple (3 pins), sturdy (4) or intricate (5). Picking it is a small game (LockPick):
the pins catch in an order of their own, one at a time. Push the pin that's binding and it
sets with a click; push one that isn't and it's springy, and your pick may snap; push a pin
that's already set and you've pushed too far: they all drop and you start again. A broken pick
is gone. Once a lock's picked it stays open (Level.unlocked).

Lockpicks are sold by the armourer and the blacksmith.
"""
from __future__ import annotations

import random
import zlib

from tcod.event import KeySym

from . import tiles as T
from .shop import Modal

PICK = "lockpick"
NAMES = {1: "simple", 2: "sturdy", 3: "intricate"}
PINS = {1: 3, 2: 4, 3: 5}
SNAP = {1: 0.05, 2: 0.09, 3: 0.14}     # the chance a pushed pin that isn't binding snaps your pick
PUSH_MINUTES = 1                       # each push of a pin
LOCKED_DOOR = 0.3                      # of the houses in a settlement
LOCKED_CHEST = {"house": 0.35, "shop": 0.5, "crypt": 0.5, "cave": 0.65, "other": 0.3}
SHOPS = ("bakery", "butcher", "armoury", "smithy", "alchemist", "guildhall")


def roll(level, x: int, y: int, what: str) -> float:
    """A steady 0..1 for this spot (the same every game)."""
    return zlib.crc32(f"{what}{level.key}{x},{y}".encode()) / 0xFFFFFFFF


def difficulty(level, x: int, y: int) -> int:
    """0 if the door or chest at (x, y) isn't locked (or has been picked), else 1..3."""
    if (x, y) in level.unlocked or not level.in_bounds(x, y):
        return 0
    tile = int(level.tiles[x, y])
    hard = roll(level, x, y, "how hard")
    if tile == T.DOOR:
        b = level.building_at(x, y)
        if b is None or b.kind != "house" or not level.surface or roll(level, x, y, "door") >= LOCKED_DOOR:
            return 0
        return 1 + (hard < 0.35)
    if tile != T.CHEST:
        return 0
    kind = level.key[0]
    depth = level.key[3] if len(level.key) > 3 else 0
    if kind not in ("cave", "crypt"):
        b = level.building_at(x, y)
        kind = "house" if b is not None and b.kind == "house" else "shop" if b is not None and b.kind in SHOPS \
            else "other"
    if roll(level, x, y, "chest") >= LOCKED_CHEST[kind]:
        return 0
    if kind == "cave":
        return min(3, 1 + (depth >= 2) + (hard < 0.4 + 0.15 * depth))
    if kind == "crypt":
        return 2 + (hard < 0.4)
    return 1 + (hard < (0.45 if kind == "shop" else 0.25))


def locked(level, x: int, y: int) -> bool:
    return difficulty(level, x, y) > 0


def what(level, x: int, y: int) -> str:
    return "door" if int(level.tiles[x, y]) == T.DOOR else "chest"


def describe(level, x: int, y: int) -> str | None:
    """'Locked (a sturdy lock)', for the Look panel."""
    d = difficulty(level, x, y)
    return f"Locked (a {NAMES[d]} lock)" if d else None


def unlock(level, x: int, y: int) -> None:
    level.unlocked.add((x, y))


def locked_doors(level) -> list[tuple[int, int]]:
    """Every locked door on the level, worked out once (and again after a lock's picked)."""
    cache = getattr(level, "_locked_doors", None)
    if cache is None or cache[0] != len(level.unlocked):
        doors = [(int(x), int(y)) for x, y in zip(*(level.tiles == T.DOOR).nonzero())]
        cache = (len(level.unlocked), [d for d in doors if locked(level, *d)])
        level._locked_doors = cache
    return cache[1]


class LockPick(Modal):
    """Picking a lock: one row a pin. Up/Down picks the pin, Enter (or a click) pushes it."""
    hint = "Up/Down choose a pin, Enter pushes it, Esc stops"
    leave_text = "You leave the lock be."

    def __init__(self, engine, x: int, y: int, then=None):
        super().__init__()
        level = engine.level
        self.x, self.y, self.then = x, y, then
        self.level = d = difficulty(level, x, y)
        self.thing = what(level, x, y)
        self.title = f"Picking the lock of the {self.thing}"
        self.greeting = (f"A {NAMES[d]} lock. Push the binding pin and it sets; the rest feel springy and "
                         "may snap your pick. Push a set pin and they all drop.")
        self.rng = random.Random(f"{level.key}{x},{y}{engine.minutes}")
        n = PINS[d]
        self.order = self.rng.sample(range(n), n)    # which pin binds first, then next...
        self.done: list[int] = []                    # the pins set so far
        self.springy: set = set()                    # pins found springy since the last one set

    def labels(self) -> list[str]:
        out = []
        for i in range(len(self.order)):
            if i in self.done:
                look = "▲  set"
            elif i in self.springy:
                look = "≈  springy"
            else:
                look = "·"
            out.append(f"Pin {i + 1}   {look}")
        return out

    def footer(self, engine) -> str:
        return f"Lockpicks {engine.player.inventory.count(PICK)}   Pins set {len(self.done)}/{len(self.order)}"

    def act(self, engine) -> bool:
        bag = engine.player.inventory
        if not bag.count(PICK):
            self.note("You've no lockpick left.", engine)
            return False
        engine.pass_time(PUSH_MINUTES / 60)
        pin = self.cursor
        if pin in self.done:
            self.done.clear()
            self.springy.clear()
            self.note("You push too far, and the pins drop. Start again.", engine)
            return True
        if pin == self.order[len(self.done)]:
            self.done.append(pin)
            self.springy.clear()
            if len(self.done) < len(self.order):
                self.note("Click. The pin sets.", engine)
                return True
            unlock(engine.level, self.x, self.y)
            engine.shop = None
            engine.say(f"Click. The last pin sets, and the {self.thing}'s lock turns.")
            if self.then is not None:
                self.then(engine)
            return False
        self.springy.add(pin)
        if self.rng.random() < SNAP[self.level]:
            bag.take(PICK)
            self.done.clear()
            self.springy.clear()
            left = bag.count(PICK)
            self.note("Snap! Your lockpick breaks, and the pins drop." +
                      (f" ({left} left)" if left else " It was your last."), engine)
            return left > 0
        self.note("That pin's springy: it isn't binding yet.", engine)
        return True

    def handle_key(self, sym, engine) -> bool:
        if sym in (KeySym.LEFT, KeySym.RIGHT):
            return True
        return super().handle_key(sym, engine)


def pick(engine, x: int, y: int, then=None) -> str | None:
    """Starts picking the lock at (x, y), if you've a lockpick. `then(engine)` runs once it's open."""
    if not locked(engine.level, x, y):
        return None
    if not engine.player.inventory.count(PICK):
        return f"The {what(engine.level, x, y)} is locked, and you've no lockpick."
    engine.shop = LockPick(engine, x, y, then)
    engine.autopath = False
    return None
