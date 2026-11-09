"""The world generator: terrain, climate, rivers, biomes, sites and roads."""
import functools
import unittest

import numpy as np

from game import biomes as B
from game.worldgen import WORLD_H, WORLD_W, generate


@functools.lru_cache(maxsize=None)
def world(seed=1):
    return generate(seed)


class TerrainTests(unittest.TestCase):
    def test_same_seed_same_world(self):
        a, b = generate(5), generate(5)
        self.assertTrue(np.array_equal(a.biome, b.biome))
        self.assertTrue(np.array_equal(a.road, b.road))
        self.assertEqual([(s.name, s.x, s.y) for s in a.sites], [(s.name, s.x, s.y) for s in b.sites])

    def test_different_seeds_differ(self):
        self.assertFalse(np.array_equal(world(1).biome, world(2).biome))

    def test_size_and_land_share(self):
        for seed in (1, 2, 3):
            w = world(seed)
            self.assertEqual(w.biome.shape, (WORLD_W, WORLD_H))
            self.assertTrue(0.3 < (w.elevation > 0).mean() < 0.55)

    def test_sea_all_round_the_edge(self):
        w = world(1)
        for edge in (w.elevation[0, :], w.elevation[-1, :], w.elevation[:, 0], w.elevation[:, -1]):
            self.assertTrue((edge <= 0).all())


class ClimateTests(unittest.TestCase):
    def test_poles_colder_than_the_equator(self):
        t = world(1).temperature
        self.assertLess(t[:, :8].mean(), t[:, 60:68].mean() - 20)
        self.assertLess(t[:, -8:].mean(), t[:, 60:68].mean() - 20)

    def test_high_ground_is_colder(self):
        w = world(1)
        band = slice(50, 78)   # near the equator, so latitude barely matters
        e, t = w.elevation[:, band], w.temperature[:, band]
        self.assertLess(t[e > 2000].mean(), t[(e > 0) & (e < 300)].mean() - 8)


class WaterTests(unittest.TestCase):
    def test_rivers_run_to_the_sea_or_a_lake(self):
        w = world(1)
        for x, y in np.argwhere(w.river)[::7]:
            for _ in range(2000):
                if w.biome[x, y] in B.WATER:
                    break
                self.assertTrue(w.river[x, y] or w.biome[x, y] in B.WATER, (x, y))
                x, y = x + w.flow_dx[x, y], y + w.flow_dy[x, y]
            else:
                self.fail("river never reached water")

    def test_flow_grows_downstream(self):
        w = world(1)
        for x, y in np.argwhere(w.river)[::11]:
            nx, ny = x + w.flow_dx[x, y], y + w.flow_dy[x, y]
            self.assertGreaterEqual(w.flow[nx, ny], w.flow[x, y])

    def test_there_are_rivers_and_lakes(self):
        w = world(1)
        self.assertGreater(w.river.sum(), 100)
        self.assertGreater((w.biome == B.LAKE).sum(), 0)


class BiomeTests(unittest.TestCase):
    def test_biomes_suit_their_climate(self):
        w = world(1)
        t, b, e = w.temperature, w.biome, w.elevation
        self.assertTrue((t[b == B.DESERT] > 17).all())
        self.assertTrue((t[b == B.JUNGLE] > 20).all())
        self.assertTrue((t[b == B.GLACIER] < -9).all())
        self.assertTrue((e[np.isin(b, [B.OCEAN, B.DEEP_OCEAN])] <= 0).all())
        self.assertTrue((e[b == B.PEAKS] > 2200).all())

    def test_a_varied_world(self):
        present = set(np.unique(np.concatenate([world(s).biome.ravel() for s in (1, 2, 3)])).tolist())
        self.assertGreaterEqual(len(present), 16)

    def test_water_cant_be_walked(self):
        w = world(1)
        self.assertFalse((B.TRAVEL[w.biome][np.isin(w.biome, B.WATER)] > 0).any())


class SiteTests(unittest.TestCase):
    def test_sites_are_on_walkable_land_with_unique_names(self):
        w = world(1)
        self.assertTrue(w.sites)
        for s in w.sites:
            self.assertTrue(w.walkable(s.x, s.y), s)
        names = [s.name for s in w.sites]
        self.assertEqual(len(names), len(set(names)))

    def test_towns_keep_their_distance(self):
        towns = [s for s in world(1).sites if s.kind == "town"]
        self.assertGreater(len(towns), 3)
        for a in towns:
            for b in towns:
                if a is not b:
                    self.assertGreaterEqual(max(abs(a.x - b.x), abs(a.y - b.y)), 16)

    def test_roads_reach_settlements(self):
        w = world(1)
        reached = 0
        for s in (s for s in w.sites if s.settled):
            around = w.road[max(0, s.x - 1): s.x + 2, max(0, s.y - 1): s.y + 2]
            reached += bool(around.any())
        self.assertGreater(reached, len([s for s in w.sites if s.settled]) // 2)

    def test_roads_stay_on_land(self):
        w = world(1)
        self.assertFalse((w.road & np.isin(w.biome, B.WATER)).any())

    def test_region_seeds_are_stable_and_distinct(self):
        w = world(1)
        self.assertEqual(w.region_seed(10, 20), generate(1).region_seed(10, 20))
        self.assertNotEqual(w.region_seed(10, 20), w.region_seed(11, 20))


if __name__ == "__main__":
    unittest.main()
