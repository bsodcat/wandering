"""Elevation and sight, the inn's floors and its barkeeper, the bag, felling, selling, digging,
grass growing back, and the town's dog or cat."""
import functools
import random
import unittest

import numpy as np
import tcod
from tcod.event import KeySym

from game import elevation
from game import items
from game import people
from game import shop as shops
from game import tiles as T
from game import trees
from game.climate import MINUTES_PER_DAY, MINUTES_PER_HOUR, Conditions
from game.engine import REGROW_MINUTES, Engine
from game.level import Level
from game.localgen import make_level
from game.render import draw
from game.worldgen import generate


@functools.lru_cache(maxsize=None)
def world(seed=1):
    return generate(seed)


def flat_engine(w=40, h=20, tile=T.GRASS) -> Engine:
    """An engine standing in the middle of a small flat test level."""
    e = Engine.new(1)
    lvl = Level(("arena", e.player.x, e.player.y), "test", np.full((w, h), tile, np.uint8))
    lvl.explored[:] = True
    e.levels[lvl.key] = lvl
    e.level, e.lx, e.ly = lvl, w // 2, h // 2
    e.update_view()
    return e


def town_engine(hour=11) -> Engine:
    e = Engine.new(1)
    e.minutes = 40 * MINUTES_PER_DAY + hour * MINUTES_PER_HOUR
    e.enter_region()
    return e


def stand_beside(e, a) -> tuple[int, int]:
    """Puts you next to actor a; returns the step that walks into them."""
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1), (1, -1), (-1, 1)):
        x, y = a.x - dx, a.y - dy
        if e.level.walkable(x, y) and people.actor_at(e.level, x, y) is None \
                and abs(int(e.level.elev[x, y]) - int(e.level.elev[a.x, a.y])) <= 2:
            e.lx, e.ly = x, y
            e.update_view()
            return dx, dy
    raise unittest.SkipTest("no room beside them")


class ElevationTests(unittest.TestCase):
    def test_local_maps_have_hills_but_no_unclimbable_steps(self):
        w = world(1)
        varied = 0
        for s in w.sites[:12]:
            lvl = make_level(w, ("region", s.x, s.y))
            h = lvl.elev.astype(int)
            self.assertLessEqual(max(np.abs(np.diff(h, axis=0)).max(), np.abs(np.diff(h, axis=1)).max()), 2)
            varied += h.max() > h.min()
        self.assertGreater(varied, 6)

    def test_heights_join_across_region_borders(self):
        w = world(1)
        x, y = next((s.x, s.y) for s in w.sites if s.kind == "cave")
        a, b = make_level(w, ("region", x + 3, y + 3)), make_level(w, ("region", x + 4, y + 3))
        self.assertLessEqual(np.abs(a.elev[-1].astype(int) - b.elev[0]).max(), 3)

    def test_settlements_are_level(self):
        w = world(1)
        s = next(s for s in w.sites if s.kind == "town")
        lvl = make_level(w, ("region", s.x, s.y))
        built = np.isin(lvl.tiles, [T.WALL, T.WOOD_FLOOR, T.DOOR, T.STREET])
        self.assertEqual(len(np.unique(lvl.elev[built])), 1)

    def test_a_ridge_hides_what_is_behind_it(self):
        h = np.zeros((30, 5), np.int16)
        h[10, :] = 4                                   # a ridge across the way
        everything = np.ones(h.shape, bool)
        seen = elevation.sightlines(h, (2, 2), everything)
        self.assertTrue(seen[10, 2])                   # the ridge itself
        self.assertFalse(seen[20, 2])                  # the ground beyond
        h[2, 2] = 8                                    # but from high enough you see over it
        self.assertTrue(elevation.sightlines(h, (2, 2), everything)[20, 2])

    def test_climbing_is_slow_and_too_steep_is_impossible(self):
        e = flat_engine()
        e.level.elev[e.lx + 1, e.ly] = 1
        e.level.elev[e.lx + 2:, :] = 3
        before = e.minutes
        e.move_local(1, 0)
        up_one = e.minutes - before
        self.assertEqual(e.lx, 20 + 1)
        before = e.minutes
        e.move_local(1, 0)                             # 1 -> 3: a scramble
        self.assertIn("scramble", e.messages[-1])
        self.assertGreater(e.minutes - before, up_one)
        e.level.elev[e.lx + 1:, :] = 7
        self.assertFalse(e.move_local(1, 0))           # 3 -> 7: a cliff
        self.assertIn("steep", e.messages[-1])

    def test_routes_go_round_cliffs(self):
        e = flat_engine()
        e.level.elev[25:, :] = 5
        e.level.elev[25:, 0] = 0
        e.level.elev[25:, 1] = 2                       # a way up at the top edge
        e.level.elev[26:, 1] = 4
        e.level.elev[27:, 1] = 5
        path = e.route(30, 10)
        steps = [(e.lx, e.ly)] + path
        for a, b in zip(steps, steps[1:]):
            self.assertLessEqual(abs(int(e.level.elev[b]) - int(e.level.elev[a])), 2)

    def test_climbing_on_the_overworld_takes_longer(self):
        w = world(1)
        self.assertGreater(elevation.world_climb_hours(w, (0, 0), (0, 0)) + 1, 0)
        low, high = np.unravel_index(np.argmin(w.elevation + (w.elevation < 0) * 1e9), w.elevation.shape), \
            np.unravel_index(np.argmax(w.elevation), w.elevation.shape)
        self.assertGreater(elevation.world_climb_hours(w, low, high), elevation.world_climb_hours(w, high, low))

    def test_relief_view_draws_heights(self):
        e = flat_engine()
        e.level.elev[:, :] = 3
        e.handle_key(KeySym.O)
        console = tcod.console.Console(120, 45, order="F")
        draw(console, e, 1.0)
        self.assertTrue((console.rgb["ch"] == ord("3")).sum() > 100)


