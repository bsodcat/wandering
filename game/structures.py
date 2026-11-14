"""What people built, and what's under and above it.

Builders work on a region's local map after its land, rivers and roads are drawn. The roads
from the world map all lead into the middle of a settlement, so places grow outward from there:

- town:    a paved square with a well and market stalls, a named inn with a bar, a bakery,
           a butcher's and an armourer's (weapon racks: the shopkeeper's), a dozen or so houses with their doors facing the square, streets
           out to every door, vegetable gardens and a pasture outside, docks if it's on the
           coast, and a lumber camp if there are woods about
- village: a green with a well, a handful of houses, paths, fields of whatever grain suits
           the climate, a pasture or two, docks on the coast, a lumber camp in wooded country
- inn:     a large named inn by the road, a paddock with horses and a well

Every inn, in a town or by the road, has stairs up to a floor of guest rooms (a corridor, a
bed in each room; the barkeeper lets them for the night) and down to a cellar of barrels.
The beds are only up there: the common room downstairs has none.

No furniture is ever put down where it would shut part of a room off from its door.

Every building is kept on the level (kind, name, box, door), and so is every place someone
works or something grazes (fields, pastures, the pier, a fishing spot on the shore, the lumber
camp): game/people.py puts the townsfolk and their animals there.
- chests:  most houses keep one (household things and the tools of the owner's trade), each
           shop has one (its takings); caves hide gold and jewels in theirs, crypts strange
           things (game/items.py fills them when they're first opened)
- tower:   a round stone watchtower; stairs climb to a room and then the roof
- ruins:   tumbled stone buildings, overgrown, one with stairs down to a crypt
- cave:    a rocky outcrop with a way down into one to three cave levels

Nothing is built within EDGE tiles of the map's edge, so neighbouring regions still join up.
"""
from __future__ import annotations

import math
import random

import numpy as np
import tcod

from . import farming
from . import rooms
from . import tiles as T
from . import trees
from .level import Building, Level, Place

EDGE = 4
DIRS4 = [(1, 0), (-1, 0), (0, 1), (0, -1)]


# ----------------------------------------------------------------- helpers

def middle(level: Level) -> tuple[int, int]:
    return level.width // 2, level.height // 2


def box_ok(level: Level, x0: int, y0: int, x1: int, y1: int, margin: int = 1) -> bool:
    """Whether the box (inclusive) plus a margin is clear land, away from the edges."""
    if x0 - margin < EDGE or y0 - margin < EDGE or x1 + margin >= level.width - EDGE \
            or y1 + margin >= level.height - EDGE:
        return False
    area = level.tiles[x0 - margin: x1 + margin + 1, y0 - margin: y1 + margin + 1]
    return bool(T.CLEARABLE[area].all())


def facing(x0, y0, x1, y1, tx, ty) -> tuple[int, int]:
    """Which side of a box faces the point (tx, ty)."""
    dx, dy = tx - (x0 + x1) / 2, (ty - (y0 + y1) / 2) * 2   # a row is two columns tall on screen
    if abs(dx) > abs(dy):
        return (1, 0) if dx > 0 else (-1, 0)
    return (0, 1) if dy > 0 else (0, -1)


def building(level: Level, rng: random.Random, x0: int, y0: int, w: int, h: int, toward: tuple[int, int],
             wall: int = T.WALL, floor: int = T.WOOD_FLOOR, torch: bool = True, kind: str = "house",
             name: str = "a house", sign: bool = False) -> tuple[tuple[int, int], tuple[int, int]]:
    """Walls, a floor and a door on the side facing `toward`, with a torch on the wall beside it
    (and a sign on the other side, for an inn). Kept on the level as a Building.
    Returns (door, the tile outside it)."""
    x1, y1 = x0 + w - 1, y0 + h - 1
    t = level.tiles
    t[x0: x1 + 1, y0: y1 + 1] = wall
    t[x0 + 1: x1, y0 + 1: y1] = floor
    side = facing(x0, y0, x1, y1, *toward)
    if side[0]:
        dx = x1 if side[0] > 0 else x0
        door = (dx, rng.randint(y0 + 1, y1 - 1))
    else:
        dy = y1 if side[1] > 0 else y0
        door = (rng.randint(x0 + 1, x1 - 1), dy)
    t[door] = T.DOOR
    outside = (door[0] + side[0], door[1] + side[1])
    if T.CLEARABLE[t[outside]]:
        t[outside] = T.PATH
    if torch:
        hang_torch(level, rng, door, side, (x0, y0, x1, y1))
    if sign:                 # beside the door if the torch left room, else one further along
        hang_torch(level, rng, door, side, (x0, y0, x1, y1), T.SIGN, reach=(1, 2))
    level.buildings.append(Building(kind, name, x0, y0, w, h, door))
    return door, outside


def hang_torch(level: Level, rng: random.Random, door, side, box=None, tile: int = T.TORCH,
               reach=(1,)) -> None:
    """A torch (or a sign) on the wall beside a door, on one side or the other, never on a corner.
    `reach` is how far along the wall from the door it may go, nearest first."""
    t = level.tiles
    along = (0, 1) if side[0] else (1, 0)
    for r in reach:
        spots = [(door[0] + along[0] * k, door[1] + along[1] * k) for k in (-r, r)]
        if box is not None:
            x0, y0, x1, y1 = box
            spots = [(x, y) for x, y in spots if (y0 < y < y1 if side[0] else x0 < x < x1)]
        spots = [s for s in spots if level.in_bounds(*s) and t[s] in (T.WALL, T.STONE_WALL)]
        if spots:
            t[rng.choice(spots)] = tile
            return


