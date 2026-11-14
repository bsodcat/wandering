"""The Updates screen on the title screen, and the Controls list in Options."""
import time
import unittest

import tcod
from tcod.event import KeySym

from game import __version__, updates
from game.controls import CONTROLS
from game.hud import draw_menu
from game.options import OPTION_ROWS, Menu
from game.title import ITEMS, UPDATE_ROWS, Title, draw_title, item_rows


def screen_text(con) -> str:
    return "\n".join("".join(chr(c) for c in con.rgb["ch"][:, r]) for r in range(con.height))


def wait_for(checker, seconds=3.0):
    end = time.monotonic() + seconds
    while checker.busy and time.monotonic() < end:
        time.sleep(0.01)


class UpdatesTests(unittest.TestCase):
    def title(self):
        menu = Menu()
        menu.top = None
        t = Title(menu)
        t.cursor = ITEMS.index("Updates")
        t.activate()
        return t

    def test_it_opens_from_the_title_and_esc_comes_back(self):
        t = self.title()
        self.assertEqual(t.screen, "updates")
        self.assertEqual(t.items(), UPDATE_ROWS)
        t.handle_key(KeySym.ESCAPE)
        self.assertEqual(t.screen, "main")
        self.assertEqual(ITEMS[t.cursor], "Updates")

    def test_it_lists_whats_new_in_every_version(self):
        t = self.title()
        con = tcod.console.Console(120, 45, order="F")
        draw_title(con, t, 0.0)
        text = screen_text(con)
        self.assertIn("Updates", text)
        self.assertIn("Stone cities", text)
        for _ in range(10):
            t.handle_key(KeySym.PAGEDOWN)
        draw_title(con, t, 0.0)
        self.assertIn("Version 1.0.0", screen_text(con))
        self.assertGreater(t.notes_scroll, 0)
        versions = [v for v, _, _ in updates.NOTES]
        self.assertIn(__version__, versions)

    def test_the_choices_go_across_and_take_clicks(self):
        t = self.title()
        t.handle_key(KeySym.RIGHT)
        self.assertEqual(UPDATE_ROWS[t.cursor], "Download page")
        y, x0, x1 = item_rows(t)[UPDATE_ROWS.index("Back")]
        t.click(x0 + 1, y)
        self.assertEqual(t.screen, "main")

    def test_versions_compare(self):
        self.assertTrue(updates.newer("v1.10.0", "1.9.2"))
        self.assertTrue(updates.newer("1.3.1", "1.3.0"))
        self.assertFalse(updates.newer("v1.3.0", "1.3.0"))
        self.assertFalse(updates.newer("1.2.9", "1.3.0"))
        self.assertTrue(updates.newer("v1.4.0", "1.4.0-beta.1"))      # the release after its beta
        self.assertTrue(updates.newer("1.4.0-beta.2", "1.4.0-beta.1"))
        self.assertFalse(updates.newer("v1.3.0", "1.4.0-beta.1"))

    def test_checking_says_whether_theres_a_newer_one(self):
        c = updates.Checker()
        c.check(lambda: "v99.0.0")
        wait_for(c)
        self.assertIn("99.0.0 is out", c.status)
        c.check(lambda: f"v{__version__}")
        wait_for(c)
        self.assertIn("up to date", c.status)

        def offline():
            raise OSError("no network")
        c.check(offline)
        wait_for(c)
        self.assertIn("Couldn't check", c.status)


class ControlsTests(unittest.TestCase):
    def menu(self):
        m = Menu()
        m.show("options")
        m.cursor = OPTION_ROWS.index("Controls")
        m.activate()
        return m

    def test_options_has_a_controls_list(self):
        m = self.menu()
        self.assertEqual(m.screen, "controls")
        con = tcod.console.Console(120, 45, order="F")
        draw_menu(con, m)
        text = screen_text(con)
        self.assertIn("Controls", text)
        self.assertIn("equipment", text)
        keys = [k for _, rows in CONTROLS for k, _ in rows]
        for key in ("e", "q", "i", "g", "x", "z", "Esc", "Tab"):
            self.assertIn(key, keys)

    def test_it_scrolls_on_a_small_screen_and_goes_back(self):
        m = self.menu()
        m.cols, m.rows = 80, 30
        con = tcod.console.Console(80, 30, order="F")
        draw_menu(con, m)
        m.handle_key(KeySym.PAGEDOWN)
        self.assertGreater(m.controls_scroll, 0)
        m.scroll_by(10_000)
        draw_menu(con, m)
        self.assertIn("dev console", screen_text(con))
        m.scroll_by(-10_000)
        self.assertEqual(m.controls_scroll, 0)
        m.handle_key(KeySym.ESCAPE)
        self.assertEqual(m.screen, "options")
        self.assertEqual(OPTION_ROWS[m.cursor], "Controls")

    def test_the_wheel_scrolls_it(self):
        import tcod.event as E
        import main
        from game.title import Title as T
        m = self.menu()
        m.cols, m.rows = 80, 30
        m.controls_shown = 10
        main.title_event(T(m), m, E.MouseWheel(x=0, y=-1, flipped=False))
        self.assertGreater(m.controls_scroll, 0)


if __name__ == "__main__":
    unittest.main()
