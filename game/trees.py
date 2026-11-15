"""Trees: a trunk on the ground and a crown of leaves on the layer above it.

As in Dwarf Fortress, a tree is two things. Its trunk stands on the ground: one tile you can't
walk through or see past. Its crown spreads over the tiles around the trunk one level up: you
walk under it, it shades the ground and keeps some rain and snow off, and from above it hides
what's beneath. A level keeps the crowns in its `canopy` array (which kind of leaves, if any,
over each tile) and `boughs` (the branch glyph pointing back to the trunk, shown when the
leaves are down).

Broadleaf trees follow the seasons: buds in spring, green in summer, colours in autumn, bare
boughs in winter. Pines and jungle trees keep their leaves, as do broadleaf trees in the tropics.
A wood doesn't change all at once: each change spreads over a week (TURNING_DAYS), every leafy
tile turning on its own day, a little ahead of or behind the trees around it (turn_delay).

Trees never crowd a way in: trunks are cleared from around doors, gates, stairs and wells, and
no leaves hang over buildings, streets, roads or paths.
"""
from __future__ import annotations

import numpy as np

from . import tiles as T
from .climate import DAYS_PER_YEAR, MIDSUMMER, year_fraction

NONE, BROADLEAF, PINE, JUNGLE = range(4)
KIND = {T.TREE: BROADLEAF, T.PINE: PINE, T.JUNGLE_TREE: JUNGLE}
TRUNKS = list(KIND)
# How far each crown spreads, as squared distance on screen (a row is two columns tall).
CROWN = {PINE: 4, BROADLEAF: 5, JUNGLE: 10}
CLEARING = 8          # no trunk this close (squared, on screen) to a way in
TROPICS = 0.2         # broadleaf trees nearer the equator than this keep their leaves

# What leaves can hang over: open land, water and fields, but not buildings or ways.
CANOPY_OK = T.NATURAL | T.WATERY | np.isin(np.arange(len(T.TILES)), [T.FENCE, T.RUBBLE, T.STUMP, T.TROUGH] + T.FIELDS)
WAYS = [T.ROAD, T.STREET, T.PATH, T.BRIDGE, T.DOCK]
SOLID = [T.WALL, T.STONE_WALL, T.FENCE, T.DOOR, T.TORCH, T.SIGN]   # built things: a way beside one is a way in


def thin(tiles: np.ndarray, rank: np.ndarray, ground: np.ndarray) -> None:
    """Keeps one trunk in any 3x3 patch, the one with the lowest rank; the rest become ground.
    Ranks come from global coordinates, so this agrees across region borders."""
    trunk = np.isin(tiles, TRUNKS)
    r = np.where(trunk, rank, np.inf)
    p = np.pad(r, 1, constant_values=np.inf)
    w, h = tiles.shape
    lowest = np.min([p[1 + dx: w + 1 + dx, 1 + dy: h + 1 + dy] for dx in (-1, 0, 1) for dy in (-1, 0, 1)], axis=0)
    lose = trunk & (r > lowest)
    tiles[lose] = ground[lose]


def offsets(reach: int):
    """The (dx, dy) a crown of squared reach covers, nearest first, without the trunk itself."""
    out = [(dx, dy) for dx in range(-4, 5) for dy in range(-2, 3)
           if (dx or dy) and dx * dx + 4 * dy * dy <= reach]
    return sorted(out, key=lambda d: -(d[0] ** 2 + 4 * d[1] ** 2))   # far first, so near ones win


def bough(dx: int, dy: int) -> int:
    """The branch glyph for a tile at (dx, dy) from its trunk."""
    if dy == 0:
        return ord("─")
    if dx == 0:
        return ord("│")
    return ord("\\") if dx * dy > 0 else ord("/")


