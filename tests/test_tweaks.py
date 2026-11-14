"""World settings, volcanoes, the year-by-year time skip and the World settings bar."""
import unittest

import numpy as np
import tcod
from tcod.event import KeySym

from game import biomes as B
from game import eras
from game import localgen
from game import tiles as T
from game import tweaks as TW
from game.engine import Engine
from game.options import Menu
from game.passage import Passage
from game.title import SIDE_ROWS, Title, describe_region, draw_title, side_rows
from game.worldgen import generate

DEFAULT = generate(5)


def world(**steps):
    tw = TW.DEFAULT
    for name, by in steps.items():
        tw = tw.stepped(name.capitalize(), by)
    return generate(5, tweaks=tw)


class SettingsTests(unittest.TestCase):
    def test_steps_stop_at_the_ends_and_say_what_changed(self):
        tw = TW.DEFAULT.stepped("Land", 10)
        self.assertEqual(tw.step_name("Land"), "Mostly land")
        self.assertEqual(tw.changed(), ["Land"])
        self.assertTrue(TW.DEFAULT.is_default)
        self.assertEqual(hash(tw), hash(TW.DEFAULT.stepped("Land", 2)))

    def test_each_setting_changes_the_world(self):
        d = DEFAULT
        self.assertGreater((world(land=2).elevation > 0).sum(), (d.elevation > 0).sum())
        self.assertGreater((world(islands=2).elevation > 0).sum(), (d.elevation > 0).sum())
        self.assertLess((world(islands=-2).elevation > 0).sum(), (d.elevation > 0).sum())
        self.assertLess(world(mountains=-2).elevation.max(), d.elevation.max())
        self.assertGreater(world(temperature=2).temperature.mean(), d.temperature.mean() + 5)
        barren = world(vegetation=-2)
        forest = [B.FOREST, B.JUNGLE, B.TAIGA]
        self.assertLess(np.isin(barren.biome, forest).sum(), np.isin(d.biome, forest).sum())
        self.assertEqual((world(lakes=-2).biome == B.LAKE).sum(), 0)
        self.assertGreater(world(aquifers=2).spring.sum(), d.spring.sum())
        self.assertEqual(world(aquifers=-2).spring.sum(), 0)
        crowded = world(population=2)
        self.assertGreater(sum(s.kind == "town" for s in crowded.sites), sum(s.kind == "town" for s in d.sites))

    def test_same_settings_same_world(self):
        a, b = world(volcanoes=2, eruptions=2), world(volcanoes=2, eruptions=2)
        self.assertTrue(np.array_equal(a.biome, b.biome))


class VolcanoTests(unittest.TestCase):
    def test_volcanoes_and_their_lava(self):
        self.assertEqual(world(volcanoes=-1).volcanoes, [])
        w = world(volcanoes=2, eruptions=2)               # Many, Violent
        self.assertEqual(len(w.volcanoes), 10)
        self.assertTrue((w.biome == B.VOLCANO).any())
        self.assertTrue((w.biome == B.LAVA_FIELD).any())
        self.assertGreater(w.ash.max(), 0.5)
        self.assertTrue(any(v.at_sea for v in w.volcanoes))     # hotspot islands
        quiet = world(volcanoes=2, eruptions=-1)               # Extinct: no lava, no fresh ash
        self.assertFalse((quiet.biome == B.LAVA_FIELD).any())
        self.assertEqual(quiet.ash.max(), 0)

    def test_a_live_crater_holds_lava(self):
        w = world(volcanoes=2, eruptions=1)                    # Active
        v = next(v for v in w.volcanoes if w.biome[v.x, v.y] == B.VOLCANO)
        level = localgen.generate_region(w, v.x, v.y)
        self.assertTrue((level.tiles == T.LAVA).any())
        self.assertTrue((level.tiles == T.BASALT).any())

    def test_region_info(self):
        w = world(volcanoes=2, eruptions=1)
        v = w.volcanoes[0]
        lines = describe_region(w, v.x, v.y)
        self.assertIn(v.name, lines[0])
        land = np.argwhere(w.biome == B.FOREST)[0]
        self.assertTrue(any("woods" in line for line in describe_region(w, *land)))


