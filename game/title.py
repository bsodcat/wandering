"""The title screen: what you see before a game, and the screens it leads to.

    New Game         a random world, straight away
    Create a World   pick a seed (type one, or roll one), the year it starts in and what the
                     ages before brought (game/eras.py), and see the world it makes first;
                     the World settings bar down the left side turns the dials on the land,
                     the climate, the people and the volcanoes (game/tweaks.py); the Region
                     view down the right shows the region under the pointer close up, and a
                     left click on the map marks where you'll start
    Dev Arena        the 256 x 256 test ground with one of everything (game/arena.py)
    Options          the display options (game/options.py)
    About            what the game is, and who made it
    Quit Game

Under the choices are the keys for the menus, picked out in colour. Up/Down (or W/S) choose,
Enter picks, Esc goes back; the mouse points and clicks. In Create a World, Tab moves between
the choices and the World settings bar, and Left/Right change a setting. Behind it all a world
drifts by.

This module keeps the title screen's state and draws it; main.py starts whatever it picks.
"""
from __future__ import annotations

import random
import textwrap

import numpy as np
from tcod.event import KeySym, Modifier

from . import __version__
from . import biomes as B
from . import eras
from . import tweaks as TW
from . import updates
from .worldgen import SITE_KINDS, World, generate

GAME_TITLE = "Gathering to Aevum: The Necromancer's Key"
SUBTITLE = "Chapter II: Wandering the Mundane"
CREATOR = "Created by: bsodcat"
ITEMS = ["New Game", "Create a World", "Dev Arena", "Options", "Updates", "About", "Quit Game"]
UPDATE_ROWS = ["Check for updates", "Download page", "Back"]
UPDATES_W = 86                                             # the Updates box, at most
CREATE_ROWS = ["Seed", "Year", "Change", "Random seed", "Begin", "Back"]
MOST_DIGITS = 9
BACKDROP_SEED = 7
SIDE_ROWS = [s.name for s in TW.SETTINGS] + ["Defaults"]   # the World settings bar
SIDE_W = 34                                                # its width, border to border
VIEW_W = 34                                                # the Region view's width

PURPLE, DEEP_PURPLE = (182, 102, 255), (95, 55, 140)
WHITE, TEXT, DIM, DARK_GREY = (255, 255, 255), (200, 200, 205), (135, 135, 145), (85, 85, 92)
KEY_FG, KEY_BG = (255, 215, 110), (52, 42, 70)
PICKED_FG, PICKED_BG = (255, 220, 120), (40, 32, 56)
BOX_BG, BOX_BORDER = (12, 10, 18), (95, 70, 130)

# What the keys do, under the choices. [Key] is drawn picked out; the rest is plain text.
MENU_HINTS = ["[↑] [↓] or [W] [S] choose   [Enter] select   [Esc] back   [Mouse] point and click"]
CREATE_HINTS = ["[0]-[9] type a seed   [R] random   [Esc] back",
                "[Tab] world settings   [←] [→] change (Shift: 1,000 years)   [Enter] select",
                "[Left mouse] on the map: start there"]
ABOUT = [
    "Wander a world made fresh from a single number: mountains, rivers and lakes, twenty "
    "biomes, volcanoes, and towns, villages, roadside inns, watchtowers, ruins and caves joined by roads.",
    "Travel the land a region at a time, or step down and walk any part of it tile by tile. "
    "Seasons turn and weather drifts across the land; the cold, the rain and the wind wear on "
    "you. Townsfolk keep their trades and their hours, fields ripen, and herds graze.",
    "Made with Python, python-tcod and numpy.",
]


def random_seed() -> str:
    return str(random.randrange(1, 10 ** MOST_DIGITS))


