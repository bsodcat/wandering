"""Drawing the panels laid over the map: the stats on the left, the Info / Map / Log panel on
the right, the recent messages along the bottom, and the tabs that bring hidden panels back.
Where everything goes, and what's open, is game/ui.py.
"""
from __future__ import annotations

import textwrap

import numpy as np
import tcod

from . import biomes as B
from . import combat
from . import items
from . import sickness
from . import tiles as T
from . import trees
from .climate import clock_text, date_text, describe_wind, time_of_day
from .elevation import LEVEL_M
from .engine import OVERLAYS, Engine
from .player import NORMAL, body_status, feels_like, stamina_status, wet_status
from .ui import LEFT_HIDE, LEFT_SHOW, LEFT_W, RIGHT_W, STRIP_H, TAB_NAMES

TEXT, DIM, TITLE = (220, 220, 220), (130, 130, 130), (255, 220, 120)
PANEL_BG, HEADER_BG, BORDER = (14, 14, 20), (32, 32, 44), (70, 70, 85)
TAB_ON, TAB_OFF = (255, 220, 120), (150, 150, 160)
EMPTY_BAR = (55, 55, 60)
LOOK_LINES = 7          # lines the Info tab keeps for what's under the pointer


class Writer:
    """Prints lines down a column of a panel, cut to its width."""

    def __init__(self, console, x: int, y: int, width: int):
        self.console, self.x, self.y, self.width = console, x, y, width

    def line(self, text: str = "", colour=TEXT) -> None:
        self.console.print(self.x, self.y, text[: self.width], fg=colour)
        self.y += 1

    def gap(self, n: int = 1) -> None:
        self.y += n

    def bar(self, value: float, top: float, colour) -> None:
        filled = int(round(self.width * max(0.0, min(1.0, value / top))))
        self.console.print(self.x, self.y, "█" * filled, fg=colour)
        self.console.print(self.x + filled, self.y, "░" * (self.width - filled), fg=EMPTY_BAR)
        self.y += 1

    def gauge(self, value: float, low: float, high: float, mark, colour) -> None:
        """A scale from low to high with a marker at `value` and a tick at `mark`."""
        pos = int(round((self.width - 1) * max(0.0, min(1.0, (value - low) / (high - low)))))
        tick = int(round((self.width - 1) * (mark - low) / (high - low)))
        cells = ["─"] * self.width
        cells[tick] = "┼"
        self.console.print(self.x, self.y, "".join(cells), fg=EMPTY_BAR)
        self.console.print(self.x + pos, self.y, "█", fg=colour)
        self.y += 1


def panel(console, x: int, width: int, border_x: int) -> None:
    """An opaque panel with a header row and a border line on its inner side."""
    console.draw_rect(x, 0, width, console.height, ord(" "), fg=TEXT, bg=PANEL_BG)
    console.draw_rect(x, 0, width, 1, ord(" "), bg=HEADER_BG)
    console.draw_rect(border_x, 0, 1, console.height, ord("│"), fg=BORDER, bg=PANEL_BG)


def button(console, box, text: str) -> None:
    x, y, w = box
    console.print(x, y, text[:w].ljust(w), fg=TAB_ON, bg=HEADER_BG)


# ----------------------------------------------------------------- left: your stats

def warmth_colour(body: float):
    status = body_status(body)
    if status in ("Comfortable",):
        return (110, 200, 110)
    if status in ("Chilly", "Warm"):
        return (220, 200, 90)
    return (90, 140, 240) if body < NORMAL else (240, 100, 60)


# The bars, in order: (label, value, top, colour, status). Add a line here for a new stat.
BARS = [
    ("Health", lambda p: p.health, 100, (200, 60, 60), lambda p: "" if p.health > 99 else "Hurt" if p.health > 40 else "Badly hurt"),
    ("Stamina", lambda p: p.stamina, 100, (90, 190, 90), lambda p: stamina_status(p.stamina)),
    ("Wet", lambda p: p.wet, 100, (70, 120, 220), lambda p: wet_status(p.wet)),
]


