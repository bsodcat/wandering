"""Boxes over the game you pick from: shops, the use menu, and barrels.

Each is a list (Up/Down or the mouse picks, Enter takes it, Esc closes), long ones scrolling:

- A shop (`Shop`): walk into someone who trades while they're at work. Each deal pays some of
  what you carry for something else.
  - A lumberjack buys logs, once you've cut some (you need an axe: there's one by their house).
  - A barkeeper lets a room upstairs for the night: you get a room key, good until mid-morning,
    and can sleep (z) in any of the beds up there.
  - An innkeeper serves hot soup, which warms you, and treats wolf fever (game/sickness.py).
  - A town's shopkeeper sells common weapons and armour, and buys trinkets and rings.
- A `Picker`: the use menu (e, or a click on something you can use: a barrel, a bed,
  someone).
- A `Container`: what's in a barrel, on two tabs: Take (things out) and Put in (what you
  carry). Left/Right, Tab or a click on a tab switches between them.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from tcod.event import KeySym

from . import combat
from . import items
from .people import ROOM_PRICE

LOG_PRICE = 3
SOUP_PRICE = 4
BOX_W = 56


class Modal:
    """A box of rows to pick from, over the game."""
    title = ""
    greeting = ""
    hint = "Up/Down choose, Enter picks, Esc closes"
    leave_text = ""

    def __init__(self):
        self.cursor = 0
        self.top = 0                 # the first row shown, when there are too many to show
        self.cols, self.rows = 120, 45   # the screen, as last drawn (for the mouse)
        self.said: list = []         # what happened, newest last, shown in the box

    def labels(self) -> list[str]:
        raise NotImplementedError

    def dim(self, i: int, engine) -> bool:
        """Whether row i can't be picked right now (drawn dim)."""
        return False

    def footer(self, engine) -> str:
        return f"Coins {engine.player.inventory.count('coin')}"

    def act(self, engine) -> bool:
        raise NotImplementedError

    def refresh(self, engine) -> None:
        """Works the rows out again (what you carry has changed)."""

    def handle_key(self, sym, engine) -> bool:
        """A key while the box is open. Returns False when it closes."""
        n = len(self.labels())
        if sym == KeySym.ESCAPE:
            return False
        if sym in (KeySym.UP, KeySym.KP_8, KeySym.W):
            self.cursor = (self.cursor - 1) % n
        elif sym in (KeySym.DOWN, KeySym.KP_2, KeySym.S):
            self.cursor = (self.cursor + 1) % n
        elif sym == KeySym.PAGEUP:
            self.cursor = max(0, self.cursor - self.shown())
        elif sym == KeySym.PAGEDOWN:
            self.cursor = min(n - 1, self.cursor + self.shown())
        elif sym in (KeySym.RETURN, KeySym.KP_ENTER, KeySym.SPACE):
            return self.act(engine)
        self.scroll()
        return True

    # ------------------------------------------------------------- where things go

    def gap(self) -> int:
        return 2 if len(self.labels()) <= 6 else 1

    def shown(self) -> int:
        return max(1, min(len(self.labels()), (self.rows - 14) // self.gap()))

    def scroll(self) -> None:
        n, k = len(self.labels()), self.shown()
        self.cursor = max(0, min(self.cursor, n - 1))
        if self.cursor < self.top:
            self.top = self.cursor
        elif self.cursor >= self.top + k:
            self.top = self.cursor - k + 1
        self.top = max(0, min(self.top, n - k))

    def box(self) -> tuple[int, int, int, int]:
        gap = self.gap()
        h = 11 - gap + self.shown() * gap
        return (self.cols - BOX_W) // 2, (self.rows - h) // 2, BOX_W, h

    def row_y(self, i: int) -> int:
        return self.box()[1] + 4 + (i - self.top) * self.gap()

    def visible_rows(self) -> range:
        self.scroll()
        return range(self.top, min(len(self.labels()), self.top + self.shown()))

    def row_at(self, sx: int, sy: int) -> int | None:
        x, _, w, _ = self.box()
        for i in self.visible_rows():
            if sy == self.row_y(i) and x < sx < x + w - 1:
                return i
        return None

    def click(self, sx: int, sy: int, engine) -> bool:
        i = self.row_at(sx, sy)
        if i is None:
            return True
        self.cursor = i
        return self.act(engine)

    def note(self, text: str | None, engine) -> None:
        if text:
            self.said = (self.said + [text])[-2:]
            engine.say(text)


@dataclass
class Deal:
    label: str
    pay: dict                         # kind -> how many you give
    get: dict                         # kind -> how many you get
    every: bool = False               # as many times over as you can afford
    after: str = ""                   # something more happens: "room", "soup"


class Shop(Modal):
    hint = "Up/Down choose, Enter trades, Esc leaves"
    leave_text = "You leave off trading."

    def __init__(self, title: str, greeting: str, deals: list):
        super().__init__()
        self.title, self.greeting, self.deals = title, greeting, deals

    def labels(self) -> list[str]:
        return [d.label for d in self.deals] + ["Leave"]

    def times(self, deal: Deal, inventory) -> int:
        """How many times over you can make a deal right now."""
        n = min(inventory.count(k) // v for k, v in deal.pay.items())
        return n if deal.every else min(n, 1)

    def dim(self, i: int, engine) -> bool:
        return i < len(self.deals) and not self.times(self.deals[i], engine.player.inventory)

    def footer(self, engine) -> str:
        bag = engine.player.inventory
        return f"Coins {bag.count('coin')}" + (f"   Logs {bag.count('log')}" if bag.count("log") else "")

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
        paid = " and ".join(items.amount(k, v * n) for k, v in deal.pay.items())
        if deal.after == "soup":
            return f"You pay {paid} for a bowl of hot soup. " + engine.eat_soup()
        if deal.after == "room":
            engine.rent_room()
        got = " and ".join(items.amount(k, v * n) for k, v in deal.get.items())
        return f"You give {paid} for {got}."

    def act(self, engine) -> bool:
        """Enter on the picked row. Returns False when you leave."""
        if self.cursor >= len(self.deals):
            return False
        self.note(self.trade(self.cursor, engine), engine)
        self.refresh(engine)
        return True


class Trader(Shop):
    """A shop whose deals depend on what you're carrying (the lumberjack's, the shopkeeper's)."""

    def __init__(self, title: str, greeting: str, make: Callable):
        self.make = make
        super().__init__(title, greeting, [])

    def refresh(self, engine) -> None:
        self.deals = self.make(engine)
        self.scroll()


@dataclass
class Option:
    label: str
    do: Callable                      # do(engine) -> what happened (str), or None
    ok: bool = True                   # drawn dim when False
    stay: bool = False                # keep the box open afterwards


class Picker(Modal):
    """A list of things to do. `build(engine)` makes the options (again after each one, for a
    barrel whose contents change)."""

    def __init__(self, title: str, build: Callable, greeting: str = "", leave: str = "Close",
                 leave_text: str = ""):
        super().__init__()
        self.title, self.build, self.greeting = title, build, greeting
        self.leave, self.leave_text = leave, leave_text
        self.options: list[Option] = []

    def refresh(self, engine) -> None:
        self.options = self.build(engine)
        self.scroll()

    def labels(self) -> list[str]:
        return [o.label for o in self.options] + [self.leave]

    def dim(self, i: int, engine) -> bool:
        return i < len(self.options) and not self.options[i].ok

    def act(self, engine) -> bool:
        if self.cursor >= len(self.options):
            return False
        opt = self.options[self.cursor]
        self.note(opt.do(engine), engine)
        if not opt.stay:
            return False
        self.refresh(engine)
        return True


class Container(Modal):
    """A barrel (or any other container): two tabs, one to take things out of it and one to
    put what you carry in. Left/Right (or Tab, or a click on a tab) switches between them;
    Enter moves the whole of what's picked."""
    hint = "Left/Right tabs, Up/Down choose, Enter, Esc"
    TABS = ("take", "put")
    KEEP = ("room key",)              # never put away: it goes back to the barkeeper

    def __init__(self, name: str, store, bag):
        super().__init__()
        self.name, self.store, self.bag = name, store, bag
        self.title = name[0].upper() + name[1:]
        self.leave = f"Close the {name.split()[-1]}"
        self.leave_text = f"You close the {name.split()[-1]}."
        self.tab = "take" if store else "put"

    # ------------------------------------------------------------- what's on each tab

    def putable(self) -> list[str]:
        return [k for k in self.bag if k not in self.KEEP]

    def rows_for(self, tab: str) -> list[tuple[str, str | None]]:
        """(label, kind) for each row on a tab; kind "*" moves everything, None closes."""
        if tab == "take":
            rows = [(f"Take {items.amount(k, n)}", k) for k, n in self.store.items()]
            if len(rows) > 1:
                rows.append(("Take everything", "*"))
        else:
            rows = [(f"Put in {items.amount(k, self.bag.count(k))}", k) for k in self.putable()]
            if len(rows) > 1:
                rows.append(("Put in everything", "*"))
        return rows + [(self.leave, None)]

    def labels(self) -> list[str]:
        return [label for label, _ in self.rows_for(self.tab)]

    @property
    def greeting(self) -> str:
        if self.tab == "take":
            return ("Inside: " + items.describe_pile(self.store) + ".") if self.store else "It's empty."
        return "You carry nothing you could put in." if not self.putable() else \
            f"Put things in the {self.name.split()[-1]}."

    def tab_labels(self) -> list[str]:
        return [f" Take ({sum(self.store.values())}) ",
                f" Put in ({sum(self.bag.count(k) for k in self.putable())}) "]

    def tab_spans(self) -> list[tuple[str, int, int]]:
        """(tab, x, width) of each tab along the top of the box."""
        x = self.box()[0] + 2
        out = []
        for tab, label in zip(self.TABS, self.tab_labels()):
            out.append((tab, x, len(label)))
            x += len(label) + 1
        return out

    def switch(self, tab: str | None = None) -> None:
        self.tab = tab or self.TABS[1 - self.TABS.index(self.tab)]
        self.cursor = self.top = 0

    # ------------------------------------------------------------- doing it

    def move(self, kind: str, engine) -> str:
        taking = self.tab == "take"
        src, dst = (self.store, self.bag) if taking else (self.bag, self.store)
        verb = "take" if taking else "put in"
        kinds = (list(src) if taking else self.putable()) if kind == "*" else [kind]
        moved = {k: src.count(k) for k in kinds if src.count(k)}
        for k, n in moved.items():
            src.take(k, n)
            dst.add(k, n)
        return f"You {verb} {items.describe_pile(moved)}." if moved else ""

    def act(self, engine) -> bool:
        rows = self.rows_for(self.tab)
        _, kind = rows[min(self.cursor, len(rows) - 1)]
        if kind is None:
            return False
        self.note(self.move(kind, engine), engine)
        self.scroll()
        return True

    def handle_key(self, sym, engine) -> bool:
        if sym in (KeySym.LEFT, KeySym.RIGHT, KeySym.TAB, KeySym.KP_4, KeySym.KP_6, KeySym.A, KeySym.D):
            self.switch()
            return True
        return super().handle_key(sym, engine)

    def click(self, sx: int, sy: int, engine) -> bool:
        if sy == self.box()[1] + 1:
            for tab, x, w in self.tab_spans():
                if x <= sx < x + w:
                    self.switch(tab)
            return True
        return super().click(sx, sy, engine)


# ----------------------------------------------------------------- the traders

def lumber_deals(engine) -> list:
    if not engine.player.inventory.count("log"):
        return []
    return [Deal(f"Sell a log for {LOG_PRICE} coins", {"log": 1}, {"coin": LOG_PRICE}),
            Deal("Sell all your logs", {"log": 1}, {"coin": LOG_PRICE}, every=True)]


def shopkeeper_deals(engine) -> list:
    """Weapons and armour for sale; and they'll buy any trinket or ring you're carrying."""
    deals = [Deal(f"Buy {items.amount(k, 1)}: {price} coins", {"coin": price}, {k: 1})
             for k, price in combat.WARES.items()]
    bag = engine.player.inventory
    for k in list(bag):
        value = items.KINDS[k].value
        if value and k not in combat.WARES:
            name = items.KINDS[k].plural if bag.count(k) > 1 else items.KINDS[k].name
            deals.append(Deal(f"Sell your {name} ({bag.count(k)}): {value} coin{'s' if value > 1 else ''} each",
                              {k: 1}, {"coin": value}, every=True))
    return deals


def for_actor(a, engine) -> Modal | None:
    """The shop someone keeps, if they trade and you've something to trade; None otherwise."""
    if a.kind == "lumberjack" and engine.player.inventory.count("log"):
        shop = Trader(f"{a.name}, the lumberjack", f"Good wood, that. I'll give you {LOG_PRICE} coins a log.",
                      lumber_deals)
    elif a.kind == "barkeeper":
        inn = next((b.name for b in engine.level.buildings if b.kind == "inn"), "the inn")
        shop = Shop(f"{a.name}, the barkeeper", f"Welcome to {inn}. A bed upstairs is {ROOM_PRICE} coins the night.",
                    [Deal(f"A room for the night: {ROOM_PRICE} coins", {"coin": ROOM_PRICE}, {"room key": 1},
                          after="room")])
    elif a.kind == "innkeeper":
        shop = Shop(f"{a.name}, the innkeeper", "Sit by the fire. The soup's hot, and it'll put you right.",
                    [Deal(f"A bowl of hot soup: {SOUP_PRICE} coins", {"coin": SOUP_PRICE}, {}, after="soup")])
    elif a.kind == "shopkeeper":
        shop = Trader(f"{a.name}, the shopkeeper", "Blades, armour, a bit of everything. And I buy trinkets.",
                      shopkeeper_deals)
    else:
        return None
    shop.refresh(engine)
    return shop
