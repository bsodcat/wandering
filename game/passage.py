"""The time skip as it happens: the years counting up one at a time, and the land changing.

Start in the time skip menu (T) begins it. The count starts at a year a frame and speeds up
the longer it runs (a century takes a few seconds, a million years under half a minute), and
meanwhile the world is remade in the background, again and again, as it would stand after the
years counted so far, so you watch the land wear and change on the map.

Stop (the button, Space, Enter or Esc) ends it on the year showing: the era is cut short
there, and you play on from the middle of it. Run to the end and it stops by itself.
"""
from __future__ import annotations

import threading
import time

from . import eras
from .worldgen import World, generate

SLOWEST = 24.0     # years a second at first: a little under one a frame, so none is skipped
SPEED_UP = 0.6     # then the count grows by this share of itself each second
FRAME = 1 / 30     # seconds between redraws while it runs


class Passage:
    """One time skip in progress: `years` of `change` from `world`, counted so far to `elapsed`."""

    def __init__(self, world: World, years: int, change: str, start_year: int):
        self.old, self.years, self.change = world, years, change
        self.start_year = start_year           # the year it is when it starts
        self.elapsed = 0                       # whole years counted
        self._count = 0.0
        self.stopped_at: int | None = None     # set by Stop (or the end): where it settles
        self.shown: tuple[int, World] | None = None    # the latest world made, and its years
        self.final: World | None = None        # the world it settles on, once made
        self._last = time.monotonic()
        self._thread = threading.Thread(target=self._remake, daemon=True)
        self._thread.start()

    # ------------------------------------------------------------- counting

    @property
    def year(self) -> int:
        return self.start_year + self.elapsed

    @property
    def running(self) -> bool:
        return self.stopped_at is None

    @property
    def done(self) -> bool:
        """Settled, and the world for it made: the game can take it."""
        return self.final is not None

    def tick(self, now: float | None = None) -> None:
        """Counts on by however long it's been since the last tick."""
        now = time.monotonic() if now is None else now
        dt, self._last = max(0.0, min(0.25, now - self._last)), now
        if not self.running:
            return
        self._count += max(SLOWEST, self._count * SPEED_UP) * dt
        self.elapsed = min(self.years, int(self._count))
        if self.elapsed >= self.years:
            self.stop()

    def stop(self) -> None:
        """Stop on the year showing (at least one year on)."""
        if self.running:
            self.elapsed = max(1, self.elapsed)
            self.stopped_at = self.elapsed

    def history(self, years: int) -> tuple:
        return self.old.history + ((years, self.change),)

    # ------------------------------------------------------------- remaking the land

    def _remake(self) -> None:
        """In the background: the world as it stands after the years counted so far, over and
        over, and last the one it stops on."""
        old = self.old
        while True:
            target = self.stopped_at if self.stopped_at is not None else max(1, self.elapsed)
            if self.shown is None or self.shown[0] != target:
                world = generate(old.seed, old.width, old.height, self.history(target), old.tweaks,
                                 eras.survivors(old, target))
                self.shown = (target, world)
            if self.stopped_at is not None and self.shown[0] == self.stopped_at:
                self.final = self.shown[1]
                return
            time.sleep(0.01)

    def wait(self, timeout: float | None = None) -> None:
        self._thread.join(timeout)

    # ------------------------------------------------------------- the screen

    def lines(self) -> list[str]:
        change = eras.BY_NAME[self.change]
        if self.running:
            state = f"{eras.years_text(self.elapsed)} of {self.years:,} {change.name.lower()}"
        elif self.final is None:
            state = f"Stopped after {eras.years_text(self.stopped_at)}: the land settles..."
        else:
            state = f"Stopped after {eras.years_text(self.stopped_at)}"
        return [f"Year {self.year:,}", state]
