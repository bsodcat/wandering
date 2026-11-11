"""Local maps: each world region opened up into LOCAL_W x LOCAL_H tiles.

The land is a function of global tile coordinates (a region's tiles start at x * LOCAL_W,
y * LOCAL_H), so neighbouring regions join without a seam:

- Biomes: each tile takes the biome of the region its noise-jittered position falls in, so
  borders wander naturally instead of running in straight lines.
- Ground and cover: each biome has a ground tile and layers of cover (trees, bushes, rocks,
  reeds) scattered by clustered noise, so forests have clearings and grassland has copses.
  Trees are thinned so no two trunks touch, and each spreads a crown of leaves on the layer
  above (game/trees.py). Mountains get cliffs along ridge lines.
- Water: oceans and lakes, shallow near the shore and deep further out.
- Rivers and roads are drawn between region "nodes" (a fixed point in each region), with a
  meander that depends only on the two ends, so both sides of a border draw the same line.
  Wide rivers have a deep channel; roads over water become bridges.

Everything is generated over the region plus a margin and then cut down, so anything that
looks at neighbours (shallow water near the shore) is the same on both sides of a border.
Structures come last, from game/structures.py, and keep away from the edges.
"""
from __future__ import annotations

import functools
import math
import random

import numpy as np
import tcod

from . import biomes as B
from . import elevation
from . import items
from . import farming
from . import people
from . import structures
from . import tiles as T
from . import trees
from . import wild
from .level import Level

LOCAL_W, LOCAL_H = 256, 216
MARGIN = 6
JITTER = 0.4          # how far, in regions, biome borders wander
NODE_JITTER = 0.18    # how far, in regions, a node sits from its region's middle

# Each biome: its ground, then layers of (tile, density, clustered) laid on top in order.
RECIPES = {
    B.BEACH: (T.SAND, [(T.DRY_GRASS, 0.08, True), (T.BOULDER, 0.01, False)]),
    B.GLACIER: (T.SNOW, [(T.ICE, 0.35, True), (T.BOULDER, 0.01, False)]),
    B.TUNDRA: (T.DIRT, [(T.SNOW, 0.45, True), (T.DRY_GRASS, 0.2, True), (T.BUSH, 0.04, True),
                        (T.BOULDER, 0.02, False)]),
    B.TAIGA: (T.GRASS, [(T.PINE, 0.4, True), (T.BUSH, 0.05, False), (T.BOULDER, 0.01, False)]),
    B.STEPPE: (T.DRY_GRASS, [(T.GRASS, 0.3, True), (T.BUSH, 0.03, False), (T.BOULDER, 0.01, False)]),
    B.GRASSLAND: (T.GRASS, [(T.TALL_GRASS, 0.35, True), (T.TREE, 0.04, True), (T.BUSH, 0.04, True),
                            (T.BOULDER, 0.005, False)]),
    B.SHRUBLAND: (T.DIRT, [(T.DRY_GRASS, 0.4, True), (T.BUSH, 0.22, True), (T.TREE, 0.02, False),
                           (T.BOULDER, 0.01, False)]),
    B.FOREST: (T.GRASS, [(T.TALL_GRASS, 0.1, True), (T.BUSH, 0.08, True), (T.TREE, 0.42, True)]),
    B.SWAMP: (T.MUD, [(T.WATER, 0.3, True), (T.REEDS, 0.25, True), (T.TREE, 0.12, True)]),
    B.DESERT: (T.SAND, [(T.DIRT, 0.1, True), (T.DRY_GRASS, 0.02, False), (T.BOULDER, 0.015, False)]),
    B.SAVANNA: (T.DRY_GRASS, [(T.GRASS, 0.25, True), (T.BUSH, 0.05, True), (T.TREE, 0.03, False)]),
    B.JUNGLE: (T.GRASS, [(T.TALL_GRASS, 0.2, True), (T.BUSH, 0.15, True), (T.JUNGLE_TREE, 0.55, True)]),
    B.HILLS: (T.GRASS, [(T.DIRT, 0.3, True), (T.SCREE, 0.1, True), (T.TREE, 0.06, True),
                        (T.BOULDER, 0.05, True)]),
    B.MOUNTAINS: (T.SCREE, [(T.SNOW, 0.15, True), (T.BOULDER, 0.06, False)]),
    B.PEAKS: (T.SNOW, [(T.ICE, 0.2, True), (T.BOULDER, 0.03, False)]),
}
CLIFFS = {B.MOUNTAINS: (0.84, 0.45), B.PEAKS: (0.72, 0.25)}   # ridge line and blob thresholds for rock


