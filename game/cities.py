"""Stone cities, forts, and the woods cleared round a settlement.

A city spans 2 x 2 regions (worldgen.CITY_SPAN). Each of its regions is built on its own, but
from a plan that only depends on where the region sits in the city, so the parts meet without a
seam:

- a curtain wall of stone runs round the outside of the whole city, set in from its edge, with a
  tower at each corner and gates where the roads come in and halfway along each part's side
- broad streets run along every border between its parts, and through each part's middle both
  ways, with lesser streets every so often between them; rivers are bridged
- the blocks between the streets are packed with stone houses, each with its door to the
  street, and a market square in each part's middle
- the trades are shared out between the parts: two inns, an armourer, a baker, a butcher and
  a blacksmith's, and guards at the gates, archers on the walls

A fort stands on high ground over a highway: a square stone curtain wall with towers at the
corners and one gate toward the road, and inside a barracks, a smithy with a forge and an
anvil, a store of weapons, a well, and archery butts along a wall. Guards keep the gate,
archers watch from the walls, and the blacksmith works the forge (and sells what's made).

Half the towns and villages (and every city and fort) have felled the woods around them long
ago: the trees within a few dozen tiles are stumps and open grass.
"""
from __future__ import annotations

import random

import numpy as np

from . import tiles as T
from . import trees
from .level import Place
from .structures import (EDGE, building, connect, furnish, hang_torch, inn_building, middle, shop, square, ways)

INSET_X, INSET_Y = 10, 6     # the city wall's distance in from the city's outer edge
SEAM = 2                     # half the width of the street along a border between parts
STREET_EVERY = (40, 18)      # tiles between the lesser streets, across and down
TRADES = [("inn", "armoury"), ("bakery", "smithy"), ("butcher", "inn"), ("smithy", "armoury")]   # by part
FORT = (27, 12)              # the fort's half-width and half-height inside its wall


# ----------------------------------------------------------------- clearing

def clear_woods(level, rng: random.Random, reach: int, centre=None) -> None:
    """Trees within `reach` columns of the middle felled: some stumps, the rest grassed over."""
    cx, cy = centre or middle(level)
    t = level.tiles
    xs, ys = np.ogrid[: level.width, : level.height]
    near = (xs - cx) ** 2 + (2 * (ys - cy)) ** 2 <= reach * reach
    trunks = near & np.isin(t, list(trees.TRUNKS))
    stumps = trunks & (np.array([[rng.random() for _ in range(level.height)] for _ in range(level.width)]) < 0.3)
    t[trunks] = T.GRASS
    t[stumps] = T.STUMP
    t[near & (t == T.BUSH)] = T.GRASS


# ----------------------------------------------------------------- the city

def lay(t: np.ndarray, xs: slice, ys: slice, tile: int = T.STREET) -> None:
    """A street over a block of tiles: paving the land, bridging shallow water."""
    area = t[xs, ys]
    area[T.CLEARABLE[area] | np.isin(area, [T.ROAD, T.PATH, T.DUG])] = tile
    area[area == T.WATER] = T.BRIDGE
    t[xs, ys] = area


def city_bounds(level, site) -> tuple[int, int, int, int]:
    """(x0, y0, x1, y1), inclusive: the part of this region inside the city wall."""
    px, py = site.part(*level.region)
    sw, sh = site.span
    w, h = level.width, level.height
    return (INSET_X if px == 0 else 0, INSET_Y if py == 0 else 0,
            w - 1 - INSET_X if px == sw - 1 else w - 1, h - 1 - INSET_Y if py == sh - 1 else h - 1)


