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

REACH = {T.HEARTH: 7.0, T.TORCH: 8.0}   # columns the light reaches
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
