"""The mouse: looking at things, and walking to the pointer while the right button is held."""
import unittest

import numpy as np
import tcod
import tcod.event as E

import main
from game import tiles as T
from game.engine import Engine
from game.render import SCREEN_H, SCREEN_W, draw, map_cell, view_origin


def new_local(seed=1):
    e = Engine.new(seed)
    e.enter_region()
    e.level.explored[:] = True
    return e


def screen_of(e, x, y):
    ox, oy = view_origin(e)
    return x - ox, y - oy


def motion(sx, sy):
    return E.MouseMotion(position=(sx, sy), tile=(sx, sy))


def press(sx, sy, button):
    return E.MouseButtonDown(position=(sx, sy), tile=(sx, sy), button=button)


def release(sx, sy, button):
    return E.MouseButtonUp(position=(sx, sy), tile=(sx, sy), button=button)


def far_walkable(e, steps=10):
    """A known, walkable tile some steps from you that a route reaches."""
    t = e.level.tiles
    for x, y in zip(*np.nonzero(T.WALK[t])):
        x, y = int(x), int(y)
        if max(abs(x - e.lx), abs(y - e.ly)) == steps and not e.panels.covers(*screen_of(e, x, y)):
            if e.route(x, y):
                return x, y
    raise AssertionError("no reachable tile")


class LookTests(unittest.TestCase):
    def test_map_cell_turns_the_screen_into_map_cells(self):
        e = new_local()
        sx, sy = screen_of(e, e.lx, e.ly)
        self.assertEqual(map_cell(e, sx, sy), (e.lx, e.ly))
        self.assertIsNone(map_cell(e, 100, 5))     # the right panel
        self.assertIsNone(map_cell(e, 5, 20))      # the stats panel
        e.panels.left_open = e.panels.right_open = False
        self.assertIsNotNone(map_cell(e, 100, 5))  # hidden: the map is under them all along
        self.assertFalse(e.panels.covers(5, 20))

    def test_describes_what_you_point_at(self):
        e = new_local()
        self.assertTrue(e.describe(e.lx, e.ly)[0].startswith("You, on"))
        door = next(zip(*np.nonzero(e.level.tiles == T.DOOR)))
        self.assertEqual(e.describe(*door)[0], "Door")
        wall = next(zip(*np.nonzero(e.level.tiles == T.WALL)))
        self.assertIn("Blocks the way", e.describe(*wall))
        e.level.explored[:] = False
        self.assertEqual(e.describe(*door), ["Unexplored"])

    def test_stairs_say_where_they_go(self):
        e = Engine.new(1)
        tower = next(s for s in e.world.sites if s.kind == "tower")
        e.player.x, e.player.y = tower.x, tower.y
        e.enter_region()
        e.level.explored[:] = True
        stairs = next(iter(e.level.exits))
        self.assertIn("Leads to the tower above", e.describe(*stairs))

    def test_describes_the_world_map(self):
        e = Engine.new(1)
        p = e.player
        lines = e.describe(p.x, p.y)
        self.assertEqual(lines[0], "You are here")
        self.assertIn(e.site.name, lines[1])
        e.reveal = True
        far = (p.x + 3, p.y)
        self.assertTrue(any("away" in line or "No known way" in line for line in e.describe(*far)))

    def test_left_click_notes_it_in_the_log(self):
        e = new_local()
        sx, sy = screen_of(e, e.lx, e.ly)
        main.handle_mouse(e, press(sx, sy, E.MouseButton.LEFT))
        self.assertTrue(e.messages[-1].startswith("You see: You, on"))

    def test_hover_shows_in_the_sidebar_and_on_the_map(self):
        e = new_local()
        sx, sy = screen_of(e, *far_walkable(e))
        main.handle_mouse(e, motion(sx, sy))
        console = tcod.console.Console(SCREEN_W, SCREEN_H, order="F")
        draw(console, e)
        text = "".join(chr(c) for c in console.rgb["ch"][92:, :].T.flatten())
        self.assertIn("Look", text)
        self.assertTrue((console.rgb["bg"][sx, sy] > 120).any())


class WalkTests(unittest.TestCase):
    def test_routes_over_known_ground_only(self):
        e = new_local()
        x, y = far_walkable(e)
        path = e.route(x, y)
        self.assertEqual(path[-1], (x, y))
        self.assertTrue(all(T.WALK[e.level.tiles[p]] for p in path))
        e.level.explored[:] = False
        e.level.explored[e.lx, e.ly] = True
        self.assertEqual(e.route(x, y), [])

    def test_holding_right_walks_there(self):
        e = new_local()
        x, y = far_walkable(e)
        sx, sy = screen_of(e, x, y)
        main.handle_mouse(e, press(sx, sy, E.MouseButton.RIGHT))
        self.assertTrue(e.autopath)
        start = e.minutes
        for _ in range(60):
            if (e.lx, e.ly) == (x, y) or not e.autopath:
                break
            main.walk(e)                     # the view scrolls, but the goal stays put
        self.assertEqual((e.lx, e.ly), (x, y))
        self.assertGreater(e.minutes, start)
        main.handle_mouse(e, release(*e.mouse, E.MouseButton.RIGHT))
        self.assertFalse(e.autopath)
        self.assertIsNone(e.goal)

    def test_moving_the_mouse_while_holding_steers(self):
        e = new_local()
        a = far_walkable(e, 6)
        main.handle_mouse(e, press(*screen_of(e, *a), E.MouseButton.RIGHT))
        self.assertEqual(e.goal, a)
        b = far_walkable(e, 8)
        main.handle_mouse(e, motion(*screen_of(e, *b)))
        self.assertEqual(e.goal, b)
        main.handle_mouse(e, release(*screen_of(e, *b), E.MouseButton.RIGHT))
        main.handle_mouse(e, motion(*screen_of(e, *a)))
        self.assertIsNone(e.goal)                # just pointing doesn't set off

    def test_keeps_dry_when_there_is_a_way_round(self):
        e = new_local()
        t = e.level.tiles
        t[:, :] = T.GRASS
        e.lx, e.ly = 10, 10
        t[15, 5:16] = T.WATER                    # a strip of shallow water with a way round the bottom
        path = e.route(20, 10)
        self.assertFalse(any(t[p] == T.WATER for p in path))
        t[15, :] = T.WATER                       # no way round: wade it
        self.assertTrue(any(t[p] == T.WATER for p in e.route(20, 10)))

    def test_something_happening_stops_the_walk(self):
        e = new_local()
        x, y = far_walkable(e)
        e.goal = (x, y)
        e.autopath = True
        e.disturbed = True
        main.walk(e)
        self.assertFalse(e.autopath)

    def test_walks_on_the_world_map(self):
        e = Engine.new(1)
        e.reveal = True
        p = e.player
        start = (p.x, p.y)
        target = next((p.x + dx, p.y) for dx in (4, -4, 3, -3) if e.route(p.x + dx, p.y))
        e.goal = target
        e.autopath = True
        for _ in range(10):
            main.walk(e)
            if (p.x, p.y) == target:
                break
        self.assertNotEqual((p.x, p.y), start)

    def test_unknown_place_says_so(self):
        e = new_local()
        e.level.explored[:] = False
        e.level.explored[e.lx, e.ly] = True
        sx, sy = screen_of(e, min(e.level.width - 1, e.lx + 5), e.ly)
        main.handle_mouse(e, press(sx, sy, E.MouseButton.RIGHT))
        self.assertEqual(e.messages[-1], "You don't know a way there.")


if __name__ == "__main__":
    unittest.main()
