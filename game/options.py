"""Settings, and the pause menu and options screen that change them.

Esc opens the pause menu (Resume, Options, Main menu, Quit); the title screen opens the options
screen on its own. The options screen sets:

- Display: windowed or fullscreen (Alt+Enter or F11 toggles it any time).
- Font: the classic Terminal bitmap font, or a TrueType font drawn at any size.
- Font size: the size of one tile, which sets the size the game is drawn at: 120 x 45 tiles,
  so 8x16 draws a 960x720 picture. "Auto" picks the biggest that fits your screen (Terminal
  keeps its own 10x20 whenever that fits).
- Scale: how many times bigger that picture is shown. Always a whole number, every pixel
  repeated, so small fonts stay pixel-sharp rather than smeared. "Auto" is the biggest that
  fits the screen (or the window, if you resize it). Only a font too big for the screen at 1x
  is shrunk, and that is smoothed.

Windowed, the window takes the size of the picture times the scale. Fullscreen, the picture is
centred on the screen with black around it.

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
FONT_SIZES = ["Auto", (6, 12), (8, 16), (10, 20), (12, 24), (14, 28), (16, 32), (20, 40)]   # all 1:2: 4:3
SCALES = ["Auto", 1, 2, 3, 4]
NATIVE = {"Terminal": (10, 20)}     # bitmap fonts' own size: crispest of all
SCREEN_GUESS = (1920, 1040)         # until the window says how big the screen really is
DISPLAYS = ["Windowed", "Fullscreen"]


def settings_path() -> str:
    base = os.environ.get("APPDATA")
    return os.path.join(base, "newrogue", "settings.json") if base else \
        os.path.join(os.path.expanduser("~"), ".newrogue", "settings.json")


def font_path(name: str) -> str:
    return os.path.join(FONT_DIR, FONTS[name][0])


def available_fonts() -> list[str]:
    return [name for name in FONTS if os.path.exists(font_path(name))] or ["Terminal"]


def fits(frame: tuple[int, int], area: tuple[int, int]) -> int:
    """The biggest whole-number scale at which `frame` fits in `area` (0 if not even 1x)."""
    return min(area[0] // frame[0], area[1] // frame[1])


@dataclass
class Settings:
    fullscreen: bool = False
    font: str = "Terminal"
    font_size: object = "Auto"        # "Auto" or (width, height)
    scale: object = "Auto"            # "Auto" or a whole number

    def cell(self, area: tuple[int, int] = SCREEN_GUESS) -> tuple[int, int]:
        """The size of one tile in pixels: the chosen size, or for Auto the font's own size if
        it has one that fits, else the biggest that fits `area` (the screen) at 1x."""
        if self.font_size != "Auto":
            return tuple(self.font_size)
        native = NATIVE.get(self.font)
        if native and fits(frame_of(native), area) >= 1:
            return native
        sizes = [s for s in FONT_SIZES[1:] if fits(frame_of(s), area) >= 1]
        return sizes[-1] if sizes else FONT_SIZES[1]

    def frame(self, area: tuple[int, int] = SCREEN_GUESS) -> tuple[int, int]:
        """The size the game is drawn at, before it's scaled."""
        return frame_of(self.cell(area))

    def factor(self, area: tuple[int, int]) -> int:
        """The whole-number scale to show the picture at in `area`; 0 if it doesn't fit even at
        1x (and has to be shrunk)."""
        best = fits(self.frame(area), area)
        return best if self.scale == "Auto" else min(int(self.scale), best)

    def window_size(self, area: tuple[int, int]) -> tuple[int, int]:
        """The window for this picture in `area`: the picture times the scale, or shrunk to fit."""
        fw, fh = self.frame(area)
        k = self.factor(area)
        if k >= 1:
            return fw * k, fh * k
        shrink = min(area[0] / fw, area[1] / fh)
        return int(fw * shrink), int(fh * shrink)

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
                    font=data.get("font", "Terminal"),
                    font_size=data.get("font_size", "Auto"),
                    scale=data.get("scale", "Auto"))
        except (OSError, ValueError, TypeError, AttributeError):
            return cls()
        if s.scale not in SCALES:
            s.scale = "Auto"
        if isinstance(s.font_size, list):
            s.font_size = tuple(s.font_size)
        if s.font_size not in FONT_SIZES:
            s.font_size = "Auto"
        if s.font not in FONTS:
            s.font = "Terminal"
        return s


def frame_of(cell: tuple[int, int]) -> tuple[int, int]:
    return SCREEN_W * cell[0], SCREEN_H * cell[1]


