"""newrogue: run with `python main.py [seed]`."""
from __future__ import annotations

import os
import sys

import tcod

from game import fon
from game.engine import Engine
from game.render import SCREEN_H, SCREEN_W, draw

TILE_W, TILE_H = 10, 20
FONTS = [r"C:\Windows\Fonts\8514oem.fon",  # the classic Terminal font, crisp at 10x20
         r"C:\Windows\Fonts\consola.ttf", "/System/Library/Fonts/Menlo.ttc",
         "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"]


def load_font(path: str) -> tcod.tileset.Tileset:
    if path.lower().endswith(".fon"):
        width, height, tiles = fon.load(path, (TILE_W, TILE_H))
        tileset = tcod.tileset.Tileset(width, height)
        for code, tile in tiles.items():
            tileset[tcod.tileset.CHARMAP_CP437[code]] = tile
        return tileset
    return tcod.tileset.load_truetype_font(path, TILE_W, TILE_H)


def load_tileset() -> tcod.tileset.Tileset | None:
    for path in FONTS:
        if os.path.exists(path):
            try:
                return load_font(path)
            except Exception:
                continue
    return None  # libtcod's own fallback font


def main() -> None:
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else None
    engine = Engine.new(seed)
    console = tcod.console.Console(SCREEN_W, SCREEN_H, order="F")
    with tcod.context.new(columns=SCREEN_W, rows=SCREEN_H, tileset=load_tileset(),
                          title="newrogue", vsync=True) as context:
        while True:
            draw(console, engine)
            context.present(console)
            for event in tcod.event.wait():
                if isinstance(event, tcod.event.Quit):
                    return
                if isinstance(event, tcod.event.KeyDown) and not engine.handle_key(event.sym, event.mod):
                    return


if __name__ == "__main__":
    main()
