"""The overworld: terrain, climate, water, biomes, settlements and roads, all from one seed.

Every array is indexed [x, y]. One world cell is a region a few kilometres across. Later each
region is expanded into its own local map (a chunk), seeded with World.region_seed(x, y), so
the same place always comes out the same. Rivers keep their flow direction (flow_dx/flow_dy)
and every road step is kept as an edge (road_edges), so a chunk knows where roads enter and leave.

The steps, in order:
  1. elevation   noise continents with ridged mountain ranges, sea all round the edge;
                 islands added or sunk, and volcanoes' cones built (game/volcanoes.py)
  2. temperature warm at the equator (the middle row), cold at the poles and up high
  3. moisture    wet near coasts and in the rain belts, dry in the horse latitudes
     erosion     ages of rain and frost: rivers cut valleys, silt fills the plains and
                 basins, crags crumble (game/erosion.py); the coastline stays put
  4. drainage    fill basins (they become lakes), route every cell downhill to the sea
                 and add up the rain that flows through it; the big flows are rivers, and
                 springs where groundwater comes up start rivers of their own
  5. biomes      from altitude, temperature and moisture; volcanoes and their lava fields
  6. people      a few great stone cities, each spanning 2 x 2 regions on a big river; towns
                 where farmland, a mild climate and water meet (most of them on a river);
                 highways joining them
                 (a spanning tree by walking time, plus short cuts); villages near the roads
                 with tracks out to them; inns along long highways; watchtowers on high
                 ground over the roads; forts guarding the highways from high ground;
                 ruins and caves out in the wilds

The world settings picked in Create a World (game/tweaks.py) turn the dials on each step:
how much land, islands, mountains, rain, warmth, plant cover, lakes, groundwater, people and
volcanoes. Each extra feature draws from its own random stream, so the rest of the world
stays put when one is changed.
"""
from __future__ import annotations

import heapq
import random
from dataclasses import dataclass, field

import numpy as np
import tcod

from . import biomes as B
from . import eras
from . import erosion
from . import tweaks as TW
from . import volcanoes as V

WORLD_W, WORLD_H = 256, 128
LAND_SHARE = 0.42        # of the map above sea level
MAX_ALTITUDE = 4800.0    # metres, the highest peak
MAX_DEPTH = 5000.0       # metres, the deepest sea
LAPSE_RATE = 6.5         # degrees C lost per 1000 m of height
RIVER_SHARE = 0.035      # of land cells that carry a river
LAKE_DEPTH = 20.0        # metres a basin must be filled by to count as a lake

