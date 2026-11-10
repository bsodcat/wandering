"""Wolves, small game, bats and goblins; fighting, wolf fever and soup; the shopkeeper,
trinkets, barrels and the use menu."""
import collections
import random
import unittest

import numpy as np
from tcod.event import KeySym

from game import combat, items, people, shop as shops, sickness, structures, wild
from game import biomes as B
from game import tiles as T
from game.climate import MINUTES_PER_DAY, MINUTES_PER_HOUR
from game.engine import Engine
from game.level import Level
from game.localgen import make_level
from game.player import Player
from game.worldgen import generate

WORLD = None


def world():
    global WORLD
    if WORLD is None:
        WORLD = generate(1)
    return WORLD


def field(w=60, h=30, tile=T.GRASS) -> Level:
    return Level(("region", 0, 0), "a test field", np.full((w, h), tile, np.uint8))


def engine_on(level, at=(30, 15), hour=12) -> Engine:
    """An engine standing on a test level, at noon on a fair day."""
    w = world()
    s = next(s for s in w.sites if s.kind == "town")
    e = Engine(w, Player(s.x, s.y))
    e.fair = True
    e.minutes = 40 * MINUTES_PER_DAY + hour * MINUTES_PER_HOUR
    e.levels[level.key] = level
    e.level = level
    e.lx, e.ly = at
    level.explored[:] = True
    level.wild_minutes = e.minutes
    e.update_view()
    return e


def tick(e, minutes=0.5, n=1):
    for _ in range(n):
        e.pass_time(minutes / 60)


