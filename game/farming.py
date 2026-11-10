"""What grows and what grazes where, and how the fields change through the year.

A village grows the grain that suits its climate (the yearly mean temperature and how wet it
is), and keeps the animals that suit its land:

- grain:  rice where it's hot and wet, millet where it's hot and dry, rye in the cold north
          and on cold uplands, wheat in the temperate lands between
- herds:  reindeer in the cold, goats in mountains and dry scrub, sheep on hills and steppe,
          pigs in forest and jungle, cows on grassland and savanna; hens everywhere people live

Grain fields go through the year: green shoots in spring, tall and green in early summer,
ripe and gold at midsummer, stubble after the harvest, then bare fallow ground until spring.
In the tropics they're always growing. Rice paddies are flooded while the rice grows.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import biomes as B
from . import tiles as T
from .climate import MIDSUMMER, latitude, year_fraction

TROPICS = 0.2


@dataclass(frozen=True)
class Land:
    """The climate a settlement farms in."""
    biome: int
    temperature: float       # yearly mean, degrees C
    moisture: float          # 0 dry .. 1 wet
    lat: float               # -1 north pole .. 1 south pole


def land_at(world, x: int, y: int) -> Land:
    return Land(int(world.biome[x, y]), float(world.temperature[x, y]), float(world.moisture[x, y]),
                float(latitude(y, world.height)))


def grain_for(land: Land) -> int:
    """The grain field tile that suits this climate."""
    if land.temperature >= 20:
        return T.RICE if land.moisture >= 0.55 or land.biome in (B.JUNGLE, B.SWAMP) else T.MILLET
    if land.temperature < 4 or land.biome in (B.TAIGA, B.TUNDRA, B.MOUNTAINS):
        return T.RYE
    if land.moisture < 0.15 or land.biome == B.DESERT:
        return T.MILLET
    return T.WHEAT


def herd_for(land: Land) -> str:
    """The animal kept in this settlement's pastures."""
    b = land.biome
    if b in (B.TUNDRA, B.TAIGA, B.GLACIER) or land.temperature < 2:
        return "reindeer"
    if b in (B.MOUNTAINS, B.PEAKS, B.DESERT, B.SHRUBLAND):
        return "goat"
    if b in (B.HILLS, B.STEPPE):
        return "sheep"
    if b in (B.FOREST, B.JUNGLE, B.SWAMP):
        return "pig"
    return "cow"


@dataclass(frozen=True)
class Animal:
    char: str
    colour: tuple
    sound: str
    plural: str
    minutes: float           # to wander one tile


ANIMALS = {
    "cow": Animal("C", (215, 190, 160), "moos", "cows", 3.0),
    "sheep": Animal("s", (235, 235, 225), "bleats", "sheep", 2.5),
    "goat": Animal("g", (185, 160, 125), "bleats", "goats", 2.0),
    "pig": Animal("p", (235, 160, 165), "grunts", "pigs", 2.5),
    "reindeer": Animal("R", (175, 135, 95), "snorts", "reindeer", 2.5),
    "horse": Animal("H", (170, 115, 75), "snorts", "horses", 2.0),
    "hen": Animal("h", (240, 225, 185), "clucks", "hens", 1.2),
    "dog": Animal("d", (200, 150, 90), "barks", "dogs", 0.9),
    "cat": Animal("c", (230, 170, 110), "meows", "cats", 1.3),
}
PETS = ("dog", "cat")         # a town's pet: wanders the town and follows you about


# ----------------------------------------------------------------- the year in the fields

def crop_stage(lat: float, minutes: float) -> str:
    """Where the grain is in its year: "shoots", "growing", "ripe", "stubble" or "fallow"."""
    if abs(lat) < TROPICS:
        return "growing"
    phase = (float(year_fraction(minutes)) - MIDSUMMER + (0.5 if lat > 0 else 0.0)) % 1.0   # 0 midsummer
    if phase < 0.08:
        return "ripe"
    if phase < 0.2:
        return "stubble"
    if phase < 0.7:
        return "fallow"
    if phase < 0.88:
        return "shoots"
    return "growing"


FALLOW = (",", (125, 100, 70), (60, 46, 32))
STUBBLE = (",", (200, 175, 110), (85, 70, 40))
SHOOTS = (".", (140, 205, 90), (52, 70, 34))
GROWING = ('"', (95, 165, 70), (45, 70, 32))
# (tile, stage) -> (glyph, fg, bg); stages not listed use the tile's own look (ripe)
CROP_LOOKS = {
    (T.WHEAT, "fallow"): FALLOW, (T.WHEAT, "stubble"): STUBBLE, (T.WHEAT, "shoots"): SHOOTS,
    (T.WHEAT, "growing"): GROWING,
    (T.RYE, "fallow"): FALLOW, (T.RYE, "stubble"): STUBBLE, (T.RYE, "shoots"): SHOOTS,
    (T.RYE, "growing"): ('"', (110, 150, 85), (45, 62, 35)),
    (T.MILLET, "fallow"): FALLOW, (T.MILLET, "stubble"): STUBBLE, (T.MILLET, "shoots"): SHOOTS,
    (T.MILLET, "growing"): ('"', (140, 170, 80), (65, 70, 35)),
    (T.RICE, "fallow"): (",", (110, 95, 70), (50, 45, 35)),
    (T.RICE, "stubble"): STUBBLE,
    (T.RICE, "shoots"): ("~", (130, 200, 110), (35, 70, 90)),
    (T.RICE, "ripe"): ('"', (215, 195, 95), (70, 75, 55)),
    (T.CROPS, "fallow"): (",", (120, 100, 70), (60, 46, 32)),
}
STAGE_WORDS = {"shoots": "green shoots", "growing": "growing", "ripe": "ripe", "stubble": "harvested",
               "fallow": "lying fallow"}
