"""The pause menu, the options screen and the saved settings."""
import os
import tempfile
import unittest

import tcod
from tcod.event import KeySym, Modifier

from game.engine import Engine
from game.options import (FONT_SIZES, RESOLUTIONS, Menu, Settings, available_fonts, box, row_y,
                          value_span)
from game.render import draw
from game.ui import SCREEN_H, SCREEN_W


def screen_text(e):
    console = tcod.console.Console(SCREEN_W, SCREEN_H, order="F")
    draw(console, e, 1.0)
    return "\n".join("".join(chr(c) for c in console.rgb["ch"][:, y]) for y in range(SCREEN_H))


class SettingsTests(unittest.TestCase):
    def test_every_choice_is_four_by_three(self):
        for w, h in RESOLUTIONS:
            self.assertEqual(w * 3, h * 4)
        for size in FONT_SIZES[1:]:
            self.assertEqual(size[0] * 2, size[1])       # 120 x 45 tiles of 1:2 make 4:3

    def test_auto_font_size_fills_the_resolution(self):
        s = Settings(resolution=(1200, 900))
        self.assertEqual(s.cell(), (10, 20))
        self.assertEqual(s.frame(), (1200, 900))
        s.resolution = (1920, 1440)
        self.assertEqual(s.cell(), (16, 32))
        self.assertEqual(s.frame(), (1920, 1440))
        s.font_size = (8, 16)
        self.assertEqual(s.frame(), (960, 720))

    def test_saves_and_loads(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "sub", "settings.json")
            Settings(fullscreen=True, resolution=(1600, 1200), font="Consolas", font_size=(12, 24)).save(path)
            s = Settings.load(path)
            self.assertEqual((s.fullscreen, s.resolution, s.font, s.font_size),
                             (True, (1600, 1200), "Consolas", (12, 24)))

    def test_bad_or_missing_settings_fall_back_to_defaults(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(Settings.load(os.path.join(d, "none.json")), Settings())
            path = os.path.join(d, "bad.json")
            with open(path, "w") as f:
                f.write('{"resolution": [123, 45], "font": "Comic Sans", "font_size": [7, 7]}')
            s = Settings.load(path)
            self.assertEqual((s.resolution, s.font, s.font_size), ((1200, 900), "Terminal", "Auto"))
            with open(path, "w") as f:
                f.write("not json")
            self.assertEqual(Settings.load(path), Settings())


class MenuTests(unittest.TestCase):
    def test_pause_menu_to_options_and_back(self):
        m = Menu()
        m.show("pause")
        m.handle_key(KeySym.DOWN)
        m.handle_key(KeySym.RETURN)
        self.assertEqual(m.screen, "options")
        m.handle_key(KeySym.ESCAPE)
        self.assertEqual(m.screen, "pause")
        m.handle_key(KeySym.ESCAPE)
        self.assertFalse(m.open)

    def test_left_and_right_change_settings(self):
        m = Menu()
        m.show("options")
        m.handle_key(KeySym.RIGHT)                       # Display
        self.assertTrue(m.settings.fullscreen and m.changed)
        m.handle_key(KeySym.DOWN)                        # Resolution
        before = m.settings.resolution
        m.handle_key(KeySym.RIGHT)
        self.assertEqual(RESOLUTIONS.index(m.settings.resolution), RESOLUTIONS.index(before) + 1)
        m.handle_key(KeySym.LEFT)
        self.assertEqual(m.settings.resolution, before)
        m.handle_key(KeySym.DOWN)                        # Font
        m.handle_key(KeySym.RIGHT)
        if len(available_fonts()) > 1:
            self.assertNotEqual(m.settings.font, "Terminal")
        m.handle_key(KeySym.DOWN)                        # Font size
        m.handle_key(KeySym.RIGHT)
        self.assertEqual(m.settings.font_size, FONT_SIZES[1])

    def test_mouse_steps_values_and_picks_items(self):
        m = Menu()
        m.show("options")
        n = len(m.items())
        left, right = value_span(n)
        y = row_y(n, 1)                                  # Resolution
        before = RESOLUTIONS.index(m.settings.resolution)
        m.click(right, y)
        self.assertEqual(RESOLUTIONS.index(m.settings.resolution), before + 1)
        m.click(left, y)
        m.click(left, y)
        self.assertEqual(RESOLUTIONS.index(m.settings.resolution), before - 1)
        x = box(n)[0] + 5
        m.click(x, row_y(n, n - 1))                      # Back
        self.assertEqual(m.screen, "pause")
        self.assertEqual(m.click(x + 15, row_y(3, 2)), "quit")

    def test_alt_enter_and_f11_toggle_fullscreen_anywhere(self):
        e = Engine.new(1)
        e.handle_key(KeySym.F11)
        self.assertTrue(e.menu.settings.fullscreen)
        e.handle_key(KeySym.RETURN, Modifier.LALT)
        self.assertFalse(e.menu.settings.fullscreen)
        self.assertIsNone(e.level)                       # Alt+Enter didn't also go into the region

    def test_the_game_waits_while_the_menu_is_up(self):
        e = Engine.new(1)
        e.handle_key(KeySym.ESCAPE)
        start = (e.player.x, e.player.y, e.minutes)
        e.handle_key(KeySym.RIGHT)
        e.handle_key(KeySym.Z)
        self.assertEqual((e.player.x, e.player.y, e.minutes), start)

    def test_menus_draw(self):
        e = Engine.new(1)
        e.handle_key(KeySym.ESCAPE)
        text = screen_text(e)
        for item in ("Paused", "Resume", "Options", "Quit"):
            self.assertIn(item, text)
        e.menu.show("options")
        text = screen_text(e)
        for item in ("Display", "Windowed", "Resolution", "1200 x 900", "Font", "Terminal", "Font size", "Auto"):
            self.assertIn(item, text)


if __name__ == "__main__":
    unittest.main()
