"""Volcanoes: where they rise, the cones they build, and what their eruptions leave behind.

Volcanoes are placed from their own random stream (so turning them on or off leaves the rest
of the world as it was):

- On land they rise along the mountain ranges, where the ground is already high.
- At sea a hotspot builds an island, with a chain of older, lower islands trailing away from
  it (the hotspot has moved on, and the old ones are sinking and wearing down).

Each builds a cone before the ages of erosion (game/erosion.py), so old volcanoes are worn and
gullied like the hills around them. What happens next depends on the Eruptions setting:

    Extinct   cold cones; the crater holds a lake; old ash has made the soil rich around them
    Dormant   a warm crater; old lava fields grown over with grass; rich soil
    Active    a lava lake in the crater, fresh lava flows down the valleys, ash downwind
    Violent   longer, wider flows, ash far downwind, and the whole world a little colder

Lava runs downhill the way the rivers do (worldgen.drain's flow directions) until it meets the
sea or a lake. Ash blows downwind: west in the tropics (the trade winds), east further out
(the westerlies). Fresh ash smothers plants; old ash makes the best farmland, and people
settle around it.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass

import numpy as np

from . import tweaks as TW

SPACING = 12                 # regions between volcanoes, at least
CONE_RADIUS = (3.0, 5.0)     # regions, from the vent to the foot of the cone
LAND_RISE = (1300.0, 2400.0)     # metres a land volcano stands over the range it grows from
ISLAND_TOP = (700.0, 2300.0)     # metres a sea volcano's summit stands above the sea
HIGHEST = 5900.0
SEA_SHARE = 0.35             # of the volcanoes, about this many are out at sea
CHAIN = (2, 4)               # older islands trailing behind a sea volcano
CRATER = {TW.EXTINCT: 70.0, TW.DORMANT: 45.0, TW.ACTIVE: 25.0, TW.VIOLENT: 15.0}   # metres deep
FLOWS = {TW.DORMANT: (1, 3), TW.ACTIVE: (2, 6), TW.VIOLENT: (3, 10)}   # (how many, regions long)
ASH = {TW.EXTINCT: 0.0, TW.DORMANT: 0.0, TW.ACTIVE: 0.55, TW.VIOLENT: 1.0}  # fresh ash, at the vent
WARMTH = {TW.EXTINCT: 0.0, TW.DORMANT: 2.0, TW.ACTIVE: 3.5, TW.VIOLENT: 5.0}  # degrees, at the vent
WINTER = 1.5                 # degrees the whole world cools when they're Violent
ACTIVITY = ["extinct", "dormant", "active", "erupting"]


@dataclass
class Volcano:
    name: str
    x: int
    y: int
    radius: float
    summit: float            # metres, when it was built (erosion wears it down after)
    at_sea: bool = False

    def activity(self, eruptions: int) -> str:
        return ACTIVITY[eruptions]


def _rng(seed: int, salt: int) -> random.Random:
    return random.Random((seed * 1_000_003 + salt) & 0xFFFFFFFFFFFF)


def _edge_distance(w: int, h: int) -> np.ndarray:
    x = np.minimum(np.arange(w), w - 1 - np.arange(w))[:, None]
    y = np.minimum(np.arange(h), h - 1 - np.arange(h))[None, :]
    return np.minimum(x, y * 2)


def _spread(mask: np.ndarray, steps: int) -> np.ndarray:
    for _ in range(steps):
        p = np.pad(mask, 1)
        mask = mask | p[:-2, 1:-1] | p[2:, 1:-1] | p[1:-1, :-2] | p[1:-1, 2:]
    return mask


def place(seed: int, elevation: np.ndarray, count: int, name) -> list[Volcano]:
    """Where `count` volcanoes stand on this land. `name(rng)` makes a name."""
    if count <= 0:
        return []
    rng = _rng(seed, 77)
    w, h = elevation.shape
    edge = _edge_distance(w, h)
    land = elevation > 0
    out: list[Volcano] = []

    def clear(x, y):
        return all(max(abs(v.x - x), abs(v.y - y)) >= SPACING for v in out)

    def pick(score, n, at_sea):
        cells = np.argwhere(score > 0)
        if not len(cells):
            return
        weights = score[cells[:, 0], cells[:, 1]].astype(np.float64)
        order = sorted(range(len(cells)), key=lambda i: -weights[i] * rng.random())
        for i in order:
            if sum(v.at_sea == at_sea for v in out) >= n:
                break
            x, y = (int(c) for c in cells[i])
            if not clear(x, y):
                continue
            radius = rng.uniform(*CONE_RADIUS)
            if at_sea:
                summit = rng.uniform(*ISLAND_TOP)
            else:
                around = elevation[max(0, x - 2): x + 3, max(0, y - 2): y + 3].max()
                summit = min(HIGHEST, float(around) + rng.uniform(*LAND_RISE))
            out.append(Volcano(f"Mount {name(rng)}", x, y, radius, summit, at_sea))

    at_sea = round(count * SEA_SHARE)
    high = np.where(land & (edge >= 8), np.maximum(elevation - 700, 0), 0)
    if not high.any():
        high = np.where(land & (edge >= 8), elevation, 0)
    pick(high, count - at_sea, False)
    open_sea = (elevation < -700) & ~_spread(land, 5) & (edge >= 14)
    pick(open_sea.astype(np.float32), at_sea, True)
    if len(out) < count:                     # not enough sea: the rest go on land
        pick(np.where(land & (edge >= 8), np.maximum(elevation, 1), 0), count - sum(v.at_sea for v in out), False)
    return out


def _distance(w: int, h: int, x: float, y: float) -> np.ndarray:
    xs = np.arange(w, dtype=np.float32)[:, None]
    ys = np.arange(h, dtype=np.float32)[None, :]
    return np.sqrt((xs - x) ** 2 + ((ys - y) * 2) ** 2)      # a cell is twice as wide as it is tall


def _cone(e: np.ndarray, x: float, y: float, radius: float, summit: float) -> None:
    w, h = e.shape
    d = _distance(w, h, x, y) / radius
    inside = d < 1
    cone = summit + (e - summit) * d ** 0.8
    e[inside] = np.maximum(e[inside], cone[inside])


def raise_cones(seed: int, elevation: np.ndarray, volcanoes: list[Volcano]) -> np.ndarray:
    """The cones built up on the land (and the islands up out of the sea), before erosion.
    A sea volcano trails a chain of older, lower islands."""
    e = elevation.copy()
    rng = _rng(seed, 91)
    w, h = e.shape
    edge = _edge_distance(w, h)
    for v in volcanoes:
        _cone(e, v.x, v.y, v.radius, v.summit)
        if not v.at_sea:
            continue
        angle = rng.uniform(0, 2 * math.pi)
        summit, x, y = v.summit, float(v.x), float(v.y)
        for _ in range(rng.randint(*CHAIN)):
            summit *= rng.uniform(0.45, 0.7)
            x += math.cos(angle) * v.radius * 2.0
            y += math.sin(angle) * v.radius * 1.0
            angle += rng.uniform(-0.35, 0.35)
            if not (0 <= x < w and 0 <= y < h) or edge[int(x), int(y)] < 10:
                break
            _cone(e, x, y, v.radius * rng.uniform(0.6, 0.9), summit)
    return e.astype(np.float32)


def craters(elevation: np.ndarray, volcanoes: list[Volcano], eruptions: int) -> np.ndarray:
    """Each vent's crater, after erosion: a hollow at the top (an extinct one fills with water)."""
    e = elevation.copy()
    for v in volcanoes:
        if e[v.x, v.y] > 0:
            e[v.x, v.y] -= CRATER[eruptions]
    return e


