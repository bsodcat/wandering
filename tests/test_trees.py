"""Trees: trunks on the ground, crowns on the layer above, and ways in kept clear."""
import functools
import unittest

import numpy as np
from tcod.event import KeySym

from game import biomes as B
from game import tiles as T
from game import trees
from game.climate import MINUTES_PER_DAY, DAYS_PER_SEASON
from game.engine import Engine
from game.localgen import LOCAL_H, LOCAL_W, MARGIN, draw_waterways, generate_region, make_level, terrain
from game.worldgen import generate


@functools.lru_cache(maxsize=None)
def world(seed=1):
    return generate(seed)


@functools.lru_cache(maxsize=None)
def level(seed, key):
    return make_level(world(seed), key)


def middle_of(w, biome):
    cells = np.argwhere(w.biome == biome)
    return (int(v) for v in cells[len(cells) // 2])


class TrunkTests(unittest.TestCase):
    def test_no_two_trunks_touch(self):
        w = world(1)
        for biome in (B.FOREST, B.TAIGA, B.JUNGLE):
            if not (w.biome == biome).any():
                continue
            t = generate_region(w, *middle_of(w, biome)).tiles
            trunk = np.isin(t, trees.TRUNKS)
            p = np.pad(trunk, 1)
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    if dx or dy:
                        self.assertFalse((trunk & p[1 + dx: LOCAL_W + 1 + dx, 1 + dy: LOCAL_H + 1 + dy]).any(), biome)

    def test_forests_are_roofed_with_leaves(self):
        w = world(1)
        lvl = generate_region(w, *middle_of(w, B.FOREST))
        self.assertGreater((lvl.canopy > 0).mean(), 0.35)
        self.assertGreater((lvl.canopy[np.isin(lvl.tiles, trees.TRUNKS)] > 0).mean(), 0.99)

    def test_kinds_of_tree(self):
        tiles = np.full((20, 10), T.GRASS, np.uint8)
        tiles[3, 3], tiles[10, 5], tiles[16, 5] = T.TREE, T.PINE, T.JUNGLE_TREE
        canopy, boughs = trees.crowns(tiles)
        self.assertEqual(canopy[3, 3], trees.BROADLEAF)
        self.assertEqual(canopy[5, 3], trees.BROADLEAF)    # two columns out
        self.assertEqual(canopy[3, 4], trees.BROADLEAF)    # one row down
        self.assertEqual(canopy[3, 5], trees.NONE)
        self.assertEqual(canopy[10, 4], trees.PINE)
        self.assertEqual(canopy[11, 4], trees.NONE)        # pines are narrow
        self.assertEqual(canopy[19, 5], trees.JUNGLE)      # jungle crowns are wide
        self.assertEqual(boughs[5, 3], ord("─"))
        self.assertEqual(boughs[3, 4], ord("│"))

    def test_leaves_join_across_region_borders(self):
        w = world(1)
        x, y = middle_of(w, B.FOREST)
        for x, y in np.argwhere(np.isin(w.biome, [B.FOREST, B.TAIGA, B.JUNGLE])):
            x, y = int(x), int(y)
            if not any(c in w.site_at for c in ((x, y), (x + 1, y))) and w.walkable(x + 1, y):
                break
        left, right = generate_region(w, x, y), generate_region(w, x + 1, y)
        gx0, gy0 = x * LOCAL_W - MARGIN, y * LOCAL_H - MARGIN
        big, _ = terrain(w, gx0, gy0, 2 * LOCAL_W + 2 * MARGIN, LOCAL_H + 2 * MARGIN)
        draw_waterways(w, big, gx0, gy0)
        canopy, boughs = trees.crowns(big)
        inner = (slice(MARGIN, MARGIN + 2 * LOCAL_W), slice(MARGIN, MARGIN + LOCAL_H))
        canopy, boughs, tiles = canopy[inner], boughs[inner], big[inner]
        trees.keep_clear(canopy, boughs, tiles)
        self.assertTrue(np.array_equal(left.canopy, canopy[:LOCAL_W]))
        self.assertTrue(np.array_equal(right.canopy, canopy[LOCAL_W:]))
        self.assertTrue((left.canopy[-3:] > 0).any() or (right.canopy[:3] > 0).any())


class ClearingTests(unittest.TestCase):
    def sites(self, kinds=("town", "village", "inn", "tower", "ruins", "cave")):
        return [(seed, s) for seed in (1, 2) for s in world(seed).sites if s.kind in kinds][:40]

    def test_no_trunk_by_a_way_in(self):
        for seed, site in self.sites():
            lvl = level(seed, ("region", site.x, site.y))
            way_in = trees.entrances(lvl.tiles, lvl.exits)
            close = trees.near(way_in, trees.CLEARING)
            self.assertFalse((close & np.isin(lvl.tiles, trees.TRUNKS)).any(), site)

    def test_no_leaves_over_buildings_ways_or_entrances(self):
        for seed, site in self.sites():
            lvl = level(seed, ("region", site.x, site.y))
            t = lvl.tiles
            covered = lvl.canopy > 0
            built = np.isin(t, [T.DOOR, T.WALL, T.STONE_WALL, T.STAIRS_DOWN, T.STAIRS_UP, T.STREET, T.PATH,
                                T.ROAD, T.BRIDGE, T.DOCK]) | T.ROOF[t]
            self.assertFalse((covered & built).any(), site)
            for x, y in lvl.exits:
                self.assertEqual(lvl.canopy[x, y], trees.NONE, site)

    def test_every_door_still_has_a_step_outside(self):
        for seed, site in self.sites(("town", "village", "inn")):
            lvl = level(seed, ("region", site.x, site.y))
            t = lvl.tiles
            for x, y in zip(*np.nonzero(t == T.DOOR)):
                steps = [(x + dx, y + dy) for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))]
                outside = [s for s in steps if lvl.in_bounds(*s) and T.WALK[t[s]] and not T.ROOF[t[s]]]
                self.assertTrue(outside, (site, x, y))


