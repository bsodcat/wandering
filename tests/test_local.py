"""Roads and settlements on the overworld, local maps, structures, and moving between them."""
import functools
import unittest
from collections import deque

import numpy as np
from tcod.event import KeySym, Modifier

from game import biomes as B
from game import structures as S
from game import tiles as T
from game.engine import LANTERN, Engine
from game.localgen import LOCAL_H, LOCAL_W, MARGIN, draw_waterways, generate_region, make_level, terrain
from game.worldgen import generate, travel_cost


@functools.lru_cache(maxsize=None)
def world(seed=1):
    return generate(seed)


@functools.lru_cache(maxsize=None)
def level(seed, key):
    return make_level(world(seed), key)


def sites(kind, seeds=(1, 2, 3)):
    return [(seed, s) for seed in seeds for s in world(seed).sites if s.kind == kind]


def reach(tiles, start):
    """Every tile you can walk to from start."""
    walk = T.WALK[tiles]
    seen, todo = {start}, deque([start])
    while todo:
        x, y = todo.popleft()
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                n = (x + dx, y + dy)
                if 0 <= n[0] < tiles.shape[0] and 0 <= n[1] < tiles.shape[1] and walk[n] and n not in seen:
                    seen.add(n)
                    todo.append(n)
    return seen


def land_reachable(w, a, b):
    import tcod
    f = tcod.path.Pathfinder(tcod.path.SimpleGraph(cost=travel_cost(w.biome, w.river), cardinal=10, diagonal=14))
    f.add_root((a.x, a.y))
    f.resolve()
    return f.distance[b.x, b.y] < np.iinfo(np.int32).max


def touches_road(w, site, width=None):
    return any((site.x, site.y) in key and (width is None or v == width) for key, v in w.road_edges.items())


class SettlementPlanTests(unittest.TestCase):
    def test_towns_you_can_walk_between_are_joined_by_highway(self):
        for seed in (1, 2, 3):
            w = world(seed)
            graph = {}
            for (a, b), width in w.road_edges.items():
                if width == 2:
                    graph.setdefault(a, set()).add(b)
                    graph.setdefault(b, set()).add(a)
            towns = [s for s in w.sites if s.kind == "town"]
            for a in towns:
                seen, todo = {(a.x, a.y)}, [(a.x, a.y)]
                while todo:
                    for n in graph.get(todo.pop(), ()):
                        if n not in seen:
                            seen.add(n)
                            todo.append(n)
                for b in towns:
                    if b is not a and land_reachable(w, a, b):
                        self.assertIn((b.x, b.y), seen, (seed, a.name, b.name))

    def test_most_villages_have_a_way_out(self):
        for seed in (1, 2, 3):
            w = world(seed)
            villages = [s for s in w.sites if s.kind == "village"]
            self.assertGreater(sum(touches_road(w, v) for v in villages), len(villages) * 0.7, seed)

    def test_inns_stand_on_highways(self):
        inns = sites("inn")
        self.assertTrue(inns)
        for seed, inn in inns:
            self.assertTrue(touches_road(world(seed), inn, 2), inn)

    def test_towers_overlook_roads_from_high_ground(self):
        towers = sites("tower")
        self.assertTrue(towers)
        for seed, t in towers:
            w = world(seed)
            self.assertIn(w.biome[t.x, t.y], (B.HILLS, B.MOUNTAINS))
            near = w.road[max(0, t.x - 4): t.x + 5, max(0, t.y - 4): t.y + 5].any() or touches_road(w, t)
            self.assertTrue(near, t)

    def test_ports_are_on_the_sea(self):
        ports = [(seed, s) for seed in (1, 2, 3) for s in world(seed).sites if s.port]
        self.assertTrue(ports)
        for seed, s in ports:
            w = world(seed)
            around = w.biome[s.x - 1: s.x + 2, s.y - 1: s.y + 2]
            self.assertTrue(np.isin(around, [B.OCEAN, B.DEEP_OCEAN]).any())

    def test_road_edges_join_neighbouring_cells(self):
        for (a, b), width in world(1).road_edges.items():
            self.assertEqual(max(abs(a[0] - b[0]), abs(a[1] - b[1])), 1)
            self.assertIn(width, (1, 2))


