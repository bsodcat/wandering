"""The developer's console: ` (the backquote key) opens a command line over the game for
trying things out mid-game.

Type a command and press Enter. Up/Down go back through what you've typed, Tab finishes a
command or item name, PageUp/PageDown or the mouse wheel scroll the output, and Esc or ` closes it. `help` lists
everything:

    help [command]            what the commands are
    god [on|off]              you can't be hurt, tire, freeze or die
    noclip [on|off]           walk through anything, up any height
    heal                      health, stamina and warmth back to full, dry, and cured
    set <stat> <value>        health, stamina, body, wet, clothing or coins
    give <item> [n]           put things in your bag ("give short sword", "give coin 50")
    drop <item> [n]           put things on the ground at your feet
    items [word]              list the item names (those with the word in them)
    spawn <creature> [n]      wolves, goblins, rabbits... or townsfolk animals, beside you
    creatures                 list what you can spawn
    kill [near|all]           kill the wild things near you (within 12 steps), or all of them here
    time                      the date and time, and whether the clock's paused
    time forward <n>[m|h|d]   let time run on (people and creatures carry on, you're exposed)
    time jump <n>[m|h|d]      move the clock on at once, with nothing happening in between
    time set <hh:mm>          jump to the next time the clock reads hh:mm
    time pause | time resume  stop the clock (you can still walk about) or start it again
    weather <kind|auto>       clear, cloudy, overcast, fog, rain, storm, snow, blizzard; auto lets it be
    tp <x> <y>                go to a tile (on a local map) or a region (on the overworld)
    reveal [on|off]           show the whole map (the overworld and the local maps)
    where                     where you are
    seed                      the world's seed
    clear                     clear the console
"""
from __future__ import annotations

import shlex
from collections import deque
from dataclasses import dataclass, field

from tcod.event import KeySym

from . import items
from . import tiles as T
from . import wild

CONSOLE_KEY = KeySym.GRAVE
HISTORY = 50
OUTPUT = 300
SHOWN = 14               # lines of output on screen
WEATHERS = ("clear", "cloudy", "overcast", "fog", "rain", "storm", "snow", "blizzard")
UNITS = {"m": 1 / 60, "h": 1.0, "d": 24.0}


class CommandError(Exception):
    pass


def on_off(args: list[str], now: bool) -> bool:
    if not args:
        return not now
    word = args[0].lower()
    if word in ("on", "1", "true", "yes"):
        return True
    if word in ("off", "0", "false", "no"):
        return False
    raise CommandError("Say on or off.")


def hours_of(text: str) -> float:
    """"90m", "3h", "2d", or a plain number of hours."""
    text = text.lower().strip()
    unit = UNITS.get(text[-1:], None)
    number = text[:-1] if unit is not None else text
    try:
        return float(number) * (unit if unit is not None else 1.0)
    except ValueError:
        raise CommandError(f"'{text}' isn't a length of time (try 30m, 6h or 2d).") from None


def thing_and_count(args: list[str], names, what: str) -> tuple[str, int]:
    """("short sword", 1) from ["short", "sword"]; ("coin", 50) from ["coin", "50"]."""
    if not args:
        raise CommandError(f"Which {what}?")
    n = 1
    if len(args) > 1 and args[-1].isdigit():
        n, args = int(args[-1]), args[:-1]
    name = " ".join(args).lower()
    names = list(names)
    if name in names:
        return name, n
    plural = {getattr(items.KINDS.get(k), "plural", k + "s"): k for k in names}
    if name in plural:
        return plural[name], n
    close = [k for k in names if name in k]
    if len(close) == 1:
        return close[0], n
    if close:
        raise CommandError(f"Which {what}? " + ", ".join(close[:12]) + ("..." if len(close) > 12 else ""))
    raise CommandError(f"There's no {what} called '{name}'.")


def spawnable() -> list[str]:
    from .farming import ANIMALS
    return list(wild.BEASTS) + [k for k in ANIMALS]


