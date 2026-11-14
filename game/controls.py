"""Every control in the game, for the Controls list in Options (game/options.py)."""
from __future__ import annotations

CONTROLS = [
    ("Getting about", [
        ("Arrows, numpad, WASD", "walk (numpad 7 9 1 3: diagonally)"),
        (". or numpad 5", "wait an hour"),
        ("z", "rest 8 hours, or sleep in a bed"),
        ("> or Enter", "step down into a region; take stairs down"),
        ("<", "take stairs up; back up to the world map"),
        ("Right mouse (hold)", "walk toward the pointer"),
        ("Walk into someone", "talk; trade with them at work; pet a dog or cat"),
        ("Walk into a creature", "fight it"),
        ("Walk into a tree", "fell it, with an axe"),
        ("Walk into rock", "climb it, with climbing gear on"),
    ]),
    ("Things to do", [
        ("e", "the use menu: what you can do here and next to you"),
        ("Left mouse", "the use menu for what's under the pointer"),
        ("q", "equipment: what you wear and wield"),
        ("i", "your inventory"),
        ("g", "pick up what's at your feet"),
        ("x", "dig, with a shovel"),
    ]),
    ("Looking", [
        ("Pointer", "describe what's under it (in the Info panel)"),
        ("o", "world map: overlays; local map: the relief"),
        ("m", "world map: reveal it; local map: the whole map or only what you've seen"),
        ("v", "look at the treetops or the ground beneath them"),
        ("Tab", "the right panel's tabs: Info, Map, Log, Inv, hidden"),
        ("c", "show or hide the stats panel"),
        ("PageUp/PageDown, wheel", "scroll the log"),
    ]),
    ("Menus and boxes", [
        ("Up/Down or W/S", "choose"),
        ("Left/Right or A/D", "change a setting; switch tabs"),
        ("Enter or Space", "pick"),
        ("Esc", "close, or go back"),
        ("Wheel, PageUp/PageDown", "scroll a long list"),
    ]),
    ("The game", [
        ("Esc", "pause menu: Resume, Options, Main menu, Quit"),
        ("t", "the time skip: let the ages pass"),
        ("F11 or Alt+Enter", "fullscreen or windowed"),
        ("` (backquote)", "the dev console (type help)"),
    ]),
]


def lines(width: int, key_w: int = 24) -> list[tuple[str, str, str]]:
    """The controls as (key, what it does, kind) lines: kind is "head", "row" or "gap". What a
    control does is wrapped onto more lines if it's too long for `width`."""
    import textwrap
    out = []
    for section, rows in CONTROLS:
        out.append((section, "", "head"))
        for key, what in rows:
            wrapped = textwrap.wrap(what, max(10, width - key_w)) or [""]
            out.append((key, wrapped[0], "row"))
            out += [("", more, "row") for more in wrapped[1:]]
        out.append(("", "", "gap"))
    return out[:-1]
