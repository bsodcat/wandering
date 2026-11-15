"""A stone city's other great buildings: the ones every city in a tale of swords and spells has.
game/landmarks.py builds the keep, the temple, the playhouse and the rest; these come on top of
them, dealt out among the parts of the city by landmarks.CITY_PLANS:

- the bathhouse: a warm pool under a roof, benches round it, a hearth to heat the water. Walk
  into the pool to bathe (bump): it warms you through and rests you
- the counting house: a moneylender's counter, chests behind it, clerks at their ledgers
- the training yard: practice dummies and archery butts, where the master-at-arms drills recruits
- the graveyard: rows of gravestones inside a fence, a few trees, and the gravedigger
- the foundling house: an orphanage, beds in rows, its children and their matron
- the house of healing: a healer, and the sick in their beds
- the Adventurers' Hall: long tables and a hearth, sellswords between jobs, and a notice board by
  the door (walk into it to read the notices)
- the brewhouse: vats and barrels; the brewer rolls barrels down to the inn
- the tannery, out by the lower quarter: vats of lye, and a tanner who buys pelts
- the mage tower: a round stone tower, an arcane circle in its floor, books wall to wall, a mage
  and their apprentices
- the schoolhouse: benches facing the schoolmaster's table, where the children learn their
  letters of a weekday morning

Each is a Building (or a Place, for the open ones) so game/citylife.py can people them.
"""
from __future__ import annotations

import random

from . import tiles as T
from .landmarks import frame, outside_of, plot, put, raise_hall, reach_street
from .level import Level, Place
from .structures import furnish

FAMILIES = ["Goldmere", "Varro", "Ashcombe", "Talbrand", "Orsini", "Halloway"]
TOWERS = ["the Violet Tower", "the Tower of the Circle", "the Starward Tower", "the Ember Tower"]


def middle(level: Level) -> tuple[int, int]:
    return level.width // 2, level.height // 2


def bathhouse(level: Level, rng: random.Random, at) -> None:
    box = plot(level, 17, 9, at)
    if box is None:
        return
    b = raise_hall(level, rng, *box, 17, 9, middle(level), "bathhouse", "the bathhouse")
    x0, y0 = box
    t = level.tiles
    for x in range(x0 + 4, x0 + 13):                      # the pool, a walk of stone all round it
        for y in range(y0 + 3, y0 + 6):
            t[x, y] = T.POOL
    for x in range(x0 + 3, x0 + 14, 2):
        for y in (y0 + 1, y0 + 7):
            put(level, b, (x, y), T.BENCH)
    put(level, b, (x0 + 15, y0 + 1), T.HEARTH)
    put(level, b, (x0 + 15, y0 + 7), T.BARREL)
    reach_street(level, outside_of(b))


def counting_house(level: Level, rng: random.Random, at) -> None:
    box = plot(level, 13, 8, at)
    if box is None:
        return
    b = raise_hall(level, rng, *box, 13, 8, middle(level), "counting house",
                   f"the counting house of {rng.choice(FAMILIES)}")
    a, depth, width, aisle = frame(b)
    for v in range(1, width + 1):                          # the counter across the room, a gap at one end
        if v != width:
            put(level, b, a(3, v), T.COUNTER)
    for v in range(1, width + 1, 2):
        put(level, b, a(depth, v), T.CHEST)
    put(level, b, a(1, 1), T.TABLE)
    reach_street(level, outside_of(b))


def training_yard(level: Level, rng: random.Random, at) -> None:
    """Flagstones fenced round: a row of practice dummies, archery butts at the far end."""
    box = plot(level, 19, 9, at)
    if box is None:
        return
    x0, y0 = box
    t = level.tiles
    t[x0: x0 + 19, y0: y0 + 9] = T.FLAGSTONES
    t[x0: x0 + 19, y0] = t[x0: x0 + 19, y0 + 8] = T.FENCE
    t[x0, y0: y0 + 9] = t[x0 + 18, y0: y0 + 9] = T.FENCE
    t[x0 + 9, y0 + 8] = T.FLAGSTONES                       # the way in
    for x in range(x0 + 3, x0 + 16, 3):
        t[x, y0 + 2] = T.DUMMY
    for y in range(y0 + 3, y0 + 7, 2):
        t[x0 + 17, y] = T.TARGET
    yard = [(x, y) for x in range(x0 + 1, x0 + 18) for y in range(y0 + 1, y0 + 8) if t[x, y] == T.FLAGSTONES]
    level.places.append(Place("training yard", "the training yard", yard))
    reach_street(level, (x0 + 9, y0 + 9))


