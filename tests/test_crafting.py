"""Crafting, campfires, torches and lanterns, flint and sticks."""
import unittest

import numpy as np
from tcod.event import KeySym

from game import crafting, items, lights
from game import tiles as T
from game.climate import MINUTES_PER_HOUR

from tests.test_wild import engine_on, field


def recipe(name):
    return next(r for r in crafting.RECIPES if r.name == name)


class CraftingTests(unittest.TestCase):
    def test_k_opens_the_crafting_menu_dim_without_the_makings(self):
        e = engine_on(field())
        e.handle_key(KeySym.K)
        self.assertEqual(e.shop.title, "Crafting")
        self.assertTrue(all(not o.ok for o in e.shop.options[:len(crafting.RECIPES)]))
        self.assertIn("still need", crafting.craft(e, recipe("campfire")))

    def test_a_campfire_takes_logs_and_flint_lights_warms_and_burns_out(self):
        e = engine_on(field(), hour=23)
        bag = e.player.inventory
        bag.add("log", 2)
        bag.add("flint")
        text = crafting.craft(e, recipe("campfire"))
        self.assertIn("campfire catches", text)
        self.assertEqual((bag.count("log"), bag.count("flint")), (0, 0))
        (x, y), = e.level.campfires
        self.assertEqual(e.level.tiles[x, y], T.CAMPFIRE)
        from game.light import firelight
        self.assertGreater(firelight(e.level)[0][x, y], 0.5)
        self.assertTrue(crafting.near_fire(e.level, e.lx, e.ly))
        e.pass_time(crafting.CAMPFIRE_HOURS + 0.5)
        self.assertEqual(e.level.tiles[x, y], T.ASHES)
        self.assertFalse(e.level.campfires)

    def test_a_torch_is_cloth_a_stick_and_the_best_fuel_you_have(self):
        e = engine_on(field())
        bag = e.player.inventory
        for k in ("strip of cloth", "stick", "animal fat", "flask of oil"):
            bag.add(k)
        crafting.craft(e, recipe("torch"))
        self.assertEqual(bag.count("torch"), 1)
        self.assertEqual(bag.count("flask of oil"), 0)               # oil burns longest: used first
        self.assertEqual(bag.count("animal fat"), 1)
        self.assertEqual(e.player.torch_hours, [lights.TORCH_FUEL["flask of oil"]])

    def test_a_felled_tree_drops_sticks_and_flint_lies_about(self):
        lv = field()
        lv.tiles[31, 15] = T.TREE
        e = engine_on(lv)
        e.player.inventory.add("axe")
        e.move_local(1, 0)
        sticks = sum(pile.count("stick") for pile in lv.items.values())
        self.assertTrue(1 <= sticks <= 3)
        from game.engine import Engine
        real = Engine.new(1)
        real.enter_region()
        self.assertTrue(any("flint" in pile for pile in real.level.items.values()))


class LightTests(unittest.TestCase):
    def cave(self):
        lv = field(tile=T.CAVE_FLOOR)
        lv.underground = True
        return engine_on(lv)

    def test_bare_eyes_a_torch_and_a_lantern_see_3_6_and_9(self):
        e = self.cave()
        p = e.player
        self.assertEqual(e.sight_radius(), lights.BARE)
        p.inventory.add("torch")
        lights.light(p, "torch")
        self.assertEqual(e.sight_radius(), 6)
        p.inventory.add("lantern")
        p.inventory.add("flask of oil")
        lights.light(p, "lantern")
        self.assertEqual(e.sight_radius(), 9)
        self.assertEqual(p.inventory.count("torch"), 1)               # the torch went back in the bag

    def test_a_torch_burns_out_unless_you_carry_fuel_and_stays_between_2_and_16(self):
        e = self.cave()
        p = e.player
        p.inventory.add("torch")
        lights.light(p, "torch")
        self.assertEqual(p.light_hours, lights.BOUGHT_TORCH)
        e.pass_time(lights.BOUGHT_TORCH + 0.5)
        self.assertIsNone(p.light)
        self.assertTrue(any("gutters out" in m for m in e.messages))
        p.inventory.add("torch")
        p.inventory.add("animal fat", 20)
        lights.light(p, "torch")
        e.pass_time(30)                                               # refilled again and again
        self.assertEqual(p.light, "torch")
        self.assertLessEqual(p.light_hours, lights.MOST_HOURS)
        self.assertLess(p.inventory.count("animal fat"), 20)
        self.assertGreaterEqual(min(lights.TORCH_FUEL.values()), 2.0)

    def test_oil_lasts_longer_than_fat_and_the_lantern_keeps_its_fuel(self):
        self.assertGreater(lights.TORCH_FUEL["flask of oil"], lights.TORCH_FUEL["pitch"])
        self.assertGreater(lights.TORCH_FUEL["pitch"], lights.TORCH_FUEL["animal fat"])
        e = self.cave()
        p = e.player
        p.inventory.add("lantern")
        self.assertIn("dry", lights.light(p, "lantern"))
        p.inventory.add("flask of oil")
        lights.light(p, "lantern")
        self.assertEqual(p.light_hours, lights.LANTERN_FUEL["flask of oil"])
        e.pass_time(3)
        lights.put_out(p)
        self.assertAlmostEqual(p.lantern_hours, 7.0, places=3)
        self.assertEqual(p.inventory.count("lantern"), 1)
