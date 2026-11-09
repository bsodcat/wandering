"""The dev arena: a 256 x 256 test ground with one of everything, for trying things out.

    north-west   a swatch of every kind of ground, and a broadleaf, a pine and a jungle wood
    middle       where you start: a paved plaza
    north        the gallery: every tile in the game on its own flagstone, a row per kind
                 (ground, trees, ways, building, furniture and trades, fields)
    south        pens with one of every townsfolk (each with a bit of their trade) and one of
                 every animal
    east         a river with a bridge, and a lake with a beach and a pier
    far south    a town (inn, bakery, butcher's, houses, gardens, a pasture, a lumber camp) and
                 a village (wheat, sheep), built and peopled the same way as in the world

Everything is explored from the start. Stairs here lead nowhere; you leave by the menu.
"""
from __future__ import annotations

import random

import numpy as np

from . import people
from . import structures
from . import tiles as T
from . import trees
from .farming import ANIMALS, Land
from .level import Level, Place
from .worldgen import Site

ARENA_W = ARENA_H = 256
SPAWN = (128, 128)
SEED = 4242                    # the arena is the same every time

GALLERY = [   # (row name, tiles) - every tile appears here once
    ("ground", [T.DEEP_WATER, T.WATER, T.SAND, T.GRASS, T.TALL_GRASS, T.DRY_GRASS, T.DIRT, T.MUD, T.SNOW,
                T.ICE, T.SCREE, T.REEDS, T.BUSH, T.BOULDER, T.ROCK]),
    ("trees", [T.TREE, T.PINE, T.JUNGLE_TREE, T.STUMP]),
    ("ways", [T.ROAD, T.STREET, T.PATH, T.BRIDGE, T.DOCK, T.FLAGSTONES, T.RUBBLE]),
    ("building", [T.WOOD_FLOOR, T.STONE_FLOOR, T.CAVE_FLOOR, T.WALL, T.STONE_WALL, T.CAVE_WALL, T.DOOR,
                  T.FENCE, T.BATTLEMENT, T.TORCH, T.SIGN, T.STAIRS_DOWN, T.STAIRS_UP]),
    ("furniture", [T.BED, T.TABLE, T.HEARTH, T.BARREL, T.WELL, T.STALL, T.OVEN, T.COUNTER, T.HOOKS,
                   T.WOODPILE, T.TROUGH]),
    ("fields", [T.CROPS, T.WHEAT, T.RYE, T.RICE, T.MILLET]),
]
GALLERY_TOP = 100
SLOT = 4                       # columns between the tiles in a gallery row
ROW = 3                        # rows between gallery rows

SWATCHES = [T.DEEP_WATER, T.WATER, T.SAND, T.TALL_GRASS, T.DRY_GRASS, T.DIRT, T.MUD, T.SNOW, T.ICE,
            T.SCREE, T.REEDS, T.BUSH, T.BOULDER, T.ROCK, T.RUBBLE, T.CAVE_FLOOR]
WOODS = [T.TREE, T.PINE, T.JUNGLE_TREE]
TRADE_PROPS = {"baker": T.OVEN, "butcher": T.HOOKS, "innkeeper": T.COUNTER, "farmer": T.WHEAT,
               "fisherman": T.WATER, "lumberjack": T.WOODPILE}
PEN_W, PEN_H = 9, 5
RIVER_X = 186                  # the river's west bank
LAKE = (228, 128, 20, 34)      # centre and radii


