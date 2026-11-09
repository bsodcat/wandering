"""The overworld: terrain, climate, water, biomes, settlements and roads, all from one seed.

Every array is indexed [x, y]. One world cell is a region a few kilometres across. Later each
region is expanded into its own local map (a chunk), seeded with World.region_seed(x, y), so
the same place always comes out the same. Rivers keep their flow direction (flow_dx/flow_dy)
and every road step is kept as an edge (road_edges), so a chunk knows where roads enter and leave.

The steps, in order:
  1. elevation   noise continents with ridged mountain ranges, sea all round the edge
  2. temperature warm at the equator (the middle row), cold at the poles and up high
  3. moisture    wet near coasts and in the rain belts, dry in the horse latitudes
  4. drainage    fill basins (they become lakes), route every cell downhill to the sea
                 and add up the rain that flows through it; the big flows are rivers
  5. biomes      from altitude, temperature and moisture
  6. people      towns where farmland, a mild climate and water meet; highways joining them
                 (a spanning tree by walking time, plus short cuts); villages near the roads
                 with tracks out to them; inns along long highways; watchtowers on high
                 ground over the roads; ruins and caves out in the wilds
"""
from __future__ import annotations

import heapq
import random
from dataclasses import dataclass, field

import numpy as np
import tcod

from . import biomes as B

WORLD_W, WORLD_H = 256, 128
LAND_SHARE = 0.42        # of the map above sea level
MAX_ALTITUDE = 4800.0    # metres, the highest peak
MAX_DEPTH = 5000.0       # metres, the deepest sea
LAPSE_RATE = 6.5         # degrees C lost per 1000 m of height
RIVER_SHARE = 0.035      # of land cells that carry a river
LAKE_DEPTH = 20.0        # metres a basin must be filled by to count as a lake