def size_text(size) -> str:
    return "Auto" if size == "Auto" else f"{size[0]}x{size[1]}"


# ----------------------------------------------------------------- the menus

PAUSE_ITEMS = ["Resume", "Options", "Main menu", "Quit"]
OPTION_ROWS = ["Display", "Font", "Font size", "Scale", "Back"]
BOX_W = 46
VALUE_X = 16                       # where a row's ◄ value ► starts, from the box's left edge


def box(rows: int, width: int = SCREEN_W, height: int = SCREEN_H) -> tuple[int, int, int, int]:
    """(x, y, width, height) of a menu box with this many rows, in the middle of a screen this
    many tiles across."""
    h = rows * 2 + 5
    return (width - BOX_W) // 2, (height - h) // 2, BOX_W, h


def row_y(rows: int, i: int, width: int = SCREEN_W, height: int = SCREEN_H) -> int:
    return box(rows, width, height)[1] + 3 + 2 * i


class Menu:
    """Which menu is open (None, "pause" or "options"), which row is picked, and the settings.
    `top` is where Back from the options goes: the pause menu in a game, or (None) closed, back
    to the title screen."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings()
        self.screen: str | None = None
        self.cursor = 0
        self.changed = False             # the display needs redoing (main.py picks this up)
        self.area = SCREEN_GUESS         # the screen space there is (game/display.py keeps it up to date)
        self.cols, self.rows = SCREEN_W, SCREEN_H   # the screen in tiles, as it's drawn
        self.shown = None                # (scale, tiles across, tiles down) as last shown, from main.py
        self.top: str | None = "pause"

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
        if row == "Font":
            return s.font
        if row == "Font size":
            cell = s.cell(self.area)
            text = size_text(s.font_size)
            if s.font_size == "Auto":
                text += f" ({size_text(cell)})"
            if NATIVE.get(s.font) == cell:
                text += " native"
            elif fits(s.frame(self.area), self.area) < 1:
                text += " too big"
            return text
        if row == "Scale":
            k = s.factor(self.area)
            shown = f"{k}x" if k >= 1 else "shrunk"
            if s.scale == "Auto":
                return f"Auto ({shown})"
            return f"{s.scale}x" + ("" if k == s.scale else f" ({shown}: fits)")
        return ""

    def note(self) -> str:
        """What the settings come to, under the options box."""
        s = self.settings
        cw, ch = s.cell(self.area)
        if self.shown is not None:
            k, cols, rows = self.shown
            if k >= 1:
                return f"{cols}x{rows} tiles of {cw}x{ch}, shown {k}x, pixel-sharp"
            return f"{cols}x{rows} tiles of {cw}x{ch}: too big, shrunk (smoothed)"
        k = s.factor(self.area)
        if k >= 1:
            return f"Tiles of {cw}x{ch}, shown {k}x, pixel-sharp"
        return f"Tiles of {cw}x{ch}: too big for the screen, shrunk (smoothed)"

    def change(self, row: str, step: int) -> None:
        """Steps a setting to its next (or previous) choice."""
        s = self.settings

        def turn(choices, current):
            i = choices.index(current) if current in choices else 0
            return choices[(i + step) % len(choices)]

        if row == "Display":
            s.fullscreen = not s.fullscreen
        elif row == "Scale":
            s.scale = turn(SCALES, s.scale)
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
        """Enter on the picked row. Returns "quit" to leave the game, "title" for the title screen."""
        item = self.items()[self.cursor]
        if item == "Resume":
            self.show(None)
        elif item == "Options":
            self.show("options")
        elif item == "Quit":
            return "quit"
        elif item == "Main menu":
            self.show(None)
            return "title"
        elif item == "Back":
            self.show(self.top)
        else:
            self.change(item, 1)
        return None

    def back(self) -> None:
        self.show(self.top if self.screen == "options" else None)

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
        x, _, w, _ = box(rows, self.cols, self.rows)
        for i in range(rows):
            if row_y(rows, i, self.cols, self.rows) == sy and x < sx < x + w - 1:
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
        if self.screen == "options" and item in ("Display", "Font", "Font size", "Scale"):
            left, right = value_span(len(self.items()), self.cols, self.rows)
            self.change(item, -1 if left <= sx < (left + right) // 2 else 1)
            return None
        return self.activate()


def value_span(rows: int, width: int = SCREEN_W, height: int = SCREEN_H) -> tuple[int, int]:
    """The columns of an options row's "◄ value ►": the ◄ is at the first, the ► at the last."""
    x, _, w, _ = box(rows, width, height)
    return x + VALUE_X, x + w - 3
