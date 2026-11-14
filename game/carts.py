"""Carts between the towns, and riding them.

Every town and city has a cart of its own. It goes round a loop of three towns: its own and the
two nearest it can reach by road. It waits in each for a day (WAIT_HOURS), then sets off down
the road to the next, a little quicker than walking. So it turns up in a town every couple of
days. Where each cart is depends only on the world and the clock (`where`), so nothing has to be
kept: the carts go on along their rounds whether you're there or not.

Carts show on the local maps too, drawn as a little cart a few tiles across: parked by the
square in town with the carter beside it, or rolling along the road between towns with the
carter up front. Walk into a cart or its carter, or click on it, and the ride menu comes up over
the world map: the four nearest towns by road from where the cart is, how long the ride takes, roughly when you'd get there, and the fare
(a few coins). Pick one and the world map comes up: the cart goes a region along the road every
half second (main.py, Engine.ride_step), and the hours that takes pass with the weather as it
comes (you sit out in it, but you're not walking). When it gets there the map closes, and you're
set down in that town's square.

On the world map you can see the carts out on the roads (╥) wherever you can see the road.
"""
from __future__ import annotations

import random
from dataclasses import dataclass

import numpy as np
import tcod

from . import tiles as T
from .climate import MINUTES_PER_HOUR, clock_text
from .worldgen import TOWNS, travel_cost

WAIT_HOURS = 24.0          # a cart waits this long in each town
ROAD_TRAVEL = 0.6          # hours a region along a road, on foot (as engine.ROAD_TRAVEL)
CART_SPEED = 0.75          # times as long as walking the same way
LOOP = 3                   # towns on a cart's round
DESTINATIONS = 4           # towns the ride menu offers
FARE_HOURS = 3.0           # a coin for every this many hours of riding
LEAST_FARE = 2
CART_FG = (205, 160, 95)
DRIVERS = ["Abel", "Bess", "Cobb", "Dora", "Eli", "Fay", "Gus", "Hattie", "Ike", "Jess", "Ned", "Olive",
           "Pell", "Ruth", "Seth", "Tilly", "Wat", "Zeb"]


@dataclass
class Leg:
    a: object            # the Site it leaves
    b: object            # and the one it's bound for
    path: list           # the regions in between, a to b
    hours: float


@dataclass
class Cart:
    driver: str
    home: object         # its town
    legs: list           # round its loop
    offset: float        # minutes into its round at the clock's start

    @property
    def period(self) -> float:
        return sum(WAIT_HOURS + leg.hours for leg in self.legs) * MINUTES_PER_HOUR


# ----------------------------------------------------------------- the network

def stop(site) -> tuple[int, int]:
    """The region a cart stops in: a city's top-left part, which has its own square."""
    return site.x, site.y


def road_costs(world) -> np.ndarray:
    cost = travel_cost(world.biome, world.river)
    return np.where(world.road & (cost > 0), round(ROAD_TRAVEL * 10), cost).astype(np.int32)


def routes(world) -> dict:
    """For each town: {other town: (hours by cart, the regions on the way)}, for those it can
    reach overland."""
    cached = getattr(world, "_cart_routes", None)
    if cached is not None:
        return cached
    towns = [s for s in world.sites if s.kind in TOWNS]
    cost = road_costs(world)
    for s in towns:                       # its own cells cost like road, so the way in is the same
        for c in s.cells:
            cost[c] = max(1, round(ROAD_TRAVEL * 10))
    out = {}
    for a in towns:
        finder = tcod.path.Pathfinder(tcod.path.SimpleGraph(cost=cost, cardinal=10, diagonal=14))
        finder.add_root(stop(a))
        finder.resolve()
        far = {}
        for b in towns:
            if b is a:
                continue
            path = [tuple(p) for p in finder.path_to(stop(b)).tolist()]
            if len(path) < 2:
                continue
            hours = sum(int(cost[p]) for p in path[1:]) / 10 * CART_SPEED
            far[b.name] = (hours, path)
        out[a.name] = far
    world._cart_routes = out
    return out


def nearest(world, site, n: int) -> list[tuple]:
    """(town, hours, path) for the n nearest towns by road from `site`."""
    by_name = {s.name: s for s in world.sites}
    options = sorted(routes(world).get(site.name, {}).items(), key=lambda kv: kv[1][0])
    return [(by_name[name], hours, path) for name, (hours, path) in options[:n]]


