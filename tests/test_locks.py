"""Locks: locked doors and chests, lockpicks, and the lock-picking game."""
import random
import unittest

import numpy as np
from tcod.event import KeySym

from game import locks
from game import tiles as T
from game.level import Building, Level

from tests.test_wild import engine_on


def house_level():
    """A field with a little house whose door (and chest) are locked."""
    t = np.full((40, 20), T.GRASS, np.uint8)
    t[10:17, 5:11] = T.WALL
    t[11:16, 6:10] = T.WOOD_FLOOR
    t[13, 10] = T.DOOR
    t[12, 7] = T.CHEST
    lv = Level(("region", 0, 0), "a test field", t)
    lv.buildings.append(Building("house", "a house", 10, 5, 7, 6, (13, 10)))
    return lv


class Locked:
    """Forces every door and chest locked at a given difficulty (the real roll is random per spot)."""

    def __init__(self, level=1):
        self.level = level

    def __enter__(self):
        self.real = locks.difficulty
        lvl = self.level
        locks.difficulty = lambda level, x, y: 0 if (x, y) in level.unlocked or \
            int(level.tiles[x, y]) not in (T.DOOR, T.CHEST) else lvl
        return self

    def __exit__(self, *exc):
        locks.difficulty = self.real


class LockTests(unittest.TestCase):
    def test_locks_are_the_same_every_game_and_only_on_doors_and_chests(self):
        lv = house_level()
        self.assertEqual([locks.difficulty(lv, 13, 10) for _ in range(3)], [locks.difficulty(lv, 13, 10)] * 3)
        self.assertEqual(locks.difficulty(lv, 2, 2), 0)
        self.assertIn(locks.difficulty(lv, 12, 7), (0, 1, 2, 3))

    def test_a_locked_door_stops_you_and_walks_go_round_it(self):
        with Locked():
            e = engine_on(house_level(), at=(13, 11))
            self.assertFalse(e.move_local(0, -1))
            self.assertEqual((e.lx, e.ly), (13, 11))
            self.assertIn("locked", e.messages[-1])
            self.assertEqual(e.route(13, 8), [])                     # no way in but the door

    def test_from_inside_you_unbar_it(self):
        with Locked():
            e = engine_on(house_level(), at=(13, 9))
            self.assertTrue(e.move_local(0, 1))
            self.assertIn((13, 10), e.level.unlocked)

    def test_no_lockpick_no_picking(self):
        with Locked():
            e = engine_on(house_level(), at=(12, 8))
            e.open_barrel(12, 7)
            self.assertIsNone(e.shop)
            self.assertIn("no lockpick", e.messages[-1])

    def test_picking_in_the_right_order_opens_the_chest(self):
        with Locked(1):
            e = engine_on(house_level(), at=(12, 8))
            e.player.inventory.add(locks.PICK, 3)
            e.open_barrel(12, 7)
            game = e.shop
            self.assertIsInstance(game, locks.LockPick)
            self.assertEqual(len(game.labels()), locks.PINS[1])
            for pin in game.order:
                game.cursor = pin
                e.handle_key(KeySym.RETURN)
            self.assertIn((12, 7), e.level.unlocked)
            self.assertEqual(type(e.shop).__name__, "Container")    # and it opens
            self.assertEqual(e.player.inventory.count(locks.PICK), 3)

    def test_springy_pins_can_snap_the_pick_and_oversetting_drops_them(self):
        with Locked(3):
            e = engine_on(house_level(), at=(13, 11))
            e.player.inventory.add(locks.PICK, 1)
            locks.pick(e, 13, 10)
            game = e.shop
            game.cursor = game.order[0]
            game.act(e)
            self.assertEqual(game.done, [game.order[0]])
            game.act(e)                                             # the same pin again: too far
            self.assertEqual(game.done, [])
            game.rng = random.Random()
            game.rng.random = lambda: 0.0                           # this push snaps it
            game.cursor = game.order[1]
            self.assertFalse(game.act(e))
            self.assertEqual(e.player.inventory.count(locks.PICK), 0)
            self.assertNotIn((13, 10), e.level.unlocked)

    def test_lockpicks_are_sold(self):
        from game import combat, shop
        self.assertIn(locks.PICK, combat.WARES)
        self.assertIn(locks.PICK, shop.SMITH_WARES)


class ClickedActionTests(unittest.TestCase):
    """Things done from a click menu that answer True/False instead of words don't break the log."""

    def test_clicking_the_inn_stairs_up_goes_up_and_the_log_still_draws(self):
        import tcod
        import main
        from game import render
        from game.engine import Engine
        e = Engine.new(1)
        s = next(s for s in e.world.sites if s.kind == "inn")
        e.player.x, e.player.y = s.x, s.y
        e.enter_region()
        up = next(p for p, k in e.level.exits.items() if k[0] == "inn_up")
        for start in (up, e.level.building_at(*up).door):            # right there, and across the room
            e.level = None
            e.enter_region()
            e.lx, e.ly = start
            e.update_view()
            e.click_at(*up)
            e.shop.cursor = next(i for i, o in enumerate(e.shop.options) if o.label == "Take the stairs up")
            e.shop.act(e)
            e.shop = None
            for _ in range(60):
                if e.pending is None and not e.autopath:
                    break
                main.walk(e)
            self.assertEqual(e.level.key[0], "inn_up")
            self.assertTrue(all(isinstance(m, str) for m in e.messages))
            render.draw(tcod.console.Console(120, 45, order="F"), e, 0.0)
