"""Glyphs: which characters a font really has, and what to draw when it hasn't got one.

The game is drawn with Classic Console Neue's glyphs in mind (game/display.py makes it the
default font), and it has thousands: daggers, a pendant, a skull, the sun, clouds and an
umbrella, notes of music, smooth partial blocks for bars. Other fonts have fewer. Whenever a
font lacks a glyph the game draws with, the closest shape it does have stands in for it
(SUBSTITUTES, best first), and only if it has none of those is a question mark drawn: nothing
is ever invisible, and nothing changes into something unrelated.

A TrueType font's own character map says what it has (font_chars); a Windows bitmap font (.fon)
has just the 256 of code page 437.
"""
from __future__ import annotations

import struct
from functools import lru_cache

import tcod

UNKNOWN = "?"
CP437 = frozenset(tcod.tileset.CHARMAP_CP437)

# A glyph -> what to draw instead in a font without it: the closest shapes, best first.
SUBSTITUTES = {
    # items
    "†": ("┼", "+"),            # a dagger: the hilt cross
    "♁": ("♀", "°"),            # a pendant on its chain
    "◎": ("◙", "○", "o"),       # a target, a mirror: a ring in a ring
    "◆": ("♦",),                # a cut jewel
    "♢": ("♦",),                # a rough one
    "∫": ("⌠", "§", "~"),       # a scroll, rolled
    "☠": ("☻", "☺", "&"),       # a skull
    "⌙": ("⌐", "¬", "_"),       # a lockpick
    "Җ": ("☼", "*"),            # a campfire: logs crossed under the flames
    "∴": (":", "."),            # ashes
    "▴": ("•", "."),            # a flint
    "╱": ("/",),                # a stick
    "∿": ("~",),                # a strip of cloth
    "ɩ": ("¡", "!"),            # a torch
    "¤": ("δ", "o"),            # a lantern
    "∪": ("u",),                # a saddle
    "⊤": ("τ", "T"),            # a pickaxe
    "Ψ": ("§", "Y"),            # a rope grapple
    "♫": ("♪", "≈"),            # music: a bone flute, a song
    "♪": ("♫", "¶"),
    "⊟": ("▄", "■"),            # a chest
    "◘": ("o", "°"),            # a barrel, end on
    "⊚": ("◘", "○", "o"),       # a well
    "☩": ("┼", "+"),            # an altar's cross
    "⌛": ("Σ", "X"),            # an hourglass
    "▪": ("■", "•"),            # a bar of soap
    "¦": ("│", "|"),            # nails, rivets
    # the weather and the sky (the HUD)
    "☀": ("☼", "*"),
    "☁": ("≈", "~"),
    "☂": ("↓", ","),
    "☇": ("↓", "!"),
    "☽": ("(", "c"),
    "★": ("*",),
    "≋": ("≈", "~"),
    # bars and frames
    "▏": ("▌", "│", "|"), "▎": ("▌", "│"), "▍": ("▌",), "▋": ("▌",), "▊": ("█", "▌"), "▉": ("█",),
    "╭": ("┌",), "╮": ("┐",), "╰": ("└",), "╯": ("┘",),
    "‣": ("►", ">"),
}
# Glyphs drawn here and there beyond the items and tiles (the HUD, menus, the map).
EXTRA = set("☀☁☂☇☽★≋♥▏▎▍▌▋▊▉█▀▄▐░▒▓╭╮╰╯─│┌┐└┘├┤┬┴┼═║╔╗╚╝►◄▲▼←→↑↓·•…‣")


def game_glyphs() -> set[str]:
    """Every glyph an item, a tile or a creature is drawn with, and the rest the game uses."""
    from . import items
    from . import tiles as T
    from . import wild
    return ({k.char for k in items.KINDS.values()} | {t.char for t in T.TILES} |
            {b.char for b in wild.BEASTS.values()} | EXTRA | set(SUBSTITUTES))


def wanted_codes() -> set[int]:
    """The characters worth making tiles for: code page 437, Latin-1 for names, and every glyph
    the game draws with."""
    return set(CP437) | set(range(0x20, 0x7F)) | set(range(0xA0, 0x100)) | \
        {ord(c) for c in game_glyphs() if len(c) == 1}


def stand_in(ch: str, have) -> str:
    """What to draw for `ch` in a font that has the characters `have`: itself, the closest
    shape it has, or a question mark."""
    if ord(ch) in have:
        return ch
    for sub in SUBSTITUTES.get(ch, ()):
        if len(sub) == 1 and ord(sub) in have:
            return sub
    return UNKNOWN


# ----------------------------------------------------------------- what a font has

@lru_cache(maxsize=None)
def font_chars(path: str, bitmap: bool) -> frozenset:
    """The characters a font has: a .fon's code page 437, or a TrueType font's character map."""
    if bitmap:
        return CP437
    try:
        with open(path, "rb") as f:
            return frozenset(ttf_cmap(f.read()))
    except (OSError, ValueError, struct.error):
        return CP437


def ttf_cmap(data: bytes) -> set[int]:
    """The code points in a TrueType font's character map (its format 4 or 12 table)."""
    tables = {}
    for i in range(struct.unpack_from(">H", data, 4)[0]):
        tag, _, off, length = struct.unpack_from(">4sIII", data, 12 + 16 * i)
        tables[tag] = off
    if b"cmap" not in tables:
        raise ValueError("no character map")
    off = tables[b"cmap"]
    best = None
    for i in range(struct.unpack_from(">H", data, off + 2)[0]):
        _, _, sub = struct.unpack_from(">HHI", data, off + 4 + 8 * i)
        fmt = struct.unpack_from(">H", data, off + sub)[0]
        if fmt == 12 or (fmt == 4 and best is None):
            best = (fmt, off + sub)
    if best is None:
        raise ValueError("no usable character map")
    fmt, base = best
    codes: set[int] = set()
    if fmt == 12:
        for i in range(struct.unpack_from(">I", data, base + 12)[0]):
            start, end, _ = struct.unpack_from(">III", data, base + 16 + 12 * i)
            codes.update(range(start, end + 1))
        return codes
    segx2 = struct.unpack_from(">H", data, base + 6)[0]
    seg = segx2 // 2
    ends = struct.unpack_from(f">{seg}H", data, base + 14)
    starts = struct.unpack_from(f">{seg}H", data, base + 16 + segx2)
    deltas = struct.unpack_from(f">{seg}h", data, base + 16 + 2 * segx2)
    ranges_at = base + 16 + 3 * segx2
    offsets = struct.unpack_from(f">{seg}H", data, ranges_at)
    for i in range(seg):
        for c in range(starts[i], ends[i] + 1):
            if c == 0xFFFF:
                continue
            if offsets[i] == 0:
                glyph = (c + deltas[i]) & 0xFFFF
            else:
                glyph = struct.unpack_from(">H", data, ranges_at + 2 * i + offsets[i] + 2 * (c - starts[i]))[0]
                glyph = (glyph + deltas[i]) & 0xFFFF if glyph else 0
            if glyph:
                codes.add(c)
    return codes
