"""Chasms in caves, fissures in the hills, the ravines below them, and the rope grapple.

- Chasms split some cave levels (not the deepest): a dark crack across the cavern floor. The
  stairs are always left joined; fall in and you land a level down, hurt, with no way back up
  but the stairs: no light reaches down there to throw a grapple by.
- Fissures crack open a few hill, mountain, downs and volcano regions (FISSURE_SHARE), never in
  a settlement: a jagged split in the ground. Fall in and you're in a ravine: a narrow canyon of
  rock open to the sky, with no way out but a rope grapple, thrown up to the light.

Either is a step you take twice: the first time you stop at the edge and are warned; the second
time you go over. Walks never route over them.

A rope grapple (bought, or made from rope and nails: game/crafting.py) climbs out of a ravine
only while there's light from above to see where to throw it: by day, not at night, and your own
torch doesn't help. It isn't used up.
"""
from __future__ import annotations

import random
import zlib

import numpy as np

from . import biomes as B
from . import gear
from . import items
from . import tiles as T
from .level import Level

GRAPPLE = "rope grapple"
FISSURE_SHARE = 0.12
FISSURE_BIOMES = (B.HILLS, B.MOUNTAINS, B.PEAKS, B.DOWNS, B.VOLCANO)
FISSURE_LENGTH = (15, 40)
CHASM_SHARE = 0.6            # of cave levels above the deepest
FALL = {"chasm": (3, 8), "fissure": (5, 10)}
SKY_LIGHT = 0.05             # daylight enough to see the rim by
CLIMB_MINUTES = 10
CLIMB_EFFORT = 3.0
RAVINE_W, RAVINE_H = 70, 13


def has_fissure(world, x: int, y: int, site) -> bool:
    if site is not None or int(world.biome[x, y]) not in FISSURE_BIOMES:
        return False
    return zlib.crc32(f"fissure{world.seed},{x},{y}".encode()) / 0xFFFFFFFF < FISSURE_SHARE


def crack(level, rng: random.Random, tile: int, length: int, on, start=None) -> list[tuple[int, int]]:
    """A jagged crack of `tile` over the tiles where `on` is true, wandering from `start`."""
    w, h = level.tiles.shape
    cells = list(zip(*np.nonzero(on)))
    if not cells:
        return []
    x, y = start if start is not None else (int(v) for v in cells[rng.randrange(len(cells))])
    angle = rng.random() * 2 * np.pi
    out = []
    for _ in range(length):
        angle += rng.uniform(-0.6, 0.6)
        for wx, wy in ((x, y), (x + rng.choice((-1, 1)), y)) if rng.random() < 0.4 else ((x, y),):
            if 1 <= wx < w - 1 and 1 <= wy < h - 1 and on[wx, wy] and (wx, wy) not in level.exits:
                level.tiles[wx, wy] = tile
                out.append((wx, wy))
        x = int(round(x + 2 * np.cos(angle)))
        y = int(round(y + np.sin(angle)))
        if not (1 <= x < w - 1 and 1 <= y < h - 1):
            break
    return out


def carve_fissure(level, world, x: int, y: int, site, rng: random.Random) -> None:
    if not has_fissure(world, x, y, site):
        return
    t = level.tiles
    ground = T.WALK[t] & T.NATURAL[t] & ~T.WATERY[t]
    crack(level, rng, T.FISSURE, rng.randint(*FISSURE_LENGTH), ground)


def carve_chasm(level, rng: random.Random, up, down) -> None:
    """A chasm across a cave level, only if the stairs up and down stay joined without it."""
    from .structures import largest_area
    if rng.random() >= CHASM_SHARE:
        return
    for _ in range(5):
        saved = level.tiles.copy()
        floor = level.tiles == T.CAVE_FLOOR
        made = crack(level, rng, T.CHASM, rng.randint(25, 60), floor)
        joined = largest_area(T.WALK[level.tiles])
        if made and joined[up] and joined[down]:
            return
        level.tiles[:] = saved