def conditions(e: Engine) -> list[tuple[str, tuple]]:
    p = e.player
    out = []
    warmth = body_status(p.body)
    if warmth != "Comfortable":
        out.append((warmth, warmth_colour(p.body)))
    for label, value, top, colour, status in BARS:
        text = status(p)
        if text and text not in ("Fresh", "Dry"):
            out.append((text, colour))
    ill = sickness.status(p)
    if ill:
        out.append((ill + " (wolf fever)" if ill != "Recovering" else "Recovering from fever",
                    (230, 150, 60) if ill != "Recovering" else (200, 200, 120)))
    return out or [("Fine", (110, 200, 110))]


def draw_stats(console, e: Engine) -> None:
    p = e.player
    panel(console, 0, LEFT_W, LEFT_W - 1)
    console.print(1, 0, p.name[: LEFT_W - 5], fg=TITLE, bg=HEADER_BG)
    button(console, LEFT_HIDE, "◄c")
    w = Writer(console, 1, 2, LEFT_W - 3)
    for label, value, top, colour, status in BARS:
        v = value(p)
        w.line(f"{label:<8}{v:5.0f}  {status(p)}"[: w.width])
        w.bar(v, top, colour)
        w.gap()
    w.line(f"Warmth  {p.body:5.1f}°C")
    w.gauge(p.body, 33.0, 41.0, NORMAL, warmth_colour(p.body))
    w.line(f"{'cold':<{w.width // 2}}{'hot':>{w.width - w.width // 2}}", EMPTY_BAR)
    w.line(body_status(p.body), warmth_colour(p.body))
    w.gap()
    c = e.now
    if e.indoors and e.level is not None:
        w.line(f"Indoors   {e.indoor_air:5.1f}°C")
    else:
        w.line(f"Feels like{feels_like(c.air, c.wind, p.wet, e.shelter):5.1f}°C")
    w.line(f"Clothing  {p.clothing:+5.0f}°C", DIM)
    w.line(f"Shelter   {e.shelter:5.0%}", DIM)
    w.line(f"Sight     {e.sight_radius():5d}", DIM)
    if e.level is not None and e.level.elev.max() > e.level.elev.min():
        w.line(f"Height    {int(e.level.elev[e.lx, e.ly]) * LEVEL_M:4.0f} m", DIM)
    w.line(f"Coins     {p.inventory.count('coin'):5d}", (240, 210, 90))
    held, weapon = combat.weapon_of(p)
    w.line(f"Attack  {weapon.low:>3}-{weapon.high:<3}", DIM)
    w.line(f"Armour    {combat.protection(p):5d}", DIM)
    w.gap()
    w.line("Condition", TITLE)
    for text, colour in conditions(e):
        w.line(f" {text}", colour)
    if not p.alive:
        w.gap()
        w.line(f"You {p.cause}.", (220, 80, 80))


# ----------------------------------------------------------------- right: info

