"""Wandering: run with `python main.py` for the title screen, or `python main.py <seed>` to go
straight into that world."""
from __future__ import annotations

import sys
import time

import tcod

from game import __version__
from game.display import Display, make_tileset
from game.engine import Engine
from game.hud import draw_menu
from game.options import Menu, Settings
from game.render import SCREEN_H, SCREEN_W, draw, map_cell
from game.title import Title, draw_title

STEP_DELAY = 0.05        # seconds between steps when walking to the pointer on a local map
WORLD_STEP_DELAY = 0.15  # and on the overworld
FRAME = 1 / 15           # seconds between redraws for the animations


def load_tileset() -> tcod.tileset.Tileset:
    """The default font: Terminal at 10x20 (for tools that draw the screen without a window)."""
    return make_tileset("Terminal", (10, 20))


def handle_mouse(engine: Engine, event) -> None:
    """Over the map: pointing looks, a left click opens the use menu for what's there (or notes
    it in the log if there's nothing to do with it), and the right button held walks. Over a panel: clicks work its tabs and buttons, the wheel scrolls the log."""
    panels = engine.panels
    if isinstance(event, (tcod.event.MouseMotion, tcod.event.MouseButtonDown, tcod.event.MouseButtonUp)):
        engine.mouse = tuple(event.integer_position)
    if engine.shop is not None and not engine.menu.open:    # so does a shop
        if engine.mouse and isinstance(event, tcod.event.MouseMotion):
            i = engine.shop.row_at(*engine.mouse)
            if i is not None:
                engine.shop.cursor = i
        elif engine.mouse and isinstance(event, tcod.event.MouseButtonDown) \
                and event.button == tcod.event.MouseButton.LEFT:
            modal = engine.shop
            if not modal.click(*engine.mouse, engine) and engine.shop is modal:
                engine.close_box()
        return
    if engine.menu.open:                    # the menu takes the mouse while it's up
        if engine.mouse and isinstance(event, tcod.event.MouseMotion):
            engine.menu.hover(*engine.mouse)
        elif engine.mouse and isinstance(event, tcod.event.MouseButtonDown)                 and event.button == tcod.event.MouseButton.LEFT:
            result = engine.menu.click(*engine.mouse)
            if result == "quit":
                engine.quitting = True
            elif result == "title":
                engine.to_title = True
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
            engine.pending = None
            if not (engine.player.alive and engine.click_at(*cell)):
                engine.say("You see: " + ", ".join(engine.describe(*cell)) + ".")
        elif event.button == tcod.event.MouseButton.RIGHT:
            engine.pending = None
            engine.autopath, engine.disturbed, engine.goal = True, False, cell
            if cell is None or not engine.route(*cell):
                engine.say("You don't know a way there.")
    elif isinstance(event, tcod.event.MouseButtonUp) and event.button == tcod.event.MouseButton.RIGHT \
            and engine.pending is None:
        engine.autopath, engine.goal = False, None


def walk(engine: Engine) -> None:
    """One step toward the goal while the right button is held. The goal is a place on the map,
    so it stays put as the view scrolls. Stops (until pressed again) when you change maps or
    something needs your attention."""
    if engine.goal is None:
        return
    if engine.try_pending():                # walked over to do something: done
        engine.autopath, engine.goal = False, None
        return
    where = engine.level
    moved = engine.step_toward(*engine.goal)
    if engine.disturbed or engine.level is not where or not engine.player.alive or \
            (engine.pending is not None and not moved):
        engine.autopath, engine.goal, engine.pending = False, None, None


def begin(action: tuple, menu: Menu) -> Engine:
    """Starts what the title screen picked: ("new", seed, world) or ("arena",)."""
    engine = Engine.arena() if action[0] == "arena" else Engine.new(action[1], action[2])
    engine.menu = menu
    menu.top = "pause"
    menu.show(None)
    return engine


def title_event(title: Title, menu: Menu, event) -> tuple | None:
    """A key or the mouse on the title screen (or the options screen over it). Returns what
    to start, if anything."""
    if isinstance(event, tcod.event.KeyDown):
        if event.sym == tcod.event.KeySym.F11 or event.sym in (tcod.event.KeySym.RETURN, tcod.event.KeySym.KP_ENTER)                 and event.mod & tcod.event.Modifier.ALT:
            menu.toggle_fullscreen()
            return None
        if menu.open:
            menu.handle_key(event.sym, event.mod)
            return None
        return title.handle_key(event.sym, event.mod)
    if not isinstance(event, (tcod.event.MouseMotion, tcod.event.MouseButtonDown)):
        return None
    x, y = event.integer_position
    pressed = isinstance(event, tcod.event.MouseButtonDown) and event.button == tcod.event.MouseButton.LEFT
    target = menu if menu.open else title
    if isinstance(event, tcod.event.MouseMotion):
        target.hover(x, y)
    elif pressed:
        result = target.click(x, y)
        return result if target is title else None
    return None


def main() -> None:
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else None
    settings = Settings.load()
    menu = Menu(settings)
    title = Title(menu)
    menu.top = None
    engine = begin(("new", seed, None), menu) if seed is not None else None
    console = tcod.console.Console(SCREEN_W, SCREEN_H, order="F")
    display = Display(settings, title=f"Wandering {__version__}")
    menu.area = display.area                  # the menu works out sizes for this screen
    try:
        last_step = 0.0
        while not (engine is not None and engine.quitting):
            if menu.changed:                   # the options screen changed something
                menu.changed = False
                display.apply(settings)
                menu.area = display.area
                settings.save()
            _, cols, rows = display.layout()
            if (console.width, console.height) != (cols, rows):     # the window changed shape
                console = tcod.console.Console(cols, rows, order="F")
            if engine is None:
                menu.cols, menu.rows = cols, rows
                draw_title(console, title, time.monotonic())
                draw_menu(console, menu)
            else:
                draw(console, engine)
            display.present(console)
            menu.shown = (display.scale, cols, rows)
            if engine is None:
                for event in tcod.event.wait(FRAME):
                    if isinstance(event, tcod.event.Quit):
                        return
                    converted = event if isinstance(event, tcod.event.KeyDown) else display.convert(event)
                    action = title_event(title, menu, converted) if converted is not None else None
                    if action == ("quit",):
                        return
                    if action:
                        engine = begin(action, menu)
                        break
                continue
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
                if engine.to_title:
                    break
            if engine.to_title:                   # Main menu: back to the title screen
                engine = None
                menu.top = None
                title.show("main")
                continue
            if engine.autopath and time.monotonic() - last_step >= delay * 0.9:
                walk(engine)
                last_step = time.monotonic()
    finally:
        display.close()


if __name__ == "__main__":
    main()