class GroundwaterTests(unittest.TestCase):
    def test_a_hole_over_full_groundwater_can_fill_with_water(self):
        e = Engine.new(5, generate(5))
        e.enter_region()
        e.player.inventory.add("shovel")
        e.world.aquifer = np.ones_like(e.world.aquifer)
        filled = 0
        for _ in range(40):
            open_ground = np.argwhere(T.DIGGABLE[e.level.tiles] & T.WALK[e.level.tiles])
            e.lx, e.ly = (int(c) for c in open_ground[len(open_ground) // 2])
            e.dig()
            filled += e.level.tiles[e.lx, e.ly] == T.WATER
        self.assertGreater(filled, 0)


class PassageTests(unittest.TestCase):
    def test_counts_a_year_at_a_time_then_stops_where_told(self):
        e = Engine.new(5, DEFAULT)
        p = Passage(e.world, 1000, "Wetter", 1)
        t, base = 0.0, p._last
        seen = []
        for _ in range(10):
            t += 1 / 30
            p.tick(base + t)
            seen.append(p.elapsed)
        self.assertLessEqual(max(b - a for a, b in zip(seen, seen[1:])), 1)     # one year a frame at first
        for _ in range(60):
            t += 0.1
            p.tick(base + t)
        self.assertTrue(p.running)
        p.stop()
        at = p.stopped_at
        self.assertGreater(at, 10)
        p.wait(60)
        self.assertTrue(p.done)
        self.assertEqual(p.final.history, ((at, "Wetter"),))
        e.time_skip(at, "Wetter", p.final)
        self.assertEqual(e.world.years, at)

    def test_a_short_skip_keeps_most_towns(self):
        e = Engine.new(5, DEFAULT)
        old = {s.name for s in e.world.sites if s.kind == "town"}
        e.time_skip(50, "Steady")
        now = {s.name for s in e.world.sites if s.kind == "town"}
        self.assertGreaterEqual(len(old & now), len(old) - 3)
        e.time_skip(200_000, "Steady")
        self.assertFalse(old & {s.name for s in e.world.sites if s.kind == "town"})

    def test_skips_keep_the_settings(self):
        tw = TW.DEFAULT.stepped("Volcanoes", 1)
        e = Engine.new(5, generate(5, tweaks=tw))
        e.time_skip(100, "Steady")
        self.assertEqual(e.world.tweaks, tw)


class SideBarTests(unittest.TestCase):
    def test_tab_and_arrows_change_settings(self):
        t = Title(Menu())
        t.show("create")
        t.handle_key(KeySym.TAB)
        self.assertTrue(t.side)
        t.handle_key(KeySym.RIGHT)                           # Land: More
        self.assertEqual(t.tweaks.step_name("Land"), "More")
        t.side_cursor = SIDE_ROWS.index("Defaults")
        t.handle_key(KeySym.RETURN)
        self.assertTrue(t.tweaks.is_default)
        t.handle_key(KeySym.ESCAPE)                          # Esc leaves the bar, not the screen
        self.assertFalse(t.side)
        self.assertEqual(t.screen, "create")

    def test_drawn_and_clickable(self):
        t = Title(Menu())
        t.show("create")
        t.seed_text = "5"
        console = tcod.console.Console(120, 45, order="F")
        draw_title(console, t, 0.0)
        text = "\n".join("".join(chr(c) for c in console.rgb["ch"][:, y]) for y in range(45))
        for name in SIDE_ROWS[:-1]:
            self.assertIn(name, text)
        self.assertIn("World settings", text)
        y, x0, x1 = side_rows(t)[SIDE_ROWS.index("Volcanoes")]
        t.click(x1 - 2, y)                                   # right of the value: a step on
        self.assertEqual(t.tweaks.step_name("Volcanoes"), "Some")
        t.click(x0 + 1, y)                                   # the left side: a step back
        self.assertEqual(t.tweaks.step_name("Volcanoes"), "Few")
        t.side = False
        t.cursor = t.items().index("Begin")
        action = t.handle_key(KeySym.RETURN)
        self.assertEqual(action[2].tweaks, t.tweaks)


class SpawnTests(unittest.TestCase):
    def test_click_the_map_to_start_there(self):
        from game.title import preview_rect
        t = Title(Menu())
        t.show("create")
        t.seed_text = "5"
        console = tcod.console.Console(120, 45, order="F")
        draw_title(console, t, 0.0)
        x, y, pw, ph = preview_rect(120, 45)
        t.click(x + pw // 2, y + ph // 2)
        spot = t.spawn
        self.assertIsNotNone(spot)
        world = t.world(5, t.history, t.tweaks)
        self.assertTrue(world.walkable(*spot))
        t.hover(x + pw // 3, y + ph // 3)
        draw_title(console, t, 0.0)
        text = "\n".join("".join(chr(c) for c in console.rgb["ch"][:, r]) for r in range(45))
        self.assertIn("Region", text)
        self.assertIn("X", text)
        t.cursor = t.items().index("Begin")
        action = t.handle_key(KeySym.RETURN)
        e = Engine.new(action[1], action[2], action[3])
        self.assertEqual((e.player.x, e.player.y), spot)
        t.click(x + pw // 2, y + ph // 2)                    # again: no longer picked
        self.assertIsNone(t.spawn)


if __name__ == "__main__":
    unittest.main()
