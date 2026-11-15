"""Mining: what's in the rock, region by region and deeper down, and breaking it with a pickaxe.

Every region has its own ore table (`ore_table`), the same every game: what you get for
breaking rock there, at each depth. The depth is 0 at the surface (boulders and rock
outcrops), a cave's level below it (1 to 5), 1 in a ravine. Shallow rock gives flint, coal and
copper; then iron, tin and coal; deeper iron and silver; deepest gold and jewels. Mountains,
hills and volcanoes are richest; each region also has deposits of its own, richer in some ores
and poorer in others. Most of the time broken rock gives nothing worth keeping.

Some ore shows in the rock (`ORE_VEIN`, a £ the colour of the ore, more of them deeper): those
always give their ore. With a pickaxe in your bag, walk into rock (a boulder, a rock outcrop,
a cave wall or a vein) to break it, unless you're wearing climbing gear, which climbs it; the
use menu breaks it either way. It's slow and tiring. The ground's left as rubble (in a cave,
cave floor). The edges of a cave can't be broken through.

A smith buys the ores (game/shop.py).
"""
from __future__ import annotations

import random
import zlib

import numpy as np

from . import biomes as B
from . import items
from . import tiles as T

PICK = "pickaxe"
BREAKABLE = {T.BOULDER: 20, T.ROCK: 40, T.CAVE_WALL: 45, T.ORE_VEIN: 45}   # minutes to break each
EFFORT = 2.5
NOTHING = None
DEPTHS = {   # depth -> ore -> weight, before the region's own richness; NOTHING is broken rock
    0: {NOTHING: 14, "flint": 6, "coal": 2, "copper ore": 2},
    1: {NOTHING: 10, "flint": 2, "coal": 4, "copper ore": 3, "tin ore": 2, "iron ore": 3},
    2: {NOTHING: 10, "coal": 4, "copper ore": 2, "tin ore": 3, "iron ore": 4},
    3: {NOTHING: 11, "coal": 2, "iron ore": 4, "silver nugget": 2},
    4: {NOTHING: 11, "iron ore": 3, "silver nugget": 3, "gold nugget": 1, "rough garnet": 1},
    5: {NOTHING: 12, "silver nugget": 2, "gold nugget": 2, "rough garnet": 1, "raw amethyst": 1,
        "uncut emerald": 1, "sapphire": 0.4, "ruby": 0.3},
}
RICH = {B.MOUNTAINS: 1.6, B.PEAKS: 1.6, B.HILLS: 1.4, B.VOLCANO: 1.8, B.LAVA_FIELD: 1.5, B.DOWNS: 1.1,
        B.DESERT: 1.1}
VEINS = (0.01, 0.025)        # share of rock faces showing a vein: at the surface, then each level down


def depth_of(level) -> int:
    kind = level.key[0]
    if kind == "region":
        return 0
    if kind == "cave":
        return min(5, level.key[3])
    return 1


def ore_table(world, x: int, y: int, depth: int) -> dict:
    """What breaking rock in region (x, y) at this depth gives: kind -> weight (None: nothing)."""
    depth = max(0, min(5, depth))
    rich = RICH.get(int(world.biome[x, y]), 0.8)
    out = {}
    for kind, weight in DEPTHS[depth].items():
        if kind is NOTHING:
            out[kind] = weight
            continue
        deposit = zlib.crc32(f"ore{world.seed},{x},{y},{kind}".encode()) / 0xFFFFFFFF   # the region's own
        out[kind] = weight * rich * (0.3 + 1.7 * deposit)
    return out


def roll(table: dict, rng, ores_only: bool = False):
    choices = [(k, w) for k, w in table.items() if not (ores_only and k in (NOTHING, "flint"))]
    total = sum(w for _, w in choices)
    pick = rng.random() * total
    for kind, weight in choices:
        pick -= weight
        if pick <= 0:
            return kind
    return choices[-1][0]


def place_veins(level, world, rng: random.Random) -> None:
    """Ore showing in rock faces beside open ground (cave walls, rock outcrops)."""
    t = level.tiles
    depth = depth_of(level)
    rock = (t == T.CAVE_WALL) if level.underground else (t == T.ROCK)
    walk = T.WALK[t]
    face = rock & (np.roll(walk, 1, 0) | np.roll(walk, -1, 0) | np.roll(walk, 1, 1) | np.roll(walk, -1, 1))
    face[[0, -1], :] = face[:, [0, -1]] = False
    share = VEINS[0] if depth == 0 else VEINS[1] * (1 + 0.25 * depth)
    table = ore_table(world, *level.region, depth)
    for x, y in zip(*np.nonzero(face)):
        if rng.random() < share:
            level.tiles[x, y] = T.ORE_VEIN
            level.ore[(int(x), int(y))] = roll(table, rng, ores_only=True)


def can_break(level, x: int, y: int) -> bool:
    if not level.in_bounds(x, y) or int(level.tiles[x, y]) not in BREAKABLE:
        return False
    return 0 < x < level.width - 1 and 0 < y < level.height - 1    # not the edge of the world


def break_rock(engine, x: int, y: int) -> str:
    """Breaks the rock at (x, y) with your pickaxe; what it gave goes in your bag."""
    level, p = engine.level, engine.player
    if not p.inventory.count(PICK):
        return "You'd need a pickaxe to break that."
    if not can_break(level, x, y):
        return "That won't break."
    if p.stamina < 10:
        return "You're too worn out to swing a pickaxe."
    tile = int(level.tiles[x, y])
    name = T.TILES[tile].name
    if tile == T.ORE_VEIN:
        got = level.ore.pop((x, y), None) or "iron ore"
    else:
        rng = random.Random(f"rock{level.key}{x},{y}")
        got = roll(ore_table(engine.world, *level.region, depth_of(level)), rng)
    level.tiles[x, y] = T.CAVE_FLOOR if level.underground else T.RUBBLE
    level._walk_costs = None
    level.fire = None                     # light reaches further now
    engine.pass_time(BREAKABLE[tile] / 60, effort=EFFORT)
    if got:
        p.inventory.add(got)
        return f"You break the {name} with your pickaxe and find {items.amount(got, 1)}."
    return f"You break the {name} with your pickaxe."