class Title:
    """Which title screen is up ("main", "create", "updates" or "about") and what's picked on it."""

    def __init__(self, menu):
        self.menu = menu                  # the options screen, shared with the game
        self.screen = "main"
        self.cursor = 0
        self.seed_text = random_seed()
        self.cols, self.rows = 120, 45    # the screen in tiles, as last drawn
        self._worlds: dict[tuple, World] = {}
        self.year = 0                     # index into eras.START_YEARS
        self.change = 0                   # index into eras.CHANGES
        self.tweaks = TW.DEFAULT          # the World settings bar
        self.side = False                 # the bar has the keys (Tab), not the choices
        self.side_cursor = 0              # which row of the bar is picked
        self.mouse: tuple[int, int] | None = None   # where the pointer is, for the map's region info
        self.spawn: tuple[int, int] | None = None   # the region picked to start in (a click on the map)
        self._regions: dict = {}                    # region maps made for the Region view
        self.checker = updates.Checker()            # the Updates screen's check for a newer version
        self.notes_scroll = 0                       # lines down the Updates notes
        self.notes_shown = 20                       # how many fit (kept up to date as they're drawn)

    def show(self, screen: str) -> None:
        self.screen, self.cursor, self.side = screen, 0, False

    # ------------------------------------------------------------- worlds

    @property
    def history(self) -> tuple:
        return eras.start_history(eras.START_YEARS[self.year], eras.CHANGES[self.change].name)

    def world(self, seed: int, history: tuple = (), tweaks: TW.Tweaks = TW.DEFAULT) -> World:
        """The world from a seed, a history and its settings, kept so the preview and the game
        share it."""
        key = (seed, history, tweaks)
        if key not in self._worlds:
            self._worlds = {k: v for k, v in self._worlds.items() if k == (BACKDROP_SEED, (), TW.DEFAULT)}
            self._worlds[key] = generate(seed, history=history, tweaks=tweaks)
        return self._worlds[key]

    @property
    def seed(self) -> int | None:
        return int(self.seed_text) if self.seed_text else None

    # ------------------------------------------------------------- choosing

    def items(self) -> list[str]:
        return {"main": ITEMS, "create": CREATE_ROWS, "updates": UPDATE_ROWS}.get(self.screen, [])

    def activate(self) -> tuple | None:
        """Enter on what's picked. Returns what main.py should start, if anything:
        ("new", seed, world), ("arena",) or ("quit",)."""
        if self.screen == "about":
            self.show("main")
            return None
        item = self.items()[self.cursor]
        if item == "New Game":
            return ("new", None, None)
        if item == "Create a World":
            self.show("create")
            self.cursor = CREATE_ROWS.index("Begin")
        elif item == "Dev Arena":
            return ("arena",)
        elif item == "Options":
            self.menu.top = None
            self.menu.show("options")
        elif item == "About":
            self.show("about")
        elif item == "Updates":
            self.show("updates")
            self.notes_scroll = 0
        elif item == "Check for updates":
            self.checker.check()
        elif item == "Download page":
            self.checker.status = updates.open_page()
        elif item == "Back" and self.screen == "updates":
            self.back()
        elif item == "Quit Game":
            return ("quit",)
        elif item == "Random seed":
            self.seed_text = random_seed()
        elif item in ("Year", "Change"):
            self.step(item, 1)
        elif item in ("Begin", "Seed"):
            seed = self.seed if self.seed is not None else int(random_seed())
            world = self.world(seed, self.history, self.tweaks)
            return ("new", seed, world, start_spot(world, self.spawn))
        elif item == "Back":
            self.show("main")
            self.cursor = ITEMS.index("Create a World")
        return None

    def back(self) -> None:
        if self.screen != "main":
            came_from = ITEMS.index({"create": "Create a World", "updates": "Updates"}.get(self.screen, "About"))
            self.show("main")
            self.cursor = came_from

    def handle_key(self, sym, mod: int = 0) -> tuple | None:
        items = self.items()
        if self.screen == "create" and sym == KeySym.TAB:
            self.side = not self.side
            return None
        if self.screen == "create" and self.side and self.side_key(sym, mod):
            return None
        if sym == KeySym.ESCAPE:
            self.back()
        elif self.screen == "updates" and sym in (KeySym.PAGEUP, KeySym.PAGEDOWN, KeySym.HOME, KeySym.END):
            self.scroll_notes({KeySym.PAGEUP: -self.notes_shown, KeySym.PAGEDOWN: self.notes_shown,
                               KeySym.HOME: -10_000, KeySym.END: 10_000}[sym])
        elif self.screen == "updates" and sym in (KeySym.LEFT, KeySym.KP_4, KeySym.A, KeySym.RIGHT, KeySym.KP_6, KeySym.D):
            step = 1 if sym in (KeySym.RIGHT, KeySym.KP_6, KeySym.D) else -1
            self.cursor = (self.cursor + step) % len(items)
        elif self.screen == "about":
            if sym in (KeySym.RETURN, KeySym.KP_ENTER, KeySym.SPACE):
                self.back()
        elif sym in (KeySym.UP, KeySym.KP_8, KeySym.W):
            self.cursor = (self.cursor - 1) % len(items)
        elif sym in (KeySym.DOWN, KeySym.KP_2, KeySym.S):
            self.cursor = (self.cursor + 1) % len(items)
        elif sym in (KeySym.RETURN, KeySym.KP_ENTER, KeySym.SPACE) and not mod & Modifier.ALT:
            return self.activate()
        elif self.screen == "create":
            self.edit_seed(sym, mod)
        return None

    def scroll_notes(self, lines: int) -> None:
        """Scrolls the Updates notes (PageUp/PageDown, the mouse wheel)."""
        total = len(updates.lines(updates_layout(self.cols, self.rows)["w"] - 6))
        self.notes_scroll = max(0, min(max(0, total - self.notes_shown), self.notes_scroll + lines))

    # ------------------------------------------------------------- the World settings bar

    def side_key(self, sym, mod: int = 0) -> bool:
        """A key while the bar has the keys. Returns whether it used it (digits and the like
        still go to the seed)."""
        row = SIDE_ROWS[self.side_cursor]
        if sym == KeySym.ESCAPE:
            self.side = False
        elif sym in (KeySym.UP, KeySym.KP_8, KeySym.W):
            self.side_cursor = (self.side_cursor - 1) % len(SIDE_ROWS)
        elif sym in (KeySym.DOWN, KeySym.KP_2, KeySym.S):
            self.side_cursor = (self.side_cursor + 1) % len(SIDE_ROWS)
        elif sym in (KeySym.LEFT, KeySym.KP_4, KeySym.A, KeySym.RIGHT, KeySym.KP_6, KeySym.D):
            if row != "Defaults":
                self.tweaks = self.tweaks.stepped(row, 1 if sym in (KeySym.RIGHT, KeySym.KP_6, KeySym.D) else -1)
        elif sym in (KeySym.RETURN, KeySym.KP_ENTER, KeySym.SPACE) and not mod & Modifier.ALT:
            self.side_pick(row, 1)
        else:
            return False
        return True

    def side_pick(self, row: str, by: int) -> None:
        """Enter or a click on a row of the bar: Defaults puts every setting back; a setting
        steps on (round to the start again past its last step)."""
        if row == "Defaults":
            self.tweaks = TW.DEFAULT
            return
        s = TW.BY_NAME[row]
        at = self.tweaks.index(row)
        nxt = (at + by) % len(s.steps)
        self.tweaks = self.tweaks.stepped(row, nxt - at)

    def step(self, row: str, by: int) -> None:
        if row == "Year":
            self.year = (self.year + by) % len(eras.START_YEARS)
        else:
            self.change = (self.change + by) % len(eras.CHANGES)

    def edit_seed(self, sym, mod: int = 0) -> None:
        row = CREATE_ROWS[self.cursor]
        if row in ("Year", "Change") and sym in (KeySym.LEFT, KeySym.RIGHT, KeySym.KP_4, KeySym.KP_6,
                                                  KeySym.A, KeySym.D):
            by = 1 if sym in (KeySym.RIGHT, KeySym.KP_6, KeySym.D) else -1
            if row == "Year" and mod & Modifier.SHIFT:   # Shift: a thousand years at a time
                by *= eras.YEAR_JUMP // eras.YEAR_STEP
            self.step(row, by)
            return
        digit = digit_of(sym)
        if digit is not None:
            if len(self.seed_text) < MOST_DIGITS:
                self.seed_text = (self.seed_text + digit).lstrip("0") or ("0" if digit == "0" else "")
            self.cursor = CREATE_ROWS.index("Seed")
        elif sym == KeySym.BACKSPACE:
            self.seed_text = self.seed_text[:-1]
            self.cursor = CREATE_ROWS.index("Seed")
        elif sym == KeySym.R:
            self.seed_text = random_seed()
        elif sym in (KeySym.LEFT, KeySym.RIGHT, KeySym.KP_4, KeySym.KP_6) and CREATE_ROWS[self.cursor] == "Seed":
            step = 1 if sym in (KeySym.RIGHT, KeySym.KP_6) else -1
            self.seed_text = str(max(0, (self.seed or 0) + step))

    # ------------------------------------------------------------- the mouse

    def row_at(self, sx: int, sy: int) -> int | None:
        rows = item_rows(self)
        for i, (y, x0, x1) in enumerate(rows):
            if sy == y and x0 <= sx < x1:
                return i
        return None

    def side_at(self, sx: int, sy: int) -> int | None:
        if self.screen != "create":
            return None
        for i, (y, x0, x1) in enumerate(side_rows(self)):
            if sy == y and x0 <= sx < x1:
                return i
        return None

    def hover(self, sx: int, sy: int) -> None:
        self.mouse = (sx, sy)
        i = self.side_at(sx, sy)
        if i is not None:
            self.side, self.side_cursor = True, i
            return
        i = self.row_at(sx, sy)
        if i is not None:
            self.side, self.cursor = False, i

    def click(self, sx: int, sy: int) -> tuple | None:
        if self.screen == "about":
            self.back()
            return None
        i = self.side_at(sx, sy)
        if i is not None:                      # the left arrow steps back, anywhere else steps on
            self.side, self.side_cursor = True, i
            _, x0, x1 = side_rows(self)[i]
            self.side_pick(SIDE_ROWS[i], -1 if sx <= side_value_x(self) else 1)
            return None
        spot = self.map_region(sx, sy)
        if spot is not None:                   # the map: start here (again: don't)
            world = self.world(self.seed, self.history, self.tweaks)
            spot = start_spot(world, spot)
            self.spawn = None if spot == self.spawn else spot
            return None
        i = self.row_at(sx, sy)
        if i is None:
            return None
        self.side, self.cursor = False, i
        return self.activate()

    def map_region(self, sx: int, sy: int) -> tuple[int, int] | None:
        """The world region under a point of the Create a World map, if it's over the map."""
        if self.screen != "create" or self.seed is None:
            return None
        x, y, pw, ph = preview_rect(self.cols, self.rows)
        if not (x <= sx < x + pw and y <= sy < y + ph):
            return None
        world = self.world(self.seed, self.history, self.tweaks)
        return (sx - x) * world.width // pw, ((sy - y) * 2) * world.height // (2 * ph)

    def region_map(self, world: World, x: int, y: int):
        """The local map of a region, for the Region view (kept: they're quick, but not free)."""
        from .localgen import generate_region
        key = (id(world), x, y)
        if key not in self._regions:
            if len(self._regions) > 24:
                self._regions.clear()
            self._regions[key] = generate_region(world, x, y)
        return self._regions[key]


