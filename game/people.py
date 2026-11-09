"""The people of a settlement and their animals, and their day.

Each settlement is populated when its map is built:

- towns:    a baker, a butcher, an innkeeper, farmers for the gardens, and a fisherman and a
            lumberjack if there's water to fish and woods to cut
- villages: farmers for the fields, and a fisherman and a lumberjack in the same way
- inns:     an innkeeper
- animals:  a herd in each pasture (what suits the land, see farming.py), and hens about
            the houses

Everyone lives in a house (the innkeeper at the inn) and keeps hours:

    job          works        then
    baker        04:00-13:00  the evening at the inn (or on the green), bed at 21:00
    fisherman    05:00-15:00
    farmer       06:00-18:00
    lumberjack   07:00-17:00
    butcher      07:00-16:00
    innkeeper    09:00-24:00  behind the bar; sleeps at the inn

They walk where they're going a tile at a time as the clock runs, a little under a minute a
tile, wander about while they work, and step round each other and you. If you've been away a
while (or rested), everyone is simply where they'd be by now. Animals amble about their
pasture; hens peck about the houses.

Walk into someone and you talk (the first time, they say who they are), and you step past
each other. Walk into an animal and you push past it.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

import numpy as np
import tcod

from . import tiles as T
from .climate import hour_of_day
from .farming import ANIMALS, STAGE_WORDS

PERSON = "☺"
WALK_MINUTES = 0.8            # a tile, for people
SNAP_MINUTES = 30             # away longer than this, and everyone is just where they'd be
MOST_STEPS = 60               # steps anyone takes in one go
BEDTIME = 21


@dataclass(frozen=True)
class Job:
    colour: tuple
    start: int                # hours of work
    end: int
    doing: str                # what they're doing at work
    lines: tuple              # things they say


JOBS = {
    "farmer": Job((150, 195, 95), 6, 18, "working the {crop}",
                  ("The {crop} could do with a dry week.", "Up before the sun, every day.",
                   "Mind the gate, or the {herd} get out.", "Good soil here. Stony, but good.")),
    "fisherman": Job((100, 160, 230), 5, 15, "fishing",
                     ("Good catch this morning.", "Nets need mending again.",
                      "The fish know when it's going to rain.", "Water's choppy today.")),
    "lumberjack": Job((205, 115, 75), 7, 17, "chopping wood",
                      ("Mind the stumps.", "Good straight timber out here.",
                       "Every hearth in {town} burns my wood.", "Stand clear when one comes down!")),
    "butcher": Job((215, 85, 85), 7, 16, "cutting meat",
                   ("Best cuts in {town}.", "Fresh today. Mostly.", "Mind the hooks.",
                    "Bring me a {herd} and I'll make it worth your while.")),
    "baker": Job((240, 225, 175), 4, 13, "baking bread",
                 ("Bread's fresh out of the oven.", "Been up since four.",
                  "Flour gets everywhere. Everywhere.", "Nothing like the smell of the ovens at dawn.")),
    "innkeeper": Job((240, 190, 80), 9, 24, "serving at the bar",
                     ("Welcome to {inn}! Warm fire, soft beds.", "What'll it be?",
                      "Travellers bring the best stories.", "Wipe your boots, please.")),
}
EVENING = {"inn": "at {inn}", "green": "chatting on the green"}
FIRST = ["Alder", "Bryn", "Cora", "Dale", "Edda", "Finn", "Greta", "Hal", "Ida", "Jory", "Kit", "Lena",
         "Milo", "Nell", "Oren", "Pia", "Quin", "Rhea", "Sol", "Tamsin", "Ulf", "Vera", "Wyn", "Yara",
         "Bram", "Elin", "Garth", "Maud", "Rowan", "Signe"]
FAMILY = ["Ashdown", "Brook", "Carrow", "Dunmore", "Ellery", "Fenwick", "Garrow", "Hollis", "Ivers",
          "Kemp", "Lowell", "Marsh", "Northey", "Penhale", "Redfern", "Stoner", "Tolley", "Underhill",
          "Vane", "Whitlow", "Yeardley"]


@dataclass
class Actor:
    kind: str                       # a job, or an animal ("sheep", "hen" ...)
    name: str
    x: int
    y: int
    home: list = field(default_factory=list)       # where they sleep
    work: list = field(default_factory=list)       # where they work (or graze)
    evening: list = field(default_factory=list)    # where they spend the evening
    evening_kind: str = "green"
    goal: tuple | None = None
    path: list = field(default_factory=list)
    budget: float = 0.0
    stuck: int = 0
    doing: str = ""
    met: bool = False

    @property
    def animal(self) -> bool:
        return self.kind in ANIMALS

    @property
    def char(self) -> str:
        return ANIMALS[self.kind].char if self.animal else PERSON

    @property
    def colour(self) -> tuple:
        return ANIMALS[self.kind].colour if self.animal else JOBS[self.kind].colour

    @property
    def title(self) -> str:
        return f"A {self.kind}" if self.animal else f"{self.name}, the {self.kind}"


# ----------------------------------------------------------------- populating a settlement

def populate(level, site, rng: random.Random) -> None:
    """The people who live and work here, and their animals."""
    t = level.tiles
    buildings = {b.kind: b for b in level.buildings if b.kind in ("inn", "bakery", "butcher")}
    houses = [b for b in level.buildings if b.kind == "house"]
    rng.shuffle(houses)
    fields_ = [p for p in level.places if p.kind == "field"]
    water = [p for p in level.places if p.kind in ("pier", "shore")]
    camp = next((p for p in level.places if p.kind == "camp"), None)
    inn = buildings.get("inn")
    if site.kind == "town":
        jobs = ["baker", "butcher", "innkeeper"] + ["farmer"] * min(2, len(fields_))
    elif site.kind == "village":
        jobs = ["farmer"] * min(3, max(1, len(fields_) - 1))
    else:
        jobs = ["innkeeper"]
    if site.kind in ("town", "village"):
        jobs += ["fisherman"] * bool(water) + ["lumberjack"] * bool(camp)
    green = settle_green(level)
    evening, evening_kind = (inn.floor(t), "inn") if inn else (green, "green")
    used_names = set()
    for i, job in enumerate(jobs):
        name = person_name(rng, used_names)
        if job == "innkeeper":
            if inn is None:
                continue
            home = [c for c in inn.floor(t) if t[c] == T.BED][:1] or inn.floor(t)
        elif houses:
            house = houses.pop()
            house.name = f"the {name.split()[1]} house"
            home = [c for c in house.floor(t) if t[c] == T.BED] or house.floor(t)
        else:
            home = green
        work = workplace(level, job, i, fields_, water, camp, buildings)
        if not work or not home:
            continue
        x, y = work[0]
        level.actors.append(Actor(job, name, x, y, home=home, work=work, evening=evening or green,
                                  evening_kind=evening_kind if evening else "green"))
    for place in (p for p in level.places if p.kind == "pasture"):
        for _ in range(rng.randint(3, 6) if place.animal != "horse" else 2):
            x, y = rng.choice(place.tiles)
            level.actors.append(Actor(place.animal, place.animal, x, y, work=place.tiles))
    if site.kind in ("town", "village") and green:
        yard = settle_yard(level)
        for _ in range(rng.randint(3, 5)):
            x, y = rng.choice(yard)
            level.actors.append(Actor("hen", "hen", x, y, work=yard))


def person_name(rng: random.Random, used: set) -> str:
    for _ in range(50):
        name = f"{rng.choice(FIRST)} {rng.choice(FAMILY)}"
        if name not in used:
            break
    used.add(name)
    return name


def workplace(level, job: str, i: int, fields_, water, camp, buildings) -> list:
    t = level.tiles
    if job == "farmer":
        return fields_[i % len(fields_)].tiles if fields_ else []
    if job == "fisherman":
        return water[0].tiles if water else []
    if job == "lumberjack":
        return camp.tiles if camp else []
    kind = {"baker": "bakery", "butcher": "butcher", "innkeeper": "inn"}[job]
    b = buildings.get(kind)
    if b is None:
        return []
    floor = b.floor(t)
    near_counter = [c for c in floor if any(t[c[0] + dx, c[1] + dy] in (T.COUNTER, T.OVEN)
                                            for dx in (-1, 0, 1) for dy in (-1, 0, 1))]
    return near_counter or floor


def settle_green(level) -> list:
    """Open ground about the middle: the square, or the village green."""
    t = level.tiles
    cx, cy = level.width // 2, level.height // 2
    return [(x, y) for x in range(cx - 8, cx + 9) for y in range(cy - 4, cy + 5)
            if level.in_bounds(x, y) and T.WALK[t[x, y]] and not T.WATERY[t[x, y]] and not T.ROOF[t[x, y]]
            and (x - cx) ** 2 + (2 * (y - cy)) ** 2 <= 64]


def settle_yard(level) -> list:
    """Where hens peck about: open ground among the houses."""
    t = level.tiles
    cx, cy = level.width // 2, level.height // 2
    return [(x, y) for x in range(cx - 18, cx + 19) for y in range(cy - 9, cy + 10)
            if level.in_bounds(x, y) and T.WALK[t[x, y]] and not T.WATERY[t[x, y]] and not T.ROOF[t[x, y]]
            and t[x, y] not in T.FIELDS and (x - cx) ** 2 + (2 * (y - cy)) ** 2 <= 18 ** 2]


# ----------------------------------------------------------------- the day

def plan(a: Actor, hour: float, names: dict) -> tuple[list, str]:
    """(where they should be, what they're doing) at this hour."""
    if a.animal:
        if a.kind == "hen":
            return a.work, "pecking about" if 6 <= hour < 20 else "roosting"
        return a.work, "grazing" if 6 <= hour < 20 else "resting"
    job = JOBS[a.kind]
    if job.start <= hour < job.end:
        return a.work, job.doing.format(**names)
    if a.kind == "innkeeper":
        return a.home, "asleep"
    if hour >= job.end and hour < BEDTIME:
        return a.evening, EVENING[a.evening_kind].format(**names)
    return a.home, "asleep" if hour >= BEDTIME + 1 or hour < job.start - 1 else "at home"


def names_for(level, engine) -> dict:
    inn = next((b.name for b in level.buildings if b.kind == "inn"), "the inn")
    herd = next((p.animal for p in level.places if p.kind == "pasture"), "sheep")
    crop = T.TILES[level.crop].name if level.crop is not None else "vegetables"
    return {"inn": inn, "town": level.name, "crop": crop, "herd": ANIMALS[herd].plural}


def walk_costs(level) -> np.ndarray:
    """What each tile costs people to walk; 0 where they won't (deep water, walls)."""
    if getattr(level, "_walk_costs", None) is None:
        t = level.tiles
        cost = np.round(T.MINUTES[t] * 10).astype(np.int32)
        cost[~T.WALK[t]] = 0
        cost[t == T.WATER] = 60          # they'd rather not wade
        level._walk_costs = cost
    return level._walk_costs


def find_path(level, start, goal) -> list:
    cost = walk_costs(level).copy()
    if not cost[goal]:
        return []
    cost[start] = max(1, int(cost[start]))
    finder = tcod.path.Pathfinder(tcod.path.SimpleGraph(cost=cost, cardinal=2, diagonal=3))
    finder.add_root(start)
    return [tuple(p) for p in finder.path_to(goal).tolist()[1:]]


def advance(level, minutes: float, engine, rng: random.Random | None = None) -> None:
    """Moves everyone on to the clock at `minutes`."""
    if not level.actors:
        level.sim_minutes = minutes
        return
    rng = rng or random.Random(int(minutes) * 7919 + hash(level.key))
    hour = float(hour_of_day(minutes))
    names = names_for(level, engine)
    you = (engine.lx, engine.ly) if engine.level is level else None
    if level.sim_minutes is None or minutes - level.sim_minutes > SNAP_MINUTES or minutes < level.sim_minutes:
        snap(level, hour, names, rng, you)
    else:
        elapsed = minutes - level.sim_minutes
        taken = {(a.x, a.y) for a in level.actors}
        if you:
            taken.add(you)
        for a in level.actors:
            area, a.doing = plan(a, hour, names)
            a.budget = min(a.budget + elapsed, MOST_STEPS * pace(a))
            while a.budget >= pace(a):
                a.budget -= pace(a)
                step(level, a, area, taken, rng)
    level.sim_minutes = minutes


def pace(a: Actor) -> float:
    return ANIMALS[a.kind].minutes if a.animal else WALK_MINUTES


def snap(level, hour: float, names: dict, rng: random.Random, you) -> None:
    """Everyone where they'd be by now."""
    taken = {you} if you else set()
    for a in level.actors:
        area, a.doing = plan(a, hour, names)
        free = [c for c in area if c not in taken] or area
        a.x, a.y = rng.choice(free)
        taken.add((a.x, a.y))
        a.goal, a.path, a.budget, a.stuck = None, [], 0.0, 0


def step(level, a: Actor, area: list, taken: set, rng: random.Random) -> None:
    here = (a.x, a.y)
    if a.animal:                         # amble to a neighbouring spot, or stand
        if rng.random() < 0.55:
            return
        options = [c for c in ((a.x + dx, a.y + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1))
                   if c != here and c in area_set(a, area) and c not in taken]
        if here not in area_set(a, area) and area:      # wandered off somehow: head back
            options = [min(area, key=lambda c: abs(c[0] - a.x) + abs(c[1] - a.y))]
        if options:
            move(a, rng.choice(options), taken)
        return
    inside = here in area_set(a, area)
    if a.goal is None or a.goal not in area_set(a, area):
        a.goal, a.path = pick_goal(level, a, area, rng), []
    if here == a.goal:
        if a.doing == "asleep" or rng.random() < 0.85 or not inside:
            return                       # stay put a while
        a.goal, a.path = pick_goal(level, a, area, rng), []
        return
    if not a.path or a.path[-1] != a.goal:
        a.path = find_path(level, here, a.goal)
        if not a.path:
            a.goal = None
            return
    nxt = a.path[0]
    if nxt in taken:
        a.stuck += 1
        if a.stuck > 3:
            a.goal, a.path, a.stuck = None, [], 0
        return
    a.path.pop(0)
    move(a, nxt, taken)


def area_set(a: Actor, area: list) -> set:
    key = id(area)
    cache = getattr(a, "_areas", None)
    if cache is None:
        cache = a._areas = {}
    if key not in cache:
        cache[key] = set(area)
    return cache[key]


def pick_goal(level, a: Actor, area: list, rng: random.Random):
    if not area:
        return None
    if area is a.home:
        beds = [c for c in area if level.tiles[c] == T.BED]
        if beds:
            return beds[0]
    return rng.choice(area)


def move(a: Actor, to: tuple, taken: set) -> None:
    taken.discard((a.x, a.y))
    a.x, a.y = to
    taken.add(to)
    a.stuck = 0


# ----------------------------------------------------------------- meeting them

def actor_at(level, x: int, y: int) -> Actor | None:
    return next((a for a in level.actors if (a.x, a.y) == (x, y)), None)


def talk(a: Actor, level, engine, rng: random.Random | None = None) -> str:
    """What happens when you walk into someone (or something)."""
    rng = rng or random.Random()
    if a.animal:
        info = ANIMALS[a.kind]
        return f"You push past the {a.kind}. It {info.sound}."
    if a.doing == "asleep":
        return f"{a.name} is fast asleep."
    names = names_for(level, engine)
    line = rng.choice(JOBS[a.kind].lines).format(**names)
    if not a.met:
        a.met = True
        return f'{a.name}, the {a.kind}: "Hello! I\'m {a.name.split()[0]}. {line}"'
    return f'{a.name.split()[0]}: "{line}"'


def describe(a: Actor) -> list[str]:
    lines = [a.title]
    if a.doing:
        lines.append(a.doing.capitalize())
    return lines


def crop_words(stage: str) -> str:
    return STAGE_WORDS.get(stage, stage)