class WolfTests(unittest.TestCase):
    def test_wolves_live_in_packs_in_the_woods(self):
        w = world()
        sizes = collections.Counter()
        cells = np.argwhere(np.isin(w.biome, [B.FOREST, B.TAIGA]))
        for x, y in cells[:: max(1, len(cells) // 30)][:30]:
            if (int(x), int(y)) in w.site_at:
                continue
            lv = make_level(w, ("region", int(x), int(y)))
            for n in collections.Counter(c.pack for c in lv.creatures if c.kind == "wolf").values():
                sizes[n] += 1
        self.assertTrue(sizes, "no wolves in the woods at all")
        self.assertGreater(sum(n for s, n in sizes.items() if s >= 2), sizes[1])    # rarely alone
        self.assertTrue(all(2 <= s <= 5 or s == 1 for s in sizes))

    def test_no_wolves_in_settlements(self):
        w = world()
        for s in [s for s in w.sites if s.settled][:4]:
            lv = make_level(w, ("region", s.x, s.y))
            self.assertFalse([c for c in lv.creatures if c.kind == "wolf"])

    def test_caves_often_have_a_wolf_den(self):
        w = world()
        caves = [s for s in w.sites if s.kind == "cave"]
        dens = [s for s in caves if wild.cave_folk(s.name) == "wolves"]
        self.assertGreater(len(dens), len(caves) // 4)
        lv = make_level(w, ("cave", dens[0].x, dens[0].y, 1))
        self.assertGreaterEqual(sum(c.kind == "wolf" for c in lv.creatures), 3)

    def test_a_hungry_pack_hunts_small_game(self):
        lv = field()
        rng = random.Random(1)
        taken = set()
        pack = wild.add_pack(lv, rng, (20, 15), 20, taken, size=3)
        for c in pack:
            c.hunger = 80
        wild.add_game(lv, rng, "rabbit", 4, (40, 15), 6, taken)
        lv.wild_minutes = 0.0
        for m in range(1, 480):
            wild.advance(lv, m * 0.5, None, rng)
        self.assertLess(sum(c.kind == "rabbit" for c in lv.creatures), 4)
        self.assertTrue(any(c.hunger < 80 for c in pack))

    def test_fed_wolves_leave_you_be(self):
        lv = field()
        e = engine_on(lv)
        for c in wild.add_pack(lv, random.Random(1), (24, 15), 10, set(), size=3):
            c.hunger = 10
        tick(e, n=40)
        self.assertEqual(e.player.health, 100)
        self.assertFalse([c for c in lv.creatures if c.target == wild.YOU])

    def test_a_ravenous_pack_stalks_then_attacks(self):
        lv = field()
        e = engine_on(lv)
        for c in wild.add_pack(lv, random.Random(1), (22, 15), 10, set(), size=3):
            c.hunger = 95
        seen = set()
        for _ in range(60):
            tick(e)
            seen |= {c.state for c in lv.creatures}
        self.assertIn("stalk", seen)
        self.assertLess(e.player.health, 100)

    def test_a_lone_wolf_wont_take_you_on(self):
        lv = field()
        e = engine_on(lv)
        w = wild.add_pack(lv, random.Random(1), (26, 15), 10, set(), size=1)[0]
        w.hunger = 100
        tick(e, n=40)
        self.assertEqual(e.player.health, 100)
        self.assertGreater(wild.dist(w, (e.lx, e.ly)), 1)

    def test_a_hurt_wolf_flees_and_limps(self):
        lv = field()
        e = engine_on(lv)
        pack = wild.add_pack(lv, random.Random(1), (27, 15), 10, set(), size=3)
        hurt = pack[0]
        hurt.hp = 5
        tick(e)
        self.assertEqual(hurt.state, "flee")
        w = wild.Wilds(lv, e, random.Random(1), e.minutes)
        start = (hurt.x, hurt.y)
        healthy = wild.Creature("wolf", 5, 5, home=(5, 5))
        self.assertGreater(w.move(hurt, start, wild.LIMP), w.move(healthy, (5, 5)))

    def test_outnumbered_wolves_back_off(self):
        lv = field()
        e = engine_on(lv)
        p = e.player
        for k in ("spear", "mail shirt"):
            p.inventory.add(k)
        combat.wield(p, "spear")
        combat.wear(p, "mail shirt")
        self.assertEqual(combat.threat(p), 2.0)
        pack = wild.add_pack(lv, random.Random(1), (27, 15), 10, set(), size=2)
        (pack[0].x, pack[0].y), (pack[1].x, pack[1].y) = (27, 15), (27, 16)
        pack[1].hp = 7                      # one of the two is hurt, so the other stands alone
        tick(e, n=6)
        self.assertTrue(all(c.state == "flee" for c in pack))

    def test_wolves_follow_a_scent(self):
        lv = field()
        rng = random.Random(1)
        w = wild.Creature("wolf", 10, 15, home=(10, 15), hunger=60)
        lv.creatures.append(w)
        for x in range(11, 30):                     # something went east, a minute a tile
            lv.scent[x, 15] = 100.0 + x
        lv.wild_minutes = 140.0
        wild.advance(lv, 150.0, None, rng)
        self.assertGreater(w.x, 12)

    def test_wolves_lose_interest_and_go_home(self):
        lv = field()
        w = wild.Creature("wolf", 50, 15, home=(10, 15), reach=12, state="track", bored=wild.BORED + 1)
        lv.creatures.append(w)
        lv.wild_minutes = 0.0
        rng = random.Random(1)
        for m in range(1, 200):
            wild.advance(lv, m * 0.5, None, rng)
        self.assertLessEqual(wild.dist(w, (10, 15)), 14)

    def test_wolves_wear_trails(self):
        lv = field()
        rng = random.Random(1)
        wild.add_pack(lv, rng, (30, 15), 15, set(), size=3)
        lv.wild_minutes = 0.0
        for m in range(1, 200):
            wild.advance(lv, m * 0.5, None, rng)
        self.assertGreater(int(lv.trail.sum()), 10)


class SmallGameTests(unittest.TestCase):
    def test_squirrels_run_up_trees(self):
        lv = field()
        lv.tiles[31, 15] = T.TREE
        e = engine_on(lv, at=(27, 15))
        sq = wild.Creature("squirrel", 30, 15, home=(30, 15))
        lv.creatures.append(sq)
        tick(e)
        self.assertEqual((sq.x, sq.y), (31, 15))
        self.assertEqual(sq.state, "up")

    def test_birds_fly_over_water(self):
        lv = field(tile=T.DEEP_WATER)
        lv.tiles[:3] = T.GRASS
        w = wild.Wilds(lv, None, random.Random(1), 0.0)
        bird = wild.Creature("bird", 30, 15)
        rabbit = wild.Creature("rabbit", 30, 15)
        self.assertTrue(w.can_stand(bird, 31, 15))
        self.assertFalse(w.can_stand(rabbit, 31, 15))


class BatTests(unittest.TestCase):
    def roost(self):
        lv = field(tile=T.CAVE_FLOOR)
        lv.underground = True
        bats = [wild.Creature("bat", 40 + i % 3, 15 + i // 3, home=(41, 15), asleep=True, pack=1000)
                for i in range(5)]
        lv.creatures += bats
        return lv, bats

    def test_bats_sleep_until_you_come_near(self):
        lv, bats = self.roost()
        e = engine_on(lv, at=(20, 15))
        tick(e, n=5)
        self.assertTrue(all(b.asleep for b in bats))
        e.lx = 38
        e.update_view()
        tick(e, n=3)
        self.assertFalse(any(b.asleep for b in bats))
        self.assertTrue(any("Bats burst" in m for m in e.messages))

    def test_bats_keep_away_then_swarm_when_hurt(self):
        lv, bats = self.roost()
        e = engine_on(lv, at=(38, 15))
        tick(e, n=6)
        self.assertTrue(all(wild.dist(b, (e.lx, e.ly)) >= 2 for b in bats))
        bat = min(bats, key=lambda b: wild.dist(b, (e.lx, e.ly)))
        wild.player_attack(lv, e, bat, random.Random(5))        # its roost-mates take note
        tick(e, n=3)
        self.assertTrue(any(b.state == "swarm" for b in bats))

    def test_bats_settle_back_down(self):
        lv, bats = self.roost()
        e = engine_on(lv, at=(38, 15))
        tick(e, n=2)
        e.lx = 3
        tick(e, n=150)
        self.assertGreaterEqual(sum(b.asleep for b in bats), 3)


class GoblinTests(unittest.TestCase):
    def cave(self):
        w = world()
        s = next(s for s in w.sites if s.kind == "cave" and wild.cave_folk(s.name) == "goblins")
        return w, s

    def test_goblins_guard_the_way_in_and_camp_deep_down(self):
        w, s = self.cave()
        top = make_level(w, ("cave", s.x, s.y, 1))
        up = next(p for p in top.exits if top.tiles[p] == T.STAIRS_UP)
        guards = [c for c in top.creatures if c.role == "guard"]
        self.assertEqual(len(guards), 2)
        self.assertTrue(all(wild.dist(g, up) <= 3 for g in guards))
        self.assertNotEqual(guards[0].sleep_hour, guards[1].sleep_hour)      # in shifts
        deep = make_level(w, ("cave", s.x, s.y, structures.cave_depth(s.name)))
        self.assertTrue(deep.camp)
        self.assertEqual(deep.tiles[deep.camp["hearth"]], T.HEARTH)
        self.assertTrue(any(deep.tiles[b] == T.BEDROLL for b in deep.camp["beds"]))
        roles = {c.role for c in deep.creatures if c.kind == "goblin"}
        self.assertTrue({"cook", "hunter"} <= roles)

    def camp(self):
        lv = field(tile=T.CAVE_FLOOR)
        lv.underground = True
        lv.tiles[20, 15] = T.HEARTH
        lv.camp = {"hearth": (20, 15), "store": (21, 15), "beds": [(18, 13), (22, 13)], "barrel": None}
        return lv

    def test_hunters_bring_food_home_and_the_cook_roasts_it(self):
        lv = self.camp()
        rng = random.Random(2)
        hunter = wild.Creature("goblin", 22, 16, home=(21, 15), role="hunter", pack=99, sleep_hour=22)
        cook = wild.Creature("goblin", 21, 16, home=(21, 15), role="cook", pack=99, sleep_hour=22)
        lv.creatures += [hunter, cook]
        wild.add_game(lv, rng, "rat", 3, (45, 15), 4, set())
        lv.wild_minutes = 12 * 60.0
        for m in range(1, 900):
            wild.advance(lv, 12 * 60 + m * 0.5, None, rng)
        pile = lv.items.get((21, 15), [])
        self.assertIn("roast meat", pile)
        self.assertLess(sum(c.kind == "rat" for c in lv.creatures), 3)

    def test_goblins_sleep_by_day(self):
        lv = self.camp()
        g = wild.Creature("goblin", 25, 15, home=(21, 15), role="hunter", pack=99, bed=(18, 13), sleep_hour=8)
        lv.creatures.append(g)
        lv.wild_minutes = 0.0
        wild.advance(lv, 10 * 60.0, None, random.Random(1))       # settles: it's ten in the morning
        self.assertTrue(g.asleep)
        self.assertEqual((g.x, g.y), (18, 13))

    def test_goblins_investigate_noises(self):
        lv = self.camp()
        e = engine_on(lv, at=(55, 25))
        g = wild.Creature("goblin", 21, 16, home=(21, 15), role="cook", pack=99, sleep_hour=22)
        lv.creatures.append(g)
        lv.noises.append((30, 16, e.minutes, 12))
        tick(e)
        self.assertEqual(g.state, "investigate")

    def test_they_raise_the_alarm_and_fight(self):
        lv = self.camp()
        e = engine_on(lv, at=(30, 15))
        gang = [wild.Creature("goblin", 25, 14 + i, home=(25, 14 + i), role="guard", pack=99, sleep_hour=22)
                for i in range(3)]
        lv.creatures += gang
        e.rng = random.Random(0)
        tick(e, n=8)
        self.assertTrue(any("alarm" in m for m in e.messages))
        self.assertLess(e.player.health, 100)

    def test_heavily_outnumbered_they_run(self):
        lv = self.camp()
        e = engine_on(lv, at=(30, 15))
        p = e.player
        for k in ("short sword", "mail shirt"):
            p.inventory.add(k)
        combat.wield(p, "short sword")
        combat.wear(p, "mail shirt")
        g = wild.Creature("goblin", 27, 15, home=(27, 15), role="guard", pack=99, sleep_hour=22)
        lv.creatures.append(g)
        tick(e, n=3)
        self.assertEqual(g.state, "flee")

    def test_dead_goblins_drop_what_they_carry(self):
        lv = self.camp()
        e = engine_on(lv, at=(30, 15))
        g = wild.Creature("goblin", 31, 15, home=(31, 15), role="guard", pack=99, sleep_hour=22, hp=1,
                          carry=["coin", "coin", "bone charm"])
        lv.creatures.append(g)
        e.rng = random.Random(0)
        for _ in range(20):
            if g not in lv.creatures:
                break
            if wild.dist(g, (e.lx, e.ly)) <= 1:
                e.attack(g)
            else:
                break
        if g in lv.creatures:
            wild.Wilds(lv, e, random.Random(1), e.minutes).kill(g)
        pile = lv.items.get((g.x, g.y), [])
        self.assertEqual(pile.count("coin"), 2)
        self.assertIn("bone charm", pile)


class FightTests(unittest.TestCase):
    def test_walking_into_a_creature_strikes_it(self):
        lv = field()
        e = engine_on(lv)
        r = wild.Creature("rabbit", 31, 15, home=(31, 15))
        lv.creatures.append(r)
        e.rng = random.Random(1)
        for _ in range(10):
            if r not in lv.creatures or (r.x, r.y) != (31, 15):
                break
            e.move_local(1, 0)
        self.assertEqual((e.lx, e.ly), (30, 15))             # you strike; you don't step
        self.assertTrue(any("rabbit" in m for m in e.messages))

    def test_armour_and_weapons(self):
        p = Player(0, 0)
        self.assertEqual(combat.weapon_of(p)[1], combat.FISTS)
        p.inventory.add("short sword")
        combat.wield(p, "short sword")
        self.assertEqual(combat.weapon_of(p)[0], "short sword")
        p.inventory.add("mail shirt")
        p.inventory.add("iron helm")
        combat.wear(p, "mail shirt")
        combat.wear(p, "iron helm")
        self.assertEqual(combat.protection(p), 4)
        p.inventory.take("mail shirt")                       # sold it: no longer worn
        self.assertEqual(combat.protection(p), 1)

    def test_no_resting_with_wolves_about(self):
        lv = field()
        e = engine_on(lv)
        wild.add_pack(lv, random.Random(1), (35, 15), 5, set(), size=2)
        e.update_view()
        before = e.minutes
        e.rest()
        self.assertEqual(e.minutes, before)
        self.assertIn("can't rest", e.messages[-1])

    def test_a_walk_never_starts_a_fight(self):
        lv = field()
        e = engine_on(lv)
        lv.creatures.append(wild.Creature("wolf", 31, 15, home=(31, 15), hunger=0))
        self.assertFalse(e.step_toward(35, 15) and (e.lx, e.ly) == (31, 15))
        self.assertTrue(all(c.hp == c.beast.hp for c in lv.creatures))


class SicknessTests(unittest.TestCase):
    def test_a_bite_rarely_goes_bad(self):
        rng = random.Random(1)
        caught = 0
        for _ in range(2000):
            p = Player(0, 0)
            caught += sickness.bitten(p, 0, rng)
        self.assertTrue(20 < caught < 110)

    def test_the_fever_comes_on_drains_and_kills_after_a_week(self):
        p = Player(0, 0)
        p.sickness = sickness.Sickness(0.0)
        msgs = []
        t = 0.0
        while p.alive and t < 20 * MINUTES_PER_DAY:
            t += MINUTES_PER_HOUR
            before = p.health
            p.health = min(100.0, p.health + 2)              # the usual healing...
            msgs += sickness.hour(p, t, 1.0, before)          # ...which the fever takes back
            if t == 6 * MINUTES_PER_DAY:
                self.assertTrue(55 < p.health < 75)           # a little lost each day
        self.assertFalse(p.alive)
        self.assertGreater(t, 7 * MINUTES_PER_DAY)
        self.assertLess(t, 12 * MINUTES_PER_DAY)
        self.assertIn("wolf fever", p.cause)
        self.assertTrue(any("feverish" in m for m in msgs))

    def test_soup_then_sleep_cures_it(self):
        lv = field()
        e = engine_on(lv)
        p = e.player
        p.sickness = sickness.Sickness(e.minutes - 2 * MINUTES_PER_DAY, nights_needed=2, shown=True)
        p.health = 60
        self.assertIn("feel better", e.eat_soup())
        tick(e, 60, 3)
        self.assertGreater(p.health, 60)                     # healing again
        self.assertLessEqual(p.health, sickness.TREATED_CAP)
        e.rest()
        self.assertIsNotNone(p.sickness)                     # one day's sleep isn't enough
        e.minutes += MINUTES_PER_DAY
        e.rest()
        self.assertIsNone(p.sickness)
        self.assertTrue(any("fever has broken" in m for m in e.messages))

    def test_the_innkeeper_sells_soup(self):
        a = people.Actor("innkeeper", "Hal Kemp", 0, 0)
        lv = field()
        e = engine_on(lv)
        s = shops.for_actor(a, e)
        self.assertIn("soup", s.labels()[0])
        coins = e.player.inventory.count("coin")
        s.act(e)
        self.assertEqual(e.player.inventory.count("coin"), coins - shops.SOUP_PRICE)


class ShopkeeperTests(unittest.TestCase):
    def test_towns_have_an_armourers_and_a_shopkeeper(self):
        w = world()
        town = next(s for s in w.sites if s.kind == "town")
        lv = make_level(w, ("region", town.x, town.y))
        self.assertTrue(any(b.kind == "armoury" for b in lv.buildings))
        self.assertTrue(any(a.kind == "shopkeeper" for a in lv.actors))
        self.assertTrue((lv.tiles == T.RACK).any())

    def test_sells_weapons_and_armour_and_buys_trinkets(self):
        lv = field()
        e = engine_on(lv)
        a = people.Actor("shopkeeper", "Signe Lowell", 0, 0)
        bag = e.player.inventory
        bag.add("tin whistle", 2)
        s = shops.for_actor(a, e)
        labels = s.labels()
        self.assertTrue(any("spear" in l for l in labels) and any("mail shirt" in l for l in labels))
        s.cursor = next(i for i, l in enumerate(labels) if "tin whistle" in l)
        s.act(e)
        self.assertEqual(bag.count("tin whistle"), 0)
        s.cursor = next(i for i, l in enumerate(s.labels()) if "dagger" in l)
        s.act(e)
        self.assertEqual(bag.count("dagger"), 1)


class TreasureTests(unittest.TestCase):
    def test_trinkets_turn_up_often_but_not_commonly(self):
        rng = random.Random(1)
        finds = [items.treasure(rng)[0] for _ in range(3000)]
        share = sum(k in items.TRINKETS for k in finds) / len(finds)
        self.assertTrue(0.12 < share < 0.35)

    def test_gold_and_silver_only_under_towns(self):
        rng = random.Random(1)
        wild_finds = {items.treasure(rng)[0] for _ in range(3000)}
        town_finds = {items.treasure(rng, town=True)[0] for _ in range(3000)}
        self.assertFalse({"silver ring", "gold ring"} & wild_finds)
        self.assertTrue({"silver ring", "gold ring"} <= town_finds)


class UseMenuTests(unittest.TestCase):
    def test_barrels_hold_things_you_can_take_and_put_back(self):
        lv = field()
        lv.tiles[31, 15] = T.BARREL
        lv.stores[(31, 15)] = items.Inventory(apple=2)
        e = engine_on(lv)
        e.click_at(31, 15)
        self.assertIn("Open the barrel", e.shop.labels())
        e.shop.cursor = e.shop.labels().index("Open the barrel")
        e.handle_key(KeySym.RETURN)
        self.assertEqual(e.shop.title, "A barrel")
        e.shop.cursor = 0                                     # Take 2 apples
        e.handle_key(KeySym.RETURN)
        self.assertEqual(e.player.inventory.count("apple"), 2)
        self.assertFalse(lv.stores[(31, 15)])
        put = next(i for i, l in enumerate(e.shop.labels()) if "apple" in l)
        e.shop.cursor = put
        e.handle_key(KeySym.RETURN)
        self.assertEqual(lv.stores[(31, 15)].count("apple"), 2)

    def test_a_click_far_off_walks_you_over_first(self):
        lv = field()
        lv.tiles[40, 15] = T.BARREL
        e = engine_on(lv)
        e.click_at(40, 15)
        e.handle_key(KeySym.RETURN)
        self.assertIsNotNone(e.pending)
        for _ in range(20):
            if e.try_pending():
                break
            e.step_toward(*e.goal)
        self.assertEqual(e.shop.title, "A barrel")
        self.assertLessEqual(abs(e.lx - 40), 1)

    def test_the_use_menu_has_people_beds_and_your_things(self):
        lv = field()
        lv.tiles[29, 15] = T.BED
        e = engine_on(lv)
        lv.actors.append(people.Actor("baker", "Cora Brook", 31, 15))
        e.player.inventory.add("apple")
        e.player.inventory.add("dagger")
        e.update_view()
        e.handle_key(KeySym.E)
        labels = e.shop.labels()
        self.assertTrue(any(l.startswith("Talk to Cora") for l in labels))
        self.assertTrue(any(l.startswith("Rest on the bed") for l in labels))
        self.assertTrue(any(l.startswith("Eat an apple") for l in labels))
        e.shop.cursor = next(i for i, l in enumerate(labels) if l.startswith("Wield the dagger"))
        e.handle_key(KeySym.RETURN)
        self.assertEqual(e.player.wielding, "dagger")

    def test_eating_restores_stamina(self):
        lv = field()
        e = engine_on(lv)
        e.player.stamina = 50
        e.player.inventory.add("roast meat")
        e.eat("roast meat")
        self.assertGreater(e.player.stamina, 60)


class ArenaTests(unittest.TestCase):
    def test_the_arena_has_the_wilds_and_a_goblin_cave(self):
        e = Engine.arena()
        kinds = collections.Counter(c.kind for c in e.level.creatures)
        for k in wild.BEASTS:
            self.assertIn(k, kinds)
        self.assertTrue(e.level.camp)
        roles = {c.role for c in e.level.creatures if c.kind == "goblin"}
        self.assertEqual(roles, {"guard", "patrol", "hunter", "cook"})


if __name__ == "__main__":
    unittest.main()
