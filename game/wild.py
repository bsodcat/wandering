"""Wild creatures: wolves, the small game they hunt, bats, and goblins.

They live on a level beside its people (`Level.creatures`) and move as the clock runs, a
quarter of a minute at a time, each when its last action is done. Away from a level for long
(or resting through it), and everything simply settles where it would be (`settle`).

Small game (rabbits, squirrels and birds in the open, rats in caves) nibbles about its patch,
leaving a scent on every tile it passes, and runs from anything that hunts it. Squirrels run up
the nearest tree; birds fly over anything in the way.

Wolves keep a territory in the forest and the wilds, and in caves, mostly in packs of two to
five (now and then one alone):
- The pack roams its territory behind its leader, along the trails it has worn before.
- Hungry, they hunt: following the freshest scent, then stalking what they find, slowly and
  low, until they're close enough to rush it (CHARGE). Not hungry, they leave things be.
- They only go for you if they're very hungry and there are at least two of them, or you've
  hurt one of them.
- They flee if hurt (and a hurt wolf goes slowly), if they're outnumbered (a wanderer with a
  real weapon and armour counts as two), or if one is alone.
- A trail gone cold, they lose interest and go back to their territory.
- A wolf's bite can, very rarely, give you wolf fever (game/sickness.py).

Bats roost in clusters deep in caves, asleep, until something comes near or makes a noise;
then they all wake, shrieking. They flit about over anything in the way, keeping away from
you, and settle back to sleep once it's quiet. Hurt one or corner one and the bats about it
swarm you together for a little while.

Goblins live in caves: guards at the way in (sleeping in shifts), patrols walking the
passages, and at their camp deep down (a fire, bedrolls, a pile of food and a barrel of
loot) a cook and hunters. They:
- hunt rats and bats, and carry them (and any carcass they find) back to the camp, where the
  cook roasts them over the fire; they eat when they're hungry
- sleep through the day on their bedrolls, waking if you come close or make a noise
- go to look at any noise they hear (a fight, bats shrieking, another goblin's alarm)
- shout the alarm when they see you, and fight, unless they're badly hurt or heavily
  outnumbered (two to one), when they run for it
- carry things you can take from them once they're dead
"""
from __future__ import annotations

import math
import random
import zlib
from dataclasses import dataclass, field

import numpy as np
import tcod

from . import biomes as B
from . import combat
from . import items
from . import sickness
from . import tiles as T
from .climate import hour_of_day

YOU = "you"
SLICE = 0.25           # minutes of the clock creatures act in, in turn
SNAP = 30              # away (or resting) longer than this, and everything settles
HUNGER_RATE = 1.5 / 60   # hunger a minute (from 0, fed, to 100, starving)
HUNT_HUNGER = 40       # wolves hunt small game past this
MAN_HUNGER = 70        # and you past this, if there are two or more of them
CHARGE = 3             # a stalking wolf rushes in from this close
STALK_PACE = 2.0       # stalking is slow, careful going
SCENT_FRESH = 240      # minutes a scent can still be followed
BORED = 50             # actions on a cold trail before a wolf gives up and goes home
INJURED = 0.5          # under this share of its health a wolf flees, and goes slowly
LIMP = 2.2             # how much slower a hurt wolf goes
GOBLIN_FLEE = 0.35     # under this share of its health a goblin runs
NEAR = 7               # tiles that count, sizing up a fight
ATTACK_MINUTES = 0.6
LONE_WOLF = 0.12       # chance a "pack" is one wolf alone
CAMP_FOOD = 4          # goblins hunt while their camp has less food than this
TRUNKS = {T.TREE, T.PINE, T.JUNGLE_TREE}


@dataclass(frozen=True)
class Beast:
    name: str
    plural: str
    char: str
    colour: tuple
    hp: int
    minutes: float          # a tile at a run, on easy ground
    bite: tuple             # damage
    to_hit: float
    dodge: float
    sense: int              # how far it notices things
    verb: str = "bites"
    flies: bool = False
    prey: bool = False      # small game: wolves and goblins hunt it
    meal: float = 0.0       # hunger eating one takes away


BEASTS = {
    "wolf": Beast("wolf", "wolves", "w", (175, 175, 185), 16, 0.32, (2, 5), 0.65, 0.15, 10),
    "rabbit": Beast("rabbit", "rabbits", "r", (205, 175, 135), 3, 0.28, (0, 1), 0.1, 0.35, 7, prey=True, meal=35),
    "squirrel": Beast("squirrel", "squirrels", "q", (195, 115, 60), 2, 0.3, (0, 1), 0.1, 0.4, 6, prey=True, meal=25),
    "bird": Beast("bird", "birds", "v", (150, 175, 215), 2, 0.2, (0, 1), 0.1, 0.45, 7, flies=True, prey=True, meal=20),
    "rat": Beast("rat", "rats", "r", (150, 130, 120), 3, 0.35, (1, 2), 0.4, 0.3, 6, prey=True, meal=25),
    "bat": Beast("bat", "bats", "b", (165, 125, 155), 4, 0.22, (1, 2), 0.55, 0.4, 6, flies=True, prey=True, meal=15),
    "goblin": Beast("goblin", "goblins", "g", (125, 195, 80), 14, 0.55, (2, 5), 0.6, 0.15, 9, verb="stabs", meal=0),
}
HOSTILE = ("wolf", "goblin", "bat")
ROLE_NAMES = {"guard": "goblin guard", "patrol": "goblin on patrol", "hunter": "goblin hunter", "cook": "goblin cook"}


@dataclass
class Creature:
    kind: str
    x: int
    y: int
    hp: float = 0.0
    home: tuple = (0, 0)              # the middle of its territory, its roost, its post or the camp
    reach: int = 20                   # how far it ranges from home
    pack: int = 0                     # wolves of a pack (and a cave's goblins) share this
    role: str = ""                    # goblins: guard, patrol, hunter, cook
    state: str = ""
    hunger: float = 30.0
    target: object = None             # a Creature, or YOU
    seen_at: tuple | None = None      # where it last saw (or heard) what it's after
    bored: int = 0
    budget: float = 0.0
    timer: float = 0.0
    carry: list = field(default_factory=list)   # item kinds
    route: list = field(default_factory=list)   # a patrol's waypoints
    leg: int = 0
    bed: tuple | None = None
    path: list = field(default_factory=list)
    goal: tuple | None = None
    asleep: bool = False
    sleep_hour: float = 8.0           # goblins: when they bed down, for eight hours
    provoked: float = -1e9            # the clock when you (or someone) last hurt it
    spotted: bool = False             # you can see it (for "You spot ...")

    def __post_init__(self):
        if not self.hp:
            self.hp = float(BEASTS[self.kind].hp)
        if not self.state:
            self.state = {"wolf": "roam", "bat": "roost", "goblin": "routine"}.get(self.kind, "graze")

    @property
    def beast(self) -> Beast:
        return BEASTS[self.kind]

    @property
    def char(self) -> str:
        return self.beast.char

    @property
    def colour(self) -> tuple:
        return self.beast.colour

    @property
    def name(self) -> str:
        return ROLE_NAMES.get(self.role, self.beast.name) if self.kind == "goblin" else self.beast.name


