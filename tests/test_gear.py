"""Equipment: the slots and what each piece does, the equipment menu, and climbing rock."""
import random
import unittest

import numpy as np
from tcod.event import KeySym

from game import combat, elevation, gear, items, shop as shops
from game import tiles as T
from game.climate import Conditions
from game.player import Player, expose, insulation

from tests.test_wild import engine_on, field


def rain(air=12.0):
    return Conditions(air=air, cloud=1.0, precip=0.8, wind=5.0, fog=0.0, light=0.6, kind="Rain")


def kit(p, *kinds):
    for k in kinds:
        p.inventory.add(k)
        if k in gear.GEAR:
            gear.wear(p, k)


class NeverSlip(random.Random):
    def random(self):
        return 0.99


class AlwaysSlip(random.Random):
    def random(self):
        return 0.0


class GearTests(unittest.TestCase):
    def test_every_piece_is_an_item_with_a_slot(self):
        for kind, g in gear.GEAR.items():
            self.assertIn(kind, items.KINDS)
            self.assertIn(g.slot, gear.SLOTS)
            self.assertTrue(gear.describe(kind))

    def test_the_shopkeeper_sells_all_of_it(self):
        for kind in list(gear.GEAR) + list(combat.WEAPONS):
            if kind not in ("rusty dagger", "crude knife", "shovel", "axe"):
                self.assertIn(kind, combat.WARES)

    def test_one_piece_to_a_place(self):
        p = Player(0, 0)
        kit(p, "wool cloak", "oilskin cloak")
        self.assertEqual(gear.worn(p), {"cloak": "oilskin cloak"})

    def test_what_you_drop_comes_off(self):
        p = Player(0, 0)
        kit(p, "fur hat")
        p.inventory.take("fur hat")
        self.assertEqual(gear.worn(p), {})

    def test_an_old_save_shield_moves_to_its_new_place(self):
        p = Player(0, 0)
        p.inventory.add("wooden shield")
        p.wearing["arm"] = "wooden shield"
        self.assertEqual(gear.worn(p), {"shield": "wooden shield"})
        self.assertAlmostEqual(gear.block(p), 1 / 6)

    def test_armour_adds_up(self):
        p = Player(0, 0)
        kit(p, "mail shirt", "iron helm", "iron-bound shield")
        self.assertEqual(combat.protection(p), 5)

    def test_warm_things_keep_you_warm(self):
        p = Player(0, 0)
        bare = insulation(p)
        kit(p, "fur coat", "fur hat", "fur-lined boots")
        self.assertEqual(insulation(p), bare + 14)

    def test_a_cloak_keeps_the_rain_off(self):
        bare, cloaked = Player(0, 0), Player(0, 0)
        kit(cloaked, "oilskin cloak")
        expose(bare, 1, rain(), shelter=0)
        expose(cloaked, 1, rain(), shelter=0)
        self.assertLess(cloaked.wet, bare.wet * 0.5)

    def test_boots_are_quicker_on_rough_ground(self):
        e = engine_on(field(tile=T.SCREE))
        before = e.step_minutes(T.SCREE, 1, 0)
        kit(e.player, "hobnailed boots")
        self.assertAlmostEqual(e.step_minutes(T.SCREE, 1, 0), before * 0.8, places=4)
        self.assertEqual(e.step_minutes(T.STREET, 1, 0), e.step_minutes(T.STREET, 1, 0))

    def test_heavy_gear_tires_you(self):
        light, heavy = engine_on(field()), engine_on(field())
        kit(heavy.player, "mail shirt", "iron-bound shield")
        for e in (light, heavy):
            for _ in range(20):
                e.move_local(1, 0)
                e.move_local(-1, 0)
        self.assertLess(heavy.player.stamina, light.player.stamina)

    def test_a_shield_blocks_more_often_with_iron(self):
        rng = random.Random(3)
        wood, iron = Player(0, 0), Player(0, 0)
        kit(wood, "wooden shield")
        kit(iron, "iron-bound shield")
        def blocks(p):
            return sum(combat.blow_at_you(p, 1, 3, 1.0, rng)[1] == "block" for _ in range(3000))
        self.assertGreater(blocks(iron), blocks(wood))


