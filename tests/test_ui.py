"""The panels over the map, and stamina."""
import unittest

import numpy as np
import tcod
import tcod.event as E
from tcod.event import KeySym

import main
from game.engine import Engine
from game.hud import BARS
from game.player import Player, stamina_status, tire
from game.render import draw
from game.ui import LEFT_HIDE, LEFT_SHOW, LEFT_W, RIGHT_HIDE, RIGHT_SHOW, RIGHT_X, SCREEN_H, SCREEN_W, Panels


def frame(e, seconds=1.0):
    console = tcod.console.Console(SCREEN_W, SCREEN_H, order="F")
    draw(console, e, seconds)
    return console


def text(console, x0=0, x1=SCREEN_W):
    return "\n".join("".join(chr(c) for c in console.rgb["ch"][x0:x1, y]) for y in range(SCREEN_H))


def at(e, ch="@"):
    xs, ys = np.nonzero(frame(e).rgb["ch"] == ord(ch))
    return list(zip(xs.tolist(), ys.tolist()))


class LayoutTests(unittest.TestCase):
    def test_the_window_is_four_by_three(self):
        self.assertEqual(SCREEN_W * 10 * 3, SCREEN_H * 20 * 4)

    def test_tab_cycles_info_map_log_hidden(self):
        p = Panels()
        seen = []
        for _ in range(5):
            seen.append(p.tab if p.right_open else None)
            p.handle_key(KeySym.TAB)
        self.assertEqual(seen, ["info", "map", "log", None, "info"])

    def test_c_hides_and_shows_the_stats(self):
        p = Panels()
        self.assertTrue(p.covers(5, 10))
        p.handle_key(KeySym.C)
        self.assertFalse(p.left_open)
        self.assertFalse(p.covers(5, 10))
        p.handle_key(KeySym.C)
        self.assertTrue(p.left_open)

    def test_buttons_and_tabs_click(self):
        p = Panels()
        tab, x, w = p.tab_spans()[1]
        self.assertTrue(p.click(x + 1, 0))
        self.assertEqual(p.tab, tab)
        self.assertTrue(p.click(RIGHT_HIDE[0], 0))
        self.assertFalse(p.right_open)
        self.assertTrue(p.covers(RIGHT_SHOW[0], 0))       # the little tab to bring it back
        self.assertFalse(p.covers(RIGHT_X + 3, 10))
        self.assertTrue(p.click(RIGHT_SHOW[0], 0))
        self.assertTrue(p.right_open)
        self.assertTrue(p.click(LEFT_HIDE[0], 0))
        self.assertFalse(p.left_open)
        self.assertTrue(p.click(LEFT_SHOW[0], 0))
        self.assertTrue(p.left_open)
        self.assertFalse(p.click(60, 20))                # the map, not a button

    def test_hiding_panels_leaves_the_map_where_it_was(self):
        for local in (False, True):
            e = Engine.new(1)
            if local:
                e.enter_region()
            before = frame(e).rgb.copy()
            spot = at(e)
            e.panels.left_open = e.panels.right_open = False
            after = frame(e).rgb
            self.assertEqual(at(e), spot)
            middle = (slice(LEFT_W, RIGHT_X), slice(1, SCREEN_H - 5))
            self.assertTrue(np.array_equal(before["ch"][middle], after["ch"][middle]))
            self.assertTrue((after["ch"][3: LEFT_W, 5: 30] != before["ch"][3: LEFT_W, 5: 30]).any())

    def test_you_stay_in_the_middle_by_the_edge_of_the_map(self):
        e = Engine.new(1)
        e.enter_region()
        e.lx, e.ly = 0, 0
        e.update_view()
        self.assertEqual(at(e), [(SCREEN_W // 2, SCREEN_H // 2)])


class PanelContentTests(unittest.TestCase):
    def test_stats_panel_shows_the_bars(self):
        e = Engine.new(1)
        left = text(frame(e), 0, LEFT_W)
        for label, *_ in BARS:
            self.assertIn(label, left)
        self.assertIn("Warmth", left)
        self.assertIn("Condition", left)

    def test_each_tab_draws(self):
        e = Engine.new(1)
        e.say("A message to find in the log.")
        e.panels.show("info")
        self.assertIn("Seed 1", text(frame(e), RIGHT_X))
        e.panels.show("map")
        console = frame(e)
        self.assertIn("The world", text(console, RIGHT_X))
        self.assertGreater((console.rgb["ch"][RIGHT_X:] == ord("▀")).sum(), 300)
        e.enter_region()
        self.assertIn("This region", text(frame(e), RIGHT_X))
        e.panels.show("log")
        self.assertIn("message to find", text(frame(e), RIGHT_X))

    def test_recent_messages_run_along_the_bottom_unless_the_log_is_open(self):
        e = Engine.new(1)
        e.say("Something just happened.")
        self.assertIn("Something just happened.", text(frame(e), LEFT_W, RIGHT_X))
        e.panels.show("log")
        self.assertNotIn("Something just happened.", text(frame(e), LEFT_W, RIGHT_X))

    def test_the_log_scrolls(self):
        e = Engine.new(1)
        for i in range(80):
            e.say(f"Message number {i}.")
        e.panels.show("log")
        self.assertIn("Message number 79.", text(frame(e), RIGHT_X))
        e.handle_key(KeySym.PAGEUP)
        e.handle_key(KeySym.PAGEUP)
        self.assertNotIn("Message number 79.", text(frame(e), RIGHT_X))
        e.handle_key(KeySym.END)
        self.assertIn("Message number 79.", text(frame(e), RIGHT_X))
        e.mouse = (RIGHT_X + 5, 10)
        main.handle_mouse(e, E.MouseWheel(x=0, y=5, flipped=False))
        self.assertEqual(e.panels.log_scroll, 15)

    def test_clicks_on_a_panel_dont_reach_the_map(self):
        e = Engine.new(1)
        e.enter_region()
        before = len(e.messages)
        main.handle_mouse(e, E.MouseButtonDown(position=(10, 20), tile=(10, 20), button=E.MouseButton.LEFT))
        main.handle_mouse(e, E.MouseButtonDown(position=(10, 20), tile=(10, 20), button=E.MouseButton.RIGHT))
        self.assertEqual(len(e.messages), before)
        self.assertFalse(e.autopath)
        x = e.panels.tab_spans()[2][1]
        main.handle_mouse(e, E.MouseButtonDown(position=(x, 0), tile=(x, 0), button=E.MouseButton.LEFT))
        self.assertEqual(e.panels.tab, "log")

    def test_overlays_moved_to_o(self):
        e = Engine.new(1)
        e.handle_key(KeySym.O)
        self.assertEqual(e.overlay, 1)
        e.handle_key(KeySym.TAB)
        self.assertEqual(e.overlay, 1)
        self.assertEqual(e.panels.tab, "map")


class StaminaTests(unittest.TestCase):
    def test_effort_tires_and_rest_restores(self):
        p = Player(0, 0)
        tire(p, 2, 1.0)
        self.assertLess(p.stamina, 100)
        low = p.stamina
        tire(p, 1, 0.0)
        self.assertGreater(p.stamina, low)
        tire(p, 100, 2.0)
        self.assertEqual(p.stamina, 0)
        self.assertEqual(stamina_status(p.stamina), "Exhausted")

    def test_walking_tires_you_and_hard_ground_more(self):
        e = Engine.new(1)
        e.enter_region()
        start = e.player.stamina
        for _ in range(20):
            e.move_local(1, 0) or e.move_local(-1, 0)
        self.assertLess(e.player.stamina, start)
        e.wait(2)
        self.assertGreater(e.player.stamina, start - 1)

    def test_exhaustion_is_announced(self):
        e = Engine.new(1)
        e.player.stamina = 16
        e.pass_time(1, effort=1.0)
        self.assertIn("You're exhausted.", e.messages)


if __name__ == "__main__":
    unittest.main()