def ravine_level(key: tuple, site, rng: random.Random) -> Level:
    """A narrow canyon open to the sky: rock walls, a stony floor, old bones and flint, a few
    veins of ore, and nothing to climb out by."""
    w, h = RAVINE_W, RAVINE_H
    t = np.full((w, h), T.ROCK, np.uint8)
    mid = h / 2
    for x in range(2, w - 2):
        wander = np.sin(x / 7.0 + rng.random() * 0.4) * 2.0
        half = 1.5 + rng.random() * 1.5
        for y in range(1, h - 1):
            if abs(y - (mid + wander)) <= half:
                t[x, y] = rng.choice([T.SCREE, T.SCREE, T.DIRT, T.RUBBLE])
    level = Level(key, "The bottom of a ravine", t, {}, underground=False, indoor_air=12.0)
    floor = list(zip(*np.nonzero(T.WALK[t])))
    for _ in range(rng.randint(3, 7)):
        items.drop(level, *(int(v) for v in rng.choice(floor)), rng.choice(["flint", "flint", "old bone", "stick"]))
    if rng.random() < 0.4:                      # someone fell in before you
        x, y = (int(v) for v in rng.choice(floor))
        items.drop(level, x, y, "old bone")
        items.drop(level, x, y, rng.choice(["coin", "rusty dagger", "coil of rope", "flask of oil"]))
    return level


def fall(engine, x: int, y: int) -> str:
    """Over the edge of the chasm or fissure at (x, y)."""
    level, p = engine.level, engine.player
    tile = int(level.tiles[x, y])
    what = "chasm" if tile == T.CHASM else "fissure"
    hurt = engine.rng.randint(*FALL[what])
    if what == "chasm":
        below = (level.key[0], level.key[1], level.key[2], level.key[3] + 1)
        nxt = engine.get_level(below)
        lx, ly = nxt.nearest_walkable(min(x, nxt.width - 1), min(y, nxt.height - 1))
        text = f"You fall into the chasm and land hard on the level below! ({hurt})"
    else:
        nxt = engine.get_level(("ravine", *level.region, 1))
        lx, ly = nxt.nearest_walkable(nxt.width // 2, nxt.height // 2)
        rim = engine.lx, engine.ly                    # where you stood: where the grapple brings you
        nxt.way_up = (level.key, rim)
        text = f"The ground gives way: you fall into the fissure, to the bottom of a ravine! ({hurt})"
    engine.edge = None
    if not p.god:
        p.health -= hurt
    engine.level, engine.lx, engine.ly = nxt, lx, ly
    if p.health <= 0 and not p.god:
        p.health, p.alive, p.cause = 0.0, False, f"fell into a {what}"
    engine.disturbed = True
    engine.pass_time(1 / 60)
    return text


def can_climb_out(engine) -> tuple[bool, str]:
    level = engine.level
    if level is None or level.key[0] != "ravine":
        return False, "There's nothing up there to throw a grapple at."
    if not engine.player.inventory.count(GRAPPLE):
        return False, "You'd need a rope grapple to climb out."
    if engine.now.light < SKY_LIGHT:
        return False, "It's too dark to see the rim: wait for daylight."
    return True, ""


def climb_out(engine) -> str:
    """Throws the grapple up to the rim and climbs out, back beside where you fell in."""
    ok, why = can_climb_out(engine)
    if not ok:
        return why
    p = engine.player
    if p.stamina < gear.CLIMB_STAMINA:
        return "You're too worn out to climb."
    c = engine.now
    if engine.rng.random() < gear.slip_chance(p, c.raining or c.snowing, False):
        hurt = engine.rng.randint(*gear.FALL)
        if not p.god:
            p.health -= hurt
        engine.pass_time(CLIMB_MINUTES / 60, effort=CLIMB_EFFORT)
        return f"The grapple slips loose and you slide back down. ({hurt})"
    key, rim = getattr(engine.level, "way_up", None) or (("region", *engine.level.region), None)
    up = engine.get_level(key)
    engine.level = up
    engine.lx, engine.ly = up.nearest_walkable(*(rim or (up.width // 2, up.height // 2)))
    engine.pass_time(CLIMB_MINUTES / 60, effort=CLIMB_EFFORT)
    return "You throw the grapple up; it bites on the rim, and you climb out into the open."
