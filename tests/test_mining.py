"""Mining, the ore table, deeper caves, chasms, fissures, ravines and the rope grapple."""
import random
import unittest

import numpy as np

from game import mining, ravines, structures
from game import tiles as T

from tests.test_places import level, world
from tests.test_wild import engine_on, field


class MiningTests(unittest.TestCase):
    def test_the_ore_table_is_steady_and_deeper_rock_holds_richer_things(self):
        w = world()
        self.assertEqual(mining.ore_table(w, 5, 5, 0), mining.ore_table(w, 5, 5, 0))
        self.assertNotIn("gold nugget", mining.ore_table(w, 5, 5, 0))
        self.assertIn("gold nugget", mining.ore_table(w, 5, 5, 5))
        self.assertIn("flint", mining.ore_table(w, 5, 5, 0))

    def test_a_pickaxe_breaks_boulders_and_veins_and_their_ore_goes_in_your_bag(self):
        lv = field()
        lv.tiles[31, 15] = T.BOULDER
        lv.tiles[29, 15] = T.ORE_VEIN
        lv.ore[(29, 15)] = "iron ore"
        e = engine_on(lv)
        self.assertFalse(e.move_local(1, 0))                        # no pickaxe: in the way
        self.assertEqual(lv.tiles[31, 15], T.BOULDER)
        e.player.inventory.add("pickaxe")
        e.move_local(1, 0)
        self.assertEqual(lv.tiles[31, 15], T.RUBBLE)
        e.move_local(-1, 0)
        self.assertEqual(lv.tiles[29, 15], T.RUBBLE)
        self.assertEqual(e.player.inventory.count("iron ore"), 1)

    def test_caves_go_3_to_5_levels_down_with_veins_and_the_stairs_always_joined(self):
        from game.localgen import make_level
        w = world()
        caves = [s for s in w.sites if s.kind == "cave"][:4]
        for s in caves:
            depth = structures.cave_depth(s.name)
            self.assertTrue(3 <= depth <= 5)
            for n in range(1, depth + 1):
                lv = make_level(w, ("cave", s.x, s.y, n))
                up = next(p for p, k in lv.exits.items() if lv.tiles[p] == T.STAIRS_UP)
                down = [p for p, k in lv.exits.items() if lv.tiles[p] == T.STAIRS_DOWN]
                joined = structures.largest_area(T.WALK[lv.tiles])
                self.assertTrue(joined[up], (s.name, n))
                for d in down:
                    self.assertTrue(joined[d], (s.name, n))
                if n == depth:
                    self.assertFalse((lv.tiles == T.CHASM).any())   # nothing below the bottom
            self.assertTrue(any((make_level(w, ("cave", s.x, s.y, n)).tiles == T.ORE_VEIN).any()
                                for n in range(1, depth + 1)))


class RavineTests(unittest.TestCase):
    def fissure_field(self):
        lv = field()
        lv.tiles[31, 10:20] = T.FISSURE
        return engine_on(lv)

    def test_the_first_step_warns_the_second_falls_into_the_ravine(self):
        e = self.fissure_field()
        self.assertFalse(e.move_local(1, 0))
        self.assertIn("edge", e.messages[-1])
        self.assertEqual(e.level.key[0], "region")
        e.move_local(1, 0)
        self.assertEqual(e.level.key[0], "ravine")
        self.assertLess(e.player.health, 100)
        self.assertEqual(e.route(31, 15), [])                         # (and walks never go there)

    def test_the_grapple_needs_daylight_from_above(self):
        e = self.fissure_field()
        e.move_local(1, 0)
        e.move_local(1, 0)
        ravine = e.level
        self.assertIn("need a rope grapple", ravines.climb_out(e))
        e.player.inventory.add("rope grapple")
        e.now = e.now.__class__(**{**e.now.__dict__, "light": 0.0})
        self.assertIn("too dark", ravines.climb_out(e))
        e.player.light, e.player.light_hours = "torch", 5.0       # your own torch doesn't help
        self.assertIn("too dark", ravines.climb_out(e))
        e.now = e.now.__class__(**{**e.now.__dict__, "light": 0.9})
        for _ in range(10):                                         # (it may slip a time or two)
            if e.level is not ravine:
                break
            ravines.climb_out(e)
        self.assertEqual(e.level.key[0], "region")
        self.assertEqual((e.lx, e.ly), (30, 15))

    def test_fissures_open_in_some_hill_country_never_in_settlements(self):
        w = world()
        hilly = [(x, y) for x in range(w.width) for y in range(w.height)
                 if int(w.biome[x, y]) in ravines.FISSURE_BIOMES and (x, y) not in w.site_at]
        cracked = [c for c in hilly if ravines.has_fissure(w, *c, None)]
        self.assertTrue(0 < len(cracked) < len(hilly) * 0.25)
        self.assertFalse(any(ravines.has_fissure(w, s.x, s.y, s) for s in w.sites))
        lv = level(("region", *cracked[0]))
        self.assertTrue((lv.tiles == T.FISSURE).any())
