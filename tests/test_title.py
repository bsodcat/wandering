"""The title screen, its choices and the dev arena."""
import unittest

import numpy as np
import tcod
from tcod.event import KeySym

from game import __version__
from game import arena
from game import people
from game import tiles as T
from game.engine import Engine
from game.farming import ANIMALS
from game.hud import draw_menu
from game.options import Menu
from game.render import draw
from game.title import (CREATOR, GAME_TITLE, ITEMS, PURPLE, SUBTITLE, Title, draw_title, item_rows, key_text,
                        main_layout)


def screen(title, cols=120, rows=45):
    console = tcod.console.Console(cols, rows, order="F")
    draw_title(console, title, 0.0)
    return console


def row_text(console, y):
    return "".join(chr(c) for c in console.rgb["ch"][:, y])


def find(console, text):
    for y in range(console.height):
        x = row_text(console, y).find(text)
        if x >= 0:
            return x, y
    return None


class TitleScreenTests(unittest.TestCase):
    def test_title_subtitle_choices_and_footer(self):
        for cols, rows in ((120, 45), (80, 30), (200, 60)):
            c = screen(Title(Menu()), cols, rows)
            x, y = find(c, GAME_TITLE)
            self.assertEqual(tuple(c.rgb["fg"][x, y]), PURPLE)
            sx, sy = find(c, SUBTITLE)
            self.assertEqual(sy, y + 2)
            self.assertEqual(tuple(c.rgb["fg"][sx, sy]), (255, 255, 255))
            last = sy
            for item in ITEMS:
                self.assertIsNotNone(find(c, item), item)
                self.assertGreater(find(c, item)[1], last)
                last = find(c, item)[1]
            vx, vy = find(c, f"Version {__version__}")
            cx, cy = find(c, CREATOR)
            self.assertEqual((vy, cy > vx), (cy, True))     # beside it, to the right
            self.assertEqual(vy, rows - 2)
            self.assertLess(max(c.rgb["fg"][cx, cy]), 100)  # dark grey
            hx, hy = find(c, " Enter ")
            self.assertGreater(hy, last)                    # the keys are under the choices
            self.assertNotEqual(tuple(c.rgb["bg"][hx, hy]), tuple(c.rgb["bg"][hx - 2, hy]))   # picked out

    def test_keys_are_marked(self):
        self.assertEqual(key_text("[Esc] back"), [(" Esc ", True), (" back", False)])

    def test_choosing_with_keys(self):
        t = Title(Menu())
        self.assertEqual(t.handle_key(KeySym.RETURN), ("new", None, None))
        t.handle_key(KeySym.DOWN)
        t.handle_key(KeySym.DOWN)
        self.assertEqual(t.handle_key(KeySym.RETURN), ("arena",))
        t.handle_key(KeySym.UP)
        t.handle_key(KeySym.UP)
        t.handle_key(KeySym.UP)
        self.assertEqual(ITEMS[t.cursor], "Quit Game")
        self.assertEqual(t.handle_key(KeySym.RETURN), ("quit",))

    def test_options_and_about(self):
        menu = Menu()
        t = Title(menu)
        t.cursor = ITEMS.index("Options")
        t.handle_key(KeySym.RETURN)
        self.assertEqual(menu.screen, "options")
        menu.handle_key(KeySym.ESCAPE)
        self.assertFalse(menu.open)                     # back to the title, not a pause menu
        t.cursor = ITEMS.index("About")
        t.handle_key(KeySym.RETURN)
        c = screen(t)
        self.assertIsNotNone(find(c, "About"))
        self.assertIsNotNone(find(c, CREATOR))
        t.handle_key(KeySym.ESCAPE)
        self.assertEqual((t.screen, ITEMS[t.cursor]), ("main", "About"))

    def test_mouse_points_and_clicks(self):
        t = Title(Menu())
        screen(t)
        y, x0, x1 = item_rows(t)[ITEMS.index("Dev Arena")]
        t.hover((x0 + x1) // 2, y)
        self.assertEqual(ITEMS[t.cursor], "Dev Arena")
        self.assertEqual(t.click((x0 + x1) // 2, y), ("arena",))
        self.assertIsNone(t.click(0, 0))

    def test_the_options_screen_draws_over_the_title(self):
        menu = Menu()
        menu.top = None
        menu.show("options")
        c = screen(Title(menu))
        draw_menu(c, menu)
        self.assertIsNotNone(find(c, "Options"))
        self.assertIsNotNone(find(c, "Esc closes"))

    def test_fits_the_smallest_screen(self):
        lay = main_layout(30)
        self.assertGreaterEqual(lay["title"], 1)
        self.assertLess(lay["hints"] + 1, 28)            # the hints end above the version line


class CreateWorldTests(unittest.TestCase):
    def test_type_a_seed_and_begin_in_that_world(self):
        t = Title(Menu())
        t.cursor = ITEMS.index("Create a World")
        t.handle_key(KeySym.RETURN)
        self.assertEqual(t.screen, "create")
        for _ in range(12):
            t.handle_key(KeySym.BACKSPACE)
        for key in (KeySym.N4, KeySym.N2):
            t.handle_key(key)
        self.assertEqual(t.seed, 42)
        c = screen(t)
        self.assertIsNotNone(find(c, "42_"))
        self.assertIsNotNone(find(c, "You start in"))
        self.assertTrue((c.rgb["ch"] == ord("▀")).sum() > 500)      # the world preview
        action = t.handle_key(KeySym.RETURN)
        self.assertEqual(action[:2], ("new", 42))
        e = Engine.new(action[1], action[2])
        self.assertEqual(e.world.seed, 42)
        self.assertTrue(np.array_equal(e.world.biome, Engine.new(42).world.biome))

    def test_random_seed_and_back(self):
        t = Title(Menu())
        t.show("create")
        before = t.seed_text
        t.handle_key(KeySym.R)
        self.assertNotEqual(t.seed_text, before)
        t.handle_key(KeySym.ESCAPE)
        self.assertEqual(t.screen, "main")


class ArenaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.e = Engine.arena()

    def test_size_and_start(self):
        lvl = self.e.level
        self.assertEqual(lvl.tiles.shape, (256, 256))
        self.assertEqual((self.e.lx, self.e.ly), arena.SPAWN)
        self.assertTrue(lvl.explored.all())

    def test_every_tile_is_in_the_gallery(self):
        lvl = self.e.level
        spots = arena.gallery_spots()
        self.assertEqual(set(spots), set(range(len(T.TILES))))
        for tile, (x, y) in spots.items():
            self.assertEqual(lvl.tiles[x, y], tile, T.TILES[tile].name)

    def test_every_person_and_animal(self):
        kinds = {a.kind for a in self.e.level.actors}
        self.assertTrue(set(people.JOBS) <= kinds)
        self.assertTrue(set(ANIMALS) <= kinds)
        self.assertTrue({"inn", "bakery", "butcher", "house"} <= {b.kind for b in self.e.level.buildings})

    def test_everyone_stands_on_floor_and_moves(self):
        e = self.e
        for _ in range(30):
            e.wait(0.05)
        for a in e.level.actors:
            self.assertTrue(T.WALK[e.level.tiles[a.x, a.y]], a.kind)

    def test_trees_have_leaves_and_you_cannot_leave(self):
        e = self.e
        self.assertGreater((e.level.canopy > 0).sum(), 500)
        self.assertFalse(e.leave_region())
        self.assertIn("dev arena", e.messages[-1])

    def test_main_menu_goes_back_to_the_title(self):
        e = Engine.arena()
        e.handle_key(KeySym.ESCAPE)
        e.menu.cursor = e.menu.items().index("Main menu")
        e.handle_key(KeySym.RETURN)
        self.assertTrue(e.to_title)
        self.assertFalse(e.menu.open)

    def test_draws(self):
        console = tcod.console.Console(120, 45, order="F")
        draw(console, self.e, 1.0)
        self.assertTrue((console.rgb["ch"] == ord("@")).any())


if __name__ == "__main__":
    unittest.main()
