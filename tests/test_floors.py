"""Floors above the ground: the ground shows through around them, seen from a rooftop or
remembered from indoors."""
import unittest

import numpy as np
import tcod

from game import render
from game import tiles as T
from game.engine import Engine
from game.worldgen import generate

WORLD = generate(5)


def upstairs_at_the_inn() -> Engine:
    e = Engine.new(5, WORLD)
    e.enter_region()
    e.lx, e.ly = next(p for p, k in e.level.exits.items() if k[0] == "inn_up")
    e.use_stairs("up")
    return e


def screen(e: Engine) -> tcod.console.Console:
    con = tcod.console.Console(100, 40, order="F")
    render.draw(con, e, 0.0)
    return con


class GroundBelowTests(unittest.TestCase):
    def test_the_inn_rooms_lie_over_the_inn(self):
        e = upstairs_at_the_inn()
        ground, (dx, dy) = e.ground_below()
        self.assertTrue(ground.surface)
        inn = next(b for b in ground.buildings if b.kind == "inn")
        cx, cy = e.level.width // 2 + dx, e.level.height // 2 + dy
        self.assertTrue(inn.contains(cx, cy))
        self.assertIsNone(e.below_visible)                  # indoors: you don't see out

    def test_remembered_ground_shows_around_the_floor_and_fades(self):
        e = upstairs_at_the_inn()
        ground, (dx, dy) = e.ground_below()
        ground.explored[:] = True
        con = tcod.console.Console(100, 40, order="F")
        render.draw_local(con, e, 0.0)                       # the map alone, without the panels
        ox, oy = render.follow(e.lx, e.ly, 100, 40)
        sx, sy = -1 - ox, e.ly - oy                          # just past the floor's west end
        near = ground.tiles[sx + ox + dx, sy + oy + dy]
        self.assertEqual(con.rgb["ch"][sx, sy], T.CHAR[near])
        far = con.rgb["bg"][max(0, sx - 40), sy].astype(int).sum()
        close = con.rgb["bg"][sx, sy].astype(int).sum()
        self.assertLessEqual(far, close)                     # fading out with distance

    def test_from_a_tower_roof_you_see_the_land_below(self):
        tower = next(s for s in WORLD.sites if s.kind == "tower")
        e = Engine.new(5, WORLD, (tower.x, tower.y))
        e.enter_region()
        e.lx, e.ly = next(p for p, k in e.level.exits.items() if k[0] == "tower")
        while not e.level.lookout:
            e.use_stairs("up")
            if not e.level.lookout:
                e.lx, e.ly = next(p for p in e.level.exits if e.level.tiles[p] == T.STAIRS_UP)
        ground, _ = e.ground_below()
        self.assertTrue(e.below_visible.any())
        self.assertTrue(ground.explored[e.below_visible].all())
        e.use_stairs("down")                                # a floor below the roof: indoors again
        self.assertIsNone(e.below_visible)
        screen(e)

    def test_caves_and_the_ground_itself_have_nothing_below(self):
        e = Engine.new(5, WORLD)
        e.enter_region()
        self.assertIsNone(e.ground_below())
        e.lx, e.ly = next(p for p, k in e.level.exits.items() if k[0] == "cellar")
        e.use_stairs("down")
        self.assertIsNone(e.ground_below())


if __name__ == "__main__":
    unittest.main()
