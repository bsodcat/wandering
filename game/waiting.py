"""The wait menu (r, or Wait... in the use menu): let the clock run on as long as you like.

Set waits (10 minutes up to 8 hours), waits until a time of day (dawn, noon, dusk, midnight),
and one of your own: on its row, Left/Right change it (by 15 minutes up to 2 hours, then by
the hour, up to a day). A wait goes an hour at a time and stops early if something dangerous
turns up. "." and numpad 5 still wait an hour straight off.
"""
from __future__ import annotations

from tcod.event import KeySym

from .climate import hour_of_day
from .shop import Option, Picker

SET = [10, 30, 60, 120, 240, 480]                       # minutes
UNTIL = [("dawn", 6), ("noon", 12), ("dusk", 18), ("midnight", 0)]
CUSTOM_START = 90
MOST = 24 * 60
LEFT_KEYS = (KeySym.LEFT, KeySym.KP_4, KeySym.A)
RIGHT_KEYS = (KeySym.RIGHT, KeySym.KP_6, KeySym.D)


def words(minutes: float) -> str:
    """'1 h 15 min', '45 min', '3 h'."""
    m = int(round(minutes))
    h, m = divmod(m, 60)
    if h and m:
        return f"{h} h {m} min"
    return f"{h} h" if h else f"{m} min"


def until(engine, hour: int) -> float:
    """Minutes from now till the next time the clock reads `hour`:00."""
    now = float(hour_of_day(engine.minutes))
    return ((hour - now) % 24 or 24) * 60


def wait_for(engine, minutes: float) -> str:
    """Waits `minutes`, an hour at a time; stops if something dangerous comes."""
    if not engine.player.alive:
        return ""
    if engine.danger():
        return ""
    left = minutes
    while left > 1e-6 and engine.player.alive:
        step = min(60.0, left)
        engine.wait(step / 60)
        left -= step
        if left > 1e-6 and engine.level is not None and engine.danger():
            return f"You stop waiting after {words(minutes - left)}."
    return f"You wait {words(minutes)}."


class WaitMenu(Picker):
    hint = "Up/Down choose, Left/Right change your own, Enter waits, Esc closes"

    def __init__(self):
        self.custom = CUSTOM_START
        super().__init__("Wait", self.rows, greeting="How long will you wait?")

    def rows(self, engine) -> list:
        out = [Option(f"Wait {words(m)}", lambda e, m=m: wait_for(e, m)) for m in SET]
        out += [Option(f"Wait until {name} ({hour:02d}:00, {words(until(engine, hour))})",
                       lambda e, h=hour: wait_for(e, until(e, h))) for name, hour in UNTIL]
        out.append(Option(f"Wait  ◄ {words(self.custom)} ►  (Left/Right)", lambda e: wait_for(e, self.custom)))
        return out

    def change(self, by: int) -> None:
        step = 15 if (self.custom < 120 or (self.custom == 120 and by < 0)) else 60
        self.custom = max(15, min(MOST, self.custom + by * step))

    def handle_key(self, sym, engine) -> bool:
        if self.cursor == len(self.options) - 1 and sym in LEFT_KEYS + RIGHT_KEYS:
            self.change(-1 if sym in LEFT_KEYS else 1)
            self.refresh(engine)
            return True
        return super().handle_key(sym, engine)


def menu(engine) -> WaitMenu:
    m = WaitMenu()
    m.refresh(engine)
    return m
