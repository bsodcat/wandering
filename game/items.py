"""Things you can carry, and the bag you carry them in.

Items are kinds (an axe, a log, a coin) and how many. They lie on a level's tiles
(`Level.items`), sometimes under the ground (`Level.buried`, found by digging), sit in barrels
(`Level.stores`), and you carry them in your `Inventory`. Some are tools that let you do things:

- an axe:    walk into a tree to fell it, and cut logs (one leans by every lumberjack's house)
- a shovel:  dig (x) the ground you're standing on for what's buried there (there's one in a
             house in every town and village)

Weapons and armour (game/combat.py) are sold by a town's shopkeeper; wield or wear them from
the use menu (e). Food can be eaten the same way. Coins pay for things, logs sell to a
lumberjack, and trinkets and rings to a shopkeeper. A room key lets you sleep upstairs at an
inn for the night. A creature killed leaves its carcass (goblins carry them off and cook them).

What turns up when you dig: mostly coins and odds and ends of the past, fairly often a trinket,
and only under a town's streets and gardens, now and then a silver or gold ring.
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
    value: int = 0            # what a shopkeeper pays for one
    meal: tuple = ()          # (health, stamina) eating one gives back


WEAPON, ARMOUR, RING = (200, 200, 215), (170, 175, 190), (215, 220, 235)

KINDS = {
    "coin": Kind("coin", "coins", "$", (240, 210, 90)),
    "axe": Kind("axe", "axes", "ƒ", (200, 200, 210), "walk into a tree to fell it; a fair weapon"),
    "shovel": Kind("shovel", "shovels", "τ", (185, 160, 120), "x digs where you stand"),
    "log": Kind("log", "logs", "%", (175, 125, 75), "a lumberjack buys these"),
    "room key": Kind("room key", "room keys", "♀", (235, 200, 110), "sleep (z) in a bed upstairs"),
    "arrowhead": Kind("arrowhead", "arrowheads", "↑", (170, 165, 155)),
    "pottery shard": Kind("pottery shard", "pottery shards", "'", (200, 120, 80)),
    "old bone": Kind("old bone", "old bones", "∞", (225, 220, 195)),
    "rusty dagger": Kind("rusty dagger", "rusty daggers", "⌡", (165, 110, 80), "a poor weapon", value=1),
    # weapons and armour: game/combat.py says what each does
    "dagger": Kind("dagger", "daggers", ")", WEAPON, "a weapon, quick to strike", value=3),
    "club": Kind("club", "clubs", ")", (165, 125, 85), "a weapon", value=1),
    "spear": Kind("spear", "spears", ")", (190, 175, 140), "a weapon with reach", value=4),
    "short sword": Kind("short sword", "short swords", ")", (220, 220, 235), "a good weapon", value=8),
    "crude knife": Kind("crude knife", "crude knives", ")", (150, 140, 110), "a goblin's weapon", value=1),
    "padded jerkin": Kind("padded jerkin", "padded jerkins", "[", (185, 165, 130), "armour: body", value=3),
    "leather coat": Kind("leather coat", "leather coats", "[", (170, 120, 75), "armour: body", value=6),
    "mail shirt": Kind("mail shirt", "mail shirts", "[", ARMOUR, "armour: body", value=15),
    "iron helm": Kind("iron helm", "iron helms", "[", (160, 160, 170), "armour: head", value=5),
    "wooden shield": Kind("wooden shield", "wooden shields", "[", (175, 130, 80), "armour: blocks blows", value=3),
    # food (eat it from the use menu)
    "roast meat": Kind("roast meat", "pieces of roast meat", "%", (200, 110, 70), "food", meal=(6, 20)),
    "apple": Kind("apple", "apples", "%", (220, 70, 60), "food", meal=(2, 8)),
    "loaf of bread": Kind("loaf of bread", "loaves of bread", "%", (225, 190, 120), "food", meal=(3, 15)),
    "salt fish": Kind("salt fish", "salt fish", "%", (190, 200, 210), "food", meal=(3, 12)),
    # what a creature leaves when it's killed
    "wolf carcass": Kind("wolf carcass", "wolf carcasses", "%", (150, 150, 160), "goblins would cook it"),
    "rabbit carcass": Kind("rabbit carcass", "rabbit carcasses", "%", (190, 160, 125)),
    "squirrel carcass": Kind("squirrel carcass", "squirrel carcasses", "%", (180, 110, 70)),
    "bird carcass": Kind("bird carcass", "bird carcasses", "%", (150, 165, 200)),
    "rat carcass": Kind("rat carcass", "rat carcasses", "%", (140, 125, 115)),
    "bat carcass": Kind("bat carcass", "bat carcasses", "%", (140, 115, 135)),
    # trinkets: dug up now and then, carried by goblins; a shopkeeper buys them
    "brass button": Kind("brass button", "brass buttons", "*", (225, 190, 90), "a trinket", value=1),
    "clay bead": Kind("clay bead", "clay beads", "*", (190, 110, 80), "a trinket", value=1),
    "tin whistle": Kind("tin whistle", "tin whistles", "*", (190, 195, 200), "a trinket", value=2),
    "bone die": Kind("bone die", "bone dice", "*", (230, 225, 205), "a trinket", value=2),
    "copper bangle": Kind("copper bangle", "copper bangles", "*", (210, 130, 80), "a trinket", value=3),
    "carved figurine": Kind("carved figurine", "carved figurines", "*", (175, 140, 100), "a trinket", value=3),
    "glass marble": Kind("glass marble", "glass marbles", "*", (130, 200, 220), "a trinket", value=2),
    "old buckle": Kind("old buckle", "old buckles", "*", (160, 150, 130), "a trinket", value=1),
    "bone charm": Kind("bone charm", "bone charms", "*", (225, 215, 170), "a goblin trinket", value=2),
    # precious: only ever found under towns
    "silver ring": Kind("silver ring", "silver rings", "○", RING, "worth a good deal", value=15),
    "gold ring": Kind("gold ring", "gold rings", "○", (245, 200, 70), "worth a great deal", value=35),
}
TRINKETS = ["brass button", "clay bead", "tin whistle", "bone die", "copper bangle", "carved figurine",
            "glass marble", "old buckle"]
FOODS = [k for k, v in KINDS.items() if v.meal]
CARCASSES = [k for k in KINDS if k.endswith(" carcass")]
# What turns up under the ground: (kind, chance, how many). "trinket" is any one of TRINKETS.
TREASURE = [("coin", 0.4, (1, 6)), ("trinket", 0.22, (1, 1)), ("pottery shard", 0.15, (1, 1)),
            ("arrowhead", 0.11, (1, 1)), ("old bone", 0.08, (1, 1)), ("rusty dagger", 0.04, (1, 1))]
PRECIOUS = [("silver ring", 0.06, (1, 1)), ("gold ring", 0.025, (1, 1))]   # under towns only


def amount(kind: str, n: int) -> str:
    """"an axe", "3 logs"."""
    k = KINDS[kind]
    if n == 1:
        return ("an " if k.name[0] in "aeiou" else "a ") + k.name
    return f"{n} {k.plural}"


def treasure(rng: random.Random, town: bool = False) -> tuple[str, int]:
    """Something lost and buried. Rings only turn up under a town."""
    r = rng.random()
    for kind, chance, (lo, hi) in (PRECIOUS if town else []) + TREASURE:
        if r < chance:
            return (rng.choice(TRINKETS) if kind == "trinket" else kind), rng.randint(lo, hi)
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


def drop(level, x: int, y: int, kind: str, n: int = 1) -> None:
    level.items.setdefault((x, y), []).extend([kind] * n)


def pick_up(level, x: int, y: int, inventory: Inventory) -> list[str]:
    """Everything lying at (x, y) into the bag. Returns what was picked up."""
    got = level.items.pop((x, y), [])
    for kind in got:
        inventory.add(kind)
    return got


def describe_pile(kinds) -> str:
    """"an axe", "2 coins and a spear": a pile (a list of kinds) or a bag (kind -> count)."""
    counts: dict[str, int] = {}
    if isinstance(kinds, dict):
        counts = {k: n for k, n in kinds.items() if n}
    else:
        for k in kinds:
            counts[k] = counts.get(k, 0) + 1
    parts = [amount(k, n) for k, n in counts.items()]
    if not parts:
        return "nothing"
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]


# ----------------------------------------------------------------- barrels

def fill_barrel(level, x: int, y: int) -> Inventory:
    """What's in a barrel the first time it's opened: food in a cellar or a house, odds and ends
    in a shed. The same every game."""
    rng = random.Random(f"{level.key}{x},{y}")
    bag = Inventory()
    inside = level.building_at(x, y)
    if level.key[0] == "cellar":
        for food in ("apple", "salt fish", "loaf of bread"):
            if rng.random() < 0.6:
                bag.add(food, rng.randint(1, 4))
    elif inside is not None and inside.kind in ("house", "inn", "bakery", "butcher", "armoury"):
        for food in ("apple", "loaf of bread", "salt fish"):
            if rng.random() < 0.4:
                bag.add(food, rng.randint(1, 2))
    elif rng.random() < 0.5:
        bag.add(rng.choice(["apple", "salt fish", "log", rng.choice(TRINKETS)]))
    if rng.random() < 0.15:
        bag.add("coin", rng.randint(1, 4))
    return bag
