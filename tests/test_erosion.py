"""Erosion: the world worn down when it's made, and soil soaking and washing on local maps."""
import random
import unittest

import numpy as np

from game import erosion
from game import tiles as T
from game.level import Level
from game.worldgen import drain


def cone(w=48, h=48, peak=2.0):
    """An island: a cone in km, sea round the edge."""
    xs, ys = np.indices((w, h))
    r = np.hypot(xs - w / 2, ys - h / 2)
    return np.maximum(peak * (1 - r / (w * 0.4)), -0.2)


class ThermalTests(unittest.TestCase):
    def test_cliffs_crumble_and_nothing_is_lost(self):
        z = np.zeros((20, 20))
        z[10, 10] = 5.0
        out = erosion.thermal(z, np.ones_like(z), iterations=200)
        self.assertLess(out.max(), 5.0)
        self.assertAlmostEqual(out.sum(), z.sum(), places=6)

    def test_hard_rock_stands_steeper(self):
        z = np.zeros((20, 20))
        z[10, 10] = 5.0
        soft = erosion.thermal(z, np.full_like(z, 0.5), iterations=200)
        hard = erosion.thermal(z, np.full_like(z, 2.0), iterations=200)
        self.assertGreater(hard.max(), soft.max())


class HydraulicTests(unittest.TestCase):
    def test_rivers_cut_valleys_and_silt_reaches_the_sea(self):
        z = cone()
        sea = z <= 0
        rain = np.ones_like(z)
        out, flow = erosion.hydraulic(z, rain, np.ones_like(z), sea, drain)
        land = ~sea
        self.assertLess(out[land].mean(), z[land].mean())          # the land's worn down
        mid = land & (z > 0.6) & (z < 1.4)                          # half way up: still steep
        big = mid & (flow > np.quantile(flow[mid], 0.9))
        small = mid & (flow < np.quantile(flow[mid], 0.5))
        self.assertGreater((z - out)[big].mean(), (z - out)[small].mean())   # cut deepest where water gathers
        self.assertGreater(out[sea].sum(), z[sea].sum())          # the sea floor silts up

    def test_roots_hold_the_soil(self):
        z = cone()
        sea = z <= 0
        bare, _ = erosion.hydraulic(z, np.ones_like(z), np.ones_like(z), sea, drain)
        green, _ = erosion.hydraulic(z, np.ones_like(z), np.full_like(z, 0.4), sea, drain)
        self.assertLess(np.abs(z - green)[~sea].sum(), np.abs(z - bare)[~sea].sum())


class WorldTests(unittest.TestCase):
    def test_coastline_stays_and_it_is_the_same_every_time(self):
        rng = np.random.default_rng(3)
        e = (cone(64, 48) * 1000).astype(np.float32) + rng.normal(0, 40, (64, 48)).astype(np.float32)
        e[e <= 0] = np.minimum(e[e <= 0], -1)
        m = np.full(e.shape, 0.5, np.float32)
        t = np.full(e.shape, 12.0, np.float32)
        a = erosion.erode_world(7, e, m, t, drain)
        b = erosion.erode_world(7, e, m, t, drain)
        self.assertTrue(np.array_equal(a, b))
        self.assertTrue(np.array_equal(a > 0, e > 0))
        self.assertLess(a.max(), e.max())


def slope_level():
    """A steep bare dirt slope (two levels a step) down to flat grass."""
    tiles = np.full((8, 6), T.DIRT, np.uint8)
    tiles[6:, :] = T.GRASS
    elev = np.zeros((8, 6), np.int16)
    for x in range(8):
        elev[x, :] = max(0, 6 - x) * 2
    return Level(("region", 0, 0), "test", tiles, elev=elev)


class SoilTests(unittest.TestCase):
    def test_rain_makes_mud_and_it_dries_out(self):
        level = slope_level()
        for hour in range(5):                                       # steady rain, too light to wash
            erosion.weather(level, 60 * hour, 1.0, 0.45, 15.0, random.Random(1))
        self.assertEqual(level.tiles[0, 0], T.MUD)
        self.assertEqual(level.tiles[7, 0], T.GRASS)                 # grass soaks it up, no mud
        for hour in range(60):
            erosion.weather(level, 60 * (5 + hour), 1.0, 0.0, 20.0, random.Random(1))
        self.assertEqual(level.tiles[0, 0], T.DIRT)
        self.assertFalse(level.mud)

    def test_heavy_rain_washes_silt_onto_the_grass_below_and_it_greens_over(self):
        level = slope_level()
        rng = random.Random(2)
        for hour in range(48):
            erosion.weather(level, 60 * hour, 1.0, 1.0, 15.0, rng)
        self.assertTrue(level.silt)
        self.assertTrue(all(x == 6 for x, _ in level.silt))         # at the foot of the slope
        self.assertTrue((level.tiles == T.SCREE).any())            # the steep bare slope's washed to stones
        later = 60 * 48
        for day in range(6):
            erosion.weather(level, later + day * 24 * 60, 24.0, 0.0, 20.0, rng)
        self.assertFalse(level.silt)
        self.assertTrue((level.tiles[6:, :] == T.GRASS).all())

    def test_a_map_you_left_dries_out(self):
        level = slope_level()
        for hour in range(5):
            erosion.weather(level, 60 * hour, 1.0, 0.45, 15.0, random.Random(1))
        self.assertEqual(level.tiles[0, 0], T.MUD)
        self.assertTrue(erosion.catch_up(level, 4 * 24 * 60))
        self.assertEqual(level.tiles[0, 0], T.DIRT)


if __name__ == "__main__":
    unittest.main()