def inside_door(t: np.ndarray, x0: int, y0: int, x1: int, y1: int) -> tuple[int, int] | None:
    """The floor tile just inside a building's door (box inclusive), or None if it has no door."""
    for x in range(x0, x1 + 1):
        for y in range(y0, y1 + 1):
            if (x in (x0, x1) or y in (y0, y1)) and t[x, y] == T.DOOR:
                return (x + (x == x0) - (x == x1), y + (y == y0) - (y == y1))
    return None


def all_reachable(t: np.ndarray, x0: int, y0: int, x1: int, y1: int) -> bool:
    """Whether every tile you can stand on inside the box (inclusive) can be reached from the
    door, stepping straight (not squeezing diagonally between two pieces of furniture)."""
    start = inside_door(t, x0, y0, x1, y1)
    walk = T.WALK[t[x0 + 1: x1, y0 + 1: y1]]
    if start is None:
        return True
    sx, sy = start[0] - x0 - 1, start[1] - y0 - 1
    if not walk[sx, sy]:
        return False
    seen = np.zeros(walk.shape, bool)
    seen[sx, sy] = True
    stack = [(sx, sy)]
    while stack:
        x, y = stack.pop()
        for dx, dy in DIRS4:
            nx, ny = x + dx, y + dy
            if 0 <= nx < walk.shape[0] and 0 <= ny < walk.shape[1] and walk[nx, ny] and not seen[nx, ny]:
                seen[nx, ny] = True
                stack.append((nx, ny))
    return bool((seen == walk).all())


def put_inside(t: np.ndarray, c: tuple[int, int], tile: int, box: tuple[int, int, int, int]) -> bool:
    """Puts a piece of furniture down unless it would wall off any part of the room from the
    door. Returns whether it went down."""
    old = t[c]
    t[c] = tile
    if T.WALK[tile] or all_reachable(t, *box):
        return True
    t[c] = old
    return False


def furnish(level: Level, rng: random.Random, x0: int, y0: int, w: int, h: int, beds: int = 1,
            hearth: bool = True, tables: int = 1, barrels: int = 0, extra=(), middle=T.TABLE) -> None:
    """Furniture against the inside walls, leaving the tiles by the door clear and never
    shutting anyone off from the door."""
    t = level.tiles
    box = (x0, y0, x0 + w - 1, y0 + h - 1)
    inside = [(x, y) for x in range(x0 + 1, x0 + w - 1) for y in range(y0 + 1, y0 + h - 1)]
    def by_door(x, y):
        return any(t[x + dx, y + dy] == T.DOOR for dx in (-1, 0, 1) for dy in (-1, 0, 1))
    walls = [c for c in inside if (c[0] in (x0 + 1, x0 + w - 2) or c[1] in (y0 + 1, y0 + h - 2))
             and not by_door(*c)]
    rng.shuffle(walls)
    for tile, count in ((T.HEARTH, int(hearth)), (T.BED, beds), (T.BARREL, barrels), *extra):
        for _ in range(count):
            while walls and not put_inside(t, walls.pop(), tile, box):
                pass
    middle_tiles = [c for c in inside if t[c] in (T.WOOD_FLOOR, T.STONE_FLOOR) and not by_door(*c)
                    and c[0] not in (x0 + 1, x0 + w - 2) and c[1] not in (y0 + 1, y0 + h - 2)]
    rng.shuffle(middle_tiles)
    for _ in range(tables):
        while middle_tiles and not put_inside(t, middle_tiles.pop(), middle, box):
            pass


def place_box(level: Level, rng: random.Random, sizes, ring, centre=None, tries: int = 200, margin: int = 1):
    """A random clear box at a distance in `ring` (in columns) from the centre."""
    cx, cy = centre or middle(level)
    for _ in range(tries):
        w, h = rng.randint(*sizes[0]), rng.randint(*sizes[1])
        angle, r = rng.uniform(0, 2 * math.pi), rng.uniform(*ring)
        x0 = int(cx + math.cos(angle) * r - w / 2)
        y0 = int(cy + math.sin(angle) * r / 2 - h / 2)
        if box_ok(level, x0, y0, x0 + w - 1, y0 + h - 1, margin):
            return x0, y0, w, h
    return None


def connect(level: Level, start: tuple[int, int], targets: np.ndarray, tile: int = T.PATH) -> None:
    """A path from `start` to the nearest target tile, over open ground where it can, through
    trees and shallow water if it must (they're cleared and bridged)."""
    t = level.tiles
    cost = np.where(T.WALK[t], 2, 0).astype(np.int32)
    cost[np.isin(t, [T.ROAD, T.STREET, T.PATH, T.BRIDGE])] = 1
    cost[np.isin(t, [T.TREE, T.PINE, T.JUNGLE_TREE, T.BOULDER, T.BUSH, T.TALL_GRASS])] = 4   # felled
    cost[t == T.WATER] = 8
    dist = tcod.path.maxarray(t.shape, dtype=np.int32)
    dist[targets & (cost > 0)] = 0
    if not (dist == 0).any() or cost[start] == 0:
        return
    tcod.path.dijkstra2d(dist, cost, 2, 3, out=dist)
    if dist[start] == np.iinfo(np.int32).max:
        return
    for x, y in tcod.path.hillclimb2d(dist, start, True, True).tolist():
        if t[x, y] == T.WATER:
            t[x, y] = T.BRIDGE
        elif T.CLEARABLE[t[x, y]]:
            t[x, y] = tile


