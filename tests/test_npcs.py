"""Townsfolk, their animals, their day; the inn, the shops, and fields that suit the climate."""
import functools
import random
import unittest

import tcod

from game import biomes as B
from game import farming
from game import people
from game import tiles as T
from game.climate import MINUTES_PER_DAY
from game.engine import Engine
from game.localgen import make_level
from game.render import SCREEN_H, SCREEN_W, draw
from game.worldgen import generate


@functools.lru_cache(maxsize=None)
def world(seed=1):
    return generate(seed)


def site_levels(kind, seeds=(1, 2), most=6):
    out = []
    for seed in seeds:
        for s in world(seed).sites:
            if s.kind == kind and len(out) < most:
                out.append((s, make_level(world(seed), ("region", s.x, s.y))))
    return out


def land(temp, moisture, biome=B.GRASSLAND, lat=-0.5):
    return farming.Land(biome, temp, moisture, lat)


class ClimateTests(unittest.TestCase):
    def test_grain_suits_the_climate(self):
        self.assertEqual(farming.grain_for(land(12, 0.5)), T.WHEAT)
        self.assertEqual(farming.grain_for(land(1, 0.5)), T.RYE)
        self.assertEqual(farming.grain_for(land(10, 0.5, B.TAIGA)), T.RYE)
        self.assertEqual(farming.grain_for(land(25, 0.8)), T.RICE)
        self.assertEqual(farming.grain_for(land(25, 0.3)), T.MILLET)
        self.assertEqual(farming.grain_for(land(14, 0.1)), T.MILLET)

    def test_herds_suit_the_land(self):
        self.assertEqual(farming.herd_for(land(12, 0.5)), "cow")
        self.assertEqual(farming.herd_for(land(12, 0.5, B.HILLS)), "sheep")
        self.assertEqual(farming.herd_for(land(12, 0.5, B.MOUNTAINS)), "goat")
        self.assertEqual(farming.herd_for(land(12, 0.5, B.FOREST)), "pig")
        self.assertEqual(farming.herd_for(land(-3, 0.5, B.TUNDRA)), "reindeer")

    def test_fields_go_through_the_year(self):
        stages = [farming.crop_stage(-0.5, d * MINUTES_PER_DAY) for d in range(120)]
        self.assertEqual(set(stages), {"shoots", "growing", "ripe", "stubble", "fallow"})
        self.assertEqual(stages[45], "ripe")                                          # midsummer, north
        self.assertEqual(farming.crop_stage(0.5, 45 * MINUTES_PER_DAY), "fallow")     # midwinter, south
        self.assertEqual({farming.crop_stage(0.05, d * MINUTES_PER_DAY) for d in range(120)}, {"growing"})

    def test_villages_grow_their_climates_grain(self):
        w = world(1)
        for s, lvl in site_levels("village", (1,)):
            self.assertEqual(lvl.crop, farming.grain_for(farming.land_at(w, s.x, s.y)), s.name)
            self.assertGreater((lvl.tiles == lvl.crop).sum(), 30, s.name)


class BuildingTests(unittest.TestCase):
    def test_every_town_has_a_named_inn_a_bakery_and_a_butcher(self):
        for s, lvl in site_levels("town"):
            kinds = {b.kind: b for b in lvl.buildings}
            for kind in ("inn", "bakery", "butcher"):
                self.assertIn(kind, kinds, s.name)
            inn = kinds["inn"]
            self.assertTrue(inn.name.startswith("The "), inn.name)
            inside = lvl.tiles[inn.x0: inn.x0 + inn.w, inn.y0: inn.y0 + inn.h]
            self.assertGreaterEqual((inside == T.COUNTER).sum(), 3)
            self.assertFalse((inside == T.BED).any())      # the beds are upstairs
            self.assertTrue((inside == T.SIGN).any())
            for kind, tile in (("bakery", T.OVEN), ("butcher", T.HOOKS)):
                b = kinds[kind]
                self.assertTrue((lvl.tiles[b.x0: b.x0 + b.w, b.y0: b.y0 + b.h] == tile).any(), (s.name, kind))

    def test_roadside_inns_get_the_same_inn_and_horses(self):
        for s, lvl in site_levels("inn"):
            self.assertTrue(any(b.kind == "inn" for b in lvl.buildings), s.name)
            self.assertEqual({a.kind for a in lvl.actors}, {"innkeeper", "barkeeper", "horse"})

    def test_pastures_are_fenced_with_a_trough(self):
        for s, lvl in site_levels("village"):
            pastures = [p for p in lvl.places if p.kind == "pasture"]
            self.assertTrue(pastures, s.name)
            for p in pastures:
                xs, ys = zip(*p.tiles)
                ring = lvl.tiles[min(xs) - 1: max(xs) + 2, min(ys) - 1: max(ys) + 2]
                self.assertTrue((ring == T.TROUGH).any())
                self.assertGreater((ring == T.FENCE).sum(), 10)


