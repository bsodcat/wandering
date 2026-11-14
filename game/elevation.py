"""Elevation on local maps, climbing, and what high ground hides.

The world map already has an elevation in metres for each region. On a local map every tile
gets a height in whole levels of LEVEL_M metres: the world's elevation smoothed between the
middles of the regions, plus rolling noise that's gentle on the plains and rough in the hills
and mountains. Like the land itself it's worked out from global tile coordinates, so it runs
on across region borders. Neighbouring tiles never differ by more than two levels, so there's
always a way up, if a slow one: settlements are levelled.

Moving up or down a level is a slope; two is a steep scramble that takes far longer and tires
you out; three or more (only where something's gone wrong at a seam) can't be climbed. Roads,
streets and paths are graded, so they're never more than a slope.

With climbing gear (game/gear.py) you can also go up and down rises of three or four levels on a
rope, and climb onto boulders and rock outcrops (`CLIMBABLE`); standing on top of one lifts your
eyes (`ON_ROCK_EYE`), so you see further over the land around.

Sight: you see a tile only if the ground between doesn't rise above the line from your eyes to
it. Standing on a hilltop you see far; behind a ridge you see nothing beyond it, and from a
cliff edge you can't see its foot. On the overworld, high ground doesn't hide anything (you see
the regions around you out to your sight's reach), but climbing there costs hours too.
"""
from __future__ import annotations

import numpy as np

from . import biomes as B
from . import tiles as T

LEVEL_M = 20.0            # metres a local height level stands for
MOST_STEP = 2             # the biggest difference between neighbouring tiles
EYE = 1.6                 # how far above the ground your eyes are, in levels
ROUGH = {B.PEAKS: 6.0, B.MOUNTAINS: 4.5, B.HILLS: 2.5, B.TAIGA: 1.2, B.FOREST: 1.0, B.JUNGLE: 1.0,
         B.TUNDRA: 0.8, B.SHRUBLAND: 1.0, B.STEPPE: 0.8, B.SAVANNA: 0.7, B.GRASSLAND: 0.8,
         B.DESERT: 1.2, B.SWAMP: 0.2, B.BEACH: 0.3, B.GLACIER: 1.5, B.PASTURE: 0.6, B.DOWNS: 2.2}
ROUGHNESS = np.array([ROUGH.get(b.id, 0.6) for b in B.BIOMES], dtype=np.float64)
GRADED = [T.ROAD, T.STREET, T.PATH, T.BRIDGE, T.DOCK, T.STAIRS_DOWN, T.STAIRS_UP, T.DOOR]

# Climbing: height difference -> (times as long, extra effort, what you notice)
CLIMB = {1: (1.6, 0.8, None), 2: (3.0, 2.5, "You scramble up the steep slope."),
         -1: (1.1, 0.1, None), -2: (1.6, 0.6, "You clamber down the steep slope.")}
ROPE_STEP = 4             # with climbing gear, the biggest rise you can climb (or let yourself down)
ROPE = {3: (5.0, 3.5, "You rope up the rock face."), 4: (6.5, 4.5, "You rope up the sheer rock face."),
        -3: (2.5, 1.0, "You let yourself down on the rope."), -4: (3.0, 1.2, "You let yourself down on the rope.")}
# Climbing onto a rock: tile -> (times as long, extra effort); along the top of one is easier
CLIMBABLE = {T.BOULDER: (3.0, 2.0), T.ROCK: (5.0, 3.0)}
ALONG_ROCK = (2.0, 1.0)
ON_ROCK_EYE = {T.BOULDER: 1.0, T.ROCK: 1.5}   # extra levels your eyes are lifted, standing on top
WORLD_CLIMB_H = 2.5       # overworld hours per 1000 m climbed
WORLD_DESCENT_H = 0.8     # and per 1000 m down


# ----------------------------------------------------------------- local heights

def world_metres(world, fx: np.ndarray, fy: np.ndarray) -> np.ndarray:
    """The world's elevation (sea level at least) at fractional region coordinates, smoothed
    between region middles."""
    elev = np.maximum(world.elevation, 0.0)
    x0 = np.clip(np.floor(fx).astype(int), 0, world.width - 1)
    y0 = np.clip(np.floor(fy).astype(int), 0, world.height - 1)
    x1, y1 = np.minimum(x0 + 1, world.width - 1), np.minimum(y0 + 1, world.height - 1)
    tx, ty = np.clip(fx - x0, 0, 1), np.clip(fy - y0, 0, 1)
    top = elev[x0, y0] * (1 - tx) + elev[x1, y0] * tx
    bottom = elev[x0, y1] * (1 - tx) + elev[x1, y1] * tx
    return top * (1 - ty) + bottom * ty


def heights(world, gx0: int, gy0: int, w: int, h: int, biome: np.ndarray, tiles: np.ndarray, noise,
            local_w: int, local_h: int) -> np.ndarray:
    """Height levels for a window of global tiles."""
    gx = (gx0 + np.arange(w))[:, None].astype(np.float64) * np.ones((1, h))
    gy = (gy0 + np.arange(h))[None, :].astype(np.float64) * np.ones((w, 1))
    base = world_metres(world, gx / local_w - 0.5, gy / local_h - 0.5) / LEVEL_M
    rough = ROUGHNESS[biome]
    hills = noise[(gx / 26, gy / 13)] * rough
    level = np.floor(base + hills)
    water = T.WATERY[tiles]
    level[water] = np.floor(base[water])                     # water lies flat at the bottom
    return relax(level.astype(np.int16))


