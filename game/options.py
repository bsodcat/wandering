"""Settings, and the pause menu and options screen that change them.

Esc opens the pause menu (Resume, Options, Quit). The options screen sets:

- Display: windowed or fullscreen (Alt+Enter or F11 toggles it any time).
- Resolution: the 4:3 size the game is drawn at. Windowed, it's the size of the window;
  fullscreen, the game is drawn at this size and scaled up to fill the screen, with black
  bars at the sides.
- Font: the classic Terminal bitmap font, or a TrueType font drawn at any size.
- Font size: the size of one tile. "Auto" picks the tile that fills the resolution exactly,
  pixel for pixel, which is the sharpest. Anything else is drawn at that size and scaled.

Changes apply at once and are saved, to %APPDATA%/newrogue/settings.json (or ~/.newrogue).
This module is only the state; game/display.py does the window and game/hud.py draws the menu.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass

from tcod.event import KeySym, Modifier

from .ui import SCREEN_H, SCREEN_W

FONT_DIR = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
FONTS = {   # name: (file, bitmap?) - bitmap fonts come in fixed sizes and are scaled to others
    "Terminal": ("8514oem.fon", True),
    "Consolas": ("consola.ttf", False),
    "Lucida Console": ("lucon.ttf", False),
    "Courier New": ("cour.ttf", False),
}
RESOLUTIONS = [(800, 600), (960, 720), (1024, 768), (1200, 900), (1280, 960), (1440, 1080),
               (1600, 1200), (1920, 1440), (2048, 1536)]
FONT_SIZES = ["Auto", (8, 16), (10, 20), (12, 24), (14, 28), (16, 32), (20, 40)]   # all 1:2, so 4:3
DISPLAYS = ["Windowed", "Fullscreen"]


def settings_path() -> str:
    base = os.environ.get("APPDATA")
    return os.path.join(base, "newrogue", "settings.json") if base else \
        os.path.join(os.path.expanduser("~"), ".newrogue", "settings.json")


def font_path(name: str) -> str:
    return os.path.join(FONT_DIR, FONTS[name][0])


def available_fonts() -> list[str]:
    return [name for name in FONTS if os.path.exists(font_path(name))] or ["Terminal"]


@dataclass
class Settings:
    fullscreen: bool = False
    resolution: tuple = (1200, 900)
    font: str = "Terminal"
    font_size: object = "Auto"        # "Auto" or (width, height)

    def cell(self) -> tuple[int, int]:
        """The size of one tile in pixels: the chosen size, or for Auto the biggest 1:2 tile
        that fits the resolution."""
        if self.font_size != "Auto":
            return tuple(self.font_size)
        w = max(4, min(self.resolution[0] // SCREEN_W, self.resolution[1] // (2 * SCREEN_H)))
        return w, 2 * w

    def frame(self) -> tuple[int, int]:
        """The size the screen is drawn at before it's scaled to the resolution."""
        w, h = self.cell()
        return SCREEN_W * w, SCREEN_H * h

    def save(self, path: str | None = None) -> None:
        path = path or settings_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=2)

    @classmethod
    def load(cls, path: str | None = None) -> Settings:
        """The saved settings, or the defaults if there are none (or they don't make sense)."""
        path = path or settings_path()
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            s = cls(fullscreen=bool(data.get("fullscreen", False)),
                    resolution=tuple(data.get("resolution", (1200, 900))),
                    font=data.get("font", "Terminal"),
                    font_size=data.get("font_size", "Auto"))
        except (OSError, ValueError, TypeError):
            return cls()
        if s.resolution not in RESOLUTIONS:
            s.resolution = (1200, 900)
        if isinstance(s.font_size, list):
            s.font_size = tuple(s.font_size)
        if s.font_size not in FONT_SIZES:
            s.font_size = "Auto"
        if s.font not in FONTS:
            s.font = "Terminal"
        return s


def size_text(size) -> str:
    return "Auto" if size == "Auto" else f"{size[0]}x{size[1]}"


# ----------------------------------------------------------------- the menus

PAUSE_ITEMS = ["Resume", "Options", "Quit"]
OPTION_ROWS = ["Display", "Resolution", "Font", "Font size", "Back"]
BOX_W = 46
VALUE_X = 16                       # where a row's ◄ value ► starts, from the box's left edge


def box(rows: int) -> tuple[int, int, int, int]:
    """(x, y, width, height) of a menu box with this many rows, in the middle of the screen."""
    h = rows * 2 + 5
    return (SCREEN_W - BOX_W) // 2, (SCREEN_H - h) // 2, BOX_W, h


