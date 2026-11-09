"""The window: fonts, resolution, fullscreen, and getting the screen onto it.

The screen is always SCREEN_W x SCREEN_H tiles. It's drawn with the chosen font at the chosen
tile size into a frame, and the frame is scaled to the chosen resolution (always 4:3). SDL then
fits that into the window or the monitor, adding black bars rather than stretching it. When
the frame is exactly the resolution it's copied pixel for pixel; otherwise it's smoothed.

Mouse positions come in as window pixels and go out as screen tiles, through the same scaling.
"""
from __future__ import annotations

import copy

import numpy as np
import tcod
import tcod.render
import tcod.sdl.render
from tcod.sdl.render import LogicalPresentation, ScaleMode

from . import fon
from .options import FONTS, Settings, available_fonts, font_path
from .ui import SCREEN_H, SCREEN_W


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


class Display:
    def __init__(self, settings: Settings, title: str = "newrogue"):
        self.settings = settings
        rw, rh = settings.resolution
        self.context = tcod.context.new(width=rw, height=rh, title=title, vsync=True,
                                        tileset=make_tileset(settings.font, settings.cell()),
                                        sdl_window_flags=tcod.context.SDL_WINDOW_RESIZABLE)
        self.window = self.context.sdl_window
        self.renderer = self.context.sdl_renderer
        self.font_key = None
        self.apply(settings)

    def close(self) -> None:
        self.context.close()

    def apply(self, settings: Settings) -> None:
        """Puts the settings into effect: the font, the window and how the frame is scaled."""
        self.settings = settings
        key = (settings.font, settings.cell())
        if key != self.font_key:
            self.tileset = make_tileset(settings.font, settings.cell())
            self.atlas = tcod.render.SDLTilesetAtlas(self.renderer, self.tileset)
            self.console_render = tcod.render.SDLConsoleRender(self.atlas)
            self.font_key = key
        if self.window.fullscreen != settings.fullscreen:
            self.window.fullscreen = settings.fullscreen
        if not settings.fullscreen:
            self.window.size = settings.resolution
        self.renderer.set_logical_presentation(settings.resolution, LogicalPresentation.LETTERBOX)

    def present(self, console: tcod.console.Console) -> None:
        rw, rh = self.settings.resolution
        texture = self.console_render.render(console)
        exact = (texture.width, texture.height) == (rw, rh)
        texture.scale_mode = ScaleMode.NEAREST if exact else ScaleMode.LINEAR
        self.renderer.draw_color = (0, 0, 0, 255)
        self.renderer.clear()
        self.renderer.copy(texture, dest=(0, 0, rw, rh))
        self.renderer.present()

    def tile_at(self, px: float, py: float) -> tuple[float, float] | None:
        """The screen tile under a window pixel, or None if it's in the black bars."""
        lx, ly = self.renderer.coordinates_from_window((px, py))
        rw, rh = self.settings.resolution
        tx, ty = lx * SCREEN_W / rw, ly * SCREEN_H / rh
        if 0 <= tx < SCREEN_W and 0 <= ty < SCREEN_H:
            return tx, ty
        return None

    def convert(self, event):
        """A mouse event with its position in screen tiles (None if it's over the bars); other
        events as they are."""
        if not isinstance(event, (tcod.event.MouseMotion, tcod.event.MouseButtonDown, tcod.event.MouseButtonUp)):
            return event
        tile = self.tile_at(*event.position)
        if tile is None:
            return None
        event = copy.copy(event)
        event.position = tcod.event.Point(*tile)
        return event
