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
class Level:
    key: tuple
    name: str
    tiles: np.ndarray                                  # uint8 tile ids, indexed [x, y]
    exits: dict = field(default_factory=dict)          # (x, y) -> key of the level it leads to
    underground: bool = False                          # no sky: no sun, no weather
    indoor_air: float = 18.0                           # degrees C under this level's roofs
    lookout: bool = False                              # high up: you can see the land around
    explored: np.ndarray | None = None

    def __post_init__(self):
        if self.explored is None:
            self.explored = np.zeros(self.tiles.shape, dtype=bool)

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

    def nearest_walkable(self, x: float, y: float) -> tuple[int, int]:
        """The walkable tile closest to (x, y), counting a row as two columns wide on screen."""
        xs, ys = np.nonzero(T.WALK[self.tiles])
        if not len(xs):
            return int(x), int(y)
        i = int(np.argmin((xs - x) ** 2 + (2 * (ys - y)) ** 2))
        return int(xs[i]), int(ys[i])
