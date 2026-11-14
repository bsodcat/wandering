"""Biomes: what each kind of land or water looks like, and what it's like to cross.

The ids index the numpy lookup tables below, so the world can store biomes as a uint8 array
and the renderer can colour a whole view in one step.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Biome:
    id: int
    name: str
    char: str
    fg: tuple[int, int, int]
    bg: tuple[int, int, int]
    travel: float     # hours to cross one world cell on foot; 0 means you can't walk it
    shelter: float    # 0..1: how much it cuts wind, rain and sun (a forest more than a plain)
    wet: float = 0.0  # wetness each crossing adds (swamps)
    blocks_view: bool = False  # mountains hide what's behind them


BIOMES = [
    Biome(0, "Deep ocean", "≈", (40, 70, 160), (8, 18, 55), 0, 0),
    Biome(1, "Ocean", "~", (70, 115, 200), (18, 42, 95), 0, 0),
    Biome(2, "Lake", "~", (100, 150, 225), (28, 60, 120), 0, 0),
    Biome(3, "Beach", ".", (230, 212, 150), (125, 108, 70), 1.0, 0.0),
    Biome(4, "Glacier", "·", (235, 240, 250), (175, 185, 205), 3.0, 0.0),
    Biome(5, "Tundra", '"', (175, 185, 165), (85, 92, 82), 1.5, 0.05),
    Biome(6, "Taiga", "♠", (70, 120, 90), (22, 48, 34), 2.0, 0.6),
    Biome(7, "Steppe", ",", (175, 172, 105), (88, 86, 50), 1.0, 0.05),
    Biome(8, "Grassland", '"', (115, 175, 70), (45, 85, 32), 1.0, 0.05),
    Biome(9, "Shrubland", ",", (155, 155, 85), (78, 78, 44), 1.2, 0.15),
    Biome(10, "Forest", "♣", (55, 145, 65), (18, 62, 28), 2.0, 0.6),
    Biome(11, "Swamp", '"', (95, 125, 75), (38, 58, 44), 3.0, 0.3, wet=40),
    Biome(12, "Desert", ".", (232, 202, 125), (150, 120, 68), 1.5, 0.0),
    Biome(13, "Savanna", '"', (195, 182, 90), (108, 98, 44), 1.2, 0.1),
    Biome(14, "Jungle", "♣", (45, 165, 75), (12, 68, 30), 3.0, 0.7),
    Biome(15, "Hills", "^", (155, 145, 105), (78, 74, 54), 2.0, 0.2),
    Biome(16, "Mountains", "▲", (165, 155, 145), (78, 74, 70), 4.0, 0.2, blocks_view=True),
    Biome(17, "Snowy peaks", "▲", (245, 245, 252), (150, 152, 168), 8.0, 0.1, blocks_view=True),
    Biome(18, "Volcano", "▲", (215, 95, 55), (70, 38, 32), 5.0, 0.05, blocks_view=True),   # game/volcanoes.py
    Biome(19, "Lava field", "░", (120, 100, 95), (45, 36, 34), 2.5, 0.0),
    Biome(20, "Pastureland", '"', (140, 195, 85), (52, 96, 36), 1.0, 0.05),   # lush open grazing land
    Biome(21, "Downs", "∩", (150, 170, 95), (66, 84, 44), 1.6, 0.1),           # rolling grassy hills, few trees
]
assert all(b.id == i for i, b in enumerate(BIOMES))
BY_NAME = {b.name: b for b in BIOMES}

DEEP_OCEAN, OCEAN, LAKE, BEACH, GLACIER, TUNDRA, TAIGA, STEPPE, GRASSLAND, SHRUBLAND, FOREST, \
    SWAMP, DESERT, SAVANNA, JUNGLE, HILLS, MOUNTAINS, PEAKS, VOLCANO, LAVA_FIELD, PASTURE, DOWNS = range(len(BIOMES))
WATER = (DEEP_OCEAN, OCEAN, LAKE)

# Lookup tables, indexed by biome id.
CHAR = np.array([ord(b.char) for b in BIOMES], dtype=np.int32)
FG = np.array([b.fg for b in BIOMES], dtype=np.float32)
BG = np.array([b.bg for b in BIOMES], dtype=np.float32)
TRAVEL = np.array([b.travel for b in BIOMES], dtype=np.float32)
SHELTER = np.array([b.shelter for b in BIOMES], dtype=np.float32)
BLOCKS_VIEW = np.array([b.blocks_view for b in BIOMES], dtype=bool)