def graveyard(level: Level, rng: random.Random, at) -> None:
    """A fence round rows of gravestones, a path up the middle, and a few old trees."""
    w, h = 23, 11
    box = plot(level, w, h, at)
    if box is None:
        return
    x0, y0 = box
    t = level.tiles
    mx = x0 + w // 2
    t[x0: x0 + w, y0: y0 + h] = T.GRASS
    t[x0: x0 + w, y0] = t[x0: x0 + w, y0 + h - 1] = T.FENCE
    t[x0, y0: y0 + h] = t[x0 + w - 1, y0: y0 + h] = T.FENCE
    t[mx, y0 + 1: y0 + h] = T.PATH
    for y in range(y0 + 2, y0 + h - 2, 2):
        for x in range(x0 + 2, x0 + w - 2, 2):
            if abs(x - mx) > 1 and rng.random() < 0.8:
                t[x, y] = T.GRAVE
    for c in ((x0 + 1, y0 + 1), (x0 + w - 2, y0 + 1)):
        t[c] = T.TREE
    ground = [(x, y) for x in range(x0 + 1, x0 + w - 1) for y in range(y0 + 1, y0 + h - 1)
              if t[x, y] in (T.GRASS, T.PATH)]
    level.places.append(Place("graveyard", "the graveyard", ground))
    reach_street(level, (mx, y0 + h))


def orphanage(level: Level, rng: random.Random, at) -> None:
    box = plot(level, 15, 8, at)
    if box is None:
        return
    raise_hall(level, rng, *box, 15, 8, middle(level), "orphanage", "the foundling house", floor=T.WOOD_FLOOR)
    furnish(level, rng, *box, 15, 8, beds=8, hearth=True, tables=2, barrels=1, extra=((T.CHEST, 1),))
    reach_street(level, outside_of(level.buildings[-1]))


def healer(level: Level, rng: random.Random, at) -> None:
    box = plot(level, 11, 7, at)
    if box is None:
        return
    raise_hall(level, rng, *box, 11, 7, middle(level), "healer", "the house of healing", floor=T.WOOD_FLOOR)
    furnish(level, rng, *box, 11, 7, beds=4, hearth=True, tables=1, barrels=1, extra=((T.CHEST, 1), (T.BOOKSHELF, 1)))
    reach_street(level, outside_of(level.buildings[-1]))


def adventurers(level: Level, rng: random.Random, at) -> None:
    """The Adventurers' Hall: long tables, a hearth, racks and chests, and the notice board out
    by the door."""
    box = plot(level, 17, 9, at)
    if box is None:
        return
    b = raise_hall(level, rng, *box, 17, 9, middle(level), "adventurers' hall", "the Adventurers' Hall",
                   floor=T.WOOD_FLOOR)
    furnish(level, rng, *box, 17, 9, beds=0, hearth=True, tables=4, barrels=2, extra=((T.RACK, 2), (T.CHEST, 1)))
    t = level.tiles
    out = outside_of(b)
    dx, dy = out[0] - b.door[0], out[1] - b.door[1]
    for side in (2, -2):                                   # beside the door, on the street side
        c = (out[0] + (side if dy else 0), out[1] + (side if dx else 0))
        if level.in_bounds(*c) and t[c] in (T.GRASS, T.DIRT, T.DRY_GRASS, T.STUMP, T.PATH, T.SAND):
            t[c] = T.NOTICE
            break
    reach_street(level, out)


def brewhouse(level: Level, rng: random.Random, at) -> None:
    box = plot(level, 12, 8, at)
    if box is None:
        return
    raise_hall(level, rng, *box, 12, 8, middle(level), "brewhouse", "the brewhouse", floor=T.WOOD_FLOOR)
    furnish(level, rng, *box, 12, 8, beds=0, hearth=True, tables=0, barrels=4, extra=((T.VAT, 3),), middle=T.VAT)
    reach_street(level, outside_of(level.buildings[-1]))


