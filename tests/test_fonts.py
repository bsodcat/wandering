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

    def test_items_not_the_same_in_every_font_show_a_question_mark_in_every_font(self):
        for font in available_fonts():
            ts = make_tileset(font, (10, 20))
            mark = ts.get_tile(ord("?"))[..., 3]
            self.assertTrue(mark.any(), font)
            # soap's ▪ is in no font; nails' ¦ is in Lucida Console only, but shows ? there too
            for ch in ("▪", "¦"):
                self.assertTrue(np.array_equal(ts.get_tile(ord(ch))[..., 3], mark), (font, ch))
            self.assertFalse(np.array_equal(ts.get_tile(ord("~"))[..., 3], mark), font)   # the scroll

    def test_question_marks_are_kept_for_items_that_need_them(self):
        import tcod
        from game import items, tiles as T
        cp437 = set(tcod.tileset.CHARMAP_CP437)
        self.assertNotIn("?", {k.char for k in items.KINDS.values()} | {t.char for t in T.TILES})
        self.assertEqual(items.KINDS["sealed scroll"].char, "~")
        # tiles are never shown as a ?: every tile glyph is in the set every font draws
        self.assertEqual([t.name for t in T.TILES if ord(t.char) not in cp437], [])

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
