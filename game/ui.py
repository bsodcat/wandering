"""The screen's layout: the map underneath, and the panels laid over it.

The screen is as many tiles as fit the window at the font's size and scale: 120x45 by
default (1200x900 with Terminal), more if the window is bigger, so a bigger window shows more
of the world rather than bigger pixels. The map always fills all of it, centred on you, and
the panels are drawn on top, pinned to the left and right edges: hiding one just uncovers
more of the map.

- Left: your stats (health, stamina, warmth, wetness and so on). `c` or its ◄ button hides
  it; the ► tab in the corner brings it back.
- Right: four tabs, Info (where you are, the weather, what's under the pointer, the keys),
  Map (a minimap), Log (every message, scrollable) and Inv (what you carry; i opens it). Tab
  cycles Info, Map, Log, Inv, hidden;
  clicking a tab picks it, and its ► button hides the panel.
- Along the bottom between them: the last few messages, over a darkened strip of map. It
  doesn't take the mouse, so you can still point at the map under it.

This module only keeps the state and answers "what's at this spot of the screen"; game/hud.py
draws it.
"""
from __future__ import annotations

from dataclasses import dataclass

from tcod.event import KeySym

SCREEN_W, SCREEN_H = 120, 45          # the screen at its default size (1200 x 900 pixels: 4:3)
MIN_W, MIN_H = 80, 30                 # the smallest screen the panels still fit on
LEFT_W = 24                           # columns of the stats panel, border included
RIGHT_W = 28                          # columns of the right panel, border included
RIGHT_X = SCREEN_W - RIGHT_W          # where the right panel starts on a default-sized screen
STRIP_H = 4                           # recent messages along the bottom
TABS = ("info", "map", "log", "inv")
TAB_NAMES = {"info": "Info", "map": "Map", "log": "Log", "inv": "Inv"}
PANEL_KEY, STATS_KEY = KeySym.TAB, KeySym.C
SCROLL_KEYS = {KeySym.PAGEUP: 10, KeySym.PAGEDOWN: -10, KeySym.HOME: 10_000, KeySym.END: -10_000}

LEFT_SHOW = (0, 0, 3)                 # (x, y, width) of the ► tab when the stats are hidden
LEFT_HIDE = (LEFT_W - 3, 0, 2)        # the stats panel's hide button
RIGHT_SHOW = (SCREEN_W - 3, 0, 3)     # the right panel's (on a default-sized screen; see Panels)
RIGHT_HIDE = (SCREEN_W - 2, 0, 2)


def inside(sx: int, sy: int, box: tuple[int, int, int]) -> bool:
    x, y, w = box
    return y == sy and x <= sx < x + w


@dataclass
class Panels:
    left_open: bool = True
    tab: str = "info"                 # the right panel's tab
    right_open: bool = True
    log_scroll: int = 0               # lines scrolled back from the newest in the Log tab
    width: int = SCREEN_W             # the screen, in tiles: kept up to date as the window changes
    height: int = SCREEN_H

    # ------------------------------------------------------------- what's where

    @property
    def right_x(self) -> int:
        """Where the right panel starts: always against the right edge."""
        return self.width - RIGHT_W

    @property
    def right_show(self) -> tuple[int, int, int]:
        return self.width - 3, 0, 3

    @property
    def right_hide(self) -> tuple[int, int, int]:
        return self.width - 2, 0, 2

    def left_edge(self) -> int:
        """The first map column not under the stats panel."""
        return LEFT_W if self.left_open else 0

    def right_edge(self) -> int:
        """One past the last map column not under the right panel."""
        return self.right_x if self.right_open else self.width

    def tab_spans(self) -> list[tuple[str, int, int]]:
        """(tab, first column, width) of each tab title on the right panel's top row."""
        spans, x = [], self.right_x + 2
        for tab in TABS:
            width = len(TAB_NAMES[tab]) + 2
            spans.append((tab, x, width))
            x += width + 1
        return spans

    def covers(self, sx: int, sy: int) -> bool:
        """Whether a panel (or a panel's tab) is over this screen cell, so the mouse is on the
        panel rather than the map."""
        if self.left_open and sx < LEFT_W or self.right_open and sx >= self.right_x:
            return True
        return (not self.left_open and inside(sx, sy, LEFT_SHOW)) or \
               (not self.right_open and inside(sx, sy, self.right_show))

    def over_log(self, sx: int, sy: int) -> bool:
        return self.right_open and self.tab == "log" and sx >= self.right_x

    # ------------------------------------------------------------- changes

    def toggle_left(self) -> None:
        self.left_open = not self.left_open

    def cycle(self) -> None:
        """Info, Map, Log, Inv, hidden, and round again."""
        if not self.right_open:
            self.right_open, self.tab = True, TABS[0]
        elif self.tab == TABS[-1]:
            self.right_open = False
        else:
            self.tab = TABS[TABS.index(self.tab) + 1]
        self.log_scroll = 0

    def show(self, tab: str) -> None:
        self.right_open, self.tab, self.log_scroll = True, tab, 0

    def scroll(self, lines: int) -> None:
        self.log_scroll = max(0, self.log_scroll + lines)

    def handle_key(self, sym) -> bool:
        """The panel keys. Returns whether the key was one of them."""
        if sym == PANEL_KEY:
            self.cycle()
        elif sym == STATS_KEY:
            self.toggle_left()
        elif sym in SCROLL_KEYS and self.right_open and self.tab == "log":
            self.scroll(SCROLL_KEYS[sym])
        else:
            return False
        return True

    def click(self, sx: int, sy: int) -> bool:
        """A left click on a panel's buttons or tabs. Returns whether it hit one."""
        if not self.left_open and inside(sx, sy, LEFT_SHOW) or self.left_open and inside(sx, sy, LEFT_HIDE):
            self.toggle_left()
            return True
        if not self.right_open and inside(sx, sy, self.right_show):
            self.right_open = True
            return True
        if self.right_open:
            if inside(sx, sy, self.right_hide):
                self.right_open = False
                return True
            for tab, x, width in self.tab_spans():
                if inside(sx, sy, (x, 0, width)):
                    self.show(tab)
                    return True
        return False
