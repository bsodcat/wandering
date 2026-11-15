"""Horses: buying, borrowing, saddling, riding and calling them.

- Every inn keeps a paddock of horses, and so do about half the towns. A stablehand works it and
  sells horses (HORSE_PRICE: one is led out into the paddock, yours) and saddles. The horses
  already in a paddock can be saddled and ridden off by anyone with a saddle: once you've
  saddled a horse it's yours.
- Click a horse (or use the use menu beside it) to saddle it, take the saddle off, or ride it.
  Riding, steps on open ground take RIDE_LOCAL of the time and travel across the land
  RIDE_WORLD (RIDE_ROAD on a road). You can't ride indoors, underground or up rock: going
  through a door or down stairs, you get down and leave the horse there.
- Your horses stay where you leave them. On the world map the region each is in shows a
  blinking H, so you don't lose them. Click yourself (or the use menu) to call one that's within
  CALL_REACH regions: it comes at a trot and turns up beside you out in the open when it gets
  there (HOURS_PER_REGION each).

The engine keeps your horses (Engine.horses: [level key, Actor]), the one you're on
(Engine.mount) and the one on its way (Engine.called: (Actor, the minute it arrives)).
"""
from __future__ import annotations

import random

from . import tiles as T

HORSE_PRICE, SADDLE_PRICE = 60, 15
SADDLE = "saddle"
RIDE_LOCAL = 0.4
RIDE_WORLD = 0.45
RIDE_ROAD = 0.6
CALL_REACH = 3              # regions away a horse still hears you call
HOURS_PER_REGION = 0.6      # its trot to you, a region
NAMES = ["Bramble", "Chestnut", "Dapple", "Ember", "Fennel", "Gale", "Hazel", "Juniper", "Kestrel", "Maple",
         "Nettle", "Oakley", "Pepper", "Quill", "Rowan", "Sorrel", "Thistle", "Willow", "Clover", "Ash"]


def name_horse(rng) -> str:
    return rng.choice(NAMES)


def region_of(key: tuple) -> tuple[int, int]:
    return int(key[1]), int(key[2])


def is_yours(engine, a) -> bool:
    return any(h is a for _, h in engine.horses) or engine.mount is a


def paddock(level):
    return next((p for p in level.places if p.kind == "pasture" and p.animal == "horse"), None)


def buy(engine) -> str:
    """A horse led out into the paddock here, yours (paid for already)."""
    from .people import Actor
    level = engine.level
    place = paddock(level)
    spots = [c for c in (place.tiles if place else []) if level.walkable(*c)]
    if not spots:
        spots = [(engine.lx + dx, engine.ly + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)
                 if (dx or dy) and level.walkable(engine.lx + dx, engine.ly + dy)]
    x, y = random.Random(engine.minutes).choice(spots)
    name = name_horse(random.Random(f"horse{engine.minutes}"))
    a = Actor("horse", name, x, y, work=spots, home=spots, evening=spots)
    level.actors.append(a)
    engine.horses.append([level.key, a])
    return f"The stablehand leads out {name}, a sturdy horse, into the paddock. It's yours (saddle it to ride)."


def saddle(engine, a) -> str:
    bag = engine.player.inventory
    if getattr(a, "saddled", False):
        return f"{display(a)} is already saddled."
    if not bag.take(SADDLE):
        return "You'd need a saddle."
    a.saddled = True
    if not is_yours(engine, a):
        engine.horses.append([engine.level.key, a])
        if a.name == "horse":
            a.name = name_horse(random.Random(f"{a.x},{a.y}{engine.minutes}"))
        return f"You saddle the horse. {a.name} is yours now."
    return f"You saddle {a.name}."


def unsaddle(engine, a) -> str:
    if not getattr(a, "saddled", False):
        return "It hasn't got a saddle on."
    a.saddled = False
    engine.player.inventory.add(SADDLE)
    return f"You take the saddle off {display(a)}."


def display(a) -> str:
    return "the horse" if a.name == "horse" else a.name


