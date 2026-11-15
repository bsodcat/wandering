"""The great buildings and gathering places of a stone city (game/cities.py builds the walls,
streets and houses round them).

Every part of a city has its market square (a fountain in its middle, statues about it, stalls
round its edge), an inn, a guardhouse, and guards posted at the crossings of its streets. The
guardhouse has a bunk for every guard of the part (the day and night watch share them), and
two more floors: upstairs the sergeant's quarters and the armoury, below a lockup of barred
cells and the watch's stores (guard_upstairs, guard_lockup). On top
of that each part has its own landmarks (CITY_PLANS), so the four parts of a city differ:

- the keep: a walled castle in the part's inner quarter, its gate toward the square, holding
  - the throne room (a carpet up to the throne), where the ruler holds court
  - the great hall, where the court dines at long tables
  - the royal chambers (the ruler's and their consort's beds)
  - the library, shelved wall to wall
  - the keep's barracks, where the royal guard sleeps
  - the gaol, with stairs down to the dungeon: a passage of barred cells, prisoners in them and
    a gaoler on watch
- a temple with an altar and pews (a part without one has a small chapel), and the gallows yard: a gallows on its platform, stocks
- a playhouse with a stage and benches, and a fighting pit ringed by a fence
- the guildhall, an alchemist's, and a market row of stalls along the main street

and besides:
- the city garden, just inside a gate of the part with the guildhall: hedges round flower
  beds, gravel walks crossing at a fountain, benches and trees
- the lower quarter, in the outer corner of the parts with the gallows or the pit: cramped
  timber hovels in place of stone houses (game/cities.py)
- trees: an avenue along each part's main streets, trees on the banks of open water, and a
  scattering out beyond the walls (plant_trees)

Each is a Building (or a Place, for the open ones), so game/citylife.py can people them.
"""
from __future__ import annotations

import random
import zlib

import numpy as np

from . import tiles as T
from .level import Building, Level, Place
from .structures import EDGE, building, connect, furnish, inn_stairs, put_inside, ways

CITY_PLANS = [("keep",), ("temple", "gallows"), ("playhouse", "pit"), ("guildhall", "alchemist", "market")]
KEEP_W, KEEP_H = 80, 34          # the keep's curtain wall, outside to outside
OPEN = [T.GRASS, T.DIRT, T.STUMP, T.DRY_GRASS, T.SAND, T.MUD, T.TALL_GRASS]
GODS = ["the Dawn", "the Hearth", "the Harvest Mother", "the Silent Judge", "the Sea Father", "the Lantern"]
CROSSINGS = 6                    # crossings a part's guards watch, at most
GARDEN = (25, 11)                # the city garden, hedge to hedge
AVENUE = 7                       # tiles between the trees along a main street
BANK_TREES = 0.05                # of open ground on the banks of open water, planted
OUTSIDE_TREES = 0.012            # of open ground beyond the walls


def plan_of(site, part: tuple[int, int]) -> tuple:
    """The landmarks in this part of the city: each city deals its parts a different hand."""
    px, py = part
    turn = zlib.crc32(site.name.encode()) % len(CITY_PLANS)
    return CITY_PLANS[(py * site.span[0] + px + turn) % len(CITY_PLANS)]


def garden_part(site) -> tuple[int, int]:
    return next((px, py) for px in range(site.span[0]) for py in range(site.span[1])
                if "guildhall" in plan_of(site, (px, py)))


def lower_quarter(site, part) -> bool:
    """Whether this part of the city has a lower quarter of hovels."""
    p = plan_of(site, part)
    return "gallows" in p or "pit" in p


def keep_part(site) -> tuple[int, int]:
    """Which part of a city the keep stands in."""
    return next((px, py) for px in range(site.span[0]) for py in range(site.span[1])
                if "keep" in plan_of(site, (px, py)))


# ----------------------------------------------------------------- finding room

