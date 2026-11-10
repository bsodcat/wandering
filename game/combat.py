"""Fighting: what you hit with, what you wear, and how a blow lands.

Walk into a creature to strike it. A blow lands with a chance (your weapon's, less how nimble
the creature is) and does a roll of the weapon's damage. Creatures strike back the same way,
less what your armour stops:

    weapon        damage   to hit      armour          stops    where
    fists         1-3      +0          padded jerkin   1        body
    rusty dagger  1-3      +0          leather coat  2        body
    crude knife   1-4      +0          mail shirt      3        body
    dagger        2-4      +10%        iron helm       1        head
    club          2-5      -5%         wooden shield   1, and turns aside one blow in six
    shovel        1-4      -10%
    axe           2-6      -10%
    spear         3-7      +0
    short sword   3-8      +5%

One weapon in hand, one piece of armour in each place. Wield and wear from the use menu (e).
How dangerous you look matters too: wolves and goblins weigh up a wanderer with a real weapon
and armour as more than one of them (`threat`).
"""
from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass(frozen=True)
class Weapon:
    low: int
    high: int
    to_hit: float
    verb: str


FISTS = Weapon(1, 3, 0.0, "punch")
WEAPONS = {
    "rusty dagger": Weapon(1, 3, 0.0, "stab"),
    "crude knife": Weapon(1, 4, 0.0, "slash"),
    "dagger": Weapon(2, 4, 0.1, "stab"),
    "club": Weapon(2, 5, -0.05, "club"),
    "shovel": Weapon(1, 4, -0.1, "whack"),
    "axe": Weapon(2, 6, -0.1, "hack at"),
    "spear": Weapon(3, 7, 0.0, "spear"),
    "short sword": Weapon(3, 8, 0.05, "slash"),
}
ARMOUR = {   # kind -> (where it's worn, how much of each blow it stops)
    "padded jerkin": ("body", 1), "leather coat": ("body", 2), "mail shirt": ("body", 3),
    "iron helm": ("head", 1), "wooden shield": ("arm", 1),
}
SHIELD_BLOCK = 1 / 6
BASE_HIT = 0.75             # your chance to land a blow, before the weapon and the target's dodge
REAL_WEAPONS = {"dagger", "spear", "short sword", "axe", "club"}
# The shopkeeper's wares: kind -> price in coins
WARES = {"club": 3, "dagger": 6, "spear": 9, "short sword": 16, "padded jerkin": 6, "leather coat": 12,
         "mail shirt": 30, "iron helm": 10, "wooden shield": 6}


def weapon_of(p) -> tuple[str | None, Weapon]:
    """(what you're holding, its numbers): your fists if nothing (or you've let it go)."""
    if p.wielding and p.inventory.count(p.wielding):
        return p.wielding, WEAPONS[p.wielding]
    p.wielding = None
    return None, FISTS


def worn(p) -> dict:
    """Where -> what you're wearing, dropping anything you no longer carry."""
    for slot, kind in list(p.wearing.items()):
        if not p.inventory.count(kind):
            del p.wearing[slot]
    return p.wearing


def protection(p) -> int:
    return sum(ARMOUR[k][1] for k in worn(p).values())


def threat(p) -> float:
    """How many wolves or goblins you count as: one, and a half more each for a real weapon and
    body armour."""
    held, _ = weapon_of(p)
    return 1.0 + 0.5 * (held in REAL_WEAPONS) + 0.5 * ("body" in worn(p))


def wield(p, kind: str | None) -> str:
    if kind is None:
        held = p.wielding
        p.wielding = None
        return f"You put away the {held}." if held else "Your hands are already empty."
    p.wielding = kind
    return f"You wield the {kind}."


def wear(p, kind: str) -> str:
    slot = ARMOUR[kind][0]
    old = worn(p).get(slot)
    p.wearing[slot] = kind
    return f"You take off the {old} and put on the {kind}." if old else f"You put on the {kind}."


def take_off(p, kind: str) -> str:
    for slot, k in list(p.wearing.items()):
        if k == kind:
            del p.wearing[slot]
    return f"You take off the {kind}."


def player_blow(p, dodge: float, rng: random.Random) -> tuple[int, str]:
    """Your blow at something that dodges this much: (damage, 0 for a miss; the verb)."""
    _, w = weapon_of(p)
    if rng.random() >= BASE_HIT + w.to_hit - dodge:
        return 0, w.verb
    return rng.randint(w.low, w.high), w.verb


def blow_at_you(p, low: int, high: int, to_hit: float, rng: random.Random) -> tuple[int, str]:
    """A creature's blow at you: (damage after armour, what happened: "miss", "block", "glance",
    "hit")."""
    if rng.random() >= to_hit:
        return 0, "miss"
    if "arm" in worn(p) and rng.random() < SHIELD_BLOCK:
        return 0, "block"
    dmg = rng.randint(low, high) - protection(p)
    return (dmg, "hit") if dmg > 0 else (0, "glance")