# ----------------------------------------------------------------- noise

@functools.lru_cache(maxsize=4)
def noises(seed: int) -> dict[str, tcod.noise.Noise]:
    def make(n, octaves):
        return tcod.noise.Noise(2, algorithm=tcod.noise.Algorithm.SIMPLEX,
                                implementation=tcod.noise.Implementation.FBM,
                                octaves=octaves, seed=(seed * 7919 + n) & 0x7FFFFFFF)
    return {"jx": make(1, 3), "jy": make(2, 3), "detail": make(3, 3), "cluster": make(4, 2),
            "ridge": make(5, 4), "height": make(6, 3)}


def hash01(gx: np.ndarray, gy: np.ndarray, salt: int) -> np.ndarray:
    """A steady pseudo-random 0..1 for each global tile and salt."""
    h = (gx.astype(np.uint64) * np.uint64(0x9E3779B1)) & np.uint64(0xFFFFFFFF)
    h ^= (gy.astype(np.uint64) * np.uint64(0x85EBCA77) + np.uint64(salt * 0xC2B2AE3D)) & np.uint64(0xFFFFFFFF)
    h ^= h >> np.uint64(15)
    h = (h * np.uint64(0x2C1B3C6D)) & np.uint64(0xFFFFFFFF)
    h ^= h >> np.uint64(12)
    h = (h * np.uint64(0x297A2D39)) & np.uint64(0xFFFFFFFF)
    h ^= h >> np.uint64(15)
    return (h & np.uint64(0xFFFFFF)).astype(np.float64) / float(1 << 24)


def dilate(mask: np.ndarray, steps: int) -> np.ndarray:
    for _ in range(steps):
        p = np.pad(mask, 1)
        mask = mask | p[:-2, 1:-1] | p[2:, 1:-1] | p[1:-1, :-2] | p[1:-1, 2:]
    return mask


# ----------------------------------------------------------------- terrain

def terrain(world, gx0: int, gy0: int, w: int, h: int) -> tuple[np.ndarray, np.ndarray]:
    """The natural land (no rivers, roads or buildings) for a window of global tiles.
    Returns (tiles, biome per tile)."""
    gx = (gx0 + np.arange(w))[:, None].astype(np.float64) * np.ones((1, h))
    gy = (gy0 + np.arange(h))[None, :].astype(np.float64) * np.ones((w, 1))
    n = noises(world.seed)
    jx = n["jx"][(gx / 40, gy / 20)] * JITTER
    jy = n["jy"][(gx / 40, gy / 20)] * JITTER
    rx = np.clip(np.floor(gx / LOCAL_W + jx), 0, world.width - 1).astype(int)
    ry = np.clip(np.floor(gy / LOCAL_H + jy), 0, world.height - 1).astype(int)
    biome = world.biome[rx, ry]
    cluster = (n["cluster"][(gx / 18, gy / 9)] + 1) / 2
    detail = n["detail"][(gx / 10, gy / 5)]
    tiles = np.full((w, h), T.GRASS, np.uint8)
    ground_of = np.full((w, h), T.GRASS, np.uint8)
    for b in np.unique(biome).tolist():
        here = biome == b
        if b in B.WATER:
            continue
        ground, layers = RECIPES.get(b, (T.GRASS, []))
        tiles[here] = ground
        ground_of[here] = ground
        for salt, (tile, density, clustered) in enumerate(layers, start=10):
            chance = density * (0.15 + 1.7 * cluster) if clustered else density
            tiles[here & (hash01(gx, gy, salt + b * 31) < chance)] = tile
        if b in CLIFFS:
            line, blob = CLIFFS[b]
            ridge = 1 - np.abs(n["ridge"][(gx / 30, gy / 15)])
            tiles[here & ((ridge > line) | (detail > blob))] = T.ROCK
    trees.thin(tiles, hash01(gx, gy, 7), ground_of)
    water = np.isin(biome, B.WATER)
    near_land = dilate(~water, 3)
    tiles[water] = T.DEEP_WATER
    tiles[water & near_land] = T.WATER
    tiles[(biome == B.LAKE) & dilate(~water, 4)] = T.WATER
    return tiles, biome