def tannery(level: Level, rng: random.Random, at) -> None:
    box = plot(level, 11, 7, at)
    if box is None:
        return
    raise_hall(level, rng, *box, 11, 7, middle(level), "tannery", "the tannery", floor=T.WOOD_FLOOR)
    furnish(level, rng, *box, 11, 7, beds=0, hearth=False, tables=1, barrels=1, extra=((T.VAT, 3), (T.RACK, 1)),
            middle=T.VAT)
    reach_street(level, outside_of(level.buildings[-1]))


def mage_tower(level: Level, rng: random.Random, at) -> None:
    """A round stone tower: an arcane circle in the middle of the floor, bookshelves round the
    wall, a table of instruments, a bed for the mage."""
    n = 11
    box = plot(level, n, n, at)
    if box is None:
        return
    b = raise_hall(level, rng, *box, n, n, middle(level), "mage tower", rng.choice(TOWERS))
    x0, y0 = box
    t = level.tiles
    c = n // 2
    for x in range(n):                                     # round it off: fill the corners with stone
        for y in range(n):
            if (x - c) ** 2 + (y - c) ** 2 > (c + 0.4) ** 2 and t[x0 + x, y0 + y] != T.DOOR:
                t[x0 + x, y0 + y] = T.STONE_WALL
    for x in range(n):
        for y in range(n):
            d = (x - c) ** 2 + (y - c) ** 2
            if d <= 2:
                t[x0 + x, y0 + y] = T.CIRCLE
            elif (c - 1.6) ** 2 < d <= (c - 0.6) ** 2 and t[x0 + x, y0 + y] == T.STONE_FLOOR and (x + y) % 2:
                t[x0 + x, y0 + y] = T.BOOKSHELF
    # keep the way in from the door to the circle clear
    a, depth, width, aisle = frame(b)
    for u in range(1, depth):
        if t[a(u, aisle)] == T.BOOKSHELF:
            t[a(u, aisle)] = T.STONE_FLOOR
    for spot, tile in (((x0 + 2, y0 + c), T.BED), ((x0 + n - 3, y0 + c), T.TABLE)):
        if t[spot] == T.STONE_FLOOR and spot != a(1, aisle):
            t[spot] = tile
    reach_street(level, outside_of(b))


def school(level: Level, rng: random.Random, at) -> None:
    box = plot(level, 13, 8, at)
    if box is None:
        return
    b = raise_hall(level, rng, *box, 13, 8, middle(level), "school", "the schoolhouse", floor=T.WOOD_FLOOR)
    a, depth, width, aisle = frame(b)
    for u in range(2, depth - 1, 2):                       # benches in rows, the aisle up the middle
        for v in range(1, width + 1):
            if abs(v - aisle) > 0:
                put(level, b, a(u, v), T.BENCH)
    put(level, b, a(depth, aisle + 1), T.TABLE)
    put(level, b, a(depth, 1), T.BOOKSHELF)
    reach_street(level, outside_of(b))


STABLE = (13, 13)         # a stable above its paddock (a city's); a fort's is low and wide: STABLE_SMALL
STABLE_SMALL = (17, 5)


