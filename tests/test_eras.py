"""Eras: a world's history, the start year, and the time skip."""
import unittest

import numpy as np

from game import biomes as B
from game import eras
from game.climate import calendar
from game.engine import SKIP_KEY, Engine
from game.worldgen import generate


class HistoryTests(unittest.TestCase):
    def test_longer_eras_do_more(self):
        self.assertEqual(eras.weight(0), 0.0)
        self.assertLess(eras.weight(100), eras.weight(10_000))
        self.assertLess(eras.weight(10_000), eras.weight(1_000_000))
        self.assertEqual(eras.weight(5_000_000), 1.0)
        self.assertGreater(eras.effects(((1_000_000, "Steady"),)).passes, eras.effects(()).passes)

    def test_changes_add_up(self):
        fx = eras.effects(((100_000, "Ice age"), (100_000, "Ice age")))
        one = eras.effects(((100_000, "Ice age"),))
        self.assertLess(fx.warm, one.warm)
        self.assertLess(one.sea, 0)

    def test_start_history(self):
        self.assertEqual(eras.start_history(1, "Wetter"), ())
        self.assertEqual(eras.start_history(1000, "Wetter"), ((999, "Wetter"),))


class WorldTests(unittest.TestCase):
    def test_same_history_same_world(self):
        h = ((10_000, "Drier"),)
        a, b = generate(3, history=h), generate(3, history=h)
        self.assertTrue(np.array_equal(a.biome, b.biome))
        self.assertEqual(a.history, h)
        self.assertEqual(a.years, 10_000)

    def test_changes_change_the_land(self):
        base = generate(1)
        ice = generate(1, history=((1_000_000, "Ice age"),))
        dry = generate(1, history=((1_000_000, "Drier"),))
        self.assertGreater((ice.biome == B.GLACIER).sum(), (base.biome == B.GLACIER).sum())
        self.assertGreater((ice.elevation > 0).sum(), (base.elevation > 0).sum())     # the sea fell
        self.assertGreater((dry.biome == B.DESERT).sum(), (base.biome == B.DESERT).sum())


class SkipTests(unittest.TestCase):
    def test_a_world_starts_in_its_year(self):
        world = generate(2, history=eras.start_history(1000, "Steady"))
        e = Engine.new(2, world)
        self.assertEqual(calendar(e.minutes)[0], 1000)

    def test_time_skip(self):
        e = Engine.new(1)
        e.enter_region()
        old = {s.name for s in e.world.sites if s.settled}
        e.time_skip(10_000, "Wetter")
        self.assertEqual(calendar(e.minutes)[0], 10_001)
        self.assertIsNone(e.level)
        self.assertFalse(e.levels)
        self.assertTrue(e.world.walkable(e.player.x, e.player.y))
        self.assertEqual(e.world.history, ((10_000, "Wetter"),))
        names = {s.name for s in e.world.sites}
        self.assertTrue(any(n in names or f"Ruins of {n}" in names for n in old))   # remembered, or ruined
        e.enter_region()                                    # the new land opens up
        self.assertIsNotNone(e.level)
        e.pass_time(1)

    def test_menu_asks_for_the_skip(self):
        e = Engine.new(1)
        e.handle_key(SKIP_KEY)
        self.assertEqual(e.menu.screen, "timeskip")
        from tcod.event import KeySym
        e.menu.cursor = e.menu.items().index("Start")
        e.handle_key(KeySym.RETURN)
        self.assertEqual(e.skip_request, e.menu.skip_choice())


if __name__ == "__main__":
    unittest.main()
