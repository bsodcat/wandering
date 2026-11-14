"""The Updates screen on the title screen: what's new in each version, and a check for a newer
release.

The check only happens when you pick "Check for updates". It asks GitHub for the latest
release of the game (a single public request, nothing about you is sent) in the background, so
the screen never freezes, and says whether you're up to date. "Download page" opens the
releases page in your web browser.
"""
from __future__ import annotations

import json
import threading
import urllib.request
import webbrowser

from . import __version__

REPO = "bsodcat/wandering"
LATEST_API = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases"
TIMEOUT = 8          # seconds

# What's new, newest first: (version, headline, [what changed])
NOTES = [
    ("1.4.0-beta.1", "Beta test: cities, forts and carts", [
        "Stone cities spanning four regions, with walls, gates, guards and archers.",
        "Forts on the high ground over the highways: guards, archers and a blacksmith.",
        "Carts between the towns: ride one for a few coins (the route shows on the world map).",
        "Pastureland with grazing herds, and rolling downs. Most towns sit on a river; some have cleared the woods.",
        "Equipment: seven places to wear things, each piece with stats (q); climbing gear to climb rock.",
        "Cold water chills you, and keeps chilling you for a while after you're out.",
        "Erosion, eras and the time skip (T); world settings in Create a World; volcanoes, lava and springs.",
        "Local maps shown whole when you arrive (m toggles); the overworld no longer hides land behind hills.",
        "A dev console (`) for god mode, items, creatures, the clock and the weather.",
        "A controls list in Options, and this Updates screen.",
        "Shops show 15 rows at a time and scroll; selling is on its own tab.",
        "The start year in Create a World steps by 50 (Shift: 1,000).",
    ]),
    ("1.3.0", "Wild things", [
        "Wolves, rabbits, squirrels, birds, rats, bats and goblins, each with their own ways.",
        "Fighting: weapons, armour and shields; wolf fever, and hot soup to cure it.",
        "The shopkeeper, trinkets to dig up and sell, the use menu, barrels.",
    ]),
    ("1.2.0", "Hills, inns and tools", [
        "Elevation on local maps: slopes, scrambles, and high ground that hides what's behind it.",
        "Inns with rooms upstairs and a cellar; the barkeeper lets a bed for the night.",
        "An inventory, shops, an axe to fell trees and a shovel to dig; town dogs and cats.",
    ]),
    ("1.1.0", "Wandering", [
        "The game is named Wandering, with a title screen.",
        "The dev arena: one of everything, for trying things out.",
    ]),
    ("1.0.0", "The first release", [
        "A whole world from one number: terrain, climate, rivers, biomes, towns and roads.",
        "Local maps for every region, townsfolk at their trades, herds and crops.",
    ]),
]


def version_tuple(text: str) -> tuple:
    """(major, minor, patch, final, pre): a pre-release ("1.4.0-beta.1") comes before its
    release ("1.4.0"), and betas count up."""
    main, _, pre = text.strip().lstrip("vV").partition("-")
    out = []
    for part in main.split("."):
        digits = "".join(ch for ch in part if ch.isdigit())
        out.append(int(digits) if digits else 0)
    out = (out + [0, 0, 0])[:3]
    pre_n = int("".join(ch for ch in pre if ch.isdigit()) or 0)
    return tuple(out) + ((0, pre_n) if pre else (1, 0))


def newer(latest: str, current: str = __version__) -> bool:
    return version_tuple(latest) > version_tuple(current)


class Checker:
    """Asks GitHub for the latest release, off the main thread. `status` is what to show."""

    def __init__(self):
        self.status = f"You have version {__version__}. Pick Check for updates to look for a newer one."
        self.latest: str | None = None
        self.busy = False

    def check(self, fetch=None) -> None:
        if self.busy:
            return
        self.busy = True
        self.status = "Checking for updates..."
        threading.Thread(target=self._run, args=(fetch or fetch_latest,), daemon=True).start()

    def _run(self, fetch) -> None:
        try:
            tag = fetch()
            self.latest = tag
            if newer(tag):
                self.status = f"Version {tag.lstrip('vV')} is out (you have {__version__}). Pick Download page to get it."
            else:
                self.status = f"You're up to date: version {__version__} is the latest."
        except Exception as error:          # offline, rate limited, GitHub down...
            self.status = f"Couldn't check for updates ({type(error).__name__}). Try again later."
        finally:
            self.busy = False


def fetch_latest() -> str:
    """The tag of the latest release on GitHub ("v1.3.0")."""
    request = urllib.request.Request(LATEST_API, headers={"Accept": "application/vnd.github+json",
                                                          "User-Agent": "Wandering-game"})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as reply:
        return str(json.load(reply)["tag_name"])


def open_page() -> str:
    try:
        webbrowser.open(RELEASES_PAGE)
        return "Opened the download page in your browser."
    except Exception:
        return f"Couldn't open a browser: the page is {RELEASES_PAGE}"


def lines(width: int) -> list[tuple[str, str]]:
    """The notes as (text, kind) lines wrapped to `width`: kind is "head", "item" or "gap"."""
    import textwrap
    out = []
    for version, headline, changes in NOTES:
        label = f"{version}  {headline}" if version == "Next" else f"Version {version}  {headline}"
        out.append((label, "head"))
        for change in changes:
            wrapped = textwrap.wrap(change, width - 2) or [""]
            out.append(("• " + wrapped[0], "item"))
            out += [("  " + rest, "item") for rest in wrapped[1:]]
        out.append(("", "gap"))
    return out
