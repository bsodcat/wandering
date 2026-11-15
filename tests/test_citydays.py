"""Livelier cities (households, the halls, routines, people talking), campfire fuel, ashes, lye
and soap, riding rules, stables, squeezing between rocks, and the light you carry."""
import random
import unittest

import numpy as np

from game import crafting, elevation, halls, horses, landmarks, mingling, routines, wild
from game import tiles as T
from game.climate import MINUTES_PER_DAY, MINUTES_PER_HOUR
from game.people import Actor, plan

from tests.test_city import city, parts
from tests.test_horses import horse_beside
from tests.test_places import level, world
from tests.test_wild import engine_on, field

PARTS = None


def city_parts():
    global PARTS
    if PARTS is None:
        PARTS = parts()
    return PARTS


class HouseholdTests(unittest.TestCase):
    def test_most_city_houses_are_lived_in(self):
        for k, lv in city_parts().items():
            houses = [b for b in lv.buildings if b.kind in ("house", "ruin")]
            empty = [b for b in houses if "junk" in b.name or b.kind == "ruin"]
            self.assertLess(len(empty) / len(houses), 0.3, k)

    def test_households_have_many_things_to_do_in_a_day(self):
        lv = city_parts()[(0, 0)]
        folk = [a for a in lv.actors if a.kind in routines.HOUSEHOLDS + ("weaver", "tailor", "potter")]
        self.assertTrue(folk)
        names = {"inn": "the inn", "town": lv.name, "day": 3, "weekday": "Tuesday"}
        for a in folk[:20]:
            doings = {plan(a, h + 0.25, names)[1] for h in range(24)}
            self.assertGreaterEqual(len(doings), 4, (a.kind, doings))

    def test_market_day_and_school_days(self):
        lv = next(lv for lv in city_parts().values() if any(b.kind == "school" for b in lv.buildings))
        kid = next(a for a in lv.actors if a.kind == "child" and a.routine)
        self.assertEqual(plan(kid, 9, {"weekday": "Monday", "inn": "", "town": ""})[1], "at their lessons")
        self.assertEqual(plan(kid, 9, {"weekday": "Saturday", "inn": "", "town": ""})[1], "playing tag")
        crafter = next(a for lv in city_parts().values() for a in lv.actors if a.kind == "cooper" and a.routine)
        self.assertEqual(plan(crafter, 14, {"weekday": "Saturday", "inn": "", "town": ""})[1], "selling wares in the square")

    def test_the_halls_are_spread_over_the_city_and_peopled(self):
        lvs = city_parts().values()
        built = {b.kind for lv in lvs for b in lv.buildings}
        for kind in ("bathhouse", "counting house", "orphanage", "healer", "adventurers' hall", "brewhouse",
                     "tannery", "mage tower", "school", "stable"):
            self.assertIn(kind, built)
        places = {p.kind for lv in lvs for p in lv.places}
        self.assertTrue({"graveyard", "training yard", "stable"} <= places)
        kinds = {a.kind for lv in lvs for a in lv.actors}
        for kind in ("bathkeeper", "moneylender", "gravedigger", "healer", "matron", "sellsword", "brewer", "tanner",
                     "mage", "apprentice", "schoolmaster", "master-at-arms", "recruit", "street sweeper", "town crier",
                     "groom"):
            self.assertIn(kind, kinds)

    def test_the_guards_horses_are_not_for_the_taking(self):
        lv = next(lv for lv in city_parts().values() if any(p.kind == "stable" for p in lv.places))
        horse = next(a for a in lv.actors if a.kind == "horse")
        self.assertEqual(horse.keeper, "the guards")
        e = engine_on(field())
        e.player.inventory.add("saddle")
        self.assertIn("guards", horses.saddle(e, horse))
        self.assertFalse(horse.saddled)

    def test_every_fort_has_a_stable(self):
        for f in [s for s in world().sites if s.kind == "fort"]:
            lv = level(("region", f.x, f.y))
            self.assertTrue(any(p.kind == "stable" for p in lv.places), f.name)
            self.assertGreaterEqual(sum(a.kind == "horse" for a in lv.actors), 3)


class MingleTests(unittest.TestCase):
    def pair(self, kinds=("townsperson", "townsperson")):
        e = engine_on(field(), hour=11)
        a = Actor(kinds[0], "Cora Brook", e.lx + 4, e.ly, work=[(e.lx + 4, e.ly)], home=[(e.lx + 4, e.ly)])
        b = Actor(kinds[1], "Hal Kemp", e.lx + 5, e.ly, work=[(e.lx + 5, e.ly)], home=[(e.lx + 5, e.ly)])
        a.doing = b.doing = "out and about"
        e.level.actors += [a, b]
        return e, a, b

    def test_two_people_side_by_side_stop_to_talk(self):
        e, a, b = self.pair()
        mingling.mingle(e.level, e, random.Random(1), 25)
        self.assertGreater(a.talk_until, e.minutes)
        self.assertIs(a.partner, b)
        self.assertIn("Hal", a.doing)
        self.assertIn("Cora", b.doing)

    def test_a_merchant_haggles(self):
        e, a, b = self.pair(("merchant", "townsperson"))
        doing_a, doing_b, line = mingling.pair_up(e.level, a, b, random.Random(2), {"town": "Town"})
        self.assertIn("haggling", doing_a)
        self.assertIn("haggles", line)

    def test_you_overhear_them_but_not_over_your_own_doings(self):
        e, a, b = self.pair()
        e.say("You do something.")
        mingling.mingle(e.level, e, random.Random(1), 25)
        self.assertEqual(e.messages[-1], "You do something.")


