"""Shops: trading with the townsfolk.

Walk into someone who trades, while they're at work, and their shop opens over the game: a
list of deals, each paying some of what you carry for something else. Up/Down (or the mouse)
picks one, Enter makes it, Esc (or Leave) walks away.

- A lumberjack buys logs, once you've cut some (you need an axe: there's one by their house).
- A barkeeper lets a room upstairs for the night: you get a room key, good until mid-morning,
  and can sleep (z) in any of the beds up there.

A shop is a title, a greeting and its deals, so another trade is a few lines (`for_actor`).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from tcod.event import KeySym

from . import items
from .people import ROOM_PRICE

LOG_PRICE = 3
BOX_W = 52


@dataclass
class Deal:
    label: str
    pay: dict                         # kind -> how many you give
    get: dict                         # kind -> how many you get
    every: bool = False               # as many times over as you can afford
    after: str = ""                   # something more happens: "room"


@dataclass
class Shop:
    title: str
    greeting: str
    deals: list
    cursor: int = 0
    cols: int = 120                   # the screen, as last drawn (for the mouse)
    rows: int = 45
    said: list = field(default_factory=list)   # what happened, newest last, shown in the box

    def labels(self) -> list[str]:
        return [d.label for d in self.deals] + ["Leave"]

    def times(self, deal: Deal, inventory) -> int:
        """How many times over you can make a deal right now."""
        n = min(inventory.count(k) // v for k, v in deal.pay.items())
        return n if deal.every else min(n, 1)

    def trade(self, i: int, engine) -> str:
        deal = self.deals[i]
        bag = engine.player.inventory
        if deal.after == "room" and bag.count("room key"):
            return "You've already got a room for tonight."
        n = self.times(deal, bag)
        if not n:
            short = next(k for k, v in deal.pay.items() if bag.count(k) < v)
            return f"You haven't got {'enough' if bag.count(short) else 'any'} {items.KINDS[short].plural}."
        for k, v in deal.pay.items():
            bag.take(k, v * n)
        for k, v in deal.get.items():
            bag.add(k, v * n)
        if deal.after == "room":
            engine.rent_room()
        paid = " and ".join(items.amount(k, v * n) for k, v in deal.pay.items())
        got = " and ".join(items.amount(k, v * n) for k, v in deal.get.items())
        return f"You give {paid} for {got}."

    def act(self, engine) -> bool:
        """Enter on the picked row. Returns False when you leave."""
        if self.cursor >= len(self.deals):
            return False
        text = self.trade(self.cursor, engine)
        self.said = (self.said + [text])[-2:]
        engine.say(text)
        return True

    def handle_key(self, sym, engine) -> bool:
        """A key while the shop's open. Returns False when you leave."""
        n = len(self.labels())
        if sym == KeySym.ESCAPE:
            return False
        if sym in (KeySym.UP, KeySym.KP_8, KeySym.W):
            self.cursor = (self.cursor - 1) % n
        elif sym in (KeySym.DOWN, KeySym.KP_2, KeySym.S):
            self.cursor = (self.cursor + 1) % n
        elif sym in (KeySym.RETURN, KeySym.KP_ENTER, KeySym.SPACE):
            return self.act(engine)
        return True

    # ------------------------------------------------------------- where things go, for the mouse

    def box(self) -> tuple[int, int, int, int]:
        h = 9 + 2 * len(self.labels())
        return (self.cols - BOX_W) // 2, (self.rows - h) // 2, BOX_W, h

    def row_y(self, i: int) -> int:
        return self.box()[1] + 4 + 2 * i

    def row_at(self, sx: int, sy: int) -> int | None:
        x, _, w, _ = self.box()
        for i in range(len(self.labels())):
            if sy == self.row_y(i) and x < sx < x + w - 1:
                return i
        return None

    def click(self, sx: int, sy: int, engine) -> bool:
        i = self.row_at(sx, sy)
        if i is None:
            return True
        self.cursor = i
        return self.act(engine)


def for_actor(a, engine) -> Shop | None:
    """The shop someone keeps, if they trade and you've something to trade; None otherwise."""
    if a.kind == "lumberjack" and engine.player.inventory.count("log"):
        return Shop(f"{a.name}, the lumberjack", f"Good wood, that. I'll give you {LOG_PRICE} coins a log.",
                    [Deal(f"Sell a log for {LOG_PRICE} coins", {"log": 1}, {"coin": LOG_PRICE}),
                     Deal("Sell all your logs", {"log": 1}, {"coin": LOG_PRICE}, every=True)])
    if a.kind == "barkeeper":
        inn = next((b.name for b in engine.level.buildings if b.kind == "inn"), "the inn")
        return Shop(f"{a.name}, the barkeeper", f"Welcome to {inn}. A bed upstairs is {ROOM_PRICE} coins the night.",
                    [Deal(f"A room for the night: {ROOM_PRICE} coins", {"coin": ROOM_PRICE}, {"room key": 1},
                          after="room")])
    return None
