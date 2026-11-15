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
import functools

import numpy as np
import tcod
import tcod.render
import tcod.sdl.render
from tcod.cffi import ffi, lib
from tcod.sdl.render import LogicalPresentation, ScaleMode

from . import fon
from . import glyphs
from .options import FONTS, PIXEL_GRID, Settings, available_fonts, font_path
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
    for n, ch in enumerate("▏▎▍▌▋▊▉", start=1):     # bars: a block filled n eighths from the left
        a = np.zeros((h, w), np.uint8)
        a[:, : max(1, round(w * n / 8))] = 255
        out[ch] = a
    r = max(1, min(w, h) // 4)                         # rounded corners: a quarter circle of radius r
    for ch, (sx, sy) in (("╭", (1, 1)), ("╮", (-1, 1)), ("╰", (1, -1)), ("╯", (-1, -1))):
        a = np.zeros((h, w), np.uint8)
        ox, oy = cx + sx * r, cy + sy * r              # the circle's middle
        for t in np.linspace(0, np.pi / 2, 4 * r + 4):
            a[int(round(oy - sy * r * np.sin(t))), int(round(ox - sx * r * np.cos(t)))] = 255
        if sx > 0:
            a[cy, ox:] = 255
        else:
            a[cy, : ox + 1] = 255
        if sy > 0:
            a[oy:, cx] = 255
        else:
            a[: oy + 1, cx] = 255
        out[ch] = a
    return out


DRAWN = frozenset(drawn_glyphs(8, 16))     # glyphs every font gets drawn by hand


def with_drawn_glyphs(tileset: tcod.tileset.Tileset) -> tcod.tileset.Tileset:
    w, h = tileset.tile_width, tileset.tile_height
    for ch, alpha in drawn_glyphs(w, h).items():
        tileset.set_tile(ord(ch), alpha)
    return tileset


def has_ink(tileset: tcod.tileset.Tileset, ch: str) -> bool:
    return bool((tileset.get_tile(ord(ch))[..., 3] > 40).any())


UNKNOWN = glyphs.UNKNOWN
CP437 = glyphs.CP437
game_glyphs = glyphs.game_glyphs


def with_fallbacks(tileset: tcod.tileset.Tileset, have=CP437) -> tcod.tileset.Tileset:
    """Every glyph the game draws with that this font hasn't got (`have` is what it has) is
    drawn as the closest shape it does have (glyphs.SUBSTITUTES), or failing that a question
    mark, so nothing is ever invisible. (No item or tile is drawn with a ? of its own.)"""
    present = {ch for ch in game_glyphs() | {s for subs in glyphs.SUBSTITUTES.values() for s in subs}
               if len(ch) == 1 and (ord(ch) in have or ch in DRAWN) and has_ink(tileset, ch)}
    mark = np.ascontiguousarray(tileset.get_tile(ord(UNKNOWN))[..., 3])
    for ch in sorted(game_glyphs()):
        if len(ch) != 1 or not ch.strip() or ch in present:
            continue
        sub = next((s for s in glyphs.SUBSTITUTES.get(ch, ()) if s in present), None)
        tile = np.ascontiguousarray(tileset.get_tile(ord(sub))[..., 3]) if sub else mark
        tileset.set_tile(ord(ch), tile)
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


PIXEL_PROBE = 7        # big pixels to one of a pixel font's pixels, when it's sampled (libtcod draws
                       # a font at 7/8 of the tile asked for, so a multiple of 7 lands them whole)


@functools.lru_cache(maxsize=4)
def pixel_glyphs(path: str, grid: tuple[int, int], codes: tuple) -> dict[int, np.ndarray]:
    """A TrueType font drawn on a pixel grid (grid = its cell in font pixels), read back pixel
    by pixel: libtcod's loader smooths it and lands it off the pixel grid, so it's drawn big and
    each font pixel's middle is sampled, on or off. Returns code -> (height, width) alpha."""
    gw, gh = grid
    big = tcod.tileset.load_truetype_font(path, gw * PIXEL_PROBE * 8 // 7, gh * PIXEL_PROBE * 8 // 7)
    block = big.get_tile(0x2588)[..., 3] > 127                   # the full block marks the cell
    ys, xs = np.nonzero(block)
    x0, y0 = xs.min(), ys.max() + 1 - gh * PIXEL_PROBE
    px = x0 + PIXEL_PROBE // 2 + PIXEL_PROBE * np.arange(gw)
    py = y0 + PIXEL_PROBE // 2 + PIXEL_PROBE * np.arange(gh)
    py = np.clip(py, 0, big.tile_height - 1)
    out = {}
    for code in codes:
        alpha = big.get_tile(code)[..., 3]
        out[code] = np.where(alpha[py[:, None], px[None, :]] > 127, 255, 0).astype(np.uint8)
    return out


def halve(tile: np.ndarray) -> np.ndarray:
    """A 2x-grid glyph at half the size: a pixel's on where at least half its 2x2 block is."""
    h, w = tile.shape
    blocks = (tile > 0).reshape(h // 2, 2, w // 2, 2).sum(axis=(1, 3))
    return np.where(blocks >= 2, 255, 0).astype(np.uint8)


def pixel_tileset(name: str, path: str, w: int, h: int) -> tcod.tileset.Tileset:
    """A pixel TrueType font at w x h: its own 16x32 grid, or halved to 8x16, scaled from the
    nearer of those for any other size, pixels repeated so it stays sharp."""
    gw, gh = PIXEL_GRID[name]
    codes = tuple(sorted(glyphs.wanted_codes()))
    full = pixel_glyphs(path, (gw, gh), codes)
    small = (w, h) != (gw, gh) and (w <= gw // 2 * 1.25 or (w, h) == (gw // 2, gh // 2))
    tileset = tcod.tileset.Tileset(w, h)
    for code, tile in full.items():
        if small:
            tile = halve(tile)
        if tile.shape != (h, w):
            tile = scale_tile(tile, w, h)
        tileset.set_tile(code, np.ascontiguousarray(tile))
    return tileset


def make_tileset(font: str, cell: tuple[int, int]) -> tcod.tileset.Tileset:
    """The font at this tile size: bitmap fonts use their nearest size, scaled; TrueType fonts
    are drawn at the size. Falls back to Terminal, then to libtcod's own font. Glyphs that
    a font hasn't got are drawn as the closest shape it has, or a ? (with_fallbacks)."""
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
                return with_fallbacks(with_drawn_glyphs(tileset), CP437)
            have = glyphs.font_chars(path, False)
            if name in PIXEL_GRID:
                tileset = with_drawn_glyphs(pixel_tileset(name, path, w, h))
                return with_fallbacks(tileset, have & glyphs.wanted_codes())
            return with_fallbacks(fit_truetype(path, w, h), have)
        except Exception:
            continue
    return with_fallbacks(tcod.tileset.get_default())


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
    def __init__(self, settings: Settings, title: str = "Wandering"):
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
