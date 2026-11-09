"""The window: fonts, fullscreen, scaling, and getting the screen onto it.

Tiles are drawn with the chosen font at exactly its size and shown at a whole-number scale,
every pixel repeated, so they stay pixel-sharp. The screen is as many tiles as fit the window
at that scale (`layout`): a bigger or wider window shows more tiles, never bigger pixels, and
the panels stay pinned to its edges. Less than a tile left over at the edges is black.

The scale is the one you chose, or for Auto the biggest at which the default 120 x 45 screen
still fits. The screen is never smaller than 80 x 30 tiles; in a window too small even for
that, the picture is shrunk to fit, smoothed.

Windowed, the window starts at the default screen's size times the scale (within the usable
part of the screen) and can then be resized, maximised or snapped to any shape. Fullscreen
fills the monitor.

Mouse positions come in as window pixels and go out as screen tiles, through the same scaling.
"""
from __future__ import annotations

import copy

import numpy as np
import tcod
import tcod.render
import tcod.sdl.render
from tcod.cffi import ffi, lib
from tcod.sdl.render import LogicalPresentation, ScaleMode

from . import fon
from .options import FONTS, Settings, available_fonts, font_path
from .ui import MIN_H, MIN_W, SCREEN_H, SCREEN_W


def scale_tile(tile: np.ndarray, w: int, h: int) -> np.ndarray:
    """A bitmap glyph resized to w x h by repeating or dropping pixels, which keeps it crisp."""
    th, tw = tile.shape
    return tile[(np.arange(h) * th // h)[:, None], (np.arange(w) * tw // w)[None, :]]


REFERENCE = "MWQ@#gjyHA"     # letters whose ink should about fill a tile
FILL = (0.92, 0.82)          # how much of a tile's width and height they should fill


def ink_box(tileset: tcod.tileset.Tileset) -> tuple[int, int, int, int]:
    """(x0, y0, x1, y1) of the ink the reference letters put down, over all of them."""
    alpha = np.stack([tileset.get_tile(ord(c))[..., 3] for c in REFERENCE]).max(axis=0)
    ys, xs = np.nonzero(alpha > 40)
    if not len(xs):
        return 0, 0, tileset.tile_width, tileset.tile_height
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def drawn_glyphs(w: int, h: int) -> dict[str, np.ndarray]:
    """Blocks, shades and single box lines drawn to meet the tile edges exactly, so bars and
    the minimap join up whatever the font. (h, w) alpha arrays."""
    full = np.full((h, w), 255, np.uint8)
    out = {"█": full, "▀": full.copy(), "▄": full.copy(), "▌": full.copy(), "▐": full.copy()}
    out["▀"][h // 2:] = 0
    out["▄"][: h // 2] = 0
    out["▌"][:, w // 2:] = 0
    out["▐"][:, : w // 2] = 0
    ys, xs = np.mgrid[:h, :w]
    for ch, keep in (("░", (xs + ys) % 4 == 0), ("▒", (xs + ys) % 2 == 0), ("▓", (xs + ys) % 4 != 0)):
        out[ch] = np.where(keep, 255, 0).astype(np.uint8)
    cx, cy = w // 2, h // 2
    arms = {"─": "lr", "│": "ud", "┼": "lrud", "├": "udr", "┤": "udl", "┬": "lrd", "┴": "lru",
            "┌": "rd", "┐": "ld", "└": "ru", "┘": "lu"}
    for ch, dirs in arms.items():
        a = np.zeros((h, w), np.uint8)
        if "l" in dirs:
            a[cy, : cx + 1] = 255
        if "r" in dirs:
            a[cy, cx:] = 255
        if "u" in dirs:
            a[: cy + 1, cx] = 255
        if "d" in dirs:
            a[cy:, cx] = 255
        out[ch] = a
    return out


def with_drawn_glyphs(tileset: tcod.tileset.Tileset) -> tcod.tileset.Tileset:
    w, h = tileset.tile_width, tileset.tile_height
    for ch, alpha in drawn_glyphs(w, h).items():
        tileset.set_tile(ord(ch), alpha)
    return tileset


def fit_truetype(path: str, w: int, h: int) -> tcod.tileset.Tileset:
    return with_drawn_glyphs(fit_letters(path, w, h))


def fit_letters(path: str, w: int, h: int) -> tcod.tileset.Tileset:
    """A TrueType font whose letters fill w x h tiles. Some fonts (Consolas) come out at half
    size from libtcod's loader, so this measures them, draws them bigger, and crops each glyph
    back to the tile around where the letters sit."""
    probe = tcod.tileset.load_truetype_font(path, w, h)
    x0, y0, x1, y1 = ink_box(probe)
    k = min(w * FILL[0] / (x1 - x0), h * FILL[1] / (y1 - y0))
    if k <= 1.05:
        return probe
    big = tcod.tileset.load_truetype_font(path, round(w * k), round(h * k))
    bx0, by0, bx1, by1 = ink_box(big)
    left = int(round((bx0 + bx1) / 2 - w / 2))
    top = int(round((by0 + by1) / 2 - h / 2))
    left = max(0, min(left, big.tile_width - w))
    top = max(0, min(top, big.tile_height - h))
    out = tcod.tileset.Tileset(w, h)
    for code in sorted(set(tcod.tileset.CHARMAP_CP437)):
        tile = big.get_tile(code)
        out.set_tile(code, np.ascontiguousarray(tile[top: top + h, left: left + w]))
    return out


def make_tileset(font: str, cell: tuple[int, int]) -> tcod.tileset.Tileset:
    """The font at this tile size: bitmap fonts use their nearest size, scaled; TrueType fonts
    are drawn at the size. Falls back to Terminal, then to libtcod's own font."""
    w, h = cell
    for name in [font] + [f for f in available_fonts() if f != font]:
        path = font_path(name)
        try:
            if FONTS[name][1]:
                fw, fh, tiles = fon.load(path, (w, h))
                tileset = tcod.tileset.Tileset(w, h)
                for code, tile in tiles.items():
                    tileset[tcod.tileset.CHARMAP_CP437[code]] = \
                        tile if (fw, fh) == (w, h) else scale_tile(tile, w, h)
                return tileset
            return fit_truetype(path, w, h)
        except Exception:
            continue
    return tcod.tileset.get_default()


TITLE_BAR = 40            # room left for the title bar and borders before they're known


def grid(output: tuple[int, int], cell: tuple[int, int], scale) -> tuple[int, int, int]:
    """(scale, tiles across, tiles down) for a window of `output` pixels: the chosen scale, or
    for Auto the biggest the default screen fits at, then as many whole tiles as fit (no fewer
    than MIN_W x MIN_H). A scale too big to leave even the smallest screen is brought down."""
    (out_w, out_h), (cw, ch) = output, cell
    if scale == "Auto":
        k = max(1, min(out_w // (cw * SCREEN_W), out_h // (ch * SCREEN_H)))
    else:
        k = int(scale)
    while k > 1 and (out_w // (cw * k) < MIN_W or out_h // (ch * k) < MIN_H):
        k -= 1
    return k, max(MIN_W, out_w // (cw * k)), max(MIN_H, out_h // (ch * k))


class Display:
    def __init__(self, settings: Settings, title: str = "newrogue"):
        self.settings = settings
        fw, fh = settings.frame()
        self.context = tcod.context.new(width=fw, height=fh, title=title, vsync=True,
                                        tileset=make_tileset(settings.font, settings.cell()),
                                        sdl_window_flags=tcod.context.SDL_WINDOW_RESIZABLE)
        self.window = self.context.sdl_window
        self.renderer = self.context.sdl_renderer
        self.font_key = None
        self.dest = (0, 0, fw, fh)          # where the picture went last frame, in output pixels
        self.cols, self.rows = SCREEN_W, SCREEN_H   # the screen in tiles, as last shown
        self.scale = 1                      # the whole-number scale last shown at (0: shrunk)
        self.sized = False                  # the window has had its starting size
        self.renderer.set_logical_presentation((0, 0), LogicalPresentation.DISABLED)
        self.apply(settings)

    def close(self) -> None:
        self.context.close()

    # ------------------------------------------------------------- the screen

    def screen_area(self, fullscreen: bool) -> tuple[int, int]:
        """The room there is for the window's insides: the whole screen when fullscreen, else
        the usable part (no taskbar) less the window's borders and title bar."""
        display = lib.SDL_GetDisplayForWindow(self.window.p)
        rect = ffi.new("SDL_Rect*")
        get = lib.SDL_GetDisplayBounds if fullscreen else lib.SDL_GetDisplayUsableBounds
        if not display or not get(display, rect):
            return (1920, 1080) if fullscreen else (1920, 1080 - TITLE_BAR)
        if fullscreen:
            return rect.w, rect.h
        top, left, bottom, right = self.window.border_size
        if top == 0:
            top = TITLE_BAR
        return rect.w - left - right, rect.h - top - bottom

    def apply(self, settings: Settings) -> None:
        """Puts the settings into effect: the font at its size, fullscreen or a window sized to
        the picture times the scale."""
        self.settings = settings
        area = self.screen_area(settings.fullscreen)
        cell = settings.cell(area)
        key = (settings.font, cell)
        if key != self.font_key:
            self.tileset = make_tileset(settings.font, cell)
            self.atlas = tcod.render.SDLTilesetAtlas(self.renderer, self.tileset)
            self.console_render = tcod.render.SDLConsoleRender(self.atlas)
            self.font_key = key
        leaving_fullscreen = self.window.fullscreen and not settings.fullscreen
        if self.window.fullscreen != settings.fullscreen:
            self.window.fullscreen = settings.fullscreen
        if not settings.fullscreen and (not self.sized or leaving_fullscreen):
            self.window.size = settings.window_size(area)     # after that, the window is yours to size
            self.sized = True
        self.area = area

    # ------------------------------------------------------------- drawing

    def layout(self) -> tuple[int, int, int]:
        """(scale, tiles across, tiles down) for the window as it is now."""
        out_w, out_h = self.renderer.output_size
        return grid((out_w, out_h), (self.tileset.tile_width, self.tileset.tile_height), self.settings.scale)

    def present(self, console: tcod.console.Console) -> None:
        texture = self.console_render.render(console)
        out_w, out_h = self.renderer.output_size
        k, _, _ = self.layout()
        w, h = texture.width * k, texture.height * k
        sharp = w <= out_w and h <= out_h
        if not sharp:                          # even the smallest screen won't fit: shrink it
            shrink = min(out_w / texture.width, out_h / texture.height)
            w, h = max(1, int(texture.width * shrink)), max(1, int(texture.height * shrink))
        self.dest = ((out_w - w) // 2, (out_h - h) // 2, w, h)
        self.cols, self.rows, self.scale = console.width, console.height, k if sharp else 0
        texture.scale_mode = ScaleMode.NEAREST if sharp else ScaleMode.LINEAR
        self.renderer.draw_color = (0, 0, 0, 255)
        self.renderer.clear()
        self.renderer.copy(texture, dest=self.dest)
        self.renderer.present()

    # ------------------------------------------------------------- the mouse

    def tile_at(self, px: float, py: float) -> tuple[float, float] | None:
        """The screen tile under a window position, or None if it's off the picture."""
        out_w, out_h = self.renderer.output_size
        win_w, win_h = self.window.size
        ox, oy = px * out_w / max(1, win_w), py * out_h / max(1, win_h)   # window points to pixels
        x, y, w, h = self.dest
        tx, ty = (ox - x) * self.cols / w, (oy - y) * self.rows / h
        if 0 <= tx < self.cols and 0 <= ty < self.rows:
            return tx, ty
        return None

    def convert(self, event):
        """A mouse event with its position in screen tiles (None if it's off the picture);
        other events as they are."""
        if not isinstance(event, (tcod.event.MouseMotion, tcod.event.MouseButtonDown, tcod.event.MouseButtonUp)):
            return event
        tile = self.tile_at(*event.position)
        if tile is None:
            return None
        event = copy.copy(event)
        event.position = tcod.event.Point(*tile)
        return event