def build_city(level, site, rng: random.Random, land=None) -> None:
    px, py = site.part(*level.region)
    sw, sh = site.span
    t = level.tiles
    w, h = level.width, level.height
    x0, y0, x1, y1 = city_bounds(level, site)
    clear_woods(level, rng, 400)
    inside = np.zeros(t.shape, bool)
    inside[x0: x1 + 1, y0: y1 + 1] = True
    t[inside & np.isin(t, [T.TALL_GRASS, T.REEDS, T.BOULDER, T.ROCK, T.SCREE, T.SNOW])] = T.GRASS
    # streets: along the seams with the other parts, through the middle, and every so often
    cx, cy = w // 2, h // 2
    if px > 0:
        lay(t, slice(0, SEAM), slice(y0 + 1, y1))
    if px < sw - 1:
        lay(t, slice(w - SEAM, w), slice(y0 + 1, y1))
    if py > 0:
        lay(t, slice(x0 + 1, x1), slice(0, SEAM // 2 + 1))
    if py < sh - 1:
        lay(t, slice(x0 + 1, x1), slice(h - SEAM // 2 - 1, h))
    lay(t, slice(cx - 1, cx + 1), slice(y0, y1 + 1))
    lay(t, slice(x0, x1 + 1), slice(cy, cy + 1))
    for x in range(cx % STREET_EVERY[0], w, STREET_EVERY[0]):
        if x0 + 6 < x < x1 - 6 and abs(x - cx) > 8:
            lay(t, slice(x, x + 2), slice(y0 + 1, y1))
    for y in range(cy % STREET_EVERY[1], h, STREET_EVERY[1]):
        if y0 + 4 < y < y1 - 4 and abs(y - cy) > 4:
            lay(t, slice(x0 + 1, x1), slice(y, y + 1))
    walls(level, site, rng, (x0, y0, x1, y1))
    # the market, the trades, then houses wherever they'll go
    square(level, 9, 4, stalls=8)
    doors = []
    for trade in TRADES[(py * sw + px) % len(TRADES)]:
        if trade == "inn":
            doors.append(inn_building(level, rng, (12, 30)))
        elif trade == "smithy":
            doors.append(smithy(level, rng, (12, 34)))
        else:
            name = {"armoury": "the armourer's", "bakery": "the bakery", "butcher": "the butcher's"}[trade]
            doors.append(shop(level, rng, trade, name, (12, 34)))
    for d in doors:
        if d is not None:
            connect(level, d, ways(level), T.STREET)
    fill_blocks(level, rng, (x0, y0, x1, y1))


def walls(level, site, rng: random.Random, bounds) -> None:
    """The curtain wall along this part's outer sides, corner towers, and gates: where the roads
    come through, and in the middle of each side."""
    px, py = site.part(*level.region)
    sw, sh = site.span
    x0, y0, x1, y1 = bounds
    t = level.tiles
    w, h = level.width, level.height
    sides = []
    if px == 0:
        sides.append(("x", x0, y0, y1))
    if px == sw - 1:
        sides.append(("x", x1, y0, y1))
    if py == 0:
        sides.append(("y", y0, x0, x1))
    if py == sh - 1:
        sides.append(("y", y1, x0, x1))
    gates = []
    for axis, at, lo, hi in sides:
        line = [(at, k) if axis == "x" else (k, at) for k in range(lo, hi + 1)]
        middle_k = (h // 2) if axis == "x" else (w // 2)
        for c in line:
            k = c[1] if axis == "x" else c[0]
            here = t[c]
            if here in (T.ROAD, T.BRIDGE, T.STREET) or abs(k - middle_k) <= 1:
                if here != T.BRIDGE:
                    t[c] = T.STREET
                gates.append(c)
            elif here not in (T.WATER, T.DEEP_WATER):
                t[c] = T.STONE_WALL
        # a road straight out through the middle gate
        out = (-1 if at in (x0, y0) else 1)
        for step in range(1, 12):
            c = (at + out * step, middle_k) if axis == "x" else (middle_k, at + out * step)
            if level.in_bounds(*c) and T.CLEARABLE[t[c]]:
                t[c] = T.ROAD
    for x in ((x0,) if px == 0 else ()) + ((x1,) if px == sw - 1 else ()):
        for y in ((y0,) if py == 0 else ()) + ((y1,) if py == sh - 1 else ()):
            for dx in range(-2, 3):
                for dy in range(-1, 2):
                    if level.in_bounds(x + dx, y + dy) and t[x + dx, y + dy] not in (T.WATER, T.DEEP_WATER):
                        t[x + dx, y + dy] = T.BATTLEMENT
    # gatehouses: torches by the middle gates, and the guards' post just inside
    groups = {}
    for c in gates:
        groups.setdefault((c[0] in (x0, x1), c[0] if c[0] in (x0, x1) else c[1]), []).append(c)
    for (_, _), cells in groups.items():
        cells.sort()
        for run in runs(cells):
            mid = run[len(run) // 2]
            on_x = mid[0] in (x0, x1) and len(set(c[0] for c in run)) == 1
            inward = ((1 if mid[0] == x0 else -1), 0) if on_x else (0, (1 if mid[1] == y0 else -1))
            for end in (run[0], run[-1]):
                beyond = (end[0] + (0 if on_x else (-1 if end is run[0] else 1)),
                          end[1] + ((-1 if end is run[0] else 1) if on_x else 0))
                if level.in_bounds(*beyond) and t[beyond] == T.STONE_WALL:
                    t[beyond] = T.TORCH
            post = [(mid[0] + inward[0] * k + (dx if not on_x else 0), mid[1] + inward[1] * k + (dx if on_x else 0))
                    for k in range(1, 5) for dx in (-2, -1, 0, 1, 2)]
            post = [c for c in post if level.in_bounds(*c) and T.WALK[t[c]] and not T.WATERY[t[c]]]
            if post:
                level.places.append(Place("gate", "the city gate", post))
    # the archers walk inside the wall
    along = []
    for axis, at, lo, hi in sides:
        step = 1 if at in (x0, y0) else -1
        for k in range(lo + 3, hi - 2):
            c = (at + step, k) if axis == "x" else (k, at + step)
            if level.in_bounds(*c) and T.WALK[t[c]] and not T.WATERY[t[c]]:
                along.append(c)
    if along:
        level.places.append(Place("walls", "the city walls", along))


def runs(cells: list) -> list[list]:
    """Cells along one wall, split into runs of neighbours."""
    out, cur = [], []
    for c in cells:
        if cur and max(abs(c[0] - cur[-1][0]), abs(c[1] - cur[-1][1])) > 1:
            out.append(cur)
            cur = []
        cur.append(c)
    if cur:
        out.append(cur)
    return out


def fill_blocks(level, rng: random.Random, bounds) -> None:
    """Stone houses packed into the blocks between the streets, doors to the street."""
    x0, y0, x1, y1 = bounds
    t = level.tiles
    for y in range(max(y0 + 2, EDGE + 1), min(y1 - 1, level.height - EDGE - 1)):
        x = max(x0 + 2, EDGE + 1)
        while x < min(x1 - 1, level.width - EDGE - 1):
            w, h = rng.randint(7, 11), rng.randint(5, 7)
            if fits(level, x, y, w, h):
                street = nearest_street(level, x, y, w, h)
                door, outside = building(level, rng, x, y, w, h, street, wall=T.STONE_WALL, floor=T.STONE_FLOOR,
                                         torch=rng.random() < 0.25)
                chest = ((T.CHEST, 1),) if rng.random() < 0.7 else ()
                furnish(level, rng, x, y, w, h, beds=rng.randint(1, 2), tables=1, barrels=rng.randint(0, 1), extra=chest)
                step_out(level, outside, street)
                x += w + rng.randint(1, 2)
            else:
                x += 1


def step_out(level, start, street) -> None:
    """A few steps of paving from a door to the street beside it."""
    import tcod
    t = level.tiles
    for x, y in tcod.los.bresenham(start, street).tolist():
        if t[x, y] in (T.STREET, T.BRIDGE):
            return
        if T.CLEARABLE[t[x, y]] or t[x, y] == T.PATH:
            t[x, y] = T.STREET
        elif not T.WALK[t[x, y]]:
            return


def fits(level, x: int, y: int, w: int, h: int) -> bool:
    """A box clear of everything but grass and dirt, with a tile's margin, and touching a street
    within three tiles (so every house is on one)."""
    t = level.tiles
    if x - 1 < EDGE or y - 1 < EDGE or x + w >= level.width - EDGE or y + h >= level.height - EDGE:
        return False
    area = t[x - 1: x + w + 1, y - 1: y + h + 1]
    if not np.isin(area, [T.GRASS, T.DIRT, T.STUMP, T.DRY_GRASS, T.SAND, T.MUD]).all():
        return False
    near = t[max(0, x - 3): x + w + 3, max(0, y - 2): y + h + 2]
    return bool(np.isin(near, [T.STREET, T.BRIDGE]).any())


def nearest_street(level, x: int, y: int, w: int, h: int) -> tuple[int, int]:
    t = level.tiles
    best, far = (x + w // 2, y + h), 1e9
    for sx in range(max(0, x - 3), min(level.width, x + w + 3)):
        for sy in range(max(0, y - 2), min(level.height, y + h + 2)):
            if t[sx, sy] in (T.STREET, T.BRIDGE):
                d = (sx - x - w / 2) ** 2 + (2 * (sy - y - h / 2)) ** 2
                if d < far:
                    best, far = (sx, sy), d
    return best


def smithy(level, rng: random.Random, ring, centre=None):
    """A blacksmith's: a forge, an anvil, a rack of what's been made and a chest of stock."""
    from .structures import place_box
    box = (place_box(level, rng, ((9, 11), (6, 7)), ring, centre)
           or place_box(level, rng, ((8, 9), (5, 6)), (ring[0], ring[1] + 14), centre))
    if box is None:
        return None
    x0, y0, w, h = box
    door, outside = building(level, rng, x0, y0, w, h, centre or middle(level), wall=T.STONE_WALL,
                             floor=T.STONE_FLOOR, kind="smithy", name="the smithy")
    furnish(level, rng, x0, y0, w, h, beds=0, hearth=False, tables=0, barrels=1,
            extra=((T.FORGE, 1), (T.ANVIL, 1), (T.RACK, 2), (T.CHEST, 1)), middle=T.COUNTER)
    return outside


# ----------------------------------------------------------------- the fort

def build_fort(level, site, rng: random.Random, land=None) -> None:
    t = level.tiles
    cx, cy = middle(level)
    rx, ry = FORT
    clear_woods(level, rng, 60)
    xs, ys = np.ogrid[: level.width, : level.height]
    yard = (abs(xs - cx) <= rx + 4) & (abs(ys - cy) <= ry + 2)
    t[yard & ~T.WATERY[t]] = T.DIRT
    x0, y0, x1, y1 = cx - rx, cy - ry, cx + rx, cy + ry
    t[x0: x1 + 1, y0] = t[x0: x1 + 1, y1] = T.STONE_WALL
    t[x0, y0: y1 + 1] = t[x1, y0: y1 + 1] = T.STONE_WALL
    for x, y in ((x0, y0), (x1, y0), (x0, y1), (x1, y1)):          # corner towers
        t[x - 2: x + 3, y - 1: y + 2] = T.BATTLEMENT
    # the gate: on the side toward the nearest road (south if there's none)
    road = np.argwhere(np.isin(t, [T.ROAD, T.PATH]) & ~yard)
    side = (0, 1)
    if len(road):
        d = ((road[:, 0] - cx) ** 2 + (2 * (road[:, 1] - cy)) ** 2)
        rxy = road[int(np.argmin(d))]
        from .structures import facing
        side = facing(x0, y0, x1, y1, int(rxy[0]), int(rxy[1]))
    if side[0]:
        gx = x1 if side[0] > 0 else x0
        gate = [(gx, cy - 1), (gx, cy), (gx, cy + 1)]
        torches = [(gx, cy - 2), (gx, cy + 2)]
    else:
        gy = y1 if side[1] > 0 else y0
        gate = [(cx - 1, gy), (cx, gy), (cx + 1, gy)]
        torches = [(cx - 2, gy), (cx + 2, gy)]
    for c in gate:
        t[c] = T.FLAGSTONES
    for c in torches:
        t[c] = T.TORCH
    outside = (gate[1][0] + side[0], gate[1][1] + side[1])
    t[outside] = T.PATH
    connect(level, outside, ways(level) & ~yard)
    inner_x, inner_y = range(x0 + 1, x1), range(y0 + 1, y1)
    # inside: barracks along the far wall from the gate, the smithy, the stores, a well, the butts
    rng2 = random.Random(rng.random())
    far = (-side[0], -side[1])
    if far[1] or not far[0]:
        by = y0 + 1 if far[1] <= 0 else y1 - 7
        barracks = (cx - 12, by, 24, 7)
        smithy_box = (x0 + 2, cy - 3, 10, 7) if side != (-1, 0) else (x1 - 11, cy - 3, 10, 7)
        stores = (x1 - 10, cy - 3, 9, 6) if side != (1, 0) else (x0 + 2, cy - 3, 9, 6)
        butts = [(x, y1 - 2 if far[1] < 0 else y0 + 2) for x in range(cx - 10, cx + 11, 4)]
    else:
        bx = x0 + 1 if far[0] < 0 else x1 - 13
        barracks = (bx, cy - 5, 13, 11)
        smithy_box = (cx - 5, y0 + 1, 10, 7)
        stores = (cx - 4, y1 - 6, 9, 6)
        butts = [(x1 - 2 if far[0] < 0 else x0 + 2, y) for y in range(cy - 8, cy + 9, 4)]
    door_to = (cx, cy)
    building(level, rng2, *barracks, door_to, wall=T.STONE_WALL, floor=T.STONE_FLOOR, kind="barracks",
             name="the barracks")
    furnish(level, rng2, *barracks, beds=8, hearth=True, tables=2, barrels=1, extra=((T.CHEST, 1),))
    building(level, rng2, *smithy_box, door_to, wall=T.STONE_WALL, floor=T.STONE_FLOOR, kind="smithy",
             name="the smithy")
    furnish(level, rng2, *smithy_box, beds=0, hearth=False, tables=0, barrels=1,
            extra=((T.FORGE, 1), (T.ANVIL, 1), (T.RACK, 1)))
    building(level, rng2, *stores, door_to, wall=T.STONE_WALL, floor=T.STONE_FLOOR, kind="stores",
             name="the stores")
    furnish(level, rng2, *stores, beds=0, hearth=False, tables=0, barrels=3, extra=((T.RACK, 2), (T.CHEST, 1)))
    for c in butts:
        if level.in_bounds(*c) and t[c] == T.DIRT:
            t[c] = T.TARGET
    t[cx + 4, cy] = T.WELL
    # where the guards stand and the archers watch
    post = [(x, y) for x in range(gate[1][0] - 4, gate[1][0] + 5) for y in range(gate[1][1] - 3, gate[1][1] + 4)
            if level.in_bounds(x, y) and T.WALK[t[x, y]] and not T.ROOF[t[x, y]] and not T.WATERY[t[x, y]]]
    level.places.append(Place("gate", "the fort gate", post))
    along = [(x, y) for x in inner_x for y in inner_y
             if (x in (x0 + 1, x1 - 1) or y in (y0 + 1, y1 - 1)) and T.WALK[t[x, y]] and not T.ROOF[t[x, y]]]
    level.places.append(Place("walls", "the fort walls", along))