DIRS = [(dx, dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if dx or dy]

SITE_KINDS = {  # kind: (char, colour, how many at most, closest to another of its kind)
    "city": ("▓", (235, 232, 245), 3, 40),
    "town": ("■", (255, 220, 110), 12, 16),
    "fort": ("╬", (205, 190, 170), 6, 22),
    "village": ("⌂", (230, 190, 120), 28, 6),
    "inn": ("≡", (240, 170, 90), 14, 12),
    "tower": ("↑", (200, 200, 215), 10, 16),
    "ruins": ("π", (170, 160, 150), 22, 6),
    "cave": ("Ω", (200, 170, 140), 16, 6),
}
SETTLED = ("city", "town", "village", "inn", "fort")   # people live there: you can rest indoors
TOWNS = ("city", "town")               # places with shops, carts between them
CITY_SPAN = (2, 2)                     # regions a city covers


@dataclass
class Site:
    kind: str
    name: str
    x: int
    y: int
    port: bool = False   # on the sea: it has docks
    span: tuple = (1, 1)  # regions it covers, from (x, y) right and down (a city's 2 x 2)

    @property
    def settled(self) -> bool:
        return self.kind in SETTLED

    @property
    def cells(self) -> list[tuple[int, int]]:
        return [(self.x + i, self.y + j) for i in range(self.span[0]) for j in range(self.span[1])]

    def part(self, x: int, y: int) -> tuple[int, int]:
        """Which of its regions (x, y) is, counting from the top left."""
        return x - self.x, y - self.y

    def distance(self, x: int, y: int) -> int:
        """Regions from (x, y) to the nearest of its regions."""
        dx = max(self.x - x, 0, x - (self.x + self.span[0] - 1))
        dy = max(self.y - y, 0, y - (self.y + self.span[1] - 1))
        return max(dx, dy)


@dataclass
class World:
    seed: int
    elevation: np.ndarray    # metres; below 0 is sea
    temperature: np.ndarray  # yearly mean air temperature, degrees C
    moisture: np.ndarray     # 0..1
    biome: np.ndarray        # uint8 ids into biomes.BIOMES
    river: np.ndarray        # bool
    flow: np.ndarray         # rain gathered from upstream; how big the river is
    flow_dx: np.ndarray      # which way the water runs out of each land cell
    flow_dy: np.ndarray
    road: np.ndarray         # bool
    sites: list[Site] = field(default_factory=list)
    road_edges: dict = field(default_factory=dict)       # ((x, y), (x, y)) sorted -> width
    river_width: np.ndarray | None = None                # 1..3 on rivers, 0 elsewhere
    history: tuple = ()                                  # ((years, change), ...): its eras (game/eras.py)
    tweaks: TW.Tweaks = TW.DEFAULT                       # the world settings it was made with
    volcanoes: list = field(default_factory=list)        # game/volcanoes.py's Volcano
    ash: np.ndarray | None = None                        # 0..1 fresh ash on each cell
    aquifer: np.ndarray | None = None                    # 0..1 how near the surface groundwater lies
    spring: np.ndarray | None = None                     # bool: springs rise here

    def __post_init__(self):
        self.site_at = {c: s for s in self.sites for c in s.cells}
        self.volcano_at = {(v.x, v.y): v for v in self.volcanoes}

    @property
    def width(self) -> int:
        return self.biome.shape[0]

    @property
    def height(self) -> int:
        return self.biome.shape[1]

    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height

    def walkable(self, x: int, y: int) -> bool:
        return self.in_bounds(x, y) and B.TRAVEL[self.biome[x, y]] > 0

    @property
    def years(self) -> int:
        """How many years of history lie behind it."""
        return eras.years(self.history)

    def region_seed(self, x: int, y: int) -> int:
        """The seed for this region's local map: the same every time for the same world."""
        return (self.seed * 73856093 ^ x * 19349663 ^ y * 83492791) & 0xFFFFFFFF


# ----------------------------------------------------------------- helpers

def noise_field(rng: random.Random, w: int, h: int, scale: float, octaves: int) -> np.ndarray:
    """Fractal simplex noise over the map, roughly -1..1."""
    noise = tcod.noise.Noise(2, algorithm=tcod.noise.Algorithm.SIMPLEX,
                             implementation=tcod.noise.Implementation.FBM,
                             octaves=octaves, seed=rng.getrandbits(31))
    origin = (rng.uniform(0, 1000), rng.uniform(0, 1000))
    return noise[tcod.noise.grid((w, h), scale, origin, indexing="ij")].astype(np.float32)


def blur(a: np.ndarray, passes: int) -> np.ndarray:
    """A cheap wide blur: repeated 3x3 box averages, edges held."""
    a = a.astype(np.float32)
    for _ in range(passes):
        p = np.pad(a, 1, mode="edge")
        a = sum(p[1 + dx: p.shape[0] - 1 + dx, 1 + dy: p.shape[1] - 1 + dy]
                for dx in (-1, 0, 1) for dy in (-1, 0, 1)) / 9
    return a


def latitude(h: int) -> np.ndarray:
    """Per row: -1 at the north pole (top), 0 at the equator, +1 at the south pole."""
    return ((np.arange(h) + 0.5) / h * 2 - 1).astype(np.float32)


def neighbours_any(mask: np.ndarray) -> np.ndarray:
    """Cells with at least one of their 8 neighbours in `mask`."""
    p = np.pad(mask, 1)
    out = np.zeros_like(mask)
    for dx, dy in DIRS:
        out |= p[1 + dx: p.shape[0] - 1 + dx, 1 + dy: p.shape[1] - 1 + dy]
    return out


# ----------------------------------------------------------------- steps

def make_elevation(rng: random.Random, w: int, h: int, land_share: float = LAND_SHARE,
                   mountains: float = 1.0) -> np.ndarray:
    base = noise_field(rng, w, h, 1 / 64, 6)
    ridges = 1 - np.abs(noise_field(rng, w, h, 1 / 40, 4))     # sharp crests along the zero lines
    ranges = np.clip(noise_field(rng, w, h, 1 / 90, 2) * 2, 0, 1)  # where mountain ranges are allowed
    x = np.minimum(np.arange(w), w - 1 - np.arange(w))[:, None] / (w * 0.12)
    y = np.minimum(np.arange(h), h - 1 - np.arange(h))[None, :] / (h * 0.14)
    edge = np.clip(np.minimum(x, y), 0, 1)                      # 0 at the border, 1 inland
    e = base + ridges ** 3 * ranges * 0.9 * mountains - (1 - edge) ** 2 * 1.2
    sea = np.quantile(e, 1 - land_share)
    e = e - sea
    land = e > 0
    top = MAX_ALTITUDE * (0.7 + 0.3 * mountains)
    e[land] = (e[land] / e[land].max()) ** (1.4 + 0.3 * (1 - mountains)) * top   # flatter lowlands, steep peaks
    e[~land] = e[~land] / -e[~land].min() * MAX_DEPTH
    border = np.ones_like(land)
    border[2:-2, 2:-2] = False
    e[border & land] = -20.0   # always sea at the very edge
    return e.astype(np.float32)


def make_temperature(rng: random.Random, elevation: np.ndarray) -> np.ndarray:
    w, h = elevation.shape
    lat = np.abs(latitude(h))[None, :]
    sea_level = 28 - 44 * lat ** 1.35                            # 28 at the equator, -16 at the poles
    height = np.maximum(elevation, 0) / 1000 * LAPSE_RATE
    wobble = noise_field(rng, w, h, 1 / 50, 3) * 3
    return (sea_level - height + wobble).astype(np.float32)


def make_moisture(rng: random.Random, elevation: np.ndarray) -> np.ndarray:
    w, h = elevation.shape
    coast = blur((elevation <= 0).astype(np.float32), 12)       # how near the sea
    lat = np.abs(latitude(h))[None, :]
    belts = 0.5 + 0.5 * np.cos(lat * np.pi * 3.3)               # wet tropics, dry ~30 deg, wet ~60 deg
    patchy = (noise_field(rng, w, h, 1 / 45, 4) + 1) / 2
    return np.clip(0.42 * patchy + 0.33 * coast ** 0.6 + 0.3 * belts - 0.05, 0, 1).astype(np.float32)


def drain(elevation: np.ndarray, rain: np.ndarray):
    """Priority-flood from the sea: every land cell is reached from the lowest way out, which
    is where its water goes. Basins are raised to their spill height on the way (`filled`).
    Returns the filled heights, the flow direction of each cell and the water through it."""
    w, h = elevation.shape
    elev = elevation.tolist()
    filled = [row[:] for row in elev]
    out = [[None] * h for _ in range(w)]
    done = [[False] * h for _ in range(w)]
    heap = []
    for x in range(w):
        for y in range(h):
            if elev[x][y] <= 0 or x in (0, w - 1) or y in (0, h - 1):
                heap.append((elev[x][y], x, y))
                done[x][y] = True
    heapq.heapify(heap)
    order = []
    while heap:
        e, x, y = heapq.heappop(heap)
        order.append((x, y))
        for dx, dy in DIRS:
            nx, ny = x + dx, y + dy
            if 0 <= nx < w and 0 <= ny < h and not done[nx][ny]:
                done[nx][ny] = True
                ne = max(elev[nx][ny], e + 0.01)   # a hair higher, so flats still drain
                filled[nx][ny] = ne
                out[nx][ny] = (x, y)
                heapq.heappush(heap, (ne, nx, ny))
    flow = rain.astype(np.float64).tolist()
    flow_dx = np.zeros((w, h), np.int8)
    flow_dy = np.zeros((w, h), np.int8)
    for x, y in reversed(order):                   # highest first, so upstream adds up before downstream
        target = out[x][y]
        if target is not None:
            flow[target[0]][target[1]] += flow[x][y]
            flow_dx[x, y], flow_dy[x, y] = target[0] - x, target[1] - y
    return np.array(filled, np.float32), flow_dx, flow_dy, np.array(flow, np.float32)


def classify(elevation, temperature, moisture, lake) -> np.ndarray:
    alt, t, m = elevation, temperature, moisture
    coast = neighbours_any(alt <= 0) & (alt > 0)
    rules = [
        (alt < -1200, B.DEEP_OCEAN),
        (alt <= 0, B.OCEAN),
        (lake, B.LAKE),
        ((alt > 3200) | ((alt > 2200) & (t < -6)), B.PEAKS),
        (alt > 1900, B.MOUNTAINS),
        (t < -9, B.GLACIER),
        (t < -2, B.TUNDRA),
        (alt > 1150, B.HILLS),
        ((alt > 700) & (t > 4) & (t < 19) & (m > 0.2) & (m < 0.62), B.DOWNS),     # rolling grassy uplands
        (coast & (alt < 40) & (t > 3), B.BEACH),
        ((t < 6) & (m > 0.42), B.TAIGA),
        (t < 6, B.STEPPE),
        ((m > 0.78) & (alt < 350) & (t > 4), B.SWAMP),
        ((t > 17) & (m < 0.27), B.DESERT),
        ((t > 20) & (m < 0.5), B.SAVANNA),
        (t > 20, B.JUNGLE),
        (m < 0.22, B.SHRUBLAND),
        ((m > 0.36) & (m < 0.5) & (t > 6) & (t < 18) & (alt < 600), B.PASTURE),   # lush, open grazing land
        (m < 0.42, B.GRASSLAND),
    ]
    return np.select([c for c, _ in rules], [b for _, b in rules], B.FOREST).astype(np.uint8)


# ----------------------------------------------------------------- people

START = ["Ash", "Bar", "Bel", "Bram", "Cal", "Dun", "El", "Fen", "Gar", "Hal", "Ith", "Kel", "Lor",
         "Mar", "Nor", "Oak", "Pell", "Quen", "Ros", "Stan", "Tor", "Ul", "Val", "Wyn", "Yar", "Thorn",
         "Mill", "Elder", "Grey", "Red", "Black", "Cold", "High", "Low", "Stone", "Briar"]
END = ["ford", "holm", "wick", "by", "ton", "dale", "mere", "stead", "vale", "burg", "haven", "moor",
       "fell", "gate", "well", "crest", "field", "brook", "mouth", "hollow"]
INN_NAMES = ["The {} Arms", "The {} Rest", "The Crossed {}", "The Wayfarer's {}", "The {} Lantern"]
INN_WORDS = ["Oak", "Stag", "Plough", "Boar", "Raven", "Kettle", "Anvil", "Wheel", "Swan", "Hound"]

HIGHWAY, TRACK = 2, 1        # road widths on the local maps
MAX_SHORTCUT_COST = 7000     # path cost (about 60 regions of easy ground): the longest extra road
LOOP_DETOUR = 1.45           # add a direct road when the network makes you walk this much further
INN_SPACING = 24             # regions of highway between inns
TOWN_EDGE = 12               # regions: towns keep this far from the left and right edges (half that, top and bottom)
VILLAGE_TRACK = 30           # regions a village will lay a track to reach the network
FARMLAND = [B.GRASSLAND, B.FOREST, B.STEPPE, B.SHRUBLAND, B.SAVANNA, B.BEACH, B.TAIGA, B.PASTURE, B.DOWNS]
HIGH_GROUND = [B.HILLS, B.MOUNTAINS]


def make_name(rng: random.Random, taken: set[str]) -> str:
    for _ in range(200):
        name = rng.choice(START) + rng.choice(END)
        if name not in taken:
            taken.add(name)
            return name
    name = f"{rng.choice(START)}{rng.choice(END)} {len(taken)}"
    taken.add(name)
    return name


def dilate(mask: np.ndarray, steps: int) -> np.ndarray:
    for _ in range(steps):
        mask = mask | neighbours_any(mask)
    return mask


def travel_cost(biome: np.ndarray, river: np.ndarray) -> np.ndarray:
    """Tenths of an hour to cross each region, 0 where you can't. Rivers cost a crossing."""
    cost = np.round(B.TRAVEL[biome] * 10 + river * 8).astype(np.int32)
    cost[B.TRAVEL[biome] <= 0] = 0
    return cost


class Planner:
    """Lays out where people live and the roads between them, in a sensible order: towns, the
    highways joining them, villages near the roads with tracks out to them, inns along long
    highways, watchtowers over the roads, then ruins and caves out in the wilds."""

    def __init__(self, rng: random.Random, arrays: dict, people: float = 1.0):
        self.rng = rng
        self.limits = {kind: (most, spacing) for kind, (_, _, most, spacing) in SITE_KINDS.items()}
        for kind in SETTLED:                       # the Population setting: more or fewer, closer or further apart
            most, spacing = self.limits[kind]
            self.limits[kind] = (max(2, round(most * people)), max(3, round(spacing / max(1.0, people) ** 0.5)))
        self.biome, self.river = arrays["biome"], arrays["river"]
        self.temperature, self.elevation = arrays["temperature"], arrays["elevation"]
        self.cost = travel_cost(self.biome, self.river)
        self.road = np.zeros(self.biome.shape, bool)
        self.edges: dict[tuple, int] = {}
        self.sites: list[Site] = []
        self.names: set[str] = set()
        self.ocean = np.isin(self.biome, [B.OCEAN, B.DEEP_OCEAN])
        w, h = self.biome.shape
        self.jitter = np.array([[rng.random() for _ in range(h)] for _ in range(w)], np.float32)

    # -- sites

    def free(self, x: int, y: int, kind: str, spacing: int, span=(1, 1)) -> bool:
        cells = [(x + i, y + j) for i in range(span[0]) for j in range(span[1])]
        return all(s.distance(cx, cy) >= (spacing if s.kind == kind else 4 if "city" not in (kind, s.kind) else 6)
                   for s in self.sites for cx, cy in cells)

    def add(self, kind: str, x: int, y: int, span=(1, 1)) -> Site:
        base = make_name(self.rng, self.names)
        name = {"ruins": f"Ruins of {base}", "cave": f"{base} Cave", "tower": f"{base} Tower",
                "inn": self.rng.choice(INN_NAMES).format(self.rng.choice(INN_WORDS))}.get(kind, base)
        port = kind in ("town", "village") and bool(self.ocean[max(0, x - 1): x + 2, max(0, y - 1): y + 2].any())
        site = Site(kind, name, int(x), int(y), port, tuple(span))
        self.sites.append(site)
        return site

    def place_cities(self, score: np.ndarray, most: int) -> list[Site]:
        """Cities: the best 2 x 2 blocks of regions, all of it good land."""
        sw, sh = CITY_SPAN
        w, h = score.shape
        block = np.full(score.shape, -1.0)
        block[: w - sw + 1, : h - sh + 1] = sum(score[i: w - sw + 1 + i, j: h - sh + 1 + j]
                                                for i in range(sw) for j in range(sh))
        good = score > 0
        whole = np.zeros(score.shape, bool)
        whole[: w - sw + 1, : h - sh + 1] = np.logical_and.reduce(
            [good[i: w - sw + 1 + i, j: h - sh + 1 + j] for i in range(sw) for j in range(sh)])
        block[~whole] = -1
        placed = []
        for flat in np.argsort(block, axis=None, kind="stable")[::-1]:
            if len(placed) >= most:
                break
            x, y = divmod(int(flat), h)
            if block[x, y] <= 0:
                break
            if self.free(x, y, "city", self.limits["city"][1], CITY_SPAN):
                placed.append(self.add("city", x, y, CITY_SPAN))
        return placed

    def place(self, kind: str, score: np.ndarray) -> list[Site]:
        most, spacing = self.limits[kind]
        placed = []
        h = score.shape[1]
        already = sum(s.kind == kind for s in self.sites)
        for flat in np.argsort(score, axis=None, kind="stable")[::-1]:
            if already + len(placed) >= most:
                break
            x, y = divmod(int(flat), h)
            if score[x, y] <= 0:
                break
            if self.free(x, y, kind, spacing):
                placed.append(self.add(kind, x, y))
        return placed

    def inherit(self, sites: list[Site]) -> list[Site]:
        """Places kept from before a time skip, where the land still allows: a settlement needs
        ground people can live on (not under water or ice, nor on a volcano or fresh lava); a
        ruin, a cave or a tower needs ground you can walk to. Ones that can't stay are lost."""
        out = []
        for s in sites:
            x, y = s.x, s.y
            b = int(self.biome[x, y])
            walkable = B.TRAVEL[b] > 0
            if not walkable or b in (B.VOLCANO, B.LAVA_FIELD):
                continue
            if s.settled and s.kind != "fort" and b in (B.GLACIER, B.PEAKS, B.MOUNTAINS):
                continue
            cells = s.cells
            if any(not (0 <= cx < self.biome.shape[0] and 0 <= cy < self.biome.shape[1])
                   or B.TRAVEL[self.biome[cx, cy]] <= 0 for cx, cy in cells):
                continue
            if any(o.distance(cx, cy) == 0 for o in self.sites for cx, cy in cells):
                continue
            port = s.kind in ("town", "village") and bool(self.ocean[max(0, x - 1): x + 2, max(0, y - 1): y + 2].any())
            site = Site(s.kind, s.name, x, y, port, tuple(s.span))
            self.sites.append(site)
            out.append(site)
        for s in sites:              # their names stay taken, even the lost ones', so no new place reuses one
            self.names.add(s.name.removeprefix("Ruins of ").removesuffix(" Cave").removesuffix(" Tower"))
        return out

    # -- roads

    def finder(self, start, with_roads: bool = True) -> tcod.path.Pathfinder:
        cost = np.where(self.road & (self.cost > 0), 3, self.cost).astype(np.int32) if with_roads else self.cost
        finder = tcod.path.Pathfinder(tcod.path.SimpleGraph(cost=cost, cardinal=10, diagonal=14))
        finder.add_root(start)
        return finder

    def lay(self, path: np.ndarray, width: int) -> None:
        self.road[path[:, 0], path[:, 1]] = True
        for p, q in zip(path[:-1].tolist(), path[1:].tolist()):
            key = tuple(sorted((tuple(p), tuple(q))))
            self.edges[key] = max(self.edges.get(key, 0), width)

    def highways(self, towns: list[Site]) -> list[np.ndarray]:
        """A minimum spanning tree over the towns by walking time, so every town that can be
        walked to is on the network, plus direct roads wherever the tree makes a short trip much
        longer. Towns on different landmasses stay apart."""
        n = len(towns)
        far = np.iinfo(np.int32).max
        cost = np.full((n, n), far, np.int64)
        for i, a in enumerate(towns):
            f = self.finder((a.x, a.y), with_roads=False)
            f.resolve()
            for j, b in enumerate(towns):
                cost[i, j] = f.distance[b.x, b.y]
        pairs = sorted((cost[i, j], i, j) for i in range(n) for j in range(i + 1, n) if cost[i, j] < far)
        group = list(range(n))

        def root(i):
            while group[i] != i:
                group[i] = group[group[i]]
                i = group[i]
            return i

        chosen = []
        for c, i, j in pairs:
            if root(i) != root(j):
                group[root(i)] = root(j)
                chosen.append((i, j))
        net = np.where(np.eye(n, dtype=bool), 0, np.inf)
        for i, j in chosen:
            net[i, j] = net[j, i] = cost[i, j]
        for k in range(n):  # shortest trips over the network
            net = np.minimum(net, net[:, k:k + 1] + net[k:k + 1, :])
        for c, i, j in pairs:
            if (i, j) not in chosen and c < MAX_SHORTCUT_COST and c * LOOP_DETOUR < net[i, j]:
                chosen.append((i, j))
                net[i, j] = net[j, i] = c
                for k in (i, j):
                    net = np.minimum(net, net[:, k:k + 1] + net[k:k + 1, :])
        paths = []
        for i, j in sorted(chosen, key=lambda e: cost[e]):
            a, b = towns[i], towns[j]
            path = self.finder((a.x, a.y)).path_to((b.x, b.y))
            if len(path) > 1:
                self.lay(path, HIGHWAY)
                paths.append(path)
        return paths

    def spur(self, site: Site, limit: int) -> bool:
        """A track from a site to the nearest road or settlement, if one is close enough."""
        f = self.finder((site.x, site.y))
        f.resolve()
        targets = self.road.copy()
        for s in self.sites:
            if s.settled:
                targets[s.x, s.y] = True
        targets[site.x, site.y] = False
        if not targets.any():
            return False
        dist = np.where(targets, f.distance, np.iinfo(np.int32).max)
        x, y = np.unravel_index(int(np.argmin(dist)), dist.shape)
        path = f.path_to((int(x), int(y)))
        if dist[x, y] >= np.iinfo(np.int32).max or len(path) - 1 > limit or len(path) < 2:
            return False
        self.lay(path, TRACK)
        return True


def plan_people(rng: random.Random, arrays: dict, people: float = 1.0,
                keep: list | None = None) -> tuple[list[Site], np.ndarray, dict]:
    P = Planner(rng, arrays, people)
    kept = P.inherit(keep or [])
    biome, t, river = P.biome, P.temperature, P.river
    land = B.TRAVEL[biome] > 0
    farmland = np.isin(biome, FARMLAND)
    near_water = neighbours_any(river | np.isin(biome, B.WATER))
    good_climate = 1 - np.clip(np.abs(t - 15) / 15, 0, 1)
    j = P.jitter
    rich = arrays.get("rich_soil", 0)               # old volcanic ash: the best farmland
    farmland = farmland & (biome != B.LAVA_FIELD)

    w, h = biome.shape
    inland = (np.minimum(np.arange(w), w - 1 - np.arange(w))[:, None] >= TOWN_EDGE) &         (np.minimum(np.arange(h), h - 1 - np.arange(h))[None, :] >= TOWN_EDGE // 2)   # not out at the world's edge
    by_river = dilate(river, 1)                     # most towns grew up on a river
    lowland = (P.elevation < 900) * inland
    cities = [s for s in kept if s.kind == "city"]
    city_land = farmland * (good_climate * 2 + river * 2.5 + near_water + j * 0.5 + rich) * lowland * by_river
    cities += P.place_cities(city_land, max(0, P.limits["city"][0] - len(cities)))
    towns = [s for s in kept if s.kind == "town"]
    towns += P.place("town", farmland * (good_climate * 2 + near_water * 1.5 + river * 1.5 + j * 0.8 + rich * 1.5)
                     * (P.elevation < 900) * inland * (0.25 + 0.75 * by_river))
    highways = P.highways(cities + towns)

    near_road = dilate(P.road, 3)
    for v in [s for s in kept if s.kind == "village"] + \
            P.place("village", farmland * (good_climate + near_water + near_road * 1.5 + j * 1.5 + rich)):
        P.spur(v, VILLAGE_TRACK)
    for inn in (s for s in kept if s.kind == "inn"):
        P.spur(inn, VILLAGE_TRACK)

    gap = max(8, round(INN_SPACING / max(0.6, people)))
    for path in highways:   # an inn every so often along the long highways
        for k in range(gap // 2, len(path) - gap // 2, gap):
            x, y = (int(c) for c in path[k])
            if not river[x, y] and P.free(x, y, "inn", gap // 2) and \
                    sum(s.kind == "inn" for s in P.sites) < P.limits["inn"][0]:
                P.add("inn", x, y)

    overlook = np.isin(biome, HIGH_GROUND) & dilate(P.road, 3) & ~P.road & ~river
    for tower in [s for s in kept if s.kind == "tower"] + P.place("tower", overlook * (P.elevation / 1000 + j)):
        P.spur(tower, 6)

    guarded = np.isin(biome, HIGH_GROUND + [B.DOWNS]) & dilate(P.road, 2) & ~P.road & ~river
    for fort in [s for s in kept if s.kind == "fort"] + P.place("fort", guarded * (P.elevation / 1500 + j + 0.3)):
        P.spur(fort, 8)

    P.place("ruins", land * (biome != B.GLACIER) * (j + 0.2 + near_road * 0.3) * ~P.road)
    edge_of_high = np.isin(biome, HIGH_GROUND) & neighbours_any(~np.isin(biome, HIGH_GROUND + [B.PEAKS]))
    P.place("cave", edge_of_high * (j + 0.2) * ~P.road)
    for s in P.sites:
        for cx, cy in s.cells:
            P.road[cx, cy] = False  # the site itself is drawn, not a road
    return P.sites, P.road, P.edges


# ----------------------------------------------------------------- the whole thing

LAKE_DEPTHS = [float("inf"), 45.0, LAKE_DEPTH, 10.0, 5.0]   # by the Lakes setting
HOLLOWS = [0, 0, 0, 25, 60]                                 # extra hollows dug for lakes to fill
SMALL_ISLAND = [400, 40]                                    # cells: islands smaller than this sink (None, Few)
ISLAND_AT = {3: 1.7, 4: 1.15}                               # noise height where new islands rise
SPRINGS = 40                                                # springs at most, at Normal aquifers
GROUNDWATER = 0.16                                          # moisture groundwater adds, at most


def generate(seed: int, width: int = WORLD_W, height: int = WORLD_H, history: tuple = (),
             tweaks: TW.Tweaks | None = None, keep: list | None = None) -> World:
    """The world from a seed, after the eras in `history` (game/eras.py), with the world
    settings in `tweaks` (game/tweaks.py). `keep` is the places that came through a time skip
    (eras.survivors): they stay where they are if the land still allows, and the rest of the
    world's people are placed around them."""
    tw = tweaks or TW.DEFAULT
    rng = random.Random(seed)
    fx = eras.effects(history)
    elevation = make_elevation(rng, width, height, tw.value("Land"), tw.value("Mountains"))
    elevation = islands(seed, elevation, int(tw.value("Islands")))
    volcanoes = V.place(seed, elevation, int(tw.value("Volcanoes")), lambda r: make_name(r, set()))
    elevation = V.raise_cones(seed, elevation, volcanoes)
    if fx.lift:
        elevation = np.where(elevation > 0, elevation * np.float32(1 + fx.lift), elevation)
    if fx.sea:
        elevation = shift_sea(elevation, fx.sea)
    eruptions = tw.index("Eruptions")
    temperature = make_temperature(rng, elevation) + np.float32(fx.warm + tw.value("Temperature"))
    if eruptions == TW.VIOLENT and volcanoes:
        temperature -= np.float32(V.WINTER)                  # ash in the sky: a volcanic winter
    moisture = make_moisture(rng, elevation) + np.float32(fx.wet + tw.value("Rainfall"))
    moisture = np.clip(moisture, 0, 1).astype(np.float32)
    worn = erosion.erode_world(seed, elevation, moisture, temperature, drain, fx.passes, fx.frost)
    temperature += (elevation - worn) * np.float32(LAPSE_RATE / 1000) * (elevation > 0)   # lower is warmer
    temperature += V.warmth(worn.shape, volcanoes, eruptions)
    elevation = V.craters(worn, volcanoes, eruptions)
    elevation = hollows(seed, elevation, HOLLOWS[tw.index("Lakes")])
    land = elevation > 0
    aquifer = groundwater(seed, elevation, tw.value("Aquifers"))
    moisture = np.clip(moisture + aquifer * GROUNDWATER * np.clip(1 - elevation / 2500, 0, 1) * land, 0, 1)
    filled, flow_dx, flow_dy, flow = drain(elevation, moisture * land)
    lake = land & (filled - elevation > LAKE_DEPTHS[tw.index("Lakes")])
    river = land & ~lake & (flow > np.quantile(flow[land], 1 - RIVER_SHARE))
    spring = springs(seed, elevation, aquifer, lake | ~land, round(SPRINGS * tw.value("Aquifers")))
    river |= downstream(spring, flow_dx, flow_dy, lake | ~land | river)
    moisture = np.clip(moisture + blur((river | lake).astype(np.float32), 2) * 0.35, 0, 1)
    fresh_ash = V.ash(elevation.shape, volcanoes, eruptions, fresh=True)
    rich_soil = V.ash(elevation.shape, volcanoes, eruptions, fresh=False) * (1 - fresh_ash)
    growth = (tw.value("Vegetation") - 1) * 0.3 - fresh_ash * 0.3   # how much greener the land looks
    biome = classify(elevation, temperature, np.clip(moisture + growth, 0, 1), lake)
    lava = V.lava(seed, elevation, lake | ~land, flow_dx, flow_dy, volcanoes, eruptions)
    vent = V.vent_mask(elevation.shape, volcanoes) & land & ~lake
    biome[lava & ~vent & land & ~lake] = B.LAVA_FIELD
    biome[vent] = B.VOLCANO
    river &= B.TRAVEL[biome] > 0
    river &= ~vent
    river_width = np.zeros(river.shape, np.uint8)
    if river.any():
        q = np.quantile(flow[river], [0.6, 0.9])
        river_width[river] = 1 + (flow[river] > q[0]) + (flow[river] > q[1])
    arrays = dict(elevation=elevation, temperature=temperature, moisture=moisture, biome=biome, river=river,
                  rich_soil=rich_soil)
    sites, road, road_edges = plan_people(rng, arrays, tw.value("Population"), keep)
    return World(seed, elevation, temperature, moisture, biome, river, flow, flow_dx, flow_dy, road,
                 sites, road_edges, river_width, tuple(history), tw, volcanoes, fresh_ash.astype(np.float32),
                 aquifer.astype(np.float32), spring & river)


# ----------------------------------------------------------------- settings at work

def _rng(seed: int, salt: int) -> random.Random:
    return random.Random((seed * 1_000_003 + salt) & 0xFFFFFFFFFFFF)


def components(mask: np.ndarray) -> np.ndarray:
    """Each connected patch of `mask` numbered from 1 (8-way), 0 outside it."""
    label = np.zeros(mask.shape, np.int32)
    w, h = mask.shape
    n = 0
    for sx, sy in zip(*np.nonzero(mask)):
        if label[sx, sy]:
            continue
        n += 1
        label[sx, sy] = n
        stack = [(int(sx), int(sy))]
        while stack:
            x, y = stack.pop()
            for dx, dy in DIRS:
                nx, ny = x + dx, y + dy
                if 0 <= nx < w and 0 <= ny < h and mask[nx, ny] and not label[nx, ny]:
                    label[nx, ny] = n
                    stack.append((nx, ny))
    return label


def islands(seed: int, elevation: np.ndarray, amount: int) -> np.ndarray:
    """The Islands setting: 0 and 1 sink small islands, 2 leaves the land as it is, 3 and 4
    raise new ones out at sea."""
    if amount == 2:
        return elevation
    e = elevation.copy()
    if amount < 2:
        label = components(e > 0)
        sizes = np.bincount(label.ravel())
        small = sizes < SMALL_ISLAND[amount]
        small[0] = False
        sink = small[label]
        e[sink] = -30.0
        return e
    w, h = e.shape
    z = noise_field(_rng(seed, 31), w, h, 1 / 9, 3)
    z = z / max(float(z.std()), 1e-6)
    x = np.minimum(np.arange(w), w - 1 - np.arange(w))[:, None]
    y = np.minimum(np.arange(h), h - 1 - np.arange(h))[None, :]
    inland = np.minimum(x, y * 2) >= 10
    rise = (z - ISLAND_AT[amount]) * 600 + 4
    new = (e <= 0) & inland & (rise > 0)
    e[new] = rise[new]
    return e.astype(np.float32)


def hollows(seed: int, elevation: np.ndarray, count: int) -> np.ndarray:
    """Basins dug out of the land for the Lakes setting to fill."""
    if not count:
        return elevation
    rng = _rng(seed, 53)
    e = elevation.copy()
    w, h = e.shape
    inland = ~neighbours_any(neighbours_any(neighbours_any(e <= 0))) & (e > 40) & (e < 1800)
    cells = np.argwhere(inland)
    if not len(cells):
        return e
    xs = np.arange(w, dtype=np.float32)[:, None]
    ys = np.arange(h, dtype=np.float32)[None, :]
    for k in rng.sample(range(len(cells)), min(count, len(cells))):
        cx, cy = (int(c) for c in cells[k])
        r, depth = rng.uniform(1.2, 2.6), rng.uniform(40, 90)
        d = np.sqrt((xs - cx) ** 2 + ((ys - cy) * 2) ** 2) / r
        bowl = np.clip(1 - d, 0, 1) * depth
        e = np.where(e > 0, np.maximum(e - bowl, 1.0), e)
    return e.astype(np.float32)


def groundwater(seed: int, elevation: np.ndarray, amount: float) -> np.ndarray:
    """0..1: how near the surface water lies under each cell (porous rock holds it; lowlands
    have more), for the Aquifers setting."""
    if amount <= 0:
        return np.zeros(elevation.shape, np.float32)
    w, h = elevation.shape
    porous = (noise_field(_rng(seed, 41), w, h, 1 / 30, 3) + 0.5)
    low = np.clip(1 - np.maximum(elevation, 0) / 2200, 0, 1)
    return np.clip(porous * low * amount, 0, 1).astype(np.float32) * (elevation > 0)


def springs(seed: int, elevation: np.ndarray, aquifer: np.ndarray, water: np.ndarray, most: int) -> np.ndarray:
    """Where groundwater comes out: at the foot of high ground over a full aquifer."""
    out = np.zeros(elevation.shape, bool)
    if most <= 0:
        return out
    w, h = elevation.shape
    p = np.pad(elevation, 1, mode="edge")
    highest = np.max([p[1 + dx: w + 1 + dx, 1 + dy: h + 1 + dy] for dx, dy in DIRS], axis=0)
    foot = (highest - elevation > 120) & (elevation > 30) & ~water & ~neighbours_any(water)
    score = np.where(foot, aquifer, 0)
    cells = np.argwhere(score > 0.45)
    if not len(cells):
        return out
    rng = _rng(seed, 67)
    order = sorted(range(len(cells)), key=lambda i: -score[tuple(cells[i])] * rng.random())
    for i in order:
        x, y = (int(c) for c in cells[i])
        if out[max(0, x - 6): x + 7, max(0, y - 3): y + 4].any():
            continue
        out[x, y] = True
        if out.sum() >= most:
            break
    return out


def downstream(start: np.ndarray, flow_dx: np.ndarray, flow_dy: np.ndarray, stop: np.ndarray) -> np.ndarray:
    """Every cell the water from `start` runs through, until it reaches `stop`."""
    out = np.zeros(start.shape, bool)
    w, h = start.shape
    for x, y in zip(*np.nonzero(start)):
        x, y = int(x), int(y)
        for _ in range(w + h):
            out[x, y] = True
            dx, dy = int(flow_dx[x, y]), int(flow_dy[x, y])
            x, y = x + dx, y + dy
            if (not dx and not dy) or not (0 <= x < w and 0 <= y < h) or stop[x, y] or out[x, y]:
                break
    return out


def shift_sea(elevation: np.ndarray, rise: float) -> np.ndarray:
    """The sea `rise` metres higher (or lower, if negative): coasts drown or the shelf comes up
    dry. The very edge of the map stays sea."""
    e = elevation - np.float32(rise)
    border = np.ones(e.shape, bool)
    border[2:-2, 2:-2] = False
    e[border] = np.minimum(e[border], -20.0)
    return e.astype(np.float32)