class HallTests(unittest.TestCase):
    def test_the_notice_board_and_the_bath(self):
        e = engine_on(field(), hour=11)
        self.assertTrue(halls.bump(e, T.NOTICE, 1, 1))
        self.assertIn("notice board", e.messages[-1])
        e.player.stamina = 20
        halls.bump(e, T.POOL, 1, 1)
        self.assertGreater(e.player.stamina, 40)


class CampfireTests(unittest.TestCase):
    def fire(self, hour=23):
        e = engine_on(field(), hour=hour)
        bag = e.player.inventory
        bag.add("log", 6)
        bag.add("flint")
        crafting.craft(e, next(r for r in crafting.RECIPES if r.name == "campfire"))
        (x, y), = e.level.campfires
        return e, x, y

    def test_feeding_a_fire_raises_it_a_stage_up_to_three(self):
        e, x, y = self.fire()
        self.assertEqual(crafting.stage(e.level, x, y, e.minutes), 2)
        before = crafting.fire_reach(e.level, x, y)
        self.assertIn("roars", crafting.feed(e, x, y, "log"))
        self.assertEqual(crafting.stage(e.level, x, y, e.minutes), 3)
        self.assertEqual(crafting.fire_reach(e.level, x, y), before + 2 * crafting.FIRE_STAGE_TILES)
        self.assertIn("as big", crafting.feed(e, x, y, "log"))
        labels = [o.label for o in e.options_at(x, y)]
        self.assertTrue(any(lab.startswith("Add a log") for lab in labels), labels)

    def test_a_fire_drops_a_stage_every_four_hours_then_ashes_for_lye_and_soap(self):
        e, x, y = self.fire()
        e.pass_time(crafting.FIRE_STAGE_HOURS + 0.2)
        self.assertEqual(crafting.stage(e.level, x, y, e.minutes), 1)
        e.pass_time(crafting.FIRE_STAGE_HOURS)
        self.assertEqual(e.level.tiles[x, y], T.ASHES)
        self.assertIn("Scoop up the ashes", [o.label for o in e.options_at(x, y)])
        crafting.scoop_ashes(e, x, y)
        bag = e.player.inventory
        self.assertEqual(bag.count("handful of ashes"), crafting.ASHES_GIVE)
        lye = next(r for r in crafting.RECIPES if r.name == "jar of lye")
        self.assertIn("water", crafting.craft(e, lye))                  # no water beside you
        e.level.tiles[e.lx + 1, e.ly + 1] = T.WELL
        crafting.craft(e, lye)
        self.assertEqual(bag.count("jar of lye"), 1)
        soap = next(r for r in crafting.RECIPES if r.name == "bar of soap")
        bag.add("animal fat")
        self.assertIn("fire", crafting.craft(e, soap))
        e.level.tiles[e.lx - 1, e.ly - 1] = T.HEARTH
        crafting.craft(e, soap)
        self.assertEqual(bag.count("bar of soap"), 1)


class RidingTests(unittest.TestCase):
    def riding(self):
        e = engine_on(field())
        a = horse_beside(e, saddled=True)
        horses.mount(e, a)
        self.assertIs(e.mount, a)
        return e

    def test_no_felling_mining_or_fires_from_the_saddle(self):
        e = self.riding()
        bag = e.player.inventory
        bag.add("axe")
        self.assertFalse(e.chop(e.lx + 1, e.ly))
        bag.add("log", 2)
        bag.add("flint")
        self.assertIn("horse", crafting.craft(e, next(r for r in crafting.RECIPES if r.name == "campfire")))
        self.assertFalse(e.level.campfires)
        bag.add("strip of cloth")
        bag.add("stick")
        bag.add("animal fat")
        crafting.craft(e, next(r for r in crafting.RECIPES if r.name == "torch"))   # into the bag: fine
        self.assertEqual(bag.count("torch"), 1)

    def test_a_horse_takes_steeper_banks_and_you_cant_get_down_stuck(self):
        self.assertTrue(horses.climb(4, False)[0])
        self.assertFalse(elevation.climb(4, False)[0])
        e = self.riding()
        e.level.elev[:] = 0
        e.level.elev[e.lx, e.ly] = 9                  # a pinnacle: on foot you'd be stuck up here
        self.assertIn("too steep", horses.dismount(e))
        self.assertIsNotNone(e.mount)
        e.level.elev[e.lx, e.ly] = 1
        horses.dismount(e)
        self.assertIsNone(e.mount)

    def test_a_blow_from_the_saddle_hits_harder(self):
        self.assertGreater(wild.MOUNTED_BLOW, 0)