# ----------------------------------------------------------------- rivers and roads

def node(world, cx: int, cy: int) -> tuple[float, float]:
    """Where rivers and roads meet inside region (cx, cy), in global tiles. A settlement's node
    is its middle, so roads lead into the square."""
    mx, my = cx * LOCAL_W + LOCAL_W // 2, cy * LOCAL_H + LOCAL_H // 2
    if (cx, cy) in world.site_at:
        return float(mx), float(my)
    rng = random.Random(world.region_seed(cx, cy))
    return (mx + rng.uniform(-NODE_JITTER, NODE_JITTER) * LOCAL_W,
            my + rng.uniform(-NODE_JITTER, NODE_JITTER) * LOCAL_H)


def wiggle(a: tuple[float, float], b: tuple[float, float], salt: int, amp: float) -> list[tuple[int, int]]:
    """Points from a to b with a gentle meander that depends only on a, b and the salt."""
    dx, dy = b[0] - a[0], (b[1] - a[1]) * 2
    length = math.hypot(dx, dy)
    steps = max(1, int(length / 8))
    rng = random.Random(hash((round(a[0]), round(a[1]), round(b[0]), round(b[1]), salt)))
    raw = [0.0] + [rng.uniform(-1, 1) for _ in range(steps - 1)] + [0.0]
    offsets = [raw[0]] + [(raw[i - 1] + 2 * raw[i] + raw[i + 1]) / 4 for i in range(1, steps)] + [raw[-1]]
    px, py = (-dy / length, dx / length / 2) if length else (0.0, 0.0)
    return [(round(a[0] + (b[0] - a[0]) * i / steps + px * offsets[i] * amp),
             round(a[1] + (b[1] - a[1]) * i / steps + py * offsets[i] * amp)) for i in range(steps + 1)]


def stroke(points: list[tuple[int, int]], rx: int, ry: int):
    """Every tile within an (rx, ry) ellipse of the line through the points."""
    out = set()
    for p, q in zip(points, points[1:]):
        for x, y in tcod.los.bresenham(p, q).tolist():
            for dx in range(-rx, rx + 1):
                for dy in range(-ry, ry + 1):
                    if (dx / (rx + 0.5)) ** 2 + (dy / (ry + 0.5)) ** 2 <= 1:
                        out.add((x + dx, y + dy))
    return out


RIVER_SHAPE = {1: ((0, 0), None), 2: ((1, 0), None), 3: ((2, 1), (1, 0))}   # width: shallow, deep core
ROAD_SHAPE = {2: (1, 0), 1: (0, 0)}                                           # highway, track


def draw_waterways(world, tiles: np.ndarray, gx0: int, gy0: int) -> None:
    """Rivers, then roads (bridging the rivers), onto a window of global tiles."""
    w, h = tiles.shape
    cx0, cx1 = gx0 // LOCAL_W - 2, (gx0 + w) // LOCAL_W + 2
    cy0, cy1 = gy0 // LOCAL_H - 2, (gy0 + h) // LOCAL_H + 2

    def near(c):
        return cx0 <= c[0] <= cx1 and cy0 <= c[1] <= cy1

    def put(cells, tile, only=None):
        for x, y in cells:
            lx, ly = x - gx0, y - gy0
            if 0 <= lx < w and 0 <= ly < h and (only is None or only[tiles[lx, ly]]):
                tiles[lx, ly] = tile

    for cx in range(max(0, cx0), min(world.width, cx1 + 1)):
        for cy in range(max(0, cy0), min(world.height, cy1 + 1)):
            if not world.river[cx, cy]:
                continue
            down = (cx + int(world.flow_dx[cx, cy]), cy + int(world.flow_dy[cx, cy]))
            pts = wiggle(node(world, cx, cy), node(world, *down), 1, 6)
            shallow, deep = RIVER_SHAPE[int(world.river_width[cx, cy]) or 1]
            put(stroke(pts, *shallow), T.WATER)
            if deep:
                put(stroke(pts, *deep), T.DEEP_WATER)
    for (a, b), width in world.road_edges.items():
        if not (near(a) or near(b)):
            continue
        pts = wiggle(node(world, *a), node(world, *b), 2, 3)
        cells = stroke(pts, *ROAD_SHAPE[width])
        put(cells, T.BRIDGE, only=T.WATERY)
        put(cells, T.ROAD, only=~np.isin(np.arange(len(T.TILES)), [T.BRIDGE, T.DEEP_WATER, T.WATER]))