def can_ride_here(engine) -> str | None:
    """Why you can't ride where you are, or None."""
    if engine.level is None:
        return None
    if engine.underground:
        return "There's no room to ride underground."
    if engine.indoors:
        return "You can't ride indoors."
    return None


def mount(engine, a) -> str:
    if not getattr(a, "saddled", False):
        return f"{display(a).capitalize()} needs a saddle on first."
    if engine.mount is not None:
        return "You're already riding."
    why = can_ride_here(engine)
    if why:
        return why
    if not is_yours(engine, a):
        engine.horses.append([engine.level.key, a])
    if a in engine.level.actors:
        engine.level.actors.remove(a)
    engine.horses = [h for h in engine.horses if h[1] is not a]
    engine.mount = a
    if engine.called and engine.called[0] is a:
        engine.called = None
    return f"You swing up onto {display(a)}."


def set_down(engine, a, x: int, y: int) -> None:
    """Puts a horse back on the level at (x, y), standing about there."""
    level = engine.level
    a.x, a.y = x, y
    around = [(x + dx, y + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if level.walkable(x + dx, y + dy)]
    a.home = a.work = a.evening = around or [(x, y)]
    a.goal, a.path = None, []
    level.actors.append(a)
    engine.horses.append([level.key, a])


def beside(engine) -> tuple[int, int] | None:
    from .people import actor_at
    level = engine.level
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, 1), (1, -1), (-1, -1), (2, 0), (-2, 0)):
        x, y = engine.lx + dx, engine.ly + dy
        if level.walkable(x, y) and not T.ROOF[level.tiles[x, y]] and actor_at(level, x, y) is None \
                and (x, y) not in level.exits:
            return x, y
    return None


def dismount(engine, why: str = "") -> str:
    a = engine.mount
    if a is None:
        return "You're not riding."
    if engine.level is None:
        return "Step down into the region first."
    spot = beside(engine) or (engine.lx, engine.ly)
    engine.mount = None
    set_down(engine, a, *spot)
    return f"You get down off {display(a)}{why}."


def nearest(engine):
    """Your nearest horse within reach, its level key and how many regions off: (actor, key, d)."""
    here = (engine.player.x, engine.player.y)
    best = None
    for key, a in engine.horses:
        rx, ry = region_of(key)
        d = max(abs(rx - here[0]), abs(ry - here[1]))
        if d <= CALL_REACH and (best is None or d < best[2]):
            best = (a, key, d)
    return best


def call(engine) -> str:
    if engine.mount is not None:
        return "You're riding already."
    found = nearest(engine)
    if found is None:
        return "You whistle, but none of your horses is near enough to hear." if engine.horses \
            else "You haven't got a horse."
    a, key, d = found
    if engine.level is not None and key == engine.level.key and a in engine.level.actors:
        if max(abs(a.x - engine.lx), abs(a.y - engine.ly)) <= 1:
            return f"{display(a).capitalize()} is right here."
    engine.called = (a, engine.minutes + max(0.1, d * HOURS_PER_REGION) * 60)
    return f"You whistle for {display(a)}; it's on its way."


def arrive(engine) -> str | None:
    """A called horse turns up, once it's had time to get here and you're out in the open."""
    if engine.called is None or engine.level is None:
        return None
    a, when = engine.called
    if engine.minutes < when or engine.underground or engine.indoors:
        return None
    spot = beside(engine)
    if spot is None:
        return None
    for key, h in list(engine.horses):          # off the level it was on
        if h is a:
            old = engine.levels.get(key)
            if old is not None and a in old.actors:
                old.actors.remove(a)
    engine.horses = [h for h in engine.horses if h[1] is not a]
    engine.called = None
    set_down(engine, a, *spot)
    return f"{display(a).capitalize()} trots up beside you."


def regions(engine) -> list[tuple[int, int]]:
    """The regions your horses are standing in (not the one you're riding), for the map."""
    return [region_of(key) for key, _ in engine.horses]