def stable(level: Level, rng: random.Random, at, name: str = "the guards' stable", size=STABLE) -> bool:
    """A timber stable, troughs along its back wall, its door onto a fenced paddock with a gate
    to the street: the guards' horses, and the groom who keeps them. A tall plot has the
    paddock below the stable, a wide one beside it. Returns whether it went up."""
    from .structures import building
    w, h = size
    box = plot(level, w, h, at)
    if box is None:
        return False
    x0, y0 = box
    t = level.tiles
    wide = w > 2 * h
    if wide:                                           # the stable on the left, the paddock to its right
        hw = 6
        building(level, rng, x0, y0, hw, h, (x0 + w, y0 + h // 2), kind="stable", name=name, torch=False)
        b = level.buildings[-1]
        for y in range(y0 + 1, y0 + h - 1, 2):
            put(level, b, (x0 + 1, y), T.TROUGH)
        px0, py0, px1, py1 = x0 + hw, y0, x0 + w - 1, y0 + h - 1
        t[px0: px1 + 1, py0: py1 + 1] = T.DIRT
        t[px0: px1 + 1, py0] = t[px0: px1 + 1, py1] = T.FENCE
        t[px1, py0: py1 + 1] = T.FENCE
        gate = ((px0 + px1) // 2, py1)
        out = (gate[0], gate[1] + 1)
        inner = [(x, y) for x in range(px0, px1) for y in range(py0 + 1, py1)]
    else:                                              # the stable on top, the paddock below
        hall_h = 5
        building(level, rng, x0, y0, w, hall_h, (x0 + w // 2, y0 + h), kind="stable", name=name, torch=False)
        b = level.buildings[-1]
        for x in range(x0 + 1, x0 + w - 1, 2):
            put(level, b, (x, y0 + 1), T.TROUGH)
        top = y0 + hall_h
        t[x0: x0 + w, top: y0 + h] = T.DIRT
        t[x0, top: y0 + h] = t[x0 + w - 1, top: y0 + h] = T.FENCE
        t[x0: x0 + w, y0 + h - 1] = T.FENCE
        gate = (x0 + w // 2, y0 + h - 1)
        out = (gate[0], gate[1] + 1)
        inner = [(x, y) for x in range(x0 + 1, x0 + w - 1) for y in range(top, y0 + h - 1)]
        t[x0 + w - 2, y0 + h - 2] = T.TROUGH
    t[gate] = T.PATH
    paddock = [c for c in inner if T.WALK[t[c]] and c != b.door]
    level.places.append(Place("stable", name, paddock + b.floor(t), "horse"))
    if level.in_bounds(*out):
        reach_street(level, out)
    return True


# ----------------------------------------------------------------- walking into things

NOTICES = [
    "WOLVES on the north road. The guard pays 3 coins a pelt, brought in.",
    "WANTED: a sellsword to see a cart of wool through the hills. Ask at the hall.",
    "Goblins seen in the old caves. Any who clear them out will be well paid.",
    "LOST: a grey cat, answers to Soot. Reward. Ask at the foundling house.",
    "The mage of the tower seeks rune-carved stones. Fair prices given.",
    "By order of the crown: no blades drawn inside the walls.",
    "Rooms at the inn: clean beds, hot soup, no fleas (mostly).",
    "The graveyard is closed after dark. The gravedigger has a spade and no patience.",
    "A ballad tonight at the playhouse: the Drowned King. Two coppers.",
    "Climbing rope and grapples at the smith's. The cliffs won't wait.",
    "Fever in the lower quarter. The house of healing has poultices.",
    "Fights at the pit every afternoon. Bets taken.",
]
BATH_MINUTES = 30
BATH_STAMINA = 30


def bump(engine, tile: int, x: int, y: int) -> bool:
    """Walking into one of these buildings' fittings. Returns whether something happened."""
    if tile == T.NOTICE:
        day = int(engine.minutes // 1440)
        notes = random.Random(f"{x},{y},{day}").sample(NOTICES, 3)
        engine.say("The notice board: " + "  /  ".join(notes))
        return True
    if tile == T.POOL:
        from .player import NORMAL
        p = engine.player
        p.body = max(p.body, NORMAL)
        p.stamina = min(100.0, p.stamina + BATH_STAMINA)
        p.wet = 0.0
        engine.pass_time(BATH_MINUTES / 60, effort=0.0)
        engine.say("You soak in the warm pool a while, then dry off by the hearth. You feel warm through, and rested.")
        return True
    if tile == T.GRAVE:
        names = random.Random(f"{x},{y}")
        from .people import FAMILY, FIRST
        engine.say(f"The gravestone reads: {names.choice(FIRST)} {names.choice(FAMILY)}. "
                   f"{names.choice(['Rest well.', 'Beloved.', 'Gone ahead.', 'Taken by the fever.', 'Lost at sea.', 'A good neighbour.'])}")
        return True
    if tile == T.DUMMY:
        engine.say("You give the practice dummy a whack. It wobbles, unimpressed.")
        return True
    return False
