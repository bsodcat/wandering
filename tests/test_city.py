"""A stone city's people and landmarks: the keep and its court, the dungeon, temples, playhouses
and gallows, the townsfolk's comings and goings, thieves and the guards after them, and the
watch fort beside every city."""
import unittest

import numpy as np

from game import cities, citylife, eras, landmarks, people, shop as shops
from game import tiles as T
from game.engine import Engine
from game.people import Actor
from game.player import Player

from tests.test_places import level, world
from tests.test_wild import engine_on, field


class Always:
    """An rng that always says yes: every roll comes up lowest."""

    def random(self):
        return 0.0

    def randint(self, a, b):
        return a

    def choice(self, seq):
        return seq[0]

    def randrange(self, n):
        return 0

    def shuffle(self, seq):
        pass


def city():
    return next(s for s in world().sites if s.kind == "city")


def parts():
    c = city()
    return {(px, py): level(("region", c.x + px, c.y + py)) for px in range(c.span[0]) for py in range(c.span[1])}


def keep_level():
    c = city()
    px, py = landmarks.keep_part(c)
    return level(("region", c.x + px, c.y + py))


def kinds(lv) -> list:
    return [a.kind for a in lv.actors]


class LandmarkTests(unittest.TestCase):
    def test_each_part_has_its_own_landmarks(self):
        built = {b.kind for lv in parts().values() for b in lv.buildings}
        places = {p.kind for lv in parts().values() for p in lv.places}
        for kind in ("throne room", "great hall", "royal chambers", "library", "barracks", "gaol", "temple",
                     "playhouse", "guildhall", "alchemist"):
            self.assertIn(kind, built)
        for kind in ("gallows", "pit", "market", "keep", "keep gate"):
            self.assertIn(kind, places)

    def test_every_part_has_an_inn_a_guardhouse_and_watched_crossings(self):
        for lv in parts().values():
            self.assertIn("inn", {b.kind for b in lv.buildings})
            self.assertIn("guardhouse", {b.kind for b in lv.buildings})
            self.assertTrue(any(p.kind == "crossing" for p in lv.places))
            self.assertTrue((lv.tiles == T.STATUE).any())

    def test_the_keep_has_a_throne_a_library_and_stairs_down_to_the_dungeon(self):
        lv = keep_level()
        self.assertEqual(int((lv.tiles == T.THRONE).sum()), 1)
        self.assertGreater(int((lv.tiles == T.BOOKSHELF).sum()), 10)
        self.assertTrue((lv.tiles == T.CARPET).any())
        down = [pos for pos, key in lv.exits.items() if key[0] == "dungeon"]
        self.assertEqual(len(down), 1)
        gaol = next(b for b in lv.buildings if b.kind == "gaol")
        self.assertTrue(gaol.contains(*down[0]))

    def test_the_other_parts_have_a_fountain(self):
        keep = keep_level()
        for lv in parts().values():
            middle = lv.tiles[lv.width // 2, lv.height // 2]
            if lv is keep:
                self.assertIn(middle, (T.WELL, T.BRIDGE))
            else:                                   # (unless the river runs through the square)
                self.assertIn(middle, (T.FOUNTAIN, T.BRIDGE))

    def test_a_watch_fort_beside_every_city(self):
        w = world()
        for c in (s for s in w.sites if s.kind == "city"):
            watch = [s for s in w.sites if s.kind == "fort" and s.ward == c.name]
            self.assertEqual(len(watch), 1, c.name)
            self.assertEqual(c.distance(watch[0].x, watch[0].y), 1)
        s = next(s for s in w.sites if s.kind == "fort" and s.ward)
        lv = level(("region", s.x, s.y))
        self.assertEqual(kinds(lv).count("guard"), 3)
        self.assertEqual(kinds(lv).count("archer"), 2)

    def test_a_city_keeps_its_size_through_a_time_skip(self):
        kept = eras.survivors(world(), 1)
        c = next(s for s in kept if s.name == city().name)
        self.assertEqual(c.span, city().span)


class PeopleTests(unittest.TestCase):
    def test_the_keep_has_a_ruler_a_consort_and_a_court(self):
        k = kinds(keep_level())
        self.assertEqual(k.count("king") + k.count("prince"), 1)
        self.assertEqual(k.count("queen") + k.count("concubine"), 1)
        for job in ("cook", "librarian", "servant"):
            self.assertIn(job, k)
        ruler = next(a for a in keep_level().actors if a.kind in ("king", "prince"))
        self.assertTrue(ruler.title.startswith(("King ", "Prince ")))

    def test_the_court_keeps_its_hours(self):
        lv = keep_level()
        ruler = next(a for a in lv.actors if a.kind in ("king", "prince"))
        throne_room = next(b for b in lv.buildings if b.kind == "throne room")
        hall = next(b for b in lv.buildings if b.kind == "great hall")
        area, doing = people.plan(ruler, 10.0, {"day": 0})
        self.assertEqual(doing, "holding court")
        self.assertTrue(all(throne_room.contains(*c) for c in area))
        area, doing = people.plan(ruler, 19.0, {"day": 0})
        self.assertIn("feasting", doing)
        self.assertTrue(all(hall.contains(*c) for c in area))
        self.assertEqual(people.plan(ruler, 2.0, {"day": 0})[1], "asleep")

    def test_a_city_is_full_of_people(self):
        for lv in parts().values():
            k = kinds(lv)
            self.assertGreaterEqual(k.count("townsperson"), 14)
            self.assertGreaterEqual(sum(k.count(c) for c in people.CRAFTS), 20)
            self.assertIn("merchant", k)
            self.assertIn("beggar", k)
            self.assertGreaterEqual(k.count("thief"), 1)

    def test_more_thieves_more_guards(self):
        for lv in parts().values():
            gates = sum(p.kind == "gate" for p in lv.places)
            crossings = sum(p.kind == "crossing" for p in lv.places)
            royal = 6 if any(b.kind == "throne room" for b in lv.buildings) else 0
            self.assertEqual(kinds(lv).count("guard"),
                             min(6, 2 * gates) + crossings + citylife.GUARDS_PER_THIEF * lv.thieves + royal)

    def test_some_guards_keep_the_night_watch(self):
        lv = next(iter(parts().values()))
        guards = [a for a in lv.actors if a.kind == "guard"]
        night = [g for g in guards if g.shift and g.shift[1] > 24]
        self.assertTrue(night and len(night) < len(guards))
        two_am = 40 * 1440 + 2 * 60
        self.assertTrue(all(people.on_duty(g, two_am) for g in night))
        self.assertFalse(any(people.on_duty(g, two_am) for g in guards if g not in night))

    def test_townsfolk_go_their_own_ways(self):
        lv = next(iter(parts().values()))
        folk = [a for a in lv.actors if a.kind == "townsperson"]
        at_noon = {people.plan(a, 12.0, {"day": 3, "inn": "the inn"})[1] for a in folk}
        self.assertGreater(len(at_noon), 1)                    # not all in the same place
        a = folk[0]
        through_the_day = {people.plan(a, h / 4, {"day": 3, "inn": "the inn"})[1] for h in range(40, 80)}
        self.assertGreater(len(through_the_day), 1)            # nor in one place all day

    def test_a_thief_passes_for_a_townsperson(self):
        lv = next(iter(parts().values()))
        th = next(a for a in lv.actors if a.kind == "thief")
        self.assertIn("townsperson", th.title)
        th.exposed = True
        self.assertIn("thief", th.title)
        th.exposed = False


class HouseTests(unittest.TestCase):
    def lived_in(self, lv) -> set:
        return {id(lv.building_at(*a.home[0])) for a in lv.actors
                if a.home and not a.animal and lv.building_at(*a.home[0]) is not None}

    def test_every_town_house_has_someone_in_it(self):
        for s in [s for s in world().sites if s.kind in ("town", "village")][:4]:
            lv = level(("region", s.x, s.y))
            homes = self.lived_in(lv)
            houses = [b for b in lv.buildings if b.kind == "house"]
            self.assertTrue(houses)
            self.assertTrue(all(id(b) in homes for b in houses), s.name)

    def test_a_city_house_nobody_lives_in_is_empty_and_full_of_junk(self):
        lv = keep_level()
        homes = self.lived_in(lv)
        empty = [b for b in lv.buildings if b.kind == "house" and id(b) not in homes]
        self.assertTrue(empty)
        for b in empty:
            self.assertIn("junk", b.name)
            inside = lv.tiles[b.x0 + 1: b.x0 + b.w - 1, b.y0 + 1: b.y0 + b.h - 1]
            self.assertFalse(np.isin(inside, [T.BED, T.TABLE, T.CHEST, T.HEARTH, T.BARREL]).any())
            self.assertTrue((inside == T.JUNK).any())

    def test_some_cities_have_abandoned_houses(self):
        abandoned = {}
        for c in (s for s in world().sites if s.kind == "city"):
            px, py = c.part(c.x, c.y)
            lv = level(("region", c.x, c.y))
            abandoned[c.name] = sum(b.name == "an abandoned house" for b in lv.buildings)
        self.assertTrue(any(abandoned.values()) and not all(abandoned.values()), abandoned)
        lv = level(("region", *next(c for c in world().sites if abandoned.get(c.name)).cells[0]))
        ruin = next(b for b in lv.buildings if b.name == "an abandoned house")
        self.assertEqual(lv.tiles[ruin.door], T.RUBBLE)


class ShoreTests(unittest.TestCase):
    def test_nothing_is_built_on_the_banks_of_open_water(self):
        for c in (s for s in world().sites if s.kind == "city"):
            band = cities.shore_of(c)
            self.assertTrue(cities.SHORE[0] <= band <= cities.SHORE[1])
            for cell in c.cells:
                lv = level(("region", *cell))
                near = cities.dilate(cities.open_water(lv.tiles), band - 1)
                for b in lv.buildings:
                    self.assertFalse(near[b.x0: b.x0 + b.w, b.y0: b.y0 + b.h].any(), (c.name, b.kind))

    def test_open_water_is_more_than_three_by_three(self):
        t = np.full((20, 20), T.GRASS, np.uint8)
        t[2:4, 2:12] = T.WATER                   # a stream two wide: not open water
        t[10:15, 10:14] = T.WATER                # a pond
        big = cities.open_water(t)
        self.assertFalse(big[2:4, 2:12].any())
        self.assertTrue(big[10:15, 10:14].all())

    def test_a_wall_comes_in_for_water_along_its_side(self):
        t = np.full((256, 216), T.GRASS, np.uint8)
        t[0:30, :] = T.WATER                      # a lake all along the west
        big = cities.open_water(t)
        bounds = cities.pull_in((10, 6, 255, 215), big, 12, (0, 0), (2, 2))
        self.assertEqual(bounds[0], 29 + 12 + 1)
        self.assertEqual(bounds[1:], (6, 255, 215))
        t[:, :] = T.GRASS
        t[0:30, 100:104] = T.WATER                # only a river coming in across it: the wall stays
        self.assertEqual(cities.pull_in((10, 6, 255, 215), cities.open_water(t), 12, (0, 0), (2, 2))[0], 10)


class WanderTests(unittest.TestCase):
    def test_townsfolk_mostly_walk_the_streets(self):
        lv = next(iter(parts().values()))
        folk = [a for a in lv.actors if a.kind == "townsperson"]
        doing = [people.plan(a, h, {"day": 2, "inn": "the inn"})[1] for a in folk for h in (9.0, 11.5, 14.0, 16.5)]
        self.assertGreater(doing.count("wandering the streets") / len(doing), 0.3)
        self.assertLess(doing.count("browsing the market") / len(doing), 0.3)


class QuarterTests(unittest.TestCase):
    def test_a_garden_inside_a_gate(self):
        c = city()
        lv = level(("region", *(a + b for a, b in zip((c.x, c.y), landmarks.garden_part(c)))))
        g = next(p for p in lv.places if p.kind == "garden")
        self.assertTrue(any(lv.tiles[x, y] == T.FLOWERS for x in range(min(x for x, _ in g.tiles) - 1,
                                                                        max(x for x, _ in g.tiles) + 2)
                            for y in range(min(y for _, y in g.tiles), max(y for _, y in g.tiles) + 1)))
        gate = [p for p in lv.places if p.kind == "gate"]
        near = min(abs(x - gx) + abs(y - gy) for x, y in g.tiles for p in gate for gx, gy in p.tiles[:1])
        self.assertLess(near, 90)

    def test_the_lower_quarter_has_hovels_and_its_people(self):
        found = False
        for part, lv in parts().items():
            hovels = [b for b in lv.buildings if "hovel" in b.name]
            if landmarks.lower_quarter(city(), part):
                self.assertGreater(len(hovels), 20)
                self.assertTrue(all(b.w <= 6 and b.h <= 5 for b in hovels))
                self.assertIn("labourer", kinds(lv))
                found = True
            else:
                self.assertEqual(hovels, [])
        self.assertTrue(found)

    def test_trees_in_and_around_the_city(self):
        for lv in parts().values():
            trunks = np.isin(lv.tiles, [T.TREE, T.PINE, T.JUNGLE_TREE])
            cx, cy = lv.width // 2, lv.height // 2
            self.assertGreater(int(trunks[cx - 4: cx + 4, :].sum()), 4)      # along the main street
            self.assertGreater(int(trunks.sum()), 40)


class FamilyTests(unittest.TestCase):
    def test_homemakers_cook_for_their_other_halves(self):
        lv = next(iter(parts().values()))
        homes = [a for a in lv.actors if a.kind == "homemaker"]
        self.assertGreater(len(homes), 5)
        h = homes[0]
        partner = next(a for a in lv.actors if a is not h and a.home is h.home)
        first = partner.name.split()[0]
        self.assertEqual(h.name.split()[-1], partner.name.split()[-1])           # the same family
        self.assertEqual(people.plan(h, 12.0, {})[1], f"cooking dinner for {first}")
        self.assertEqual(people.plan(h, 17.0, {})[1], f"preparing supper for {first}")
        house = lv.building_at(*h.home[0])
        self.assertTrue(all(house.contains(*c) for c in people.plan(h, 12.0, {})[0]))
        self.assertEqual(partner.evening_kind, "home")                         # home for supper

    def test_towns_have_homemakers_too(self):
        found = 0
        for s in [s for s in world().sites if s.kind == "town"][:4]:
            found += kinds(level(("region", s.x, s.y))).count("homemaker")
        self.assertGreater(found, 0)

    def test_children_play_tag_in_bands(self):
        lv = next(iter(parts().values()))
        kids = [a for a in lv.actors if a.kind == "child"]
        self.assertGreater(len(kids), 3)
        for k in kids:
            self.assertGreaterEqual(len(k.friends), 2)
            self.assertEqual(sum(f.it for f in k.friends), 1)

    def test_a_tag_and_the_other_ones_it(self):
        lv = field(80, 30)
        a = Actor("child", "Pip Vane", 20, 15, home=[(2, 2)], work=[(20, 15)])
        b = Actor("child", "Wren Vane", 22, 15, home=[(2, 2)], work=[(22, 15)])
        citylife.playmates([a, b], Always())
        it, other = (a, b) if a.it else (b, a)
        for k in (a, b):
            k.doing = "playing tag"
        lv.actors += [a, b]
        e = engine_on(lv, at=(60, 25))
        for _ in range(10):
            citylife.play(lv, e, Always(), 1.0)
            if other.it:
                break
        self.assertTrue(other.it)
        self.assertFalse(it.it)


class SundayTests(unittest.TestCase):
    def test_every_part_has_a_temple_or_a_chapel(self):
        for lv in parts().values():
            self.assertIsNotNone(people.church_of(lv))

    def test_sunday_service(self):
        lv = next(iter(parts().values()))
        church = people.church_of(lv)
        sunday = people.plans(lv, 9.5, {"day": 6, "weekday": "Sunday", "inn": "the inn"})
        monday = people.plans(lv, 9.5, {"day": 7, "weekday": "Monday", "inn": "the inn"})
        going = [a for a, (area, doing) in zip(lv.actors, sunday) if doing == "at the Sunday service"]
        self.assertGreater(len(going), 20)
        self.assertTrue(all(church.contains(*area[0]) for area, doing in sunday if doing == "at the Sunday service"))
        self.assertFalse(any(doing == "at the Sunday service" for _, doing in monday))
        self.assertFalse(any(a.kind in ("guard", "thief") for a in going))
        priest = [doing for a, (_, doing) in zip(lv.actors, sunday) if a.kind == "priest"]
        self.assertEqual(priest, ["leading the Sunday service"])


class InnTests(unittest.TestCase):
    def test_an_inn_holds_eight_at_most_staff_and_all(self):
        from game.level import Building
        lv = field(80, 30)
        inn = Building("inn", "the Red Lion", 10, 5, 15, 8, (17, 12))
        lv.buildings.append(inn)
        floor = inn.floor(lv.tiles)
        green = [(x, 20) for x in range(30, 50)]
        lv.actors += [Actor("innkeeper", "Hal Kemp", 11, 6, home=floor, work=floor),
                      Actor("barkeeper", "Ida Vane", 12, 6, home=floor, work=floor)]
        lv.actors += [Actor("weaver", f"Weaver {i}", 40, 20, home=green, work=green, evening=floor,
                            evening_kind="inn") for i in range(12)]
        evening = people.plans(lv, 19.0, {"day": 1, "inn": "the Red Lion"})
        inside = [a for a, (area, _) in zip(lv.actors, evening) if inn.contains(*area[0])]
        self.assertEqual(len(inside), people.INN_CROWD)
        self.assertIn("innkeeper", [a.kind for a in inside])
        self.assertIn("barkeeper", [a.kind for a in inside])
        later = people.plans(lv, 20.0, {"day": 1, "inn": "the Red Lion"})
        self.assertEqual([a for a, (area, _) in zip(lv.actors, later) if inn.contains(*area[0])], inside)


class CrimeTests(unittest.TestCase):
    def scene(self, guard_at=(42, 15)):
        lv = field(80, 30)
        lv.thieves = 1
        lv.crime_day = 40
        th = Actor("thief", "Kit Marsh", 20, 15, home=[(2, 2)], work=[(20, 15)], shift=(10, 26))
        victim = Actor("townsperson", "Cora Vane", 21, 15, home=[(2, 3)], work=[(21, 15)])
        guard = Actor("guard", "Hal Brook", *guard_at, home=[(2, 4)], work=[guard_at])
        lv.actors += [th, victim, guard]
        e = engine_on(lv, at=(25, 20))
        return e, lv, th, victim, guard

    def test_a_thief_picks_a_pocket_and_the_guard_gives_chase(self):
        e, lv, th, victim, guard = self.scene()
        citylife.crime(lv, e, Always(), 1.0)
        self.assertGreater(th.loot, 0)
        self.assertTrue(th.exposed)
        self.assertIsNotNone(th.fleeing)
        self.assertIs(guard.chase, th)
        self.assertTrue(any("Thief!" in m for m in e.messages))

    def test_not_with_a_guard_looking_on(self):
        e, lv, th, victim, guard = self.scene(guard_at=(24, 15))
        citylife.crime(lv, e, Always(), 1.0)
        self.assertEqual(th.loot, 0)
        self.assertIsNone(th.fleeing)

    def test_the_guard_runs_the_thief_down(self):
        e, lv, th, victim, guard = self.scene(guard_at=(30, 15))
        citylife.alarm(lv, e, th, victim, Always())
        for _ in range(60):
            if th not in lv.actors:
                break
            e.minutes += 1
            citylife.chase(lv, e, Always(), 1.0)
        self.assertNotIn(th, lv.actors)
        self.assertEqual(lv.arrests, 1)
        self.assertIsNone(guard.chase)

    def test_a_thief_who_outruns_them_gets_away(self):
        e, lv, th, victim, guard = self.scene()
        citylife.alarm(lv, e, th, victim, Always())
        e.minutes = th.fleeing
        citylife.chase(lv, e, Always(), 1.0)
        self.assertIn(th, lv.actors)
        self.assertIsNone(th.fleeing)
        self.assertIsNone(guard.chase)

    def test_new_thieves_turn_up_each_day(self):
        e, lv, th, victim, guard = self.scene()
        lv.actors.remove(th)
        victim.haunts = [("wandering", [(30, 10)], "any")]
        e.minutes += 1440
        citylife.restock(lv, e, Always())
        self.assertEqual(sum(a.kind == "thief" for a in lv.actors), 1)

    def test_chasers_and_runners_dont_wander(self):
        e, lv, th, victim, guard = self.scene()
        citylife.alarm(lv, e, th, victim, Always())
        lv.sim_minutes = e.minutes
        people.advance(lv, e.minutes + 1, e)
        self.assertEqual(guard.doing, "chasing a thief")
        self.assertEqual(th.doing, "running from the guards")
        self.assertFalse(e.at_work(guard))


class DungeonTests(unittest.TestCase):
    def test_down_to_the_dungeon_and_back(self):
        c = city()
        px, py = landmarks.keep_part(c)
        e = Engine(world(), Player(c.x + px, c.y + py))
        e.enter_region()
        stairs = next(pos for pos, key in e.level.exits.items() if key[0] == "dungeon")
        e.lx, e.ly = stairs
        self.assertTrue(e.use_stairs())
        d = e.level
        self.assertEqual(d.name, f"The dungeon under {c.name}")
        self.assertIn("climb down to the dungeon", e.messages[-1])
        self.assertEqual([a.kind for a in d.actors].count("gaoler"), 1)
        self.assertGreaterEqual([a.kind for a in d.actors].count("prisoner"), 3)
        self.assertTrue((d.tiles == T.BARS).any())
        self.assertTrue(e.use_stairs())
        self.assertEqual((e.lx, e.ly), stairs)


class ShopTests(unittest.TestCase):
    def test_merchants_and_the_alchemist_trade(self):
        e = engine_on(field())
        e.player.inventory.add("tin whistle")
        e.player.inventory.add("black candle")
        m = shops.for_actor(Actor("merchant", "Ida Kemp", 0, 0), e)
        self.assertEqual(len(m.deals), 6)
        m.switch("sell")
        self.assertTrue(any("tin whistle" in label for label in m.labels()))
        a = shops.for_actor(Actor("alchemist", "Oren Vane", 0, 0), e)
        self.assertTrue(any("grave dust" in label for label in a.labels()))
        a.switch("sell")
        self.assertTrue(any("black candle" in label for label in a.labels()))


if __name__ == "__main__":
    unittest.main()


class GuardhouseTests(unittest.TestCase):
    def test_the_guardhouse_has_a_floor_above_and_a_lockup_below(self):
        from game.localgen import make_level
        for lv in parts().values():
            house = next(b for b in lv.buildings if b.kind == "guardhouse")
            ways = {k[0]: k for pos, k in lv.exits.items() if house.contains(*pos)}
            self.assertEqual(set(ways), {"guard_up", "guard_cells"})
            up, down = make_level(world(), ways["guard_up"]), make_level(world(), ways["guard_cells"])
            self.assertEqual(up.tiles.shape, (house.w, house.h))         # drawn right over the house
            self.assertIn("sergeant", kinds(up))
            self.assertTrue((up.tiles == T.RACK).any() and (up.tiles == T.BED).any())
            self.assertIn("gaoler", kinds(down))
            self.assertTrue(down.underground and (down.tiles == T.BARS).any())
            for floor in (up, down):                                      # and the stairs lead back
                self.assertIn(("region", *lv.region), floor.exits.values())

    def test_every_watchman_has_a_bunk_shared_only_across_the_watches(self):
        for lv in parts().values():
            house = next(b for b in lv.buildings if b.kind == "guardhouse")
            bunks = {c for c in house.floor(lv.tiles) if lv.tiles[c] == T.BED}
            watch = [a for a in lv.actors if a.kind == "guard" and len(a.home) == 1 and tuple(a.home[0]) in bunks]
            self.assertTrue(watch)
            sharing = {}
            for a in watch:
                sharing.setdefault(tuple(a.home[0]), []).append(a.shift is not None)
            for night in sharing.values():
                self.assertLessEqual(len(night), 2)
                if len(night) == 2:
                    self.assertEqual(sorted(night), [False, True])       # one sleeps while the other's out