DIGITS = {getattr(KeySym, f"N{i}"): str(i) for i in range(10)}   # the number row (the numpad moves)


def digit_of(sym) -> str | None:
    return DIGITS.get(sym)


# ----------------------------------------------------------------- where things go

def main_layout(rows: int) -> dict:
    hints = len(MENU_HINTS)
    block = 5 + 2 + (2 * len(ITEMS) - 1) + 2 + hints
    spare = rows - 3 - block
    gap = 2 if spare >= 8 else 1
    top = max(1, (spare - 2 * (gap - 1)) // 3)
    title_y = top
    items_y = title_y + 5 + gap
    hints_y = items_y + 2 * len(ITEMS) - 1 + gap + 1
    return {"title": title_y, "items": items_y, "hints": hints_y}


def create_layout(cols: int, rows: int) -> dict:
    """Where everything on Create a World goes: the World settings bar down the left, the
    Region view down the right (if there's room), and the rest centred between them (`mid` is
    its middle column)."""
    side = min(SIDE_W, max(24, cols // 4))
    view = min(VIEW_W, max(24, cols // 4)) if cols >= 100 else 0
    area = cols - side - 1 - (view + 1 if view else 0)
    mid = side + 1 + area // 2
    pw = min(area - 6, 128)
    ph = pw // 4                          # half blocks: square pixels, and the world is 2:1
    room = rows - 27                      # the rest: headings, stats, the era, choices, keys and the footer
    if ph > room:
        ph = max(4, room)
        pw = ph * 4
    top = max(1, (rows - (ph + 27)) // 2)
    gap = 2 if rows - 6 >= 2 * len(SIDE_ROWS) + 10 else 1
    return {"title": top, "preview": (top + 3, pw, ph), "stats": top + 5 + ph, "start": top + 6 + ph,
            "era": top + 7 + ph, "rows": top + 9 + ph, "hints": top + 9 + ph + 2 * len(CREATE_ROWS),
            "mid": mid, "area": area, "side": (0, 1, side, rows - 4), "side_gap": gap,
            "view": (cols - view, 1, view, rows - 4) if view else None}


def preview_rect(cols: int, rows: int) -> tuple[int, int, int, int]:
    """(x, y, width, height) of the Create a World map, in tiles."""
    lay = create_layout(cols, rows)
    y, pw, ph = lay["preview"]
    return lay["mid"] - pw // 2, y, pw, ph


def start_spot(world: World, spot: tuple[int, int] | None) -> tuple[int, int] | None:
    """A picked start region, moved to the nearest land you can walk if it's in the water."""
    if spot is None:
        return None
    x, y = spot
    if world.walkable(x, y):
        return x, y
    cells = np.argwhere(B.TRAVEL[world.biome] > 0)
    i = int(np.argmin((cells[:, 0] - x) ** 2 + (cells[:, 1] - y) ** 2))
    return int(cells[i][0]), int(cells[i][1])


def side_rows(title: Title) -> list[tuple[int, int, int]]:
    """(y, x0, x1) of each row of the World settings bar."""
    lay = create_layout(title.cols, title.rows)
    x, y, w, _ = lay["side"]
    gap = lay["side_gap"]
    out = [(y + 3 + gap * i, x + 1, x + w - 1) for i in range(len(TW.SETTINGS))]
    out.append((out[-1][0] + gap + 1, x + 1, x + w - 1))      # Defaults, a line below the rest
    return out


def side_value_x(title: Title) -> int:
    """The middle of the values' column: a click left of it steps back."""
    x, _, w, _ = create_layout(title.cols, title.rows)["side"]
    return x + w - 10


def item_rows(title: Title) -> list[tuple[int, int, int]]:
    """(y, x0, x1) of each choice on the current screen, for the mouse."""
    cols, rows = title.cols, title.rows
    if title.screen == "main":
        y0 = main_layout(rows)["items"]
        return [(y0 + 2 * i, cols // 2 - 12, cols // 2 + 12) for i in range(len(ITEMS))]
    if title.screen == "create":
        lay = create_layout(cols, rows)
        y0, mid = lay["rows"], lay["mid"]
        return [(y0 + 2 * i, mid - 16, mid + 16) for i in range(len(CREATE_ROWS))]
    if title.screen == "updates":
        lay = updates_layout(cols, rows)
        return [(lay["choices_y"], x0, x1) for x0, x1 in lay["choices"]]
    return []


def updates_layout(cols: int, rows: int) -> dict:
    """Where the Updates box goes: the notes, then the status line and the choices in a row."""
    w = min(cols - 6, UPDATES_W)
    h = max(14, rows - 6)
    x, y = (cols - w) // 2, 2
    labels = [f"  {r}  " for r in UPDATE_ROWS]
    total = sum(len(lab) for lab in labels) + 4 * (len(labels) - 1)
    cx, choices = (cols - total) // 2, []
    for lab in labels:
        choices.append((cx, cx + len(lab)))
        cx += len(lab) + 4
    return {"x": x, "y": y, "w": w, "h": h, "notes_y": y + 2, "notes_rows": h - 9,
            "status_y": y + h - 6, "choices_y": y + h - 3, "choices": choices}


# ----------------------------------------------------------------- drawing

def centred(console, y: int, text: str, fg, bg=None, mid: int | None = None) -> None:
    """Text centred on the screen, or on column `mid`."""
    mid = console.width // 2 if mid is None else mid
    console.print(max(0, mid - len(text) // 2), y, text, fg=fg, bg=bg)


def key_text(line: str) -> list[tuple[str, bool]]:
    """A hint line split into (text, is a key) pieces: [Key] marks a key."""
    out = []
    while line:
        start = line.find("[")
        if start < 0:
            out.append((line, False))
            break
        end = line.index("]", start)
        if start:
            out.append((line[:start], False))
        out.append((f" {line[start + 1: end]} ", True))
        line = line[end + 1:]
    return out


def hint_width(line: str) -> int:
    return sum(len(text) for text, _ in key_text(line))


def draw_hint(console, y: int, line: str, mid: int | None = None) -> None:
    """A line of keys and what they do, centred (on column `mid`), with the keys picked out."""
    mid = console.width // 2 if mid is None else mid
    x = max(0, mid - hint_width(line) // 2)
    for text, key in key_text(line):
        if key:
            console.print(x, y, text, fg=KEY_FG, bg=KEY_BG)
        else:
            console.print(x, y, text, fg=DIM)
        x += len(text)


def draw_backdrop(console, world: World, seconds: float) -> None:
    """A world drifting slowly by behind everything, dimmed right down."""
    w, h = console.width, console.height
    xs = (np.arange(w) + int(seconds * 1.5)) % world.width
    ys = (np.arange(h) + (world.height - h) // 2) % world.height
    biome = world.biome[xs[:, None], ys[None, :]]
    river = world.river[xs[:, None], ys[None, :]]
    ch, fg, bg = B.CHAR[biome].copy(), B.FG[biome].copy(), B.BG[biome].copy()
    ch[river], fg[river] = ord("~"), (90, 150, 235)
    cx = np.abs(np.arange(w) - w / 2)[:, None] / (w / 2)
    cy = np.abs(np.arange(h) - h / 2)[None, :] / (h / 2)
    dim = (0.1 + 0.16 * np.clip(np.maximum(cx * 1.1, cy * 0.6), 0, 1))[..., None]   # darkest behind the words
    console.rgb["ch"] = ch
    console.rgb["fg"] = np.clip(fg * dim, 0, 255).astype(np.uint8)
    console.rgb["bg"] = np.clip(bg * dim * 0.8, 0, 255).astype(np.uint8)


def draw_heading(console, y: int) -> None:
    """The title in purple, the subtitle in white, between two rules."""
    rule = "═" * 18 + " ♦ " + "═" * 18
    centred(console, y, rule, DEEP_PURPLE)
    centred(console, y + 1, GAME_TITLE, PURPLE)
    centred(console, y + 3, SUBTITLE, WHITE)
    centred(console, y + 4, rule, DEEP_PURPLE)


def draw_choices(console, items: list[str], cursor: int, y0: int, values: dict | None = None,
                 mid: int | None = None, focused: bool = True) -> None:
    mid = console.width // 2 if mid is None else mid
    for i, item in enumerate(items):
        y = y0 + 2 * i
        text = item + (values or {}).get(item, "")
        if i == cursor and focused:
            label = f"►  {text}  ◄"
            x = mid - len(label) // 2
            console.draw_rect(x - 2, y, len(label) + 4, 1, ord(" "), bg=PICKED_BG)
            console.print(x, y, label, fg=PICKED_FG, bg=PICKED_BG)
        else:
            centred(console, y, text, PICKED_FG if i == cursor else TEXT, mid=mid)


def draw_footer(console) -> None:
    """The version at the bottom, and who made it beside it."""
    y = console.height - 2
    version = f"Version {__version__}"
    console.print(2, y, version, fg=DIM)
    console.print(2 + len(version) + 4, y, CREATOR, fg=DARK_GREY)


def draw_title(console, title: Title, seconds: float) -> None:
    title.cols, title.rows = console.width, console.height
    console.clear()
    draw_backdrop(console, title.world(BACKDROP_SEED), seconds)
    if title.screen == "create":
        draw_create(console, title)
    elif title.screen == "about":
        draw_about(console)
    elif title.screen == "updates":
        draw_updates(console, title)
    else:
        lay = main_layout(console.height)
        draw_heading(console, lay["title"])
        draw_choices(console, ITEMS, title.cursor, lay["items"])
        y = lay["hints"]
        for line in MENU_HINTS:
            draw_hint(console, y, line)
            y += 1
    draw_footer(console)


def world_preview(world: World, pw: int, ph: int) -> np.ndarray:
    """The whole world as a (pw, 2 ph, 3) picture: biomes, rivers, and where people live."""
    xs = (np.arange(pw) * world.width // pw)
    ys = (np.arange(2 * ph) * world.height // (2 * ph))
    biome = world.biome[xs[:, None], ys[None, :]]
    pic = B.BG[biome] * 0.45 + B.FG[biome] * 0.55
    river = world.river[xs[:, None], ys[None, :]]
    pic[river] = (70, 120, 220)
    for s in world.sites:
        px, py = s.x * pw // world.width, s.y * 2 * ph // world.height
        if s.kind in ("city", "town", "village", "inn", "fort"):
            pic[px, py] = SITE_KINDS[s.kind][1]
    live = world.tweaks.index("Eruptions") >= TW.ACTIVE
    for v in world.volcanoes:
        px, py = v.x * pw // world.width, v.y * 2 * ph // world.height
        if world.biome[v.x, v.y] == B.VOLCANO:
            pic[px, py] = (255, 110, 40) if live else (200, 90, 70)
    return pic


def draw_create(console, title: Title) -> None:
    from .hud import half_blocks
    lay = create_layout(console.width, console.height)
    mid, area = lay["mid"], lay["area"]
    draw_side(console, title, lay)
    centred(console, lay["title"], "Create a World", PURPLE, mid=mid)
    centred(console, lay["title"] + 1, "Every seed makes its own world; the same seed, the same world."[:area], DIM,
            mid=mid)
    y, pw, ph = lay["preview"]
    x = mid - pw // 2
    console.draw_frame(x - 1, y - 1, pw + 2, ph + 2, fg=BOX_BORDER, bg=BOX_BG)
    seed = title.seed
    if seed is None:
        console.draw_rect(x, y, pw, ph, ord(" "), bg=BOX_BG)
        centred(console, y + ph // 2, "Type a seed, or leave it empty for a random world"[:pw], DIM, BOX_BG, mid=mid)
    else:
        world = title.world(seed, title.history, title.tweaks)
        half_blocks(console, x, y, world_preview(world, pw, ph))
        kinds = [s.kind for s in world.sites]
        stats = (f"{kinds.count('town')} towns, {kinds.count('village')} villages, {kinds.count('inn')} inns, "
                 f"{kinds.count('ruins') + kinds.count('cave') + kinds.count('tower')} ruins, caves and towers")
        centred(console, lay["stats"], stats[:area], TEXT, mid=mid)
        start = next((s for s in world.sites if s.kind == "town"), None) or \
            next((s for s in world.sites if s.settled), None)
        where = []
        spawn = start_spot(world, title.spawn)
        if spawn is not None:
            where.append(f"You start at {region_title(world, *spawn)}")
            console.print(x + spawn[0] * pw // world.width, y + spawn[1] * ph // world.height, "X",
                          fg=(255, 255, 255), bg=(150, 30, 30))
        elif start is not None:
            where.append(f"You start in {start.name}")
        if world.volcanoes:
            n = len(world.volcanoes)
            where.append(f"{n} {world.volcanoes[0].activity(title.tweaks.index('Eruptions'))} volcano{'es' if n != 1 else ''}")
        centred(console, lay["start"], "   ".join(where)[:area], TEXT, mid=mid)
        hovered = title.map_region(*title.mouse) if title.mouse is not None else None
        if lay["view"] is not None:            # the Region view: the region pointed at, or where you start
            viewed = hovered or spawn or ((start.x, start.y) if start is not None else None)
            draw_view(console, title, world, lay["view"], viewed, hovered is None and viewed == spawn,
                      hovered is None and spawn is None)
        elif hovered is not None:              # no room for it: the info beside the pointer
            draw_region_info(console, describe_region(world, *hovered), *title.mouse)
    shown = (title.seed_text or "random") + ("_" if CREATE_ROWS[title.cursor] == "Seed" and not title.side else "")
    change = eras.CHANGES[title.change]
    year = eras.START_YEARS[title.year]
    era = f"Year {year:,}: " + (f"{eras.years_text(year - 1)} {change.name.lower()}, {change.blurb}" if year > 1
                                else "a new world, no ages behind it yet")
    centred(console, lay["era"], era[:area], DIM, mid=mid)
    draw_choices(console, CREATE_ROWS, title.cursor, lay["rows"],
                 {"Seed": f":  {shown}", "Year": f":  {year:,}", "Change": f":  {change.name}"},
                 mid=mid, focused=not title.side)
    for i, line in enumerate(CREATE_HINTS):
        draw_hint(console, lay["hints"] + i, line, mid=mid)


def draw_side(console, title: Title, lay: dict) -> None:
    """The World settings bar: each setting and its step, Defaults, and what the picked one does."""
    x, y, w, h = lay["side"]
    console.draw_frame(x, y, w, h, fg=BOX_BORDER, bg=BOX_BG)
    console.print(x + (w - 16) // 2, y, " World settings ", fg=PURPLE if title.side else DIM, bg=BOX_BG)
    changed = title.tweaks.changed()
    note = f"{len(changed)} changed" if changed else "all at their usual"
    console.print(x + 2, y + 1, note[: w - 4], fg=DIM, bg=BOX_BG)
    rows = side_rows(title)
    for i, (ry, x0, x1) in enumerate(rows):
        row = SIDE_ROWS[i]
        picked = title.side and i == title.side_cursor
        bg = PICKED_BG if picked else BOX_BG
        if picked:
            console.draw_rect(x0, ry, x1 - x0, 1, ord(" "), bg=bg)
        if row == "Defaults":
            label = "Reset to defaults"
            console.print(x + (w - len(label)) // 2, ry, label, fg=PICKED_FG if picked else TEXT, bg=bg)
            continue
        console.print(x + 2, ry, row, fg=PICKED_FG if picked else TEXT, bg=bg)
        step = title.tweaks.step_name(row)
        value = f"◄ {step} ►" if picked else step
        off_default = row in changed
        console.print(x + w - 2 - len(value), ry, value, bg=bg,
                      fg=PICKED_FG if picked else (KEY_FG if off_default else DIM))
    blurb_y = rows[-1][0] + 2
    if title.side and SIDE_ROWS[title.side_cursor] != "Defaults":
        text = TW.BY_NAME[SIDE_ROWS[title.side_cursor]].blurb.capitalize() + "."
    elif title.side:
        text = "Every setting back to its usual step."
    else:
        text = "[Tab] or the mouse to change these."
    for k, line in enumerate(textwrap.wrap(text, w - 4)[: max(0, y + h - 1 - blurb_y)]):
        console.print(x + 2, blurb_y + k, line, fg=DIM, bg=BOX_BG)


# ----------------------------------------------------------------- what's in a region

# What you'll find on the ground in each biome (game/localgen.py's recipes, in words).
LAND = {
    B.DEEP_OCEAN: "open water, far from shore",
    B.OCEAN: "sea, shallows near the coast",
    B.LAKE: "fresh water, shallow round the edge",
    B.BEACH: "sand and dune grass, a few rocks",
    B.GLACIER: "snow and ice, the odd boulder",
    B.TUNDRA: "frozen dirt, snow patches, low bushes",
    B.TAIGA: "pine forest, bushes, grassy clearings",
    B.STEPPE: "dry grass, patches of green, bushes",
    B.GRASSLAND: "grass, tall grass, copses of trees",
    B.SHRUBLAND: "dirt, dry grass, thick bushes",
    B.FOREST: "broadleaf woods, bushes, clearings",
    B.SWAMP: "mud, pools, reeds, swamp trees",
    B.DESERT: "sand, bare dirt, scattered rocks",
    B.SAVANNA: "dry grass, bushes, lone trees",
    B.JUNGLE: "dense jungle trees, tall grass, bushes",
    B.HILLS: "grass, dirt and scree, trees, boulders",
    B.MOUNTAINS: "scree, snow, cliffs of rock",
    B.PEAKS: "snow, ice, sheer rock",
    B.VOLCANO: "basalt, ash and scree; a crater at the top",
    B.LAVA_FIELD: "black basalt, boulders",
    B.PASTURE: "open grass, grazing herds, hardly a tree",
    B.DOWNS: "rolling grassy hills, a few rocks, hardly a tree",
}
RAIN_WORDS = [(0.2, "arid"), (0.35, "dry"), (0.55, "moderate rain"), (0.75, "wet"), (2.0, "very wet")]


def describe_region(world: World, x: int, y: int) -> list[str]:
    """A region of a world, for the pointer over a map: what's there and what it's like."""
    biome = int(world.biome[x, y])
    lines = []
    site = world.site_at.get((x, y))
    if site is not None:
        lines.append(f"{site.name}, {site.kind}{' (port)' if site.port else ''}")
    volcano = world.volcano_at.get((x, y))
    eruptions = world.tweaks.index("Eruptions")
    if volcano is not None:
        lines.append(f"{volcano.name}, {volcano.activity(eruptions)}")
    lines.append(B.BIOMES[biome].name + "".join(f", {t}" for t, on in (("river", world.river[x, y]),
                                                                         ("road", world.road[x, y])) if on))
    land = LAND.get(biome, "")
    if biome == B.LAVA_FIELD:
        land += ", molten in places" if eruptions >= TW.ACTIVE else ", grown over with grass"
    if land:
        lines.append(land[0].upper() + land[1:])
    e = float(world.elevation[x, y])
    if biome in B.WATER:
        lines.append(f"Depth {max(0.0, -e):.0f} m" if e < 0 else "Lake")
    else:
        rain = next(word for limit, word in RAIN_WORDS if world.moisture[x, y] < limit)
        lines.append(f"Alt {e:.0f} m, {world.temperature[x, y]:.0f}°C a year, {rain}")
    extras = []
    if world.spring is not None and world.spring[x, y]:
        extras.append("a spring")
    if world.aquifer is not None and world.aquifer[x, y] > 0.6 and biome not in B.WATER:
        extras.append("groundwater close below")
    if world.ash is not None and world.ash[x, y] > 0.25:
        extras.append("fresh ash")
    if extras:
        lines.append(", ".join(extras).capitalize())
    return lines


def draw_region_info(console, lines: list[str], mx: int, my: int) -> None:
    """A small box of region info beside the pointer, kept on the screen."""
    w = max(len(line) for line in lines) + 4
    h = len(lines) + 2
    x = mx + 2 if mx + 2 + w <= console.width else mx - 1 - w
    y = min(max(0, my + 1), console.height - h)
    x = max(0, x)
    console.draw_frame(x, y, w, h, fg=BOX_BORDER, bg=BOX_BG)
    for i, line in enumerate(lines):
        console.print(x + 2, y + 1 + i, line[: w - 4], fg=PICKED_FG if i == 0 else TEXT, bg=BOX_BG)


def region_title(world: World, x: int, y: int) -> str:
    site = world.site_at.get((x, y))
    return site.name if site is not None else f"the {B.BIOMES[world.biome[x, y]].name.lower()} ({x}, {y})"


def region_picture(tiles: np.ndarray, w: int, h: int) -> tuple[np.ndarray, int]:
    """A local map shrunk to fit w x h cells: each cell shows a block of tiles, by its middle,
    except that walls, streets and roads show through, so towns and ways stay in sight.
    Returns the tile per cell and the block size."""
    tw, th = tiles.shape
    step = max(-(-tw // w), -(-th // h))
    cw, ch = tw // step, th // step
    blocks = tiles[: cw * step, : ch * step].reshape(cw, step, ch, step).transpose(0, 2, 1, 3).reshape(cw, ch, -1)
    out = blocks[:, :, (step // 2) * step + step // 2].copy()
    import game.tiles as T
    for shows in ([T.ROAD, T.PATH, T.BRIDGE], [T.STREET, T.FLAGSTONES], [T.WALL, T.STONE_WALL]):
        mask = np.isin(blocks, shows)
        has = mask.any(axis=2)
        first = np.argmax(mask, axis=2)
        out[has] = np.take_along_axis(blocks, first[..., None], axis=2)[..., 0][has]
    return out, step


def draw_view(console, title: Title, world: World, box, spot, is_spawn: bool, is_default: bool) -> None:
    """The Region view: the region close up, and what's there."""
    import game.tiles as T
    x, y, w, h = box
    console.draw_frame(x, y, w, h, fg=BOX_BORDER, bg=BOX_BG)
    console.print(x + (w - 8) // 2, y, " Region ", fg=PURPLE, bg=BOX_BG)
    if spot is None:
        console.print(x + 2, y + 2, "Point at the map"[: w - 4], fg=DIM, bg=BOX_BG)
        return
    rx, ry = spot
    console.print(x + 2, y + 1, region_title(world, rx, ry)[: w - 4], fg=PICKED_FG, bg=BOX_BG)
    info = describe_region(world, rx, ry)
    if world.site_at.get((rx, ry)) is not None:
        info = info[1:]                      # the name's already up top
    note = "Where you'll start" if is_spawn else "The first town: you start here" if is_default \
        else "Left click: start here"
    lines = [line for raw in info for line in textwrap.wrap(raw, w - 4)]
    pic_h = max(4, h - 5 - len(lines) - 2)
    level = title.region_map(world, rx, ry)
    pic, _ = region_picture(level.tiles, w - 2, pic_h)
    pw, ph = pic.shape
    px = x + 1 + (w - 2 - pw) // 2
    console.rgb["ch"][px: px + pw, y + 3: y + 3 + ph] = T.CHAR[pic]
    console.rgb["fg"][px: px + pw, y + 3: y + 3 + ph] = T.FG[pic].astype(np.uint8)
    console.rgb["bg"][px: px + pw, y + 3: y + 3 + ph] = T.BG[pic].astype(np.uint8)
    ty = y + 3 + ph + 1
    for k, line in enumerate(lines[: max(0, y + h - 3 - ty)]):
        console.print(x + 2, ty + k, line, fg=TEXT, bg=BOX_BG)
    console.print(x + 2, y + h - 2, note[: w - 4], fg=KEY_FG if is_spawn else DIM, bg=BOX_BG)


def draw_about(console) -> None:
    width = min(console.width - 6, 76)
    paras = [textwrap.wrap(p, width - 6) for p in ABOUT]
    h = 9 + sum(len(p) + 1 for p in paras) + 2
    x, y = (console.width - width) // 2, max(1, (console.height - h) // 2 - 1)
    console.draw_frame(x, y, width, h, fg=BOX_BORDER, bg=BOX_BG)
    console.print(x + (width - 7) // 2, y, " About ", fg=PURPLE, bg=BOX_BG)
    centred(console, y + 2, GAME_TITLE, PURPLE, BOX_BG)
    centred(console, y + 3, SUBTITLE, WHITE, BOX_BG)
    row = y + 5
    for lines in paras:
        for line in lines:
            console.print(x + 3, row, line, fg=TEXT, bg=BOX_BG)
            row += 1
        row += 1
    centred(console, row, f"Version {__version__}", DIM, BOX_BG)
    centred(console, row + 1, CREATOR, DARK_GREY, BOX_BG)
    draw_hint(console, y + h - 2, "[Esc] [Enter] back")


def draw_updates(console, title: Title) -> None:
    """What's new in each version, scrolling, and below it the update check."""
    lay = updates_layout(console.width, console.height)
    x, y, w, h = lay["x"], lay["y"], lay["w"], lay["h"]
    console.draw_frame(x, y, w, h, fg=BOX_BORDER, bg=BOX_BG)
    console.print(x + (w - 9) // 2, y, " Updates ", fg=PURPLE, bg=BOX_BG)
    notes = updates.lines(w - 6)
    shown = lay["notes_rows"]
    title.notes_shown = shown
    title.scroll_notes(0)
    for i, (text, kind) in enumerate(notes[title.notes_scroll: title.notes_scroll + shown]):
        fg = PURPLE if kind == "head" else TEXT
        console.print(x + 3, lay["notes_y"] + i, text, fg=fg, bg=BOX_BG)
    if len(notes) > shown:
        size = max(1, shown * shown // len(notes))
        start = round(title.notes_scroll * (shown - size) / max(1, len(notes) - shown))
        for i in range(shown):
            thumb = start <= i < start + size
            console.print(x + w - 2, lay["notes_y"] + i, "█" if thumb else "│", fg=PICKED_FG if thumb else DARK_GREY,
                          bg=BOX_BG)
    console.draw_rect(x + 1, lay["status_y"] - 1, w - 2, 1, ord("─"), fg=BOX_BORDER, bg=BOX_BG)
    for i, line in enumerate(textwrap.wrap(title.checker.status, w - 6)[:2]):
        centred(console, lay["status_y"] + i, line, WHITE if not title.checker.busy else DIM, BOX_BG)
    for i, ((x0, x1), row) in enumerate(zip(lay["choices"], UPDATE_ROWS)):
        picked = i == title.cursor
        label = f"  {row}  "
        console.print(x0, lay["choices_y"], label, fg=PICKED_FG if picked else TEXT,
                      bg=PICKED_BG if picked else BOX_BG)
    draw_hint(console, y + h - 1, "[←] [→] choose   [Enter] select   [PgUp] [PgDn] scroll   [Esc] back")
