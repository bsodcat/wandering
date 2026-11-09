"""Rooms and corridors: a dungeon-style local map. Not used yet; kept for building interiors and dungeons when regions open into local maps."""
from __future__ import annotations

import random

import numpy as np
import tcod

FLOOR_LIT, FLOOR_DARK = (200, 180, 120), (60, 60, 90)
WALL_LIT, WALL_DARK = (150, 130, 90), (40, 40, 70)


class GameMap:
    """Arrays are indexed [x, y], the same order as a Console made with order="F"."""

    def __init__(self, width: int, height: int):
        self.width, self.height = width, height
        self.walkable = np.zeros((width, height), dtype=bool)  # floor; everything else is wall
        self.visible = np.zeros((width, height), dtype=bool)   # in view right now
        self.explored = np.zeros((width, height), dtype=bool)  # ever seen

    @property
    def transparent(self) -> np.ndarray:
        return self.walkable  # walls block sight, floor doesn't

    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height

    def update_fov(self, x: int, y: int, radius: int = 8) -> None:
        self.visible = tcod.map.compute_fov(self.transparent, (x, y), radius,
                                            algorithm=tcod.constants.FOV_SYMMETRIC_SHADOWCAST)
        self.explored |= self.visible

    def render(self, console: tcod.console.Console) -> None:
        """Lit tiles in view, dim ones seen before, nothing for the rest."""
        wall = ~self.walkable
        fg = np.where(self.visible[..., None],
                      np.where(wall[..., None], WALL_LIT, FLOOR_LIT),
                      np.where(wall[..., None], WALL_DARK, FLOOR_DARK))
        ch = np.where(wall, ord("#"), ord("."))
        view = console.rgb[: self.width, : self.height]
        view["ch"] = np.where(self.visible | self.explored, ch, ord(" "))
        view["fg"] = fg
        view["bg"] = (0, 0, 0)


Room = tuple[int, int, int, int]  # x1, y1, x2, y2 including the walls around it


def center(room: Room) -> tuple[int, int]:
    return (room[0] + room[2]) // 2, (room[1] + room[3]) // 2


def overlaps(a: Room, b: Room) -> bool:
    return a[0] <= b[2] and a[2] >= b[0] and a[1] <= b[3] and a[3] >= b[1]


def tunnel(m: GameMap, start: tuple[int, int], end: tuple[int, int], rng: random.Random) -> None:
    """An L-shaped corridor, turning one way or the other at random."""
    (x1, y1), (x2, y2) = start, end
    corner = (x2, y1) if rng.random() < 0.5 else (x1, y2)
    for a, b in ((start, corner), (corner, end)):
        for x, y in tcod.los.bresenham(a, b).tolist():
            m.walkable[x, y] = True


def generate(width: int, height: int, rng: random.Random, max_rooms: int = 30,
             min_size: int = 6, max_size: int = 10) -> tuple[GameMap, tuple[int, int], list[Room]]:
    """Rooms joined by corridors, each to the one before. Returns the map, where the player
    starts (the middle of the first room) and the rooms."""
    m = GameMap(width, height)
    rooms: list[Room] = []
    for _ in range(max_rooms):
        w, h = rng.randint(min_size, max_size), rng.randint(min_size, max_size)
        x, y = rng.randint(0, width - w - 1), rng.randint(0, height - h - 1)
        room = (x, y, x + w, y + h)
        if any(overlaps(room, other) for other in rooms):
            continue
        m.walkable[x + 1: x + w, y + 1: y + h] = True
        if rooms:
            tunnel(m, center(rooms[-1]), center(room), rng)
        rooms.append(room)
    return m, center(rooms[0]), rooms