def row_y(rows: int, i: int) -> int:
    return box(rows)[1] + 3 + 2 * i


class Menu:
    """Which menu is open (None, "pause" or "options"), which row is picked, and the settings."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings()
        self.screen: str | None = None
        self.cursor = 0
        self.changed = False             # the display needs redoing (main.py picks this up)

    @property
    def open(self) -> bool:
        return self.screen is not None

    def items(self) -> list[str]:
        return PAUSE_ITEMS if self.screen == "pause" else OPTION_ROWS

    def show(self, screen: str | None) -> None:
        self.screen, self.cursor = screen, 0

    def value(self, row: str) -> str:
        s = self.settings
        if row == "Display":
            return DISPLAYS[s.fullscreen]
        if row == "Resolution":
            return f"{s.resolution[0]} x {s.resolution[1]}"
        if row == "Font":
            return s.font
        if row == "Font size":
            text = size_text(s.font_size)
            if s.font_size == "Auto":
                text += f" ({size_text(s.cell())})"
            if s.font == "Terminal" and s.cell() == (10, 20):
                text += " native"
            return text
        return ""

    def change(self, row: str, step: int) -> None:
        """Steps a setting to its next (or previous) choice."""
        s = self.settings

        def turn(choices, current):
            i = choices.index(current) if current in choices else 0
            return choices[(i + step) % len(choices)]

        if row == "Display":
            s.fullscreen = not s.fullscreen
        elif row == "Resolution":
            s.resolution = turn(RESOLUTIONS, s.resolution)
        elif row == "Font":
            s.font = turn(available_fonts(), s.font)
        elif row == "Font size":
            s.font_size = turn(FONT_SIZES, s.font_size)
        else:
            return
        self.changed = True

    def toggle_fullscreen(self) -> None:
        self.change("Display", 1)

    def activate(self) -> str | None:
        """Enter on the picked row. Returns "quit" to leave the game."""
        item = self.items()[self.cursor]
        if item == "Resume":
            self.show(None)
        elif item == "Options":
            self.show("options")
        elif item == "Quit":
            return "quit"
        elif item == "Back":
            self.show("pause")
        else:
            self.change(item, 1)
        return None

    def back(self) -> None:
        self.show("pause" if self.screen == "options" else None)

    def handle_key(self, sym, mod: int = 0) -> str | None:
        """A key while a menu is open. Returns "quit" to leave the game."""
        n = len(self.items())
        if sym == KeySym.ESCAPE:
            self.back()
        elif sym in (KeySym.UP, KeySym.KP_8, KeySym.W):
            self.cursor = (self.cursor - 1) % n
        elif sym in (KeySym.DOWN, KeySym.KP_2, KeySym.S):
            self.cursor = (self.cursor + 1) % n
        elif sym in (KeySym.LEFT, KeySym.KP_4, KeySym.A) and self.screen == "options":
            self.change(self.items()[self.cursor], -1)
        elif sym in (KeySym.RIGHT, KeySym.KP_6, KeySym.D) and self.screen == "options":
            self.change(self.items()[self.cursor], 1)
        elif sym in (KeySym.RETURN, KeySym.KP_ENTER, KeySym.SPACE):
            if sym == KeySym.RETURN and mod & Modifier.ALT:
                self.toggle_fullscreen()
            else:
                return self.activate()
        return None

    # ------------------------------------------------------------- the mouse

    def row_at(self, sx: int, sy: int) -> int | None:
        rows = len(self.items())
        x, _, w, _ = box(rows)
        for i in range(rows):
            if row_y(rows, i) == sy and x < sx < x + w - 1:
                return i
        return None

    def hover(self, sx: int, sy: int) -> None:
        i = self.row_at(sx, sy)
        if i is not None:
            self.cursor = i

    def click(self, sx: int, sy: int) -> str | None:
        """A left click: on a row's ◄ or ► steps that setting; anywhere else on a row picks it."""
        i = self.row_at(sx, sy)
        if i is None:
            return None
        self.cursor = i
        item = self.items()[i]
        if self.screen == "options" and item in ("Display", "Resolution", "Font", "Font size"):
            left, right = value_span(len(self.items()))
            self.change(item, -1 if left <= sx < (left + right) // 2 else 1)
            return None
        return self.activate()


def value_span(rows: int) -> tuple[int, int]:
    """The columns of an options row's "◄ value ►": the ◄ is at the first, the ► at the last."""
    x, _, w, _ = box(rows)
    return x + VALUE_X, x + w - 3