def draw_info(console, e: Engine, look: list[str]) -> None:
    p, wd, c = e.player, e.world, e.now
    w = Writer(console, e.panels.right_x + 2, 2, RIGHT_W - 3)
    w.line(date_text(e.minutes), TITLE)
    w.line(f"{clock_text(e.minutes)}  {time_of_day(e.lat, e.minutes)}")
    w.gap()
    site = e.site
    if e.level is not None and not e.level.surface:
        w.line(e.level.name, TITLE)
        w.line("Underground" if e.underground else ("Indoors" if e.indoors else "Out in the open"), DIM)
        w.line(e.tile.name.capitalize(), DIM)
    else:
        w.line(site.name if site else e.biome.name, TITLE)
        if site:
            w.line(f"{site.kind.title()}{' (port)' if site.port else ''}, {e.biome.name.lower()}", DIM)
        extras = [t for t, on in (("river", wd.river[p.x, p.y]), ("road", wd.road[p.x, p.y])) if on]
        w.line(f"Alt {max(0, wd.elevation[p.x, p.y]):.0f} m" + (f"  {', '.join(extras)}" if extras else ""), DIM)
        if e.level is not None:
            w.line(e.tile.name.capitalize() + ("  indoors" if e.indoors else "  under trees" if e.leaves else ""), DIM)
    w.gap()
    if e.indoors and e.level is not None:
        w.line(f"Outside {c.air:5.1f}°C")
        w.line("Underground" if e.underground else f"{c.kind} outside", DIM)
    else:
        w.line(f"Air   {c.air:5.1f}°C  {c.kind}")
        w.line(f"{describe_wind(c.wind)} {c.wind:.0f} km/h", DIM)
    if e.level is None:
        w.line(f"Overlay {OVERLAYS[e.overlay]}{'  revealed' if e.reveal else ''}", DIM)
    else:
        w.line(f"Region {p.x},{p.y}  at {e.lx},{e.ly}", DIM)
    if look:
        w.gap()
        w.line("Look", TITLE)
        wrapped = [part for text in look for part in textwrap.wrap(text, w.width)]
        for text in wrapped[:LOOK_LINES]:
            w.line(text, DIM)
    if e.level is None:
        keys = ("arrows/numpad/wasd  go", "> Enter  go into region", ". or 5   wait an hour",
                "z        rest 8 hours", "o        overlays", "m        reveal map")
    else:
        keys = ("arrows/numpad/wasd  go", "> <      stairs down/up", "<        (no stairs) map",
                f"v        {'ground' if e.treetops else 'treetops'} view", ". or 5   wait an hour",
                "z        rest / sleep", "g x      pick up, dig", "i        inventory",
                "e        use menu", "bump     fight",
                f"o        {'normal' if e.relief else 'relief'} view", "m        reveal level")
    keys += ("mouse    L use, R walk", "Tab      panel tabs", "c        stats panel", "F11      fullscreen", "Esc      menu, options")
    w.y = max(w.y + 1, console.height - len(keys) - 1)
    for text in keys + (f"Seed {wd.seed}",):
        w.line(text, DIM)


# ----------------------------------------------------------------- right: minimap

def half_blocks(console, x: int, y: int, colours: np.ndarray) -> None:
    """Draws a (w, 2h, 3) image as w x h cells of upper-half blocks: two pixels a cell."""
    w, h2, _ = colours.shape
    h = h2 // 2
    out = console.rgb[x: x + w, y: y + h]
    out["ch"] = ord("▀")
    out["fg"] = np.clip(colours[:, 0::2][:, :h], 0, 255).astype(np.uint8)
    out["bg"] = np.clip(colours[:, 1::2][:, :h], 0, 255).astype(np.uint8)


UNKNOWN = np.array((10, 10, 14))
YOU = np.array((255, 255, 255))
SETTLEMENT = np.array((255, 220, 120))


def world_colours(e: Engine, xs: np.ndarray, ys: np.ndarray) -> np.ndarray:
    """The world map's colours at sample points, with what you haven't seen blacked out."""
    wd = e.world
    gx, gy = np.meshgrid(xs, ys, indexing="ij")
    biome = wd.biome[gx, gy]
    col = B.FG[biome] * 0.55 + B.BG[biome] * 0.45
    col[wd.river[gx, gy]] = (70, 120, 210)
    col[wd.road[gx, gy]] = col[wd.road[gx, gy]] * 0.5 + np.array((185, 150, 95)) * 0.5
    known = e.explored[gx, gy] | e.reveal
    col[~known] = UNKNOWN
    return col


def mark(col: np.ndarray, xs: np.ndarray, ys: np.ndarray, x: float, y: float, colour) -> None:
    i, j = int(np.abs(xs - x).argmin()), int(np.abs(ys - y).argmin())
    col[i, j] = colour