def relax(h: np.ndarray, fixed: np.ndarray | None = None, step: int = MOST_STEP, rounds: int = 40) -> np.ndarray:
    """Brings neighbouring tiles within `step` levels of each other, lowering the highs and
    raising the lows, but leaving `fixed` tiles alone."""
    h = h.astype(np.int16).copy()
    for _ in range(rounds):
        p = np.pad(h, 1, mode="edge")
        w, hh = h.shape
        around = [p[1 + dx: w + 1 + dx, 1 + dy: hh + 1 + dy] for dx in (-1, 0, 1) for dy in (-1, 0, 1)]
        low, high = np.min(around, axis=0), np.max(around, axis=0)
        new = np.clip(h, high - step, low + step)
        new = np.where(low + step < high - step, (low + high) // 2, new)
        if fixed is not None:
            new[fixed] = h[fixed]
        if np.array_equal(new, h):
            break
        h = new
    return h


def level_ground(h: np.ndarray, tiles: np.ndarray) -> np.ndarray:
    """A settlement's ground levelled: everything built (and a little round it) at one height,
    the land around eased into it."""
    built = ~T.NATURAL[tiles] & ~T.WATERY[tiles] & ~np.isin(tiles, [T.ROAD, T.BRIDGE])
    if not built.any():
        return h
    from .localgen import dilate
    flat = dilate(built, 2)
    h = h.copy()
    h[flat] = int(np.median(h[flat]))
    return relax(h, fixed=flat)


# ----------------------------------------------------------------- climbing

def climb(dh: int, graded: bool, roped: bool = False) -> tuple[bool, float, float, str | None]:
    """Stepping up (or down) `dh` levels: (can you, times as long, extra effort, a message).
    `roped`: you've climbing gear on, so a rise of up to ROPE_STEP levels can be climbed."""
    if graded:
        dh = max(-1, min(1, dh))
    if dh == 0:
        return True, 1.0, 0.0, None
    if roped and MOST_STEP < abs(dh) <= ROPE_STEP:
        slow, effort, message = ROPE[dh]
        return True, slow, effort, message
    if abs(dh) > MOST_STEP:
        if roped:
            return False, 1.0, 0.0, ("It's too high to climb, even with a rope." if dh > 0
                                     else "It's too far to let yourself down.")
        return False, 1.0, 0.0, "It's too steep to climb." if dh > 0 else "It's too far to drop down."
    slow, effort, message = CLIMB[dh]
    return True, slow, effort, message


def passable(height: np.ndarray, tiles: np.ndarray, dx: int, dy: int) -> np.ndarray:
    """Where a step by (dx, dy) from each tile isn't too steep (for finding a way)."""
    w, h = height.shape
    ok = np.zeros((w, h), bool)
    sx = slice(max(0, -dx), w - max(0, dx))
    sy = slice(max(0, -dy), h - max(0, dy))
    tx = slice(max(0, dx), w - max(0, -dx))
    ty = slice(max(0, dy), h - max(0, -dy))
    graded = np.isin(tiles, GRADED)
    diff = np.abs(height[tx, ty].astype(int) - height[sx, sy])
    ok[sx, sy] = (diff <= MOST_STEP) | (graded[sx, sy] & graded[tx, ty])
    return ok


# ----------------------------------------------------------------- sight

def sightlines(height: np.ndarray, origin: tuple[int, int], candidates: np.ndarray, eye: float = EYE) -> np.ndarray:
    """Which `candidates` you can see over the ground from `origin`: nothing in between rises
    above the line from your eyes to the ground there."""
    out = np.zeros(candidates.shape, bool)
    xs, ys = np.nonzero(candidates)
    if not len(xs):
        return out
    ox, oy = origin
    dx, dy = xs - ox, ys - oy
    n = np.maximum(np.abs(dx), np.abs(dy))
    far = int(n.max())
    if far <= 1:
        out[xs, ys] = True
        return out
    k = np.arange(1, far)[None, :]
    t = k / np.maximum(n, 1)[:, None]
    between = k < n[:, None]
    sx = np.clip(np.rint(ox + dx[:, None] * t).astype(int), 0, height.shape[0] - 1)
    sy = np.clip(np.rint(oy + dy[:, None] * t).astype(int), 0, height.shape[1] - 1)
    ground = height[sx, sy].astype(np.float64)
    e0 = float(height[ox, oy]) + eye
    line = e0 + (height[xs, ys].astype(np.float64)[:, None] - e0) * t
    hidden = (between & (ground > line + 1e-6)).any(axis=1)
    out[xs[~hidden], ys[~hidden]] = True
    return out


def world_climb_hours(world, a: tuple[int, int], b: tuple[int, int]) -> float:
    """Extra overworld hours for the climb (or descent) from region a to region b."""
    dz = max(0.0, float(world.elevation[b])) - max(0.0, float(world.elevation[a]))
    return dz / 1000 * (WORLD_CLIMB_H if dz > 0 else -WORLD_DESCENT_H)
