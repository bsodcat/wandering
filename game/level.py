"""A local map: one world region opened up, or a cave, crypt or tower floor linked to it.

Levels are named by a key: ("region", x, y) for the land itself, and ("cave", x, y, depth),
("crypt", x, y, depth) or ("tower", x, y, floor) for what's under or above it. Stairs are exits:
each maps a tile to the key of the level it leads to, and the level at the other end has an
exit leading back, which is where you arrive.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from . import tiles as T


@dataclass
class Building:
    kind: str                  # "house", "inn", "bakery", "butcher", "shed", "ruin"
    name: str
    x0: int
    y0: int
    w: int
    h: int
    door: tuple

    def contains(self, x: int, y: int) -> bool:
        return self.x0 <= x < self.x0 + self.w and self.y0 <= y < self.y0 + self.h

    def floor(self, tiles: np.ndarray) -> list[tuple[int, int]]:
        """The tiles inside you can stand on."""
        return [(x, y) for x in range(self.x0 + 1, self.x0 + self.w - 1)
                for y in range(self.y0 + 1, self.y0 + self.h - 1) if T.WALK[tiles[x, y]]]


@dataclass
class Place:
    kind: str                  # "field", "pasture", "pier", "shore", "camp", "green"
    name: str
    tiles: list                # where someone working or grazing here can be
    animal: str = ""           # what grazes a pasture


@dataclass
class Level:
    key: tuple
    name: str
    tiles: np.ndarray                                  # uint8 tile ids, indexed [x, y]
    exits: dict = field(default_factory=dict)          # (x, y) -> key of the level it leads to
    underground: bool = False                          # no sky: no sun, no weather
    indoor_air: float = 18.0                           # degrees C under this level's roofs
    lookout: bool = False                              # high up: you can see the land around
    explored: np.ndarray | None = None
    canopy: np.ndarray | None = None                   # the layer above: leaves over each tile (trees.py)
    boughs: np.ndarray | None = None                   # branch glyphs, shown when the leaves are down
    fire: tuple | None = field(default=None, repr=False)   # firelight, worked out when first drawn (light.py)
    buildings: list = field(default_factory=list)      # Building: houses, shops, the inn
    places: list = field(default_factory=list)         # Place: fields, pastures, the pier, a lumber camp
    actors: list = field(default_factory=list)         # people and animals (people.py)
    sim_minutes: float | None = None                   # the clock when the actors were last moved
    crop: int | None = None                            # the grain grown here, if any
    elev: np.ndarray | None = None                     # ground height in levels (elevation.py)
    items: dict = field(default_factory=dict)          # (x, y) -> [item kind, ...] lying there
    buried: dict = field(default_factory=dict)         # (x, y) -> (item kind, how many) under the ground
    dug: dict = field(default_factory=dict)            # (x, y) -> [the ground it was, when rain first fell on it]
    stores: dict = field(default_factory=dict)         # (x, y) -> Inventory: what's in a barrel, once opened
    creatures: list = field(default_factory=list)      # wild things (game/wild.py)
    wild_minutes: float | None = None                  # the clock when they were last moved
    wild_spec: list = field(default_factory=list)      # (kind, how many, home, reach): small game that comes back
    camp: dict = field(default_factory=dict)           # a goblin camp: "hearth", "store", "beds", "stairs"
    noises: list = field(default_factory=list)         # (x, y, when, how far it carries): what creatures hear
    scent: np.ndarray | None = None                    # when something last passed each tile (for wolves)
    trail: np.ndarray | None = None                    # how worn each tile is by wolves' feet

    def __post_init__(self):
        if self.explored is None:
            self.explored = np.zeros(self.tiles.shape, dtype=bool)
        if self.canopy is None:
            self.canopy = np.zeros(self.tiles.shape, dtype=np.uint8)
        if self.boughs is None:
            self.boughs = np.zeros(self.tiles.shape, dtype=np.int32)
        if self.elev is None:
            self.elev = np.zeros(self.tiles.shape, dtype=np.int16)
        if self.scent is None:
            self.scent = np.full(self.tiles.shape, -1e9, dtype=np.float64)
        if self.trail is None:
            self.trail = np.zeros(self.tiles.shape, dtype=np.int16)

    @property
    def region(self) -> tuple[int, int]:
        return self.key[1], self.key[2]

    @property
    def surface(self) -> bool:
        return self.key[0] == "region"

    @property
    def width(self) -> int:
        return self.tiles.shape[0]

    @property
    def height(self) -> int:
        return self.tiles.shape[1]

    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height

    def walkable(self, x: int, y: int) -> bool:
        return self.in_bounds(x, y) and bool(T.WALK[self.tiles[x, y]])

    def arrival(self, from_key: tuple) -> tuple[int, int] | None:
        """The stairs that lead back to `from_key`: where you arrive from there."""
        for pos, key in self.exits.items():
            if key == from_key:
                return pos
        return None

    def building_at(self, x: int, y: int):
        return next((b for b in self.buildings if b.contains(x, y)), None)

    def nearest_walkable(self, x: float, y: float) -> tuple[int, int]:
        """The walkable tile closest to (x, y), counting a row as two columns wide on screen."""
        xs, ys = np.nonzero(T.WALK[self.tiles])
        if not len(xs):
            return int(x), int(y)
        i = int(np.argmin((xs - x) ** 2 + (2 * (ys - y)) ** 2))
        return int(xs[i]), int(ys[i])
