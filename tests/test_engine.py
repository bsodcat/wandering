"""Travel, time, the view and the keys."""
import unittest

import numpy as np
import tcod
from tcod.event import KeySym

from game import biomes as B
from game.engine import NIGHT_SLOWDOWN, OVERLAYS, ROAD_TRAVEL, START_MINUTES, Engine
from game.render import SCREEN_H, SCREEN_W, camera, draw


def engine(seed=1):
    return Engine.new(seed)


def step_into(e, test):
    """A step from the player's spot to a neighbour where test(x, y) holds, or None."""
    p = e.player
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            if (dx or dy) and e.world.in_bounds(p.x + dx, p.y + dy) and test(p.x + dx, p.y + dy):
                return dx, dy
    return None


def put(e, x, y):
    e.player.x, e.player.y = int(x), int(y)
    e.now = e.climate.at(x, y, e.minutes)
    e.update_view()


class StartTests(unittest.TestCase):
    def test_starts_in_a_town_in_the_morning(self):
        e = engine()
        self.assertEqual(e.site.kind, "town")
        self.assertEqual(e.minutes, START_MINUTES)
        self.assertIn("You set out from", e.messages[0])
        self.assertTrue(e.visible[e.player.x, e.player.y])

    def test_the_start_town_tells_you_about_the_land_around_it(self):
        e = engine()
        p = e.player
        self.assertTrue(e.explored[p.x + 10, p.y] or not e.world.in_bounds(p.x + 10, p.y))
        self.assertGreater(e.explored.sum(), e.visible.sum() * 3)
        self.assertTrue(any("tell you about the land" in m for m in e.messages))

    def test_a_settlement_shares_what_it_knows_only_once(self):
        e = engine()
        before = len(e.messages)
        e.visit()
        self.assertEqual(len(e.messages), before)


class TravelTests(unittest.TestCase):
    def test_water_stops_you(self):
        e = engine()
        coast = np.argwhere((B.TRAVEL[e.world.biome] > 0) & np.isin(np.roll(e.world.biome, -1, 0), B.WATER))
        put(e, *coast[0])
        before = (e.player.x, e.player.y, e.minutes)
        self.assertFalse(e.move(1, 0))
        self.assertEqual((e.player.x, e.player.y, e.minutes), before)
        self.assertIn("too deep to cross", e.messages[-1])

    def test_a_step_costs_the_ground_s_travel_time(self):
        e = engine()
        w = e.world
        mountain = np.argwhere((w.biome == B.MOUNTAINS) & ~w.road & ~w.river)
        x, y = mountain[0]
        start = step_into_from(e, x, y)
        put(e, *start)
        e.minutes = 12 * 60   # midday, so no night slowdown
        e.now = e.climate.at(*start, e.minutes)
        hours, _ = e.travel_time(x, y, x - start[0], y - start[1])
        self.assertGreaterEqual(hours, B.BIOMES[B.MOUNTAINS].travel)

    def test_roads_are_quick(self):
        e = engine()
        e.minutes = 12 * 60
        e.now = e.climate.at(e.player.x, e.player.y, e.minutes)
        x, y = np.argwhere(e.world.road & ~e.world.river)[0]
        hours, soak = e.travel_time(x, y, 1, 0)
        self.assertLessEqual(hours, ROAD_TRAVEL * 1.8)   # a snowstorm may slow it a little
        self.assertEqual(soak, 0)

    def test_night_is_slower(self):
        e = engine()
        x, y = np.argwhere(e.world.road & ~e.world.river)[0]
        e.now = e.climate.at(x, y, 12 * 60)
        e.now.kind, e.now.light = "Clear", 1.0
        day, _ = e.travel_time(x, y, 1, 0)
        e.now.light = 0.05
        night, _ = e.travel_time(x, y, 1, 0)
        self.assertAlmostEqual(night, day * NIGHT_SLOWDOWN)

    def test_fording_a_river_gets_you_wet(self):
        e = engine()
        w = e.world
        fords = np.argwhere(w.river & ~w.road)
        for x, y in fords:
            start = step_into_from(e, x, y, lambda a, b: w.walkable(a, b) and not w.river[a, b])
            if start is not None and (x, y) not in w.site_at:
                break
        put(e, *start)
        e.player.wet = 0
        self.assertTrue(e.move(int(x - start[0]), int(y - start[1])))
        self.assertIn("You wade across the river.", e.messages)
        self.assertGreater(e.player.wet, 5)

    def test_moving_runs_the_clock(self):
        e = engine()
        move = step_into(e, e.world.walkable)
        before = e.minutes
        self.assertTrue(e.move(*move))
        self.assertGreater(e.minutes, before)