def build_arena(world, region: tuple[int, int]) -> Level:
    """The arena, with `region` the world region whose weather and daylight it takes."""
    rng = random.Random(SEED)
    level = Level(("arena", *region), "the Dev Arena", np.full((ARENA_W, ARENA_H), T.GRASS, np.uint8),
                  indoor_air=19.0)
    t = level.tiles
    xs, ys = np.ogrid[:ARENA_W, :ARENA_H]
    swatches(t, rng)
    woods(t, rng)
    water(level, xs, ys)
    plaza = ((xs - SPAWN[0]) / 11) ** 2 + ((ys - SPAWN[1]) / 5) ** 2 <= 1
    t[plaza] = T.FLAGSTONES
    gallery(t)
    pens(level, rng)
    settlement(level, world, rng, Site("town", "Testbury", *region), (4, 196), (96, 48), Land(0, 12.0, 0.5, -0.5))
    settlement(level, world, rng, Site("village", "Little Testing", *region), (102, 198), (80, 44),
               Land(5, 12.0, 0.5, -0.5))
    for x0, y0, w, h in ((4, 196, 96, 48), (102, 198, 80, 44)):     # roads from the settlements' middles
        structures.connect(level, (x0 + w // 2, y0 + h // 2 - 2), plaza, T.ROAD)
    east = int(np.nonzero(plaza[:, SPAWN[1]])[0].max()) + 1      # a path east, over the river to the pier
    shore = LAKE[0] - LAKE[2] - 2
    t[east: shore, SPAWN[1]] = np.where(T.WATERY[t[east: shore, SPAWN[1]]], T.BRIDGE, T.PATH)
    trees.clear_entrances(t, level.exits)
    level.canopy, level.boughs = trees.crowns(t)
    trees.keep_clear(level.canopy, level.boughs, t, level.exits)
    level.explored[:] = True
    return level


def swatches(t: np.ndarray, rng: random.Random) -> None:
    """A patch of every kind of ground, in rows of four, in the north-west."""
    for i, tile in enumerate(SWATCHES):
        x0, y0 = 6 + (i % 4) * 20, 6 + (i // 4) * 12
        if tile == T.BOULDER:        # boulders lie about on dirt
            t[x0: x0 + 18, y0: y0 + 10] = T.DIRT
            for _ in range(25):
                t[rng.randrange(x0, x0 + 18), rng.randrange(y0, y0 + 10)] = T.BOULDER
        else:
            t[x0: x0 + 18, y0: y0 + 10] = tile


def woods(t: np.ndarray, rng: random.Random) -> None:
    """A broadleaf wood, a pine wood and a jungle, side by side, with brush under the trees."""
    for i, tile in enumerate(WOODS):
        x0, y0, w, h = 6 + i * 27, 58, 25, 36
        patch = t[x0: x0 + w, y0: y0 + h]
        r = np.array([[rng.random() for _ in range(h)] for _ in range(w)])
        patch[r < 0.1] = T.TALL_GRASS
        patch[(r >= 0.1) & (r < 0.14)] = T.BUSH
        patch[r > 0.55] = tile
        rank = np.array([[rng.random() for _ in range(h)] for _ in range(w)])
        trees.thin(patch, rank, np.full(patch.shape, T.GRASS, np.uint8))


def water(level: Level, xs, ys) -> None:
    """A river down the east, deep in the middle, and a lake beyond it with a beach and a pier."""
    t = level.tiles
    t[RIVER_X: RIVER_X + 7, :] = T.WATER
    t[RIVER_X + 2: RIVER_X + 5, :] = T.DEEP_WATER
    t[RIVER_X - 1, ::3] = T.REEDS
    cx, cy, rx, ry = LAKE
    d = ((xs - cx) / rx) ** 2 + ((ys - cy) / ry) ** 2
    t[d <= 1.35] = T.SAND
    t[d <= 1.0] = T.WATER
    t[d <= 0.7] = T.DEEP_WATER
    west = cx - rx - 2
    t[west: west + 10, cy: cy + 2] = T.DOCK
    level.places.append(Place("pier", "the end of the pier", [(west + 8, cy), (west + 9, cy), (west + 8, cy + 1)]))


def gallery(t: np.ndarray) -> None:
    """Every tile on its own flagstone, a row for each kind, north of the plaza."""
    width = max(len(row) for _, row in GALLERY) * SLOT + 4
    x0 = SPAWN[0] - width // 2
    t[x0: x0 + width, GALLERY_TOP - 2: SPAWN[1] - 3] = T.FLAGSTONES
    for r, (_, row) in enumerate(GALLERY):
        start = SPAWN[0] - (len(row) * SLOT) // 2 + SLOT // 2
        for i, tile in enumerate(row):
            t[start + i * SLOT, GALLERY_TOP + r * ROW] = tile


def gallery_spots() -> dict[int, tuple[int, int]]:
    """Where each tile stands in the gallery."""
    out = {}
    for r, (_, row) in enumerate(GALLERY):
        start = SPAWN[0] - (len(row) * SLOT) // 2 + SLOT // 2
        for i, tile in enumerate(row):
            out[tile] = (start + i * SLOT, GALLERY_TOP + r * ROW)
    return out


def pen(level: Level, x0: int, y0: int, floor: int = T.GRASS) -> list:
    """A fenced pen with a gate on the north side. Returns the tiles inside."""
    t = level.tiles
    t[x0: x0 + PEN_W, y0: y0 + PEN_H] = T.FENCE
    t[x0 + 1: x0 + PEN_W - 1, y0 + 1: y0 + PEN_H - 1] = floor
    t[x0 + PEN_W // 2, y0] = T.PATH
    return [(x, y) for x in range(x0 + 1, x0 + PEN_W - 1) for y in range(y0 + 1, y0 + PEN_H - 1)]


def pens(level: Level, rng: random.Random) -> None:
    """South of the plaza: a pen for each of the townsfolk with a bit of their trade, then one
    for each animal."""
    t = level.tiles
    used: set = set()
    jobs = list(people.JOBS)
    for row, kinds in enumerate((jobs, list(ANIMALS))):
        y0 = SPAWN[1] + 9 + row * (PEN_H + 3)
        x_start = SPAWN[0] - (len(kinds) * (PEN_W + 1)) // 2
        for i, kind in enumerate(kinds):
            x0 = x_start + i * (PEN_W + 1)
            inside = pen(level, x0, y0, T.DIRT if kind == "hen" else T.GRASS)
            if kind in TRADE_PROPS:
                corner = (x0 + PEN_W - 2, y0 + PEN_H - 2)
                t[corner] = TRADE_PROPS[kind]
                inside = [c for c in inside if T.WALK[t[c]] and not T.WATERY[t[c]]]
            x, y = inside[len(inside) // 2]
            if kind in ANIMALS:
                level.actors.append(people.Actor(kind, kind, x, y, work=inside))
                level.places.append(Place("pasture", f"a pen of {ANIMALS[kind].plural}", inside, kind))
            else:
                level.actors.append(people.Actor(kind, people.person_name(rng, used), x, y, home=inside,
                                                 work=inside, evening=inside))


def settlement(level: Level, world, rng: random.Random, site: Site, at: tuple[int, int], size: tuple[int, int],
               land: Land) -> None:
    """A settlement built and peopled as in the world, on its own patch of the arena, with
    woods round its edge for a lumber camp."""
    x0, y0 = at
    w, h = size
    patch = level.tiles[x0: x0 + w, y0: y0 + h]                # a view: building on it builds the arena
    edge = np.zeros(patch.shape, bool)
    edge[:10], edge[-10:] = True, True
    r = np.array([[rng.random() for _ in range(h)] for _ in range(w)])
    patch[edge & (r > 0.5)] = T.TREE
    trees.thin(patch, r, np.full(patch.shape, T.GRASS, np.uint8))
    sub = Level(("region", site.x, site.y), site.name, patch)
    structures.build(sub, site, random.Random(rng.random()), land)
    people.populate(sub, site, random.Random(rng.random()))
    shift = lambda cells: [(x + x0, y + y0) for x, y in cells]
    for b in sub.buildings:
        b.x0, b.y0, b.door = b.x0 + x0, b.y0 + y0, (b.door[0] + x0, b.door[1] + y0)
        level.buildings.append(b)
    for p in sub.places:
        p.tiles = shift(p.tiles)
        level.places.append(p)
    moved: dict[int, list] = {}
    for a in sub.actors:
        a.x, a.y = a.x + x0, a.y + y0
        for name in ("home", "work", "evening"):
            cells = getattr(a, name)
            if id(cells) not in moved:
                moved[id(cells)] = shift(cells)
            setattr(a, name, moved[id(cells)])
        level.actors.append(a)
    if sub.crop is not None and level.crop is None:
        level.crop = sub.crop

