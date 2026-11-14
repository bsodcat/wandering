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
from game.carts import RIDE_STEP_SECONDS
from game.passage import FRAME as PASSAGE_FRAME, Passage
from game.title import Title, draw_title, world_preview

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
    if engine.riding is not None and not engine.menu.open and not engine.console.open:
        return                              # on a cart ride: just watch the land go by
    if engine.console.open:                 # the dev console: the wheel scrolls its output
        if isinstance(event, tcod.event.MouseWheel):
            engine.console.scroll_by(int(-event.y if event.flipped else event.y) * 3)
        return
    if engine.shop is not None and not engine.menu.open:    # so does a shop
        if isinstance(event, tcod.event.MouseWheel):          # the wheel scrolls its list
            engine.shop.scroll_by(-int(-event.y if event.flipped else event.y))
        elif engine.mouse and isinstance(event, tcod.event.MouseMotion):
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
        if isinstance(event, tcod.event.MouseWheel):       # (the Controls list scrolls)
            engine.menu.scroll_by(-int(-event.y if event.flipped else event.y) * 3)
        if engine.mouse and isinstance(event, tcod.event.MouseMotion):
            engine.menu.hover(*engine.mouse)
        elif engine.mouse and isinstance(event, tcod.event.MouseButtonDown)                 and event.button == tcod.event.MouseButton.LEFT:
            result = engine.menu.click(*engine.mouse)
            if result == "quit":
                engine.quitting = True
            engine.menu_result(result)
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


def typing(display, on: bool) -> None:
    """Text input from the keyboard (the dev console) only while it's wanted."""
    window = getattr(display, "window", None)
    if window is None or getattr(display, "typing", False) == on:
        return
    try:
        window.start_text_input() if on else window.stop_text_input()
    except Exception:
        pass
    display.typing = on


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


def passage_box(console) -> tuple[int, int, int, int]:
    """Where the time skip's map goes: (x, y, width, height in rows)."""
    pw = min(console.width - 10, 128)
    ph = pw // 4
    room = console.height - 12
    if ph > room:
        ph = max(4, room)
        pw = ph * 4
    return (console.width - pw) // 2, (console.height - ph) // 2 + 1, pw, ph


def stop_button(console) -> tuple[int, int, int]:
    """(x, y, width) of the Stop button, under the map."""
    x, y, pw, ph = passage_box(console)
    return console.width // 2 - 6, y + ph + 2, 12


def draw_passage(console, passage: Passage, hover: tuple | None = None) -> None:
    """Over the dimmed game: the year counting up, the land as it stands, and Stop."""
    from game.hud import half_blocks
    from game.title import BOX_BG, BOX_BORDER, PICKED_BG, PICKED_FG, describe_region, draw_region_info
    console.rgb["fg"] = console.rgb["fg"] // 5
    console.rgb["bg"] = console.rgb["bg"] // 5
    x, y, pw, ph = passage_box(console)
    console.draw_frame(x - 1, y - 1, pw + 2, ph + 2, fg=BOX_BORDER, bg=BOX_BG)
    shown = passage.shown
    if shown is not None:
        half_blocks(console, x, y, world_preview(shown[1], pw, ph))
    lines = passage.lines()
    console.print(console.width // 2 - len(lines[0]) // 2, y - 4, lines[0], fg=(255, 220, 120))
    console.print(console.width // 2 - len(lines[1]) // 2, y - 3, lines[1], fg=(170, 170, 180))
    if shown is not None:
        note = f"The land as of year {passage.start_year + shown[0]:,}"
        console.print(console.width // 2 - len(note) // 2, y + ph + 1, note, fg=(120, 120, 130))
    bx, by, bw = stop_button(console)
    if passage.running:
        console.draw_rect(bx, by, bw, 1, ord(" "), bg=(120, 40, 40))
        console.print(bx + (bw - 6) // 2, by, "■ STOP", fg=(255, 230, 220), bg=(120, 40, 40))
        hint = "Space, Enter or click STOP to play from this year"
        console.print(console.width // 2 - len(hint) // 2, by + 2, hint, fg=(120, 120, 130))
    if shown is not None and hover is not None:
        mx, my = hover
        if x <= mx < x + pw and y <= my < y + ph:
            world = shown[1]
            wx, wy = (mx - x) * world.width // pw, ((my - y) * 2) * world.height // (2 * ph)
            draw_region_info(console, describe_region(world, wx, wy), mx, my)


def run_passage(console, display, engine: Engine, years: int, change: str) -> bool:
    """The time skip, a year at a time, until it's stopped or runs out; then the game takes the
    world it settled on. Returns False if the window was closed."""
    from game.climate import calendar
    passage = Passage(engine.world, years, change, calendar(engine.minutes)[0])
    hover = None
    while not passage.done:
        passage.tick()
        draw(console, engine)
        draw_passage(console, passage, hover)
        display.present(console)
        for event in tcod.event.wait(PASSAGE_FRAME):
            if isinstance(event, tcod.event.Quit):
                passage.stop()
                return False
            if isinstance(event, tcod.event.KeyDown) and event.sym in (
                    tcod.event.KeySym.SPACE, tcod.event.KeySym.RETURN, tcod.event.KeySym.KP_ENTER,
                    tcod.event.KeySym.ESCAPE, tcod.event.KeySym.S):
                passage.stop()
            converted = display.convert(event) if isinstance(event, (tcod.event.MouseMotion,
                                                                     tcod.event.MouseButtonDown)) else None
            if converted is None:
                continue
            mx, my = converted.integer_position
            hover = (mx, my)
            if isinstance(converted, tcod.event.MouseButtonDown):
                bx, by, bw = stop_button(console)
                if my == by and bx <= mx < bx + bw:
                    passage.stop()
    engine.time_skip(passage.stopped_at, change, passage.final)
    return True


def begin(action: tuple, menu: Menu) -> Engine:
    """Starts what the title screen picked: ("new", seed, world) or ("arena",)."""
    engine = Engine.arena() if action[0] == "arena" else \
        Engine.new(action[1], action[2], action[3] if len(action) > 3 else None)
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
    if isinstance(event, tcod.event.MouseWheel):          # scrolls the Controls list or the Updates notes
        lines = -int(-event.y if event.flipped else event.y) * 3
        if menu.open:
            menu.scroll_by(lines)
        elif title.screen == "updates":
            title.scroll_notes(lines)
        return None
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
        last_step = last_ride = 0.0
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
                elif isinstance(event, tcod.event.TextInput):
                    if engine.console.open:          # typing into the dev console
                        engine.console.text(event.text)
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
            typing(display, engine.console.open)
            if engine.to_title:                   # Main menu: back to the title screen
                engine = None
                menu.top = None
                title.show("main")
                continue
            if engine.skip_request is not None:   # the time skip: count the years, remake the world
                years, change = engine.skip_request
                engine.skip_request = None
                if not run_passage(console, display, engine, years, change):
                    return
                continue
            if engine.riding is not None and not engine.menu.open and not engine.console.open \
                    and time.monotonic() - last_ride >= RIDE_STEP_SECONDS:
                engine.ride_step()            # the cart goes on a region along the road
                last_ride = time.monotonic()
            if engine.autopath and time.monotonic() - last_step >= delay * 0.9:
                walk(engine)
                last_step = time.monotonic()
    finally:
        display.close()


if __name__ == "__main__":
    main()
