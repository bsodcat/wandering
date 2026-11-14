"""Boxes over the game you pick from: shops, the use menu, and barrels.

Each is a list (Up/Down or the mouse picks, Enter takes it, Esc closes). Every row is one line,
straight under the one before; the box is as wide as its longest row needs (up to the screen),
and a list too long for the screen scrolls, with a scroll bar down the side: Up/Down,
PageUp/PageDown, Home/End or the mouse wheel move through it.

- A shop (`Shop`): walk into someone who trades while they're at work. Each deal pays some of
  what you carry for something else.
  - A lumberjack buys logs, once you've cut some (you need an axe: there's one by their house).
  - A barkeeper lets a room upstairs for the night: you get a room key, good until mid-morning,
    and can sleep (z) in any of the beds up there.
  - An innkeeper serves hot soup, which warms you, and treats wolf fever (game/sickness.py).
  - A town's shopkeeper sells common weapons and armour, and buys trinkets and rings.
  - A shop that buys as well as sells (the shopkeeper's, the blacksmith's) has two tabs: Buy
    and Sell. Left/Right, Tab or a click on a tab switches between them. A shop shows at most
    MOST_ROWS rows at a time, and scrolls past that.
- A `Picker`: the use menu (e, or a click on something you can use: a barrel, a bed,
  someone).
- `Equipment` (q): your weapon hand and each place you wear something (game/gear.py), what's
  there, and what it all adds up to; Enter on a row (a `SlotPicker`) lists what you could put
  there instead.
- A `Container`: what's in a barrel, on two tabs: Take (things out) and Put in (what you
  carry). Left/Right, Tab or a click on a tab switches between them.
"""
from __future__ import annotations

import textwrap
from dataclasses import dataclass
from typing import Callable

from tcod.event import KeySym

from . import combat
from . import gear
from . import items
from .people import ROOM_PRICE

LOG_PRICE = 3
SOUP_PRICE = 4
BOX_W = 56                   # the narrowest a box is
MOST_GREETING = 3            # lines of greeting at the top, at most
MOST_SAID = 3                # lines of what just happened, at the bottom
MOST_ROWS = 15               # a shop's list scrolls past this many rows