class ClimbingTests(unittest.TestCase):
    def rocky(self):
        level = field()
        level.tiles[31, 15] = T.ROCK
        level.tiles[32, 15] = T.ROCK
        level.tiles[30, 16] = T.BOULDER
        e = engine_on(level)
        e.rng = NeverSlip()
        return e

    def test_rock_is_in_the_way_without_gear(self):
        e = self.rocky()
        self.assertFalse(e.move_local(1, 0))
        self.assertIn("climbing gear", e.messages[-1])
        self.assertEqual((e.lx, e.ly), (30, 15))

    def test_climbing_gear_gets_you_up(self):
        e = self.rocky()
        kit(e.player, "climbing gear")
        before = e.minutes
        self.assertTrue(e.move_local(1, 0))
        self.assertEqual((e.lx, e.ly), (31, 15))
        self.assertEqual(e.on_rock, T.ROCK)
        self.assertTrue(any("climb up onto the rock" in m for m in e.messages))
        self.assertGreater(e.minutes - before, 2.5)            # slow going
        self.assertTrue(e.move_local(1, 0))                     # along the top
        self.assertTrue(e.move_local(1, 0))                     # and down the far side
        self.assertIsNone(e.on_rock)
        self.assertTrue(any("climb down" in m for m in e.messages))

    def test_boulders_too(self):
        e = self.rocky()
        kit(e.player, "climbing gear")
        self.assertTrue(e.move_local(0, 1))
        self.assertEqual(e.on_rock, T.BOULDER)

    def test_too_tired_to_climb(self):
        e = self.rocky()
        kit(e.player, "climbing gear")
        e.player.stamina = 5
        self.assertFalse(e.move_local(1, 0))
        self.assertIn("too worn out", e.messages[-1])

    def test_a_slip_hurts_and_leaves_you_below(self):
        e = self.rocky()
        kit(e.player, "climbing gear")
        e.rng = AlwaysSlip()
        self.assertFalse(e.move_local(1, 0))
        self.assertEqual((e.lx, e.ly), (30, 15))
        self.assertLess(e.player.health, 100)
        self.assertTrue(any("lose your hold" in m for m in e.messages))

    def test_grip_and_weather_change_the_odds(self):
        p = Player(0, 0)
        kit(p, "climbing gear")
        dry = gear.slip_chance(p, False, False)
        self.assertGreater(gear.slip_chance(p, True, True), dry)
        kit(p, "leather gloves", "hobnailed boots")
        self.assertLess(gear.slip_chance(p, False, False), dry)
        mitts = Player(0, 0)
        kit(mitts, "climbing gear", "fur mittens")
        self.assertGreater(gear.slip_chance(mitts, False, False), dry)

    def test_a_rope_climbs_what_walking_cannot(self):
        self.assertFalse(elevation.climb(3, False)[0])
        self.assertTrue(elevation.climb(3, False, roped=True)[0])
        self.assertTrue(elevation.climb(-4, False, roped=True)[0])
        self.assertFalse(elevation.climb(5, False, roped=True)[0])
        level = field()
        level.elev[31, 15] = 3
        e = engine_on(level)
        e.rng = NeverSlip()
        self.assertFalse(e.move_local(1, 0))
        kit(e.player, "climbing gear")
        self.assertTrue(e.move_local(1, 0))

    def test_you_see_further_from_on_top(self):
        level = field(80, 40)
        level.elev[:, :] = 0
        level.elev[33:35, :] = 2                   # a ridge you can't see past
        level.tiles[31, 20] = T.ROCK
        e = engine_on(level, at=(30, 20))
        e.rng = NeverSlip()
        kit(e.player, "climbing gear")
        below = e.local_visible[60, 20]
        e.move_local(1, 0)
        self.assertFalse(below)
        self.assertTrue(e.local_visible[60, 20])


class EquipmentMenuTests(unittest.TestCase):
    def test_q_opens_it_with_a_row_a_place(self):
        e = engine_on(field())
        e.handle_key(KeySym.Q)
        self.assertIsInstance(e.shop, shops.Equipment)
        self.assertEqual(len(e.shop.options), 1 + len(gear.SLOTS))
        self.assertEqual(len(e.shop.greeting_lines()), 3)

    def test_putting_something_on_from_the_menu(self):
        e = engine_on(field())
        e.player.inventory.add("climbing gear")
        e.player.inventory.add("short sword")
        e.handle_key(KeySym.Q)
        e.shop.cursor = 1 + gear.SLOTS.index("harness")
        e.handle_key(KeySym.RETURN)
        self.assertIsInstance(e.shop, shops.SlotPicker)
        self.assertIn("climbing gear", e.shop.labels()[0])
        e.handle_key(KeySym.RETURN)
        self.assertIsInstance(e.shop, shops.Equipment)     # back to the menu
        self.assertTrue(gear.can_climb(e.player))
        self.assertIn("Climbing yes", e.shop.greeting_lines()[2])
        e.shop.cursor = 0                                  # the weapon hand
        e.handle_key(KeySym.RETURN)
        e.handle_key(KeySym.RETURN)
        self.assertEqual(e.player.wielding, "short sword")
        e.handle_key(KeySym.ESCAPE)
        self.assertIsNone(e.shop)

    def test_esc_on_a_place_goes_back(self):
        e = engine_on(field())
        e.handle_key(KeySym.Q)
        e.shop.cursor = 2
        e.handle_key(KeySym.RETURN)
        self.assertIsInstance(e.shop, shops.SlotPicker)
        self.assertTrue(e.shop.dim(0, e))                  # nothing to put there
        e.handle_key(KeySym.ESCAPE)
        self.assertIsInstance(e.shop, shops.Equipment)
        self.assertEqual(e.shop.cursor, 2)

    def test_pairs_read_right(self):
        self.assertEqual(items.amount("leather gloves", 1), "a pair of leather gloves")
        self.assertEqual(items.amount("climbing gear", 1), "a set of climbing gear")


if __name__ == "__main__":
    unittest.main()
