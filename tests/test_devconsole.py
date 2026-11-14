"""The dev console, the local maps shown whole, and the overworld not hiding things behind hills."""
import unittest

import numpy as np
import tcod
from tcod.event import KeySym

from game import biomes as B, render, wild
from game import tiles as T
from game.climate import MINUTES_PER_DAY
from game.engine import Engine

from tests.test_wild import engine_on, field


def run(e, line):
    e.console.run(line)
    return e.console.output[-1]


class ConsoleTests(unittest.TestCase):
    def test_backquote_opens_it_and_keys_go_to_it(self):
        e = engine_on(field())
        e.handle_key(KeySym.GRAVE)
        self.assertTrue(e.console.open)
        e.console.text("`give axe")            # the key that opened it isn't typed
        self.assertEqual(e.console.line, "give axe")
        before = (e.lx, e.ly)
        e.handle_key(KeySym.D)                 # not a step while typing
        self.assertEqual((e.lx, e.ly), before)
        e.handle_key(KeySym.RETURN)
        self.assertEqual(e.player.inventory.count("axe"), 1)
        e.handle_key(KeySym.UP)
        self.assertEqual(e.console.line, "give axe")
        e.handle_key(KeySym.ESCAPE)
        self.assertFalse(e.console.open)

    def test_help_lists_every_command(self):
        e = engine_on(field())
        e.console.run("help")
        text = "\n".join(e.console.output)
        for name in ("god", "give", "spawn", "time", "weather", "tp", "noclip"):
            self.assertIn(name, text)

    def test_give_and_drop_find_items_by_part_of_a_name(self):
        e = engine_on(field())
        run(e, "give sword")
        self.assertEqual(e.player.inventory.count("short sword"), 1)
        run(e, "give coin 50")
        self.assertEqual(e.player.inventory.count("coin"), 70)
        run(e, "drop climbing gear")
        self.assertEqual(e.level.items[(e.lx, e.ly)], ["climbing gear"])
        self.assertIn("Which item", run(e, "give ring"))

    def test_god_mode_survives_anything(self):
        e = engine_on(field())
        run(e, "god")
        e.player.health = -50
        e.player.body = 30
        e.pass_time(1)
        self.assertTrue(e.player.alive)
        self.assertEqual(e.player.health, 100)
        run(e, "god off")
        self.assertFalse(e.player.god)

    def test_spawn_and_kill(self):
        e = engine_on(field())
        run(e, "spawn wolf 3")
        wolves = [c for c in e.level.creatures if c.kind == "wolf"]
        self.assertEqual(len(wolves), 3)
        self.assertTrue(all(max(abs(c.x - e.lx), abs(c.y - e.ly)) <= 8 for c in wolves))
        run(e, "spawn goblin")
        run(e, "spawn sheep 2")
        self.assertEqual(sum(a.kind == "sheep" for a in e.level.actors), 2)
        run(e, "god")
        e.pass_time(0.5)                       # they all get on with things without trouble
        run(e, "kill")
        self.assertEqual(e.level.creatures, [])

    def test_time_commands(self):
        e = engine_on(field(), hour=12)
        start = e.minutes
        run(e, "time jump 2h")
        self.assertAlmostEqual(e.minutes, start + 120)
        run(e, "time set 06:30")
        self.assertAlmostEqual(e.minutes % MINUTES_PER_DAY, 6 * 60 + 30)
        self.assertGreater(e.minutes, start)
        run(e, "time pause")
        frozen = e.minutes
        e.move_local(1, 0)
        e.wait(1)
        self.assertEqual(e.minutes, frozen)
        run(e, "time forward 30m")             # running time on works even while paused
        self.assertAlmostEqual(e.minutes, frozen + 30)
        run(e, "time resume")
        e.wait(1)
        self.assertGreater(e.minutes, frozen + 30)
        self.assertIn("isn't a length", run(e, "time forward soon"))

    def test_weather(self):
        e = engine_on(field())
        e.fair = False
        run(e, "weather blizzard")
        self.assertEqual(e.now.kind, "Blizzard")
        self.assertTrue(e.now.snowing)
        run(e, "weather auto")
        self.assertIsNone(e.forced_weather)

    def test_tp_noclip_set_and_heal(self):
        e = engine_on(field())
        run(e, "tp 10 5")
        self.assertEqual((e.lx, e.ly), (10, 5))
        e.level.tiles[11, 5] = T.STONE_WALL
        self.assertFalse(e.move_local(1, 0))
        run(e, "noclip")
        self.assertTrue(e.move_local(1, 0))
        self.assertEqual((e.lx, e.ly), (11, 5))
        run(e, "set health 12")
        self.assertEqual(e.player.health, 12)
        run(e, "set coins 5")
        self.assertEqual(e.player.inventory.count("coin"), 5)
        run(e, "heal")
        self.assertEqual(e.player.health, 100)

    def test_bad_input_says_so(self):
        e = engine_on(field())
        self.assertIn("No such command", run(e, "fly"))
        self.assertIn("isn't a number", run(e, "set health lots"))
        self.assertIn("no creature", run(e, "spawn dragon"))

    def test_it_draws(self):
        e = engine_on(field())
        e.console.toggle()
        e.console.run("god")
        e.console.line = "time"
        console = tcod.console.Console(120, 45, order="F")
        render.draw(console, e)
        top = "".join(chr(c) for c in console.rgb["ch"][:, 1:17].T.reshape(-1))
        self.assertIn("God mode on.", top)
        self.assertIn("> time", top)


class ViewTests(unittest.TestCase):
    def test_a_local_map_is_shown_whole_when_you_enter(self):
        e = Engine.new(1)
        e.enter_region()
        self.assertTrue(e.known().all())
        self.assertFalse(e.level.explored.all())     # though you've only really seen a part
        e.handle_key(KeySym.M)
        self.assertFalse(e.known().all())
        e.handle_key(KeySym.M)
        self.assertTrue(e.known().all())

    def test_the_overworld_does_not_hide_regions_behind_high_ground(self):
        e = Engine.new(1)
        p, w = e.player, e.world
        r = e.sight_radius()
        xs, ys = np.ogrid[: w.width, : w.height]
        near = ((xs - p.x) ** 2 + (ys - p.y) ** 2 <= (r - 1) ** 2)
        fov = tcod.map.compute_fov(~B.BLOCKS_VIEW[w.biome], (p.x, p.y), r,
                                   algorithm=tcod.constants.FOV_SYMMETRIC_SHADOWCAST)
        self.assertTrue((e.visible | ~(near & fov)).all())


if __name__ == "__main__":
    unittest.main()
