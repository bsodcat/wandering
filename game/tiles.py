"""Local map tiles: what each looks like, whether you can walk through or see past it, and what
it costs to cross. Like biomes, the ids index numpy lookup tables so a whole map is coloured or
tested at once."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Tile:
    id: int
    name: str
    char: str
    fg: tuple[int, int, int]
    bg: tuple[int, int, int]
    walk: bool = True
    see: bool = True          # light and sight pass through
    minutes: float = 0.6      # to cross one tile
    roof: bool = False        # under a roof: out of the weather
    soak: float = 0.0         # wetness each step adds
    natural: bool = True      # open ground that can be built on, snowed on, cleared


TILES = [
    Tile(0, "deep water", "≈", (60, 100, 190), (12, 30, 80), walk=False, natural=False),
    Tile(1, "shallow water", "~", (110, 160, 230), (30, 70, 140), minutes=2.5, soak=12, natural=False),
    Tile(2, "sand", ".", (225, 205, 145), (150, 130, 85)),
    Tile(3, "grass", ".", (110, 170, 70), (40, 75, 30)),
    Tile(4, "tall grass", '"', (140, 190, 80), (45, 80, 32), minutes=0.9),
    Tile(5, "dirt", ".", (160, 130, 90), (75, 58, 40)),
    Tile(6, "mud", ",", (120, 100, 70), (55, 45, 32), minutes=1.6, soak=2),
    Tile(7, "snow", ".", (235, 240, 250), (170, 178, 195), minutes=1.1),
    Tile(8, "ice", "·", (210, 230, 250), (140, 170, 200), minutes=1.2),
    Tile(9, "tree trunk", "O", (150, 105, 60), (45, 34, 22), walk=False),   # leaves: game/trees.py
    Tile(10, "pine trunk", "O", (125, 85, 55), (38, 30, 22), walk=False),
    Tile(11, "jungle tree trunk", "O", (160, 135, 85), (40, 36, 22), walk=False),
    Tile(12, "bush", "♠", (95, 150, 70), (40, 72, 30), minutes=1.5),
    Tile(13, "boulder", "•", (160, 155, 145), (70, 68, 62), walk=False),
    Tile(14, "rock", "▲", (140, 132, 125), (85, 80, 75), walk=False, see=False, natural=False),
    Tile(15, "scree", ",", (150, 142, 130), (80, 76, 70), minutes=1.3),
    Tile(16, "road", ".", (190, 160, 110), (100, 80, 55), minutes=0.4, natural=False),
    Tile(17, "street", "·", (180, 175, 165), (85, 82, 78), minutes=0.35, natural=False),
    Tile(18, "bridge", "=", (200, 160, 100), (90, 65, 40), minutes=0.4, natural=False),
    Tile(19, "path", ".", (175, 145, 100), (85, 68, 46), minutes=0.45, natural=False),
    Tile(20, "wooden floor", ".", (170, 125, 80), (70, 48, 30), minutes=0.4, roof=True, natural=False),
    Tile(21, "stone floor", ".", (165, 160, 155), (60, 58, 56), minutes=0.4, roof=True, natural=False),
    Tile(22, "wall", "#", (170, 150, 120), (95, 80, 60), walk=False, see=False, natural=False),
    Tile(23, "stone wall", "#", (165, 165, 170), (90, 90, 95), walk=False, see=False, natural=False),
    Tile(24, "door", "+", (220, 170, 90), (90, 60, 30), minutes=0.5, roof=True, natural=False),
    Tile(25, "bed", "Θ", (200, 120, 110), (70, 48, 30), minutes=1.0, roof=True, natural=False),
    Tile(26, "table", "π", (200, 150, 90), (70, 48, 30), walk=False, roof=True, natural=False),
    Tile(27, "hearth", "☼", (255, 160, 60), (110, 40, 20), walk=False, roof=True, natural=False),
    Tile(28, "well", "o", (150, 190, 230), (80, 80, 85), walk=False, natural=False),
    Tile(29, "market stall", "∩", (230, 170, 80), (110, 60, 40), walk=False, natural=False),
    Tile(30, "vegetable garden", '"', (210, 190, 80), (85, 70, 30), minutes=1.0, natural=False),
    Tile(31, "fence", "#", (150, 110, 70), (55, 42, 30), walk=False, natural=False),
    Tile(32, "dock", "=", (180, 140, 90), (70, 50, 32), minutes=0.4, natural=False),
    Tile(33, "rubble", ",", (150, 145, 135), (65, 62, 58), minutes=1.3, natural=False),
    Tile(34, "cave floor", ".", (130, 120, 105), (35, 32, 28), minutes=0.7, roof=True, natural=False),
    Tile(35, "cave wall", "#", (110, 100, 90), (55, 50, 45), walk=False, see=False, roof=True, natural=False),
    Tile(36, "stairs down", ">", (255, 230, 120), (50, 45, 40), minutes=0.6, natural=False),
    Tile(37, "stairs up", "<", (255, 230, 120), (50, 45, 40), minutes=0.6, natural=False),
    Tile(38, "battlement", "▪", (175, 175, 180), (90, 90, 95), walk=False, natural=False),
    Tile(39, "barrel", "o", (170, 120, 70), (60, 45, 30), walk=False, roof=True, natural=False),
    Tile(40, "dry grass", '"', (190, 175, 95), (90, 80, 40), minutes=0.8),
    Tile(41, "reeds", "|", (120, 160, 90), (40, 62, 40), minutes=1.4, soak=3),
    Tile(42, "flagstones", ".", (175, 172, 165), (75, 73, 70), minutes=0.4, natural=False),
    Tile(43, "torch", "¡", (255, 190, 80), (95, 80, 60), walk=False, see=False, natural=False),   # on a wall
    # grain fields: their look changes with the season (farming.py)
    Tile(44, "wheat", '"', (215, 185, 80), (95, 80, 35), minutes=1.0, natural=False),
    Tile(45, "rye", '"', (180, 170, 110), (80, 72, 45), minutes=1.0, natural=False),
    Tile(46, "rice paddy", '"', (120, 190, 90), (40, 75, 85), minutes=1.8, soak=4, natural=False),
    Tile(47, "millet", '"', (200, 160, 90), (90, 70, 40), minutes=1.0, natural=False),
    # trades
    Tile(48, "bread oven", "■", (235, 120, 60), (90, 40, 25), walk=False, roof=True, natural=False),
    Tile(49, "counter", "▬", (180, 135, 85), (70, 48, 30), walk=False, roof=True, natural=False),
    Tile(50, "meat hooks", "¶", (210, 95, 95), (70, 48, 30), walk=False, roof=True, natural=False),
    Tile(51, "inn sign", "≡", (245, 205, 95), (95, 80, 60), walk=False, see=False, natural=False),
    Tile(52, "woodpile", "═", (170, 120, 70), (60, 42, 26), walk=False, natural=False),
    Tile(53, "tree stump", "°", (160, 115, 70), (55, 45, 30), minutes=1.2, natural=False),
    Tile(54, "trough", "▄", (150, 115, 75), (55, 42, 30), walk=False, natural=False),
]
assert all(t.id == i for i, t in enumerate(TILES))
ID = {t.name: t.id for t in TILES}

(DEEP_WATER, WATER, SAND, GRASS, TALL_GRASS, DIRT, MUD, SNOW, ICE, TREE, PINE, JUNGLE_TREE, BUSH,
 BOULDER, ROCK, SCREE, ROAD, STREET, BRIDGE, PATH, WOOD_FLOOR, STONE_FLOOR, WALL, STONE_WALL, DOOR,
 BED, TABLE, HEARTH, WELL, STALL, CROPS, FENCE, DOCK, RUBBLE, CAVE_FLOOR, CAVE_WALL, STAIRS_DOWN,
 STAIRS_UP, BATTLEMENT, BARREL, DRY_GRASS, REEDS, FLAGSTONES, TORCH, WHEAT, RYE, RICE, MILLET, OVEN,
 COUNTER, HOOKS, SIGN, WOODPILE, STUMP, TROUGH) = range(len(TILES))
GRAINS = [WHEAT, RYE, RICE, MILLET]
FIELDS = GRAINS + [CROPS]

CHAR = np.array([ord(t.char) for t in TILES], dtype=np.int32)
FG = np.array([t.fg for t in TILES], dtype=np.float32)
BG = np.array([t.bg for t in TILES], dtype=np.float32)
WALK = np.array([t.walk for t in TILES], dtype=bool)
SEE = np.array([t.see for t in TILES], dtype=bool)
MINUTES = np.array([t.minutes for t in TILES], dtype=np.float32)
ROOF = np.array([t.roof for t in TILES], dtype=bool)
SOAK = np.array([t.soak for t in TILES], dtype=np.float32)
NATURAL = np.array([t.natural for t in TILES], dtype=bool)
WATERY = np.isin(np.arange(len(TILES)), [DEEP_WATER, WATER])
GROUND = NATURAL & WALK                      # open ground a building or field can go on
CLEARABLE = NATURAL | np.isin(np.arange(len(TILES)), [TREE, PINE, JUNGLE_TREE, BOULDER])
SNOWS_ON = np.isin(np.arange(len(TILES)), [GRASS, TALL_GRASS, DIRT, SAND, DRY_GRASS, SCREE, MUD, BUSH, CROPS, PATH, ROAD,
                                             WHEAT, RYE, MILLET, STUMP])