@dataclass
class DevConsole:
    engine: object
    open: bool = False
    line: str = ""
    history: list = field(default_factory=list)
    back: int = 0                     # how far back through the history Up has gone
    output: deque = field(default_factory=lambda: deque(maxlen=OUTPUT))
    scroll: int = 0

    # ------------------------------------------------------------- typing

    def toggle(self) -> None:
        self.open = not self.open
        self.line, self.back, self.scroll = "", 0, 0
        if self.open and not self.output:
            self.print("Dev console. Type help for the commands; Esc or ` closes.")

    def text(self, typed: str) -> None:
        """Text typed while the console's open (the key that opened it doesn't count)."""
        self.line += "".join(ch for ch in typed if ch not in "`~" and ch.isprintable())

    def handle_key(self, sym, mod: int = 0) -> None:
        if sym in (KeySym.ESCAPE, CONSOLE_KEY):
            self.toggle()
        elif sym in (KeySym.RETURN, KeySym.KP_ENTER):
            line, self.line, self.back, self.scroll = self.line.strip(), "", 0, 0
            if line:
                self.history = (self.history + [line])[-HISTORY:]
                self.run(line)
        elif sym == KeySym.BACKSPACE:
            self.line = self.line[:-1]
        elif sym == KeySym.UP and self.history:
            self.back = min(len(self.history), self.back + 1)
            self.line = self.history[-self.back]
        elif sym == KeySym.DOWN:
            self.back = max(0, self.back - 1)
            self.line = self.history[-self.back] if self.back else ""
        elif sym == KeySym.PAGEUP:
            self.scroll = min(max(0, len(self.output) - SHOWN), self.scroll + SHOWN // 2)
        elif sym == KeySym.PAGEDOWN:
            self.scroll = max(0, self.scroll - SHOWN // 2)
        elif sym == KeySym.TAB:
            self.complete()

    def scroll_by(self, lines: int) -> None:
        """The mouse wheel: positive goes back through the output."""
        self.scroll = max(0, min(max(0, len(self.output) - SHOWN), self.scroll + lines))

    def complete(self) -> None:
        """Tab: finish the command, or the item or creature name after give, drop or spawn."""
        words = self.line.split(" ")
        if len(words) == 1:
            options = [c for c in COMMANDS if c.startswith(words[0].lower())]
            prefix = ""
        elif words[0] in ("give", "drop", "spawn"):
            names = spawnable() if words[0] == "spawn" else list(items.KINDS)
            typed = " ".join(words[1:]).lower()
            options = [k for k in names if k.startswith(typed)]
            prefix = words[0] + " "
        else:
            return
        if len(options) == 1:
            self.line = prefix + options[0] + " "
        elif options:
            self.print("  " + ", ".join(options[:20]) + (" ..." if len(options) > 20 else ""))

    def print(self, text: str) -> None:
        for part in text.split("\n"):
            self.output.append(part)

    # ------------------------------------------------------------- commands

    def run(self, line: str) -> None:
        self.print("> " + line)
        try:
            words = shlex.split(line)
        except ValueError:
            words = line.split()
        name, args = words[0].lower(), words[1:]
        command = COMMANDS.get(name)
        if command is None:
            self.print(f"No such command: {name}. Type help.")
            return
        try:
            result = command(self, args)
        except CommandError as error:
            result = str(error)
        if result:
            self.print(result)

    @property
    def player(self):
        return self.engine.player

    def cmd_help(self, args):
        """help [command]: what the commands are"""
        if args:
            fn = COMMANDS.get(args[0].lower())
            if fn is None:
                raise CommandError(f"No such command: {args[0]}.")
            return fn.__doc__
        return "\n".join(f"  {fn.__doc__.split(": ", 1)[0]:<34}{fn.__doc__.split(": ", 1)[1].strip()}"
                         for fn in dict.fromkeys(COMMANDS.values()))

    def cmd_god(self, args):
        """god [on|off]: you can't be hurt, tire, freeze or die"""
        p = self.player
        p.god = on_off(args, p.god)
        if p.god:
            p.alive, p.cause = True, ""
            self.engine.restore()
        return f"God mode {'on' if p.god else 'off'}."

    def cmd_noclip(self, args):
        """noclip [on|off]: walk through anything, up any height"""
        p = self.player
        p.noclip = on_off(args, p.noclip)
        return f"Noclip {'on' if p.noclip else 'off'}."

    def cmd_heal(self, args):
        """heal: health, stamina and warmth back to full, dry, and cured"""
        p = self.player
        p.alive, p.cause = True, ""
        self.engine.restore(dry=True)
        p.sickness = None
        p.in_cold_water, p.afterdrop, p.cold_turns = 0.0, 0, 0
        return "You're as good as new."

    def cmd_set(self, args):
        """set <stat> <value>: health, stamina, body, wet, clothing or coins"""
        if len(args) != 2:
            raise CommandError("set <health|stamina|body|wet|clothing|coins> <value>")
        stat, value = args[0].lower(), args[1]
        try:
            v = float(value)
        except ValueError:
            raise CommandError(f"'{value}' isn't a number.") from None
        p = self.player
        if stat == "coins":
            p.inventory.take("coin", p.inventory.count("coin"))
            if int(v) > 0:
                p.inventory.add("coin", int(v))
            return f"You have {int(v)} coins."
        limits = {"health": (0, 100), "stamina": (0, 100), "body": (25, 44), "wet": (0, 100), "clothing": (-30, 60)}
        if stat not in limits:
            raise CommandError("You can set health, stamina, body, wet, clothing or coins.")
        lo, hi = limits[stat]
        setattr(p, stat, max(lo, min(hi, v)))
        if stat == "health" and p.health > 0:
            p.alive, p.cause = True, ""
        return f"{stat.capitalize()} {getattr(p, stat):g}."

    def cmd_give(self, args):
        """give <item> [n]: put things in your bag"""
        kind, n = thing_and_count(args, items.KINDS, "item")
        self.player.inventory.add(kind, n)
        return f"You now have {items.amount(kind, self.player.inventory.count(kind))}."

    def cmd_drop(self, args):
        """drop <item> [n]: put things on the ground at your feet"""
        e = self.engine
        if e.level is None:
            raise CommandError("Only on a local map.")
        kind, n = thing_and_count(args, items.KINDS, "item")
        items.drop(e.level, e.lx, e.ly, kind, n)
        return f"{items.amount(kind, n).capitalize()} at your feet."

    def cmd_items(self, args):
        """items [word]: list the item names"""
        word = " ".join(args).lower()
        names = [k for k in items.KINDS if word in k]
        return ", ".join(names) if names else "None match."

    def cmd_spawn(self, args):
        """spawn <creature> [n]: a wild thing or an animal beside you"""
        e = self.engine
        if e.level is None:
            raise CommandError("Only on a local map.")
        kind, n = thing_and_count(args, spawnable(), "creature")
        made = e.spawn(kind, n)
        if not made:
            raise CommandError("There's no room nearby.")
        return f"Spawned {made} {kind if made == 1 else wild.BEASTS[kind].plural if kind in wild.BEASTS else kind}."

    def cmd_creatures(self, args):
        """creatures: list what you can spawn"""
        return ", ".join(spawnable())

    def cmd_kill(self, args):
        """kill [near|all]: kill the wild things near you, or all of them here"""
        e = self.engine
        if e.level is None:
            raise CommandError("Only on a local map.")
        everywhere = bool(args) and args[0].lower() == "all"
        doomed = [c for c in e.level.creatures
                  if everywhere or max(abs(c.x - e.lx), abs(c.y - e.ly)) <= 12]
        for c in doomed:
            e.level.creatures.remove(c)
        return f"Killed {len(doomed)}."

    def cmd_time(self, args):
        """time [forward|jump <n>[m|h|d] | set <hh:mm> | pause | resume]: the clock"""
        from .climate import clock_text, date_text
        e = self.engine
        if not args:
            return f"{date_text(e.minutes)}, {clock_text(e.minutes)}" + ("  (paused)" if e.paused else "")
        what = args[0].lower()
        if what in ("pause", "stop", "freeze"):
            e.paused = True
            return "The clock stops. (time resume starts it again)"
        if what in ("resume", "unpause", "start", "go"):
            e.paused = False
            return "The clock runs again."
        if what in ("forward", "fwd", "pass") and len(args) == 2:
            hours = hours_of(args[1])
            if hours <= 0 or hours > 24 * 30:
                raise CommandError("Forward by up to 30 days.")
            e.dev_pass(hours)
        elif what in ("jump", "skip") and len(args) == 2:
            hours = hours_of(args[1])
            if hours <= 0:
                raise CommandError("The clock only goes forward.")
            e.jump_clock(hours * 60)
        elif what == "set" and len(args) == 2:
            try:
                hh, mm = (args[1].split(":") + ["0"])[:2]
                target = int(hh) * 60 + int(mm)
            except ValueError:
                raise CommandError("time set <hh:mm>") from None
            if not 0 <= target < 24 * 60:
                raise CommandError("Between 00:00 and 23:59.")
            now = e.minutes % (24 * 60)
            e.jump_clock((target - now) % (24 * 60))
        else:
            raise CommandError("time [forward|jump <n>[m|h|d] | set <hh:mm> | pause | resume]")
        return self.cmd_time([])

    def cmd_weather(self, args):
        """weather <kind|auto>: clear, cloudy, overcast, fog, rain, storm, snow, blizzard"""
        e = self.engine
        if not args:
            return f"{e.now.kind}, {e.now.air:.1f}°C" + (f"  (forced {e.forced_weather})" if e.forced_weather else "")
        kind = args[0].lower()
        if kind == "auto":
            e.forced_weather = None
        elif kind in WEATHERS:
            e.forced_weather = kind
        else:
            raise CommandError("weather " + "|".join(WEATHERS) + "|auto")
        e.now = e.weather()
        e.update_view()
        return self.cmd_weather([])

    def cmd_tp(self, args):
        """tp <x> <y>: go to a tile on this local map, or a region on the overworld"""
        try:
            x, y = int(args[0]), int(args[1])
        except (ValueError, IndexError):
            raise CommandError("tp <x> <y>") from None
        e = self.engine
        if e.level is None:
            if not e.world.in_bounds(x, y):
                raise CommandError(f"The world is {e.world.width} x {e.world.height}.")
            e.player.x, e.player.y = x, y
        else:
            if not e.level.in_bounds(x, y):
                raise CommandError(f"This map is {e.level.width} x {e.level.height}.")
            e.lx, e.ly = x, y
        e.now = e.weather()
        e.update_view()
        return self.cmd_where([])

    def cmd_reveal(self, args):
        """reveal [on|off]: show the whole map, overworld and local"""
        e = self.engine
        e.reveal = e.reveal_local = on_off(args, e.reveal)
        return f"Reveal {'on' if e.reveal else 'off'}."

    def cmd_where(self, args):
        """where: where you are"""
        e = self.engine
        p = e.player
        if e.level is None:
            return f"Region {p.x},{p.y} on the overworld."
        tile = T.TILES[e.level.tiles[e.lx, e.ly]].name
        return f"{e.level.name}: tile {e.lx},{e.ly} ({tile}), region {p.x},{p.y}."

    def cmd_seed(self, args):
        """seed: the world's seed"""
        return f"Seed {self.engine.world.seed}."

    def cmd_clear(self, args):
        """clear: clear the console"""
        self.output.clear()
        return ""


COMMANDS = {
    "help": DevConsole.cmd_help, "god": DevConsole.cmd_god, "noclip": DevConsole.cmd_noclip,
    "heal": DevConsole.cmd_heal, "set": DevConsole.cmd_set, "give": DevConsole.cmd_give,
    "drop": DevConsole.cmd_drop, "items": DevConsole.cmd_items, "spawn": DevConsole.cmd_spawn,
    "creatures": DevConsole.cmd_creatures, "kill": DevConsole.cmd_kill, "time": DevConsole.cmd_time,
    "weather": DevConsole.cmd_weather, "tp": DevConsole.cmd_tp, "reveal": DevConsole.cmd_reveal,
    "where": DevConsole.cmd_where, "seed": DevConsole.cmd_seed, "clear": DevConsole.cmd_clear,
}
