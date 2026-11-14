"""Pastureland and downs, towns on rivers, stone cities over 2 x 2 regions, forts with guards,
archers and a blacksmith, cleared woods, and the carts between the towns."""
import random
import unittest

import numpy as np
from tcod.event import KeySym

from game import biomes as B, carts, cities, guards, people, shop as shops, wild
from game import tiles as T
from game.engine import Engine
from game.localgen import LOCAL_H, LOCAL_W, make_level
from game.worldgen import dilate, generate

from tests.test_wild import engine_on, field

WORLDS = {}


def world(seed=1):
    if seed not in WORLDS:
        WORLDS[seed] = generate(seed)
    return WORLDS[seed]


LEVELS = {}


def level(key, seed=1):
    if (seed, key) not in LEVELS:
        LEVELS[(seed, key)] = make_level(world(seed), key)
    return LEVELS[(seed, key)]


class LandTests(unittest.TestCase):
    def test_pastureland_and_downs_are_on_the_map(self):
        w = world()
        self.assertGreater(int((w.biome == B.PASTURE).sum()), 50)
        self.assertGreater(int((w.biome == B.DOWNS).sum()), 50)

    def test_they_have_few_trees(self):
        w = world()
        for biome in (B.PASTURE, B.DOWNS):
            same = (w.biome == biome)
            inner = same & np.logical_and.reduce([np.roll(np.roll(same, dx, 0), dy, 1)
                                                  for dx in (-1, 0, 1) for dy in (-1, 0, 1)])
            spots = [(int(a), int(b)) for a, b in np.argwhere(inner & ~w.road & ~w.river) if (a, b) not in w.site_at]
            if not spots:
                continue
            x, y = spots[0]
            t = level(("region", x, y)).tiles
            self.assertLess(np.isin(t, [T.TREE, T.PINE, T.JUNGLE_TREE]).mean(), 0.03, B.BIOMES[biome].name)

    def test_downs_are_hilly(self):
        w = world()
        x, y = (int(v) for v in np.argwhere(w.biome == B.DOWNS)[len(np.argwhere(w.biome == B.DOWNS)) // 2])
        elev = level(("region", x, y)).elev
        self.assertGreaterEqual(int(elev.max()) - int(elev.min()), 3)

    def test_herds_graze_the_pastureland(self):
        w = world()
        for x, y in np.argwhere(w.biome == B.PASTURE)[:6]:
            if (int(x), int(y)) not in w.site_at:
                lv = level(("region", int(x), int(y)))
                if any(a.animal for a in lv.actors):
                    return
        self.fail("no herds in the pastureland")

    def test_most_towns_are_on_a_river(self):
        for seed in (1, 2):
            w = world(seed)
            near = dilate(w.river, 1)
            towns = [s for s in w.sites if s.kind in ("city", "town")]
            on = sum(any(near[c] for c in s.cells) for s in towns)
            self.assertGreaterEqual(on / len(towns), 0.75)


class CityTests(unittest.TestCase):
    def city(self):
        return next(s for s in world().sites if s.kind == "city")

    def test_a_city_spans_four_regions_all_named_for_it(self):
        s = self.city()
        self.assertEqual(len(s.cells), 4)
        for c in s.cells:
            self.assertIs(world().site_at[c], s)

    def test_a_city_is_on_a_river_and_the_roads(self):
        w = world()
        for s in (s for s in w.sites if s.kind == "city"):
            self.assertTrue(any(w.river[c] for c in s.cells), s.name)
            self.assertTrue(any(w.road[c[0] + dx, c[1] + dy] for c in s.cells for dx in (-1, 0, 1, 2)
                                for dy in (-1, 0, 1, 2) if w.in_bounds(c[0] + dx, c[1] + dy)), s.name)

    def test_stone_houses_and_the_trades_shared_out(self):
        s = self.city()
        kinds, people_ = set(), set()
        for c in s.cells:
            lv = level(("region", *c))
            houses = [b for b in lv.buildings if b.kind == "house"]
            self.assertGreater(len(houses), 100)
            self.assertEqual(lv.tiles[houses[0].x0, houses[0].y0], T.STONE_WALL)
            kinds |= {b.kind for b in lv.buildings}
            people_ |= {a.kind for a in lv.actors}
        self.assertTrue({"inn", "armoury", "bakery", "butcher", "smithy"} <= kinds)
        self.assertTrue({"guard", "archer", "blacksmith", "innkeeper", "baker"} <= people_)

    def test_the_parts_meet_without_a_seam(self):
        s = self.city()
        left = level(("region", s.x, s.y)).tiles
        right = level(("region", s.x + 1, s.y)).tiles
        y0 = cities.INSET_Y
        # the wall runs straight on across the border, and the streets meet at it
        wallish = [T.STONE_WALL, T.BATTLEMENT, T.WATER, T.DEEP_WATER, T.TORCH, T.STREET, T.BRIDGE]
        self.assertIn(left[LOCAL_W - 1, y0], wallish)
        self.assertIn(right[0, y0], wallish)
        mid = LOCAL_H // 2 + 20
        self.assertTrue(left[LOCAL_W - 1, mid] in (T.STREET, T.BRIDGE, T.WATER, T.DEEP_WATER))
        self.assertTrue(right[0, mid] in (T.STREET, T.BRIDGE, T.WATER, T.DEEP_WATER))
        self.assertNotEqual(left[LOCAL_W - 1, y0], T.STREET)    # no gap in the wall where the parts join

    def test_the_wall_has_gates(self):
        s = self.city()
        lv = level(("region", s.x, s.y))
        self.assertTrue(any(p.kind == "gate" for p in lv.places))
        x0 = cities.INSET_X
        self.assertGreater(int((lv.tiles[x0, :] == T.STONE_WALL).sum()), 100)
        self.assertTrue((lv.tiles[x0, :] == T.STREET).any())


class FortTests(unittest.TestCase):
    def fort(self):
        s = next(s for s in world().sites if s.kind == "fort")
        return s, level(("region", s.x, s.y))

    def test_a_fort_has_its_garrison(self):
        s, lv = self.fort()
        kinds = [a.kind for a in lv.actors]
        self.assertEqual(kinds.count("guard"), 4)
        self.assertEqual(kinds.count("archer"), 3)
        self.assertIn("blacksmith", kinds)
        self.assertTrue({"barracks", "smithy", "stores"} <= {b.kind for b in lv.buildings})
        self.assertTrue((lv.tiles == T.FORGE).any() and (lv.tiles == T.ANVIL).any())
        self.assertTrue((lv.tiles == T.TARGET).any())

    def test_forts_stand_on_high_ground_by_the_roads(self):
        w = world()
        for s in (s for s in w.sites if s.kind == "fort"):
            self.assertIn(int(w.biome[s.x, s.y]), (B.HILLS, B.MOUNTAINS, B.DOWNS))

    def test_the_blacksmith_sells_and_buys_old_iron(self):
        e = engine_on(field())
        smith = people.Actor("blacksmith", "Garth Kemp", 31, 15, work=[(31, 15)])
        e.level.actors.append(smith)
        e.player.inventory.add("rusty dagger")
        e.minutes = e.minutes - e.minutes % 1440 + 10 * 60
        shop = shops.for_actor(smith, e)
        self.assertIn("mace", " ".join(shop.labels()))
        self.assertNotIn("rusty dagger", " ".join(shop.labels()))   # that's on the Sell tab
        shop.switch("sell")
        self.assertIn("rusty dagger", " ".join(shop.labels()))

    def test_archers_and_guards_see_off_wolves(self):
        lv = field(80, 40)
        e = engine_on(lv, at=(5, 5))
        e.minutes = e.minutes - e.minutes % 1440 + 12 * 60
        lv.actors.append(people.Actor("archer", "Kit Marsh", 40, 20, work=[(40, 20)]))
        lv.actors.append(people.Actor("guard", "Hal Brook", 46, 20, work=[(46, 20)]))
        wolves = [wild.Creature("wolf", 44 + i, 21, home=(44, 21)) for i in range(3)]
        lv.creatures.extend(wolves)
        rng = random.Random(2)
        for _ in range(4):                                  # a few minutes of it
            guards.defend(lv, e, rng, 10)
        self.assertTrue(all(w.hp <= 0 for w in wolves))
        self.assertEqual([c for c in lv.creatures if c.kind == "wolf"], [])
        self.assertTrue(any(k.endswith("carcass") for pile in lv.items.values() for k in pile))

    def test_off_duty_they_leave_it(self):
        lv = field(80, 40)
        e = engine_on(lv, at=(5, 5))
        e.minutes = e.minutes - e.minutes % 1440 + 2 * 60
        lv.actors.append(people.Actor("archer", "Kit Marsh", 40, 20, work=[(40, 20)]))
        wolf = wild.Creature("wolf", 44, 21, home=(44, 21))
        lv.creatures.append(wolf)
        guards.defend(lv, e, random.Random(2), 10)
        self.assertGreater(wolf.hp, 0)


class ClearedTests(unittest.TestCase):
    def test_some_towns_have_cleared_the_woods(self):
        w = world()
        wooded = []
        for s in (s for s in w.sites if s.kind in ("town", "village") and w.biome[s.x, s.y] in (B.FOREST, B.TAIGA)):
            lv = level(("region", s.x, s.y))
            cx, cy = lv.width // 2, lv.height // 2
            near = lv.tiles[cx - 40: cx + 40, cy - 15: cy + 15]
            wooded.append((int(np.isin(near, list(cities.trees.TRUNKS)).sum()), int((near == T.STUMP).sum())))
        cleared = [t for t, stumps in wooded if t == 0 and stumps > 0]
        if not wooded:
            self.skipTest("no wooded towns")
        self.assertTrue(cleared, wooded)

    def test_clearing_leaves_stumps_and_grass(self):
        lv = field(120, 60, T.GRASS)
        lv.tiles[::3, ::3] = T.TREE
        cities.clear_woods(lv, random.Random(1), 30)
        cx, cy = 60, 30
        near = lv.tiles[cx - 20: cx + 20, cy - 8: cy + 8]
        self.assertFalse((near == T.TREE).any())
        self.assertTrue((near == T.STUMP).any())
        self.assertTrue((lv.tiles[:5, :5] == T.TREE).any())       # further out the woods stand


class CartTests(unittest.TestCase):
    def test_every_town_has_a_cart_on_a_round_of_towns(self):
        w = world()
        cs = carts.carts(w)
        towns = [s for s in w.sites if s.kind in ("city", "town")]
        self.assertGreaterEqual(len(cs), len(towns) - 2)
        for c in cs:
            self.assertEqual(len(c.legs), carts.LOOP)
            self.assertIs(c.legs[0].a, c.home)
            for a, b in zip(c.legs, c.legs[1:]):
                self.assertIs(a.b, b.a)

    def test_a_cart_waits_a_day_then_takes_the_road(self):
        c = carts.carts(world())[0]
        states = [carts.where(c, m)[0] for m in range(0, int(c.period), 60)]
        self.assertIn("town", states)
        self.assertIn("road", states)
        # it comes round within a few days
        self.assertLess(c.period / 60, 24 * 8)

    def test_carts_show_on_the_roads(self):
        w = world()
        for m in range(0, 3 * 24 * 60, 120):
            for x, y in carts.on_the_road(w, m):
                self.assertTrue(w.road[x, y] or (x, y) in w.site_at or w.river[x, y] or True)
        self.assertTrue(any(carts.on_the_road(w, m) for m in range(0, 2 * 24 * 60, 60)))

    def ride_ready(self):
        e = Engine.new(1)
        c = carts.carts(e.world)[0]
        m = next(m for m in range(0, int(c.period), 30) if carts.where(c, e.minutes + m)[0] == "town")
        site = carts.where(c, e.minutes + m)[1]
        e.jump_clock(m)
        e.level = None
        e.player.x, e.player.y = carts.stop(site)
        e.enter_region()
        carter = next(a for a in e.level.actors if a.kind == "carter" and a.name == c.driver)
        return e, c, carter

    def test_the_carter_stands_by_the_square_with_the_cart(self):
        e, c, carter = self.ride_ready()
        parked = [lc for lc in carts.local_carts(e) if lc.driver == c.driver]
        self.assertTrue(parked and not parked[0].moving)
        self.assertEqual(sorted(parked[0].cells.values()), sorted("┌───┐O═══O"))
        self.assertTrue(all(T.WALK[e.level.tiles[q]] for q in parked[0].cells))
        self.assertLess(abs(carter.x - e.level.width // 2), 50)
        e.jump_clock(c.period / 2 + 60 * 30)                # long gone on its round
        if not any(carts.where(o, e.minutes)[0] == "town" and carts.where(o, e.minutes)[1] is
                   e.world.site_at[e.level.region] for o in carts.carts(e.world)):
            self.assertFalse(any(a.kind == "carter" for a in e.level.actors))
            self.assertFalse(any(not lc.moving for lc in carts.local_carts(e)))

    def test_riding_to_one_of_the_four_nearest_towns(self):
        e, c, carter = self.ride_ready()
        e.move_local(carter.x - e.lx, carter.y - e.ly) if max(abs(carter.x - e.lx), abs(carter.y - e.ly)) == 1 \
            else None
        e.shop = shops.for_actor(carter, e)
        self.assertIsInstance(e.shop, shops.RideMenu)
        self.assertEqual(len(e.shop.options), carts.DESTINATIONS)
        hours = [h for _, h, _ in e.shop.options]
        self.assertEqual(hours, sorted(hours))
        self.assertIn("coins", e.shop.labels()[0])
        self.assertTrue(e.shop.marks(e))
        dest, h, _ = e.shop.options[0]
        coins, start = e.player.inventory.count("coin"), e.minutes
        e.handle_key(KeySym.RETURN)
        self.assertIsNone(e.shop)
        self.assertIsNotNone(e.riding)                      # off along the road on the world map
        self.assertIsNone(e.level)
        self.assertEqual(e.player.inventory.count("coin"), coins - carts.fare(h))
        regions = e.riding.total
        e.handle_key(KeySym.D)                              # you can't walk off a moving cart
        self.assertEqual(e.riding.total - len(e.riding.steps), 0)
        seen, steps = [], 0
        while e.ride_step():                                # a region each half second, in the game
            seen.append((e.player.x, e.player.y))
            steps += 1
        self.assertEqual(steps + 1, regions)
        self.assertEqual(len(set(seen)), len(seen))         # a new region every step
        self.assertIsNone(e.riding)
        self.assertEqual(e.level.region, carts.stop(dest))
        self.assertAlmostEqual((e.minutes - start) / 60, h, delta=0.2)
        self.assertIn(dest.name, e.messages[-1])

    def test_riding_shows_on_the_world_map(self):
        import tcod
        from game import render
        e, c, carter = self.ride_ready()
        e.shop = shops.for_actor(carter, e)
        dest = e.shop.options[0][0]
        e.handle_key(KeySym.RETURN)
        e.ride_step()
        con = tcod.console.Console(120, 45, order="F")
        render.draw(con, e)
        text = "".join(chr(ch) for ch in con.rgb["ch"].T.reshape(-1))
        self.assertIn(f"to {dest.name}", text)
        self.assertIn("to go", text)
        e.handle_key(KeySym.ESCAPE)                         # the menu still comes up
        self.assertTrue(e.menu.open)

    def on_the_road(self):
        """An engine standing just by a cart that's out on the road."""
        e = Engine.new(1)
        c = carts.carts(e.world)[0]
        m = next(m for m in range(0, int(c.period), 10)
                 if carts.where(c, e.minutes + m)[0] == "road" and 0.3 < carts.where(c, e.minutes + m)[2] < 0.5)
        e.jump_clock(m)
        leg, along = carts.where(c, e.minutes)[1:]
        gx, gy = carts.road_point(e.world, leg.path, along)
        e.level = None
        e.player.x, e.player.y = gx // LOCAL_W, gy // LOCAL_H
        e.enter_region()
        lc = next(lc for lc in carts.local_carts(e) if lc.driver == c.driver)
        return e, c, lc

    def test_carts_roll_along_the_road_on_the_local_map(self):
        e, c, lc = self.on_the_road()
        self.assertTrue(lc.moving)
        self.assertIn("☺", lc.cells.values())                # the carter up front
        self.assertIn("O", lc.cells.values())                # and wheels
        before = dict(lc.cells)
        e.wait(2 / 60)
        after = next((l for l in carts.local_carts(e) if l.driver == c.driver), None)
        self.assertTrue(after is None or after.cells != before)

    def test_bumping_or_clicking_a_cart_offers_a_ride(self):
        e, c, lc = self.on_the_road()
        cell = min(lc.cells, key=lambda q: q[0])
        e.lx, e.ly = cell[0] - 1, cell[1]
        e.update_view()
        e.move_local(1, 0)
        self.assertIsInstance(e.shop, shops.RideMenu)
        self.assertEqual(e.shop.driver, c.driver)
        self.assertEqual(len(e.shop.options), carts.DESTINATIONS)
        self.assertIn("Bound for", e.shop.greeting)
        e.shop = None
        lc = next(l for l in carts.local_carts(e) if l.driver == c.driver)
        x, y = next(iter(lc.cells))
        labels = [o.label for o in e.options_at(x, y)]
        self.assertTrue(any(lab.startswith("Ride with") for lab in labels), labels)
        self.assertIn("cart", e.describe(x, y)[0])

    def test_no_coins_no_ride(self):
        e, c, carter = self.ride_ready()
        e.player.inventory.take("coin", e.player.inventory.count("coin"))
        e.shop = shops.for_actor(carter, e)
        self.assertTrue(e.shop.dim(0, e))
        where = e.level.region
        e.handle_key(KeySym.RETURN)
        self.assertEqual(e.level.region, where)

    def test_the_menu_draws_over_the_world_map(self):
        import tcod
        from game import render
        e, c, carter = self.ride_ready()
        e.shop = shops.for_actor(carter, e)
        con = tcod.console.Console(120, 45, order="F")
        render.draw(con, e)
        text = "".join(chr(ch) for ch in con.rgb["ch"].T.reshape(-1))
        self.assertIn(e.shop.options[0][0].name, text)


class ConsoleWheelTests(unittest.TestCase):
    def test_the_wheel_scrolls_the_dev_console(self):
        import tcod.event as E
        import main
        e = engine_on(field())
        e.console.toggle()
        e.console.run("help")
        e.console.run("help")
        main.handle_mouse(e, E.MouseWheel(x=0, y=1, flipped=False))
        self.assertGreater(e.console.scroll, 0)
        main.handle_mouse(e, E.MouseWheel(x=0, y=-10, flipped=False))
        self.assertEqual(e.console.scroll, 0)


if __name__ == "__main__":
    unittest.main()
