"""Boxes you pick from (shops, barrels, chests): rows one under another, wide enough for their
text, and long lists scrolling."""
import unittest

from tcod.event import KeySym

from game import shop as shops
from game import items
from game.items import Inventory


class Rows(shops.Modal):
    """A box of made-up rows."""
    greeting = "Pick one."

    def __init__(self, labels):
        super().__init__()
        self._labels = labels

    def labels(self):
        return self._labels

    def act(self, engine):
        return True


def chest(kinds: int, name_len: int = 6) -> shops.Modal:
    box = Rows([f"Take {i + 1} thing{i:02d}" + "x" * name_len for i in range(kinds)] + ["Close the chest"])
    box.cols, box.rows = 120, 45
    return box


class LayoutTests(unittest.TestCase):
    def test_rows_are_always_one_under_another(self):
        for kinds in (1, 3, 40):
            box = chest(kinds)
            ys = [box.row_y(i) for i in box.visible_rows()]
            self.assertEqual(ys, list(range(ys[0], ys[0] + len(ys))), kinds)

    def test_box_grows_to_fit_long_names(self):
        short, long = chest(2), chest(2, name_len=70)
        self.assertGreater(long.width(), short.width())
        self.assertTrue(all(len(label) + 6 <= long.width() for label in long.labels()))
        self.assertLessEqual(long.width(), long.cols - 4)

    def test_long_lists_scroll_inside_the_screen(self):
        box = chest(60)
        x, y, w, h = box.box()
        self.assertGreaterEqual(y, 1)
        self.assertLessEqual(y + h, box.rows - 1)
        self.assertTrue(box.scrollable())
        bar = box.scroll_bar()
        self.assertIsNotNone(bar)
        for _ in range(50):                        # Down wraps past the end, so not all the way
            box.handle_key(KeySym.DOWN, None)
        self.assertIn(box.cursor, box.visible_rows())
        self.assertGreater(box.top, 0)
        box.scroll_by(-100)                        # the wheel, all the way up
        self.assertEqual(box.top, 0)
        self.assertIn(box.cursor, box.visible_rows())
        box.handle_key(KeySym.END, None)
        self.assertEqual(box.cursor, len(box.labels()) - 1)

    def test_greeting_and_news_wrap_rather_than_cut(self):
        box = chest(30)
        box.said = ["You take " + ", ".join(f"thing{i}" for i in range(30)) + "."]
        lines = box.said_lines()
        self.assertTrue(all(len(line) <= box.width() - 4 for line in lines))
        self.assertTrue(lines[0].startswith("You take"))       # it reads from the start
        self.assertLessEqual(len(lines), shops.MOST_SAID)


class ContainerTests(unittest.TestCase):
    def test_a_full_chest_lists_everything_and_keeps_its_greeting_short(self):
        store = Inventory()
        for kind in list(items.KINDS)[:40]:
            store.add(kind, 2)
        box = shops.Container("a chest", store, Inventory())
        box.cols, box.rows = 120, 45
        self.assertEqual(len(box.labels()), len(store) + 2)     # each kind, everything, close
        self.assertEqual(len(box.greeting_lines()), 1)
        self.assertTrue(box.scrollable())


class ShopTabsTests(unittest.TestCase):
    def shop(self):
        deals = [shops.Deal(f"Buy thing {i}: 1 coin", {"coin": 1}, {"dagger": 1}) for i in range(30)]
        deals += [shops.Deal("Sell your tin whistle (1): 2 coins each", {"tin whistle": 1}, {"coin": 2}, every=True)]
        s = shops.Shop("A shopkeeper", "Hello.", deals, buys=True)
        s.cols, s.rows = 120, 60
        return s

    def test_a_long_shop_shows_fifteen_rows_and_scrolls(self):
        s = self.shop()
        self.assertEqual(s.shown(), shops.MOST_ROWS)
        self.assertTrue(s.scrollable())
        s.handle_key(KeySym.END, None)
        self.assertEqual(s.visible_rows().stop, len(s.labels()))
        few = shops.Shop("Barkeeper", "Hi.", [shops.Deal("A room", {"coin": 5}, {"room key": 1})])
        few.cols, few.rows = 120, 60
        self.assertFalse(few.scrollable())
        self.assertFalse(few.tabbed)

    def test_selling_is_on_its_own_tab(self):
        s = self.shop()
        self.assertTrue(s.tabbed)
        self.assertFalse(any("Sell" in l for l in s.labels()))
        self.assertEqual(len(s.labels()), 31)                  # 30 to buy, and Leave
        s.handle_key(KeySym.TAB, None)
        self.assertEqual(s.tab, "sell")
        self.assertEqual(s.labels(), ["Sell your tin whistle (1): 2 coins each", "Leave"])
        self.assertIn("Sell (1)", "".join(s.tab_labels()))
        tab, x, w = s.tab_spans()[0]
        s.click(x, s.box()[1] + 1, None)
        self.assertEqual(s.tab, "buy")


if __name__ == "__main__":
    unittest.main()
