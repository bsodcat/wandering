"""Time, seasons, daylight, weather and the air temperature at any place and moment.

Everything here is a pure function of the world, a place and the time, so the same moment
always has the same weather, nothing needs saving, and a whole view can be worked out at once
with numpy. Time is counted in minutes from the start of year 1.

Weather comes from 3D noise (x, y, time) that drifts east, so fronts roll across the map:
clouds gather over wet land and sea, rain falls under the thickest of them (snow when it's
cold enough), wind picks up under storms and over mountains, and fog settles on still, damp
mornings.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import tcod

from . import biomes as B

MINUTES_PER_HOUR = 60
HOURS_PER_DAY = 24
MINUTES_PER_DAY = MINUTES_PER_HOUR * HOURS_PER_DAY
DAYS_PER_SEASON = 30
SEASONS = ["Spring", "Summer", "Autumn", "Winter"]
DAYS_PER_YEAR = DAYS_PER_SEASON * len(SEASONS)
MIDSUMMER = 0.375            # of the way through the year (the middle of summer, north)
SEASON_SWING = 14.0          # degrees C between the yearly mean and midsummer, at the poles
DAY_SWING = 5.0              # degrees C between the daily mean and mid-afternoon
FRONT_SPEED = 0.6            # world cells per hour that weather drifts east


# ----------------------------------------------------------------- calendar

def calendar(minutes: int) -> tuple[int, str, int, int, int]:
    """(year, season, day of the season, hour, minute)."""
    day, minute_of_day = divmod(int(minutes), MINUTES_PER_DAY)
    year, day_of_year = divmod(day, DAYS_PER_YEAR)
    season, day_of_season = divmod(day_of_year, DAYS_PER_SEASON)
    hour, minute = divmod(minute_of_day, MINUTES_PER_HOUR)
    return year + 1, SEASONS[season], day_of_season + 1, hour, minute


def date_text(minutes: int) -> str:
    year, season, day, _, _ = calendar(minutes)
    return f"{season} {day}, Year {year}"


def clock_text(minutes: int) -> str:
    _, _, _, hour, minute = calendar(minutes)
    return f"{hour:02d}:{minute:02d}"


def year_fraction(minutes) -> np.ndarray | float:
    return (np.asarray(minutes) / MINUTES_PER_DAY % DAYS_PER_YEAR) / DAYS_PER_YEAR


def hour_of_day(minutes) -> np.ndarray | float:
    return np.asarray(minutes) % MINUTES_PER_DAY / MINUTES_PER_HOUR


def latitude(y, height: int):
    """-1 at the north pole (the top row), 0 at the equator, +1 at the south pole."""
    return (np.asarray(y) + 0.5) / height * 2 - 1


def summer(lat, minutes):
    """+1 at midsummer and -1 at midwinter for this latitude; the south has them swapped."""
    north = np.cos(2 * np.pi * (year_fraction(minutes) - MIDSUMMER))
    return np.where(np.asarray(lat) <= 0, north, -north)


def season_offset(lat, minutes):
    """How far today's mean temperature is from the yearly mean. Big swings near the poles."""
    return SEASON_SWING * np.abs(lat) * summer(lat, minutes)


def day_length(lat, minutes):
    """Hours of daylight: long summer days and short winter ones, more so near the poles."""
    return np.clip(12 + 10 * np.abs(lat) ** 0.8 * summer(lat, minutes), 1.5, 22.5)


def daylight(lat, minutes):
    """0 at night, 1 in full sun, with a soft dawn and dusk."""
    length = day_length(lat, minutes)
    since_dawn = hour_of_day(minutes) - (12 - length / 2)
    sun = np.sin(np.pi * since_dawn / length)       # above 0 while the sun is up
    sun = np.where((since_dawn > -1.5) & (since_dawn < length + 1.5), sun, -1)
    return np.clip((sun + 0.12) / 0.45, 0, 1)


def day_offset(minutes):
    """Warmest at 15:00, coldest at 03:00."""
    return DAY_SWING * np.cos(2 * np.pi * (hour_of_day(minutes) - 15) / HOURS_PER_DAY)


def time_of_day(lat: float, minutes: int) -> str:
    light, hour = float(daylight(lat, minutes)), float(hour_of_day(minutes))
    if light <= 0:
        return "Night"
    if light < 0.95:
        return "Dawn" if hour < 12 else "Dusk"
    return "Morning" if hour < 12 else ("Afternoon" if hour < 18 else "Evening")


# ----------------------------------------------------------------- weather

@dataclass
class Conditions:
    """What it's like at one place and moment."""
    air: float          # degrees C
    cloud: float        # 0..1
    precip: float       # 0..1, how hard it's raining or snowing
    wind: float         # km/h
    fog: float          # 0..1
    light: float        # 0..1, how bright it is outside
    kind: str           # Clear, Cloudy, Overcast, Fog, Rain, Storm, Snow, Blizzard

    @property
    def snowing(self) -> bool:
        return self.kind in ("Snow", "Blizzard")

    @property
    def raining(self) -> bool:
        return self.kind in ("Rain", "Storm")