def ways(level: Level) -> np.ndarray:
    return np.isin(level.tiles, [T.ROAD, T.STREET, T.BRIDGE, T.PATH])


def ellipse(level: Level, cx: int, cy: int, rx: float, ry: float) -> np.ndarray:
    xs, ys = np.ogrid[: level.width, : level.height]
    return ((xs - cx) / rx) ** 2 + ((ys - cy) / ry) ** 2 <= 1


# ----------------------------------------------------------------- pieces

def square(level: Level, rx: int, ry: int, stalls: int) -> None:
    """A paved square in the middle with a well, and stalls around its edge."""
    cx, cy = middle(level)
    t = level.tiles
    paved = ellipse(level, cx, cy, rx, ry) & (T.CLEARABLE[t] | (t == T.ROAD) | (t == T.PATH))
    t[paved] = T.STREET
    if t[cx, cy] == T.STREET:
        t[cx, cy] = T.WELL
    for i in range(stalls):
        angle = 2 * math.pi * (i + 0.5) / stalls
        x, y = round(cx + math.cos(angle) * (rx - 1)), round(cy + math.sin(angle) * (ry - 1))
        if t[x, y] == T.STREET and not any(t[x + dx, y + dy] in (T.ROAD, T.BRIDGE) for dx, dy in DIRS4):
            t[x, y] = T.STALL


def houses(level: Level, rng: random.Random, count: int, ring, sizes=((7, 10), (5, 7))) -> list:
    cx, cy = middle(level)
    doors = []
    for _ in range(count):
        box = place_box(level, rng, sizes, ring) or place_box(level, rng, sizes, (ring[0], ring[1] + 24))   # (a river in the way)
        if box is None:
            continue
        x0, y0, w, h = box
        door, outside = building(level, rng, x0, y0, w, h, (cx, cy))
        chest = ((T.CHEST, 1),) if rng.random() < 0.8 else ()
        furnish(level, rng, x0, y0, w, h, beds=rng.randint(1, 2), tables=1, barrels=rng.randint(0, 1), extra=chest)
        doors.append(outside)
    return doors


