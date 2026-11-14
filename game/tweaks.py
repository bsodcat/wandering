"""World settings: the dials you can turn in Create a World before the land is made.

Each setting is a short list of steps with a sensible middle (the "Normal" world). A world
keeps its settings (World.tweaks), so a time skip remakes it with the same ones, and the same
seed, history and settings always make the same world.

    Land          how much of the map is above the sea
    Islands       small islands out at sea: none at all, up to whole archipelagos
    Mountains     how high and how many the ranges are
    Rainfall      how wet the winds are
    Temperature   the whole world warmer or colder
    Vegetation    how thickly things grow: biomes lean drier or greener, and local maps have
                  fewer or more trees, bushes and reeds
    Lakes         how many basins hold water (and, at Many or Lots, extra hollows to fill)
    Aquifers      groundwater: it feeds springs, which start rivers, and keeps dry country
                  green (oases in the desert); it rises into holes you dig
    Population    how many towns, villages and inns
    Volcanoes     how many (game/volcanoes.py), on the mountain ranges and out at sea
    Eruptions     how lively they are: Extinct, Dormant, Active or Violent

The settings are stored as indices into each step list, so a Tweaks is small and hashable
(the title screen caches worlds by it).
"""
from __future__ import annotations

from dataclasses import dataclass, fields, replace


@dataclass(frozen=True)
class Setting:
    name: str
    steps: tuple[str, ...]
    values: tuple[float, ...]
    default: int
    blurb: str                       # what it does, shown when it's picked


SETTINGS = [
    Setting("Land", ("Mostly sea", "Less", "Normal", "More", "Mostly land"),
            (0.26, 0.34, 0.42, 0.52, 0.62), 2, "how much of the world is dry land"),
    Setting("Islands", ("None", "Few", "Normal", "Many", "Archipelago"),
            (0, 1, 2, 3, 4), 2, "small islands out at sea"),
    Setting("Mountains", ("Flat", "Low", "Normal", "High", "Towering"),
            (0.35, 0.65, 1.0, 1.35, 1.75), 2, "how many and how high the ranges are"),
    Setting("Rainfall", ("Arid", "Dry", "Normal", "Wet", "Soaking"),
            (-0.22, -0.11, 0.0, 0.1, 0.2), 2, "how much rain the winds bring"),
    Setting("Temperature", ("Frozen", "Cold", "Normal", "Warm", "Hot"),
            (-10.0, -5.0, 0.0, 4.0, 8.0), 2, "the whole world colder or warmer"),
    Setting("Vegetation", ("Barren", "Sparse", "Normal", "Lush", "Overgrown"),
            (0.25, 0.6, 1.0, 1.35, 1.7), 2, "how thickly forests, bushes and grass grow"),
    Setting("Lakes", ("None", "Few", "Normal", "Many", "Lots"),
            (0, 1, 2, 3, 4), 2, "how many basins and hollows hold water"),
    Setting("Aquifers", ("None", "Few", "Normal", "Many", "Rich"),
            (0.0, 0.5, 1.0, 1.5, 2.0), 2, "groundwater: springs, oases, wet holes"),
    Setting("Population", ("Sparse", "Few", "Normal", "Many", "Crowded"),
            (0.35, 0.6, 1.0, 1.5, 2.2), 2, "how many towns, villages and inns"),
    Setting("Volcanoes", ("None", "Few", "Some", "Many", "Lots"),
            (0, 3, 6, 10, 16), 1, "volcanoes on the ranges and out at sea"),
    Setting("Eruptions", ("Extinct", "Dormant", "Active", "Violent"),
            (0, 1, 2, 3), 1, "how lively the volcanoes are"),
]
BY_NAME = {s.name: s for s in SETTINGS}
EXTINCT, DORMANT, ACTIVE, VIOLENT = range(4)


def _attr(name: str) -> str:
    return name.lower()


@dataclass(frozen=True)
class Tweaks:
    """Which step each setting is on (indices into Setting.steps)."""
    land: int = BY_NAME["Land"].default
    islands: int = BY_NAME["Islands"].default
    mountains: int = BY_NAME["Mountains"].default
    rainfall: int = BY_NAME["Rainfall"].default
    temperature: int = BY_NAME["Temperature"].default
    vegetation: int = BY_NAME["Vegetation"].default
    lakes: int = BY_NAME["Lakes"].default
    aquifers: int = BY_NAME["Aquifers"].default
    population: int = BY_NAME["Population"].default
    volcanoes: int = BY_NAME["Volcanoes"].default
    eruptions: int = BY_NAME["Eruptions"].default

    def index(self, name: str) -> int:
        return getattr(self, _attr(name))

    def step_name(self, name: str) -> str:
        return BY_NAME[name].steps[self.index(name)]

    def value(self, name: str) -> float:
        return BY_NAME[name].values[self.index(name)]

    def stepped(self, name: str, by: int) -> Tweaks:
        """These settings with one moved a step (it stops at the ends, it doesn't wrap)."""
        s = BY_NAME[name]
        return replace(self, **{_attr(name): max(0, min(len(s.steps) - 1, self.index(name) + by))})

    def changed(self) -> list[str]:
        """The settings that aren't on their default, by name."""
        return [s.name for s in SETTINGS if self.index(s.name) != s.default]

    @property
    def is_default(self) -> bool:
        return not self.changed()


assert [f.name for f in fields(Tweaks)] == [_attr(s.name) for s in SETTINGS]
DEFAULT = Tweaks()