class Modal:
    """A box of rows to pick from, over the game."""
    title = ""
    greeting = ""
    hint = "Up/Down choose, Enter picks, Esc closes"
    leave_text = ""
    tabbed = False               # a row of tabs under the title (Container)

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
        elif sym == KeySym.HOME:
            self.cursor = 0
        elif sym == KeySym.END:
            self.cursor = n - 1
        elif sym in (KeySym.RETURN, KeySym.KP_ENTER, KeySym.SPACE):
            return self.act(engine)
        self.scroll()
        return True

    # ------------------------------------------------------------- where things go

    def width(self) -> int:
        """Wide enough for the longest row (and a scroll bar), within the screen."""
        longest = max((len(label) for label in self.labels()), default=0)
        return max(BOX_W, min(self.cols - 4, longest + 8))

    def greeting_lines(self) -> list[str]:
        return textwrap.wrap(self.greeting, self.width() - 4)[:MOST_GREETING]

    def said_lines(self) -> list[str]:
        """What just happened, from its start; if it runs on longer, the end's cut with "..."
        (it's all in the log too)."""
        if not self.said:
            return []
        lines = textwrap.wrap(self.said[-1], self.width() - 4)
        if len(lines) > MOST_SAID:
            lines = lines[:MOST_SAID]
            lines[-1] = lines[-1][: self.width() - 7] + "..."
        return lines

    def header(self) -> int:
        """Lines from the top border to the first row: tabs, the greeting and a blank line."""
        return 1 + self.tabbed + len(self.greeting_lines()) + 1

    def footer_lines(self) -> int:
        """Lines from the last row to the bottom: a blank, what happened, the coins, the keys
        and the border."""
        return 1 + MOST_SAID + 3

    def shown(self) -> int:
        """How many rows fit on the screen, with a line's margin above and below the box."""
        room = self.rows - 2 - self.header() - self.footer_lines()
        return max(1, min(len(self.labels()), room))

    def scroll(self) -> None:
        n, k = len(self.labels()), self.shown()
        self.cursor = max(0, min(self.cursor, n - 1))
        if self.cursor < self.top:
            self.top = self.cursor
        elif self.cursor >= self.top + k:
            self.top = self.cursor - k + 1
        self.top = max(0, min(self.top, n - k))

    def scroll_by(self, lines: int) -> None:
        """The mouse wheel: the list moves, and the pick stays on a row you can see."""
        n, k = len(self.labels()), self.shown()
        self.top = max(0, min(self.top + lines, n - k))
        self.cursor = max(self.top, min(self.cursor, self.top + k - 1))

    def scrollable(self) -> bool:
        return len(self.labels()) > self.shown()

    def box(self) -> tuple[int, int, int, int]:
        w = self.width()
        h = self.header() + self.shown() + self.footer_lines()
        return (self.cols - w) // 2, (self.rows - h) // 2, w, h

    def row_y(self, i: int) -> int:
        return self.box()[1] + self.header() + (i - self.top)

    def visible_rows(self) -> range:
        self.scroll()
        return range(self.top, min(len(self.labels()), self.top + self.shown()))

    def scroll_bar(self) -> tuple[int, int, int] | None:
        """(column, first line, lines) of the scroll bar's thumb, if the list scrolls."""
        if not self.scrollable():
            return None
        n, k = len(self.labels()), self.shown()
        x, _, w, _ = self.box()
        size = max(1, k * k // n)
        start = round(self.top * (k - size) / max(1, n - k))
        return x + w - 2, self.box()[1] + self.header() + start, size

    def row_at(self, sx: int, sy: int) -> int | None:
        x, _, w, _ = self.box()
        for i in self.visible_rows():
            if sy == self.row_y(i) and x < sx < x + w - 2:
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


class Tabs:
    """Tabs along the top of a box (TABS, tab_labels): Left/Right, Tab or a click switches."""
    TABS: tuple = ()

    def tab_labels(self) -> list[str]:
        raise NotImplementedError

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

    def handle_key(self, sym, engine) -> bool:
        if self.tabbed and sym in (KeySym.LEFT, KeySym.RIGHT, KeySym.TAB, KeySym.KP_4, KeySym.KP_6,
                                   KeySym.A, KeySym.D):
            self.switch()
            return True
        return super().handle_key(sym, engine)

    def click(self, sx: int, sy: int, engine) -> bool:
        if self.tabbed and sy == self.box()[1] + 1:
            for tab, x, w in self.tab_spans():
                if x <= sx < x + w:
                    self.switch(tab)
            return True
        return super().click(sx, sy, engine)


@dataclass
class Deal:
    label: str
    pay: dict                         # kind -> how many you give
    get: dict                         # kind -> how many you get
    every: bool = False               # as many times over as you can afford
    after: str = ""                   # something more happens: "room", "soup"

    @property
    def sell(self) -> bool:
        """Whether it's you selling (you're paid in coin)."""
        return "coin" in self.get


class Shop(Tabs, Modal):
    """Deals to pick from. With `buys` (the shop buys from you as well as selling), the deals
    split onto a Buy tab and a Sell tab."""
    hint = "Up/Down choose, Enter trades, Esc leaves"
    leave_text = "You leave off trading."
    TABS = ("buy", "sell")

    def __init__(self, title: str, greeting: str, deals: list, buys: bool = False):
        super().__init__()
        self.title, self.greeting, self.all_deals = title, greeting, deals
        self.tabbed = buys
        self.tab = "buy"
        if buys:
            self.hint = "Left/Right Buy/Sell, Enter trades, Esc leaves"

    @property
    def deals(self) -> list:
        """The deals on the tab you're on (all of them, in a shop without tabs)."""
        if not self.tabbed:
            return self.all_deals
        return [d for d in self.all_deals if d.sell == (self.tab == "sell")]

    @deals.setter
    def deals(self, deals: list) -> None:
        self.all_deals = deals

    def tab_labels(self) -> list[str]:
        sells = sum(d.sell for d in self.all_deals)
        return [" Buy ", f" Sell ({sells}) "]

    def greeting_lines(self) -> list[str]:
        lines = super().greeting_lines()
        if self.tabbed and self.tab == "sell" and not self.deals:
            lines = lines + ["You've nothing they'd buy."]
        return lines

    def shown(self) -> int:
        return min(MOST_ROWS, super().shown())

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

    def __init__(self, title: str, greeting: str, make: Callable, buys: bool = False):
        self.make = make
        super().__init__(title, greeting, [], buys)

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


class Container(Tabs, Modal):
    """A barrel (or any other container): two tabs, one to take things out of it and one to
    put what you carry in. Left/Right (or Tab, or a click on a tab) switches between them;
    Enter moves the whole of what's picked."""
    hint = "Left/Right tabs, Up/Down choose, Enter, Esc"
    tabbed = True
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
        if self.tab == "take":                  # the rows list what's inside, so this stays short
            if not self.store:
                return "It's empty."
            things, kinds = sum(self.store.values()), len(self.store)
            return f"Inside: {things} thing{'s' if things != 1 else ''}, {kinds} kind{'s' if kinds != 1 else ''}."
        return "You carry nothing you could put in." if not self.putable() else \
            f"Put things in the {self.name.split()[-1]}."

    def tab_labels(self) -> list[str]:
        return [f" Take ({sum(self.store.values())}) ",
                f" Put in ({sum(self.bag.count(k) for k in self.putable())}) "]

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


# ----------------------------------------------------------------- the traders

def lumber_deals(engine) -> list:
    if not engine.player.inventory.count("log"):
        return []
    return [Deal(f"Sell a log for {LOG_PRICE} coins", {"log": 1}, {"coin": LOG_PRICE}),
            Deal("Sell all your logs", {"log": 1}, {"coin": LOG_PRICE}, every=True)]


def shopkeeper_deals(engine) -> list:
    """Weapons, armour, clothes and climbing gear for sale; and they'll buy any trinket or ring you're carrying."""
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


SMITH_WARES = ["dagger", "spear", "mace", "short sword", "axe", "shovel", "iron helm", "mail shirt",
               "iron-bound shield", "hobnailed boots", "climbing gear"]
SCRAP = ["rusty dagger", "crude knife", "horseshoe", "iron nails", "iron rivets"]   # a smith buys these


def smith_deals(engine) -> list:
    """What the blacksmith has made, and the old iron they'll buy."""
    deals = [Deal(f"Buy {items.amount(k, 1)}: {combat.WARES[k]} coins", {"coin": combat.WARES[k]}, {k: 1})
             for k in SMITH_WARES]
    bag = engine.player.inventory
    for k in SCRAP:
        if bag.count(k):
            value = max(1, items.KINDS[k].value)
            deals.append(Deal(f"Sell your {items.KINDS[k].plural if bag.count(k) > 1 else k} ({bag.count(k)}): "
                              f"{value} coin{'s' if value > 1 else ''} each", {k: 1}, {"coin": value}, every=True))
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
    elif a.kind == "blacksmith":
        shop = Trader(f"{a.name}, the blacksmith", "Fresh from the forge. And I'll take any old iron off you.",
                      smith_deals, buys=True)
    elif a.kind == "carter":
        from . import carts
        return carts.ride_menu(a.name, engine)
    elif a.kind == "shopkeeper":
        shop = Trader(f"{a.name}, the shopkeeper", "Blades, armour, warm things, climbing gear. And I buy trinkets.",
                      shopkeeper_deals, buys=True)
    else:
        return None
    shop.refresh(engine)
    return shop


# ----------------------------------------------------------------- the equipment menu

WEAPON_SLOT = "weapon"


def weapon_words(kind: str | None) -> str:
    w = combat.WEAPONS[kind] if kind else combat.FISTS
    return f"damage {w.low}-{w.high}, {w.to_hit:+.0%} to hit"


def summary(engine) -> list[str]:
    """What everything you have on adds up to, in three lines."""
    from .player import insulation
    p = engine.player
    held, w = combat.weapon_of(p)
    roped = gear.can_climb(p)
    climb = f"yes, {gear.slip_chance(p, False, False):.0%} slip" if roped else "no"
    return [f"Attack {w.low}-{w.high} ({w.to_hit:+.0%} to hit)   Armour {gear.armour(p)}   Block {gear.block(p):.0%}",
            f"Warmth {insulation(p):+.0f}°C (clothes {p.clothing:+.0f}, gear {gear.warmth(p):+.0f})   "
            f"Rain cover {gear.cover(p):.0%}",
            f"Footing {gear.footing(p):.0%}   Burden {gear.burden(p):+.0%} effort   Climbing {climb}"]


class Equipment(Picker):
    """q: a row for your weapon hand and for each place you wear something, with what's there
    and what it does; what it all adds up to at the top. Enter on a row lists what you carry
    that could go there."""
    hint = "Up/Down choose, Enter changes, Esc closes"

    def __init__(self, cursor: int = 0):
        super().__init__("Equipment", self.rows)
        self.cursor = cursor
        self.lines: list[str] = []

    @staticmethod
    def rows(engine) -> list:
        p = engine.player
        held, _ = combat.weapon_of(p)
        on = gear.worn(p)
        out = [Option(f"{'Weapon':<8} {held or 'bare hands':<18} {weapon_words(held)}",
                      lambda e: open_slot(e, WEAPON_SLOT))]
        for slot in gear.SLOTS:
            kind = on.get(slot)
            out.append(Option(f"{gear.SLOT_NAMES[slot]:<8} {kind or '-':<18} {gear.describe(kind) if kind else ''}".rstrip(),
                              lambda e, s=slot: open_slot(e, s)))
        return out

    def refresh(self, engine) -> None:
        super().refresh(engine)
        self.lines = summary(engine)

    def width(self) -> int:
        longest = max((len(line) for line in self.lines), default=0)
        return max(super().width(), min(self.cols - 4, longest + 4))

    def greeting_lines(self) -> list[str]:
        return [line[: self.width() - 4] for line in self.lines]


class SlotPicker(Picker):
    """What you carry that could go in one place (or in your hand); Back (or Esc) goes back to
    the equipment menu."""
    hint = "Up/Down choose, Enter picks, Esc back"

    def __init__(self, slot: str, engine):
        self.slot = slot
        name = "your weapon hand" if slot == WEAPON_SLOT else gear.SLOT_NAMES[slot].lower()
        super().__init__(f"Equipment: {name}", self.choices, leave="Back")
        self.greeting = "Pick what to use." if slot == WEAPON_SLOT else "Pick what to wear here."
        self.refresh(engine)

    def back(self, engine, text: str | None = None) -> None:
        index = 0 if self.slot == WEAPON_SLOT else 1 + gear.SLOTS.index(self.slot)
        engine.shop = equipment(engine, index)
        engine.shop.note(text, engine)

    def choices(self, engine) -> list:
        p, bag = engine.player, engine.player.inventory
        out = []
        if self.slot == WEAPON_SLOT:
            held, _ = combat.weapon_of(p)
            for k in combat.WEAPONS:
                if bag.count(k) and k != held:
                    out.append(Option(f"Wield the {k}  ({weapon_words(k)})",
                                      lambda e, k=k: self.back(e, combat.wield(e.player, k))))
            if held:
                out.append(Option(f"Put away the {held}", lambda e: self.back(e, combat.wield(e.player, None))))
        else:
            on = gear.worn(p).get(self.slot)
            for k, g in gear.GEAR.items():
                if g.slot == self.slot and bag.count(k) and k != on:
                    out.append(Option(f"Put on the {k}  ({gear.describe(k)})",
                                      lambda e, k=k: self.back(e, gear.wear(e.player, k))))
            if on:
                out.append(Option(f"Take off the {on}", lambda e: self.back(e, gear.take_off(e.player, on))))
        if not out:
            out.append(Option("You carry nothing that goes here", lambda e: self.back(e), ok=False))
        return out

    def act(self, engine) -> bool:
        if self.cursor >= len(self.options):
            self.back(engine)
            return False
        return super().act(engine)

    def handle_key(self, sym, engine) -> bool:
        if sym == KeySym.ESCAPE:
            self.back(engine)
            return False
        return super().handle_key(sym, engine)


def open_slot(engine, slot: str) -> None:
    engine.shop = SlotPicker(slot, engine)


def equipment(engine, cursor: int = 0) -> Equipment:
    menu = Equipment(cursor)
    menu.refresh(engine)
    return menu


# ----------------------------------------------------------------- riding a cart

class RideMenu(Modal):
    """A carter's offer, over the world map: the nearest towns by road, how long the ride takes,
    about when you'd arrive, and the fare. Enter rides there (game/carts.py)."""
    hint = "Up/Down choose, Enter rides, Esc leaves"
    leave_text = "You leave the cart be."
    overworld = True                     # drawn over the world map, the way marked

    def __init__(self, driver: str, cart, site, region, options):
        super().__init__()
        self.driver, self.cart, self.site, self.region, self.options = driver, cart, site, region, options
        self.title = f"{driver}'s cart"
        self.greeting = ""

    def refresh(self, engine) -> None:
        from . import carts
        first = self.driver.split()[0]
        state = carts.where(self.cart, engine.minutes) if self.cart is not None else None
        if not self.options:
            self.greeting = f'{first}: "No roads out of here I can take you on, I\'m afraid."'
        elif state is not None and state[0] == "road":
            self.greeting = (f'{first}: "Bound for {state[1].b.name}. Hop up: for the fare I\'ll take you '
                             f'any of these ways."')
        elif state is not None and self.site is not None:
            nxt = next((leg.b.name for leg in self.cart.legs if leg.a is self.site), None)
            self.greeting = (f'{first}: "I\'m off to {nxt} in {carts.hours_text(state[2] / 60)}. But for the '
                             f'fare I\'ll take you any of these ways, straight off."' if nxt else f'{first}: "Where to?"')
        else:
            self.greeting = f'{first}: "Where to?"'
        self.scroll()

    def labels(self) -> list[str]:
        from . import carts
        out = []
        for dest, hours, _ in self.options:
            out.append(f"{dest.name:<14} {carts.hours_text(hours):>13}   {carts.fare(hours):>2} coins")
        return out + ["Leave"]

    def dim(self, i: int, engine) -> bool:
        from . import carts
        return i < len(self.options) and engine.player.inventory.count("coin") < carts.fare(self.options[i][1])

    def footer(self, engine) -> str:
        from . import carts
        text = f"Coins {engine.player.inventory.count('coin')}"
        if self.cursor < len(self.options):
            dest, hours, _ = self.options[self.cursor]
            text += f"   Arrive about {carts.arrival_text(engine, hours)}"
        return text

    def act(self, engine) -> bool:
        from . import carts
        if self.cursor >= len(self.options):
            return False
        dest, hours, path = self.options[self.cursor]
        text = carts.ride(engine, self.driver, dest, hours, path)
        if text:
            self.note(text, engine)
            return engine.shop is self
        return False

    def marks(self, engine) -> list:
        """What to mark on the world map: each town you could go to, and the way to the one picked."""
        from .worldgen import SITE_KINDS
        out = []
        for i, (dest, hours, path) in enumerate(self.options):
            picked = i == self.cursor
            if picked:
                out += [(c, "·", (255, 220, 120)) for c in path[1:-1]]
            for c in dest.cells:
                out.append((c, SITE_KINDS[dest.kind][0], (255, 240, 150) if picked else (200, 200, 200)))
        for c in (self.site.cells if self.site is not None else [self.region]):
            out.append((c, "@", (255, 255, 255)))
        return out