def dist(a, b) -> int:
    ax, ay = (a.x, a.y) if isinstance(a, Creature) else a
    bx, by = (b.x, b.y) if isinstance(b, Creature) else b
    return max(abs(ax - bx), abs(ay - by))


def a_name(name: str) -> str:
    return ("an " if name[0] in "aeiou" else "a ") + name


def creature_at(level, x: int, y: int) -> Creature | None:
    return next((c for c in level.creatures if (c.x, c.y) == (x, y)), None)


def clear_line(level, a, b) -> bool:
    """Nothing that blocks sight between a and b."""
    for x, y in tcod.los.bresenham(a, b).tolist()[1:-1]:
        if not T.SEE[level.tiles[x, y]]:
            return False
    return True


# ----------------------------------------------------------------- the clock

def advance(level, minutes: float, engine=None, rng: random.Random | None = None) -> None:
    """Moves every creature on a level on to the clock at `minutes`."""
    if not level.creatures and not level.wild_spec:
        level.wild_minutes = minutes
        return
    rng = rng or random.Random(int(minutes * 4) * 7919 + zlib.crc32(repr(level.key).encode()))
    last = level.wild_minutes
    w = Wilds(level, engine, rng, minutes if last is None else last)
    if last is None or minutes - last > SNAP or minutes < last:
        w.settle(minutes, None if last is None else minutes - last)
    else:
        w.run(minutes - last)
    level.wild_minutes = minutes
    level.noises = [n for n in level.noises if minutes - n[2] <= 2]