def crowns(tiles: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(canopy kind, bough glyph) over every tile, from the trunks in `tiles`."""
    w, h = tiles.shape
    canopy = np.zeros((w, h), np.uint8)
    boughs = np.zeros((w, h), np.int32)
    for tile, kind in sorted(KIND.items(), key=lambda kv: -CROWN[kv[1]]):   # big crowns first, under
        trunk = tiles == tile
        if not trunk.any():
            continue
        for dx, dy in offsets(CROWN[kind]):
            src = trunk[max(0, -dx): w - max(0, dx), max(0, -dy): h - max(0, dy)]
            dst = (slice(max(0, dx), w - max(0, -dx)), slice(max(0, dy), h - max(0, -dy)))
            canopy[dst][src] = kind
            boughs[dst][src] = bough(dx, dy)
        canopy[trunk] = kind
        boughs[trunk] = ord("┼")
    return canopy, boughs


def entrances(tiles: np.ndarray, exits) -> np.ndarray:
    """Ways in: doors, stairs, wells and exits, and any way tile beside a wall or fence (the
    step outside a door, a gate)."""
    way_in = np.isin(tiles, [T.DOOR, T.STAIRS_DOWN, T.STAIRS_UP, T.WELL])
    for x, y in exits:
        way_in[x, y] = True
    solid = np.pad(np.isin(tiles, SOLID), 1)
    beside = solid[:-2, 1:-1] | solid[2:, 1:-1] | solid[1:-1, :-2] | solid[1:-1, 2:]
    return way_in | (np.isin(tiles, WAYS) & beside)


def near(mask: np.ndarray, reach: int) -> np.ndarray:
    """Every tile within squared screen distance `reach` of a tile in `mask`."""
    w, h = mask.shape
    out = mask.copy()
    for dx in range(-4, 5):
        for dy in range(-2, 3):
            if dx * dx + 4 * dy * dy > reach:
                continue
            src = mask[max(0, -dx): w - max(0, dx), max(0, -dy): h - max(0, dy)]
            out[max(0, dx): w - max(0, -dx), max(0, dy): h - max(0, -dy)] |= src
    return out


def clear_entrances(tiles: np.ndarray, exits=(), ground: int = T.GRASS) -> np.ndarray:
    """Fells the trunks around every way in. Returns the mask of tiles near a way in."""
    around = near(entrances(tiles, exits), CLEARING)
    tiles[around & np.isin(tiles, TRUNKS)] = ground
    return around


def keep_clear(canopy: np.ndarray, boughs: np.ndarray, tiles: np.ndarray, exits=()) -> None:
    """No leaves over buildings or ways, or hanging right over a way in."""
    off = ~CANOPY_OK[tiles] | np.isin(tiles, WAYS) | near(entrances(tiles, exits), 4)
    canopy[off] = NONE
    boughs[off] = 0


# ----------------------------------------------------------------- seasons

TURNING_DAYS = 7          # each change of the leaves spreads over this many days
GROVE = (6, 3)            # tiles (wide, tall) that turn about together
STAGES = [(0.13, "green"), (0.3, "autumn"), (0.68, "bare"), (0.8, "budding"), (1.01, "green")]   # by phase


def foliage(lat: float, minutes: float, delay=0.0):
    """What broadleaf trees look like now: "green", "budding", "autumn" or "bare". `delay` (0..1,
    one number or an array: see turn_delay) is how far into the week of turning a tree is late
    to change; an array of delays gives an array of looks."""
    if abs(lat) < TROPICS:
        return "green" if np.ndim(delay) == 0 else np.full(np.shape(delay), "green", "<U7")
    phase = (float(year_fraction(minutes)) - MIDSUMMER + (0.5 if lat > 0 else 0.0)) % 1.0  # 0 midsummer
    phase = (phase - np.asarray(delay, np.float64) * TURNING_DAYS / DAYS_PER_YEAR) % 1.0
    looks = np.select([phase < edge for edge, _ in STAGES], [look for _, look in STAGES], "green")
    return str(looks) if looks.ndim == 0 else looks.astype("<U7")


def turn_delay(gx, gy) -> np.ndarray:
    """A steady 0..1 for each tile (global coordinates): how late in the week its leaves turn.
    Half is shared by the grove around it, so neighbours turn about together."""
    def hash01(x, y, salt):
        h = (np.asarray(x, np.int64) * 374761393 + np.asarray(y, np.int64) * 668265263 + salt) & 0xFFFFFFFF
        h = (h ^ (h >> 13)) * 1274126177 & 0xFFFFFFFF
        return ((h ^ (h >> 16)) & 0xFFFF) / 65536.0
    gx, gy = np.asarray(gx, np.int64), np.asarray(gy, np.int64)
    return 0.5 * hash01(gx, gy, 911) + 0.5 * hash01(gx // GROVE[0], gy // GROVE[1], 4049)


LEAF_SHELTER = {"green": 0.45, "budding": 0.3, "autumn": 0.35, "bare": 0.1}
EVERGREEN_SHELTER = 0.5


def leaf_shelter(kind: int, look: str) -> float:
    """How much a crown overhead keeps off the rain and wind."""
    if kind == NONE:
        return 0.0
    return LEAF_SHELTER[look] if kind == BROADLEAF else EVERGREEN_SHELTER


# ----------------------------------------------------------------- felling

LOGS = {T.TREE: 2, T.PINE: 2, T.JUNGLE_TREE: 3}    # what a felled trunk cuts into


def fell(level, x: int, y: int) -> int:
    """Cuts down the trunk at (x, y), leaving a stump, and takes its crown off the layer above
    (leaves from the trees around stay). Returns how many logs it made."""
    logs = LOGS.get(int(level.tiles[x, y]), 0)
    level.tiles[x, y] = T.STUMP
    w, h = level.tiles.shape
    x0, x1, y0, y1 = max(0, x - 9), min(w, x + 10), max(0, y - 5), min(h, y + 6)
    canopy, boughs = crowns(level.tiles[x0:x1, y0:y1])
    keep_clear(canopy, boughs, level.tiles[x0:x1, y0:y1])
    near = (slice(max(0, x - 4) - x0, min(w, x + 5) - x0), slice(max(0, y - 2) - y0, min(h, y + 3) - y0))
    level.canopy[x0:x1, y0:y1][near] = canopy[near]
    level.boughs[x0:x1, y0:y1][near] = boughs[near]
    return logs
