"""Fire and water: hearths and torches that light their surroundings and flicker, and water
that moves."""
import functools
import unittest

import numpy as np
import tcod

from game import tiles as T
from game.climate import MINUTES_PER_DAY
from game.engine import Engine
from game.light import REACH, firelight, flicker
from game.localgen import make_level
from game.render import SCREEN_H, SCREEN_W, draw
from game.worldgen import generate


@functools.lru_cache(maxsize=None)
def world(seed=1):
    return generate(seed)


def site_level(kind, seed=1, n=0):
    w = world(seed)
    s = [s for s in w.sites if s.kind == kind][n]
    return s, make_level(w, ("region", s.x, s.y))


class TorchTests(unittest.TestCase):
    def test_settlements_hang_torches_beside_doors(self):
        for kind in ("town", "village", "inn"):
            site, lvl = site_level(kind)
            t = lvl.tiles
            torches = list(zip(*np.nonzero(t == T.TORCH)))
            self.assertTrue(torches, site)
            for x, y in torches:
                beside = [t[x + dx, y + dy] for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))]
                self.assertIn(T.DOOR, beside, (site, x, y))

    def test_doors_still_open_onto_the_way_out(self):
        site, lvl = site_level("town")
        t = lvl.tiles
        for x, y in zip(*np.nonzero(t == T.DOOR)):
            steps = [t[x + dx, y + dy] for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))]
            self.assertTrue(any(T.WALK[s] and not T.ROOF[s] for s in steps), (x, y))

    def test_ruins_have_no_torches(self):
        for n in range(3):
            _, lvl = site_level("ruins", n=n)
            self.assertFalse((lvl.tiles == T.TORCH).any())

    def test_towers_have_one_by_the_door(self):
        _, lvl = site_level("tower")
        self.assertEqual((lvl.tiles == T.TORCH).sum(), 1)


class FirelightTests(unittest.TestCase):
    def test_fires_light_what_is_near_them(self):
        _, lvl = site_level("town")
        strength, phase = firelight(lvl)
        self.assertIs(firelight(lvl), lvl.fire)          # worked out once
        for tile in (T.HEARTH, T.TORCH):
            x, y = next(zip(*np.nonzero(lvl.tiles == tile)))
            self.assertAlmostEqual(float(strength[x, y]), 1.0)
        far = np.ones(lvl.tiles.shape, bool)
        for x, y in zip(*np.nonzero(np.isin(lvl.tiles, [T.HEARTH, T.TORCH]))):
            xs, ys = np.ogrid[: lvl.width, : lvl.height]
            far &= (xs - x) ** 2 + (2 * (ys - y)) ** 2 > max(REACH.values()) ** 2
        self.assertEqual(float(strength[far].max()), 0.0)

    def test_torchlight_stays_outside(self):
        t = np.full((20, 10), T.GRASS, np.uint8)
        t[5:15, 2:8] = T.WALL
        t[6:14, 3:7] = T.WOOD_FLOOR
        t[10, 7] = T.DOOR
        t[11, 7] = T.TORCH
        from game.level import Level
        lvl = Level(("region", 0, 0), "test", t)
        strength, _ = firelight(lvl)
        self.assertGreater(strength[11, 8], 0.5)
        self.assertEqual(float(strength[6:14, 3:7].max()), 0.0)

    def test_flicker_wavers_within_bounds(self):
        phase = np.linspace(0, 6, 50)
        values = np.concatenate([flicker(phase, s / 10) for s in range(100)])
        self.assertGreater(values.min(), 0.6)
        self.assertLess(values.max(), 1.1)
        self.assertGreater(values.std(), 0.03)


def frame(e, seconds):
    console = tcod.console.Console(SCREEN_W, SCREEN_H, order="F")
    draw(console, e, seconds)
    return console.rgb.copy()


class AnimationTests(unittest.TestCase):
    def test_water_moves(self):
        e = Engine.new(1)
        w = e.world
        x, y = (int(v) for v in np.argwhere(w.river & ~w.road)[3])
        e.player.x, e.player.y = x, y
        e.minutes = 5 * MINUTES_PER_DAY + 12 * 60
        e.now = e.climate.at(x, y, e.minutes)
        e.enter_region()
        a, b = frame(e, 1.0), frame(e, 1.5)
        self.assertFalse(np.array_equal(a["ch"], b["ch"]) and np.array_equal(a["fg"], b["fg"]))
        e.leave_region()
        a, b = frame(e, 1.0), frame(e, 1.5)
        self.assertFalse(np.array_equal(a["fg"], b["fg"]))

    def test_fires_flicker_and_light_up_the_night(self):
        e = Engine.new(1)
        e.minutes = 3 * MINUTES_PER_DAY + 22 * 60
        e.now = e.climate.at(e.player.x, e.player.y, e.minutes)
        e.enter_region()
        e.update_view()
        lvl = e.level
        r = e.sight_radius()
        xs, ys = np.ogrid[: lvl.width, : lvl.height]
        beyond = (xs - e.lx) ** 2 + (2 * (ys - e.ly)) ** 2 > (r + 2) ** 2
        self.assertTrue((e.local_visible & beyond).any())       # firelit places, seen from afar
        self.assertTrue((e.local_visible & beyond & (firelight(lvl)[0] == 0)).sum() == 0)
        a, b = frame(e, 1.0), frame(e, 1.37)
        torches = lvl.tiles == T.TORCH
        self.assertFalse(np.array_equal(a["fg"], b["fg"]))
        self.assertTrue(torches.any())


if __name__ == "__main__":
    unittest.main()