def warmth(shape, volcanoes: list[Volcano], eruptions: int) -> np.ndarray:
    """Degrees of warmth from the ground around each live volcano."""
    out = np.zeros(shape, np.float32)
    if not WARMTH[eruptions]:
        return out
    for v in volcanoes:
        d = _distance(*shape, v.x, v.y) / (v.radius * 2)
        out = np.maximum(out, WARMTH[eruptions] * np.clip(1 - d, 0, 1))
    return out


def ash(shape, volcanoes: list[Volcano], eruptions: int, fresh: bool) -> np.ndarray:
    """0..1 ash on each cell: fresh (from Active or Violent volcanoes, smothering, blown downwind),
    or old (any volcano: rich soil close round it)."""
    out = np.zeros(shape, np.float32)
    w, h = shape
    lat = (np.arange(h) + 0.5) / h * 2 - 1
    for v in volcanoes:
        if fresh:
            strength = ASH[eruptions]
            if not strength:
                return out
            wind = -1.0 if abs(lat[v.y]) < 0.33 else 1.0         # trade winds blow west, westerlies east
            reach = v.radius * (2.5 if eruptions == TW.ACTIVE else 4.5)
            cx = v.x + wind * reach * 0.6
            xs = np.arange(w, dtype=np.float32)[:, None]
            ys = np.arange(h, dtype=np.float32)[None, :]
            d = np.sqrt(((xs - cx) / reach) ** 2 + ((ys - v.y) * 2 / (reach * 0.45)) ** 2)
            out = np.maximum(out, strength * np.clip(1 - d, 0, 1) ** 0.7)
            near = _distance(w, h, v.x, v.y) / v.radius
            out = np.maximum(out, strength * np.clip(1 - near, 0, 1))
        else:
            d = _distance(w, h, v.x, v.y) / (v.radius * 2.5)
            out = np.maximum(out, np.clip(1 - d, 0, 1))
    return out


def lava(seed: int, elevation: np.ndarray, water: np.ndarray, flow_dx: np.ndarray, flow_dy: np.ndarray,
         volcanoes: list[Volcano], eruptions: int) -> np.ndarray:
    """The lava fields: flows run from each vent's rim downhill until they reach water."""
    out = np.zeros(elevation.shape, bool)
    if eruptions not in FLOWS:
        return out
    rng = _rng(seed, 113)
    w, h = elevation.shape
    count, length = FLOWS[eruptions]
    for v in volcanoes:
        for _ in range(count):
            angle = rng.uniform(0, 2 * math.pi)
            x = int(round(v.x + math.cos(angle) * 1.5))
            y = int(round(v.y + math.sin(angle) * 0.8))
            for _step in range(length):
                if not (0 <= x < w and 0 <= y < h) or water[x, y] or elevation[x, y] <= 0:
                    break
                out[x, y] = True
                if eruptions == TW.VIOLENT:                  # wide flows spill to the sides
                    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        nx, ny = x + dx, y + dy
                        if 0 <= nx < w and 0 <= ny < h and not water[nx, ny] and elevation[nx, ny] > 0 \
                                and rng.random() < 0.35:
                            out[nx, ny] = True
                dx, dy = int(flow_dx[x, y]), int(flow_dy[x, y])
                if not dx and not dy:
                    break
                x, y = x + dx, y + dy
    return out


def vent_mask(shape, volcanoes: list[Volcano]) -> np.ndarray:
    """The cells the volcano itself stands on: the vent and the steep top of the cone."""
    out = np.zeros(shape, bool)
    for v in volcanoes:
        out |= _distance(*shape, v.x, v.y) <= max(1.0, v.radius * 0.4)
    return out
