"""Fighting: what you hit with, what you wear, and how a blow lands.

Walk into a creature to strike it. A blow lands with a chance (your weapon's, less how nimble
the creature is) and does a roll of the weapon's damage. Creatures strike back the same way,
less what your armour stops:

    weapon        damage   to hit
    fists         1-3      +0
    rusty dagger  1-3      +0
    crude knife   1-4      +0
    dagger        2-4      +10%
    club          2-5      -5%
    quarterstaff  2-5      +5%
    shovel        1-4      -10%
    axe           2-6      -10%
    mace          3-7      -5%
    spear         3-7      +0
    short sword   3-8      +5%

Armour, shields and everything else you wear are in game/gear.py: each piece stops so much of
a blow (`armour`), and a shield now and then turns one aside (`block`). One weapon in hand, one
piece in each place. Wield and wear from the equipment menu (q) or the use menu (e).
How dangerous you look matters too: wolves and goblins weigh up a wanderer with a real weapon
and armour as more than one of them (`threat`).
"""
from __future__ import annotations

import random
from dataclasses import dataclass

from . import gear
from .gear import take_off, wear, worn  # noqa: F401  (wearing things is gear's business)


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
    "quarterstaff": Weapon(2, 5, 0.05, "strike"),
    "shovel": Weapon(1, 4, -0.1, "whack"),
    "axe": Weapon(2, 6, -0.1, "hack at"),
    "mace": Weapon(3, 7, -0.05, "smash"),
    "spear": Weapon(3, 7, 0.0, "spear"),
    "short sword": Weapon(3, 8, 0.05, "slash"),
}
ARMOUR = {k: (g.slot, g.armour) for k, g in gear.GEAR.items() if g.armour or g.block}   # what's worn for a fight
BASE_HIT = 0.75             # your chance to land a blow, before the weapon and the target's dodge
REAL_WEAPONS = {"dagger", "spear", "short sword", "axe", "club", "mace", "quarterstaff"}
# The shopkeeper's wares: kind -> price in coins
WARES = {"club": 3, "quarterstaff": 4, "dagger": 6, "spear": 9, "mace": 12, "short sword": 16,
         "padded jerkin": 6, "leather coat": 12, "mail shirt": 30, "fur coat": 18,
         "leather cap": 3, "iron helm": 10, "fur hat": 5, "straw hat": 2,
         "wool cloak": 6, "oilskin cloak": 10, "fur cloak": 14,
         "wooden shield": 6, "iron-bound shield": 14,
         "leather gloves": 4, "fur mittens": 5,
         "leather boots": 6, "hobnailed boots": 9, "fur-lined boots": 10,
         "climbing gear": 20, "axe": 8, "shovel": 5}


def weapon_of(p) -> tuple[str | None, Weapon]:
    """(what you're holding, its numbers): your fists if nothing (or you've let it go)."""
    if p.wielding and p.inventory.count(p.wielding):
        return p.wielding, WEAPONS[p.wielding]
    p.wielding = None
    return None, FISTS


def protection(p) -> int:
    return gear.armour(p)


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
    shield = gear.block(p)
    if shield and rng.random() < shield:
        return 0, "block"
    dmg = rng.randint(low, high) - protection(p)
    return (dmg, "hit") if dmg > 0 else (0, "glance")