def fields(level: Level, rng: random.Random, count: int, ring, sizes=((8, 14), (4, 7)), crop: int = T.CROPS,
           kind: str = "field", animal: str = "") -> list:
    """Crops (or a pasture, with a trough) inside a fence, with a gate toward the middle. Each is
    kept as a Place. Returns the tiles outside the gates."""
    cx, cy = middle(level)
    gates = []
    t = level.tiles
    for _ in range(count):
        box = place_box(level, rng, sizes, ring, margin=1)
        if box is None:
            continue
        x0, y0, w, h = box
        x1, y1 = x0 + w - 1, y0 + h - 1
        t[x0: x1 + 1, y0: y1 + 1] = T.FENCE
        t[x0 + 1: x1, y0 + 1: y1] = crop
        side = facing(x0, y0, x1, y1, cx, cy)
        gate = ((x1 if side[0] > 0 else x0), (y0 + y1) // 2) if side[0] else ((x0 + x1) // 2, (y1 if side[1] > 0 else y0))
        t[gate] = T.PATH
        gates.append((gate[0] + side[0], gate[1] + side[1]))
        if kind == "pasture":     # a trough in the far corner from the gate
            t[x1 - 1 if gate[0] < (x0 + x1) / 2 else x0 + 1, y1 - 1 if gate[1] < (y0 + y1) / 2 else y0 + 1] = T.TROUGH
        inside = [(x, y) for x in range(x0 + 1, x1) for y in range(y0 + 1, y1) if T.WALK[t[x, y]]]
        name = f"a pasture of {farming.ANIMALS[animal].plural}" if kind == "pasture" else f"a field of {T.TILES[crop].name}"
        level.places.append(Place(kind, name, inside, animal))
    return gates


def pastures(level: Level, rng: random.Random, count: int, ring, animal: str) -> list:
    return fields(level, rng, count, ring, sizes=((8, 12), (4, 6)), crop=T.GRASS, kind="pasture", animal=animal)


def docks(level: Level, rng: random.Random) -> tuple[int, int] | None:
    """A pier out from the shore nearest the middle into open water, and a shed at its foot.
    Returns the tile at the foot of the pier."""
    t = level.tiles
    cx, cy = middle(level)
    best = None
    for x in range(EDGE, level.width - EDGE):
        for y in range(EDGE, level.height - EDGE):
            if not T.WALK[t[x, y]] or T.WATERY[t[x, y]] or not T.NATURAL[t[x, y]] and t[x, y] not in (T.ROAD, T.PATH):
                continue
            for dx, dy in DIRS4:
                run = 0
                while run < 12 and level.in_bounds(x + dx * (run + 1), y + dy * (run + 1)) \
                        and T.WATERY[t[x + dx * (run + 1), y + dy * (run + 1)]]:
                    run += 1
                if run >= 5:
                    d = (x - cx) ** 2 + (2 * (y - cy)) ** 2
                    if best is None or d < best[0]:
                        best = (d, x, y, dx, dy, run)
    if best is None:
        return None
    _, x, y, dx, dy, run = best
    length = min(run, 10 if dx else 6)
    end = []
    for i in range(1, length + 1):
        for side in (0, 1):
            px, py = x + dx * i + (side if dy else 0), y + dy * i + (side if dx else 0)
            if level.in_bounds(px, py) and T.WATERY[t[px, py]]:
                t[px, py] = T.DOCK
                if i >= length - 1:
                    end.append((px, py))
    if end:
        level.places.append(Place("pier", "the end of the pier", end))
    box = place_box(level, rng, ((4, 5), (3, 4)), (2, 8), centre=(x - dx * 4, y - dy * 3), tries=60)
    if box is not None:
        x0, y0, w, h = box
        building(level, rng, x0, y0, w, h, (x, y), kind="shed", name="a boat shed")
        furnish(level, rng, x0, y0, w, h, beds=0, hearth=False, tables=0, barrels=2)
    return x, y


def fishing_spot(level: Level) -> None:
    """Without a pier, a spot on the bank of the river, lake or sea nearest the middle."""
    if any(p.kind == "pier" for p in level.places):
        return
    t = level.tiles
    water = np.isin(t, [T.WATER, T.DEEP_WATER])
    p = np.pad(water, 1)
    beside = p[:-2, 1:-1] | p[2:, 1:-1] | p[1:-1, :-2] | p[1:-1, 2:]
    bank = beside & T.WALK[t] & ~T.WATERY[t] & ~T.ROOF[t]
    bank[: EDGE + 1], bank[-EDGE - 1:], bank[:, : EDGE + 1], bank[:, -EDGE - 1:] = False, False, False, False
    xs, ys = np.nonzero(bank)
    if not len(xs):
        return
    cx, cy = middle(level)
    d = (xs - cx) ** 2 + (2 * (ys - cy)) ** 2
    i = int(np.argmin(d))
    if d[i] > 40 ** 2:
        return
    x, y = int(xs[i]), int(ys[i])
    spot = [(x + dx, y + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if bank[x + dx, y + dy]]
    level.places.append(Place("shore", "a fishing spot on the bank", spot))


def lumber_camp(level: Level, rng: random.Random):
    """Where the woods are thickest, not too near the middle: a woodpile, stumps where trees
    have been felled, and room to work. Returns the tile to run a path from, or None if
    there aren't the woods for it."""
    t = level.tiles
    trunk = np.isin(t, trees.TRUNKS)
    if trunk.sum() < 15:
        return None
    w, h = t.shape
    p = np.pad(trunk, ((6, 6), (3, 3))).astype(np.int32)
    density = sum(p[6 + dx: w + 6 + dx, 3 + dy: h + 3 + dy] for dx in range(-6, 7) for dy in range(-3, 4))
    cx, cy = middle(level)
    xs, ys = np.ogrid[:w, :h]
    far = (xs - cx) ** 2 + (2 * (ys - cy)) ** 2
    ok = (T.CLEARABLE[t] & ~trunk & (far >= 14 ** 2))
    ok[: EDGE + 4], ok[-EDGE - 4:], ok[:, : EDGE + 3], ok[:, -EDGE - 3:] = False, False, False, False
    for dx in (1, 2):           # room for the woodpile beside it
        ok[:-dx] &= T.CLEARABLE[t[dx:]] & ~trunk[dx:]
    score = np.where(ok, density - np.sqrt(far) * 0.05, -1)
    x, y = (int(v) for v in np.unravel_index(int(np.argmax(score)), score.shape))
    if score[x, y] < 6:
        return None
    t[x: x + 3, y] = T.WOODPILE
    near = [(int(a), int(b)) for a, b in zip(*np.nonzero(trunk))]
    near.sort(key=lambda c: (c[0] - x - 1) ** 2 + (2 * (c[1] - y)) ** 2)
    for c in near[: rng.randint(4, 7)]:
        t[c] = T.STUMP
    room = [(a, b) for a in range(x - 6, x + 9) for b in range(y - 3, y + 4)
            if level.in_bounds(a, b) and T.WALK[t[a, b]] and not T.WATERY[t[a, b]]
            and (a - x - 1) ** 2 + (2 * (b - y)) ** 2 <= 36]
    level.places.append(Place("camp", "a lumber camp", room))
    return (x + 1, y + 1) if T.WALK[t[x + 1, y + 1]] else (x + 1, y - 1)


# ----------------------------------------------------------------- the inn and the shops

INN_WORDS = (["Red", "Golden", "Laughing", "Sleeping", "Old", "Silver", "Drowned", "Green", "Wandering",
              "Crooked", "Merry", "Blue", "Black", "Lonely", "Jolly", "Whistling"],
             ["Stag", "Goose", "Lantern", "Anchor", "Plough", "Barrel", "Fox", "Bell", "Crown", "Boar",
              "Kettle", "Heron", "Wheel", "Tankard", "Owl", "Hart"])


def inn_name(rng: random.Random) -> str:
    return f"The {rng.choice(INN_WORDS[0])} {rng.choice(INN_WORDS[1])}"


def inn_building(level: Level, rng: random.Random, ring, sizes=((13, 15), (7, 8))):
    """A big common room: a bar along the wall across from the door with kegs at its ends, a
    hearth and benches by the side walls, tables in the middle, a sign and a torch by the door.
    The beds are all upstairs (inn_upstairs). Returns the tile outside the door, or None if it
    didn't fit."""
    box = (place_box(level, rng, sizes, ring)
           or place_box(level, rng, ((12, 13), (7, 7)), (ring[0], ring[1] + 12)))   # smaller, further out
    if box is None:
        return None
    x0, y0, w, h = box
    x1, y1 = x0 + w - 1, y0 + h - 1
    door, outside = building(level, rng, x0, y0, w, h, middle(level), kind="inn", name=inn_name(rng), sign=True)
    t = level.tiles
    inn_stairs(level, x0, y0, x1, y1, door)     # first, so the furniture keeps a way to them
    if door[0] in (x0, x1):              # door on a side wall: the bar runs down the far one
        bx = x0 + 1 if door[0] == x1 else x1 - 1
        mid = (y0 + y1) // 2
        bar = [(bx, y) for y in range(mid - 1, mid + 2)]
        kegs = [(bx, mid - 2), (bx, mid + 2)]
        sides = [(x, y) for x in range(x0 + 2, x1 - 1, 2) for y in (y0 + 1, y1 - 1)]
    else:                                # door on the top or bottom: the bar runs along the other
        by = y0 + 1 if door[1] == y1 else y1 - 1
        mid = (x0 + x1) // 2
        bar = [(x, by) for x in range(mid - 2, mid + 2)]
        kegs = [(mid - 3, by), (mid + 2, by)]
        sides = [(x, y) for x in (x0 + 1, x1 - 1) for y in range(y0 + 1, y1, 2)]
    def by_door(c):
        return abs(c[0] - door[0]) <= 1 and abs(c[1] - door[1]) <= 1
    box = (x0, y0, x1, y1)
    for c in bar:
        put_inside(t, c, T.COUNTER, box)
    for c in kegs:
        if t[c] == T.WOOD_FLOOR:
            put_inside(t, c, T.BARREL, box)
    sides = [c for c in sides if t[c] == T.WOOD_FLOOR and not by_door(c)]
    rng.shuffle(sides)
    for c in sides:
        if put_inside(t, c, T.HEARTH, box):
            break
    middle_tiles = [(x, y) for x in range(x0 + 3, x1 - 2) for y in range(y0 + 2, y1 - 1)
                    if t[x, y] == T.WOOD_FLOOR and not by_door((x, y))
                    and all(t[x + dx, y + dy] != T.COUNTER for dx in (-1, 0, 1) for dy in (-1, 0, 1))]
    rng.shuffle(middle_tiles)
    placed = []
    for c in middle_tiles:
        if len(placed) == 4:
            break
        if all(abs(c[0] - p[0]) > 1 or abs(c[1] - p[1]) > 1 for p in placed) and put_inside(t, c, T.TABLE, box):
            placed.append(c)
    return outside


def inn_stairs(level: Level, x0: int, y0: int, x1: int, y1: int, door) -> None:
    """Stairs up to the guest rooms and down to the cellar, in the inn's corners away from the
    door."""
    t = level.tiles
    corners = [(x0 + 1, y0 + 1), (x1 - 1, y0 + 1), (x0 + 1, y1 - 1), (x1 - 1, y1 - 1)]
    corners.sort(key=lambda c: -((c[0] - door[0]) ** 2 + (2 * (c[1] - door[1])) ** 2))
    for (x, y), way in zip(corners[:2], (("inn_up", T.STAIRS_UP), ("cellar", T.STAIRS_DOWN))):
        t[x, y] = way[1]
        level.exits[(x, y)] = (way[0], *level.region, 1)


def shop(level: Level, rng: random.Random, kind: str, name: str, ring):
    """A bakery (bread ovens, flour, a counter), a butcher's (meat hooks, a counter) or an
    armourer's (weapon racks, a counter)."""
    box = (place_box(level, rng, ((8, 10), (6, 7)), ring)
           or place_box(level, rng, ((7, 8), (5, 6)), (ring[0], ring[1] + 12)))   # smaller, further out
    if box is None:
        return None
    x0, y0, w, h = box
    door, outside = building(level, rng, x0, y0, w, h, middle(level), kind=kind, name=name)
    if kind == "bakery":
        furnish(level, rng, x0, y0, w, h, beds=0, hearth=False, tables=2, barrels=2,
                extra=((T.OVEN, 2), (T.CHEST, 1)), middle=T.COUNTER)
    elif kind == "armoury":
        furnish(level, rng, x0, y0, w, h, beds=0, hearth=False, tables=2, barrels=1,
                extra=((T.RACK, 3), (T.CHEST, 1)), middle=T.COUNTER)
    else:
        furnish(level, rng, x0, y0, w, h, beds=0, hearth=False, tables=2, barrels=1,
                extra=((T.HOOKS, 2), (T.CHEST, 1)), middle=T.COUNTER)
    return outside


# ----------------------------------------------------------------- builders

def build_town(level: Level, site, rng: random.Random, land=None) -> None:
    land = land or DEFAULT_LAND
    square(level, 7, 3, stalls=6)
    doors = [inn_building(level, rng, (9, 16)),
             shop(level, rng, "bakery", "the bakery", (9, 20)),
             shop(level, rng, "butcher", "the butcher's", (9, 20)),
             shop(level, rng, "armoury", "the armourer's", (9, 22))]
    doors = [d for d in doors if d is not None]
    doors += houses(level, rng, rng.randint(11, 16), (9, 36))
    gates = fields(level, rng, rng.randint(3, 5), (36, 50))
    gates += pastures(level, rng, 1, (36, 50), farming.herd_for(land))
    foot = docks(level, rng) if site.port else None
    camp = lumber_camp(level, rng)
    for start in doors + gates + [s for s in (foot, camp) if s]:
        connect(level, start, ways(level), T.STREET if start in doors else T.PATH)
    fishing_spot(level)


def build_village(level: Level, site, rng: random.Random, land=None) -> None:
    land = land or DEFAULT_LAND
    square(level, 4, 2, stalls=0)
    level.tiles[level.tiles == T.STREET] = T.GRASS
    doors = houses(level, rng, rng.randint(4, 7), (6, 24))
    level.crop = farming.grain_for(land)
    gates = fields(level, rng, rng.randint(3, 5), (20, 40), sizes=((10, 16), (5, 8)), crop=level.crop)
    gates += pastures(level, rng, rng.randint(1, 2), (20, 42), farming.herd_for(land))
    foot = docks(level, rng) if site.port else None
    camp = lumber_camp(level, rng)
    cx, cy = middle(level)
    hub = np.zeros(level.tiles.shape, bool)
    hub[cx - 1: cx + 2, cy - 1: cy + 2] = True
    for start in doors + gates + [s for s in (foot, camp) if s]:
        connect(level, start, ways(level) | hub)
    fishing_spot(level)


def build_inn(level: Level, site, rng: random.Random, land=None) -> None:
    doors = [inn_building(level, rng, (4, 12), sizes=((14, 16), (7, 8)))]
    doors = [d for d in doors if d is not None]
    doors += fields(level, rng, 1, (10, 18), sizes=((8, 11), (4, 6)), crop=T.DIRT, kind="pasture", animal="horse")
    well = place_box(level, rng, ((1, 1), (1, 1)), (5, 9))
    if well is not None:
        level.tiles[well[0], well[1]] = T.WELL
    for start in doors:
        connect(level, start, ways(level))


def build_tower(level: Level, site, rng: random.Random) -> None:
    """A round stone tower in the middle, its door toward the nearest way in."""
    cx, cy = middle(level)
    t = level.tiles
    outer, inner = ellipse(level, cx, cy, 5.5, 3.5), ellipse(level, cx, cy, 4.5, 2.5)
    around = ellipse(level, cx, cy, 8, 5)
    t[around & ~outer & ~T.WALK[t] & T.CLEARABLE[t]] = T.GRASS
    t[around & ~outer & (t == T.ROCK)] = T.SCREE
    t[outer] = T.STONE_WALL
    t[inner] = T.STONE_FLOOR
    door = (cx, cy + 3)
    t[door] = T.DOOR
    t[cx, cy + 4] = T.PATH
    hang_torch(level, rng, door, (0, 1))
    t[cx, cy] = T.STAIRS_UP
    t[cx - 3, cy] = T.TABLE
    level.exits[(cx, cy)] = ("tower", *level.region, 1)
    connect(level, (cx, cy + 4), ways(level) & ~ellipse(level, cx, cy, 6.5, 4.5))


def build_ruins(level: Level, site, rng: random.Random) -> None:
    """Stone buildings fallen in and grown over; the biggest still has a way down."""
    boxes = []
    for _ in range(rng.randint(4, 7)):
        box = place_box(level, rng, ((5, 10), (4, 7)), (0, 24))
        if box is not None:
            boxes.append(box)
            building(level, rng, *box, middle(level), wall=T.STONE_WALL, floor=T.STONE_FLOOR, torch=False,
                     kind="ruin", name="a ruined building")
    t = level.tiles
    for x0, y0, w, h in boxes:
        for x in range(x0, x0 + w):
            for y in range(y0, y0 + h):
                r = rng.random()
                if t[x, y] in (T.STONE_WALL, T.DOOR):
                    if r < 0.35:
                        t[x, y] = T.RUBBLE
                    elif r < 0.45:
                        t[x, y] = T.GRASS
                    elif t[x, y] == T.DOOR:
                        t[x, y] = T.RUBBLE
                elif t[x, y] == T.STONE_FLOOR:   # the roofs are long gone
                    t[x, y] = (T.RUBBLE if r < 0.3 else T.DIRT if r < 0.65 else
                               T.TALL_GRASS if r < 0.9 else T.TREE if r < 0.95 else T.BUSH)
    if boxes:
        x0, y0, w, h = max(boxes, key=lambda b: b[2] * b[3])
        sx, sy = x0 + w // 2, y0 + h // 2
        t[sx, sy] = T.STAIRS_DOWN
        for dx, dy in DIRS4:
            if not T.WALK[t[sx + dx, sy + dy]]:
                t[sx + dx, sy + dy] = T.RUBBLE
        level.exits[(sx, sy)] = ("crypt", *level.region, 1)


def build_cave(level: Level, site, rng: random.Random) -> None:
    """A rocky outcrop with a dark way down on its south side."""
    cx, cy = middle(level)
    t = level.tiles
    xs, ys = np.ogrid[: level.width, : level.height]
    wobble = np.array([[rng.uniform(-0.25, 0.25) for _ in range(level.height)] for _ in range(level.width)])
    rock = ((xs - cx) / 9) ** 2 + ((ys - cy) / 4.5) ** 2 <= 1 + wobble
    t[rock & ~T.WATERY[t]] = T.ROCK
    y = cy
    while y + 1 < level.height - EDGE and t[cx, y + 1] == T.ROCK:
        y += 1
    t[cx, y] = T.STAIRS_DOWN
    for dy in (1, 2):
        if not T.WALK[t[cx, y + dy]] and not T.WATERY[t[cx, y + dy]]:
            t[cx, y + dy] = T.DIRT
    level.exits[(cx, y)] = ("cave", *level.region, 1)
    connect(level, (cx, y + 2), ways(level))


BUILDERS = {"town": build_town, "village": build_village, "inn": build_inn, "tower": build_tower,
            "ruins": build_ruins, "cave": build_cave}
CLEARED = 0.5      # how often a town or village has cleared the woods around it


DEFAULT_LAND = farming.Land(0, 12.0, 0.5, -0.5)   # a temperate grassland, when none is given


def build(level: Level, site, rng: random.Random, land=None) -> None:
    from . import cities
    if site.kind in ("city", "fort"):
        (cities.build_city if site.kind == "city" else cities.build_fort)(level, site, rng, land)
        return
    if site.kind in ("town", "village") and random.Random(f"clear{site.name}").random() < CLEARED:
        cities.clear_woods(level, rng, 70 if site.kind == "town" else 50)   # felled long ago for timber and fields
    builder = BUILDERS[site.kind]
    if site.kind in ("town", "village", "inn"):
        builder(level, site, rng, land)
    else:
        builder(level, site, rng)


# ----------------------------------------------------------------- levels above and below

CAVE_DEPTHS = (1, 3)       # a cave goes this many levels down
TOWER_FLOORS = 2           # a room, then the roof


def parent(key: tuple) -> tuple:
    kind, x, y, n = key
    return ("region", x, y) if n == 1 else (kind, x, y, n - 1)


def cave_depth(site_name: str) -> int:
    """How many levels a cave goes down: fixed by its name, so it never changes."""
    return CAVE_DEPTHS[0] + sum(map(ord, site_name)) % (CAVE_DEPTHS[1] - CAVE_DEPTHS[0] + 1)


def largest_area(walk: np.ndarray) -> np.ndarray:
    """The biggest connected patch of walkable tiles (8-way)."""
    w, h = walk.shape
    label = np.zeros(walk.shape, np.int32)
    best, best_size, n = 0, 0, 0
    for sx, sy in zip(*np.nonzero(walk)):
        if label[sx, sy]:
            continue
        n += 1
        stack, size = [(sx, sy)], 0
        label[sx, sy] = n
        while stack:
            x, y = stack.pop()
            size += 1
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < w and 0 <= ny < h and walk[nx, ny] and not label[nx, ny]:
                        label[nx, ny] = n
                        stack.append((nx, ny))
        if size > best_size:
            best, best_size = n, size
    return label == best


def safe_spot(walk: np.ndarray, x: int, y: int) -> bool:
    """Whether blocking (x, y) leaves everything round it still joined (8-way), so nothing
    beyond it is cut off."""
    w, h = walk.shape
    ring = [(x + dx, y + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if (dx or dy)
            and 0 <= x + dx < w and 0 <= y + dy < h and walk[x + dx, y + dy]]
    if not ring:
        return False
    seen, todo = {ring[0]}, [ring[0]]
    while todo:
        a = todo.pop()
        for b in ring:
            if b not in seen and abs(a[0] - b[0]) <= 1 and abs(a[1] - b[1]) <= 1:
                seen.add(b)
                todo.append(b)
    return len(seen) == len(ring)


def hide_chests(tiles: np.ndarray, floor: int, rng: random.Random, count: int, avoid=()) -> list:
    """Chests tucked into nooks (the floor tiles with the fewest open neighbours), away from
    the stairs and from each other, never where they'd cut a way off."""
    walk = T.WALK[tiles].copy()
    w, h = tiles.shape
    def open_round(x, y):
        return sum(walk[x + dx, y + dy] for dx in (-1, 0, 1) for dy in (-1, 0, 1)
                   if (dx or dy) and 0 <= x + dx < w and 0 <= y + dy < h)
    spots = [(int(x), int(y)) for x, y in zip(*np.nonzero(tiles == floor))
             if all(max(abs(x - a), abs(y - b)) > 4 for a, b in avoid)]
    rng.shuffle(spots)
    spots.sort(key=lambda c: open_round(*c))
    placed = []
    for x, y in spots:
        if len(placed) == count:
            break
        if all(max(abs(x - a), abs(y - b)) > 8 for a, b in placed) and safe_spot(walk, x, y):
            tiles[x, y] = T.CHEST
            walk[x, y] = False
            placed.append((x, y))
    return placed


def far_tile(walk: np.ndarray, start: tuple[int, int]) -> tuple[int, int]:
    dist = tcod.path.maxarray(walk.shape, dtype=np.int32)
    dist[start] = 0
    tcod.path.dijkstra2d(dist, walk.astype(np.int32), 2, 3, out=dist)
    reach = np.where(dist < np.iinfo(np.int32).max, dist, -1)
    x, y = np.unravel_index(int(np.argmax(reach)), reach.shape)
    return int(x), int(y)


def cave_level(key: tuple, site, rng: random.Random) -> Level:
    """Caverns grown by a cellular automaton, kept to their biggest connected part."""
    w, h = 72, 36
    wall = np.array([[rng.random() < 0.46 for _ in range(h)] for _ in range(w)])
    for _ in range(5):
        p = np.pad(wall, 1, constant_values=True)
        count = sum(p[1 + dx: w + 1 + dx, 1 + dy: h + 1 + dy] for dx in (-1, 0, 1) for dy in (-1, 0, 1))
        wall = count >= 5
    wall[[0, -1], :] = wall[:, [0, -1]] = True
    floor = largest_area(~wall)
    tiles = np.where(floor, T.CAVE_FLOOR, T.CAVE_WALL).astype(np.uint8)
    pools = floor & (np.array([[rng.random() for _ in range(h)] for _ in range(w)]) < 0.03)
    tiles[pools] = T.WATER
    cells = list(zip(*np.nonzero(floor)))
    up = tuple(int(c) for c in cells[rng.randrange(len(cells))])
    tiles[up] = T.STAIRS_UP
    level = Level(key, f"{site.name}, level {key[3]}", tiles, {up: parent(key)}, underground=True,
                  indoor_air=11.0 - key[3])
    if key[3] < cave_depth(site.name):
        down = far_tile(T.WALK[tiles], up)
        tiles[down] = T.STAIRS_DOWN
        level.exits[down] = (key[0], key[1], key[2], key[3] + 1)
    hide_chests(tiles, T.CAVE_FLOOR, rng, rng.randint(1, 2), avoid=list(level.exits))
    return level


def crypt_level(key: tuple, site, rng: random.Random) -> Level:
    """Rooms and corridors under the ruins."""
    m, start, _ = rooms.generate(60, 30, rng, max_rooms=14, min_size=4, max_size=8)
    tiles = np.where(m.walkable, T.STONE_FLOOR, T.STONE_WALL).astype(np.uint8)
    tiles[start] = T.STAIRS_UP
    hide_chests(tiles, T.STONE_FLOOR, rng, rng.randint(2, 3), avoid=[start])
    return Level(key, f"Crypt under the {site.name}", tiles, {start: parent(key)}, underground=True,
                 indoor_air=12.0)


def tower_floor(key: tuple, site, rng: random.Random) -> Level:
    """A round room with stairs both ways, or the roof with its battlements."""
    w, h = 15, 9
    cx, cy = w // 2, h // 2
    xs, ys = np.ogrid[:w, :h]
    outer = ((xs - cx) / 5.5) ** 2 + ((ys - cy) / 3.5) ** 2 <= 1
    inner = ((xs - cx) / 4.5) ** 2 + ((ys - cy) / 2.5) ** 2 <= 1
    roof = key[3] == TOWER_FLOORS
    tiles = np.full((w, h), T.STONE_WALL, np.uint8)
    tiles[outer] = T.BATTLEMENT if roof else T.STONE_WALL
    tiles[inner] = T.FLAGSTONES if roof else T.STONE_FLOOR
    tiles[cx, cy] = T.STAIRS_DOWN
    exits = {(cx, cy): parent(key)}
    if not roof:
        tiles[cx + 2, cy] = T.STAIRS_UP
        exits[(cx + 2, cy)] = (key[0], key[1], key[2], key[3] + 1)
        tiles[cx - 3, cy] = T.BED
        tiles[cx, cy - 2] = T.TABLE
    name = f"Top of {site.name}" if roof else f"{site.name}, floor {key[3] + 1}"
    return Level(key, name, tiles, exits, indoor_air=14.0, lookout=roof, footprint=outer)


INN_ROOMS = 4               # guest rooms along each side of the corridor upstairs
ROOM_W = 5


def inn_upstairs(key: tuple, site, rng: random.Random) -> Level:
    """A corridor with guest rooms off both sides, each with a bed, and the stairs down at one
    end. (game/engine.py names it after the inn.)"""
    w, h = 2 + INN_ROOMS * ROOM_W, 11
    tiles = np.full((w, h), T.WALL, np.uint8)
    cy = h // 2
    tiles[1: w - 1, cy] = T.WOOD_FLOOR
    for i in range(INN_ROOMS):
        x0 = 1 + i * ROOM_W
        for ya, yb, door_y in ((1, cy - 1, cy - 1), (cy + 2, h - 1, cy + 1)):
            tiles[x0: x0 + ROOM_W - 1, ya: yb] = T.WOOD_FLOOR
            tiles[x0 + 1, door_y] = T.DOOR
            far = ya if door_y == cy - 1 else yb - 1
            tiles[x0 + ROOM_W - 2, far] = T.BED
            tiles[x0, far] = rng.choice([T.TABLE, T.BARREL, T.WOOD_FLOOR])
    tiles[w - 2, cy] = T.HEARTH
    tiles[1, cy] = T.STAIRS_DOWN
    name = f"Upstairs at {site.name}" if site is not None else "Upstairs at the inn"
    return Level(key, name, tiles, {(1, cy): parent(key)}, indoor_air=19.0)


def inn_cellar(key: tuple, site, rng: random.Random) -> Level:
    """A low stone cellar of barrels and kegs under the inn."""
    w, h = 20, 9
    tiles = np.full((w, h), T.STONE_WALL, np.uint8)
    tiles[1: w - 1, 1: h - 1] = T.STONE_FLOOR
    for x in range(2, w - 2):
        for y in (1, h - 2):
            if rng.random() < 0.7:
                tiles[x, y] = T.BARREL
    for x in range(4, w - 4, 4):
        tiles[x, h // 2] = T.BARREL
    tiles[1, h // 2] = T.STAIRS_UP
    name = f"The cellar at {site.name}" if site is not None else "The inn's cellar"
    return Level(key, name, tiles, {(1, h // 2): parent(key)}, underground=True, indoor_air=12.0)


def sublevel(key: tuple, site, rng: random.Random) -> Level:
    return {"cave": cave_level, "crypt": crypt_level, "tower": tower_floor, "inn_up": inn_upstairs,
            "cellar": inn_cellar}[key[0]](key, site, rng)