def plot(level: Level, w: int, h: int, target: tuple[int, int], margin: int = 1):
    """The clear box (x0, y0) of w x h, with a margin of open ground round it, nearest `target`;
    None if there's no room anywhere."""
    t = level.tiles
    ok = np.isin(t, OPEN)
    off = getattr(level, "_keep_off", None)      # a city's banks (game/cities.py)
    if off is not None:
        ok &= ~off
    ok[: EDGE + 1, :] = ok[-EDGE - 1:, :] = False
    ok[:, : EDGE + 1] = ok[:, -EDGE - 1:] = False
    bw, bh = w + 2 * margin, h + 2 * margin
    if bw > t.shape[0] or bh > t.shape[1]:
        return None
    s = np.zeros((t.shape[0] + 1, t.shape[1] + 1), np.int32)
    s[1:, 1:] = ok.astype(np.int32).cumsum(0).cumsum(1)
    sums = s[bw:, bh:] - s[:-bw, bh:] - s[bw:, :-bh] + s[:-bw, :-bh]
    spots = np.argwhere(sums == bw * bh)
    if not len(spots):
        return None
    xs, ys = spots[:, 0] + margin, spots[:, 1] + margin
    d = (xs + w / 2 - target[0]) ** 2 + (2 * (ys + h / 2 - target[1])) ** 2
    i = int(np.argmin(d))
    return int(xs[i]), int(ys[i])