DIRS = [(dx, dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if dx or dy]

SITE_KINDS = {  # kind: (char, colour, how many at most, closest to another of its kind)
    "town": ("■", (255, 220, 110), 12, 16),
    "village": ("⌂", (230, 190, 120), 28, 6),
    "inn": ("≡", (240, 170, 90), 14, 12),
    "tower": ("↑", (200, 200, 215), 10, 16),
    "ruins": ("π", (170, 160, 150), 22, 6),
    "cave": ("Ω", (200, 170, 140), 16, 6),
}
SETTLED = ("town", "village", "inn")   # people live there: you can rest indoors


@dataclass
class Site:
    kind: str
    name: str
    x: int
    y: int
    port: bool = False   # on the sea: it has docks

    @property
    def settled(self) -> bool:
        return self.kind in SETTLED


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

    def __post_init__(self):
        self.site_at = {(s.x, s.y): s for s in self.sites}

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

def make_elevation(rng: random.Random, w: int, h: int) -> np.ndarray:
    base = noise_field(rng, w, h, 1 / 64, 6)
    ridges = 1 - np.abs(noise_field(rng, w, h, 1 / 40, 4))     # sharp crests along the zero lines
    ranges = np.clip(noise_field(rng, w, h, 1 / 90, 2) * 2, 0, 1)  # where mountain ranges are allowed
    x = np.minimum(np.arange(w), w - 1 - np.arange(w))[:, None] / (w * 0.12)
    y = np.minimum(np.arange(h), h - 1 - np.arange(h))[None, :] / (h * 0.14)
    edge = np.clip(np.minimum(x, y), 0, 1)                      # 0 at the border, 1 inland
    e = base + ridges ** 3 * ranges * 0.9 - (1 - edge) ** 2 * 1.2
    sea = np.quantile(e, 1 - LAND_SHARE)
    e = e - sea
    land = e > 0
    e[land] = (e[land] / e[land].max()) ** 1.4 * MAX_ALTITUDE   # flatter lowlands, steep peaks
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
        (coast & (alt < 40) & (t > 3), B.BEACH),
        ((t < 6) & (m > 0.42), B.TAIGA),
        (t < 6, B.STEPPE),
        ((m > 0.78) & (alt < 350) & (t > 4), B.SWAMP),
        ((t > 17) & (m < 0.27), B.DESERT),
        ((t > 20) & (m < 0.5), B.SAVANNA),
        (t > 20, B.JUNGLE),
        (m < 0.22, B.SHRUBLAND),
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
VILLAGE_TRACK = 30           # regions a village will lay a track to reach the network
FARMLAND = [B.GRASSLAND, B.FOREST, B.STEPPE, B.SHRUBLAND, B.SAVANNA, B.BEACH, B.TAIGA]
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

    def __init__(self, rng: random.Random, arrays: dict):
        self.rng = rng
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

    def free(self, x: int, y: int, kind: str, spacing: int) -> bool:
        return all(max(abs(s.x - x), abs(s.y - y)) >= (spacing if s.kind == kind else 4) for s in self.sites)

    def add(self, kind: str, x: int, y: int) -> Site:
        base = make_name(self.rng, self.names)
        name = {"ruins": f"Ruins of {base}", "cave": f"{base} Cave", "tower": f"{base} Tower",
                "inn": self.rng.choice(INN_NAMES).format(self.rng.choice(INN_WORDS))}.get(kind, base)
        port = kind in ("town", "village") and bool(self.ocean[max(0, x - 1): x + 2, max(0, y - 1): y + 2].any())
        site = Site(kind, name, int(x), int(y), port)
        self.sites.append(site)
        return site

    def place(self, kind: str, score: np.ndarray) -> list[Site]:
        _, _, most, spacing = SITE_KINDS[kind]
        placed = []
        h = score.shape[1]
        for flat in np.argsort(score, axis=None, kind="stable")[::-1]:
            if len(placed) >= most:
                break
            x, y = divmod(int(flat), h)
            if score[x, y] <= 0:
                break
            if self.free(x, y, kind, spacing):
                placed.append(self.add(kind, x, y))
        return placed

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


def plan_people(rng: random.Random, arrays: dict) -> tuple[list[Site], np.ndarray, dict]:
    P = Planner(rng, arrays)
    biome, t, river = P.biome, P.temperature, P.river
    land = B.TRAVEL[biome] > 0
    farmland = np.isin(biome, FARMLAND)
    near_water = neighbours_any(river | np.isin(biome, B.WATER))
    good_climate = 1 - np.clip(np.abs(t - 15) / 15, 0, 1)
    j = P.jitter

    towns = P.place("town", farmland * (good_climate * 2 + near_water * 1.5 + river * 0.5 + j * 0.8)
                    * (P.elevation < 900))
    highways = P.highways(towns)

    near_road = dilate(P.road, 3)
    for v in P.place("village", farmland * (good_climate + near_water + near_road * 1.5 + j * 1.5)):
        P.spur(v, VILLAGE_TRACK)

    for path in highways:   # an inn every so often along the long highways
        for k in range(INN_SPACING // 2, len(path) - INN_SPACING // 2, INN_SPACING):
            x, y = (int(c) for c in path[k])
            if not river[x, y] and P.free(x, y, "inn", INN_SPACING // 2) and \
                    sum(s.kind == "inn" for s in P.sites) < SITE_KINDS["inn"][2]:
                P.add("inn", x, y)

    overlook = np.isin(biome, HIGH_GROUND) & dilate(P.road, 3) & ~P.road & ~river
    for tower in P.place("tower", overlook * (P.elevation / 1000 + j)):
        P.spur(tower, 6)

    P.place("ruins", land * (biome != B.GLACIER) * (j + 0.2 + near_road * 0.3) * ~P.road)
    edge_of_high = np.isin(biome, HIGH_GROUND) & neighbours_any(~np.isin(biome, HIGH_GROUND + [B.PEAKS]))
    P.place("cave", edge_of_high * (j + 0.2) * ~P.road)
    for s in P.sites:
        P.road[s.x, s.y] = False  # the site itself is drawn, not a road
    return P.sites, P.road, P.edges


# ----------------------------------------------------------------- the whole thing

def generate(seed: int, width: int = WORLD_W, height: int = WORLD_H) -> World:
    rng = random.Random(seed)
    elevation = make_elevation(rng, width, height)
    temperature = make_temperature(rng, elevation)
    moisture = make_moisture(rng, elevation)
    land = elevation > 0
    filled, flow_dx, flow_dy, flow = drain(elevation, moisture * land)
    lake = land & (filled - elevation > LAKE_DEPTH)
    river = land & ~lake & (flow > np.quantile(flow[land], 1 - RIVER_SHARE))
    moisture = np.clip(moisture + blur((river | lake).astype(np.float32), 2) * 0.35, 0, 1)
    biome = classify(elevation, temperature, moisture, lake)
    river &= B.TRAVEL[biome] > 0
    river_width = np.zeros(river.shape, np.uint8)
    if river.any():
        q = np.quantile(flow[river], [0.6, 0.9])
        river_width[river] = 1 + (flow[river] > q[0]) + (flow[river] > q[1])
    arrays = dict(elevation=elevation, temperature=temperature, moisture=moisture, biome=biome, river=river)
    sites, road, road_edges = plan_people(rng, arrays)
    return World(seed, elevation, temperature, moisture, biome, river, flow, flow_dx, flow_dy, road,
                 sites, road_edges, river_width)
