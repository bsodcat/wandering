"""Making things (k, or Craft... in the use menu).

    campfire       2 logs and a flint, laid on open ground beside you. It burns 8 hours,
                   lighting and warming the ground around it, then leaves ashes.
    torch          a strip of cloth bound round a stick, soaked in fuel: pitch (5 hours), animal
                   fat (3) or a flask of oil (7); the best you carry is used.
    rope grapple   a coil of rope and 3 iron nails bent into hooks.

Each recipe lists what it takes; one you can't make yet is drawn dim, and picking it says what
you're missing. Logs come from felling trees, sticks fall round a felled tree, flint lies about
on stony ground and turns up when you break rock; the rest is bought (or found in chests).
"""
from __future__ import annotations

from dataclasses import dataclass

from . import items
from . import lights
from . import tiles as T
from .shop import Option, Picker

CAMPFIRE_HOURS = 8.0
CAMPFIRE_WARMTH = 18.0         # degrees C of the air right by a campfire (2 tiles)
CAMPFIRE_REACH = 2
CRAFT_MINUTES = {"campfire": 20, "torch": 10, "rope grapple": 30}


@dataclass(frozen=True)
class Recipe:
    name: str
    needs: tuple                 # (kind, how many), or (("pitch", "animal fat", ...), 1): one of them
    note: str


RECIPES = [
    Recipe("campfire", (("log", 2), ("flint", 1)), "burns 8 hours beside you"),
    Recipe("torch", (("strip of cloth", 1), ("stick", 1), (tuple(lights.TORCH_FUEL), 1)), "see 6 tiles, 2-16 hours"),
    Recipe("rope grapple", (("coil of rope", 1), ("iron nails", 3)), "climb out of a ravine"),
]


def describe_need(need) -> str:
    kind, n = need
    if isinstance(kind, tuple):
        return " or ".join(kind)
    return items.amount(kind, n)


def missing(bag, recipe: Recipe) -> list[str]:
    out = []
    for kind, n in recipe.needs:
        if isinstance(kind, tuple):
            if not any(bag.count(k) >= n for k in kind):
                out.append(" or ".join(kind))
        elif bag.count(kind) < n:
            out.append(items.amount(kind, n - bag.count(kind)))
    return out


def fire_spot(engine) -> tuple[int, int] | None:
    """Open ground beside you for a campfire: not indoors, not on a floor, nothing lying there."""
    level = engine.level
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, 1), (1, -1), (-1, -1)):
        x, y = engine.lx + dx, engine.ly + dy
        if not level.in_bounds(x, y):
            continue
        t = int(level.tiles[x, y])
        if T.WALK[t] and not T.ROOF[t] and (T.NATURAL[t] or t in (T.CAVE_FLOOR, T.ASHES, T.PATH)) \
                and not level.items.get((x, y)) and (x, y) not in level.exits:
            return x, y
    return None


def craft(engine, recipe: Recipe) -> str:
    p, level = engine.player, engine.level
    bag = p.inventory
    lack = missing(bag, recipe)
    if lack:
        return f"For a {recipe.name} you still need {', '.join(lack)}."
    if recipe.name == "campfire":
        if level is None:
            return "Step down into the region first."
        spot = fire_spot(engine)
        if spot is None:
            return "There's no open ground beside you to build a fire on."
    used = []
    for kind, n in recipe.needs:
        if isinstance(kind, tuple):
            kind = next(k for k in kind if bag.count(k) >= n)     # the best fuel first
        bag.take(kind, n)
        used.append(kind)
    engine.pass_time(CRAFT_MINUTES[recipe.name] / 60, effort=0.5)
    if recipe.name == "campfire":
        light_fire(level, *spot, engine.minutes)
        return "You stack the logs, strike the flint, and the campfire catches."
    if recipe.name == "torch":
        fuel = used[-1]
        hours = max(lights.LEAST_HOURS, lights.TORCH_FUEL[fuel])
        bag.add("torch")
        p.torch_hours.append(hours)
        return f"You bind the cloth round the stick and soak it in {fuel}: a torch good for {hours:.0f} hours."
    bag.add(recipe.name)
    return f"You make a {recipe.name}."


def light_fire(level, x: int, y: int, minutes: float) -> None:
    level.tiles[x, y] = T.CAMPFIRE
    level.campfires[(x, y)] = minutes + CAMPFIRE_HOURS * 60
    level.fire = None                 # the firelight's worked out again
    level._walk_costs = None


def tend(level, minutes: float) -> list[str]:
    """Campfires that have burned down go to ashes."""
    out = []
    for (x, y), until in list(level.campfires.items()):
        if minutes >= until:
            del level.campfires[(x, y)]
            if level.tiles[x, y] == T.CAMPFIRE:
                level.tiles[x, y] = T.ASHES
                level.fire = None
                level._walk_costs = None
                out.append("The campfire burns down to ashes.")
    return out


def near_fire(level, x: int, y: int) -> bool:
    return any(abs(fx - x) <= CAMPFIRE_REACH and abs(fy - y) <= CAMPFIRE_REACH for fx, fy in level.campfires)


def menu(engine) -> Picker:
    def build(e) -> list:
        bag = e.player.inventory
        out = []
        for r in RECIPES:
            needs = ", ".join(describe_need(n) for n in r.needs)
            out.append(Option(f"{r.name.capitalize():<13} {needs}  ({r.note})",
                              lambda e, r=r: craft(e, r), ok=not missing(bag, r), stay=True))
        return out
    picker = Picker("Crafting", build, greeting="What will you make?")
    picker.refresh(engine)
    return picker
