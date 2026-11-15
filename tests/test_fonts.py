"""Fonts: every font, at every size, fills its tiles, and blocks join edge to edge."""
import unittest

import numpy as np

from game.display import drawn_glyphs, ink_box, make_tileset, scale_tile
from game.options import FONT_SIZES, available_fonts


class FontTests(unittest.TestCase):
    def test_every_font_fills_its_tiles(self):
        for font in available_fonts():
            for size in FONT_SIZES[2:6]:             # 8x16 up; 6x12 is too small to fill
                ts = make_tileset(font, size)
                self.assertEqual((ts.tile_width, ts.tile_height), size, font)
                x0, y0, x1, y1 = ink_box(ts)
                self.assertGreater((x1 - x0) / size[0], 0.7, (font, size))
                self.assertGreater((y1 - y0) / size[1], 0.6, (font, size))

    def test_blocks_meet_the_edges(self):
        for font in available_fonts():
            ts = make_tileset(font, (12, 24))
            full = ts.get_tile(ord("█"))[..., 3]
            self.assertTrue((full > 200).all(), font)
            top = ts.get_tile(ord("▀"))[..., 3]
            self.assertTrue((top[:12] > 200).all() and (top[12:] < 50).all(), font)

    def test_no_glyph_the_game_draws_is_blank_in_any_font(self):
        import glob
        import re
        from game.display import game_glyphs, has_ink
        glyphs = set(game_glyphs())
        for path in glob.glob("game/*.py"):          # one-character glyphs anywhere else (creatures, map)
            glyphs |= set(re.findall(r'"([^\x00-\x7f])"', open(path, encoding="utf-8").read()))
        for font in available_fonts():
            for size in ((8, 16), (10, 20), (16, 32)):
                ts = make_tileset(font, size)
                blank = [c for c in glyphs if c.strip() and not has_ink(ts, c)]
                self.assertEqual(blank, [], (font, size))

    def test_a_font_without_a_glyph_draws_the_closest_shape_or_a_question_mark(self):
        from game.display import with_fallbacks
        tile = lambda ts, ch: ts.get_tile(ord(ch))[..., 3]
        neue = make_tileset("Classic Console Neue", (8, 16))
        old = make_tileset("Terminal", (8, 16))                      # code page 437 only
        for ch, closest in (("▪", "■"), ("⌙", "⌐"), ("†", "┼"), ("⊟", "▄"), ("☂", "↓")):
            self.assertFalse(np.array_equal(tile(neue, ch), tile(neue, closest)), ch)   # its own glyph here
            self.assertTrue(np.array_equal(tile(old, ch), tile(old, closest)), ch)      # the stand-in there
        import tcod
        bare = tcod.tileset.Tileset(8, 16)                            # a font with nothing but a ?
        bare.set_tile(ord("?"), np.full((16, 8), 255, np.uint8))
        with_fallbacks(bare, {ord("?")})
        self.assertTrue(np.array_equal(tile(bare, "†"), tile(bare, "?")))

    def test_every_glyph_the_game_draws_has_a_stand_in_every_font_has(self):
        import tcod
        from game import glyphs, items, tiles as T
        cp437 = set(tcod.tileset.CHARMAP_CP437)
        self.assertNotIn("?", {k.char for k in items.KINDS.values()} | {t.char for t in T.TILES})
        self.assertEqual(items.KINDS["sealed scroll"].char, "∫")
        # tiles are never shown as a ?: every tile glyph is in code page 437 or stands in with one that is
        missing = [t.name for t in T.TILES if glyphs.stand_in(t.char, cp437 | set(map(ord, "▏▎▍▋▊▉╭╮╰╯"))) == "?"]
        self.assertEqual(missing, [])

    def test_classic_console_neue_is_pixel_sharp_at_its_own_sizes(self):
        for size in ((8, 16), (16, 32)):
            ts = make_tileset("Classic Console Neue", size)
            for ch in "Mg@†☠":
                alpha = ts.get_tile(ord(ch))[..., 3]
                self.assertEqual(set(np.unique(alpha)) - {0, 255}, set(), (size, ch))

    def test_drawn_lines_cross_the_whole_tile(self):
        g = drawn_glyphs(10, 20)
        self.assertTrue((g["─"][10] == 255).all())
        self.assertTrue((g["│"][:, 5] == 255).all())

    def test_scaling_a_bitmap_keeps_it_crisp(self):
        tile = np.array([[0, 255], [255, 0]], np.uint8)
        big = scale_tile(tile, 4, 4)
        self.assertEqual(set(np.unique(big)), {0, 255})
        self.assertEqual(big.shape, (4, 4))


if __name__ == "__main__":
    unittest.main()


class BundledFontTests(unittest.TestCase):
    def test_bigblue_terminal_comes_with_the_game(self):
        from game.options import NATIVE, OWN_FONT_DIR, Settings, font_path
        self.assertIn("BigBlue Terminal", available_fonts())
        self.assertTrue(font_path("BigBlue Terminal").startswith(OWN_FONT_DIR))
        tiles = make_tileset("BigBlue Terminal", NATIVE["BigBlue Terminal"][0])
        self.assertEqual((tiles.tile_width, tiles.tile_height), (8, 12))
        self.assertTrue((tiles.get_tile(ord("A"))[..., 3] > 0).any())
        self.assertEqual(Settings(font="BigBlue Terminal").cell((1920, 1040)), (8, 12))