class SqueezeTests(unittest.TestCase):
    def test_no_slipping_diagonally_between_two_corners_of_rock(self):
        t = np.full((5, 5), T.GRASS, np.uint8)
        t[2, 1] = t[1, 2] = T.ROCK
        self.assertTrue(elevation.squeeze(t, 1, 1, 1, 1))
        self.assertFalse(elevation.squeeze(t, 2, 2, 1, 1))
        self.assertTrue(elevation.squeezes(t, 1, 1)[1, 1])

    def test_nor_between_two_corners_of_the_mountains_on_the_world_map(self):
        e = engine_on(field())
        e.level = None
        w, p = e.world, e.player
        open_ = w.walkable
        w.walkable = lambda x, y: (x, y) not in {(p.x + 1, p.y), (p.x, p.y + 1)} and open_(x, y)
        try:
            before = (p.x, p.y)
            if open_(p.x + 1, p.y + 1):
                self.assertFalse(e.move(1, 1))
                self.assertEqual((p.x, p.y), before)
        finally:
            w.walkable = open_


class CarriedLightTests(unittest.TestCase):
    def test_a_torch_lights_warm_and_flickers(self):
        from game.light import carried
        dist = np.array([[1.0, 4.0, 30.0]])
        a = carried("torch", 6, dist, 1.0, 0.0)
        b = carried("torch", 6, dist, 1.0, 0.37)
        self.assertGreater(a[0, 0], a[0, 1])
        self.assertEqual(a[0, 2], 0)
        self.assertNotAlmostEqual(float(a[0, 0]), float(b[0, 0]), places=3)
        lantern = carried("lantern", 9, dist, 1.0, 0.0)
        self.assertGreater(lantern[0, 1], a[0, 1])


class ShopTests(unittest.TestCase):
    def trader(self, kind):
        from game import shop as shops
        e = engine_on(field(), hour=11)
        spot = [(e.lx + 1, e.ly)]
        a = Actor(kind, "Bryn Kemp", e.lx + 1, e.ly, home=spot, work=spot, evening=spot)
        e.level.actors.append(a)
        return e, shops.for_actor(a, e)

    def test_the_baker_and_the_butcher_buy_and_sell(self):
        from game import shop as shops
        e, shop = self.trader("baker")
        self.assertIsNotNone(shop)
        e.player.inventory.add("coin", 20)
        labels = [d.label for d in shop.deals]
        self.assertTrue(any("meat pie" in lab for lab in labels), labels)
        e, shop = self.trader("butcher")
        e.player.inventory.add("rabbit carcass")
        self.assertTrue(any("rabbit carcass" in d.label and d.sell for d in shops.butcher_deals(e)))

    def test_a_drink_at_the_inn(self):
        e, shop = self.trader("innkeeper")
        e.player.inventory.add("coin", 20)
        e.player.stamina = 30
        coins = e.player.inventory.count("coin")
        i = next(i for i, d in enumerate(shop.deals) if "ale" in d.label)
        text = shop.trade(i, e)
        self.assertIn("ale", text)
        self.assertGreater(e.player.stamina, 30)
        self.assertEqual(e.player.inventory.count("coin"), coins - 2)


class WaitTests(unittest.TestCase):
    def test_the_wait_menu_waits_as_long_as_you_like(self):
        from tcod.event import KeySym
        from game import waiting
        e = engine_on(field(), hour=11)
        e.handle_key(KeySym.R)
        self.assertEqual(e.shop.title, "Wait")
        menu = e.shop
        menu.cursor = len(menu.options) - 1
        menu.handle_key(KeySym.RIGHT, e)
        self.assertEqual(menu.custom, waiting.CUSTOM_START + 15)
        start = e.minutes
        menu.handle_key(KeySym.RETURN, e)
        self.assertAlmostEqual(e.minutes - start, waiting.CUSTOM_START + 15, delta=1)
        self.assertAlmostEqual(waiting.until(e, 18) / 60 % 24, (18 - (e.minutes / 60) % 24) % 24, delta=0.05)


class LogColourTests(unittest.TestCase):
    def test_nouns_and_numbers_are_picked_out(self):
        from game import logcolour
        text = 'You pay 4 coins for a loaf of bread. The wolf bites (3). Cora: "Hello!"'
        got = {text[a:b]: c for a, b, c in logcolour.spans(text)}
        self.assertEqual(got["4 coins"], logcolour.NUMBER)
        self.assertEqual(got["loaf of bread"], logcolour.THING)
        self.assertEqual(got["wolf"], logcolour.CREATURE)
        self.assertEqual(got["Cora"], logcolour.NAME)
        self.assertEqual(got['"Hello!"'], logcolour.SPEECH)


if __name__ == "__main__":
    unittest.main()