class PeopleTests(unittest.TestCase):
    def test_towns_have_their_trades_where_there_is_work_for_them(self):
        for s, lvl in site_levels("town"):
            jobs = [a.kind for a in lvl.actors if not a.animal]
            for job in ("baker", "butcher", "innkeeper", "farmer"):
                self.assertIn(job, jobs, s.name)
            places = {p.kind for p in lvl.places}
            self.assertEqual("fisherman" in jobs, bool(places & {"pier", "shore"}), s.name)
            self.assertEqual("lumberjack" in jobs, "camp" in places, s.name)

    def test_villages_have_farmers_but_no_shops(self):
        for s, lvl in site_levels("village"):
            jobs = {a.kind for a in lvl.actors if not a.animal}
            self.assertIn("farmer", jobs, s.name)
            self.assertFalse(jobs & {"baker", "butcher", "innkeeper"}, s.name)

    def test_everyone_keeps_their_hours(self):
        s, lvl = site_levels("town", most=1)[0]
        e = Engine.new(1)
        for hour, where in ((2, "home"), (11, "work")):
            lvl.sim_minutes = None               # placed fresh for each hour
            people.advance(lvl, 40 * MINUTES_PER_DAY + hour * 60, e, random.Random(1))
            for a in lvl.actors:
                if a.animal:
                    continue
                expected = a.home if where == "home" else a.work
                self.assertIn((a.x, a.y), expected, (a.kind, hour))

    def test_walking_keeps_to_floors_and_out_of_each_others_way(self):
        s, lvl = site_levels("town", most=1)[0]
        e = Engine.new(1)
        start = 40 * MINUTES_PER_DAY + 5 * 60
        rng = random.Random(3)
        lvl.sim_minutes = None
        people.advance(lvl, start, e, rng)
        before = {id(a): (a.x, a.y) for a in lvl.actors}
        for minute in range(0, 300, 3):          # five hours, a few minutes at a time
            people.advance(lvl, start + minute, e, rng)
            spots = [(a.x, a.y) for a in lvl.actors]
            self.assertEqual(len(spots), len(set(spots)))
            for a in lvl.actors:
                self.assertTrue(T.WALK[lvl.tiles[a.x, a.y]], (a.kind, a.x, a.y))
                if a.animal and a.kind not in ("hen", "dog", "cat"):     # pets wander, and follow you
                    self.assertIn((a.x, a.y), a.work)
        moved = sum((a.x, a.y) != before[id(a)] for a in lvl.actors if not a.animal)
        self.assertGreater(moved, 2)


class MeetingTests(unittest.TestCase):
    def engine_beside(self, kind):
        e = Engine.new(1)
        e.minutes = 40 * MINUTES_PER_DAY + 11 * 60
        e.enter_region()
        lvl = e.level
        a = next(a for a in lvl.actors if a.kind == kind)
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1), (1, -1), (-1, 1)):
            x, y = a.x - dx, a.y - dy
            if lvl.walkable(x, y) and people.actor_at(lvl, x, y) is None:
                e.lx, e.ly = x, y
                e.update_view()
                return e, a, (dx, dy)
        self.skipTest("no room beside them")

    def test_walking_into_someone_talks_and_steps_past(self):
        e, a, (dx, dy) = self.engine_beside("baker")
        old, there = (e.lx, e.ly), (a.x, a.y)
        e.move_local(dx, dy)
        talked = [m for m in e.messages if "the baker" in m]
        self.assertTrue(talked and "Hello" in talked[-1])
        self.assertEqual((e.lx, e.ly), there)
        self.assertTrue(a.met)
        self.assertNotEqual((a.x, a.y), there)
        self.assertTrue(abs(a.x - old[0]) <= 1 and abs(a.y - old[1]) <= 1)

    def test_pointing_at_someone_says_who_they_are(self):
        e, a, _ = self.engine_beside("baker")
        lines = e.describe(a.x, a.y)
        self.assertEqual(lines[0], f"{a.name}, the baker")
        self.assertIn("Baking bread", lines)
        self.assertTrue(any(line.startswith("In the bakery") for line in lines))

    def test_animals_get_pushed_past(self):
        e = Engine.new(1)
        e.enter_region()
        hen = next(a for a in e.level.actors if a.kind == "hen")
        self.assertIn("clucks", people.talk(hen, e.level, e))

    def test_people_are_drawn(self):
        e, a, _ = self.engine_beside("baker")
        console = tcod.console.Console(SCREEN_W, SCREEN_H, order="F")
        draw(console, e, 1.0)
        self.assertTrue((console.rgb["ch"] == ord(people.PERSON)).any())


if __name__ == "__main__":
    unittest.main()