def carts(world) -> list[Cart]:
    """One cart for each town, going round its loop. The same every time for the same world."""
    cached = getattr(world, "_carts", None)
    if cached is not None:
        return cached
    rng = random.Random(world.seed * 7 + 11)
    out = []
    for site in (s for s in world.sites if s.kind in TOWNS):
        near = nearest(world, site, LOOP - 1)
        if not near:
            continue
        loop = [site] + [s for s, _, _ in near]
        legs = []
        table = routes(world)
        for a, b in zip(loop, loop[1:] + loop[:1]):
            hours, path = table[a.name].get(b.name, (None, None))
            if hours is None:
                back = table[b.name].get(a.name)
                if back is None:
                    break
                hours, path = back[0], back[1][::-1]
            legs.append(Leg(a, b, path, hours))
        if len(legs) != len(loop):
            continue
        cart = Cart(f"{rng.choice(DRIVERS)} the carter", site, legs, 0.0)
        cart.offset = rng.random() * cart.period
        out.append(cart)
    world._carts = out
    return out


def where(cart: Cart, minutes: float):
    """("town", site, minutes till it leaves) or ("road", leg, how far along 0..1)."""
    t = (minutes + cart.offset) % cart.period
    for leg in cart.legs:
        wait = WAIT_HOURS * MINUTES_PER_HOUR
        if t < wait:
            return "town", leg.a, wait - t
        t -= wait
        travel = leg.hours * MINUTES_PER_HOUR
        if t < travel:
            return "road", leg, t / travel
        t -= travel
    return "town", cart.legs[0].a, 0.0


def on_the_road(world, minutes: float) -> list[tuple[int, int]]:
    """The regions carts are passing through right now."""
    out = []
    for cart in carts(world):
        state = where(cart, minutes)
        if state[0] == "road":
            leg, along = state[1], state[2]
            out.append(leg.path[min(len(leg.path) - 1, int(along * len(leg.path)))])
    return out


def fare(hours: float) -> int:
    return max(LEAST_FARE, round(hours / FARE_HOURS))


def hours_text(hours: float) -> str:
    h, m = int(hours), int(round((hours - int(hours)) * 60))
    if m == 60:
        h, m = h + 1, 0
    return f"{h} h {m:02d} min" if h else f"{m} min"


# ----------------------------------------------------------------- in town

# The cart as it's drawn on a local map: (dx, dy, char, which colour) from its anchor, the middle
# of its wheels. On the road the carter sits up front; in town they stand beside it.
ON_ROAD = ["┌─☺─┐", "O═══O"]
PARKED = ["┌───┐", "O═══O"]
SPRITE_FG = {"┌": (190, 140, 80), "─": (190, 140, 80), "┐": (190, 140, 80), "☺": (205, 175, 120),
             "O": (150, 110, 70), "═": (120, 95, 65)}


