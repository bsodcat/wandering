"""What people built, and what's under and above it.

Builders work on a region's local map after its land, rivers and roads are drawn. The roads
from the world map all lead into the middle of a settlement, so places grow outward from there:

- town:    a paved square with a well and market stalls, an inn, a dozen or so houses with
           their doors facing the square, streets out to every door, walled fields outside,
           and docks if it's on the coast
- village: a green with a well, a handful of houses, paths, bigger fields; docks on the coast
- inn:     a large inn by the road, a fenced paddock and a well
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

from . import rooms
from . import tiles as T
from .level import Level

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
             wall: int = T.WALL, floor: int = T.WOOD_FLOOR) -> tuple[tuple[int, int], tuple[int, int]]:
    """Walls, a floor and a door on the side facing `toward`. Returns (door, the tile outside it)."""
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
    return door, outside


def furnish(level: Level, rng: random.Random, x0: int, y0: int, w: int, h: int, beds: int = 1,
            hearth: bool = True, tables: int = 1, barrels: int = 0) -> None:
    """Furniture against the inside walls, leaving the tiles by the door clear."""
    t = level.tiles
    inside = [(x, y) for x in range(x0 + 1, x0 + w - 1) for y in range(y0 + 1, y0 + h - 1)]
    def by_door(x, y):
        return any(t[x + dx, y + dy] == T.DOOR for dx in (-1, 0, 1) for dy in (-1, 0, 1))
    walls = [c for c in inside if (c[0] in (x0 + 1, x0 + w - 2) or c[1] in (y0 + 1, y0 + h - 2))
             and not by_door(*c)]
    rng.shuffle(walls)
    for tile, count in ((T.HEARTH, int(hearth)), (T.BED, beds), (T.BARREL, barrels)):
        for _ in range(count):
            if walls:
                t[walls.pop()] = tile
    middle_tiles = [c for c in inside if c not in walls and t[c] == T.WOOD_FLOOR and not by_door(*c)
                    and c[0] not in (x0 + 1, x0 + w - 2) and c[1] not in (y0 + 1, y0 + h - 2)]
    rng.shuffle(middle_tiles)
    for _ in range(tables):
        if middle_tiles:
            t[middle_tiles.pop()] = T.TABLE


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
    cost[np.isin(t, [T.TREE, T.PINE, T.JUNGLE_TREE, T.BOULDER, T.BUSH, T.TALL_GRASS])] = 4
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


def houses(level: Level, rng: random.Random, count: int, ring, sizes=((5, 8), (4, 6))) -> list:
    cx, cy = middle(level)
    doors = []
    for _ in range(count):
        box = place_box(level, rng, sizes, ring)
        if box is None:
            continue
        x0, y0, w, h = box
        door, outside = building(level, rng, x0, y0, w, h, (cx, cy))
        furnish(level, rng, x0, y0, w, h, beds=rng.randint(1, 2), tables=1, barrels=rng.randint(0, 1))
        doors.append(outside)
    return doors


def fields(level: Level, rng: random.Random, count: int, ring, sizes=((8, 14), (4, 7))) -> list:
    """Crops inside a fence, with a gate toward the middle."""
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
        t[x0 + 1: x1, y0 + 1: y1] = T.CROPS
        side = facing(x0, y0, x1, y1, cx, cy)
        gate = ((x1 if side[0] > 0 else x0), (y0 + y1) // 2) if side[0] else ((x0 + x1) // 2, (y1 if side[1] > 0 else y0))
        t[gate] = T.PATH
        gates.append((gate[0] + side[0], gate[1] + side[1]))
    return gates


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
    for i in range(1, length + 1):
        for side in (0, 1):
            px, py = x + dx * i + (side if dy else 0), y + dy * i + (side if dx else 0)
            if level.in_bounds(px, py) and T.WATERY[t[px, py]]:
                t[px, py] = T.DOCK
    box = place_box(level, rng, ((4, 5), (3, 4)), (2, 8), centre=(x - dx * 4, y - dy * 3), tries=60)
    if box is not None:
        x0, y0, w, h = box
        building(level, rng, x0, y0, w, h, (x, y))
        furnish(level, rng, x0, y0, w, h, beds=0, hearth=False, tables=0, barrels=2)
    return x, y


# ----------------------------------------------------------------- builders

def build_town(level: Level, site, rng: random.Random) -> None:
    square(level, 7, 3, stalls=6)
    cx, cy = middle(level)
    inn = place_box(level, rng, ((11, 13), (6, 7)), (9, 16))
    doors = []
    if inn is not None:
        x0, y0, w, h = inn
        door, outside = building(level, rng, x0, y0, w, h, (cx, cy))
        furnish(level, rng, x0, y0, w, h, beds=4, tables=3, barrels=2)
        doors.append(outside)
    doors += houses(level, rng, rng.randint(11, 16), (9, 30))
    gates = fields(level, rng, rng.randint(3, 5), (30, 44))
    foot = docks(level, rng) if site.port else None
    for start in doors + gates + ([foot] if foot else []):
        connect(level, start, ways(level), T.STREET if start in doors else T.PATH)


def build_village(level: Level, site, rng: random.Random) -> None:
    square(level, 4, 2, stalls=0)
    level.tiles[level.tiles == T.STREET] = T.GRASS
    doors = houses(level, rng, rng.randint(4, 7), (6, 20))
    gates = fields(level, rng, rng.randint(3, 5), (16, 36), sizes=((10, 16), (5, 8)))
    foot = docks(level, rng) if site.port else None
    cx, cy = middle(level)
    hub = np.zeros(level.tiles.shape, bool)
    hub[cx - 1: cx + 2, cy - 1: cy + 2] = True
    for start in doors + gates + ([foot] if foot else []):
        connect(level, start, ways(level) | hub)


def build_inn(level: Level, site, rng: random.Random) -> None:
    cx, cy = middle(level)
    doors = []
    inn = place_box(level, rng, ((12, 14), (6, 8)), (4, 12))
    if inn is not None:
        x0, y0, w, h = inn
        door, outside = building(level, rng, x0, y0, w, h, (cx, cy))
        furnish(level, rng, x0, y0, w, h, beds=5, tables=3, barrels=3)
        doors.append(outside)
    paddock = place_box(level, rng, ((8, 11), (4, 6)), (10, 18))
    if paddock is not None:
        x0, y0, w, h = paddock
        t = level.tiles
        t[x0: x0 + w, y0: y0 + h] = T.FENCE
        t[x0 + 1: x0 + w - 1, y0 + 1: y0 + h - 1] = T.DIRT
        gate = (x0 + w // 2, y0 if cy < y0 else y0 + h - 1)
        t[gate] = T.PATH
        doors.append((gate[0], gate[1] + (-1 if gate[1] == y0 else 1)))
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
            building(level, rng, *box, middle(level), wall=T.STONE_WALL, floor=T.STONE_FLOOR)
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


def build(level: Level, site, rng: random.Random) -> None:
    BUILDERS[site.kind](level, site, rng)


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
    return level


def crypt_level(key: tuple, site, rng: random.Random) -> Level:
    """Rooms and corridors under the ruins."""
    m, start, _ = rooms.generate(60, 30, rng, max_rooms=14, min_size=4, max_size=8)
    tiles = np.where(m.walkable, T.STONE_FLOOR, T.STONE_WALL).astype(np.uint8)
    tiles[start] = T.STAIRS_UP
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
    return Level(key, name, tiles, exits, indoor_air=14.0, lookout=roof)


def sublevel(key: tuple, site, rng: random.Random) -> Level:
    return {"cave": cave_level, "crypt": crypt_level, "tower": tower_floor}[key[0]](key, site, rng)
