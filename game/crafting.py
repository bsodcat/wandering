"""Making things (k, or Craft... in the use menu).

    campfire       2 logs and a flint, laid on open ground beside you. It burns 8 hours,
                   lighting and warming the ground around it, then leaves ashes.
    lye            2 handfuls of ashes steeped in water: you need fresh water beside you (a
                   well, a fountain, a trough, a stream).
    bar of soap    a jar of lye boiled with a lump of animal fat: you need a fire beside you (a
                   campfire, a hearth, an oven).

A campfire burns in stages (FIRE_STAGES): the more fuel on it, the bigger it burns. Each stage
is FIRE_STAGE_HOURS of burning and lights FIRE_STAGE_TILES more tiles round it (and warms a
tile further). A new fire is laid at the second stage; feed it a log (or a bundle of sticks)
from the use menu or a click on it and it climbs a stage, up to the third; as it burns down it
drops back a stage every FIRE_STAGE_HOURS, smaller and dimmer, until it's ashes. The ashes can
be scooped up (a click on them, or the use menu) for lye.
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

CAMPFIRE_HOURS = 8.0           # a new fire: the second stage
FIRE_STAGE_HOURS = 4.0         # each stage of a campfire burns this long before it drops to the one below
FIRE_STAGES = 3                # the most fuel a fire takes: three stages, 12 hours
FIRE_STAGE_TILES = 3           # each stage lights this many tiles further round it
FIRE_FUEL = {"log": 1, "stick": 3}   # what feeds a fire a stage: a log, or a bundle of 3 sticks
FEED_MINUTES = 2
CAMPFIRE_WARMTH = 18.0         # degrees C of the air right by a campfire (2 tiles)
CAMPFIRE_REACH = 2             # tiles a fire at the second stage warms (one less or more a stage)
ASHES_GIVE = 2                 # handfuls of ashes from a burned-out fire
SCOOP_MINUTES = 3
CRAFT_MINUTES = {"campfire": 20, "torch": 10, "rope grapple": 30, "jar of lye": 30, "bar of soap": 45}
WATER = (T.WATER, T.WELL, T.FOUNTAIN, T.TROUGH)    # fresh water beside you, for lye
FIRES = (T.CAMPFIRE, T.HEARTH, T.OVEN, T.FORGE)     # a fire beside you, to boil soap


@dataclass(frozen=True)
class Recipe:
    name: str
    needs: tuple                 # (kind, how many), or (("pitch", "animal fat", ...), 1): one of them
    note: str
    beside: str = ""             # "water" or "fire": what has to be next to you


PLACED = ("campfire",)          # recipes laid down in the world: not from horseback (what goes in your bag is fine)
RECIPES = [
    Recipe("campfire", (("log", 2), ("flint", 1)), "burns 8 hours beside you"),
    Recipe("torch", (("strip of cloth", 1), ("stick", 1), (tuple(lights.TORCH_FUEL), 1)), "see 6 tiles, 2-16 hours"),
    Recipe("rope grapple", (("coil of rope", 1), ("iron nails", 3)), "climb out of a ravine"),
    Recipe("jar of lye", (("handful of ashes", 2),), "steep ashes beside water", beside="water"),
    Recipe("bar of soap", (("jar of lye", 1), ("animal fat", 1)), "boil lye and fat beside a fire", beside="fire"),
]


def describe_need(need) -> str:
    kind, n = need
    if isinstance(kind, tuple):
        return " or ".join(kind)
    return items.amount(kind, n)


def beside(engine, tiles) -> bool:
    """Whether one of these tiles is next to you (or under you)."""
    level = engine.level
    if level is None:
        return False
    return any(level.in_bounds(engine.lx + dx, engine.ly + dy) and int(level.tiles[engine.lx + dx, engine.ly + dy]) in tiles
               for dx in (-1, 0, 1) for dy in (-1, 0, 1))


def missing(bag, recipe: Recipe, engine=None) -> list[str]:
    out = []
    if engine is not None and recipe.name in PLACED and getattr(engine, "mount", None) is not None:
        out.append("to get down off your horse")
    if recipe.beside and engine is not None and not beside(engine, WATER if recipe.beside == "water" else FIRES):
        out.append("fresh water beside you" if recipe.beside == "water" else "a fire beside you")
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
    lack = missing(bag, recipe, engine)
    if lack:
        return f"For a {recipe.name} you still need {', '.join(lack)}."
    if recipe.name == "campfire":
        if level is None:
            return "Step down into the region first."
        if engine.mount is not None:
            return "You can't lay a fire from the saddle. Get down first."
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
    if recipe.name == "jar of lye":
        bag.add("jar of lye")
        return "You steep the ashes in water and pour off the lye: a jar of it, sharp enough to sting."
    if recipe.name == "bar of soap":
        bag.add("bar of soap")
        return "You boil the lye with the fat, stirring till it thickens, and leave it to set: a bar of soap."
    bag.add(recipe.name)
    return f"You make a {recipe.name}."


def light_fire(level, x: int, y: int, minutes: float) -> None:
    level.tiles[x, y] = T.CAMPFIRE
    level.campfires[(x, y)] = minutes + CAMPFIRE_HOURS * 60
    level.fire = None                 # the firelight's worked out again
    level._walk_costs = None


def stage(level, x: int, y: int, minutes: float | None = None) -> int:
    """How big a campfire burns now: 1 (low) to FIRE_STAGES, or 0 if it's out."""
    until = level.campfires.get((x, y))
    if until is None:
        return 0
    now = getattr(level, "_fire_now", None) if minutes is None else minutes
    if now is None:
        return 2
    left = (until - now) / 60
    return max(0, min(FIRE_STAGES, -int(-left // FIRE_STAGE_HOURS)))


def fire_reach(level, x: int, y: int) -> float:
    """Columns a campfire's light reaches (a row counting two): FIRE_STAGE_TILES a stage."""
    return float(2 * FIRE_STAGE_TILES * max(1, stage(level, x, y)))


def feed(engine, x: int, y: int, fuel: str) -> str:
    """Puts a log (or a bundle of sticks) on a campfire: a stage bigger, FIRE_STAGE_HOURS more."""
    level, bag = engine.level, engine.player.inventory
    if engine.mount is not None:
        return "Get down off your horse to tend the fire."
    if (x, y) not in level.campfires:
        return "There's no fire there to feed."
    n = FIRE_FUEL[fuel]
    if bag.count(fuel) < n:
        return f"You haven't got {items.amount(fuel, n)}."
    left = (level.campfires[(x, y)] - engine.minutes) / 60
    if left + FIRE_STAGE_HOURS > FIRE_STAGES * FIRE_STAGE_HOURS + 1e-6:
        return "The fire's burning as big as it'll go. Let it burn down a while first."
    bag.take(fuel, n)
    level.campfires[(x, y)] += FIRE_STAGE_HOURS * 60
    engine.pass_time(FEED_MINUTES / 60, effort=0.2)
    level._fire_now = engine.minutes
    level.fire = None
    words = {1: "burns low", 2: "burns steadily", 3: "roars up, throwing light far around"}
    what = "a log" if fuel == "log" else "a bundle of sticks"
    return f"You put {what} on the fire. It {words[stage(level, x, y, engine.minutes)]}."


def scoop_ashes(engine, x: int, y: int) -> str:
    """Scoops up the ashes of a burned-out fire, for lye."""
    level = engine.level
    if engine.mount is not None:
        return "Get down off your horse to scoop up the ashes."
    if int(level.tiles[x, y]) != T.ASHES:
        return "There are no ashes there."
    engine.player.inventory.add("handful of ashes", ASHES_GIVE)
    level.tiles[x, y] = T.CAVE_FLOOR if level.underground else T.DIRT
    level.fire = None
    level._walk_costs = None
    engine.pass_time(SCOOP_MINUTES / 60, effort=0.1)
    return f"You scoop up the cold ashes: {items.amount('handful of ashes', ASHES_GIVE)}."


def fire_options(engine, x: int, y: int) -> list:
    """What you can do with a campfire or its ashes at (x, y) (the use menu, a click)."""
    level, bag = engine.level, engine.player.inventory
    tile = int(level.tiles[x, y])
    out = []
    if tile == T.CAMPFIRE and (x, y) in level.campfires:
        now = stage(level, x, y, engine.minutes)
        left = (level.campfires[(x, y)] - engine.minutes) / 60
        full = left + FIRE_STAGE_HOURS > FIRE_STAGES * FIRE_STAGE_HOURS + 1e-6
        for fuel, n in FIRE_FUEL.items():
            what = "a log" if fuel == "log" else f"{n} sticks"
            out.append(Option(f"Add {what} to the fire (stage {now} of {FIRE_STAGES}, {left:.1f} h left)",
                              lambda e, f=fuel: e.go_do(x, y, lambda e: feed(e, x, y, f)),
                              ok=bag.count(fuel) >= n and not full))
    elif tile == T.ASHES:
        out.append(Option("Scoop up the ashes", lambda e: e.go_do(x, y, lambda e: scoop_ashes(e, x, y))))
    return out


def tend(level, minutes: float) -> list[str]:
    """Campfires burn down a stage at a time (each a little smaller and dimmer), then go to
    ashes."""
    out = []
    level._fire_now = minutes
    stages = getattr(level, "_fire_stages", None)
    if stages is None:
        stages = level._fire_stages = {}
    for (x, y) in level.campfires:
        s = stage(level, x, y, minutes)
        if stages.get((x, y)) != s:
            if (x, y) in stages and 0 < s < stages[(x, y)]:
                out.append("The campfire burns lower." if s > 1 else "The campfire has burned down to embers.")
            stages[(x, y)] = s
            level.fire = None              # its light is worked out again
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
    """Close enough to a campfire to be warmed by it: a tile further for each stage it burns."""
    for fx, fy in level.campfires:
        reach = CAMPFIRE_REACH + stage(level, fx, fy) - 2
        if abs(fx - x) <= reach and abs(fy - y) <= reach:
            return True
    return False


def menu(engine) -> Picker:
    def build(e) -> list:
        bag = e.player.inventory
        out = []
        for r in RECIPES:
            needs = ", ".join(describe_need(n) for n in r.needs)
            out.append(Option(f"{r.name.capitalize():<13} {needs}  ({r.note})",
                              lambda e, r=r: craft(e, r), ok=not missing(bag, r, e), stay=True))
        return out
    picker = Picker("Crafting", build, greeting="What will you make?")
    picker.refresh(engine)
    return picker