def sprite_cells(anchor: tuple[int, int], rows: list[str]) -> dict:
    """{(x, y): char} for a cart whose wheels' middle is at `anchor`."""
    ax, ay = anchor
    out = {}
    for j, row in enumerate(rows):
        for i, ch in enumerate(row):
            out[(ax - len(row) // 2 + i, ay - (len(rows) - 1) + j)] = ch
    return out


@dataclass
class LocalCart:
    driver: str
    cart: Cart
    cells: dict          # (x, y) on this map -> char
    moving: bool


def spot(level, taken=()) -> tuple[int, int] | None:
    """Where a cart stands in town: open ground by the square, east of the middle if it can,
    clear of anything already standing there."""
    t = level.tiles
    cx, cy = level.width // 2, level.height // 2
    taken = set(taken)
    for r in range(10, 50):
        for dx, dy in ((r, 0), (-r, 0), (r, 1), (-r, 1), (r, -1), (-r, -1), (0, r // 2), (0, -r // 2)):
            x, y = cx + dx, cy + dy
            room = sprite_cells((x, y), PARKED)
            around = [(a + i, b + j) for a, b in room for i in (-1, 0, 1) for j in (-1, 0, 1)]
            if all(level.in_bounds(*c) and T.WALK[t[c]] and not T.WATERY[t[c]] and not T.ROOF[t[c]]
                   and c not in taken and c not in level.exits for c in around):
                return x, y
    return None


def road_point(world, path: list, along: float) -> tuple[int, int]:
    """Where along its way a cart is, in global tiles: on the road between the regions' nodes,
    drawn the same way as the road itself (localgen.draw_waterways)."""
    from .localgen import node, wiggle
    n = len(path)
    if n < 2:
        return tuple(int(v) for v in node(world, *path[0]))
    s = along * (n - 1)
    j = min(int(s), n - 2)
    f = s - j
    a, b = tuple(path[j]), tuple(path[j + 1])
    first, second = sorted((a, b))
    pts = wiggle(node(world, *first), node(world, *second), 2, 3)
    if (first, second) != (a, b):
        pts = pts[::-1]
    k = min(len(pts) - 1, int(f * (len(pts) - 1) + 0.5))
    if k < len(pts) - 1:                      # between two points of the line
        g = f * (len(pts) - 1) - int(f * (len(pts) - 1))
        x = pts[int(f * (len(pts) - 1))][0] * (1 - g) + pts[min(len(pts) - 1, int(f * (len(pts) - 1)) + 1)][0] * g
        y = pts[int(f * (len(pts) - 1))][1] * (1 - g) + pts[min(len(pts) - 1, int(f * (len(pts) - 1)) + 1)][1] * g
        return round(x), round(y)
    return pts[k]


def local_carts(engine) -> list[LocalCart]:
    """The carts on the map you're on now: parked by the square in town, or out on the road."""
    level = engine.level
    if level is None or level.key[0] != "region":
        return []
    from .localgen import LOCAL_H, LOCAL_W
    key = (level.key, round(engine.minutes, 3))
    cached = getattr(engine, "_local_carts", None)
    if cached is not None and cached[0] == key:
        return cached[1]
    world = engine.world
    rx, ry = level.region
    out = []
    parked = getattr(level, "carts", {}) or {}
    for cart in carts(world):
        state = where(cart, engine.minutes)
        if state[0] == "town":
            if cart.driver in parked:
                out.append(LocalCart(cart.driver, cart, sprite_cells(parked[cart.driver], PARKED), False))
            continue
        leg, along = state[1], state[2]
        if not any(abs(px - rx) <= 1 and abs(py - ry) <= 1 for px, py in leg.path):
            continue
        gx, gy = road_point(world, leg.path, along)
        cells = {(x - rx * LOCAL_W, y - ry * LOCAL_H): ch for (x, y), ch in sprite_cells((gx, gy), ON_ROAD).items()}
        cells = {c: ch for c, ch in cells.items() if level.in_bounds(*c)}
        if cells:
            out.append(LocalCart(cart.driver, cart, cells, True))
    engine._local_carts = (key, out)
    return out


def cart_at(engine, x: int, y: int) -> LocalCart | None:
    return next((c for c in local_carts(engine) if (x, y) in c.cells), None)


def sync(engine) -> None:
    """Parks the carts that are in this town now beside its square, with their carters, and
    takes away the ones that have left."""
    level = engine.level
    if level is None or level.key[0] != "region":
        return
    from .people import Actor
    world = engine.world
    site = world.site_at.get(level.region)
    here = {}
    if site is not None and site.kind in TOWNS and stop(site) == tuple(level.region):
        for cart in carts(world):
            state = where(cart, engine.minutes)
            if state[0] == "town" and state[1] is site:
                here[cart.driver] = cart
    parked = getattr(level, "carts", None)
    if parked is None:
        parked = level.carts = {}
    for driver in list(parked):
        if driver not in here:
            parked.pop(driver)
            level.actors = [a for a in level.actors if not (a.kind == "carter" and a.name == driver)]
    for driver, cart in here.items():
        if driver in parked:
            continue
        taken = {c for d in parked.values() for c in sprite_cells(d, PARKED)}
        pos = spot(level, {(x + i, y + j) for x, y in taken for i in range(-2, 3) for j in (-1, 0, 1)})
        if pos is None:
            continue
        parked[driver] = pos
        body = sprite_cells(pos, PARKED)
        around = [(pos[0] + i, pos[1] + j) for i in range(-4, 5) for j in range(-2, 3)
                  if (pos[0] + i, pos[1] + j) not in body and level.in_bounds(pos[0] + i, pos[1] + j)
                  and T.WALK[level.tiles[pos[0] + i, pos[1] + j]] and not T.WATERY[level.tiles[pos[0] + i, pos[1] + j]]]
        if not around:
            continue
        x, y = min(around, key=lambda c: abs(c[0] - pos[0] - 3) + abs(c[1] - pos[1]))
        level.actors.append(Actor("carter", driver, x, y, home=around, work=around, evening=around))
    engine._local_carts = None


def cart_of(engine, driver: str) -> Cart | None:
    return next((c for c in carts(engine.world) if c.driver == driver), None)


def nearest_from(world, region: tuple[int, int], n: int) -> list[tuple]:
    """(town, hours, path) for the n nearest towns by road from any region (a cart out on the
    road). From a town's own stop it's the same as `nearest`."""
    site = world.site_at.get(tuple(region))
    if site is not None and site.kind in TOWNS and stop(site) == tuple(region):
        return nearest(world, site, n)
    cache = getattr(world, "_cart_from", None)
    if cache is None:
        cache = world._cart_from = {}
    if tuple(region) not in cache:
        cost = road_costs(world)
        for s in world.sites:
            if s.kind in TOWNS:
                for c in s.cells:
                    cost[c] = max(1, round(ROAD_TRAVEL * 10))
        cost[tuple(region)] = max(1, int(cost[tuple(region)]))
        finder = tcod.path.Pathfinder(tcod.path.SimpleGraph(cost=cost, cardinal=10, diagonal=14))
        finder.add_root(tuple(region))
        finder.resolve()
        options = []
        for b in (s for s in world.sites if s.kind in TOWNS and s is not site):
            path = [tuple(q) for q in finder.path_to(stop(b)).tolist()]
            if len(path) >= 2:
                options.append((b, sum(int(cost[q]) for q in path[1:]) / 10 * CART_SPEED, path))
        options.sort(key=lambda o: o[1])
        if len(cache) > 64:
            cache.clear()
        cache[tuple(region)] = options
    return cache[tuple(region)][:n]


# ----------------------------------------------------------------- the ride

def ride_menu(driver: str, engine):
    """The ride menu for a cart: the nearest towns from where it is now."""
    from .shop import RideMenu
    if engine.level is None:
        return None
    region = tuple(engine.level.region)
    site = engine.world.site_at.get(region)
    menu = RideMenu(driver, cart_of(engine, driver), site, region, nearest_from(engine.world, region, DESTINATIONS))
    menu.refresh(engine)
    return menu


RIDE_STEP_SECONDS = 0.5   # on screen, the cart goes a region along the road this often


@dataclass
class Ride:
    """A cart ride under way: the world map shows, and the cart goes a region along the road
    every RIDE_STEP_SECONDS (main.py) until it gets there (Engine.ride_step)."""
    driver: str
    dest: object
    steps: list          # the regions still to go, in order
    each: float          # hours a region takes
    total: int           # regions in all

    @property
    def hours_left(self) -> float:
        return self.each * len(self.steps)


def ride(engine, driver: str, dest, hours: float, path: list) -> str:
    """Pays the fare and sets off for `dest`: the world map comes up, and the cart goes a region
    at a time along the road (Engine.ride_step) till it sets you down in that town's square."""
    p = engine.player
    cost = fare(hours)
    if not p.inventory.take("coin", cost):
        return f"The fare's {cost} coins, and you haven't got them."
    name = driver.split()[0]
    engine.say(f"You pay {name} {cost} coins and climb up onto the cart, bound for {dest.name}.")
    engine.shop = None
    engine.level = None
    engine.autopath, engine.pending = False, None
    steps = [tuple(c) for c in path[1:]] or [stop(dest)]
    engine.riding = Ride(driver, dest, steps, hours / len(steps), len(steps))
    engine.update_view()
    return ""


def ride_marks(engine) -> list:
    """What to mark on the world map while riding: the road still to go, and where it ends."""
    from .worldgen import SITE_KINDS
    r = engine.riding
    out = [(c, "·", (255, 220, 120)) for c in r.steps[:-1]]
    out += [(c, SITE_KINDS[r.dest.kind][0], (255, 240, 150)) for c in r.dest.cells]
    out.append(((engine.player.x, engine.player.y), "╥", CART_FG))
    return out


def arrival_text(engine, hours: float) -> str:
    return clock_text(engine.minutes + hours * MINUTES_PER_HOUR)
