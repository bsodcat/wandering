"""Firelight: hearths inside and torches by the doors outside.

Each fire lights the tiles it can see, fading with distance (counted on screen, where a row is
two columns tall). Hearths light the room they're in; torches light the ground outside. A
level works its firelight out once, the first time it's drawn, and keeps it: the strength of
the light on each tile and the "phase" of the fire it comes from, so every fire flickers to
its own rhythm and everything it lights flickers with it.

Firelight matters most in the dark: at night a lit town shows from far off, and you can see
by it beyond your lantern.
"""
from __future__ import annotations

import math

import numpy as np
import tcod

from . import tiles as T

REACH = {T.HEARTH: 7.0, T.TORCH: 8.0, T.OVEN: 5.0, T.FORGE: 6.0, T.CAMPFIRE: 6.0}   # columns the light reaches
LAVA_GLOW = 5                              # columns lava lights around it (no shadows: it's everywhere)
SEEN_FROM_AFAR = 0.2                       # firelight this strong shows up past your lantern
FLAME_FG = [(255, 150, 50), (255, 200, 90), (240, 110, 40), (255, 230, 140)]


def firelight(level) -> tuple[np.ndarray, np.ndarray]:
    """(strength 0..1, phase) of the firelight on each tile of a level, worked out once."""
    if level.fire is not None:
        return level.fire
    tiles = level.tiles
    strength = np.zeros(tiles.shape, np.float32)
    phase = np.zeros(tiles.shape, np.float32)
    xs, ys = np.ogrid[: level.width, : level.height]
    transparent = T.SEE[tiles]
    for tile, reach in REACH.items():
        for x, y in zip(*np.nonzero(tiles == tile)):
            x, y = int(x), int(y)
            if tile == T.CAMPFIRE:            # a campfire's light grows with the fuel on it
                from .crafting import fire_reach
                reach = fire_reach(level, x, y)
            seen = tcod.map.compute_fov(transparent, (x, y), int(reach) + 1, light_walls=True,
                                        algorithm=tcod.constants.FOV_SYMMETRIC_SHADOWCAST)
            if tile == T.TORCH:
                seen &= ~T.ROOF[tiles]      # a torch lights the outside of the wall it's on
            seen[x, y] = True
            dist = np.sqrt((xs - x) ** 2 + (2 * (ys - y)) ** 2)
            lit = np.where(seen, np.clip(1 - dist / reach, 0, 1) ** 1.3, 0).astype(np.float32)
            stronger = lit > strength
            strength[stronger] = lit[stronger]
            phase[stronger] = (x * 12.9898 + y * 78.233) % (2 * math.pi)
    lava = tiles == T.LAVA
    if lava.any():                         # lava glows all round, too much of it to cast shadows
        glow = lava.astype(np.float32)
        reach = lava.copy()
        for step in range(1, LAVA_GLOW + 1):
            p = np.pad(reach, 1)
            reach = reach | p[:-2, 1:-1] | p[2:, 1:-1] | (step % 2 == 0) & (p[1:-1, :-2] | p[1:-1, 2:])
            glow = np.maximum(glow, reach * (1 - step / (LAVA_GLOW + 1)) ** 1.3)
        stronger = glow > strength
        strength[stronger] = glow[stronger]
        phase[stronger] = ((xs * 12.9898 + ys * 78.233) % (2 * math.pi) * np.ones_like(glow))[stronger]
    level.fire = (strength, phase)
    return level.fire


def flicker(phase: np.ndarray, seconds: float) -> np.ndarray:
    """How bright each fire burns right now: about 0.7 to 1, wavering."""
    return (0.85 + 0.09 * np.sin(seconds * 7.3 + phase) + 0.06 * np.sin(seconds * 13.1 + phase * 1.7)
            + 0.04 * np.sin(seconds * 23.0 + phase * 2.3))


def flame(phase: np.ndarray, seconds: float) -> tuple[np.ndarray, np.ndarray]:
    """The glyph and colour of the flames themselves this instant."""
    step = (np.floor(seconds * 8 + phase * 3)).astype(int)
    colours = np.array(FLAME_FG, dtype=np.float32)[step % len(FLAME_FG)]
    return step, colours


# ----------------------------------------------------------------- the light you carry

# A torch burns orange and wavers; a lantern burns yellow, behind glass, and hardly wavers.
CARRIED = {"torch": ((95, 45, 0), (70, 30, 0), 1.0), "lantern": ((110, 80, 5), (80, 52, 0), 0.35)}
CARRIED_MOST = 0.9          # how far towards its own colours (and the flame's) the light brings a tile


def carried(kind: str | None, reach: int, dist: np.ndarray, dark, seconds: float) -> np.ndarray:
    """0..1: how strongly a torch or lantern you hold lights each tile, `dist` columns away
    (a row counting two). It fades out to `reach` tiles, shows most in the dark (`dark` 0..1),
    and flickers: the whole pool breathes, and the edge wavers."""
    if kind not in CARRIED:
        return np.zeros(dist.shape, np.float32)
    wobble = CARRIED[kind][2]
    f = float(flicker(np.zeros(1), seconds)[0])            # 0.7..1 for a torch
    f = 1 - (1 - f) * wobble
    edge = 2 * reach + 1
    edge = edge * (1 - 0.08 * wobble + 0.08 * wobble * (f - 0.7) / 0.3)
    fall = np.clip(1 - dist / edge, 0, 1) ** 0.75
    return (fall * f * CARRIED_MOST * dark).astype(np.float32)


def carried_light(fg, bg, base_fg, base_bg, amount: np.ndarray, kind: str) -> tuple[np.ndarray, np.ndarray]:
    """Brings each tile from the dark (blue at night) back towards its own colours, warmed by
    the flame's, as strongly as `amount`."""
    warm_fg, warm_bg, _ = CARRIED[kind]
    a = amount[..., None]
    lit_fg = base_fg * 0.95 + np.array(warm_fg, np.float32)
    lit_bg = base_bg * 0.75 + np.array(warm_bg, np.float32)
    return fg + (lit_fg - fg) * a, bg + (lit_bg - bg) * a
