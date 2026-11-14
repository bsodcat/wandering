"""Erosion: the land worn down by rain, rivers and gravity.

The terrain is kept as layers, each an array indexed [x, y] like the rest of the world:
elevation, the water running over it, the sediment that water carries, how hard the rock is,
and the vegetation whose roots hold the soil. Three processes work on them:

  hydraulic  rain falls and runs downhill, each cell's water joining the next one down, so it
             gathers into streams and rivers. Water carries silt: the more of it there is and
             the steeper it runs, the more it can carry (capacity = K x flow x slope). Carrying
             less than it could, it digs into the ground; carrying more, it drops the excess.
             So valleys deepen where water gathers, and silt settles on plains, in basins and
             off river mouths.
  thermal    slopes steeper than the rock can stand crumble, and the loose stuff slides down.
             Hard rock stands steeper than soft.
  biological roots hold soil: the greener the ground, the less water can take from it.

The world is worn down once, when it's made (worldgen.generate calls erode_world), so the same
seed still gives the same world.

On a local map the same processes go on live, at the scale of a footstep, through the soil:
rain soaks into open ground and sun and warm air dry it out. Bare earth (dirt, dug ground) that's
soaked turns to mud, and firms up again as it dries. In heavy rain, waterlogged bare ground on a
slope washes down onto the tile below: the silt buries the grass there (mud, then bare dirt that
greens over in a few days), and a steep slope washed bare is left as scree. Grass, bushes and
trees hold their soil, so only bare ground moves. Heights on a local map are whole levels of
20 m, far more than a storm shifts, so the live side moves soil, not heights. Only the map you're
on is rained on; one you left just dries out by the time you're back.
"""
from __future__ import annotations

import random

import numpy as np

from . import tiles as T

