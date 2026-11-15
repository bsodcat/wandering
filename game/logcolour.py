"""Colour in the log, so a line can be read at a glance: numbers (coins, hours, degrees, damage)
in gold, things (items) in green, creatures and animals in red, people's names in blue, trades
and titles in violet, and what's said "in quotes" in a pale blue. The rest stays the log's own
colour; an older, dimmer line keeps its highlights dimmed to match.
"""
from __future__ import annotations

import re
from functools import lru_cache

NUMBER = (240, 205, 95)
THING = (150, 215, 125)
CREATURE = (235, 120, 100)
NAME = (125, 190, 245)
TRADE = (200, 165, 240)
SPEECH = (175, 205, 225)
NUMBER_RE = re.compile(r"(?<![\w])[+-]?\d[\d,]*(?:\.\d+)?(?:\s?(?:°C|%|h\b|min\b|coins?\b))?")
SPEECH_RE = re.compile(r'"[^"]*"?')


@lru_cache(maxsize=1)
def vocabulary() -> tuple:
    """(regex of every noun worth colouring, {lowercased noun: colour})."""
    from . import horses, items, people
    from .farming import ANIMALS
    words: dict[str, tuple] = {}
    for k in items.KINDS.values():
        for w in (k.name, k.plural):
            words[w.lower()] = THING
    try:
        from .wild import BEASTS
        for name in BEASTS:
            words[name.lower()] = CREATURE
            words[f"{name.lower()}s"] = CREATURE
    except ImportError:
        pass
    for name, a in ANIMALS.items():
        words[name.lower()] = CREATURE
        words[a.plural.lower()] = CREATURE
    for job in people.JOBS:
        words[job.lower()] = TRADE
    for n in people.FIRST + people.FAMILY + horses.NAMES:
        words[n.lower()] = NAME
    from .citylife import KINGLY, QUEENLY
    for n in KINGLY + QUEENLY:
        words[n.lower()] = NAME
    for pets in people.PET_NAMES.values():
        for n in pets:
            words[n.lower()] = NAME
    ordered = sorted(words, key=len, reverse=True)
    pattern = re.compile(r"\b(" + "|".join(re.escape(w) for w in ordered) + r")\b", re.IGNORECASE)
    return pattern, words


@lru_cache(maxsize=1024)
def spans(text: str) -> tuple:
    """(start, end, colour) of the parts of `text` to colour, in order, not overlapping."""
    marked = [False] * len(text)
    out = []

    def take(a, b, colour):
        if not any(marked[a:b]):
            for i in range(a, b):
                marked[i] = True
            out.append((a, b, colour))
    for m in SPEECH_RE.finditer(text):                # what's said first, so its words aren't picked out
        if m.end() - m.start() > 1:
            take(m.start(), m.end(), SPEECH)
    for m in NUMBER_RE.finditer(text):
        take(m.start(), m.end(), NUMBER)
    pattern, words = vocabulary()
    for m in pattern.finditer(text):
        word = m.group(0)
        colour = words.get(word.lower())
        if colour is NAME and not word[:1].isupper():  # "hal", "kit" ... only as names
            continue
        if colour is not None:
            take(m.start(), m.end(), colour)
    return tuple(sorted(out))


def print_coloured(console, x: int, y: int, text: str, base, width: int | None = None) -> None:
    """Prints `text` in `base`, with its highlights over it, dimmed as `base` is dimmed."""
    if width is not None:
        text = text[:width]
    console.print(x, y, text, fg=base)
    if not text.strip():
        return
    shade = max(base) / 235 if max(base) else 1.0
    for a, b, colour in spans(text):
        console.print(x + a, y, text[a:b], fg=tuple(min(255, int(c * min(1.0, shade))) for c in colour))