class Wilds:
    """One stretch of the clock on one level."""

    def __init__(self, level, engine, rng: random.Random, now: float):
        self.level, self.engine, self.rng, self.now = level, engine, rng, now
        here = engine is not None and engine.level is level and engine.player.alive
        self.you = (engine.lx, engine.ly) if here else None
        self.taken = {(c.x, c.y) for c in level.creatures} | {(a.x, a.y) for a in level.actors}
        if self.you:
            self.taken.add(self.you)

    # ------------------------------------------------------------- telling you

    def visible(self, pos) -> bool:
        e = self.engine
        return (e is not None and e.level is self.level and e.local_visible.shape == self.level.tiles.shape
                and bool(e.local_visible[pos]))

    def say(self, text: str, pos=None, stop: bool = False) -> None:
        if self.engine is None:
            return
        if pos is None or self.visible(pos):
            self.engine.say(text)
            if stop:
                self.engine.disturbed = True

    def noise(self, pos, reach: int) -> None:
        self.level.noises.append((pos[0], pos[1], self.now, reach))

    def heard(self, c) -> tuple | None:
        for x, y, when, reach in reversed(self.level.noises):
            if self.now - when <= 1.0 and dist(c, (x, y)) <= reach and (x, y) != (c.x, c.y):
                return (x, y)
        return None

    # ------------------------------------------------------------- running

    def run(self, elapsed: float) -> None:
        end = self.now + elapsed
        while self.now < end - 1e-9:
            dt = min(SLICE, end - self.now)
            self.now += dt
            for c in list(self.level.creatures):
                if c.hp <= 0 or (self.engine is not None and not self.engine.player.alive):
                    continue
                c.hunger = min(100.0, c.hunger + HUNGER_RATE * dt)
                c.budget = min(c.budget + dt, 5.0)
                tries = 0
                while c.budget > 0 and c.hp > 0 and tries < 6:
                    c.budget -= max(0.05, self.act(c))
                    tries += 1

    def act(self, c) -> float:
        if c.asleep:
            return self.sleeping(c)
        if c.kind == "wolf":
            return self.wolf(c)
        if c.kind == "bat":
            return self.bat(c)
        if c.kind == "goblin":
            return self.goblin(c)
        return self.small(c)

    # ------------------------------------------------------------- where things are

    def pos(self, t):
        return self.you if t == YOU else (t.x, t.y)

    def alive(self, t) -> bool:
        return self.you is not None if t == YOU else (t.hp > 0 and t in self.level.creatures)

    def sees(self, c, pos, reach: int | None = None) -> bool:
        return pos is not None and dist(c, pos) <= (reach or c.beast.sense) and clear_line(self.level, (c.x, c.y), pos)

    def can_stand(self, c, x: int, y: int) -> bool:
        level = self.level
        if not level.in_bounds(x, y) or (x, y) in self.taken or (x, y) in level.exits:
            return False
        t = int(level.tiles[x, y])
        if c.beast.flies:
            return bool(T.SEE[t])
        if c.kind == "squirrel" and t in TRUNKS:
            return True
        if not T.WALK[t] or t == T.DEEP_WATER:
            return False
        return abs(int(level.elev[x, y]) - int(level.elev[c.x, c.y])) <= 2

    def neighbours(self, c) -> list:
        return [(c.x + dx, c.y + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)
                if (dx or dy) and self.can_stand(c, c.x + dx, c.y + dy)]

    def move(self, c, to, pace: float = 1.0) -> float:
        self.taken.discard((c.x, c.y))
        c.x, c.y = to
        self.taken.add(to)
        level = self.level
        if c.beast.prey and not c.beast.flies:
            level.scent[to] = self.now
        if c.kind == "wolf":
            level.trail[to] = min(500, int(level.trail[to]) + 1)
        ground = 1.0 if c.beast.flies else float(T.MINUTES[level.tiles[to]]) / 0.6
        return c.beast.minutes * max(0.6, ground) * pace

    def step_toward(self, c, goal, pace: float = 1.0) -> float | None:
        """A step nearer the goal, round anything in the way. None if there's no way on."""
        if goal is None or (c.x, c.y) == tuple(goal):
            return None
        here = (c.x - goal[0]) ** 2 + (c.y - goal[1]) ** 2
        opts = self.neighbours(c)
        if opts:
            best = min(opts, key=lambda p: ((p[0] - goal[0]) ** 2 + (p[1] - goal[1]) ** 2, self.rng.random()))
            if (best[0] - goal[0]) ** 2 + (best[1] - goal[1]) ** 2 < here and \
                    (c.beast.flies or dist(c, goal) <= 6 or not c.path):
                c.path = []
                return self.move(c, best, pace)
        if c.beast.flies:
            return None
        if c.goal != tuple(goal) or not c.path:
            c.goal, c.path = tuple(goal), self.find_path(c, goal)
        if c.path and self.can_stand(c, *c.path[0]):
            return self.move(c, c.path.pop(0), pace)
        if c.path:                 # someone's in the way: wait, or think again
            c.path = [] if self.rng.random() < 0.3 else c.path
        return None

    def find_path(self, c, goal) -> list:
        from .people import walk_costs
        cost = walk_costs(self.level).copy()
        goal = tuple(goal)
        if not cost[goal]:
            cost[goal] = 10
        cost[c.x, c.y] = max(1, int(cost[c.x, c.y]))
        for (x, y) in self.level.exits:
            if (x, y) != goal:
                cost[x, y] = 0
        finder = tcod.path.Pathfinder(tcod.path.SimpleGraph(cost=cost, cardinal=2, diagonal=3))
        finder.add_root((c.x, c.y))
        path = [tuple(p) for p in finder.path_to(goal).tolist()[1:]]
        return path[:-1] if path and not T.WALK[self.level.tiles[goal]] else path

    def step_away(self, c, threats: list, pace: float = 1.0) -> float | None:
        opts = self.neighbours(c)
        if not opts:
            return None
        def safety(p):
            return min((p[0] - t[0]) ** 2 + (p[1] - t[1]) ** 2 for t in threats)
        best = max(opts, key=lambda p: (safety(p), self.rng.random()))
        if safety(best) < safety((c.x, c.y)):
            return None
        return self.move(c, best, pace)

    def wander(self, c, centre, reach: int, pace: float = 1.0, trails: bool = False) -> float:
        if dist(c, centre) > reach:
            return self.step_toward(c, centre, pace) or 1.0
        if c.goal is None or dist(c, c.goal) <= 1 or self.rng.random() < 0.02:
            c.goal, c.path = self.spot_near(centre, reach), []
        opts = self.neighbours(c)
        if not opts:
            return 1.0
        gx, gy = c.goal
        here = math.hypot(c.x - gx, c.y - gy)
        def score(p):
            s = math.hypot(p[0] - gx, p[1] - gy) - here + self.rng.random() * 0.9
            return s - (min(int(self.level.trail[p]), 40) * 0.04 if trails else 0)
        return self.move(c, min(opts, key=score), pace)

    def spot_near(self, centre, reach: int) -> tuple:
        level = self.level
        for _ in range(30):
            x = centre[0] + self.rng.randint(-reach, reach)
            y = centre[1] + self.rng.randint(-reach // 2 - 1, reach // 2 + 1)
            if level.walkable(x, y) and not T.WATERY[level.tiles[x, y]] and (x, y) not in level.exits:
                return (x, y)
        return tuple(centre)

    def threats_to(self, c) -> list:
        """(where, how much of a threat) for everything near that might hurt it."""
        out = []
        if self.you and dist(c, self.you) <= NEAR and (c.kind != "wolf" or self.sees(c, self.you, NEAR)):
            out.append((self.you, combat.threat(self.engine.player)))
        enemy = "goblin" if c.kind == "wolf" else "wolf" if c.kind == "goblin" else None
        for o in self.level.creatures:
            if o.kind == enemy and not o.asleep and o.hp > 0 and dist(c, o) <= NEAR:
                out.append(((o.x, o.y), 1.0))
        return out

    def strength(self, c) -> list:
        """Its own kind near it, awake and standing their ground (itself among them)."""
        return [o for o in self.level.creatures if o.kind == c.kind and o.pack == c.pack and not o.asleep
                and o.state != "flee" and o.hp > 0 and dist(c, o) <= NEAR]

    # ------------------------------------------------------------- blows

    def strike(self, c, target) -> float:
        b = c.beast
        if target == YOU:
            p = self.engine.player
            dmg, what = combat.blow_at_you(p, *b.bite, b.to_hit, self.rng)
            the = f"The {c.name}"
            if what == "miss":
                self.engine.say(f"{the} {'snaps at' if c.kind != 'goblin' else 'swings at'} you and misses.")
            elif what == "block":
                self.engine.say(f"You catch the {c.name}'s blow on your shield.")
            elif what == "glance":
                self.engine.say(f"{the}'s {'bite' if c.kind != 'goblin' else 'blade'} glances off your armour.")
            else:
                p.health -= dmg
                self.engine.say(f"{the} {b.verb} you! ({dmg})")
                if c.kind == "wolf":
                    sickness.bitten(p, self.now, self.rng)
                if p.health <= 0:
                    p.health, p.alive = 0.0, False
                    p.cause = f"were killed by {a_name(c.name)}"
                    self.engine.say(f"You {p.cause}.")
            self.engine.disturbed = True
            self.noise((c.x, c.y), 6)
            return ATTACK_MINUTES
        if self.rng.random() < b.to_hit - target.beast.dodge + 0.2:
            target.hp -= self.rng.randint(max(1, b.bite[0]), max(1, b.bite[1]))
            target.provoked = self.now
            if target.hp <= 0:
                self.kill(target, by=c)
        self.noise((c.x, c.y), 4)
        return ATTACK_MINUTES

    def kill(self, t, by=None) -> None:
        """`t` dies. A wolf eats what it kills; a goblin carries it off; otherwise the carcass
        (and whatever it carried) is left where it fell."""
        if t in self.level.creatures:
            self.level.creatures.remove(t)
        self.taken.discard((t.x, t.y))
        t.hp = 0
        carcass = f"{t.kind} carcass" if t.kind != "goblin" else None
        if by is not None and by.kind == "wolf" and t.beast.prey:
            by.state, by.timer = "eat", 12
            by.hunger = max(0.0, by.hunger - t.beast.meal)
            for o in self.level.creatures:
                if o.kind == "wolf" and o.pack == by.pack and o is not by and dist(o, by) <= 4:
                    o.hunger = max(0.0, o.hunger - t.beast.meal / 2)
            self.say(f"The wolf catches {a_name(t.name)} and wolfs it down.", (t.x, t.y))
            return
        if by is not None and by.kind == "goblin" and carcass:
            by.carry.append(carcass)
            self.say(f"The {by.name} kills {a_name(t.name)} and slings it over its shoulder.", (t.x, t.y))
            return
        if by is not None:
            self.say(f"The {by.name} kills {a_name(t.name)}.", (t.x, t.y))
        if carcass:
            items.drop(self.level, t.x, t.y, carcass)
        for kind in t.carry:
            items.drop(self.level, t.x, t.y, kind)
        if t.kind == "goblin" and self.rng.random() < 0.4:
            items.drop(self.level, t.x, t.y, "crude knife")

    # ------------------------------------------------------------- small game

    def small(self, c) -> float:
        b = c.beast
        if c.state == "up":                         # a squirrel up a tree
            c.timer -= 1
            if c.timer > 0:
                return 1.0
            if not self.dangers(c):
                c.state = "graze"
                opts = [p for p in self.neighbours(c) if self.level.tiles[p] not in TRUNKS]
                return self.move(c, self.rng.choice(opts)) if opts else 1.0
            c.timer = 5
            return 1.0
        danger = self.dangers(c)
        if danger:
            if c.kind == "squirrel":
                trees = [p for p in self.neighbours(c) if self.level.tiles[p] in TRUNKS]
                if trees:
                    c.state, c.timer = "up", 12
                    return self.move(c, trees[0], 0.7)
            c.state = "flee"
            return self.step_away(c, danger, 0.8) or 0.5
        c.state = "graze"
        if self.rng.random() < 0.6:
            return 1.5
        return self.wander(c, c.home, c.reach, 1.5)

    def dangers(self, c) -> list:
        """What it's noticed that might eat it. A stalking wolf isn't noticed till it's close."""
        out = []
        for o in self.level.creatures:
            if o.kind in ("wolf", "goblin") and not o.asleep and o.hp > 0:
                reach = 3 if o.state == "stalk" else 2 if o.role == "hunter" else c.beast.sense
                if dist(c, o) <= reach and self.sees(c, (o.x, o.y), reach):
                    out.append((o.x, o.y))
        if self.you and dist(c, self.you) <= c.beast.sense - 2 and self.sees(c, self.you):
            out.append(self.you)
        return out

    # ------------------------------------------------------------- wolves

    def pack_of(self, c) -> list:
        return [o for o in self.level.creatures if o.kind == "wolf" and o.pack == c.pack and o.hp > 0]

    def wolf(self, c) -> float:
        b = c.beast
        hurt = c.hp < INJURED * b.hp
        pace = LIMP if hurt else 1.0
        if c.state == "eat":
            c.timer -= 1
            if c.timer <= 0:
                c.state = "roam"
            return 1.0
        threats = self.threats_to(c)
        if threats:
            danger = sum(w for _, w in threats)
            stand = len(self.strength(c))
            alone = stand <= 1
            if hurt or alone or danger > stand or c.state == "flee":
                if c.state != "flee":
                    why = "limps away" if hurt else "slinks off" if alone else "turns and flees"
                    self.say(f"The wolf {why}.", (c.x, c.y))
                    c.timer = 25                           # and keeps running a while
                c.state, c.target = "flee", None
                spots = [p for p, _ in threats]
                cost = self.step_away(c, spots, pace)
                if cost is None:
                    near = next((p for p in spots if dist(c, p) <= 1), None)
                    if near is not None:                       # cornered: it bites
                        return self.strike(c, YOU if near == self.you else creature_at(self.level, *near))
                return cost or 1.0
        if c.state == "flee":
            c.timer -= 1
            if c.timer > 0:
                return self.step_toward(c, c.home, pace) or 1.0
            c.state = "return"
        target = self.wolf_target(c, hurt)
        if target is not None:
            tp = self.pos(target)
            c.target, c.seen_at, c.bored = target, tp, 0
            d = dist(c, tp)
            if d <= 1:
                return self.strike(c, target)
            if d <= CHARGE:
                if c.state != "charge" and target == YOU:
                    self.say("A wolf rushes at you!", (c.x, c.y), stop=True)
                c.state = "charge"
                return self.step_toward(c, tp, pace) or 0.5
            if c.state not in ("stalk", "charge") and target == YOU:
                self.say("A wolf is stalking you, low to the ground.", (c.x, c.y), stop=True)
            c.state = "stalk"
            return self.step_toward(c, tp, pace * STALK_PACE) or 0.5
        if c.state in ("stalk", "charge") and c.seen_at is not None:   # lost sight of it
            c.state = "track"
        if c.state == "track":
            c.bored += 1
            if c.bored > BORED:
                c.state, c.seen_at = "return", None
            elif c.seen_at is not None and dist(c, c.seen_at) > 1:
                cost = self.step_toward(c, c.seen_at, pace)
                if cost:
                    return cost
                c.seen_at = None
            else:
                c.seen_at = None
                nxt = self.sniff(c)
                if nxt is not None:
                    return self.move(c, nxt, pace * 1.2)
        elif c.hunger >= HUNT_HUNGER and c.state == "roam":
            nxt = self.sniff(c)
            if nxt is not None:
                c.state, c.bored = "track", 0
                return self.move(c, nxt, pace * 1.2)
        if c.state == "return":
            if dist(c, c.home) <= max(3, c.reach // 3):
                c.state, c.bored, c.target = "roam", 0, None
            else:
                return self.step_toward(c, c.home, pace * 1.3) or self.wander(c, c.home, c.reach, pace)
        return self.roam(c, pace)

    def wolf_target(self, c, hurt: bool):
        if hurt:
            return None
        b = c.beast
        found = []
        if c.hunger >= HUNT_HUNGER:
            for o in self.level.creatures:
                if o.beast.prey and o.state != "up" and dist(c, o) <= b.sense and self.sees(c, (o.x, o.y)):
                    found.append(o)
        if self.you and c.state != "return" and self.sees(c, self.you):
            provoked = self.now - c.provoked < 30
            if provoked or (c.hunger >= MAN_HUNGER and len(self.strength(c)) >= 2):
                found.append(YOU)
        return min(found, key=lambda t: dist(c, self.pos(t))) if found else None

    def sniff(self, c) -> tuple | None:
        """The neighbouring tile with the freshest scent, if it's fresher than here."""
        level = self.level
        best, when = None, max(float(level.scent[c.x, c.y]), self.now - SCENT_FRESH)
        for p in self.neighbours(c):
            if level.scent[p] > when:
                best, when = p, float(level.scent[p])
        return best

    def roam(self, c, pace: float) -> float:
        """The leader wanders the territory along the pack's old trails; the rest follow it."""
        pack = self.pack_of(c)
        leader = pack[0]
        if leader is not c and dist(c, leader) > 2:
            return self.step_toward(c, (leader.x, leader.y), pace * 1.5) or 1.0
        if leader is not c or self.rng.random() < 0.35:
            return 1.0                                   # lying up a while
        return self.wander(c, c.home, c.reach, pace * 2.0, trails=True)

    # ------------------------------------------------------------- bats

    def sleeping(self, c) -> float:
        if c.kind == "goblin":
            if not self.bedtime(c):
                c.asleep, c.state = False, "return"
                return 1.0
            woke = self.heard(c)
            if self.you and dist(c, self.you) <= 2 and self.rng.random() < 0.2:
                woke = self.you
            if woke is not None:
                c.asleep, c.state, c.seen_at, c.timer = False, "investigate", woke, 10
                self.say(f"The {c.name} wakes with a start!", (c.x, c.y), stop=True)
                return 1.0
            return 2.0
        if c.kind == "bat":
            close = self.you is not None and dist(c, self.you) <= 3 and self.sees(c, self.you)
            if close or self.heard(c):
                roost = [o for o in self.level.creatures if o.kind == "bat" and o.asleep and dist(o, c) <= 4]
                for o in roost:
                    o.asleep, o.state, o.bored = False, "flutter", 0
                self.noise((c.x, c.y), 7)
                self.say("Bats burst from the roof, shrieking!" if len(roost) > 1 else "A bat wakes, shrieking.",
                         (c.x, c.y), stop=True)
                return 0.5
            return 1.0
        c.asleep = False
        return 1.0

    def bat(self, c) -> float:
        you = self.you
        d = dist(c, you) if you else 99
        if c.state == "swarm":
            c.timer -= 1
            if c.timer <= 0 or you is None:
                c.state = "flutter"
            elif d <= 1:
                cost = self.strike(c, YOU)
                if self.rng.random() < 0.5:
                    cost += self.step_away(c, [you], 0.5) or 0
                return cost
            else:
                return self.step_toward(c, you) or 0.5
        cornered = you is not None and d <= 1 and not any(dist(p, you) > 1 for p in self.neighbours(c))
        if you is not None and (self.now - c.provoked < 3 or cornered):
            group = [o for o in self.level.creatures if o.kind == "bat" and not o.asleep and dist(o, c) <= 6]
            if len(group) >= 2:
                for o in group[:5]:
                    o.state, o.timer = "swarm", self.rng.randint(6, 12)
                self.say("The bats swarm at you!", (c.x, c.y), stop=True)
                return 0.5
        if you is not None and d <= 4:
            c.bored = 0
            return self.step_away(c, [you]) or self.flit(c)
        c.bored += 1
        if c.bored > 40:
            c.state = "home"
            if dist(c, c.home) <= 1:
                c.asleep, c.state = True, "roost"
                return 2.0
            return self.step_toward(c, c.home) or self.flit(c)
        return self.flit(c)

    def flit(self, c) -> float:
        opts = self.neighbours(c)
        if not opts or self.rng.random() < 0.3:
            return 1.0
        near_home = [p for p in opts if dist(p, c.home) <= 8] or opts
        return self.move(c, self.rng.choice(near_home))

    # ------------------------------------------------------------- goblins

    def bedtime(self, c) -> bool:
        hour = float(hour_of_day(self.now))
        return (hour - c.sleep_hour) % 24 < 8

    def station(self, c) -> tuple:
        """Where its work keeps it."""
        camp = self.level.camp
        if c.role == "guard":
            return c.home
        if c.role == "patrol" and c.route:
            return c.route[c.leg % len(c.route)]
        if c.role == "cook" and camp:
            return camp["store"]
        return camp.get("store", c.home) if camp else c.home

    def goblin(self, c) -> float:
        b = c.beast
        level = self.level
        here = level.items.get((c.x, c.y))
        if here and (c.x, c.y) != level.camp.get("store"):
            food = [k for k in here if k in items.CARCASSES or k in items.FOODS]
            for k in food:                                # gathers up food and carcasses
                here.remove(k)
                c.carry.append(k)
            if not here:
                del level.items[(c.x, c.y)]
        sees_you = self.you is not None and self.sees(c, self.you)
        if sees_you:
            if c.state not in ("fight", "flee"):
                self.say(f"The {c.name} spots you and shrieks the alarm!", (c.x, c.y), stop=True)
                self.noise((c.x, c.y), 12)
                c.state = "fight"
            c.target, c.seen_at = YOU, self.you
        if c.state in ("fight", "flee"):
            threats = self.threats_to(c)
            foes = sum(w for _, w in threats)
            allies = len(self.strength(c))
            if threats and (c.hp < GOBLIN_FLEE * b.hp or foes >= 2 * allies):
                if c.state != "flee":
                    self.say(f"The {c.name} turns and runs, yelling for help!", (c.x, c.y))
                    self.noise((c.x, c.y), 12)
                c.state = "flee"
                spots = [p for p, _ in threats]
                cost = self.step_away(c, spots)
                if cost is None and self.you and dist(c, self.you) <= 1:
                    return self.strike(c, YOU)             # cornered
                return cost or 1.0
            if c.state == "flee":
                c.state = "return"
            elif sees_you:
                if dist(c, self.you) <= 1:
                    return self.strike(c, YOU)
                return self.step_toward(c, self.you) or 1.0
            else:
                c.state, c.timer = "investigate", 10        # lost you: where were you last?
        heard = self.heard(c)
        if heard is not None and c.state in ("routine", "return"):
            c.state, c.seen_at, c.timer = "investigate", heard, 10
            self.say(f"The {c.name} cocks its head and creeps toward the noise.", (c.x, c.y))
        if c.state == "investigate":
            if c.seen_at is not None and dist(c, c.seen_at) > 1:
                cost = self.step_toward(c, c.seen_at)
                if cost:
                    return cost
            c.seen_at = None
            c.timer -= 1
            if c.timer <= 0:
                c.state = "return"
            return self.wander(c, (c.x, c.y), 3)
        if self.bedtime(c):
            bed = c.bed or self.station(c)
            if dist(c, bed) == 0 or self.step_toward(c, bed) is None:
                c.asleep, c.state = True, "routine"
                return 2.0
            return b.minutes * 1.5
        if c.state == "return":
            spot = self.station(c)
            if dist(c, spot) <= 1:
                c.state = "routine"
            else:
                return self.step_toward(c, spot) or self.wander(c, spot, 4)
        camp = level.camp
        if c.hunger > 60 and camp:
            store = camp["store"]
            pile = level.items.get(store, [])
            if "roast meat" in pile:
                if dist(c, store) <= 1:
                    pile.remove("roast meat")
                    c.hunger = max(0.0, c.hunger - 60)
                    self.say(f"The {c.name} tears into a piece of roast meat.", (c.x, c.y))
                    return 8.0
                return self.step_toward(c, store) or 1.0
        return getattr(self, f"goblin_{c.role or 'guard'}")(c)

    def goblin_guard(self, c) -> float:
        if dist(c, c.home) > 0:
            return self.step_toward(c, c.home) or 1.0
        return 2.0

    def goblin_patrol(self, c) -> float:
        if not c.route:
            return self.wander(c, c.home, 8)
        spot = c.route[c.leg % len(c.route)]
        if dist(c, spot) <= 1:
            c.leg += 1
            return 2.0
        cost = self.step_toward(c, spot)
        if cost is None:
            c.leg += 1
            return 1.0
        return cost

    def camp_food(self) -> int:
        camp = self.level.camp
        pile = self.level.items.get(camp["store"], []) if camp else []
        return sum(1 for k in pile if k in items.CARCASSES or k in items.FOODS)

    def goblin_hunter(self, c) -> float:
        level = self.level
        camp = level.camp
        if not camp:
            return self.goblin_patrol(c)
        carried = [k for k in c.carry if k in items.CARCASSES or k in items.FOODS]
        if carried:                                     # home with it, to the pile by the fire
            store = camp["store"]
            if dist(c, store) <= 1:
                for k in carried:
                    c.carry.remove(k)
                    items.drop(level, *store, k)
                self.say(f"The {c.name} drops {items.describe_pile(carried)} by the fire.", (c.x, c.y))
                return 2.0
            return self.step_toward(c, store) or 1.0
        if self.camp_food() >= CAMP_FOOD:
            return self.wander(c, camp["store"], 4, 2.0)
        lying = [p for p, pile in level.items.items() if p != camp["store"]
                 and any(k in items.CARCASSES for k in pile) and dist(c, p) <= 20]
        if lying:
            spot = min(lying, key=lambda p: dist(c, p))
            return self.step_toward(c, spot) or self.wander(c, (c.x, c.y), 3)
        prey = [o for o in level.creatures if o.beast.prey and dist(c, o) <= 25]
        if prey:                                   # a sleeping bat is easiest; else creep up and dash
            o = min(prey, key=lambda o: dist(c, o) - (10 if o.asleep else 0))
            if dist(c, o) <= 1:
                return self.strike(c, o)
            return self.step_toward(c, (o.x, o.y), 0.5 if dist(c, o) <= 3 else 1.3) or                 self.wander(c, (c.x, c.y), 4)
        return self.wander(c, c.home, c.reach)

    def goblin_cook(self, c) -> float:
        level = self.level
        camp = level.camp
        if not camp:
            return self.goblin_guard(c)
        store = camp["store"]
        if dist(c, store) > 1:
            return self.step_toward(c, store) or 1.0
        pile = level.items.setdefault(store, [])
        raw = next((k for k in pile if k in items.CARCASSES), None)
        if raw is None:
            c.timer = 0
            return 3.0
        c.timer += 1
        if c.timer >= 10:                          # done: off the spit
            c.timer = 0
            pile.remove(raw)
            pile.append("roast meat")
            self.say(f"The {c.name} takes a roasted {raw.replace(' carcass', '')} off the spit.", (c.x, c.y))
        elif c.timer == 1:
            self.say(f"The {c.name} spits {a_name(raw)} over the fire.", (c.x, c.y))
        return 2.0

    # ------------------------------------------------------------- settling

    def settle(self, minutes: float, elapsed: float | None) -> None:
        """Everything where it would be by now, after a long while."""
        level, rng = self.level, self.rng
        self.now = minutes
        self.taken = {(a.x, a.y) for a in level.actors}
        if self.you:
            self.taken.add(self.you)
        for c in level.creatures:
            if elapsed:
                c.hp = min(float(c.beast.hp), c.hp + elapsed / 60 * 3)
                c.hunger = min(100.0, c.hunger + HUNGER_RATE * elapsed)
                if c.hunger > 85 and c.kind == "wolf":       # they've hunted while you were away
                    c.hunger = rng.uniform(25, 60)
                if c.kind == "goblin":
                    c.hunger = min(c.hunger, 50.0)
            c.target, c.seen_at, c.path, c.goal, c.bored, c.timer, c.budget = None, None, [], None, 0, 0, 0
            if c.kind == "wolf":
                c.state = "roam"
                spot = self.away(c.home, c.reach // 2)
            elif c.kind == "bat":
                c.state, c.asleep = "roost", True
                spot = self.away(c.home, 2)
            elif c.kind == "goblin":
                c.state = "routine"
                c.asleep = self.bedtime(c)
                spot = c.bed if c.asleep and c.bed else self.station(c)
                if spot in self.taken:
                    spot = self.away(spot, 3)
            else:
                c.state = "graze"
                spot = self.away(c.home, c.reach)
            self.taken.discard((c.x, c.y))
            c.x, c.y = spot
            self.taken.add(spot)
        if elapsed:                                  # small game breeds back
            for kind, count, home, reach in level.wild_spec:
                have = sum(1 for c in level.creatures if c.kind == kind and c.home == home)
                for _ in range(count - have):
                    spot = self.away(home, reach)
                    level.creatures.append(Creature(kind, *spot, home=home, reach=reach))
                    self.taken.add(spot)

    def away(self, centre, reach: int) -> tuple:
        """A free spot near `centre`, out of your sight if it can be."""
        best = None
        for _ in range(40):
            p = self.spot_near(centre, max(1, reach))
            if p in self.taken:
                continue
            if self.you is None or dist(p, self.you) > 10:
                return p
            best = best or p
        return best or tuple(centre)


# ----------------------------------------------------------------- you and them

def player_attack(level, engine, c, rng: random.Random) -> None:
    """You strike `c`."""
    w = Wilds(level, engine, rng, engine.minutes)
    b = c.beast
    dmg, verb = combat.player_blow(engine.player, b.dodge, rng)
    if c.asleep:
        c.asleep = False
    c.provoked = engine.minutes
    for o in level.creatures:                     # its pack, its roost, its tribe take note
        if o.kind == c.kind and o.pack == c.pack and dist(o, c) <= 10:
            o.provoked = engine.minutes
    w.noise((engine.lx, engine.ly), 8)
    if c.kind == "goblin" and c.state not in ("fight", "flee"):
        c.state, c.target, c.seen_at = "fight", YOU, (engine.lx, engine.ly)
    if not dmg:
        engine.say(f"You {verb} at the {c.name} and miss.")
        return
    c.hp -= dmg
    if c.hp <= 0:
        w.kill(c)
        left = items.describe_pile(level.items.get((c.x, c.y), []))
        engine.say(f"You kill the {c.name}." + (f" It leaves {left}." if left != "nothing" else ""))
    else:
        how = "badly hurt" if c.hp < c.beast.hp * 0.4 else "hurt"
        engine.say(f"You {verb} the {c.name} ({dmg}). It's {how}.")


def threatening(level, engine) -> list:
    """Creatures about that won't let you rest: wolves and goblins you can see, awake, and bats
    swarming or anything after you."""
    out = []
    for c in level.creatures:
        if c.kind not in HOSTILE or c.asleep:
            continue
        seen = engine.local_visible.shape == level.tiles.shape and engine.local_visible[c.x, c.y]
        after_you = c.target == YOU and c.state in ("stalk", "charge", "fight", "swarm", "track")
        if (seen and c.kind != "bat" and dist(c, (engine.lx, engine.ly)) <= 15) or after_you or c.state == "swarm":
            out.append(c)
    return out


def notice(level, engine) -> None:
    """Tells you about wolves, goblins and waking bats as they come into sight."""
    if engine.local_visible.shape != level.tiles.shape:
        return
    new: dict[str, int] = {}
    for c in level.creatures:
        seen = bool(engine.local_visible[c.x, c.y])
        if seen and not c.spotted and c.kind in HOSTILE and not (c.kind == "bat" and c.asleep):
            new[c.kind] = new.get(c.kind, 0) + 1
        c.spotted = seen
    if new:
        parts = [a_name(BEASTS[k].name) if n == 1 else f"{n} {BEASTS[k].plural}" for k, n in new.items()]
        engine.say("You spot " + (parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]) + ".")
        engine.disturbed = True


STATE_WORDS = {
    "roam": "roaming its territory", "stalk": "stalking, low to the ground", "charge": "charging!",
    "track": "following a scent", "return": "heading home", "flee": "fleeing", "eat": "eating its kill",
    "graze": "nibbling about", "up": "up a tree", "flutter": "flitting about", "swarm": "swooping at you",
    "home": "flitting back to its roost", "roost": "roosting", "fight": "fighting",
    "investigate": "looking for whatever made that noise",
}
ROLE_WORDS = {"guard": "standing guard", "patrol": "on patrol", "hunter": "hunting", "cook": "tending the fire"}


def describe(c) -> list[str]:
    lines = [a_name(c.name).capitalize()]
    if c.asleep:
        lines.append("Asleep" if c.kind != "bat" else "Hanging from the roof, asleep")
    elif c.kind == "goblin" and c.state == "routine":
        lines.append(ROLE_WORDS.get(c.role, "about its business").capitalize())
    elif c.kind == "goblin" and c.state == "return":
        lines.append("Going back to its work")
    else:
        lines.append(STATE_WORDS.get(c.state, c.state).capitalize())
    if c.hp < c.beast.hp:
        lines.append("Badly hurt" if c.hp < c.beast.hp * 0.4 else "Wounded")
    if c.kind == "wolf" and c.hunger >= MAN_HUNGER:
        lines.append("Ravenous")
    elif c.kind == "wolf" and c.hunger >= HUNT_HUNGER:
        lines.append("Hungry")
    if c.carry and c.kind == "goblin":
        lines.append("Carrying " + items.describe_pile(c.carry))
    return lines


# ----------------------------------------------------------------- who lives where

WOODED = (B.FOREST, B.TAIGA, B.JUNGLE)
OPEN = (B.GRASSLAND, B.STEPPE, B.SAVANNA, B.SHRUBLAND, B.HILLS, B.TUNDRA)
WOLF_CHANCE = {B.FOREST: 0.5, B.TAIGA: 0.5, B.HILLS: 0.3, B.TUNDRA: 0.3, B.GRASSLAND: 0.25, B.STEPPE: 0.25,
               B.SHRUBLAND: 0.25, B.MOUNTAINS: 0.2, B.JUNGLE: 0.12, B.SWAMP: 0.12, B.SAVANNA: 0.12}
CAVE_WOLVES = 0.6        # a cave's region has a pack about its mouth this often


def small_game(biome: int, settled: bool) -> list:
    if settled:
        return [("bird", 2, 4)]
    if biome in WOODED:
        return [("squirrel", 3, 6), ("bird", 3, 6), ("rabbit", 1, 3)]
    if biome in OPEN:
        return [("rabbit", 4, 7), ("bird", 3, 5)]
    if biome == B.SWAMP:
        return [("bird", 4, 7), ("rabbit", 1, 2)]
    return [("bird", 0, 2), ("rabbit", 0, 2)]


def open_ground(level) -> list:
    t = level.tiles
    ok = T.WALK[t] & ~T.WATERY[t] & ~T.ROOF[t]
    ok[:3], ok[-3:], ok[:, :3], ok[:, -3:] = False, False, False, False
    return [(int(x), int(y)) for x, y in zip(*np.nonzero(ok)) if (int(x), int(y)) not in level.exits]


def place(level, rng: random.Random, centre, reach: int, taken: set) -> tuple | None:
    for _ in range(60):
        x = centre[0] + rng.randint(-reach, reach)
        y = centre[1] + rng.randint(-max(1, reach // 2), max(1, reach // 2))
        if level.walkable(x, y) and not T.WATERY[level.tiles[x, y]] and (x, y) not in taken \
                and (x, y) not in level.exits:
            taken.add((x, y))
            return x, y
    return None


def add_game(level, rng: random.Random, kind: str, n: int, home, reach: int, taken: set) -> None:
    if n <= 0:
        return
    level.wild_spec.append((kind, n, home, reach))
    for _ in range(n):
        spot = place(level, rng, home, reach, taken)
        if spot:
            level.creatures.append(Creature(kind, *spot, home=home, reach=reach))


def add_pack(level, rng: random.Random, home, reach: int, taken: set, size: int | None = None) -> list:
    if size is None:
        size = 1 if rng.random() < LONE_WOLF else rng.choices([2, 3, 4, 5], [3, 3.5, 2.5, 1])[0]
    pack = 1 + max((c.pack for c in level.creatures), default=0)
    hunger = rng.uniform(20, 85)
    out = []
    for _ in range(size):
        spot = place(level, rng, home, 4, taken) or place(level, rng, home, 10, taken)
        if spot:
            w = Creature("wolf", *spot, home=tuple(home), reach=reach, pack=pack,
                         hunger=max(0.0, min(100.0, hunger + rng.uniform(-8, 8))))
            level.creatures.append(w)
            out.append(w)
    return out


def taken_on(level) -> set:
    return {(a.x, a.y) for a in level.actors} | {(c.x, c.y) for c in level.creatures}


def populate_region(level, world, x: int, y: int, site, rng: random.Random) -> None:
    """Small game everywhere, and in the wilds now and then a pack of wolves."""
    biome = int(world.biome[x, y])
    settled = site is not None and site.settled
    ground = open_ground(level)
    if not ground:
        return
    taken = taken_on(level)
    for kind, lo, hi in small_game(biome, settled):
        add_game(level, rng, kind, rng.randint(lo, hi), rng.choice(ground), 18, taken)
    if settled:
        return
    chance = WOLF_CHANCE.get(biome, 0.0)
    home = rng.choice(ground)
    if site is not None and site.kind == "cave":
        chance = max(chance, CAVE_WOLVES)
        mouth = next(iter(level.exits), None)
        if mouth is not None:
            home = (mouth[0], min(level.height - 4, mouth[1] + 3))
    if rng.random() < chance:
        add_pack(level, rng, home, rng.randint(22, 32), taken)


def cave_folk(site_name: str) -> str:
    """Who lives in a cave, fixed by its name: "wolves" (a den on the first level), "goblins",
    or nobody but the bats and rats."""
    r = zlib.crc32(site_name.encode()) % 100
    return "wolves" if r < 45 else "goblins" if r < 90 else ""


def walk_distance(level, start) -> np.ndarray:
    walk = T.WALK[level.tiles].astype(np.int32)
    d = tcod.path.maxarray(walk.shape, dtype=np.int32)
    d[start] = 0
    tcod.path.dijkstra2d(d, walk, 2, 3, out=d)
    return d


def ranked(level, start) -> list:
    """Every reachable floor tile, nearest the start first."""
    d = walk_distance(level, start)
    cells = [(int(x), int(y)) for x, y in zip(*np.nonzero((d < np.iinfo(np.int32).max) & T.WALK[level.tiles]))
             if (int(x), int(y)) not in level.exits and level.tiles[x, y] == T.CAVE_FLOOR]
    cells.sort(key=lambda c: d[c])
    return cells


def populate_cave(level, site, depth: int, deepest: int, rng: random.Random) -> None:
    """Bats and rats in every cave level; a wolf den, or goblins, in some."""
    up = next((p for p, k in level.exits.items() if level.tiles[p] == T.STAIRS_UP), None)
    if up is None:
        return
    cells = ranked(level, up)
    if len(cells) < 30:
        return
    taken = taken_on(level)
    n = len(cells)
    for _ in range(rng.randint(2, 3)):                         # bat roosts, well in
        roost = cells[rng.randrange(n * 2 // 5, n)]
        for _ in range(rng.randint(3, 6)):
            spot = place(level, rng, roost, 2, taken)
            if spot:
                level.creatures.append(Creature("bat", *spot, home=roost, reach=10, asleep=True,
                                                pack=1000 + roost[0] * 100 + roost[1]))
    add_game(level, rng, "rat", rng.randint(2, 5), cells[rng.randrange(n // 4, n)], 30, taken)
    folk = cave_folk(site.name) if site is not None else ""
    if folk == "wolves" and depth == 1:
        add_pack(level, rng, cells[n * 3 // 5], 40, taken, size=rng.randint(3, 5))
    if folk != "goblins":
        return
    tribe = 99
    gang = []
    if depth == 1:                                             # guards at the way in, sleeping in shifts
        posts = [c for c in cells if 2 <= dist(c, up) <= 3][:6]
        rng.shuffle(posts)
        for i, post in enumerate(posts[:2]):
            gang.append(Creature("goblin", *post, home=post, role="guard", pack=tribe,
                                 sleep_hour=(9.0 if i == 0 else 21.0)))
            taken.add(post)
    if depth == deepest:
        camp = make_camp(level, rng, cells, up)
        if camp:
            beds = list(camp["beds"])
            roles = ["cook", "hunter", "hunter"] + ["patrol"] * rng.randint(1, 2)
            for role in roles:
                spot = place(level, rng, camp["store"], 4, taken)
                if spot is None:
                    continue
                g = Creature("goblin", *spot, home=camp["store"], role=role, pack=tribe, reach=25,
                             bed=beds.pop() if beds else None, sleep_hour=8.0 + rng.uniform(-1.5, 1.5))
                if role == "patrol":
                    g.route = [cells[rng.randrange(n // 3, n)] for _ in range(3)] + [camp["store"]]
                gang.append(g)
    if depth != deepest or depth == 1:
        for _ in range(rng.randint(1, 2)):
            route = [cells[rng.randrange(n // 5, n)] for _ in range(rng.randint(3, 4))]
            spot = place(level, rng, route[0], 3, taken)
            if spot:
                gang.append(Creature("goblin", *spot, home=route[0], role="patrol", pack=tribe, route=route,
                                     sleep_hour=8.0 + rng.uniform(-1.5, 1.5)))
    for g in gang:
        loot(g, rng)
        g.hunger = rng.uniform(10, 50)
    level.creatures += gang


def loot(g, rng: random.Random) -> None:
    """What a goblin carries."""
    if rng.random() < 0.5:
        g.carry += ["coin"] * rng.randint(1, 5)
    if rng.random() < 0.4:
        g.carry.append(rng.choice(items.TRINKETS))
    if rng.random() < 0.25:
        g.carry.append("bone charm")


def make_camp(level, rng: random.Random, cells: list, up) -> dict | None:
    """Deep in: a fire, bedrolls round it, a pile of food beside it and a barrel of loot."""
    t = level.tiles
    reach_before = len(cells)
    for centre in cells[len(cells) * 4 // 5:][::-1]:
        x, y = centre
        ring = [(x + dx, y + dy) for dx in range(-5, 6) for dy in range(-3, 4)
                if level.in_bounds(x + dx, y + dy) and t[x + dx, y + dy] == T.CAVE_FLOOR
                and (x + dx, y + dy) not in level.exits]
        if len(ring) < 18:
            continue
        t[centre] = T.HEARTH
        store = next((p for p in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)) if t[p] == T.CAVE_FLOOR), None)
        if store is None or len(ranked(level, up)) < reach_before - 1:
            t[centre] = T.CAVE_FLOOR
            continue
        barrel = next((p for p in ring if dist(p, centre) == 3 and p != store), None)
        if barrel is not None:
            t[barrel] = T.BARREL
            if len(ranked(level, up)) < reach_before - 2:
                t[barrel] = T.CAVE_FLOOR
                barrel = None
        beds = [p for p in ring if 2 <= dist(p, centre) <= 4 and t[p] == T.CAVE_FLOOR and p != store]
        rng.shuffle(beds)
        beds = beds[: rng.randint(4, 6)]
        for b in beds:
            t[b] = T.BEDROLL
        items.drop(level, *store, "roast meat", rng.randint(1, 2))
        items.drop(level, *store, rng.choice(["rat carcass", "bat carcass"]))
        if barrel is not None:
            bag = items.Inventory()
            bag.add("coin", rng.randint(3, 12))
            for _ in range(rng.randint(1, 3)):
                bag.add(rng.choice(items.TRINKETS))
            if rng.random() < 0.5:
                bag.add(rng.choice(["dagger", "rusty dagger", "crude knife", "iron helm"]))
            level.stores[barrel] = bag
        level.camp = {"hearth": centre, "store": store, "beds": beds, "barrel": barrel}
        return level.camp
    return None
