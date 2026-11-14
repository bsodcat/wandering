"""Cold water: it chills you every turn you're in it, and for a while after you come out."""
import random
import unittest

from game import tiles as T
from game.player import (AFTERDROP_TURNS, CHILL_COLDEST, CHILL_WARMEST, NORMAL, Player, chill, chill_rate,
                         chill_status)

from tests.test_wild import engine_on, field


class ChillTests(unittest.TestCase):
    def test_how_fast_water_chills(self):
        self.assertEqual(chill_rate(21.0), 0.0)
        self.assertEqual(chill_rate(25.0), 0.0)
        self.assertAlmostEqual(chill_rate(20.99), CHILL_WARMEST, places=2)
        self.assertAlmostEqual(chill_rate(0.0), CHILL_COLDEST)
        self.assertTrue(CHILL_WARMEST < chill_rate(10.0) < CHILL_COLDEST)

    def test_each_turn_in_cold_water(self):
        p = Player(0, 0)
        chill(p, 1, 5.0, random.Random(1))
        self.assertAlmostEqual(p.body, NORMAL - chill_rate(5.0))
        chill(p, 4, 5.0, random.Random(1))
        self.assertAlmostEqual(p.body, NORMAL - 5 * chill_rate(5.0))
        self.assertEqual(chill_status(p), "In cold water")

    def test_warm_water_does_nothing(self):
        p = Player(0, 0)
        self.assertEqual(chill(p, 10, 24.0, random.Random(1)), [])
        self.assertEqual(p.body, NORMAL)

    def test_the_afterdrop_lasts_30_to_45_turns_and_eases_off(self):
        for seed in range(20):
            p = Player(0, 0)
            chill(p, 3, 2.0, random.Random(seed))
            rng = random.Random(seed)
            drops, turns = [], 0
            while True:
                before = p.body
                chill(p, 1, None, rng)
                if p.body == before:
                    break
                drops.append(before - p.body)
                turns += 1
            self.assertTrue(AFTERDROP_TURNS[0] <= turns <= AFTERDROP_TURNS[1], turns)
            self.assertGreater(drops[0], drops[-1])
            self.assertEqual(chill_status(p), "")

    def test_going_back_in_starts_it_over(self):
        p = Player(0, 0)
        rng = random.Random(2)
        chill(p, 2, 5.0, rng)
        chill(p, 5, None, rng)
        chill(p, 1, 5.0, rng)
        self.assertEqual(p.afterdrop, 0)
        self.assertTrue(p.in_cold_water)


class WadingTests(unittest.TestCase):
    def test_wading_chills_you_and_the_cold_follows_you_out(self):
        level = field()
        level.tiles[31:36, 15] = T.WATER
        e = engine_on(level)
        self.assertLess(e.water_temp(), 21)
        for _ in range(5):
            e.move_local(1, 0)
        self.assertLess(e.player.body, NORMAL - 4 * CHILL_WARMEST)
        e.move_local(1, 0)                                  # out onto the grass
        self.assertGreater(e.player.afterdrop, 0)
        before = e.player.body
        e.move_local(0, 1)
        self.assertLess(e.player.body, before)

    def test_a_long_wait_counts_as_many_turns(self):
        level = field()
        level.tiles[30, 15] = T.WATER
        e = engine_on(level)
        e.pass_time(1 / 60)
        one = NORMAL - e.player.body
        e.player.body = NORMAL
        e.pass_time(1)
        self.assertGreater(NORMAL - e.player.body, 5 * one)

    def test_looking_at_water_tells_you_how_cold(self):
        level = field()
        level.tiles[31, 15] = T.WATER
        e = engine_on(level)
        self.assertTrue(any(line.startswith("Water ") for line in e.describe(31, 15)))


if __name__ == "__main__":
    unittest.main()
