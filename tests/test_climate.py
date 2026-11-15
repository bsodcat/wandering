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
        self.assertEqual(C.date_text(0), "Monday 1 Thaw, Year 1")

    def test_twelve_months_of_four_weeks(self):
        self.assertEqual(C.DAYS_PER_YEAR, 336)
        self.assertEqual(len(C.MONTHS), 12)
        self.assertEqual(C.date(27 * DAY)[1:4], ("Thaw", 28, "Sunday"))
        self.assertEqual(C.date(28 * DAY)[1:4], ("Seedtide", 1, "Monday"))      # every month starts on a Monday
        self.assertEqual(C.date(3 * 28 * DAY)[4], "Summer")                     # three months to a season
        self.assertEqual(C.date(11 * 28 * DAY)[1:], ("Lastsnow", 1, "Monday", "Winter"))
        self.assertEqual(C.weekday(6 * DAY + 10 * HOUR), "Sunday")
        self.assertEqual(C.date_text(C.DAYS_PER_YEAR * DAY + 6 * DAY), "Sunday 7 Thaw, Year 2")
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


class HemisphereTests(unittest.TestCase):
    """The season you're told is the one you see in the trees and feel in the air, north or south."""

    def test_the_named_season_matches_the_trees_and_the_warmth_everywhere(self):
        from game import trees
        from game.climate import DAYS_PER_YEAR, MINUTES_PER_DAY, date, season_offset
        for lat in (-0.5, 0.5):
            for year in range(3):
                for d in range(year * DAYS_PER_YEAR, (year + 1) * DAYS_PER_YEAR, 7):
                    m = d * MINUTES_PER_DAY + 12 * 60
                    season = date(m, lat)[4]
                    if season == "Summer":
                        self.assertEqual(trees.foliage(lat, m), "green", (lat, d))
                        self.assertGreater(float(season_offset(lat, m)), 0, (lat, d))
                    elif season == "Winter":
                        self.assertEqual(trees.foliage(lat, m), "bare", (lat, d))
                        self.assertLess(float(season_offset(lat, m)), 0, (lat, d))

    def test_the_south_names_its_months_half_a_year_on(self):
        from game.climate import MINUTES_PER_DAY, date
        m = 100 * MINUTES_PER_DAY
        north, south = date(m, -0.5), date(m, 0.5)
        self.assertNotEqual(north[1], south[1])
        self.assertEqual((north[0], north[2], north[3]), (south[0], south[2], south[3]))   # same day, same year
