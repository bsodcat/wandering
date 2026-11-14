"""What you wear and carry on your body, and what each piece does for you.

You have a weapon hand (game/combat.py) and seven places to wear things. One piece goes in each
place, and the equipment menu (q) shows them all:

    head      iron helm, leather cap, fur hat, straw hat
    cloak     wool cloak, oilskin cloak, fur cloak
    body      padded jerkin, leather coat, mail shirt, fur coat
    shield    wooden shield, iron-bound shield
    hands     leather gloves, fur mittens
    feet      leather boots, hobnailed boots, fur-lined boots
    harness   climbing gear

Every piece has a few numbers, and what you have on adds them up:

- armour:  how much of each blow it stops
- block:   the chance a shield turns a blow aside completely
- warmth:  degrees C added to your clothing (a straw hat's shade cools you; mail is cold)
- cover:   the share of rain and snow kept off you
- footing: the share of time saved on slow ground (mud, scree, snow, bushes) and in lying snow
- grip:    a steadier hold when climbing (it lowers the chance of slipping)
- burden:  extra effort on every step: heavy gear tires you sooner

Climbing gear (a harness, rope and pitons) lets you climb onto boulders and rock outcrops that
are otherwise in the way, and up or down rises too steep to walk. On top of a rock you see over
the land and over the rocks around you. Climbing is slow and hard work. Exhausted, you can't
climb at all, and you can slip: less often with a good grip, more often in rain or in the dark.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Gear:
    slot: str
    armour: int = 0
    block: float = 0.0
    warmth: float = 0.0
    cover: float = 0.0
    footing: float = 0.0
    grip: float = 0.0
    burden: float = 0.0
    climbing: bool = False


SLOTS = ("head", "cloak", "body", "shield", "hands", "feet", "harness")
SLOT_NAMES = {"head": "Head", "cloak": "Cloak", "body": "Body", "shield": "Shield", "hands": "Hands",
              "feet": "Feet", "harness": "Harness"}
OLD_SLOTS = {"arm": "shield"}       # saved slots from before there was an equipment menu

GEAR = {
    # head
    "iron helm": Gear("head", armour=1, burden=0.05),
    "leather cap": Gear("head", warmth=1, cover=0.05),
    "fur hat": Gear("head", warmth=3),
    "straw hat": Gear("head", warmth=-2, cover=0.05),
    # cloak
    "wool cloak": Gear("cloak", warmth=3, cover=0.2),
    "oilskin cloak": Gear("cloak", warmth=1, cover=0.6),
    "fur cloak": Gear("cloak", warmth=5, cover=0.15, burden=0.05),
    # body
    "padded jerkin": Gear("body", armour=1, warmth=2),
    "leather coat": Gear("body", armour=2, warmth=3, cover=0.1, burden=0.05),
    "mail shirt": Gear("body", armour=3, warmth=-1, burden=0.3),
    "fur coat": Gear("body", armour=1, warmth=8, burden=0.1),
    # shield
    "wooden shield": Gear("shield", block=1 / 6, burden=0.05),
    "iron-bound shield": Gear("shield", armour=1, block=0.25, burden=0.15),
    # hands
    "leather gloves": Gear("hands", warmth=1, grip=0.06),
    "fur mittens": Gear("hands", warmth=3, grip=-0.08),
    # feet
    "leather boots": Gear("feet", warmth=1, footing=0.1),
    "hobnailed boots": Gear("feet", footing=0.2, grip=0.04, burden=0.05),
    "fur-lined boots": Gear("feet", warmth=3, footing=0.1),
    # harness
    "climbing gear": Gear("harness", grip=0.04, burden=0.1, climbing=True),
}

MOST_COVER = 0.9          # nothing keeps every drop off
MOST_FOOTING = 0.4

# Climbing (see game/elevation.py for slopes and steps)
SLIP = 0.12               # the chance of slipping on a climb, before grip and the weather
WET_SLIP = 0.12           # more in rain or snow, or when you're wet through
DARK_SLIP = 0.06          # and in the dark
LEAST_SLIP, MOST_SLIP = 0.02, 0.5
CLIMB_STAMINA = 15        # below this you're too worn out to climb
FALL = (2, 6)             # health a slip costs you


def slot_of(kind: str) -> str:
    return GEAR[kind].slot


def worn(p) -> dict:
    """Slot -> what you're wearing there. Drops anything you no longer carry, and moves things
    saved under an old slot name to the new one."""
    for old, new in OLD_SLOTS.items():
        if old in p.wearing:
            p.wearing.setdefault(new, p.wearing.pop(old))
    for slot, kind in list(p.wearing.items()):
        if not p.inventory.count(kind) or kind not in GEAR:
            del p.wearing[slot]
    return p.wearing


def wear(p, kind: str) -> str:
    slot = GEAR[kind].slot
    old = worn(p).get(slot)
    if old == kind:
        return f"You're already wearing the {kind}."
    p.wearing[slot] = kind
    verb = "put on" if slot != "harness" else "buckle on"
    return f"You take off the {old} and {verb} the {kind}." if old else f"You {verb} the {kind}."


def take_off(p, kind: str) -> str:
    for slot, k in list(p.wearing.items()):
        if k == kind:
            del p.wearing[slot]
    return f"You take off the {kind}."


def pieces(p) -> list[Gear]:
    return [GEAR[k] for k in worn(p).values()]


def total(p, stat: str) -> float:
    return sum(getattr(g, stat) for g in pieces(p))


def armour(p) -> int:
    return int(total(p, "armour"))


def block(p) -> float:
    return min(0.5, total(p, "block"))


def warmth(p) -> float:
    return total(p, "warmth")


def cover(p) -> float:
    return max(0.0, min(MOST_COVER, total(p, "cover")))


def footing(p) -> float:
    return max(0.0, min(MOST_FOOTING, total(p, "footing")))


def burden(p) -> float:
    return max(0.0, total(p, "burden"))


def grip(p) -> float:
    return total(p, "grip")


def can_climb(p) -> bool:
    return any(g.climbing for g in pieces(p))


def slip_chance(p, wet_weather: bool, dark: bool) -> float:
    """The chance of losing your hold on a climb."""
    chance = SLIP - grip(p)
    if wet_weather or p.wet >= 70:
        chance += WET_SLIP
    if dark:
        chance += DARK_SLIP
    return max(LEAST_SLIP, min(MOST_SLIP, chance))


def describe(kind: str) -> str:
    """"armour 2, warmth +3, cover 10%": what a piece does, briefly."""
    g = GEAR[kind]
    parts = []
    if g.armour:
        parts.append(f"armour {g.armour}")
    if g.block:
        parts.append(f"blocks {g.block:.0%}")
    if g.warmth:
        parts.append(f"warmth {g.warmth:+.0f}°C")
    if g.cover:
        parts.append(f"rain cover {g.cover:.0%}")
    if g.footing:
        parts.append(f"footing {g.footing:.0%}")
    if g.climbing:
        parts.append("climb rock")
    if g.grip:
        parts.append(f"grip {g.grip * 100:+.0f}")
    if g.burden:
        parts.append(f"burden {g.burden:.0%}")
    return ", ".join(parts)