class LocalTerrainTests(unittest.TestCase):
    def test_same_region_same_map(self):
        w = world(1)
        town = next(s for s in w.sites if s.kind == "town")
        a, b = generate_region(w, town.x, town.y), generate_region(w, town.x, town.y)
        self.assertTrue(np.array_equal(a.tiles, b.tiles))
        self.assertEqual(a.tiles.shape, (LOCAL_W, LOCAL_H))

    def test_neighbouring_regions_join_without_a_seam(self):
        w = world(1)
        # a pair of land regions side by side with a river or road and no sites
        for x, y in np.argwhere((w.river | w.road) & (B.TRAVEL[w.biome] > 0)):
            x, y = int(x), int(y)
            if (x, y) not in w.site_at and (x + 1, y) not in w.site_at and w.walkable(x + 1, y):
                break
        gx0, gy0 = x * LOCAL_W - MARGIN, y * LOCAL_H - MARGIN
        big, _ = terrain(w, gx0, gy0, 2 * LOCAL_W + 2 * MARGIN, LOCAL_H + 2 * MARGIN)
        draw_waterways(w, big, gx0, gy0)
        big = big[MARGIN: MARGIN + 2 * LOCAL_W, MARGIN: MARGIN + LOCAL_H]
        left, right = generate_region(w, x, y), generate_region(w, x + 1, y)
        self.assertTrue(np.array_equal(left.tiles, big[:LOCAL_W]))
        self.assertTrue(np.array_equal(right.tiles, big[LOCAL_W:]))

    def test_rivers_and_roads_show_up(self):
        w = world(1)
        x, y = (int(v) for v in np.argwhere(w.river & ~w.road)[5])
        if (x, y) not in w.site_at:
            self.assertTrue(T.WATERY[generate_region(w, x, y).tiles].any())
        x, y = (int(v) for v in np.argwhere(w.road)[5])
        tiles = generate_region(w, x, y).tiles
        self.assertTrue(np.isin(tiles, [T.ROAD, T.BRIDGE]).any())

    def test_biomes_look_like_themselves(self):
        w = world(1)
        def share(biome, wanted):
            x, y = (int(v) for v in np.argwhere(w.biome == biome)[len(np.argwhere(w.biome == biome)) // 2])
            return np.isin(generate_region(w, x, y).tiles, wanted).mean()
        self.assertGreater(share(B.FOREST, [T.TREE]), 0.05)
        self.assertGreater(share(B.DESERT, [T.SAND]), 0.4)
        self.assertGreater(share(B.DEEP_OCEAN, [T.DEEP_WATER]), 0.5)


class StructureTests(unittest.TestCase):
    def check_doors_reachable(self, seed, site, least):
        lvl = level(seed, ("region", site.x, site.y))
        doors = list(zip(*np.nonzero(lvl.tiles == T.DOOR)))
        self.assertGreaterEqual(len(doors), least, site)
        start = lvl.nearest_walkable(LOCAL_W // 2, LOCAL_H // 2 + 1)
        reachable = reach(lvl.tiles, start)
        self.assertGreater(sum(d in reachable for d in doors), len(doors) * 0.8, site)
        return lvl

    def test_towns(self):
        for seed, town in sites("town", (1,))[:4]:
            lvl = self.check_doors_reachable(seed, town, 8)
            t = lvl.tiles
            for tile in (T.STREET, T.BED, T.HEARTH, T.CROPS, T.FENCE):
                self.assertTrue((t == tile).any(), (town.name, T.TILES[tile].name))

    def test_villages(self):
        for seed, v in sites("village", (1,))[:4]:
            lvl = self.check_doors_reachable(seed, v, 3)
            self.assertTrue(np.isin(lvl.tiles, T.FIELDS).any())

    def test_inns(self):
        for seed, inn in sites("inn")[:3]:
            lvl = self.check_doors_reachable(seed, inn, 1)
            b = next(b for b in lvl.buildings if b.kind == "inn")
            self.assertFalse(any(lvl.tiles[c] == T.BED for c in b.floor(lvl.tiles)), inn)   # beds are upstairs
            up = make_level(world(seed), ("inn_up", inn.x, inn.y, 1))
            self.assertGreaterEqual((up.tiles == T.BED).sum(), 3)

    def test_chests_in_homes_shops_caves_and_crypts(self):
        seed, s = sites("town", (1,))[0]
        town = level(seed, ("region", s.x, s.y))
        homes = [b for b in town.buildings if b.kind in ("house", "bakery", "butcher", "armoury")]
        with_chest = [b for b in homes if any(town.tiles[x, y] == T.CHEST for x in range(b.x0, b.x0 + b.w)
                                              for y in range(b.y0, b.y0 + b.h))]
        self.assertGreater(len(with_chest), len(homes) // 2)
        for kind, sub in (("cave", "cave"), ("ruins", "crypt")):
            seed, s = sites(kind)[0]
            lvl = make_level(world(seed), (sub, s.x, s.y, 1))
            self.assertTrue((lvl.tiles == T.CHEST).any(), kind)
            walk = T.WALK[lvl.tiles]
            self.assertEqual(S.largest_area(walk).sum(), walk.sum(), kind)   # nothing cut off

    def test_no_room_is_shut_off_from_its_door(self):
        for seed, s in sites("town", (1, 2))[:4] + sites("village", (1, 2))[:4] + sites("inn", (1, 2))[:3]:
            lvl = level(seed, ("region", s.x, s.y))
            for b in lvl.buildings:
                self.assertTrue(S.all_reachable(lvl.tiles, b.x0, b.y0, b.x0 + b.w - 1, b.y0 + b.h - 1),
                                (s.name, b.kind))

    def test_ports_get_docks(self):
        ports = [(seed, s) for seed in (1, 2, 3) for s in world(seed).sites if s.port]
        with_docks = sum((level(seed, ("region", s.x, s.y)).tiles == T.DOCK).any() for seed, s in ports)
        self.assertGreater(with_docks, len(ports) * 0.6)

    def test_nothing_built_at_the_edges(self):
        for seed, s in sites("town", (1,))[:3] + sites("ruins", (1,))[:3]:
            lvl = level(seed, ("region", s.x, s.y))
            fresh = generate_region(world(seed), s.x, s.y).tiles   # sanity: same either way
            self.assertTrue(np.array_equal(lvl.tiles, fresh))
            edge = np.ones(lvl.tiles.shape, bool)
            edge[S.EDGE - 1: -S.EDGE + 1, S.EDGE - 1: -S.EDGE + 1] = False
            built = np.isin(lvl.tiles, [T.WALL, T.STONE_WALL, T.DOOR, T.FENCE, T.WOOD_FLOOR])
            self.assertFalse((built & edge).any(), s)


class LevelLinkTests(unittest.TestCase):
    def follow(self, seed, site, kind):
        """Walks every linked level below or above a site: each has a way back to the one it
        came from, and the stairs at both ends are reachable from each other."""
        key = ("region", site.x, site.y)
        lvl = level(seed, key)
        down = [k for k in lvl.exits.values() if k[0] == kind]
        self.assertTrue(down, site)
        count = 0
        prev, key = key, down[0]
        while key is not None:
            lvl = level(seed, key)
            arrive = lvl.arrival(prev)
            self.assertIsNotNone(arrive, key)
            onward = [(pos, k) for pos, k in lvl.exits.items() if k[0] == kind and k[3] == key[3] + 1]
            if onward:
                self.assertIn(onward[0][0], reach(lvl.tiles, arrive))
            count += 1
            prev, key = key, (onward[0][1] if onward else None)
        return count, lvl

    def test_caves_go_down_and_back(self):
        for seed, cave in sites("cave", (1,))[:4]:
            depth, bottom = self.follow(seed, cave, "cave")
            self.assertEqual(depth, S.cave_depth(cave.name))
            self.assertTrue(bottom.underground)

    def test_ruins_hide_a_crypt(self):
        for seed, ruins in sites("ruins", (1,))[:4]:
            depth, crypt = self.follow(seed, ruins, "crypt")
            self.assertEqual(depth, 1)

    def test_towers_climb_to_a_lookout(self):
        for seed, tower in sites("tower")[:3]:
            floors, roof = self.follow(seed, tower, "tower")
            self.assertEqual(floors, S.TOWER_FLOORS)
            self.assertTrue(roof.lookout)


def shift():
    return Modifier.LSHIFT


class SwitchingTests(unittest.TestCase):
    def test_enter_and_leave_a_region(self):
        e = Engine.new(1)
        e.handle_key(KeySym.RETURN)
        self.assertIsNotNone(e.level)
        self.assertEqual(e.level.key, ("region", e.player.x, e.player.y))
        self.assertTrue(e.level.walkable(e.lx, e.ly))
        e.handle_key(KeySym.COMMA, shift())          # <
        self.assertIsNone(e.level)

    def test_steps_take_minutes_not_hours(self):
        e = Engine.new(1)
        e.enter_region()
        start = e.minutes
        for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1)] * 3:
            e.move_local(dx, dy)
        self.assertLess(e.minutes - start, 60)          # minutes (shallow water is slow), not hours
        self.assertGreater(e.minutes, start)

    def test_walking_off_the_edge_enters_the_next_region(self):
        e = Engine.new(1)
        e.enter_region()
        x0 = e.player.x
        lvl = e.level
        # stand at the east edge on a walkable tile whose neighbour across the border is walkable too
        nxt = e.get_level(("region", x0 + 1, e.player.y))
        rows = [y for y in range(lvl.height) if lvl.walkable(lvl.width - 1, y) and nxt.walkable(0, y)]
        self.assertTrue(rows)
        e.lx, e.ly = lvl.width - 1, rows[0]
        self.assertTrue(e.move_local(1, 0))
        self.assertEqual(e.player.x, x0 + 1)
        self.assertEqual((e.lx, e.ly), (0, rows[0]))
        self.assertIs(e.level, nxt)
        e.move_local(-1, 0)
        self.assertEqual(e.player.x, x0)
        self.assertIs(e.level, lvl)        # the same map, kept with what you explored

    def test_stairs_down_and_back_up(self):
        e = Engine.new(1)
        cave = next(s for s in e.world.sites if s.kind == "cave")
        e.player.x, e.player.y = cave.x, cave.y
        e.enter_region()
        mouth = next(pos for pos, k in e.level.exits.items() if k[0] == "cave")
        e.lx, e.ly = mouth
        e.handle_key(KeySym.PERIOD, shift())         # >
        self.assertTrue(e.underground)
        self.assertEqual(e.level.key, ("cave", cave.x, cave.y, 1))
        self.assertEqual(e.tile.id, T.STAIRS_UP)
        self.assertEqual(e.sight_radius(), LANTERN)
        e.handle_key(KeySym.COMMA, shift())          # <
        self.assertEqual(e.level.key, ("region", cave.x, cave.y))
        self.assertEqual((e.lx, e.ly), mouth)

    def test_you_cant_leave_for_the_map_from_underground(self):
        e = Engine.new(1)
        cave = next(s for s in e.world.sites if s.kind == "cave")
        e.player.x, e.player.y = cave.x, cave.y
        e.enter_region()
        e.lx, e.ly = next(pos for pos, k in e.level.exits.items() if k[0] == "cave")
        e.use_stairs("down")
        e.lx, e.ly = e.level.nearest_walkable(0, 0)
        e.handle_key(KeySym.COMMA, shift())
        self.assertTrue(e.underground)

    def test_caves_keep_out_the_weather(self):
        e = Engine.new(1)
        cave = next(s for s in e.world.sites if s.kind == "cave")
        e.player.x, e.player.y = cave.x, cave.y
        e.enter_region()
        e.lx, e.ly = next(pos for pos, k in e.level.exits.items() if k[0] == "cave")
        e.use_stairs("down")
        e.player.wet = 80
        e.wait(10)
        self.assertTrue(e.indoors)
        self.assertEqual(e.shelter, 1.0)
        self.assertLess(e.player.wet, 80)

    def test_the_tower_roof_shows_the_land_around(self):
        e = Engine.new(1)
        tower = next(s for s in e.world.sites if s.kind == "tower")
        e.player.x, e.player.y = tower.x, tower.y
        e.enter_region()
        e.lx, e.ly = next(pos for pos, k in e.level.exits.items() if k[0] == "tower")
        before = e.explored.sum()
        e.use_stairs("up")
        e.lx, e.ly = next(pos for pos, k in e.level.exits.items() if k[0] == "tower" and k[3] == 2)
        e.use_stairs("up")
        self.assertTrue(e.level.lookout)
        self.assertGreater(e.explored.sum(), before)
        self.assertTrue(e.explored[tower.x + 8, tower.y] or not e.world.in_bounds(tower.x + 8, tower.y))

    def test_walking_into_a_house_is_indoors(self):
        e = Engine.new(1)
        e.enter_region()
        door = tuple(int(v) for v in np.argwhere(e.level.tiles == T.DOOR)[0])
        e.lx, e.ly = door
        self.assertTrue(e.indoors)
        self.assertGreaterEqual(e.indoor_air, 16)

    def test_bumping_repeats_are_counted_not_listed(self):
        e = Engine.new(1)
        e.say("The wall is in the way.")
        e.say("The wall is in the way.")
        e.say("The wall is in the way.")
        self.assertEqual(e.messages.count("The wall is in the way."), 1)
        self.assertEqual(e.repeats, 3)


if __name__ == "__main__":
    unittest.main()
