"""Things you can carry, and the bag you carry them in.

Items are kinds (an axe, a log, a coin) and how many. They lie on a level's tiles
(`Level.items`), sometimes under the ground (`Level.buried`, found by digging), sit in barrels
and chests (`Level.stores`), and you carry them in your `Inventory`. Some are tools that let you do things:

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
    # precious: only ever found under towns, or in a chest
    "silver ring": Kind("silver ring", "silver rings", "○", RING, "worth a good deal", value=15),
    "gold ring": Kind("gold ring", "gold rings", "○", (245, 200, 70), "worth a great deal", value=35),
    # household things, kept in chests at home
    "candle": Kind("candle", "candles", "¡", (240, 230, 190), "household goods"),
    "wool blanket": Kind("wool blanket", "wool blankets", "≡", (170, 150, 130), "household goods"),
    "wooden spoon": Kind("wooden spoon", "wooden spoons", "/", (190, 150, 100), "household goods"),
    "spool of thread": Kind("spool of thread", "spools of thread", "°", (200, 180, 200), "household goods"),
    "clay cup": Kind("clay cup", "clay cups", "u", (200, 130, 90), "household goods"),
    "bar of soap": Kind("bar of soap", "bars of soap", "▪", (225, 220, 180), "household goods"),
    # the tools and stuff of a trade, kept in a chest at the worker's house or shop
    "seed pouch": Kind("seed pouch", "seed pouches", "°", (170, 150, 90), "a farmer's"),
    "horseshoe": Kind("horseshoe", "horseshoes", "∩", (165, 165, 175), "a farmer's", value=1),
    "ball of twine": Kind("ball of twine", "balls of twine", "°", (200, 175, 120), "a farmer's"),
    "fishing net": Kind("fishing net", "fishing nets", "#", (170, 185, 170), "a fisherman's", value=1),
    "fish hook": Kind("fish hook", "fish hooks", "¿", (180, 185, 195), "a fisherman's"),
    "coil of rope": Kind("coil of rope", "coils of rope", "§", (190, 160, 110), "rope", value=1),
    "whetstone": Kind("whetstone", "whetstones", "▬", (150, 150, 160), "for sharpening blades", value=1),
    "iron nails": Kind("iron nails", "iron nails", "¦", (160, 160, 170), "a lumberjack's"),
    "sack of flour": Kind("sack of flour", "sacks of flour", "♠", (235, 230, 215), "a baker's", value=1),
    "rolling pin": Kind("rolling pin", "rolling pins", "─", (200, 160, 110), "a baker's"),
    "pouch of salt": Kind("pouch of salt", "pouches of salt", "°", (235, 235, 235), "a butcher's", value=1),
    "butcher's apron": Kind("butcher's apron", "butcher's aprons", "[", (210, 190, 180), "a butcher's"),
    "flask of oil": Kind("flask of oil", "flasks of oil", "!", (200, 180, 90), "for keeping steel bright", value=1),
    "iron rivets": Kind("iron rivets", "iron rivets", "¦", (175, 175, 185), "an armourer's"),
    # what's hidden deep in caves
    "silver nugget": Kind("silver nugget", "silver nuggets", "•", RING, "raw silver", value=6),
    "gold nugget": Kind("gold nugget", "gold nuggets", "•", (245, 200, 70), "raw gold", value=12),
    "rough garnet": Kind("rough garnet", "rough garnets", "♦", (170, 40, 50), "a jewel", value=8),
    "raw amethyst": Kind("raw amethyst", "raw amethysts", "♦", (160, 90, 200), "a jewel", value=10),
    "uncut emerald": Kind("uncut emerald", "uncut emeralds", "♦", (60, 190, 110), "a jewel", value=20),
    "sapphire": Kind("sapphire", "sapphires", "♦", (70, 110, 230), "a fine jewel", value=25),
    "ruby": Kind("ruby", "rubies", "♦", (230, 40, 60), "a fine jewel", value=30),
    # strange things from the crypts: nobody buys them, and what they're for is yet to be learned
    "black candle": Kind("black candle", "black candles", "¡", (90, 80, 100), "strange; what is it for?"),
    "bone flute": Kind("bone flute", "bone flutes", "¦", (225, 220, 195), "strange; what is it for?"),
    "rune-carved stone": Kind("rune-carved stone", "rune-carved stones", "♣", (140, 170, 160), "strange; what is it for?"),
    "tarnished amulet": Kind("tarnished amulet", "tarnished amulets", "♀", (150, 160, 120), "strange; what is it for?"),
    "vial of grave dust": Kind("vial of grave dust", "vials of grave dust", "!", (150, 140, 130), "strange; what is it for?"),
    "sealed scroll": Kind("sealed scroll", "sealed scrolls", "?", (220, 205, 160), "strange; what is it for?"),
    "silver reliquary": Kind("silver reliquary", "silver reliquaries", "Φ", RING, "strange; what is it for?"),
    "obsidian mirror": Kind("obsidian mirror", "obsidian mirrors", "○", (70, 60, 90), "strange; what is it for?"),
}
TRINKETS = ["brass button", "clay bead", "tin whistle", "bone die", "copper bangle", "carved figurine",
            "glass marble", "old buckle"]
FOODS = [k for k, v in KINDS.items() if v.meal]
CARCASSES = [k for k in KINDS if k.endswith(" carcass")]
# What turns up under the ground: (kind, chance, how many). "trinket" is any one of TRINKETS.
TREASURE = [("coin", 0.4, (1, 6)), ("trinket", 0.22, (1, 1)), ("pottery shard", 0.15, (1, 1)),
            ("arrowhead", 0.11, (1, 1)), ("old bone", 0.08, (1, 1)), ("rusty dagger", 0.04, (1, 1))]
PRECIOUS = [("silver ring", 0.06, (1, 1)), ("gold ring", 0.025, (1, 1))]   # under towns only
HOUSEHOLD = ["candle", "wool blanket", "wooden spoon", "spool of thread", "clay cup", "bar of soap"]
TRADE_GOODS = {     # a worker -> what they keep in their chest
    "farmer": ["seed pouch", "horseshoe", "ball of twine", "apple"],
    "fisherman": ["fishing net", "fish hook", "coil of rope", "salt fish"],
    "lumberjack": ["whetstone", "iron nails", "coil of rope", "log"],
    "baker": ["sack of flour", "rolling pin", "loaf of bread"],
    "butcher": ["pouch of salt", "butcher's apron", "roast meat"],
    "shopkeeper": ["whetstone", "flask of oil", "iron rivets"],
}
SHOP_KEEPER = {"bakery": "baker", "butcher": "butcher", "armoury": "shopkeeper"}
GEMS = ["rough garnet", "raw amethyst", "uncut emerald", "sapphire", "ruby"]   # commonest first
CURIOS = ["black candle", "bone flute", "rune-carved stone", "tarnished amulet", "vial of grave dust",
          "sealed scroll", "silver reliquary", "obsidian mirror"]


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


# ----------------------------------------------------------------- chests

def fill_chest(level, x: int, y: int) -> Inventory:
    """What's in a chest the first time it's opened. The same every game.

    - at home: household things and the tools of the owner's trade, sometimes coins or a trinket
      (now and then a family ring)
    - in a shop: the stuff of the trade and the takings
    - in a cave: gold and silver and rough jewels, richer the deeper you go
    - in a crypt: old coins and strange things whose use is yet to be learned
    """
    rng = random.Random(f"chest{level.key}{x},{y}")
    bag = Inventory()
    kind, depth = level.key[0], (level.key[3] if len(level.key) > 3 else 0)
    if kind == "cave":
        bag.add("coin", rng.randint(5, 15) * depth)
        for _ in range(rng.randint(1, 2) + depth // 2):
            bag.add(rng.choice(["silver nugget", "silver nugget", "gold nugget"]))
        for _ in range(rng.randint(1, 1 + depth)):
            bag.add(GEMS[min(len(GEMS) - 1, int(rng.random() ** 1.5 * (2 + depth)))])
        return bag
    if kind == "crypt":
        for k in rng.sample(CURIOS, rng.randint(1, 2)):
            bag.add(k)
        if rng.random() < 0.6:
            bag.add("coin", rng.randint(4, 18))
        if rng.random() < 0.3:
            bag.add(rng.choice(TRINKETS + ["old bone", "old bone"]))
        if rng.random() < 0.1:
            bag.add(rng.choice(["silver ring", "gold ring"]))
        return bag
    inside = level.building_at(x, y)
    owner = getattr(inside, "owner", "") or SHOP_KEEPER.get(getattr(inside, "kind", ""), "")
    shop = inside is not None and inside.kind in SHOP_KEEPER
    goods = TRADE_GOODS.get(owner, [])
    for k in rng.sample(goods, min(len(goods), rng.randint(1, 2 + shop))):
        bag.add(k, rng.randint(1, 3) if k in FOODS or k == "log" or k.endswith(("nails", "rivets", "hook")) else 1)
    if not shop:
        for k in rng.sample(HOUSEHOLD, rng.randint(1, 2)):
            bag.add(k)
    if rng.random() < (0.9 if shop else 0.5):
        bag.add("coin", rng.randint(5, 20) if shop else rng.randint(2, 10))
    if rng.random() < 0.35:
        bag.add(rng.choice(TRINKETS))
    if rng.random() < 0.06 and not shop:                     # a family heirloom
        bag.add(rng.choice(["silver ring", "silver ring", "gold ring"]))
    return bag