class InnTests(unittest.TestCase):
    def test_inns_have_stairs_up_and_down(self):
        w = world(1)
        for s in [s for s in w.sites if s.kind in ("town", "inn")][:6]:
            lvl = make_level(w, ("region", s.x, s.y))
            kinds = {k[0] for k in lvl.exits.values()}
            self.assertTrue({"inn_up", "cellar"} <= kinds, s.name)

    def test_going_upstairs_and_down_to_the_cellar(self):
        e = town_engine()
        for kind, where in (("inn_up", "Upstairs at The"), ("cellar", "The cellar of The")):
            spot = next(p for p, k in e.level.exits.items() if k[0] == kind)
            ground = e.level
            e.lx, e.ly = spot
            self.assertTrue(e.use_stairs())
            self.assertTrue(e.level.name.startswith(where), e.level.name)
            self.assertEqual(e.level.underground, kind == "cellar")
            self.assertTrue(e.use_stairs())
            self.assertIs(e.level, ground)
            self.assertEqual((e.lx, e.ly), spot)

    def test_barkeeper_lets_a_room_and_you_sleep_in_it(self):
        e = town_engine(hour=20)
        bar = next(a for a in e.level.actors if a.kind == "barkeeper")
        coins = e.player.inventory.count("coin")
        step = stand_beside(e, bar)
        e.move_local(*step)
        self.assertIsNotNone(e.shop)
        e.handle_key(KeySym.RETURN)                    # the room
        self.assertEqual(e.player.inventory.count("coin"), coins - people.ROOM_PRICE)
        self.assertEqual(e.player.inventory.count("room key"), 1)
        e.handle_key(KeySym.ESCAPE)
        self.assertIsNone(e.shop)
        e.lx, e.ly = next(p for p, k in e.level.exits.items() if k[0] == "inn_up")
        e.use_stairs()
        e.lx, e.ly = (int(v) for v in np.argwhere(e.level.tiles == T.BED)[0])
        e.player.stamina = 30
        e.handle_key(KeySym.Z)
        self.assertEqual(int(e.minutes // 60 % 24), 7)
        self.assertEqual(e.player.stamina, 100)
        e.wait(4)                                      # mid-morning: the key goes back
        self.assertEqual(e.player.inventory.count("room key"), 0)

    def test_no_key_no_bed(self):
        e = town_engine()
        e.lx, e.ly = next(p for p, k in e.level.exits.items() if k[0] == "inn_up")
        e.use_stairs()
        e.lx, e.ly = (int(v) for v in np.argwhere(e.level.tiles == T.BED)[0])
        before = e.minutes
        e.handle_key(KeySym.Z)
        self.assertEqual(e.minutes, before)
        self.assertIn("paying guests", e.messages[-1])


class ToolTests(unittest.TestCase):
    def test_the_axe_leans_by_the_lumberjacks_house_and_a_shovel_is_indoors(self):
        w = world(1)
        found_axe = found_shovel = 0
        for s in [s for s in w.sites if s.kind in ("town", "village")][:10]:
            lvl = make_level(w, ("region", s.x, s.y))
            for (x, y), pile in lvl.items.items():
                if "axe" in pile:
                    found_axe += 1
                    jack = next(a for a in lvl.actors if a.kind == "lumberjack")
                    house = next(b for b in lvl.buildings if set(jack.home) & set(b.floor(lvl.tiles)))
                    self.assertLessEqual(abs(x - house.door[0]) + abs(y - house.door[1]), 4)
                    self.assertFalse(T.ROOF[lvl.tiles[x, y]])
                if "shovel" in pile:
                    found_shovel += 1
                    self.assertEqual(lvl.building_at(x, y).kind, "house")
            self.assertEqual(any("axe" in p for p in lvl.items.values()),
                             any(a.kind == "lumberjack" for a in lvl.actors), s.name)
        self.assertGreater(found_axe, 0)
        self.assertEqual(found_shovel, 10)

    def test_pick_up_and_chop(self):
        e = flat_engine()
        items.drop(e.level, e.lx, e.ly, "axe")
        e.handle_key(KeySym.G)
        self.assertEqual(e.player.inventory.count("axe"), 1)
        self.assertFalse(e.level.items)
        e.level.tiles[e.lx + 1, e.ly] = T.TREE
        e.level.canopy[:], e.level.boughs[:] = trees.crowns(e.level.tiles)
        e.move_local(1, 0)
        self.assertEqual(e.level.tiles[e.lx + 1, e.ly], T.STUMP)
        self.assertEqual(e.player.inventory.count("log"), 2)
        self.assertFalse(e.level.canopy.any())

    def test_without_an_axe_trees_are_in_the_way(self):
        e = flat_engine()
        e.level.tiles[e.lx + 1, e.ly] = T.TREE
        self.assertFalse(e.move_local(1, 0))
        self.assertEqual(e.level.tiles[e.lx + 1, e.ly], T.TREE)

    def test_selling_logs_to_the_lumberjack(self):
        e = town_engine()
        jack = next((a for a in e.level.actors if a.kind == "lumberjack"), None)
        if jack is None:
            self.skipTest("no lumberjack in this town")
        step = stand_beside(e, jack)
        e.move_local(*step)                            # no logs: just a word about the axe
        self.assertIsNone(e.shop)
        self.assertIn("axe", e.messages[-1])
        jack.x, jack.y = e.lx + step[0], e.ly + step[1]
        if not e.level.walkable(jack.x, jack.y):
            step = stand_beside(e, jack)
        e.player.inventory.add("log", 4)
        coins = e.player.inventory.count("coin")
        e.move_local(*step)
        self.assertIsNotNone(e.shop)
        e.handle_key(KeySym.DOWN)                      # sell all
        e.handle_key(KeySym.RETURN)
        self.assertEqual(e.player.inventory.count("log"), 0)
        self.assertEqual(e.player.inventory.count("coin"), coins + 4 * shops.LOG_PRICE)

    def test_shop_draws(self):
        e = town_engine(hour=20)
        bar = next(a for a in e.level.actors if a.kind == "barkeeper")
        e.move_local(*stand_beside(e, bar))
        console = tcod.console.Console(120, 45, order="F")
        draw(console, e, 1.0)
        text = "".join(chr(c) for c in console.rgb["ch"].T.flatten())
        self.assertIn("A room for the night", text)
        x, y, w, h = e.shop.box()
        self.assertTrue(e.shop.click(x + 10, e.shop.row_y(1), e) is False)   # Leave


class DiggingTests(unittest.TestCase):
    def test_dig_finds_what_is_buried_and_leaves_turned_earth(self):
        e = flat_engine()
        e.level.elev[:] = 4
        e.handle_key(KeySym.X)
        self.assertIn("shovel", e.messages[-1])
        e.player.inventory.add("shovel")
        e.level.buried[(e.lx, e.ly)] = ("silver ring", 1)
        e.handle_key(KeySym.X)
        self.assertEqual(e.player.inventory.count("silver ring"), 1)
        self.assertEqual(e.level.tiles[e.lx, e.ly], T.DUG)
        self.assertEqual(e.level.elev[e.lx, e.ly], 4)  # digging doesn't change the height
        e.handle_key(KeySym.X)
        self.assertIn("already", e.messages[-1])
        e.lx += 1
        e.handle_key(KeySym.X)
        self.assertIn("nothing", e.messages[-1])

    def test_no_digging_floors_or_underground(self):
        e = flat_engine(tile=T.WOOD_FLOOR)
        e.player.inventory.add("shovel")
        e.handle_key(KeySym.X)
        self.assertEqual(e.level.tiles[e.lx, e.ly], T.WOOD_FLOOR)

    def test_grass_grows_back_after_rain(self):
        e = flat_engine()
        e.fair = False
        e.player.inventory.add("shovel")
        dry = Conditions(15, 0.1, 0, 5, 0, 1, "Clear")
        wet = Conditions(15, 0.9, 0.5, 5, 0, 0.6, "Rain")
        e.weather = lambda: dry
        e.now = dry
        e.handle_key(KeySym.X)
        spot = (e.lx, e.ly)
        e.wait(10)
        self.assertEqual(e.level.tiles[spot], T.DUG)           # no rain, no grass
        e.weather = lambda: wet
        e.wait(1)
        e.weather = lambda: dry
        e.wait(REGROW_MINUTES / 60 + 1)
        self.assertEqual(e.level.tiles[spot], T.GRASS)

    def test_settlements_and_country_have_things_buried(self):
        w = world(1)
        s = next(s for s in w.sites if s.kind == "ruins")
        lvl = make_level(w, ("region", s.x, s.y))
        self.assertGreater(len(lvl.buried), 10)
        for (x, y), (kind, n) in lvl.buried.items():
            self.assertTrue(T.DIGGABLE[lvl.tiles[x, y]])
            self.assertIn(kind, items.KINDS)


class PetTests(unittest.TestCase):
    def test_every_town_has_a_dog_or_a_cat(self):
        w = world(1)
        for s in [s for s in w.sites if s.kind == "town"][:5]:
            lvl = make_level(w, ("region", s.x, s.y))
            pets = [a for a in lvl.actors if a.kind in ("dog", "cat")]
            self.assertEqual(len(pets), 1, s.name)
        for s in [s for s in w.sites if s.kind == "village"][:5]:
            self.assertFalse(any(a.kind in ("dog", "cat") for a in make_level(w, ("region", s.x, s.y)).actors))

    def test_the_pet_follows_you(self):
        e = town_engine()
        pet = next(a for a in e.level.actors if a.kind in ("dog", "cat"))
        e.lx, e.ly = e.level.nearest_walkable(pet.x + 8, pet.y)
        start = max(abs(pet.x - e.lx), 2 * abs(pet.y - e.ly))
        e.wait(0.5)
        self.assertLess(max(abs(pet.x - e.lx), 2 * abs(pet.y - e.ly)), start)

    def test_petting(self):
        e = town_engine()
        pet = next(a for a in e.level.actors if a.kind in ("dog", "cat"))
        where = (pet.x, pet.y)
        step = stand_beside(e, pet)
        before = (e.lx, e.ly)
        e.move_local(*step)
        self.assertEqual((e.lx, e.ly), before)          # you stay put to pet it
        self.assertIn(pet.name, e.messages[-1])
        self.assertTrue(any(w in e.messages[-1] for w in ("pet", "scratch", "rub", "belly")))
        self.assertTrue(abs(pet.x - where[0]) <= 2)


class ArenaItemTests(unittest.TestCase):
    def test_the_arena_has_every_item_a_hill_and_a_dig_site(self):
        e = Engine.arena()
        lying = {k for pile in e.level.items.values() for k in pile}
        self.assertEqual(set(items.KINDS) - lying, set())
        self.assertGreaterEqual(int(e.level.elev.max()), 10)
        self.assertGreater(len(e.level.buried), 50)
        self.assertTrue({"dog", "cat", "barkeeper"} <= {a.kind for a in e.level.actors})
        inn_up = next(p for p, k in e.level.exits.items() if k[0] == "inn_up")
        e.lx, e.ly = inn_up
        self.assertTrue(e.use_stairs())
        self.assertTrue(e.use_stairs())
        self.assertEqual(e.level.key[0], "arena")


if __name__ == "__main__":
    unittest.main()