DIRS = [(dx, dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if dx or dy]
DIST = [2 ** 0.5 if dx and dy else 1.0 for dx, dy in DIRS]

# World erosion. Heights are worked in kilometres so the constants stay readable.
WORLD_ITERATIONS = 20
CAPACITY = 0.05           # K in capacity = K x flow x slope (flow in cells of rain, slope km per cell)
FLOW_POWER = 1.0          # twice the water carries twice the silt
DIG = 0.5                 # share of the spare capacity a cell's water digs out
DROP = 0.5                # share of the excess silt it drops
LAKE_DEPTH = 5.0          # metres of standing water that make a hollow a lake to the silt
REROUTE = 4               # passes between working out the drainage afresh
TALUS = 0.45              # km per cell: the steepest slope rock of hardness 1 stands at
THERMAL_RATE = 0.4        # share of the overhang that slides each step
THERMAL_ITERATIONS = 20
ROOT_HOLD = 0.6           # how much full vegetation cuts erosion
SHORE = 0.001             # km: land is never worn below this, so the coastline stays put


def neighbour(a: np.ndarray, dx: int, dy: int, fill: float | None = None) -> np.ndarray:
    """Each cell's neighbour at (x + dx, y + dy): the edge repeats, or `fill` beyond it."""
    p = np.pad(a, 1, mode="edge") if fill is None else np.pad(a, 1, constant_values=fill)
    w, h = a.shape
    return p[1 + dx: w + 1 + dx, 1 + dy: h + 1 + dy]


def send(amounts: list[np.ndarray]) -> np.ndarray:
    """What each cell receives when every cell sends amounts[i] to its neighbour DIRS[i]."""
    return sum(neighbour(a, -dx, -dy, 0.0) for a, (dx, dy) in zip(amounts, DIRS))


def thermal(z: np.ndarray, hardness: np.ndarray, iterations: int | None = None,
            talus: float | None = None, rate: float | None = None) -> np.ndarray:
    """Slopes steeper than the rock can stand crumble onto the cells below them."""
    iterations = THERMAL_ITERATIONS if iterations is None else iterations
    talus = TALUS if talus is None else talus
    rate = THERMAL_RATE if rate is None else rate
    z = z.astype(np.float64).copy()
    limit = talus * hardness
    for _ in range(iterations):
        over = [np.maximum(z - neighbour(z, dx, dy) - limit * d, 0.0) for (dx, dy), d in zip(DIRS, DIST)]
        total = sum(over)
        if not total.any():
            break
        moving = rate * 0.5 * np.max(over, axis=0)
        share = np.divide(moving, total, out=np.zeros_like(total), where=total > 0)
        z += send([o * share for o in over]) - moving
    return z


def hydraulic(z: np.ndarray, rain: np.ndarray, erodibility: np.ndarray, sink: np.ndarray, route,
              iterations: int | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Rain gathers downhill into rivers, which dig where they could carry more silt and drop
    it where they can't. `route(z)` gives the way water leaves each cell, filling basins so it
    always reaches the sea (worldgen.drain); it's worked out afresh every REROUTE passes.
    `sink` cells (the sea) take whatever reaches them and keep its silt.
    Returns the new heights and the water that ran through each cell on the last pass."""
    iterations = WORLD_ITERATIONS if iterations is None else iterations
    z = z.astype(np.float64).copy()
    w, h = z.shape
    rain_l = np.where(sink, 0.0, rain).ravel().tolist()
    erod_l = erodibility.ravel().tolist()
    sink_l = sink.ravel().tolist()
    xs, ys = np.indices((w, h))
    water = rain_l
    for n in range(iterations):
        if n % REROUTE == 0:
            filled, fdx, fdy, _ = route(z * 1000, np.zeros_like(z))   # drain works in metres
            fdx, fdy = fdx.astype(int), fdy.astype(int)
            rec = ((xs + fdx) * h + ys + fdy).ravel().tolist()
            dist = np.where(fdx * fdy != 0, 2 ** 0.5, 1.0).ravel().tolist()
            order = np.argsort(-filled, axis=None, kind="stable").tolist()
            lake = (filled - z * 1000 > LAKE_DEPTH).ravel().tolist()
        zl = z.ravel().tolist()
        water = rain_l[:]
        silt = [0.0] * (w * h)
        for i in order:
            r = rec[i]
            q = silt[i]
            if sink_l[i] or r == i:            # the sea: the silt settles on its floor
                zl[i] += q
                continue
            if lake[i]:                        # a lake: the silt's carried through to its outlet,
                silt[r] += q                   # so lakes last (and drop it as a delta below)
                water[r] += water[i]
                continue
            s = max(zl[i] - zl[r], 0.0) / dist[i]
            cap = CAPACITY * water[i] ** FLOW_POWER * s
            if q < cap:
                dig = min(DIG * (cap - q) * erod_l[i], s * 0.5)   # never below the next cell down
                zl[i] -= dig
                q += dig
            else:                              # slowing water: a plain silts up
                drop = DROP * (q - cap)
                zl[i] += drop
                q -= drop
            silt[r] += q
            water[r] += water[i]
        z = np.array(zl).reshape(w, h)
    return z, np.array(water).reshape(w, h)


def hardness_field(seed: int, w: int, h: int) -> np.ndarray:
    """How hard the rock is, about 0.4 (soft clay and sandstone) .. 2.6 (granite), in patches."""
    import tcod
    rng = random.Random(seed * 7919 + 17)
    noise = tcod.noise.Noise(2, algorithm=tcod.noise.Algorithm.SIMPLEX,
                             implementation=tcod.noise.Implementation.FBM, octaves=3,
                             seed=rng.getrandbits(31))
    origin = (rng.uniform(0, 1000), rng.uniform(0, 1000))
    n = noise[tcod.noise.grid((w, h), 1 / 30, origin, indexing="ij")].astype(np.float64)
    return 2.0 ** (n * 1.4)


def erode_world(seed: int, elevation: np.ndarray, moisture: np.ndarray,
                temperature: np.ndarray, route, passes: int | None = None, frost: float = 0.0) -> np.ndarray:
    """The world's elevation (metres) after ages of rain and frost. The coastline doesn't move:
    land stays land and sea stays sea, though the sea floor silts up off river mouths.
    `route` is worldgen.drain; `passes` is how long it's had (more for an older world, see
    game/eras.py), and `frost` (0..1) how much harder an ice age's frost shatters the rock."""
    sea = elevation <= 0
    w, h = elevation.shape
    hardness = hardness_field(seed, w, h)
    vegetation = np.clip(moisture * 1.3, 0, 1) * np.clip((temperature + 4) / 12, 0, 1)
    erodibility = (1 - ROOT_HOLD * vegetation) / hardness
    z = elevation.astype(np.float64) / 1000
    z = thermal(z, hardness / (1 + frost), iterations=round(THERMAL_ITERATIONS * (1 + frost)))
    z, _ = hydraulic(z, moisture.astype(np.float64), erodibility, sea, route, passes)
    z = thermal(z, hardness, iterations=5)
    out = z * 1000
    out[~sea] = np.maximum(out[~sea], SHORE * 1000)
    out[sea] = np.minimum(out[sea], -1.0)
    out[sea & (elevation == -20.0)] = -20.0          # the border sea, as worldgen left it
    return out.astype(np.float32)


# ----------------------------------------------------------------- live, on a local map

SOAK_RATE = 0.4           # soil wetness an hour of the heaviest rain adds (0 dry .. 1 waterlogged)
DRY_RATE = 0.02           # wetness lost an hour at 0 C in dry weather ...
DRY_PER_DEGREE = 0.002    # ... and this much more for every degree warmer
MUDDY_AT = 0.7            # bare earth this wet is mud
FIRM_AT = 0.35            # and mud this dry is firm again
WASH_RAIN = 0.5           # rain at least this hard washes soil down bare slopes
WASH_CHANCE = 0.06        # an hour, for each waterlogged bare tile on a slope, in the heaviest rain
STRIP_CHANCE = 0.4        # that a washout on a steep slope takes the last of the soil, leaving scree
SILT_GREENS = 3 * 24 * 60   # minutes before grass grows back through fresh silt
CATCH_UP_AIR = 10.0       # degrees C: the weather a map you left is taken to have had

_ids = np.arange(len(T.TILES))
GETS_MUDDY = np.isin(_ids, [T.DIRT, T.DUG])                 # bare earth
BARE = GETS_MUDDY | (_ids == T.MUD)                          # loose soil nothing holds
HOLDS_WATER = (T.NATURAL & T.WALK) | np.isin(_ids, [T.DUG])  # ground that soaks up rain
SILTS = np.isin(_ids, [T.GRASS, T.TALL_GRASS, T.DRY_GRASS, T.DIRT, T.SAND])   # silt can settle on it


def soil(level) -> np.ndarray:
    """The level's soil wetness, made when it's first needed."""
    if level.soil is None:
        level.soil = np.zeros(level.tiles.shape, np.float32)
    return level.soil


def drying(air: float) -> float:
    return DRY_RATE + DRY_PER_DEGREE * max(0.0, air)


def weather(level, minutes: float, hours: float, precip: float, air: float, rng) -> tuple[bool, list]:
    """`hours` of weather on a local map: rain (`precip` 0..1, 0 when it's dry or snowing)
    soaking in or the ground drying out, mud forming and firming, and soil washing down
    slopes. Returns (whether any tile changed, the tiles washed out)."""
    wet = soil(level)
    holds = HOLDS_WATER[level.tiles]
    wet += SOAK_RATE * precip * hours - drying(air) * (1 - precip) * hours
    np.clip(wet, 0, 1, out=wet)
    wet[~holds] = 0
    washed = wash(level, minutes, hours, precip, rng) if precip >= WASH_RAIN else []
    changed = settle(level, minutes) or bool(washed)
    level.soil_minutes = minutes
    return changed, washed


def catch_up(level, minutes: float) -> bool:
    """A map you left, back in view: it's dried out for as long as you've been away."""
    if level.soil is None or level.soil_minutes is None:
        return False
    hours = (minutes - level.soil_minutes) / 60
    if hours <= 0:
        return False
    level.soil -= drying(CATCH_UP_AIR) * hours
    np.clip(level.soil, 0, 1, out=level.soil)
    level.soil_minutes = minutes
    return settle(level, minutes)


def settle(level, minutes: float) -> bool:
    """Soaked bare earth turns to mud and dry mud firms up; grass grows back through old silt."""
    tiles, wet = level.tiles, soil(level)
    changed = False
    for x, y in np.argwhere(GETS_MUDDY[tiles] & (wet >= MUDDY_AT)):
        level.mud[(int(x), int(y))] = int(tiles[x, y])
        tiles[x, y] = T.MUD
        changed = True
    for spot, was in list(level.mud.items()):
        if tiles[spot] != T.MUD:            # dug up, or grown over: no longer ours to dry
            del level.mud[spot]
        elif wet[spot] < FIRM_AT:
            tiles[spot] = was
            del level.mud[spot]
            changed = True
    for spot, (was, laid) in list(level.silt.items()):
        if tiles[spot] not in (T.DIRT, T.MUD):
            del level.silt[spot]
        elif tiles[spot] == T.DIRT and minutes - laid >= SILT_GREENS:
            tiles[spot] = was
            del level.silt[spot]
            changed = True
    return changed


def wash(level, minutes: float, hours: float, precip: float, rng) -> list[tuple[int, int]]:
    """Heavy rain carries waterlogged bare soil down onto the next tile below."""
    tiles, wet = level.tiles, soil(level)
    elev = level.elev.astype(np.int32)
    drops = np.stack([elev - neighbour(elev, dx, dy) for dx, dy in DIRS])   # the edge repeats: no drop
    way, drop = np.argmax(drops, axis=0), np.max(drops, axis=0)
    chance = WASH_CHANCE * precip * min(hours, 1.0)
    dice = np.random.default_rng(rng.getrandbits(32)).random(tiles.shape)
    washed = []
    for x, y in np.argwhere(BARE[tiles] & (wet >= MUDDY_AT) & (drop > 0) & (dice < chance)):
        x, y = int(x), int(y)
        dx, dy = DIRS[way[x, y]]
        best = (x + dx, y + dy)
        washed.append((x, y))
        below = int(tiles[best])
        if SILTS[below]:                    # the silt buries what was there
            if below != T.DIRT:
                level.silt[best] = [below, minutes]
            level.mud[best] = T.DIRT
            tiles[best] = T.MUD
            wet[best] = max(wet[best], MUDDY_AT)
        if drop[x, y] >= 2 and level.mud.get((x, y)) == T.DIRT and rng.random() < STRIP_CHANCE:   # down to stones
            del level.mud[(x, y)]
            level.silt.pop((x, y), None)
            tiles[x, y] = T.SCREE
            wet[x, y] = 0
    return washed
