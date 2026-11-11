"""A bigger window shows more tiles, not bigger pixels; the panels stay pinned to its edges."""
import unittest

import numpy as np
import tcod
from tcod.event import KeySym

from game.display import grid
from game.engine import Engine
from game.render import draw, map_cell
from game.ui import LEFT_W, MIN_H, MIN_W, RIGHT_W


def frame(e, cols, rows):
    console = tcod.console.Console(cols, rows, order="F")
    draw(console, e, 1.0)
    return console


def text(console, x0, x1):
    return "\n".join("".join(chr(c) for c in console.rgb["ch"][x0:x1, y]) for y in range(console.height))


class GridTests(unittest.TestCase):
    def test_the_default_window_is_the_default_screen(self):
        self.assertEqual(grid((1200, 900), (10, 20), "Auto"), (1, 120, 45))

    def test_a_bigger_window_gets_more_tiles_not_bigger_pixels(self):
        self.assertEqual(grid((2000, 1060), (10, 20), "Auto"), (1, 200, 53))
        self.assertEqual(grid((2560, 1440), (10, 20), "Auto"), (1, 256, 72))

    def test_any_shape(self):
        k, cols, rows = grid((2400, 600), (10, 20), "Auto")     # a long, low window
        self.assertEqual((k, cols, rows), (1, 240, 30))
        k, cols, rows = grid((900, 1400), (10, 20), "Auto")     # a tall, narrow one
        self.assertEqual((k, cols, rows), (1, 90, 70))

    def test_auto_scales_up_when_twice_the_default_screen_fits(self):
        self.assertEqual(grid((1440, 1080), (6, 12), "Auto"), (2, 120, 45))
        self.assertEqual(grid((2000, 1300), (6, 12), "Auto"), (2, 166, 54))

    def test_a_chosen_scale_comes_down_if_the_screen_would_be_too_small(self):
        self.assertEqual(grid((2560, 1440), (10, 20), 2), (2, 128, 36))
        self.assertEqual(grid((1200, 900), (10, 20), 3), (1, 120, 45))

    def test_never_fewer_tiles_than_the_panels_need(self):
        k, cols, rows = grid((400, 300), (10, 20), "Auto")
        self.assertEqual((cols, rows), (MIN_W, MIN_H))      # shown shrunk instead


class WideScreenTests(unittest.TestCase):
    def test_panels_hug_the_edges_of_any_screen(self):
        for cols, rows in ((120, 45), (200, 53), (90, 70)):
            e = Engine.new(1)
            console = frame(e, cols, rows)
            self.assertIn("Health", text(console, 0, LEFT_W))
            right = text(console, cols - RIGHT_W, cols)
            self.assertIn("Info", right)
            self.assertIn("Seed", right)
            self.assertEqual(chr(console.rgb["ch"][cols - 2, 0]), "►")

    def test_you_stay_in_the_middle_and_the_map_fills_the_rest(self):
        e = Engine.new(1)
        e.enter_region()
        console = frame(e, 200, 53)
        xs, ys = np.nonzero(console.rgb["ch"] == ord("@"))
        self.assertEqual((int(xs[0]), int(ys[0])), (100, 26))
        e.panels.left_open = e.panels.right_open = False
        e.level.explored[:] = True
        console = frame(e, 200, 53)
        level_cols = (console.rgb["ch"][:, 10] != ord(" ")).sum()
        self.assertGreaterEqual(level_cols, min(e.level.width, 200) - 2)   # the map fills the screen's width

    def test_mouse_and_clicks_follow_the_screen_size(self):
        e = Engine.new(1)
        frame(e, 200, 53)
        self.assertIsNone(map_cell(e, 190, 10))         # the right panel, at the new right edge
        self.assertIsNotNone(map_cell(e, 120, 10))      # map, where the panel used to be
        tab, x, w = e.panels.tab_spans()[2]
        self.assertGreater(x, 170)
        self.assertTrue(e.panels.click(x + 1, 0))
        self.assertEqual(e.panels.tab, "log")

    def test_menu_stays_in_the_middle_and_clickable(self):
        e = Engine.new(1)
        e.handle_key(KeySym.ESCAPE)
        console = frame(e, 200, 53)
        from game.options import box, row_y
        x, y, w, h = box(4, 200, 53)
        self.assertEqual(x, (200 - w) // 2)
        self.assertIn("Paused", text(console, x, x + w))
        self.assertEqual(e.menu.click(x + 20, row_y(4, 3, 200, 53)), "quit")


if __name__ == "__main__":
    unittest.main()