def weather_kind(air, precip, cloud, wind, fog) -> str:
    if precip > 0.15:
        if air <= 0.5:
            return "Blizzard" if wind > 40 else "Snow"
        return "Storm" if precip > 0.7 and air > 10 else "Rain"
    if fog > 0.4:
        return "Fog"
    if cloud > 0.6:
        return "Overcast"
    return "Cloudy" if cloud > 0.42 else "Clear"


class Climate:
    """The weather and temperature over one world."""

    def __init__(self, world):
        self.world = world
        def noise(n, octaves):
            return tcod.noise.Noise(3, algorithm=tcod.noise.Algorithm.SIMPLEX,
                                    implementation=tcod.noise.Implementation.FBM,
                                    octaves=octaves, seed=world.seed * 31 + n)
        self.cloud_noise, self.wind_noise, self.fog_noise = noise(1, 3), noise(2, 2), noise(3, 2)

    def fields(self, xs: np.ndarray, ys: np.ndarray, minutes: int) -> dict[str, np.ndarray]:
        """Weather, light and air temperature for every (x, y): xs and ys are integer index
        arrays that broadcast together, e.g. a column and a row for a rectangle."""
        w = self.world
        xs, ys = np.broadcast_arrays(np.asarray(xs), np.asarray(ys))
        hours = minutes / MINUTES_PER_HOUR
        moist = w.moisture[xs, ys]
        lat = latitude(ys, w.height)
        drift = xs - FRONT_SPEED * hours
        t = np.full(xs.shape, hours, np.float32)
        c = self.cloud_noise[(drift / 22, ys / 22, t / 30)]
        cloud = np.clip(0.48 + 0.75 * c + 0.45 * (moist - 0.45), 0, 1)
        precip = np.clip((cloud - 0.7) / 0.28, 0, 1) * np.clip(0.4 + moist, 0, 1)
        high = np.maximum(w.elevation[xs, ys], 0) / 1000
        wind = np.clip(4 + 24 * (self.wind_noise[(drift / 30, ys / 30, t / 20)] + 1) / 2
                       + 18 * precip + 6 * high, 0, 120)
        hour = hour_of_day(minutes)
        morning = np.clip(1 - np.abs(hour - 6.5) / 3.5, 0, 1)
        fog = np.clip((self.fog_noise[(xs / 12, ys / 12, t / 8)] + 0.3) * 2, 0, 1) \
            * morning * np.clip((moist - 0.45) * 3, 0, 1) * np.clip((26 - wind) / 10, 0, 1) * (precip < 0.15)
        sun = daylight(lat, minutes)
        air = (w.temperature[xs, ys] + season_offset(lat, minutes)
               + day_offset(minutes) * (1 - 0.6 * cloud) - 3 * precip)
        light = np.clip(sun * (1 - 0.5 * cloud - 0.25 * precip) + 0.1 * (1 - 0.7 * cloud) - 0.2 * fog, 0.04, 1)
        return dict(air=air.astype(np.float32), cloud=cloud.astype(np.float32), precip=precip.astype(np.float32),
                    wind=wind.astype(np.float32), fog=fog.astype(np.float32), light=light.astype(np.float32),
                    sun=np.asarray(sun * np.ones(xs.shape), np.float32))

    def at(self, x: int, y: int, minutes: int) -> Conditions:
        f = {k: float(v.reshape(-1)[0]) for k, v in self.fields(np.array([x]), np.array([y]), minutes).items()}
        kind = weather_kind(f["air"], f["precip"], f["cloud"], f["wind"], f["fog"])
        return Conditions(f["air"], f["cloud"], f["precip"], f["wind"], f["fog"], f["light"], kind)


def describe_wind(kmh: float) -> str:
    for limit, name in ((2, "Calm"), (12, "Light breeze"), (29, "Breezy"), (50, "Strong wind"), (75, "Gale")):
        if kmh < limit:
            return name
    return "Storm winds"


def snow_cover(world, x: int, y: int, minutes: float) -> bool:
    """Whether snow lies on the ground in this region now: always on glaciers and peaks,
    elsewhere whenever the season's mean temperature is below freezing."""
    if world.biome[x, y] in (B.GLACIER, B.PEAKS):
        return True
    lat = latitude(y, world.height)
    return float(world.temperature[x, y] + season_offset(lat, minutes)) < -1.0


def shelter_at(world, x: int, y: int) -> float:
    """0..1: how much the surroundings shield you. Indoors in a settlement is full shelter."""
    site = world.site_at.get((x, y))
    if site is not None and site.settled:
        return 1.0
    if site is not None and site.kind == "cave":
        return 0.9
    return float(B.SHELTER[world.biome[x, y]])