def draw_minimap(console, e: Engine, seconds: float) -> None:
    wd = e.world
    x0, width = e.panels.right_x + 2, RIGHT_W - 3
    blink = int(seconds * 3) % 2 == 0
    w = Writer(console, x0, 2, width)
    w.line("The world", TITLE)
    rows = 12                                     # 24 samples tall: square on screen
    xs = np.linspace(0, wd.width - 1, width).round().astype(int)
    ys = np.linspace(0, wd.height - 1, rows * 2).round().astype(int)
    col = world_colours(e, xs, ys)
    for s in wd.sites:
        if s.kind == "town" and (e.explored[s.x, s.y] or e.reveal):
            mark(col, xs, ys, s.x, s.y, SETTLEMENT)
    if blink:
        mark(col, xs, ys, e.player.x, e.player.y, YOU)
    half_blocks(console, x0, w.y, col)
    w.gap(rows + 1)
    p = e.player
    if e.level is None:
        w.line("Around you", TITLE)
        span_x, span_y = width * 2, rows * 2           # two regions a sample across, one down
        xs = np.clip(np.arange(p.x - span_x // 2, p.x + span_x // 2, 2), 0, wd.width - 1)
        ys = np.clip(np.arange(p.y - span_y // 2, p.y + span_y // 2), 0, wd.height - 1)
        col = world_colours(e, xs[:width], ys[: rows * 2])
        for s in wd.sites:
            if (e.explored[s.x, s.y] or e.reveal) and s.settled:
                if xs[0] <= s.x <= xs[-1] and ys[0] <= s.y <= ys[-1]:
                    mark(col, xs, ys, s.x, s.y, SETTLEMENT)
        if blink:
            mark(col, xs, ys, p.x, p.y, YOU)
    else:
        level = e.level
        w.line(level.name if not level.surface else "This region", TITLE)
        xs = np.linspace(0, level.width - 1, width).round().astype(int)
        ys = np.linspace(0, level.height - 1, rows * 2).round().astype(int)
        gx, gy = np.meshgrid(xs, ys, indexing="ij")
        t = level.tiles[gx, gy]
        col = T.FG[t] * 0.45 + T.BG[t] * 0.55
        solid = ~T.WALK[t] & ~T.WATERY[t]
        col[solid] = T.FG[t][solid] * 0.8
        canopy = level.canopy[gx, gy] if e.treetops and level.surface else np.zeros(t.shape, np.uint8)
        col[canopy > 0] = (40, 110, 50)
        col[~level.explored[gx, gy]] = UNKNOWN
        if blink:
            mark(col, xs, ys, e.lx, e.ly, YOU)
    half_blocks(console, x0, w.y, col)
    w.gap(rows + 1)
    w.line(f"Explored {e.explored.mean():.0%} of the world", DIM)
    if e.level is not None:
        w.line(f"and {e.level.explored.mean():.0%} of {'here' if e.level.surface else 'this level'}", DIM)


# ----------------------------------------------------------------- right: log

def log_lines(e: Engine, width: int) -> list[str]:
    texts = list(e.messages)
    if texts and e.repeats > 1:
        texts[-1] = f"{texts[-1]} (x{e.repeats})"
    out = []
    for text in texts:
        out += textwrap.wrap(text, width, subsequent_indent=" ") or [""]
    return out


def draw_log(console, e: Engine) -> None:
    width = RIGHT_W - 3
    lines = log_lines(e, width)
    rows = console.height - 4
    e.panels.log_scroll = min(e.panels.log_scroll, max(0, len(lines) - rows))
    end = len(lines) - e.panels.log_scroll
    shown = lines[max(0, end - rows): end]
    w = Writer(console, e.panels.right_x + 2, 2, width)
    for i, text in enumerate(shown):
        newest = end - len(shown) + i >= len(lines) - 3
        w.line(text, TEXT if newest else DIM)
    hint = "PgUp/PgDn, wheel: scroll" if not e.panels.log_scroll else f"{e.panels.log_scroll} lines back; End"
    console.print(e.panels.right_x + 2, console.height - 1, hint[:width], fg=DIM)


def draw_right(console, e: Engine, look: list[str], seconds: float) -> None:
    right_x = e.panels.right_x
    panel(console, right_x, RIGHT_W, right_x)
    for tab, x, width in e.panels.tab_spans():
        on = tab == e.panels.tab
        console.print(x, 0, f" {TAB_NAMES[tab]} ", fg=(20, 20, 20) if on else TAB_OFF,
                      bg=TAB_ON if on else HEADER_BG)
    button(console, e.panels.right_hide, "►")
    if e.panels.tab == "info":
        draw_info(console, e, look)
    elif e.panels.tab == "map":
        draw_minimap(console, e, seconds)
    elif e.panels.tab == "inv":
        draw_inventory(console, e)
    else:
        draw_log(console, e)


def draw_inventory(console, e: Engine) -> None:
    """What you carry, and what you can do with it."""
    bag = e.player.inventory
    w = Writer(console, e.panels.right_x + 2, 2, RIGHT_W - 3)
    w.line("Carrying", TITLE)
    w.line(f"{bag.count('coin')} coins", (240, 210, 90))
    w.gap()
    things = [k for k in bag if k != "coin"]
    if not things:
        w.line("Nothing else.", DIM)
    held, _ = combat.weapon_of(e.player)
    on = combat.worn(e.player).values()
    for kind in things:
        k = items.KINDS[kind]
        n = bag.count(kind)
        console.print(w.x, w.y, k.char, fg=k.colour)
        w.x += 2
        tag = " (in hand)" if kind == held else " (worn)" if kind in on else ""
        w.line((k.name if n == 1 else f"{k.plural} x{n}") + tag, TITLE if tag else TEXT)
        w.x -= 2
        for part in textwrap.wrap(k.note, w.width - 2):
            w.line(f"  {part}", DIM)
    if e.room_until is not None:
        w.gap()
        w.line("Your room's paid for", DIM)
        w.line(f"until {clock_text(e.room_until)}", DIM)
    keys = ("g        pick up", "x        dig (shovel)", "e        eat, wield, wear",
            "walk into a tree with", "an axe to fell it", "walk into a trader", "to trade with them")
    w.y = max(w.y + 1, console.height - len(keys) - 1)
    for text in keys:
        w.line(text, DIM)


# ----------------------------------------------------------------- the bottom strip

def draw_strip(console, e: Engine) -> None:
    """The last few messages over a darkened band of the map, between the open panels."""
    if e.panels.right_open and e.panels.tab == "log":
        return
    x0, x1 = e.panels.left_edge(), e.panels.right_edge()
    width = x1 - x0 - 2
    lines = log_lines(e, width)[-STRIP_H:]
    if not lines:
        return
    y0 = console.height - len(lines)
    band = console.rgb[x0: x1, y0:]
    band["bg"] = (band["bg"] * 0.3).astype(np.uint8)
    band["fg"] = (band["fg"] * 0.35).astype(np.uint8)
    for i, text in enumerate(lines):
        age = len(lines) - 1 - i
        shade = max(110, 235 - age * 35)
        console.print(x0 + 1, y0 + i, text[:width], fg=(shade, shade, shade))


def draw_hud(console: tcod.console.Console, e: Engine, look: list[str], seconds: float) -> None:
    draw_strip(console, e)
    if e.panels.left_open:
        draw_stats(console, e)
    else:
        button(console, LEFT_SHOW, "►c")
    if e.panels.right_open:
        draw_right(console, e, look, seconds)
    else:
        button(console, e.panels.right_show, "◄")


# ----------------------------------------------------------------- the pause menu and options

MENU_HINTS = {
    "pause": "Up/Down choose, Enter picks, Esc resumes",
    "options_top": "Up/Down pick, Left/Right change, Esc closes",
    "options": "Up/Down choose, Left/Right change, Esc back",
}


def draw_shop(console: tcod.console.Console, e: Engine) -> None:
    """A shop, the use menu or a barrel, over the dimmed game."""
    shop = e.shop
    if shop is None:
        return
    shop.cols, shop.rows = console.width, console.height
    console.rgb["fg"] = (console.rgb["fg"] * 0.4).astype(np.uint8)
    console.rgb["bg"] = (console.rgb["bg"] * 0.4).astype(np.uint8)
    x, y, w, h = shop.box()
    console.draw_frame(x, y, w, h, fg=BORDER, bg=PANEL_BG)
    title = f" {shop.title[: w - 4]} "
    console.print(x + (w - len(title)) // 2, y, title, fg=TITLE, bg=PANEL_BG)
    for i, line in enumerate(textwrap.wrap(shop.greeting, w - 4)[:2]):
        console.print(x + 2, y + 1 + i, line, fg=DIM, bg=PANEL_BG)
    labels = shop.labels()
    rows = shop.visible_rows()
    for i in rows:
        ry = shop.row_y(i)
        picked = i == shop.cursor
        if picked:
            console.draw_rect(x + 1, ry, w - 2, 1, ord(" "), bg=HEADER_BG)
        colour = TAB_ON if picked else TEXT
        if shop.dim(i, e):
            colour = (120, 110, 90) if picked else DIM
        console.print(x + 3, ry, labels[i][: w - 6], fg=colour)
    if rows.start > 0:
        console.print(x + w - 3, shop.row_y(rows.start), "▲", fg=DIM)
    if rows.stop < len(labels):
        console.print(x + w - 3, shop.row_y(rows.stop - 1), "▼", fg=DIM)
    said = shop.said[-1] if shop.said else ""
    console.print(x + 2, y + h - 4, said[: w - 4], fg=TEXT, bg=PANEL_BG)
    console.print(x + 2, y + h - 3, shop.footer(e)[: w - 4], fg=(240, 210, 90), bg=PANEL_BG)
    hint = shop.hint
    console.print(x + (w - len(hint)) // 2, y + h - 2, hint, fg=DIM, bg=PANEL_BG)


def draw_menu(console: tcod.console.Console, menu) -> None:
    """The pause menu or the options screen, over a dimmed game (or title screen)."""
    from .options import box, row_y, value_span
    if not menu.open:
        return
    console.rgb["fg"] = (console.rgb["fg"] * 0.3).astype(np.uint8)
    console.rgb["bg"] = (console.rgb["bg"] * 0.3).astype(np.uint8)
    items = menu.items()
    x, y, w, h = box(len(items), console.width, console.height)
    console.draw_frame(x, y, w, h, fg=BORDER, bg=PANEL_BG)
    title = " Paused " if menu.screen == "pause" else " Options "
    console.print(x + (w - len(title)) // 2, y, title, fg=TITLE, bg=PANEL_BG)
    left, right = value_span(len(items), console.width, console.height)
    for i, item in enumerate(items):
        ry = row_y(len(items), i, console.width, console.height)
        picked = i == menu.cursor
        if picked:
            console.draw_rect(x + 1, ry, w - 2, 1, ord(" "), bg=HEADER_BG)
        colour = TAB_ON if picked else TEXT
        value = menu.value(item) if menu.screen == "options" else ""
        if value:
            console.print(x + 3, ry, item, fg=colour)
            console.print(left, ry, "◄", fg=colour)
            console.print(right, ry, "►", fg=colour)
            inner = right - left - 1
            console.print(left + 1, ry, value[:inner].center(inner), fg=TEXT)
        else:
            console.print(x + (w - len(item)) // 2, ry, item, fg=colour)
    hint = MENU_HINTS["options_top" if menu.screen == "options" and menu.top is None else menu.screen]
    console.print(x + (w - len(hint)) // 2, y + h - 2, hint, fg=DIM, bg=PANEL_BG)
    if menu.screen == "options":
        note = menu.note()
        console.print(x + (w - len(note)) // 2, y + h, note, fg=DIM)