def centre_door(level: Level, b: Building) -> tuple[tuple[int, int], tuple[int, int]]:
    """Moves a building's door to the middle of its wall (for a hall, with its aisle up the
    middle). Returns (door, the tile outside it)."""
    t = level.tiles
    x0, y0, x1, y1 = b.x0, b.y0, b.x0 + b.w - 1, b.y0 + b.h - 1
    dx, dy = b.door
    wall = t[x0, y0]
    if dx in (x0, x1):
        new, out = (dx, (y0 + y1) // 2), (dx + (1 if dx == x1 else -1), (y0 + y1) // 2)
    else:
        new, out = ((x0 + x1) // 2, dy), ((x0 + x1) // 2, dy + (1 if dy == y1 else -1))
    if new != b.door:
        t[b.door] = wall
        t[new] = T.DOOR
        b.door = new
    if level.in_bounds(*out) and (T.CLEARABLE[t[out]] or t[out] == T.FLAGSTONES):
        t[out] = T.PATH if t[out] != T.FLAGSTONES else T.FLAGSTONES
    return new, out


def frame(b: Building):
    """(to_xy, depth, width, aisle) for laying out a hall from its door: u runs 1..depth from the
    door's wall to the far one, v 1..width across, and the aisle is the v of the door."""
    x0, y0, x1, y1 = b.x0, b.y0, b.x0 + b.w - 1, b.y0 + b.h - 1
    dx, dy = b.door
    if dx == x0:
        return (lambda u, v: (x0 + u, y0 + v)), b.w - 2, b.h - 2, dy - y0
    if dx == x1:
        return (lambda u, v: (x1 - u, y0 + v)), b.w - 2, b.h - 2, dy - y0
    if dy == y0:
        return (lambda u, v: (x0 + v, y0 + u)), b.h - 2, b.w - 2, dx - x0
    return (lambda u, v: (x0 + v, y1 - u)), b.h - 2, b.w - 2, dx - x0


def raise_hall(level: Level, rng: random.Random, x0: int, y0: int, w: int, h: int, toward, kind: str, name: str,
               floor: int = T.STONE_FLOOR) -> Building:
    """Stone walls and a floor, the door in the middle of the side facing `toward`."""
    building(level, rng, x0, y0, w, h, toward, wall=T.STONE_WALL, floor=floor, kind=kind, name=name)
    b = level.buildings[-1]
    centre_door(level, b)
    return b


def box_of(b: Building) -> tuple[int, int, int, int]:
    return b.x0, b.y0, b.x0 + b.w - 1, b.y0 + b.h - 1


def put(level: Level, b: Building, c: tuple[int, int], tile: int) -> bool:
    t = level.tiles
    if not b.contains(*c) or t[c] not in (T.STONE_FLOOR, T.WOOD_FLOOR, T.CARPET):
        return False
    return put_inside(t, c, tile, box_of(b))


def pews(level: Level, b: Building, first: int, last: int, tile: int = T.BENCH) -> None:
    """Rows of benches across a hall, every other row from `first` to `last`, either side of the
    aisle."""
    at, depth, width, aisle = frame(b)
    for u in range(first, last + 1, 2):
        for v in range(2, width):
            if abs(v - aisle) > 1:
                put(level, b, at(u, v), tile)


def reach_street(level: Level, outside: tuple[int, int]) -> None:
    connect(level, outside, np.isin(level.tiles, [T.STREET, T.BRIDGE, T.ROAD]), T.STREET)


# ----------------------------------------------------------------- the square

def adorn_square(level: Level, fountain: bool) -> None:
    """A fountain in place of the well (the keep's part keeps its well), and statues about it."""
    t = level.tiles
    cx, cy = level.width // 2, level.height // 2
    if fountain and t[cx, cy] == T.WELL:
        t[cx, cy] = T.FOUNTAIN
    for x, y in ((cx - 5, cy - 2), (cx + 4, cy + 2), (cx - 5, cy + 2), (cx + 4, cy - 2)):
        if t[x, y] == T.STREET and x not in (cx - 1, cx) and y != cy:
            t[x, y] = T.STATUE


def square_stalls(level: Level) -> list:
    """The street tiles beside the square's stalls, where the merchants stand."""
    t = level.tiles
    cx, cy = level.width // 2, level.height // 2
    out = []
    for x in range(cx - 10, cx + 11):
        for y in range(cy - 5, cy + 6):
            if t[x, y] == T.STALL:
                out.append([(x + dx, y + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)
                            if level.walkable(x + dx, y + dy) and not T.ROOF[t[x + dx, y + dy]]])
    return [s for s in out if s]


def market_row(level: Level, rng: random.Random) -> None:
    """Stalls in a row along each side of the main street, out from the square both ways."""
    t = level.tiles
    cx, cy = level.width // 2, level.height // 2
    stalls = []
    for x in list(range(cx - 14, cx - 46, -3)) + list(range(cx + 14, cx + 46, 3)):
        for y in (cy - 1, cy + 1):
            off = getattr(level, "_keep_off", None)
            if level.in_bounds(x, y) and t[x, y] in OPEN and t[x, cy] == T.STREET and (off is None or not off[x, y]):
                t[x, y] = T.STALL
                stalls.append((x, y))
    if stalls:
        # the stall keepers stand in the street before them
        front = [(x, cy) for x, _ in stalls if t[x, cy] == T.STREET]
        level.places.append(Place("market", "the market row", sorted(set(front))))


GUARDHOUSE = (16, 8)      # the guardhouse, and its floors above and below
GUARD_BUNKS = 16          # beds in it: enough for the watch, the day and night guards sharing
SMALL_GUARDHOUSE = (10, 6)   # where there's no room for that: one floor, a few beds


def guardhouse(level: Level, rng: random.Random, at) -> None:
    """The watch's house: bunks round the walls, a hearth, tables and weapon racks, and stairs up
    to the sergeant's floor and down to the lockup. Squeezed for room, a small one-floor house."""
    big = True
    box = plot(level, *GUARDHOUSE, at)
    if box is None:
        big, box = False, plot(level, *SMALL_GUARDHOUSE, at)
        if box is None:
            return
    w, h = GUARDHOUSE if big else SMALL_GUARDHOUSE
    b = raise_hall(level, rng, *box, w, h, (level.width // 2, level.height // 2), "guardhouse", "the guardhouse")
    if big:
        x0, y0 = box
        inn_stairs(level, x0, y0, x0 + w - 1, y0 + h - 1, b.door, ways=("guard_up", "guard_cells"))
    furnish(level, rng, *box, w, h, beds=GUARD_BUNKS if big else 4, hearth=True, tables=2 if big else 1,
            barrels=1, extra=((T.RACK, 2 if big else 1),))
    reach_street(level, outside_of(b))


def guard_upstairs(key: tuple, site, rng: random.Random) -> Level:
    """Over the guardhouse: the sergeant's quarters (a bed, a desk, a chest, a hearth) and,
    through a door, the armoury, its walls lined with weapon racks. The sergeant keeps to it."""
    from .people import Actor, person_name
    w, h = GUARDHOUSE
    t = np.full((w, h), T.STONE_WALL, np.uint8)
    t[1: w - 1, 1: h - 1] = T.WOOD_FLOOR
    mid = w // 2
    t[mid, 1: h - 1] = T.STONE_WALL                  # the wall between the two rooms
    t[mid, h // 2] = T.DOOR
    t[1, h // 2] = T.STAIRS_DOWN
    t[1, 1], t[mid - 1, 1], t[3, h - 2] = T.BED, T.HEARTH, T.CHEST
    t[mid - 3, h // 2], t[mid - 2, h - 2] = T.TABLE, T.BARREL
    for x in range(mid + 1, w - 1):                  # the armoury: racks along both long walls
        for y in (1, h - 2):
            if (x - mid) % 2:
                t[x, y] = T.RACK
    t[w - 2, h // 2], t[w - 3, h // 2] = T.CHEST, T.TABLE
    name = f"Upstairs in the guardhouse of {site.name}" if site is not None else "Upstairs in the guardhouse"
    level = Level(key, name, t, {(1, h // 2): ("region", key[1], key[2])}, indoor_air=17.0)
    room = [(x, y) for x in range(1, mid) for y in range(1, h - 1) if T.WALK[t[x, y]]]
    armoury = [(x, y) for x in range(mid + 1, w - 1) for y in range(1, h - 1) if T.WALK[t[x, y]]]
    bedside = [c for c in room if abs(c[0] - 1) + abs(c[1] - 1) == 1]
    level.actors.append(Actor("sergeant", person_name(rng, set()), mid - 4, h // 2, home=bedside or room,
                              work=room + armoury, evening=room))
    return level


def guard_lockup(key: tuple, site, rng: random.Random) -> Level:
    """Under the guardhouse: a passage, barred cells along one side for the thieves the watch
    brings in, and the stores (barrels, a rack) along the other. A turnkey keeps the passage."""
    from .people import Actor, person_name
    w, h = GUARDHOUSE
    t = np.full((w, h), T.STONE_WALL, np.uint8)
    cy = h // 2
    t[1: w - 1, cy: h - 2] = T.STONE_FLOOR           # the passage
    t[1: w - 1, h - 2] = T.STONE_FLOOR               # the stores along the far wall
    cells = []
    for x0 in range(3, w - 4, 4):                    # cells off the passage, behind bars
        t[x0: x0 + 3, 1: cy - 1] = T.STONE_FLOOR
        t[x0: x0 + 3, cy - 1] = T.BARS
        t[x0, 1] = T.BEDROLL
        cells.append([(x, y) for x in range(x0, x0 + 3) for y in range(1, cy - 1) if T.WALK[t[x, y]]])
    for x in range(3, w - 2, 2):
        t[x, h - 2] = T.BARREL
    t[w - 2, h - 2] = T.RACK
    t[2, cy - 1] = T.TORCH
    t[1, cy] = T.STAIRS_UP
    name = f"The lockup under the guardhouse of {site.name}" if site is not None else "The guardhouse lockup"
    level = Level(key, name, t, {(1, cy): ("region", key[1], key[2])}, underground=True, indoor_air=11.0)
    used: set = set()
    passage = [(x, y) for x in range(2, w - 1) for y in range(cy, h - 2) if T.WALK[t[x, y]]]
    level.actors.append(Actor("gaoler", person_name(rng, used), 3, cy, home=passage, work=passage, evening=passage))
    for cell in rng.sample(cells, rng.randint(0, min(2, len(cells)))):
        x, y = rng.choice(cell)
        level.actors.append(Actor("prisoner", person_name(rng, used), x, y, home=cell, work=cell, evening=cell))
    return level


def outside_of(b: Building) -> tuple[int, int]:
    x0, y0, x1, y1 = box_of(b)
    dx, dy = b.door
    return (dx + (dx == x1) - (dx == x0), dy + (dy == y1) - (dy == y0))


def crossings(level: Level, xs: list, ys: list) -> None:
    """Where the streets cross: a guard's post at each of the nearest few to the square."""
    t = level.tiles
    cx, cy = level.width // 2, level.height // 2
    points = [(cx, y) for y in ys] + [(x, cy) for x in xs]
    points.sort(key=lambda p: (p[0] - cx) ** 2 + (2 * (p[1] - cy)) ** 2)
    n = 0
    for px, py in points:
        if abs(px - cx) < 12 and abs(py - cy) < 6:
            continue                    # the square has its own watch
        tiles = [(x, y) for x in range(px - 3, px + 4) for y in range(py - 2, py + 3)
                 if level.in_bounds(x, y) and t[x, y] in (T.STREET, T.BRIDGE)]
        if len(tiles) >= 6:
            level.places.append(Place("crossing", "the crossing", tiles))
            n += 1
            if n >= CROSSINGS:
                return


# ----------------------------------------------------------------- landmarks

def temple(level: Level, rng: random.Random, at) -> None:
    box = plot(level, 17, 11, at)
    if box is None:
        return
    god = rng.choice(GODS)
    b = raise_hall(level, rng, *box, 17, 11, (level.width // 2, level.height // 2), "temple", f"the temple of {god}")
    at_, depth, width, aisle = frame(b)
    put(level, b, at_(depth, aisle), T.ALTAR)
    for v in (aisle - 3, aisle + 3):
        put(level, b, at_(depth, v), T.HEARTH)        # braziers either side of the altar
    pews(level, b, 3, depth - 3)
    reach_street(level, outside_of(b))


def chapel(level: Level, rng: random.Random, at) -> None:
    """A small stone chapel (a part of the city without the temple has one): an altar and a few
    rows of pews."""
    box = plot(level, 13, 9, at)
    if box is None:
        return
    god = rng.choice(GODS)
    b = raise_hall(level, rng, *box, 13, 9, (level.width // 2, level.height // 2), "chapel", f"the chapel of {god}")
    at_, depth, width, aisle = frame(b)
    put(level, b, at_(depth, aisle), T.ALTAR)
    pews(level, b, 3, depth - 2)
    reach_street(level, outside_of(b))


def playhouse(level: Level, rng: random.Random, at) -> None:
    box = plot(level, 19, 11, at)
    if box is None:
        return
    b = raise_hall(level, rng, *box, 19, 11, (level.width // 2, level.height // 2), "playhouse", "the playhouse",
                   floor=T.WOOD_FLOOR)
    t = level.tiles
    at_, depth, width, aisle = frame(b)
    for u in range(depth - 2, depth + 1):
        for v in range(1, width + 1):
            t[at_(u, v)] = T.STAGE
    pews(level, b, 3, depth - 4)
    reach_street(level, outside_of(b))


def guildhall(level: Level, rng: random.Random, at) -> None:
    box = plot(level, 16, 9, at)
    if box is None:
        return
    b = raise_hall(level, rng, *box, 16, 9, (level.width // 2, level.height // 2), "guildhall",
                   f"the {rng.choice(['Merchants', 'Weavers', 'Masons', 'Vintners'])}' Guildhall")
    furnish(level, rng, *box, 16, 9, beds=0, hearth=True, tables=3, barrels=2, extra=((T.CHEST, 2),))
    reach_street(level, outside_of(b))


def alchemist(level: Level, rng: random.Random, at) -> None:
    box = plot(level, 9, 7, at)
    if box is None:
        return
    b = raise_hall(level, rng, *box, 9, 7, (level.width // 2, level.height // 2), "alchemist", "the alchemist's")
    furnish(level, rng, *box, 9, 7, beds=0, hearth=True, tables=1, barrels=2,
            extra=((T.BOOKSHELF, 2), (T.CHEST, 1)), middle=T.COUNTER)
    reach_street(level, outside_of(b))


def gallows(level: Level, rng: random.Random, at) -> None:
    """An open yard of flagstones: the gallows up on a platform, and a row of stocks."""
    box = plot(level, 19, 9, at)
    if box is None:
        return
    x0, y0 = box
    t = level.tiles
    t[x0: x0 + 19, y0: y0 + 9] = T.FLAGSTONES
    mx = x0 + 9
    t[mx - 3: mx + 4, y0 + 1: y0 + 3] = T.STAGE
    t[mx - 2, y0 + 1] = t[mx + 2, y0 + 1] = T.GALLOWS
    for x in (x0 + 2, x0 + 4, x0 + 14, x0 + 16):
        t[x, y0 + 7] = T.STOCKS
    yard = [(x, y) for x in range(x0, x0 + 19) for y in range(y0 + 3, y0 + 9) if T.WALK[t[x, y]]]
    level.places.append(Place("gallows", "the gallows yard", yard))
    reach_street(level, (mx, y0 + 8))


def pit(level: Level, rng: random.Random, at) -> None:
    """A fighting pit: a ring of fence round trodden sand, a gap each end, and room to watch."""
    box = plot(level, 23, 11, at)
    if box is None:
        return
    x0, y0 = box
    t = level.tiles
    cx, cy = x0 + 11, y0 + 5
    ring, inside, around = [], [], []
    for x in range(x0, x0 + 23):
        for y in range(y0, y0 + 11):
            d = ((x - cx) / 8.5) ** 2 + ((y - cy) / 3.6) ** 2
            if d <= 0.75:
                t[x, y] = T.SAND
                inside.append((x, y))
            elif d <= 1.15:
                ring.append((x, y))
            else:
                t[x, y] = T.DIRT
                around.append((x, y))
    for c in ring:
        t[c] = T.FENCE if abs(c[1] - cy) > 0 else T.DIRT        # a way in at each end
        if t[c] == T.DIRT:
            around.append(c)
    level.places.append(Place("pit", "the fighting pit", inside))
    level.places.append(Place("pitside", "the pit's edge", around))
    reach_street(level, (x0 + 11, y0 + 10))


# ----------------------------------------------------------------- the city garden

def garden(level: Level, rng: random.Random) -> None:
    """Just inside one of the city's gates: a hedge round four flower beds, gravel walks
    crossing at a fountain, benches along them, and a tree in each corner."""
    gates = [p for p in level.places if p.kind == "gate"]
    if not gates:
        return
    cx, cy = level.width // 2, level.height // 2
    def centre(p):
        return (sum(x for x, _ in p.tiles) / len(p.tiles), sum(y for _, y in p.tiles) / len(p.tiles))
    gx, gy = min((centre(p) for p in gates), key=lambda c: abs(c[0] - cx) + abs(c[1] - cy) * 2)
    tx, ty = gx + (cx - gx) * 0.35, gy + (cy - gy) * 0.35        # a little way in from the gate
    w, h = GARDEN
    box = plot(level, w, h, (tx, ty))
    if box is None:
        return
    x0, y0 = box
    t = level.tiles
    x1, y1 = x0 + w - 1, y0 + h - 1
    mx, my = x0 + w // 2, y0 + h // 2
    t[x0: x1 + 1, y0: y1 + 1] = T.GRASS
    t[x0: x1 + 1, y0] = t[x0: x1 + 1, y1] = T.BUSH
    t[x0, y0: y1 + 1] = t[x1, y0: y1 + 1] = T.BUSH
    t[mx - 1: mx + 2, y0 + 1: y1] = T.PATH                   # the walks, and the ways in
    t[x0 + 1: x1, my] = T.PATH
    for c in ((mx, y0), (mx, y1), (x0, my), (x1, my)):
        t[c] = T.PATH
    for x in range(x0 + 2, x1 - 1):
        for y in range(y0 + 2, y1 - 1):
            if t[x, y] == T.GRASS and abs(x - mx) > 2 and abs(y - my) > 1 and (x + y) % 3:
                t[x, y] = T.FLOWERS
    t[mx, my] = T.FOUNTAIN
    for x in (mx - 4, mx + 4):
        for y in (my - 1, my + 1):
            if t[x, y] == T.PATH:
                t[x, y] = T.BENCH
    for c in ((x0 + 2, y0 + 2), (x1 - 2, y0 + 2), (x0 + 2, y1 - 2), (x1 - 2, y1 - 2)):
        t[c] = T.TREE
    walks = [(x, y) for x in range(x0 + 1, x1) for y in range(y0 + 1, y1) if t[x, y] in (T.PATH, T.BENCH, T.GRASS)]
    level.places.append(Place("garden", "the city garden", walks))
    for c in ((mx, y1 + 1), (mx, y0 - 1), (x0 - 1, my), (x1 + 1, my)):
        if level.in_bounds(*c):
            reach_street(level, c)


# ----------------------------------------------------------------- trees

def tree_kind(level: Level) -> int:
    """The trees that grow here: the commonest trunk on the map, broadleaf if there are none."""
    counts = {k: int((level.tiles == k).sum()) for k in (T.TREE, T.PINE, T.JUNGLE_TREE)}
    best = max(counts, key=counts.get)
    return best if counts[best] else T.TREE


def plant_trees(level: Level, rng: random.Random, bounds, kind: int, banks=None) -> None:
    """Trees for looks: an avenue along the main streets (clear of the square, the doors and the
    stalls), trees on the banks of open water, and a scattering out beyond the walls."""
    t = level.tiles
    cx, cy = level.width // 2, level.height // 2
    x0, y0, x1, y1 = bounds
    def clear(x, y):
        if not level.in_bounds(x, y) or t[x, y] not in (T.GRASS, T.DIRT, T.STUMP, T.DRY_GRASS):
            return False
        return not any(t[x + dx, y + dy] in (T.DOOR, T.STALL, T.PATH, T.TREE, T.PINE, T.JUNGLE_TREE)
                       for dx in (-2, -1, 0, 1, 2) for dy in (-1, 0, 1) if level.in_bounds(x + dx, y + dy))
    for y in range(y0 + 3, y1 - 2, AVENUE // 2 + 1):
        for x in (cx - 3, cx + 2):
            if abs(y - cy) > 6 and clear(x, y):
                t[x, y] = kind
    for x in range(x0 + 4, x1 - 3, AVENUE):
        for y in (cy - 2, cy + 2):
            if abs(x - cx) > 13 and clear(x, y):
                t[x, y] = kind
    if banks is not None:
        for x, y in np.argwhere(banks):
            if x0 < x < x1 and y0 < y < y1 and rng.random() < BANK_TREES and clear(int(x), int(y)):
                t[x, y] = kind
    outside = np.ones(t.shape, bool)
    outside[max(0, x0 - 8): x1 + 9, max(0, y0 - 5): y1 + 6] = False
    for x, y in np.argwhere(outside & np.isin(t, [T.GRASS, T.DRY_GRASS, T.STUMP])):
        if rng.random() < OUTSIDE_TREES and clear(int(x), int(y)):
            t[x, y] = kind


# ----------------------------------------------------------------- the keep

def build_keep(level: Level, site, rng: random.Random, bounds, part: tuple[int, int]) -> None:
    """The keep, in this part's quarter toward the middle of the city, its gate facing the
    square."""
    t = level.tiles
    x0b, y0b, x1b, y1b = bounds
    cx, cy = level.width // 2, level.height // 2
    sx = 1 if part[0] < site.span[0] - 1 else -1
    sy = 1 if part[1] < site.span[1] - 1 else -1
    best = None
    off = getattr(level, "_keep_off", None)
    for dx in range(40, 81, 8):
        for dy in range(28, 65, 6):
            kx, ky = cx + sx * dx, cy + sy * dy
            ax, ay = kx - KEEP_W // 2, ky - KEEP_H // 2
            if ax < x0b + 6 or ay < y0b + 4 or ax + KEEP_W > x1b - 6 or ay + KEEP_H > y1b - 4:
                continue
            if ax <= cx + 1 <= ax + KEEP_W or ay <= cy <= ay + KEEP_H:
                continue                       # not over the main streets
            box = (slice(ax, ax + KEEP_W), slice(ay, ay + KEEP_H))
            wet = int(T.WATERY[t[box]].sum()) * 4 + (int(off[box].sum()) if off is not None else 0)
            score = (wet, abs(dx - 64) + abs(dy - 52))
            if best is None or score < best[0]:
                best = (score, ax, ay)
    if best is None:
        return
    _, ax, ay = best
    gate_low = ay + KEEP_H // 2 < cy          # the square's below: the gate's in the bottom wall
    def at(x, y):                             # keep coordinates (gate at the bottom) to the map's
        return ax + x, ay + (y if gate_low else KEEP_H - 1 - y)
    def box(x, y, w, h):
        return (ax + x, ay + y if gate_low else ay + KEEP_H - y - h, w, h)
    t[ax: ax + KEEP_W, ay: ay + KEEP_H] = T.FLAGSTONES
    t[ax: ax + KEEP_W, ay] = t[ax: ax + KEEP_W, ay + KEEP_H - 1] = T.STONE_WALL
    t[ax, ay: ay + KEEP_H] = t[ax + KEEP_W - 1, ay: ay + KEEP_H] = T.STONE_WALL
    for x, y in ((ax, ay), (ax + KEEP_W - 1, ay), (ax, ay + KEEP_H - 1), (ax + KEEP_W - 1, ay + KEEP_H - 1)):
        t[x - 2: x + 3, y - 1: y + 2] = T.BATTLEMENT
    mid = KEEP_W // 2
    for x in (mid - 1, mid, mid + 1):
        t[at(x, KEEP_H - 1)] = T.FLAGSTONES
    t[at(mid - 2, KEEP_H - 1)] = t[at(mid + 2, KEEP_H - 1)] = T.TORCH
    out = at(mid, KEEP_H)
    reach_street(level, out)
    court = at(mid, 16)
    rng2 = random.Random(rng.random())
    def raise_(x, y, w, h, kind, name, floor=T.STONE_FLOOR):
        bx, by, bw, bh = box(x, y, w, h)
        return raise_hall(level, rng2, bx, by, bw, bh, (bx + bw // 2, court[1]), kind, name, floor)
    throne = raise_(2, 2, 24, 10, "throne room", "the throne room")
    a, depth, width, aisle = frame(throne)
    for u in range(1, depth):
        t[a(u, aisle)] = T.CARPET
    put(level, throne, a(depth, aisle), T.THRONE)
    for v in (aisle - 3, aisle + 3):
        put(level, throne, a(depth, v), T.HEARTH)
    for u in range(2, depth - 1, 3):
        for v in (1, width):
            put(level, throne, a(u, v), T.STATUE)
    hall = raise_(27, 2, 26, 10, "great hall", "the great hall")
    a, depth, width, aisle = frame(hall)
    for v in (aisle - 3, aisle + 3):
        for u in range(3, depth - 1):
            put(level, hall, a(u, v), T.TABLE)
        for u in range(3, depth - 1):
            for side in (-1, 1):
                if t[a(u, v + side)] == T.STONE_FLOOR:
                    t[a(u, v + side)] = T.BENCH
    for v in range(aisle - 2, aisle + 3):
        put(level, hall, a(depth, v), T.TABLE)           # the high table
    for v in (1, width):
        put(level, hall, a(depth // 2, v), T.HEARTH)
    raise_(55, 2, 23, 10, "royal chambers", "the royal chambers", T.CARPET)
    bx, by, bw, bh = box(55, 2, 23, 10)
    furnish(level, rng2, bx, by, bw, bh, beds=2, hearth=True, tables=2, barrels=0,
            extra=((T.CHEST, 2), (T.STATUE, 1), (T.BOOKSHELF, 2)))
    raise_(2, 21, 22, 9, "barracks", "the keep's barracks")
    bx, by, bw, bh = box(2, 21, 22, 9)
    furnish(level, rng2, bx, by, bw, bh, beds=10, hearth=True, tables=2, barrels=1, extra=((T.RACK, 3), (T.CHEST, 1)))
    raise_(54, 21, 15, 9, "library", "the library")
    bx, by, bw, bh = box(54, 21, 15, 9)
    shelves = (bw - 2) * 2 + (bh - 2) * 2 - 4
    furnish(level, rng2, bx, by, bw, bh, beds=0, hearth=False, tables=2, barrels=0, extra=((T.BOOKSHELF, shelves),))
    gaol = raise_(70, 21, 8, 9, "gaol", "the gaol")
    a, depth, width, aisle = frame(gaol)
    down = a(depth, width)
    t[down] = T.STAIRS_DOWN
    level.exits[down] = ("dungeon", *level.region, 1)
    put(level, gaol, a(2, 1), T.TABLE)
    put(level, gaol, a(depth, 1), T.RACK)
    # the yard: a well, gardens, the guards' butts
    t[court] = T.WELL
    for x in list(range(28, 36)) + list(range(45, 53)):
        for y in (14, 18):
            c = at(x, y)
            if t[c] == T.FLAGSTONES and (x + y) % 2:
                t[c] = T.BUSH
    for x in range(27, 34, 3):
        t[at(x, 30)] = T.TARGET
    yard = [at(x, y) for x in range(1, KEEP_W - 1) for y in range(12, KEEP_H - 1)
            if t[at(x, y)] == T.FLAGSTONES and not level.building_at(*at(x, y))]
    level.places.append(Place("keep", f"the keep of {site.name}", yard))
    level.places.append(Place("keep gate", "the keep gate",
                              [at(x, y) for x in range(mid - 4, mid + 5) for y in range(KEEP_H - 5, KEEP_H - 1)
                               if t[at(x, y)] == T.FLAGSTONES]))


# ----------------------------------------------------------------- the dungeon

CELLS = 5                        # barred cells along each side of the dungeon's passage


def dungeon_level(key: tuple, site, rng: random.Random) -> Level:
    """Under the gaol: a passage between two rows of barred cells, torches on the walls, and the
    stairs up at one end. A few of the cells are occupied, and the gaoler keeps the passage."""
    from .people import Actor, person_name
    w, h = 4 + CELLS * 5, 11
    tiles = np.full((w, h), T.STONE_WALL, np.uint8)
    cy = h // 2
    tiles[1: w - 1, cy - 1: cy + 2] = T.STONE_FLOOR
    cells = []
    for i in range(CELLS):
        x0 = 3 + i * 5
        for ya, yb, bars_y in ((1, cy - 2, cy - 2), (cy + 3, h - 1, cy + 2)):
            tiles[x0: x0 + 4, ya: yb] = T.STONE_FLOOR
            tiles[x0: x0 + 4, bars_y] = T.BARS
            far = ya if bars_y == cy - 2 else yb - 1
            tiles[x0, far] = T.BEDROLL
            cells.append([(x, y) for x in range(x0, x0 + 4) for y in range(ya, yb) if T.WALK[tiles[x, y]]])
    for i in range(CELLS):                    # torches on the walls between the cells
        tiles[3 + i * 5 + 4, cy - 2] = T.TORCH
    tiles[1, cy] = T.STAIRS_UP
    name = f"The dungeon under {site.name}" if site is not None else "The dungeon"
    level = Level(key, name, tiles, {(1, cy): ("region", key[1], key[2])}, underground=True, indoor_air=11.0)
    used: set = set()
    passage = [(x, y) for x in range(3, w - 1) for y in range(cy - 1, cy + 2)]
    keeper = person_name(rng, used)
    level.actors.append(Actor("gaoler", keeper, 4, cy, home=passage, work=passage, evening=passage))
    for cell in rng.sample(cells, rng.randint(3, 6)):
        x, y = rng.choice(cell)
        level.actors.append(Actor("prisoner", person_name(rng, used), x, y, home=cell, work=cell, evening=cell))
    return level
