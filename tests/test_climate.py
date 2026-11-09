"""Time, seasons, daylight, weather and temperature."""
import functools
import unittest

import numpy as np

from game import climate as C
from game.worldgen import generate

DAY, HOUR = C.MINUTES_PER_DAY, C.MINUTES_PER_HOUR
MIDSUMMER = int(C.MIDSUMMER * C.DAYS_PER_YEAR) * DAY       # the middle of northern summer
MIDWINTER = MIDSUMMER + C.DAYS_PER_YEAR // 2 * DAY


@functools.lru_cache(maxsize=None)
def climate():
    return C.Climate(generate(1))


class CalendarTests(unittest.TestCase):
    def test_calendar(self):
        self.assertEqual(C.calendar(0), (1, "Spring", 1, 0, 0))
        self.assertEqual(C.calendar(8 * HOUR + 30), (1, "Spring", 1, 8, 30))
        self.assertEqual(C.calendar(C.DAYS_PER_SEASON * DAY), (1, "Summer", 1, 0, 0))
        self.assertEqual(C.calendar(C.DAYS_PER_YEAR * DAY)[0], 2)
        self.assertEqual(C.date_text(0), "Spring 1, Year 1")
        self.assertEqual(C.clock_text(13 * HOUR + 5), "13:05")


class SunTests(unittest.TestCase):
    def test_noon_is_bright_and_midnight_dark(self):
        self.assertEqual(float(C.daylight(-0.3, 12 * HOUR)), 1.0)
        self.assertEqual(float(C.daylight(-0.3, 0)), 0.0)

    def test_summer_days_are_longer(self):
        north = -0.6
        self.assertGreater(float(C.day_length(north, MIDSUMMER)), 16)
        self.assertLess(float(C.day_length(north, MIDWINTER)), 8)

    def test_the_south_has_its_summer_in_the_north_winter(self):
        self.assertGreater(float(C.season_offset(0.6, MIDWINTER)), 5)
        self.assertLess(float(C.season_offset(-0.6, MIDWINTER)), -5)

    def test_the_equator_barely_changes(self):
        self.assertLess(abs(float(C.season_offset(0.0, MIDWINTER))), 0.5)

    def test_afternoon_warmer_than_before_dawn(self):
        self.assertGreater(float(C.day_offset(15 * HOUR)), float(C.day_offset(3 * HOUR)) + 8)


class WeatherTests(unittest.TestCase):
    def test_the_same_moment_has_the_same_weather(self):
        c = climate()
        self.assertEqual(c.at(100, 60, 5000), c.at(100, 60, 5000))

    def test_snow_only_when_cold(self):
        c = climate()
        w = c.world
        xs, ys = np.arange(w.width)[:, None], np.arange(w.height)[None, :]
        for minutes in (8 * HOUR, MIDWINTER + 3 * HOUR, MIDSUMMER + 15 * HOUR):
            f = c.fields(xs, ys, minutes)
            kinds = np.vectorize(C.weather_kind)(f["air"], f["precip"], f["cloud"], f["wind"], f["fog"])
            self.assertTrue((f["air"][np.isin(kinds, ["Snow", "Blizzard"])] <= 0.5).all())
            self.assertTrue((f["air"][np.isin(kinds, ["Rain", "Storm"])] > 0.5).all())

    def test_weather_changes_over_time(self):
        c = climate()
        kinds = {c.at(120, 50, h * HOUR).kind for h in range(0, 24 * 20, 6)}
        self.assertGreater(len(kinds), 2)

    def test_a_mix_of_weather_across_the_world(self):
        c = climate()
        w = c.world
        f = c.fields(np.arange(w.width)[:, None], np.arange(w.height)[None, :], 10 * HOUR)
        rain_share = (f["precip"] > 0.15).mean()
        self.assertTrue(0.05 < rain_share < 0.4, rain_share)

    def test_clouds_and_night_dim_the_light(self):
        c = climate()
        noon = c.fields(np.arange(256)[:, None], np.arange(128)[None, :], 12 * HOUR)
        night = c.fields(np.arange(256)[:, None], np.arange(128)[None, :], 0)
        self.assertGreater(noon["light"].mean(), night["light"].mean() + 0.4)
        clear, cloudy = noon["cloud"] < 0.2, noon["cloud"] > 0.8
        self.assertGreater(noon["light"][clear].mean(), noon["light"][cloudy].mean())


class ShelterTests(unittest.TestCase):
    def test_towns_are_full_shelter(self):
        w = generate(1)
        town = next(s for s in w.sites if s.kind == "town")
        self.assertEqual(C.shelter_at(w, town.x, town.y), 1.0)


if __name__ == "__main__":
    unittest.main()