# ----------------------------------------------------------------- levels

def region_name(world, x: int, y: int) -> str:
    site = world.site_at.get((x, y))
    return site.name if site else f"{B.BIOMES[world.biome[x, y]].name} ({x}, {y})"


def generate_region(world, x: int, y: int) -> Level:
    gx0, gy0 = x * LOCAL_W - MARGIN, y * LOCAL_H - MARGIN
    window, biome = terrain(world, gx0, gy0, LOCAL_W + 2 * MARGIN, LOCAL_H + 2 * MARGIN)
    draw_waterways(world, window, gx0, gy0)
    height = elevation.heights(world, gx0, gy0, LOCAL_W + 2 * MARGIN, LOCAL_H + 2 * MARGIN, biome, window,
                               noises(world.seed)["height"], LOCAL_W, LOCAL_H)
    inner = (slice(MARGIN, MARGIN + LOCAL_W), slice(MARGIN, MARGIN + LOCAL_H))
    site = world.site_at.get((x, y))
    level = Level(("region", x, y), region_name(world, x, y), window[inner].copy(),
                  indoor_air=19.0 if site is not None and site.settled else 14.0, elev=height[inner].copy())
    if site is not None:
        structures.build(level, site, random.Random(world.region_seed(x, y)), farming.land_at(world, x, y))
        level.elev = elevation.level_ground(level.elev, level.tiles)
    # Trees keep clear of every way in; then the crowns, from the trunks left standing here and
    # in the margin, so leaves reach across the border from trees in the next region.
    trees.clear_entrances(level.tiles, level.exits)
    window[inner] = level.tiles
    canopy, boughs = trees.crowns(window)
    level.canopy, level.boughs = canopy[inner].copy(), boughs[inner].copy()
    trees.keep_clear(level.canopy, level.boughs, level.tiles, level.exits)
    if site is not None:
        people.populate(level, site, random.Random(world.region_seed(x, y) + 1))
    bury(level, random.Random(world.region_seed(x, y) + 2), BURIED.get(site.kind if site else None, BURIED[None]),
         town=site is not None and site.kind == "town")
    wild.populate_region(level, world, x, y, site, random.Random(world.region_seed(x, y) + 3))
    return level


BURIED = {None: 1 / 150, "ruins": 1 / 50, "town": 1 / 250, "village": 1 / 200}   # share of open ground with something under it


def bury(level: Level, rng: random.Random, share: float, town: bool = False) -> None:
    """Things lost and buried over the years, under open ground you could dig (silver and gold
    only under a town)."""
    spots = list(zip(*np.nonzero(T.DIGGABLE[level.tiles])))
    for x, y in rng.sample(spots, min(len(spots), round(len(spots) * share))):
        level.buried[(int(x), int(y))] = items.treasure(rng, town)


def make_level(world, key: tuple) -> Level:
    """Builds the level for a key. The same key always builds the same level."""
    kind, x, y = key[:3]
    if kind == "region":
        return generate_region(world, x, y)
    site = world.site_at.get((x, y))
    level = structures.sublevel(key, site, random.Random(world.region_seed(x, y) * 31 + key[3]))
    if kind == "cave" and site is not None:
        wild.populate_cave(level, site, key[3], structures.cave_depth(site.name),
                           random.Random(world.region_seed(x, y) * 37 + key[3]))
    return level


def node_local(world, x: int, y: int) -> tuple[float, float]:
    """A region's node in its own local tiles: where to arrive when you step down into it."""
    gx, gy = node(world, x, y)
    return gx - x * LOCAL_W, gy - y * LOCAL_H