class SeasonTests(unittest.TestCase):
    def test_broadleaf_trees_follow_the_seasons_away_from_the_tropics(self):
        day = MINUTES_PER_DAY
        north = -0.6
        looks = {trees.foliage(north, d * day) for d in range(0, 4 * DAYS_PER_SEASON, 3)}
        self.assertEqual(looks, {"green", "budding", "autumn", "bare"})
        self.assertEqual({trees.foliage(0.05, d * day) for d in range(0, 120, 3)}, {"green"})
        midsummer = int(0.375 * 4 * DAYS_PER_SEASON) * day
        self.assertEqual(trees.foliage(north, midsummer), "green")
        self.assertEqual(trees.foliage(-north, midsummer), "bare")    # the south has winter then

    def test_leaves_give_shelter_bare_boughs_less(self):
        self.assertGreater(trees.leaf_shelter(trees.PINE, "bare"), trees.leaf_shelter(trees.BROADLEAF, "bare"))
        self.assertGreater(trees.leaf_shelter(trees.BROADLEAF, "green"), 0.3)
        self.assertEqual(trees.leaf_shelter(trees.NONE, "green"), 0)


class EngineTreeTests(unittest.TestCase):
    def test_under_the_trees_you_are_sheltered(self):
        e = Engine.new(1)
        w = e.world
        e.player.x, e.player.y = middle_of(w, B.FOREST)
        e.enter_region()
        lvl = e.level
        under = np.argwhere((lvl.canopy > 0) & T.WALK[lvl.tiles] & ~np.isin(lvl.tiles, trees.TRUNKS))
        open_ = np.argwhere((lvl.canopy == 0) & T.WALK[lvl.tiles] & ~T.ROOF[lvl.tiles])
        self.assertTrue(len(under) and len(open_))
        e.lx, e.ly = (int(v) for v in open_[0])
        e.level.tiles[max(0, e.lx - 1): e.lx + 2, max(0, e.ly - 1): e.ly + 2][
            np.isin(e.level.tiles[max(0, e.lx - 1): e.lx + 2, max(0, e.ly - 1): e.ly + 2], trees.TRUNKS)] = T.GRASS
        in_the_open = e.shelter
        e.lx, e.ly = (int(v) for v in under[0])
        self.assertTrue(e.leaves)
        self.assertGreater(e.shelter, in_the_open)

    def test_v_switches_between_treetops_and_ground(self):
        e = Engine.new(1)
        e.enter_region()
        self.assertTrue(e.treetops)
        e.handle_key(KeySym.V)
        self.assertFalse(e.treetops)
        e.handle_key(KeySym.V)
        self.assertTrue(e.treetops)

    def test_draws_both_views(self):
        import tcod
        from game.render import SCREEN_H, SCREEN_W, draw
        e = Engine.new(1)
        e.player.x, e.player.y = middle_of(e.world, B.FOREST)
        e.enter_region()
        console = tcod.console.Console(SCREEN_W, SCREEN_H, order="F")
        draw(console, e)
        above = console.rgb["ch"].copy()
        e.handle_key(KeySym.V)
        draw(console, e)
        below = console.rgb["ch"].copy()
        self.assertGreater(np.isin(above, [ord("♣"), ord('"'), ord("♠"), ord("─"), ord("│")]).sum(),
                           np.isin(below, [ord("♣"), ord("♠")]).sum())
        self.assertTrue((below == ord("O")).any())


if __name__ == "__main__":
    unittest.main()
