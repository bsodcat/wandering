"""newrogue: run with `python main.py [seed]`."""
from __future__ import annotations

import sys
import time

import tcod

from game import __version__
from game.display import Display, make_tileset
from game.engine import Engine
from game.options import Settings
from game.render import SCREEN_H, SCREEN_W, draw, map_cell

STEP_DELAY = 0.05        # seconds between steps when walking to the pointer on a local map
WORLD_STEP_DELAY = 0.15  # and on the overworld
FRAME = 1 / 15           # seconds between redraws for the animations


def load_tileset() -> tcod.tileset.Tileset:
    """The default font: Terminal at 10x20 (for tools that draw the screen without a window)."""
    return make_tileset("Terminal", (10, 20))


def handle_mouse(engine: Engine, event) -> None:
    """Over the map: pointing looks, a left click notes what's there in the log, and the right
    button held walks. Over a panel: clicks work its tabs and buttons, the wheel scrolls the log."""
    panels = engine.panels
    if isinstance(event, (tcod.event.MouseMotion, tcod.event.MouseButtonDown, tcod.event.MouseButtonUp)):
        engine.mouse = tuple(event.integer_position)
    if engine.menu.open:                    # the menu takes the mouse while it's up
        if engine.mouse and isinstance(event, tcod.event.MouseMotion):
            engine.menu.hover(*engine.mouse)
        elif engine.mouse and isinstance(event, tcod.event.MouseButtonDown)                 and event.button == tcod.event.MouseButton.LEFT:
            if engine.menu.click(*engine.mouse) == "quit":
                engine.quitting = True
        return
    if isinstance(event, tcod.event.MouseWheel):
        if engine.mouse and panels.over_log(*engine.mouse):
            panels.scroll(int(-event.y if event.flipped else event.y) * 3)
        return
    on_panel = engine.mouse is not None and panels.covers(*engine.mouse)
    if on_panel and isinstance(event, tcod.event.MouseButtonDown):
        if event.button == tcod.event.MouseButton.LEFT:
            panels.click(*engine.mouse)     # tabs and hide/show buttons
        return
    cell = map_cell(engine, *engine.mouse) if engine.mouse else None
    if isinstance(event, tcod.event.MouseMotion) and engine.autopath and cell is not None:
        engine.goal = cell                 # steering while you hold the button
    elif isinstance(event, tcod.event.MouseButtonDown):
        if event.button == tcod.event.MouseButton.LEFT and cell is not None:
            engine.say("You see: " + ", ".join(engine.describe(*cell)) + ".")
        elif event.button == tcod.event.MouseButton.RIGHT:
            engine.autopath, engine.disturbed, engine.goal = True, False, cell
            if cell is None or not engine.route(*cell):
                engine.say("You don't know a way there.")
    elif isinstance(event, tcod.event.MouseButtonUp) and event.button == tcod.event.MouseButton.RIGHT:
        engine.autopath, engine.goal = False, None


def walk(engine: Engine) -> None:
    """One step toward the goal while the right button is held. The goal is a place on the map,
    so it stays put as the view scrolls. Stops (until pressed again) when you change maps or
    something needs your attention."""
    if engine.goal is None:
        return
    where = engine.level
    engine.step_toward(*engine.goal)
    if engine.disturbed or engine.level is not where or not engine.player.alive:
        engine.autopath, engine.goal = False, None


def main() -> None:
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else None
    settings = Settings.load()
    engine = Engine.new(seed)
    engine.menu.settings = settings
    console = tcod.console.Console(SCREEN_W, SCREEN_H, order="F")
    display = Display(settings, title=f"Rogue Adventure {__version__}")
    engine.menu.area = display.area           # the menu works out sizes for this screen
    try:
        last_step = 0.0
        while not engine.quitting:
            if engine.menu.changed:            # the options screen changed something
                engine.menu.changed = False
                display.apply(settings)
                engine.menu.area = display.area
                settings.save()
            _, cols, rows = display.layout()
            if (console.width, console.height) != (cols, rows):     # the window changed shape
                console = tcod.console.Console(cols, rows, order="F")
            draw(console, engine)
            display.present(console)
            engine.menu.shown = (display.scale, cols, rows)
            delay = STEP_DELAY if engine.level is not None else WORLD_STEP_DELAY
            # wake up every frame even with nothing pressed, so water runs and fires flicker
            for event in tcod.event.wait(min(delay, FRAME) if engine.autopath else FRAME):
                if isinstance(event, tcod.event.Quit):
                    return
                if isinstance(event, tcod.event.KeyDown):
                    engine.autopath = False
                    if not engine.handle_key(event.sym, event.mod):
                        return
                elif isinstance(event, tcod.event.WindowEvent) and event.type == "WindowLeave":
                    engine.mouse, engine.autopath = None, False
                else:
                    converted = display.convert(event)
                    if converted is None:          # over the black bars
                        engine.mouse = None
                    else:
                        handle_mouse(engine, converted)
            if engine.autopath and time.monotonic() - last_step >= delay * 0.9:
                walk(engine)
                last_step = time.monotonic()
    finally:
        display.close()


if __name__ == "__main__":
    main()
