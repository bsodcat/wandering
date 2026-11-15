"""Horses: buying, saddling, riding faster, getting down, calling, and the map marker."""
import unittest

from game import horses, shop as shops
from game import tiles as T
from game.people import Actor

from tests.test_wild import engine_on, field


def horse_beside(e, saddled=False):
    a = Actor("horse", "horse", e.lx + 1, e.ly, work=[(e.lx + 1, e.ly)])
    a.saddled = saddled
    e.level.actors.append(a)
    return a


class HorseTests(unittest.TestCase):
    def test_saddling_a_pasture_horse_makes_it_yours_and_you_can_ride_it(self):
        e = engine_on(field())
        a = horse_beside(e)
        labels = [o.label for o in e.options_at(a.x, a.y)]
        self.assertTrue(any(lab.startswith("Saddle") for lab in labels), labels)
        self.assertIn("need a saddle", horses.saddle(e, a))
        e.player.inventory.add("saddle")
        horses.saddle(e, a)
        self.assertTrue(a.saddled and horses.is_yours(e, a))
        self.assertNotEqual(a.name, "horse")                         # it gets a name
        horses.mount(e, a)
        self.assertIs(e.mount, a)
        self.assertNotIn(a, e.level.actors)
        self.assertIn("Get down", " ".join(o.label for o in e.own_options()))

    def test_riding_is_faster_on_the_ground_and_across_the_land(self):
        e = engine_on(field())
        on_foot = e.step_minutes(T.GRASS, 1, 0)
        hours, _ = e.travel_time(e.player.x + 1, e.player.y, 1, 0)
        a = horse_beside(e, saddled=True)
        horses.mount(e, a)
        self.assertAlmostEqual(e.step_minutes(T.GRASS, 1, 0), on_foot * horses.RIDE_LOCAL)
        self.assertLess(e.travel_time(e.player.x + 1, e.player.y, 1, 0)[0], hours)

    def test_getting_down_leaves_the_horse_beside_you_and_doors_make_you(self):
        e = engine_on(field())
        a = horse_beside(e, saddled=True)
        horses.mount(e, a)
        horses.dismount(e)
        self.assertIsNone(e.mount)
        self.assertIn(a, e.level.actors)
        self.assertEqual(max(abs(a.x - e.lx), abs(a.y - e.ly)), 1)
        horses.mount(e, a)
        e.level.tiles[e.lx, e.ly - 1] = T.DOOR
        e.move_local(0, -1)
        self.assertIsNone(e.mount)                                  # left by the door

    def test_call_brings_a_horse_within_3_regions_and_not_further(self):
        e = engine_on(field())
        a = Actor("horse", "Bramble", 5, 5, work=[(5, 5)])
        a.saddled = True
        far = ("region", e.player.x + 3, e.player.y)
        e.horses.append([far, a])
        self.assertIn("on its way", horses.call(e))
        e.pass_time(3 * horses.HOURS_PER_REGION + 0.2)
        self.assertIn(a, e.level.actors)
        self.assertTrue(any("trots up" in m for m in e.messages))
        e.level.actors.remove(a)
        e.horses = [[("region", e.player.x + 4, e.player.y), a]]
        self.assertIn("none of your horses", horses.call(e))

    def test_the_stablehand_sells_horses_into_the_paddock_and_they_blink_on_the_map(self):
        from game.level import Place
        lv = field()
        lv.places.append(Place("pasture", "a paddock", [(10, 5), (11, 5), (12, 5)], "horse"))
        e = engine_on(lv)
        hand = Actor("stablehand", "Wat Groom", e.lx + 1, e.ly, work=[(e.lx + 1, e.ly)])
        e.player.inventory.add("coin", 100)
        shop = shops.for_actor(hand, e) or shops.Shop("x", "", [])
        self.assertTrue(any("horse" in d.label for d in shop.deals))
        shop.trade(0, e)
        self.assertEqual(len(e.horses), 1)
        self.assertIn((e.horses[0][1].x, e.horses[0][1].y), lv.places[0].tiles)
        self.assertEqual(horses.regions(e), [lv.region])