def step_into_from(e, x, y, ok=None):
    """A walkable neighbour of (x, y) to step in from."""
    ok = ok or e.world.walkable
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            if (dx or dy) and e.world.in_bounds(x + dx, y + dy) and ok(x + dx, y + dy):
                return int(x + dx), int(y + dy)
    return None


class TimeTests(unittest.TestCase):
    def test_wait_and_rest(self):
        e = engine()
        start = e.minutes
        e.handle_key(KeySym.PERIOD)
        self.assertEqual(e.minutes, start + 60)
        e.handle_key(KeySym.Z)
        self.assertEqual(e.minutes, start + 9 * 60)

    def test_nightfall_is_announced(self):
        e = engine()
        e.wait(16)
        self.assertIn("Night falls.", e.messages)

    def test_night_shortens_the_view(self):
        e = engine()
        e.minutes = 12 * 60
        e.now = e.climate.at(e.player.x, e.player.y, e.minutes)
        day = e.sight_radius()
        e.minutes = 24 * 60
        e.now = e.climate.at(e.player.x, e.player.y, e.minutes)
        self.assertLess(e.sight_radius(), day)

    def test_in_town_you_stay_comfortable_whatever_the_weather(self):
        e = engine()
        e.wait(48)
        self.assertTrue(e.player.alive)
        self.assertGreater(e.player.body, 36.3)


class KeyTests(unittest.TestCase):
    def test_escape_quits(self):
        self.assertFalse(engine().handle_key(KeySym.ESCAPE))

    def test_tab_cycles_overlays_and_m_reveals(self):
        e = engine()
        for i in range(len(OVERLAYS)):
            self.assertEqual(e.overlay, i)
            e.handle_key(KeySym.TAB)
        self.assertEqual(e.overlay, 0)
        e.handle_key(KeySym.M)
        self.assertTrue(e.reveal)

    def test_the_dead_dont_move(self):
        e = engine()
        e.player.alive = False
        start = (e.player.x, e.player.y, e.minutes)
        for key in (KeySym.RIGHT, KeySym.PERIOD, KeySym.Z):
            e.handle_key(key)
        self.assertEqual((e.player.x, e.player.y, e.minutes), start)


class RenderTests(unittest.TestCase):
    def test_draws_the_player_in_every_overlay(self):
        e = engine()
        console = tcod.console.Console(SCREEN_W, SCREEN_H, order="F")
        cx, cy = camera(e)
        for i in range(len(OVERLAYS)):
            e.overlay = i
            draw(console, e)
            self.assertEqual(console.rgb["ch"][e.player.x - cx, e.player.y - cy], ord("@"))

    def test_unexplored_is_blank_until_revealed(self):
        e = engine()
        console = tcod.console.Console(SCREEN_W, SCREEN_H, order="F")
        draw(console, e)
        cx, cy = camera(e)
        hidden = ~e.explored[cx: cx + 74, cy: cy + 39]
        self.assertTrue(hidden.any())
        self.assertTrue((console.rgb["ch"][:74, :39][hidden] == ord(" ")).all())
        e.reveal = True
        draw(console, e)
        self.assertFalse((console.rgb["ch"][:74, :39] == ord(" ")).any())


if __name__ == "__main__":
    unittest.main()
