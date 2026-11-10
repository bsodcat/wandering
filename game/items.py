"""Things you can carry, and the bag you carry them in.

Items are kinds (an axe, a log, a coin) and how many. They lie on a level's tiles
(`Level.items`), sometimes under the ground (`Level.buried`, found by digging), and you carry
them in your `Inventory`. Some are tools that let you do things:

- an axe:    walk into a tree to fell it, and cut logs (one leans by every lumberjack's house)
- a shovel:  dig (x) the ground you're standing on for what's buried there (there's one in a
             house in every town and village)

Coins pay for things, and logs sell to a lumberjack. A room key lets you sleep upstairs at an
inn for the night.
"""
from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass(frozen=True)
class Kind:
    name: str
    plural: str
    char: str
    colour: tuple
    note: str = ""


KINDS = {
    "coin": Kind("coin", "coins", "$", (240, 210, 90)),
    "axe": Kind("axe", "axes", "ƒ", (200, 200, 210), "walk into a tree to fell it"),
    "shovel": Kind("shovel", "shovels", "τ", (185, 160, 120), "x digs where you stand"),
    "log": Kind("log", "logs", "%", (175, 125, 75), "a lumberjack buys these"),
    "room key": Kind("room key", "room keys", "♀", (235, 200, 110), "sleep (z) in a bed upstairs"),
    "silver ring": Kind("silver ring", "silver rings", "○", (215, 220, 235)),
    "arrowhead": Kind("arrowhead", "arrowheads", "↑", (170, 165, 155)),
    "pottery shard": Kind("pottery shard", "pottery shards", "'", (200, 120, 80)),
    "old bone": Kind("old bone", "old bones", "∞", (225, 220, 195)),
    "rusty dagger": Kind("rusty dagger", "rusty daggers", "⌡", (165, 110, 80)),
}
# What turns up under the ground: (kind, chance, how many)
TREASURE = [("coin", 0.45, (1, 8)), ("pottery shard", 0.2, (1, 1)), ("arrowhead", 0.15, (1, 1)),
            ("old bone", 0.1, (1, 1)), ("rusty dagger", 0.06, (1, 1)), ("silver ring", 0.04, (1, 1))]


def amount(kind: str, n: int) -> str:
    """"an axe", "3 logs"."""
    k = KINDS[kind]
    if n == 1:
        return ("an " if k.name[0] in "aeiou" else "a ") + k.name
    return f"{n} {k.plural}"


def treasure(rng: random.Random) -> tuple[str, int]:
    r = rng.random()
    for kind, chance, (lo, hi) in TREASURE:
        if r < chance:
            return kind, rng.randint(lo, hi)
        r -= chance
    return "coin", 1


class Inventory(dict):
    """What you carry: kind -> how many, in the order you got them."""

    def count(self, kind: str) -> int:
        return self.get(kind, 0)

    def add(self, kind: str, n: int = 1) -> None:
        self[kind] = self.get(kind, 0) + n

    def take(self, kind: str, n: int = 1) -> bool:
        """Takes n away; False (and nothing taken) if there aren't that many."""
        if self.get(kind, 0) < n:
            return False
        self[kind] -= n
        if not self[kind]:
            del self[kind]
        return True


def drop(level, x: int, y: int, kind: str) -> None:
    level.items.setdefault((x, y), []).append(kind)


def pick_up(level, x: int, y: int, inventory: Inventory) -> list[str]:
    """Everything lying at (x, y) into the bag. Returns what was picked up."""
    got = level.items.pop((x, y), [])
    for kind in got:
        inventory.add(kind)
    return got


def describe_pile(kinds: list[str]) -> str:
    counts: dict[str, int] = {}
    for k in kinds:
        counts[k] = counts.get(k, 0) + 1
    parts = [amount(k, n) for k, n in counts.items()]
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]
