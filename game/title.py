"""The title screen: what you see before a game, and the screens it leads to.

    New Game         a random world, straight away
    Create a World   pick a seed (type one, or roll one) and see the world it makes first
    Dev Arena        the 256 x 256 test ground with one of everything (game/arena.py)
    Options          the display options (game/options.py)
    About            what the game is, and who made it
    Quit Game

Under the choices are the keys for the menus and for playing, the keys picked out in colour.
Up/Down (or W/S) choose, Enter picks, Esc goes back; the mouse points and clicks. Behind it
all a world drifts by.

This module keeps the title screen's state and draws it; main.py starts whatever it picks.
"""
from __future__ import annotations

import random
import textwrap

import numpy as np
from tcod.event import KeySym, Modifier

from . import __version__
from . import biomes as B
from .worldgen import SITE_KINDS, World, generate

GAME_TITLE = "Gathering to Aevum: The Necromancer's Key"
SUBTITLE = "Chapter II: Wandering the Mundane"
CREATOR = "Created by: bsodcat"
ITEMS = ["New Game", "Create a World", "Dev Arena", "Options", "About", "Quit Game"]
CREATE_ROWS = ["Seed", "Random seed", "Begin", "Back"]
MOST_DIGITS = 9
BACKDROP_SEED = 7

PURPLE, DEEP_PURPLE = (182, 102, 255), (95, 55, 140)
WHITE, TEXT, DIM, DARK_GREY = (255, 255, 255), (200, 200, 205), (135, 135, 145), (85, 85, 92)
KEY_FG, KEY_BG = (255, 215, 110), (52, 42, 70)
PICKED_FG, PICKED_BG = (255, 220, 120), (40, 32, 56)
BOX_BG, BOX_BORDER = (12, 10, 18), (95, 70, 130)

# What the keys do, under the choices. [Key] is drawn picked out; the rest is plain text.
MENU_HINTS = ["[↑] [↓] or [W] [S] choose   [Enter] select   [Esc] back   [Mouse] point and click"]
PLAY_HINTS = [
    "[Arrows] [WASD] [Numpad] move    [.] wait an hour    [Z] rest 8 hours",
    "[Enter] [>] go in, stairs down    [<] stairs up, back to the world",
    "[V] treetops    [Tab] right panel    [C] stats    [O] overlays    [M] reveal map",
    "Hold [Right mouse] walk there    [F11] fullscreen    [Esc] pause menu",
]
CREATE_HINTS = ["[0]-[9] type a seed   [Backspace] erase   [R] random seed   [Enter] select   [Esc] back"]
ABOUT = [
    "Wander a world made fresh from a single number: mountains, rivers and lakes, eighteen "
    "biomes, and towns, villages, roadside inns, watchtowers, ruins and caves joined by roads.",
    "Travel the land a region at a time, or step down and walk any part of it tile by tile. "
    "Seasons turn and weather drifts across the land; the cold, the rain and the wind wear on "
    "you. Townsfolk keep their trades and their hours, fields ripen, and herds graze.",
    "Made with Python, python-tcod and numpy.",
]


def random_seed() -> str:
    return str(random.randrange(1, 10 ** MOST_DIGITS))


class Title:
    """Which title screen is up ("main", "create" or "about") and what's picked on it."""

    def __init__(self, menu):
        self.menu = menu                  # the options screen, shared with the game
        self.screen = "main"
        self.cursor = 0
        self.seed_text = random_seed()
        self.cols, self.rows = 120, 45    # the screen in tiles, as last drawn
        self._worlds: dict[int, World] = {}

    def show(self, screen: str) -> None:
        self.screen, self.cursor = screen, 0

    # ------------------------------------------------------------- worlds

    def world(self, seed: int) -> World:
        """The world from a seed, kept so the preview and the game share it."""
        if seed not in self._worlds:
            self._worlds = {k: v for k, v in self._worlds.items() if k == BACKDROP_SEED}
            self._worlds[seed] = generate(seed)
        return self._worlds[seed]

    @property
    def seed(self) -> int | None:
        return int(self.seed_text) if self.seed_text else None

    # ------------------------------------------------------------- choosing

    def items(self) -> list[str]:
        return ITEMS if self.screen == "main" else CREATE_ROWS if self.screen == "create" else []

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
        elif item == "Quit Game":
            return ("quit",)
        elif item == "Random seed":
            self.seed_text = random_seed()
        elif item in ("Begin", "Seed"):
            seed = self.seed if self.seed is not None else int(random_seed())
            return ("new", seed, self.world(seed))
        elif item == "Back":
            self.show("main")
            self.cursor = ITEMS.index("Create a World")
        return None

    def back(self) -> None:
        if self.screen != "main":
            came_from = ITEMS.index("Create a World" if self.screen == "create" else "About")
            self.show("main")
            self.cursor = came_from

    def handle_key(self, sym, mod: int = 0) -> tuple | None:
        items = self.items()
        if sym == KeySym.ESCAPE:
            self.back()
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
            self.edit_seed(sym)
        return None

    def edit_seed(self, sym) -> None:
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

    def hover(self, sx: int, sy: int) -> None:
        i = self.row_at(sx, sy)
        if i is not None:
            self.cursor = i

    def click(self, sx: int, sy: int) -> tuple | None:
        if self.screen == "about":
            self.back()
            return None
        i = self.row_at(sx, sy)
        if i is None:
            return None
        self.cursor = i
        return self.activate()


DIGITS = {getattr(KeySym, f"N{i}"): str(i) for i in range(10)}   # the number row (the numpad moves)


def digit_of(sym) -> str | None:
    return DIGITS.get(sym)


# ----------------------------------------------------------------- where things go

def main_layout(rows: int) -> dict:
    hints = len(MENU_HINTS) + len(PLAY_HINTS) + 2
    block = 5 + 2 + (2 * len(ITEMS) - 1) + 2 + hints
    spare = rows - 3 - block
    gap = 2 if spare >= 8 else 1
    top = max(1, (spare - 2 * (gap - 1)) // 3)
    title_y = top
    items_y = title_y + 5 + gap
    hints_y = items_y + 2 * len(ITEMS) - 1 + gap + 1
    return {"title": title_y, "items": items_y, "hints": hints_y}


def create_layout(cols: int, rows: int) -> dict:
    pw = min(cols - 8, 128)
    ph = pw // 4                          # half blocks: square pixels, and the world is 2:1
    room = rows - 19                      # the rest: headings, stats, choices, keys and the footer
    if ph > room:
        ph = max(4, room)
        pw = ph * 4
    top = max(1, (rows - (ph + 19)) // 2)
    return {"title": top, "preview": (top + 3, pw, ph), "stats": top + 5 + ph, "rows": top + 7 + ph,
            "hints": top + 7 + ph + 2 * len(CREATE_ROWS)}


def item_rows(title: Title) -> list[tuple[int, int, int]]:
    """(y, x0, x1) of each choice on the current screen, for the mouse."""
    cols, rows = title.cols, title.rows
    if title.screen == "main":
        y0 = main_layout(rows)["items"]
        return [(y0 + 2 * i, cols // 2 - 12, cols // 2 + 12) for i in range(len(ITEMS))]
    if title.screen == "create":
        y0 = create_layout(cols, rows)["rows"]
        return [(y0 + 2 * i, cols // 2 - 16, cols // 2 + 16) for i in range(len(CREATE_ROWS))]
    return []


# ----------------------------------------------------------------- drawing

def centred(console, y: int, text: str, fg, bg=None) -> None:
    console.print(max(0, (console.width - len(text)) // 2), y, text, fg=fg, bg=bg)


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


def draw_hint(console, y: int, line: str) -> None:
    """A line of keys and what they do, centred, with the keys picked out."""
    x = max(0, (console.width - hint_width(line)) // 2)
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


def draw_choices(console, items: list[str], cursor: int, y0: int, values: dict | None = None) -> None:
    for i, item in enumerate(items):
        y = y0 + 2 * i
        text = item + (values or {}).get(item, "")
        if i == cursor:
            label = f"►  {text}  ◄"
            x = (console.width - len(label)) // 2
            console.draw_rect(x - 2, y, len(label) + 4, 1, ord(" "), bg=PICKED_BG)
            console.print(x, y, label, fg=PICKED_FG, bg=PICKED_BG)
        else:
            centred(console, y, text, TEXT)


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
    else:
        lay = main_layout(console.height)
        draw_heading(console, lay["title"])
        draw_choices(console, ITEMS, title.cursor, lay["items"])
        y = lay["hints"]
        for line in MENU_HINTS:
            draw_hint(console, y, line)
            y += 1
        y += 1
        centred(console, y, "Playing", DIM)
        for line in PLAY_HINTS:
            y += 1
            draw_hint(console, y, line)
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
        if s.kind in ("town", "village", "inn"):
            pic[px, py] = SITE_KINDS[s.kind][1]
    return pic


def draw_create(console, title: Title) -> None:
    from .hud import half_blocks
    lay = create_layout(console.width, console.height)
    centred(console, lay["title"], "Create a World", PURPLE)
    centred(console, lay["title"] + 1, "Every seed makes its own world; the same seed, the same world.", DIM)
    y, pw, ph = lay["preview"]
    x = (console.width - pw) // 2
    console.draw_frame(x - 1, y - 1, pw + 2, ph + 2, fg=BOX_BORDER, bg=BOX_BG)
    seed = title.seed
    if seed is None:
        console.draw_rect(x, y, pw, ph, ord(" "), bg=BOX_BG)
        centred(console, y + ph // 2, "Type a seed, or leave it empty for a random world", DIM, BOX_BG)
    else:
        world = title.world(seed)
        half_blocks(console, x, y, world_preview(world, pw, ph))
        kinds = [s.kind for s in world.sites]
        start = next((s for s in world.sites if s.kind == "town"), None) or \
            next((s for s in world.sites if s.settled), None)
        stats = (f"{kinds.count('town')} towns, {kinds.count('village')} villages, {kinds.count('inn')} inns, "
                 f"{kinds.count('ruins') + kinds.count('cave') + kinds.count('tower')} ruins, caves and towers")
        if start is not None:
            stats += f"   You start in {start.name}"
        centred(console, lay["stats"], stats, TEXT)
    shown = (title.seed_text or "random") + ("_" if CREATE_ROWS[title.cursor] == "Seed" else "")
    draw_choices(console, CREATE_ROWS, title.cursor, lay["rows"], {"Seed": f":  {shown}"})
    for i, line in enumerate(CREATE_HINTS):
        draw_hint(console, lay["hints"] + i, line)


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
