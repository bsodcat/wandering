"""The game state: the world, the clock, the player, and what keys do.

Two ways to get about:

- The overworld: one region per step, each costing the hours it takes to cross that ground.
  Enter (or >) steps down into the region you're in.
- Local maps: the region tile by tile, each step costing minutes. Walk off an edge and you're
  in the next region's map; < takes you back up to the overworld. Stairs (> and <, or Enter)
  lead down into caves and crypts and up towers. Trees spread their leaves on a layer above
  the ground; v switches between looking down on the treetops and the ground beneath them.

The mouse: pointing at a place describes it (`describe`); a left click puts that in the log.
Holding the right button walks you toward the pointer a step at a time (`step_toward`), over
ground you know, until you get there, let go, or something needs your attention.

Ground rises and falls (game/elevation.py): a step up or down a level is a slope, two is a
scramble, and high ground hides what's behind it. On the overworld, climbing costs hours.

What you carry (game/items.py): g picks up what's at your feet, i shows your bag, x digs with a
shovel for what's buried, and walking into a tree with an axe fells it for logs. Walking into
someone who trades opens their shop (game/shop.py); walking into a dog or cat pets it. A room
key from an inn's barkeeper lets you sleep (z) in a bed upstairs. Dug ground grows back over a
few hours once it's rained on.

Wild things (game/wild.py) live on local maps beside the people: small game, wolves in the
wilds and in caves, bats and goblins underground. Walk into one to strike it (game/combat.py);
a wolf's bite can, rarely, give you wolf fever (game/sickness.py), which hot soup from an
innkeeper treats. You can't rest with wolves or goblins about.

e (or a left click on something you can use) opens the use menu: talk, trade, pet, attack,
open a barrel, sleep in a bed, pick things up, eat, wield and wear. Something out of reach,
you walk over to first.

Local maps are built when first visited and kept, with what you've explored, for the rest of
the game. The weather and temperature come from the region you're in either way.
"""
from __future__ import annotations

import random

import numpy as np
import tcod
from tcod.event import KeySym, Modifier

from . import biomes as B
from . import combat
from . import elevation
from . import items
from . import people
from . import shop as shops
from . import sickness
from . import tiles as T
from . import trees
from . import wild
from .farming import PETS, crop_stage
from .light import SEEN_FROM_AFAR, firelight
from .climate import (DAYS_PER_SEASON, MINUTES_PER_DAY, MINUTES_PER_HOUR, Climate, Conditions, hour_of_day,
                      latitude, shelter_at, snow_cover, time_of_day)
from .level import Level
from .localgen import LOCAL_H, LOCAL_W, make_level, node_local
from .player import NORMAL, Player, expose, tire
from .options import Menu
from .ui import Panels
from .worldgen import World, generate, travel_cost

MOVES = {
    KeySym.UP: (0, -1), KeySym.DOWN: (0, 1), KeySym.LEFT: (-1, 0), KeySym.RIGHT: (1, 0),
    KeySym.KP_8: (0, -1), KeySym.KP_2: (0, 1), KeySym.KP_4: (-1, 0), KeySym.KP_6: (1, 0),
    KeySym.KP_7: (-1, -1), KeySym.KP_9: (1, -1), KeySym.KP_1: (-1, 1), KeySym.KP_3: (1, 1),
    KeySym.W: (0, -1), KeySym.S: (0, 1), KeySym.A: (-1, 0), KeySym.D: (1, 0),
}
WAIT_KEYS = {KeySym.PERIOD, KeySym.KP_5}
ENTER_KEYS = {KeySym.RETURN, KeySym.KP_ENTER}
REST_KEY, OVERLAY_KEY, REVEAL_KEY, LAYER_KEY = KeySym.Z, KeySym.O, KeySym.M, KeySym.V
OVERWORLD_EFFORT = 0.5  # a day's travel is steadier going than scrambling about on foot
MENU_KEY = KeySym.ESCAPE  # the pause menu: resume, options, quit
FULLSCREEN_KEY = KeySym.F11
OVERLAYS = ["Normal", "Elevation", "Temperature", "Moisture", "Weather"]
PICKUP_KEY, DIG_KEY, BAG_KEY, USE_KEY = KeySym.G, KeySym.X, KeySym.I, KeySym.E
ATTACK_MINUTES, ATTACK_EFFORT = 0.5, 1.5  # a blow
MEAL_MINUTES = 5
SOUP_MINUTES = 15
DIRECTIONS = {(0, 0): "here", (0, -1): "north", (0, 1): "south", (-1, 0): "west", (1, 0): "east",
              (-1, -1): "north-west", (1, -1): "north-east", (-1, 1): "south-west", (1, 1): "south-east"}
CHOP_MINUTES, CHOP_EFFORT = 20, 2.5     # felling a tree
DIG_MINUTES, DIG_EFFORT = 30, 2.5       # digging a hole
REGROW_MINUTES = 4 * 60                 # dug ground greens over this long after rain first falls on it
WAKE_HOUR = 7                           # sleeping in a bed you've paid for, you sleep till then
ROOM_UNTIL_HOUR = 10                    # and give the key back by then

START_MINUTES = 8 * MINUTES_PER_HOUR  # 08:00 on the first day of spring
ROAD_TRAVEL = 0.6       # hours per region along a road
RIVER_TRAVEL = 1.0      # extra hours to ford a river where there's no bridge
RIVER_SOAK = 50         # wetness from wading one
NIGHT_SLOWDOWN = 1.5    # travel takes this much longer in the dark
SNOW_SLOWDOWN = {"Snow": 1.3, "Blizzard": 1.8}
SNOWY_GROUND = 1.4      # local steps through lying snow
REST_HOURS = 8
LANTERN = 6             # how many columns your lantern lights, underground or on a dark night
WET_DETOUR = 4          # a walk to the pointer goes this many tenths of a minute round per point of wetting
LOOKOUT_RANGE = 12     # regions you can see from the top of a tower
LOCAL_KNOWLEDGE = {"town": 14, "village": 8, "inn": 6}  # regions around a settlement its people tell you about
LEAF_NAMES = {trees.BROADLEAF: "broadleaf", trees.PINE: "pine", trees.JUNGLE: "jungle"}
WHERE_STAIRS_GO = {"cave": "the caves below", "crypt": "a crypt below", "tower": "the tower above",
                   "region": "the surface", "inn_up": "the rooms upstairs", "cellar": "the cellar",
                   "arena": "the arena"}
SKY = {"Clear": "clear", "Cloudy": "cloudy", "Overcast": "overcast", "Fog": "foggy", "Rain": "raining",
       "Storm": "stormy", "Snow": "snowing", "Blizzard": "a blizzard"}

WEATHER_NEWS = {
    "Rain": "It starts to rain.", "Storm": "A storm breaks overhead.", "Snow": "It begins to snow.",
    "Blizzard": "A blizzard howls in.", "Fog": "Fog rolls in.", "Overcast": "The sky turns grey and heavy.",
}
LIGHT_NEWS = {"Dawn": "The sun comes up.", "Dusk": "The sun is going down.", "Night": "Night falls."}


def step_effort(tile: int) -> float:
    """How hard a step onto this tile is, from how slow the going is (a street is easy, wading
    or bushes hard)."""
    return float(np.clip(T.MINUTES[tile] / 0.6, 0.6, 2.5))


class Engine:
    def __init__(self, world: World, player: Player, minutes: float = START_MINUTES):
        self.world, self.player, self.minutes = world, player, minutes
        self.climate = Climate(world)
        self.explored = np.zeros(world.biome.shape, dtype=bool)
        self.visible = np.zeros(world.biome.shape, dtype=bool)
        self.messages: list[str] = []
        self.repeats = 1
        self.overlay = 0
        self.reveal = False
        self.now: Conditions = self.climate.at(player.x, player.y, minutes)
        self.visited: set = set()
        self.levels: dict[tuple, Level] = {}
        self.level: Level | None = None   # None: on the overworld
        self.lx = self.ly = 0              # where you are on the local map
        self.treetops = True               # local maps show the leaves above (v: the ground beneath)
        self.mouse: tuple[int, int] | None = None   # the map cell under the pointer
        self.autopath = False              # walking toward the pointer (right button held)
        self.goal: tuple[int, int] | None = None    # where that walk is headed, on the current map
        self.panels = Panels()             # what's laid over the map (game/ui.py)
        self.menu = Menu()                 # the pause menu and options (game/options.py)
        self.quitting = False              # Quit was clicked in the menu
        self.to_title = False              # Main menu was picked: back to the title screen
        self.fair = False                  # always fair weather (the dev arena)
        self.shop: shops.Shop | None = None  # the shop you're trading at, if any
        self.room_until: float | None = None  # when your inn room key goes back
        self.relief = False                # o on a local map: colour it by height
        self.disturbed = False             # something happened that should stop a walk
        self.pending = None                # (x, y, do, stand on it, who): to do once you get there
        self.rng = random.Random()         # blows and bites
        self.local_visible = np.zeros((1, 1), dtype=bool)
        self.update_view()

    @classmethod
    def new(cls, seed: int | None = None, world: World | None = None) -> Engine:
        """A fresh world, starting in its best town. The same seed makes the same world (pass
        `world` if it's already been generated from that seed)."""
        if world is None:
            world = generate(random.randrange(2**31) if seed is None else seed)
        start = next((s for s in world.sites if s.kind == "town"), None) or \
            next((s for s in world.sites if s.settled), None)
        if start is not None:
            x, y, where = start.x, start.y, start.name
        else:  # no settlements at all: the walkable cell nearest the middle
            cells = np.argwhere(B.TRAVEL[world.biome] > 0)
            x, y = min(map(tuple, cells), key=lambda c: (c[0] - world.width // 2) ** 2 + (c[1] - world.height // 2) ** 2)
            where = "the wilds"
        engine = cls(world, Player(int(x), int(y)))
        engine.say(f"You set out from {where}. It's {SKY[engine.now.kind]}, {engine.now.air:.0f}°C.")
        engine.visit()
        return engine

    @classmethod
    def arena(cls, seed: int = 1) -> Engine:
        """The dev arena (game/arena.py), on a fine summer's morning, in the first town of world
        `seed` (for the latitude and the season)."""
        from .arena import SPAWN, build_arena
        engine = cls.new(seed)
        level = build_arena(engine.world, (engine.player.x, engine.player.y))
        engine.levels[level.key] = level
        engine.level = level
        engine.lx, engine.ly = SPAWN
        engine.fair = True
        engine.minutes = (DAYS_PER_SEASON + 10) * MINUTES_PER_DAY + 11 * MINUTES_PER_HOUR   # early summer, late morning
        engine.now = engine.weather()
        engine.messages.clear()
        engine.say("Welcome to the dev arena: every tile, person and animal in the game. "
                   "Point at anything to name it; Esc, then Main menu, to leave.")
        engine.pass_time(1 / 60)
        return engine

    # ------------------------------------------------------------- queries

    def say(self, text: str) -> None:
        if self.messages and self.messages[-1] == text:
            self.repeats += 1         # shown as "(x3)" rather than filling the log
            return
        self.repeats = 1
        self.messages.append(text)
        del self.messages[:-200]

    @property
    def site(self):
        return self.world.site_at.get((self.player.x, self.player.y))

    @property
    def biome(self) -> B.Biome:
        return B.BIOMES[self.world.biome[self.player.x, self.player.y]]

    @property
    def lat(self) -> float:
        return float(latitude(self.player.y, self.world.height))

    @property
    def tile(self) -> T.Tile | None:
        return T.TILES[self.level.tiles[self.lx, self.ly]] if self.level else None

    @property
    def underground(self) -> bool:
        return self.level is not None and self.level.underground

    @property
    def indoors(self) -> bool:
        """Out of the weather: under a roof, underground, or in a settlement on the overworld."""
        if self.level is None:
            site = self.site
            return site is not None and site.settled
        return self.level.underground or bool(T.ROOF[self.level.tiles[self.lx, self.ly]])

    @property
    def leaves(self) -> int:
        """The kind of leaves over you (trees.NONE if open sky or a roof)."""
        if self.level is None or self.level.underground:
            return trees.NONE
        return int(self.level.canopy[self.lx, self.ly])

    @property
    def crop_stage(self) -> str:
        """Where the grain is in its year, here and now."""
        return crop_stage(self.lat, self.minutes)

    @property
    def foliage(self) -> str:
        """How the broadleaf trees look here this time of year."""
        return trees.foliage(self.lat, self.minutes)

    @property
    def indoor_air(self) -> float:
        return self.level.indoor_air if self.level else 20.0

    @property
    def shelter(self) -> float:
        if self.indoors:
            return 1.0
        if self.level is None:
            return shelter_at(self.world, self.player.x, self.player.y)
        base = float(B.SHELTER[self.world.biome[self.player.x, self.player.y]])
        t = self.level.tiles[max(0, self.lx - 1): self.lx + 2, max(0, self.ly - 1): self.ly + 2]
        cover = np.isin(t, [T.TREE, T.PINE, T.JUNGLE_TREE, T.WALL, T.STONE_WALL, T.ROCK]).sum()
        here = max(base if self.level.surface else 0.0, cover * 0.12)
        return float(min(0.85, here + trees.leaf_shelter(self.leaves, self.foliage)))

    @property
    def snowy(self) -> bool:
        return not self.underground and snow_cover(self.world, self.player.x, self.player.y, self.minutes)

    def weather(self) -> Conditions:
        """The weather where you are now (always fair and mild in the dev arena)."""
        c = self.climate.at(self.player.x, self.player.y, self.minutes)
        if self.fair:      # fine all day, but for a shower at six in the evening
            shower = 18 <= float(hour_of_day(self.minutes)) < 19
            c = Conditions(air=max(c.air, 18.0), cloud=0.6 if shower else 0.1, precip=0.35 if shower else 0.0,
                           wind=min(c.wind, 8.0), fog=0.0, light=c.light * (0.8 if shower else 1.0),
                           kind="Rain" if shower else "Clear")
        return c

    def sight_radius(self) -> int:
        """How far you can make things out. On the overworld it's regions: less at night and in
        fog or rain, more from high ground. On a local map it's tiles, and your lantern always
        lights the nearest few."""
        c = self.now
        if self.level is None:
            r = 2 + 7 * c.light - 4 * c.fog - 2 * c.precip
            r += {B.HILLS: 1, B.MOUNTAINS: 3, B.PEAKS: 4}.get(int(self.world.biome[self.player.x, self.player.y]), 0)
            return max(1, round(r))
        if self.level.underground:
            return LANTERN
        r = (4 + 36 * c.light) * (1 - 0.75 * c.fog) * (1 - 0.4 * c.precip)
        return max(LANTERN, round(r))

    def travel_time(self, x: int, y: int, dx: int, dy: int) -> tuple[float, float]:
        """(hours, wetness) to step into overworld region (x, y)."""
        w = self.world
        site = w.site_at.get((x, y))
        on_road = w.road[x, y] or (site is not None and site.settled)
        biome = B.BIOMES[w.biome[x, y]]
        hours = ROAD_TRAVEL if on_road else biome.travel
        soak = 0.0 if on_road else biome.wet
        if w.river[x, y] and not on_road:
            hours += RIVER_TRAVEL
            soak += RIVER_SOAK
        hours += elevation.world_climb_hours(w, (x - dx, y - dy), (x, y)) * (0.5 if on_road else 1.0)
        if dx and dy:
            hours *= 1.41
        if self.now.light < 0.25:
            hours *= NIGHT_SLOWDOWN
        hours *= SNOW_SLOWDOWN.get(self.now.kind, 1.0)
        return hours, soak

    def step_minutes(self, tile: int, dx: int, dy: int) -> float:
        """Minutes to take one step onto a local tile."""
        minutes = float(T.MINUTES[tile]) * (1.41 if dx and dy else 1.0)
        if not self.underground and not T.ROOF[tile]:
            if self.now.light < 0.25:
                minutes *= 1.3
            minutes *= SNOW_SLOWDOWN.get(self.now.kind, 1.0) ** 0.5
            if self.snowy and T.SNOWS_ON[tile]:
                minutes *= SNOWY_GROUND
        return minutes

    # ------------------------------------------------------------- overworld

    def move(self, dx: int, dy: int) -> bool:
        """Travels one region on the overworld. Returns whether the player moved."""
        p, w = self.player, self.world
        if not p.alive:
            return False
        x, y = p.x + dx, p.y + dy
        if not w.in_bounds(x, y):
            self.say("You can't go any further that way.")
            return False
        if not w.walkable(x, y):
            self.say(f"The {B.BIOMES[w.biome[x, y]].name.lower()} is too deep to cross.")
            return False
        hours, soak = self.travel_time(x, y, dx, dy)
        old_biome = self.biome
        p.x, p.y = x, y
        site = self.site
        if w.river[x, y] and w.road[x, y]:
            self.say("You cross the river by the bridge.")
        elif w.river[x, y] and not (site is not None and site.settled):
            self.say("You wade across the river.")
        if site is not None:
            self.say(f"You reach {site.name}." if site.settled else f"You come upon the {site.name}.")
            self.visit()
        elif self.biome is not old_biome:
            self.say(f"You enter the {self.biome.name.lower()}.")
        self.pass_time(hours, soak, effort=OVERWORLD_EFFORT * (0.7 if w.road[x, y] else 1.0))
        return True

    def visit(self) -> None:
        """The first time you stop in a settlement, its people tell you about the land around it."""
        site = self.site
        if site is None or (site.x, site.y) in self.visited or site.kind not in LOCAL_KNOWLEDGE:
            return
        self.visited.add((site.x, site.y))
        self.learn_around(site.x, site.y, LOCAL_KNOWLEDGE[site.kind])
        self.say(f"The people of {site.name} tell you about the land around it." if site.kind != "inn"
                 else f"Travellers at {site.name} tell you about the roads nearby.")

    def learn_around(self, x: int, y: int, r: int) -> None:
        xs, ys = np.ogrid[: self.world.width, : self.world.height]
        self.explored |= (xs - x) ** 2 + (2 * (ys - y)) ** 2 <= r * r  # tiles are twice as tall as wide

    # ------------------------------------------------------------- local maps

    def get_level(self, key: tuple) -> Level:
        if key not in self.levels:
            level = make_level(self.world, key)
            if key[0] in ("inn_up", "cellar"):         # named after the inn they're in
                ground = self.level if self.level is not None and self.level.region == key[1:3] else \
                    self.levels.get(("region", key[1], key[2]))
                inn = next((b.name for b in ground.buildings if b.kind == "inn"), None) if ground else None
                if inn:
                    level.name = f"Upstairs at {inn}" if key[0] == "inn_up" else f"The cellar of {inn}"
            self.levels[key] = level
        return self.levels[key]

    def enter_region(self) -> bool:
        """Steps down from the overworld into the local map of the region you're in."""
        p = self.player
        if self.level is not None or not p.alive:
            return False
        level = self.get_level(("region", p.x, p.y))
        cx, cy = (LOCAL_W // 2, LOCAL_H // 2 + 1) if self.site else node_local(self.world, p.x, p.y)
        self.level = level
        self.lx, self.ly = level.nearest_walkable(cx, cy)
        self.say(f"You walk into {level.name}.")
        self.pass_time(1 / 60)
        return True

    def leave_region(self) -> bool:
        """Back up to the overworld, from the surface of a region."""
        if self.level is None:
            return False
        if self.level.key[0] == "arena":
            self.say("This is the dev arena: Esc, then Main menu, to leave.")
            return False
        if not self.level.surface:
            self.say("You'll have to find the way back up first.")
            return False
        self.level = None
        self.say("You take in the lie of the land.")
        self.update_view()
        return True

    def move_local(self, dx: int, dy: int) -> bool:
        """One step on a local map. Off the edge of a region's map is into the next region."""
        p, level = self.player, self.level
        if not p.alive:
            return False
        nx, ny = self.lx + dx, self.ly + dy
        if not level.in_bounds(nx, ny):
            return self.cross_border(dx, dy, nx, ny)
        beast = wild.creature_at(level, nx, ny)
        if beast is not None:
            return self.attack(beast)
        tile = int(level.tiles[nx, ny])
        if tile in trees.KIND and self.player.inventory.count("axe"):
            return self.chop(nx, ny)
        if not T.WALK[tile]:
            self.say("The water is too deep to wade." if tile == T.DEEP_WATER
                     else f"The {T.TILES[tile].name} is in the way.")
            return False
        dh = int(level.elev[nx, ny]) - int(level.elev[self.lx, self.ly])
        graded = tile in elevation.GRADED and int(level.tiles[self.lx, self.ly]) in elevation.GRADED
        ok, slow, extra, note = elevation.climb(dh, graded)
        if not ok:
            self.say(note)
            return False
        someone = people.actor_at(level, nx, ny)
        if someone is not None and not self.meet(someone):
            return False
        was_inside = self.indoors
        self.lx, self.ly = nx, ny
        if note:
            self.say(note)
        if (nx, ny) in level.exits:
            self.say(f"There are {T.TILES[tile].name} here.")
        elif self.indoors != was_inside and not level.underground:
            self.say("You step inside." if self.indoors else "You step outside.")
        if level.items.get((nx, ny)):
            self.say(f"There's {items.describe_pile(level.items[(nx, ny)])} here (g picks it up).")
        self.pass_time(self.step_minutes(tile, dx, dy) * slow / 60, float(T.SOAK[tile]),
                       effort=step_effort(tile) + extra)
        return True

    def at_work(self, a) -> bool:
        if a.animal or a.doing == "asleep":
            return False
        job = people.JOBS[a.kind]
        return job.start <= float(hour_of_day(self.minutes)) < job.end

    def meet(self, someone) -> bool:
        """Walking into someone: pet them, trade, or talk and step past. Returns whether you
        go on into their place."""
        level = self.level
        if someone.kind in PETS:
            self.say(people.talk(someone, level, self))
            self.pass_time(1 / 60)
            return False
        shop = shops.for_actor(someone, self) if self.at_work(someone) else None
        if shop is not None:
            someone.met = True
            self.say(f'{someone.name.split()[0]}: "{shop.greeting}"')
            self.shop = shop
            self.autopath = False
            return False
        self.say(people.talk(someone, level, self))
        if someone.kind == "lumberjack" and self.at_work(someone):
            self.say(f'{someone.name.split()[0]}: "Fell a tree or two and I\'ll buy the logs, '
                     f'{shops.LOG_PRICE} coins apiece. My axe is by the house."')
        someone.x, someone.y = self.lx, self.ly
        someone.goal, someone.path = None, []
        return True

    # ------------------------------------------------------------- things to do

    def attack(self, c) -> bool:
        """Strikes a creature with whatever you're holding."""
        wild.player_attack(self.level, self, c, self.rng)
        self.autopath = False
        self.pass_time(ATTACK_MINUTES / 60, effort=ATTACK_EFFORT)
        return False

    def heal(self, amount: float) -> None:
        """Health back (from food or sleep), as far as a fever lets it come."""
        p = self.player
        s = p.sickness
        top = 100.0
        if s is not None and s.shown and not s.treated:
            top = p.health
        elif s is not None and s.treated:
            top = max(p.health, sickness.TREATED_CAP)
        p.health = min(top, p.health + amount)

    def eat(self, kind: str) -> str:
        p = self.player
        if not p.inventory.take(kind):
            return f"You haven't got any {items.KINDS[kind].plural}."
        health, stamina = items.KINDS[kind].meal
        self.heal(health)
        p.stamina = min(100.0, p.stamina + stamina)
        self.pass_time(MEAL_MINUTES / 60)
        return f"You eat {items.amount(kind, 1)}."

    def eat_soup(self) -> str:
        """A bowl of the innkeeper's hot soup: warming, and the cure for wolf fever."""
        p = self.player
        p.body = max(p.body, min(NORMAL, p.body + 1.5))
        p.stamina = min(100.0, p.stamina + 15)
        text = sickness.soup(p)
        self.heal(5)
        self.pass_time(SOUP_MINUTES / 60)
        return text

    def open_barrel(self, x: int, y: int) -> None:
        """What's in a barrel: take things out, put things in."""
        level = self.level
        store = level.stores.get((x, y))
        if store is None:
            store = level.stores[(x, y)] = items.fill_barrel(level, x, y)
        bag = self.player.inventory

        def shift(src, dst, kind, verb):
            n = src.count(kind)
            src.take(kind, n)
            dst.add(kind, n)
            return f"You {verb} {items.amount(kind, n)}."

        def take_all(e):
            got = dict(store)
            for k, n in got.items():
                bag.add(k, n)
            store.clear()
            return f"You take {items.describe_pile(got)}."

        def build(e):
            picker.greeting = ("Inside: " + items.describe_pile(store) + ".") if store else "It's empty."
            opts = [shops.Option(f"Take {items.amount(k, n)}", lambda e, k=k: shift(store, bag, k, "take"), stay=True)
                    for k, n in store.items()]
            if len(store) > 1:
                opts.append(shops.Option("Take everything", take_all, stay=True))
            opts += [shops.Option(f"Put in {items.amount(k, n)}", lambda e, k=k: shift(bag, store, k, "put in"),
                                  stay=True) for k, n in bag.items() if k != "room key"]
            return opts

        picker = shops.Picker("A barrel", build, leave="Close the barrel", leave_text="You close the barrel.")
        picker.refresh(self)
        self.shop = picker
        self.autopath = False

    def use_menu(self) -> None:
        """e: everything you can do here and next to you."""
        if self.level is None:
            self.say("Step down into the region (Enter) first.")
            return
        opts = []
        for (dx, dy), where in DIRECTIONS.items():
            x, y = self.lx + dx, self.ly + dy
            if self.level.in_bounds(x, y):
                suffix = "" if (dx, dy) == (0, 0) else f" ({where})"
                opts += [shops.Option(o.label + suffix, o.do, o.ok) for o in self.options_at(x, y)]
        if not opts:
            self.say("There's nothing to use here.")
            return
        menu = shops.Picker("What will you do?", lambda e: opts)
        menu.refresh(self)
        self.shop = menu
        self.autopath = False

    def click_at(self, x: int, y: int) -> bool:
        """A left click on the map: the use menu for what's there, if there's anything to do
        with it. Returns whether it opened."""
        if self.level is None or not self.level.in_bounds(x, y) or not self.level.explored[x, y]:
            return False
        opts = self.options_at(x, y)
        if not opts:
            return False
        lines = self.describe(x, y)
        look = shops.Option("Look", lambda e: "You see: " + ", ".join(lines) + ".")
        menu = shops.Picker(lines[0] if lines else "There", lambda e: opts + [look])
        menu.refresh(self)
        self.shop = menu
        self.autopath = False
        return True

    def options_at(self, x: int, y: int) -> list:
        """What you could do with what's at (x, y). Each walks you over first if it's out of
        reach."""
        level, p = self.level, self.player
        out = []
        here = (x, y) == (self.lx, self.ly)
        seen = bool(self.local_visible[x, y]) if self.local_visible.shape == level.tiles.shape else False
        go = self.go_do
        beast = wild.creature_at(level, x, y)
        if beast is not None and seen and not here:
            out.append(shops.Option(f"Attack the {beast.name}",
                                    lambda e, c=beast: go(c.x, c.y, lambda e: e.attack(c), who=c)))
        a = people.actor_at(level, x, y)
        if a is not None and seen and not here:
            first = a.name.split()[0]
            if a.kind in PETS:
                out.append(shops.Option(f"Pet {a.name}", lambda e, a=a: go(a.x, a.y, lambda e: e.talk_to(a), who=a)))
            elif not a.animal:
                if self.at_work(a) and a.kind in ("lumberjack", "barkeeper", "innkeeper", "shopkeeper"):
                    out.append(shops.Option(f"Trade with {first}",
                                            lambda e, a=a: go(a.x, a.y, lambda e: e.trade_with(a), who=a)))
                out.append(shops.Option(f"Talk to {first}", lambda e, a=a: go(a.x, a.y, lambda e: e.talk_to(a), who=a)))
        tile = int(level.tiles[x, y])
        if tile == T.BARREL:
            out.append(shops.Option("Open the barrel", lambda e: go(x, y, lambda e: e.open_barrel(x, y))))
        if tile in (T.BED, T.BEDROLL):
            inn = level.key[0] == "inn_up" and p.inventory.count("room key")
            out.append(shops.Option("Sleep in the bed till morning" if inn else f"Rest on the {T.TILES[tile].name}",
                                    lambda e: go(x, y, lambda e: e.rest(), on=True)))
        pile = level.items.get((x, y))
        if pile:
            out.append(shops.Option(f"Pick up {items.describe_pile(pile)}",
                                    lambda e: go(x, y, lambda e: e.pick_up(x, y))))
        if (x, y) in level.exits:
            way = "down" if tile == T.STAIRS_DOWN else "up"
            out.append(shops.Option(f"Take the stairs {way}", lambda e: go(x, y, lambda e: e.use_stairs(), on=True)))
        if tile in trees.KIND and p.inventory.count("axe") and beast is None:
            out.append(shops.Option("Fell the tree", lambda e: go(x, y, lambda e: e.chop(x, y))))
        if here:
            out += self.own_options()
        return out

    def own_options(self) -> list:
        """What you can do with what you carry, and where you stand."""
        p, level = self.player, self.level
        bag = p.inventory
        out = []
        tile = int(level.tiles[self.lx, self.ly])
        if bag.count("shovel") and T.DIGGABLE[tile] and not level.underground:
            out.append(shops.Option("Dig here", lambda e: e.dig()))
        for kind in items.FOODS:
            if bag.count(kind):
                out.append(shops.Option(f"Eat {items.amount(kind, 1)} ({bag.count(kind)})", lambda e, k=kind: e.eat(k)))
        held, _ = combat.weapon_of(p)
        for kind in combat.WEAPONS:
            if bag.count(kind) and kind != held:
                out.append(shops.Option(f"Wield the {kind}", lambda e, k=kind: combat.wield(e.player, k)))
        if held:
            out.append(shops.Option(f"Put away the {held}", lambda e: combat.wield(e.player, None)))
        on = combat.worn(p)
        for kind in combat.ARMOUR:
            if bag.count(kind):
                if kind in on.values():
                    out.append(shops.Option(f"Take off the {kind}", lambda e, k=kind: combat.take_off(e.player, k)))
                else:
                    out.append(shops.Option(f"Wear the {kind}", lambda e, k=kind: combat.wear(e.player, k)))
        if tile not in (T.BED, T.BEDROLL):
            out.append(shops.Option(f"Rest {REST_HOURS} hours", lambda e: e.rest()))
        return out

    def go_do(self, x: int, y: int, do, on: bool = False, who=None):
        """Does `do` now if (x, y) is in reach (or underfoot, if `on`), or walks you there first."""
        if (on and (x, y) == (self.lx, self.ly)) or (not on and max(abs(x - self.lx), abs(y - self.ly)) <= 1):
            return do(self)
        goal = (x, y)
        if not on and not self.level.walkable(x, y):        # beside it, the nearest side
            sides = [(x + dx, y + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)
                     if (dx or dy) and self.level.walkable(x + dx, y + dy) and self.level.explored[x + dx, y + dy]]
            if not sides:
                return "You can't get at it."
            goal = min(sides, key=lambda c: max(abs(c[0] - self.lx), abs(c[1] - self.ly)))
        if not self.route(*goal):
            return "You don't know a way there."
        self.pending = (x, y, do, on, who)
        self.goal, self.autopath, self.disturbed = goal, True, False
        return None

    def try_pending(self) -> bool:
        """On a walk to do something: does it once you're there. Returns whether it's done (or
        can't be)."""
        if self.pending is None:
            return False
        x, y, do, on, who = self.pending
        if who is not None:
            if who not in self.level.actors and who not in self.level.creatures:
                self.pending = None
                return True
            x, y = who.x, who.y
            self.goal = (x, y)
            self.pending = (x, y, do, on, who)
        if (on and (x, y) == (self.lx, self.ly)) or (not on and max(abs(x - self.lx), abs(y - self.ly)) <= 1):
            self.pending = None
            text = do(self)
            if text:
                self.say(text)
            return True
        return False

    def talk_to(self, a) -> None:
        self.say(people.talk(a, self.level, self))
        if a.kind in PETS:
            self.pass_time(1 / 60)

    def trade_with(self, a) -> None:
        shop = shops.for_actor(a, self) if self.at_work(a) else None
        if shop is None:
            self.say(f"{a.name.split()[0]} has nothing to trade with you just now.")
            return
        a.met = True
        self.say(f'{a.name.split()[0]}: "{shop.greeting}"')
        self.shop = shop
        self.autopath = False

    def chop(self, x: int, y: int) -> bool:
        """Fells the tree at (x, y) with your axe."""
        level = self.level
        logs = trees.fell(level, x, y)
        level._walk_costs = None
        self.player.inventory.add("log", logs)
        self.say(f"You fell the tree with your axe and cut {items.amount('log', logs)}.")
        self.pass_time(CHOP_MINUTES / 60, effort=CHOP_EFFORT)
        return False

    def pick_up(self, x: int | None = None, y: int | None = None) -> None:
        if self.level is None:
            self.say("There's nothing to pick up out here; step down into the region (Enter).")
            return
        x, y = (self.lx, self.ly) if x is None else (x, y)
        got = items.pick_up(self.level, x, y, self.player.inventory)
        if not got:
            self.say("There's nothing here to pick up.")
            return
        self.say(f"You pick up {items.describe_pile(got)}.")
        for kind in dict.fromkeys(got):
            if items.KINDS[kind].note:
                self.say(f"The {items.KINDS[kind].name}: {items.KINDS[kind].note}.")

    def dig(self) -> None:
        """Digs where you stand, for whatever's buried there. The ground stays at its height;
        the hole is just turned earth, and greens over after rain."""
        level = self.level
        if level is None:
            self.say("Step down into the region (Enter) to find somewhere to dig.")
            return
        if not self.player.inventory.count("shovel"):
            self.say("You need a shovel to dig.")
            return
        tile = int(level.tiles[self.lx, self.ly])
        if tile == T.DUG:
            self.say("You've already dug here.")
            return
        if level.underground or not T.DIGGABLE[tile]:
            self.say(f"You can't dig into the {T.TILES[tile].name}.")
            return
        level.dug[(self.lx, self.ly)] = [tile, None]
        level.tiles[self.lx, self.ly] = T.DUG
        level._walk_costs = None
        found = level.buried.pop((self.lx, self.ly), None)
        if found:
            self.player.inventory.add(*found)
            self.say(f"You dig a hole and find {items.amount(*found)}!")
        else:
            self.say("You dig a hole, but there's nothing down there.")
        self.pass_time(DIG_MINUTES / 60, effort=DIG_EFFORT)

    def regrow(self) -> None:
        """Dug ground waits for rain, and then greens over."""
        for level in self.levels.values():
            if not level.dug or level.underground:
                continue
            raining = None
            grew = False
            for spot, record in list(level.dug.items()):
                if record[1] is None:
                    if raining is None:
                        c = self.now if level is self.level else self.climate.at(*level.region, self.minutes)
                        raining = c.raining
                    if raining:
                        record[1] = self.minutes
                elif self.minutes - record[1] >= REGROW_MINUTES:
                    was = record[0]
                    level.tiles[spot] = T.GRASS if was in (T.GRASS, T.TALL_GRASS, T.DRY_GRASS) else was
                    del level.dug[spot]
                    level._walk_costs = None
                    grew = True
            if grew and level is self.level:
                self.say("The ground you dug has grown back over.")

    def rent_room(self) -> None:
        """Paid for a room: the key's good till mid-morning."""
        day = int(self.minutes // MINUTES_PER_DAY)
        hour = float(hour_of_day(self.minutes))
        self.room_until = (day + (1 if hour >= ROOM_UNTIL_HOUR - 4 else 0)) * MINUTES_PER_DAY + \
            ROOM_UNTIL_HOUR * MINUTES_PER_HOUR
        self.say("The rooms are upstairs. Any free bed is yours tonight.")

    def danger(self) -> bool:
        """Whether something's about that won't let you rest (and says so)."""
        if self.level is None:
            return False
        about = wild.threatening(self.level, self)
        if about:
            self.say(f"You can't rest with {wild.a_name(about[0].name)} about!")
        return bool(about)

    def rest(self) -> None:
        level = self.level
        p = self.player
        if self.danger():
            return
        if level is not None and level.key[0] == "inn_up" and level.tiles[self.lx, self.ly] == T.BED:
            if not p.inventory.count("room key"):
                self.say("These beds are for paying guests. The barkeeper downstairs lets them.")
                return
            hours = (WAKE_HOUR - float(hour_of_day(self.minutes))) % 24 or 24
            self.say(f"You sleep soundly in a warm bed {level.name[0].lower()}{level.name[1:]}.")
            self.wait(hours)
            if p.alive:
                p.stamina, p.wet = 100.0, 0.0
                self.heal(30)
                self.say("You wake well rested.")
                for text in sickness.slept(p, self.minutes, hours):
                    self.say(text)
            return
        self.say(f"You rest for {REST_HOURS} hours.")
        self.wait(REST_HOURS)
        if p.alive:
            for text in sickness.slept(p, self.minutes, REST_HOURS):
                self.say(text)

    def cross_border(self, dx: int, dy: int, nx: int, ny: int) -> bool:
        level = self.level
        if not level.surface:
            return False
        rx = self.player.x + (-1 if nx < 0 else 1 if nx >= level.width else 0)
        ry = self.player.y + (-1 if ny < 0 else 1 if ny >= level.height else 0)
        if not self.world.in_bounds(rx, ry):
            self.say("You can't go any further that way.")
            return False
        nxt = self.get_level(("region", rx, ry))
        lx, ly = nx % nxt.width, ny % nxt.height
        tile = int(nxt.tiles[lx, ly])
        if not T.WALK[tile]:
            self.say("The water is too deep to wade." if tile == T.DEEP_WATER
                     else f"The {T.TILES[tile].name} is in the way.")
            return False
        self.player.x, self.player.y = rx, ry
        self.level, self.lx, self.ly = nxt, lx, ly
        self.say(f"You cross into {nxt.name}.")
        if self.site is not None:
            self.visit()
        self.pass_time(self.step_minutes(tile, dx, dy) / 60, float(T.SOAK[tile]), effort=step_effort(tile))
        return True

    def use_stairs(self, way: str | None = None) -> bool:
        """Takes the stairs you're standing on. `way` is "down", "up" or None for either."""
        level = self.level
        key = level.exits.get((self.lx, self.ly))
        tile = int(level.tiles[self.lx, self.ly])
        if key is None or (way == "down" and tile != T.STAIRS_DOWN) or (way == "up" and tile != T.STAIRS_UP):
            if way == "up" and level.surface and key is None:
                return self.leave_region()
            if key is None and tile in (T.STAIRS_DOWN, T.STAIRS_UP):  # (the arena's gallery)
                self.say("These stairs don't lead anywhere.")
                return False
            self.say("There are no stairs here." if key is None else f"These stairs go {'down' if tile == T.STAIRS_DOWN else 'up'}.")
            return False
        nxt = self.get_level(key)
        if level.key[0] == "arena":           # the arena's buildings lead back to the arena
            for pos, back in list(nxt.exits.items()):
                if back == ("region", *nxt.region):
                    nxt.exits[pos] = level.key
        self.level = nxt
        self.lx, self.ly = nxt.arrival(level.key) or nxt.nearest_walkable(nxt.width / 2, nxt.height / 2)
        self.say(f"You climb {'down' if tile == T.STAIRS_DOWN else 'up'} to {nxt.name}.")
        if nxt.lookout and ("lookout", *nxt.region) not in self.visited:
            self.visited.add(("lookout", *nxt.region))
            self.learn_around(*nxt.region, LOOKOUT_RANGE)
            self.say("From up here you can see for miles around; the land shows on your map.")
        self.pass_time(1 / 60)
        return True

    # ------------------------------------------------------------- the mouse

    def known(self) -> np.ndarray:
        """The cells you know on the current map: explored, or the whole world map when revealed."""
        if self.level is not None:
            return self.level.explored
        return self.explored | self.reveal

    def in_map(self, x: int, y: int) -> bool:
        return self.level.in_bounds(x, y) if self.level is not None else self.world.in_bounds(x, y)

    def describe(self, x: int, y: int) -> list[str]:
        """What you know about a cell of the current map, a short line at a time."""
        if not self.in_map(x, y):
            return []
        if not self.known()[x, y]:
            return ["Unexplored"]
        return self.describe_local(x, y) if self.level is not None else self.describe_world(x, y)

    def describe_local(self, x: int, y: int) -> list[str]:
        level = self.level
        tile = T.TILES[level.tiles[x, y]]
        here = (x, y) == (self.lx, self.ly)
        name = tile.name
        if tile.id in T.GRAINS:
            name += ", " + people.crop_words(self.crop_stage)
        lines = ["You, on " + name if here else name.capitalize()]
        pile = level.items.get((x, y))
        if pile:
            lines.insert(0, items.describe_pile(pile).capitalize() + " lying here")
        dh = int(level.elev[x, y]) - int(level.elev[self.lx, self.ly])
        if here and level.elev.max() > level.elev.min():
            lines.append(f"Height {int(level.elev[x, y])} ({int(level.elev[x, y]) * elevation.LEVEL_M:.0f} m)")
        elif dh:
            lines.append(f"{abs(dh)} level{'s' if abs(dh) != 1 else ''} {'above' if dh > 0 else 'below'} you")
        if (x, y) in level.dug:
            lines.append("Greening over" if level.dug[(x, y)][1] is not None else "Freshly dug")
        someone = people.actor_at(level, x, y)
        if someone is not None and self.local_visible[x, y] and not here:
            lines = people.describe(someone) + lines
        beast = wild.creature_at(level, x, y)
        if beast is not None and self.local_visible[x, y] and not here:
            lines = wild.describe(beast) + lines
        if level.stores.get((x, y)) is not None and tile.id == T.BARREL:
            lines.append("Holds " + items.describe_pile(level.stores[(x, y)]))
        inside = level.building_at(x, y)
        if inside is not None and inside.name:
            lines.append(f"{'In' if T.ROOF[tile.id] else 'At'} {inside.name}")
        key = level.exits.get((x, y))
        if key is not None:
            dest = self.levels.get(key)
            lines.append(f"Leads to {dest.name if dest else WHERE_STAIRS_GO[key[0]]}")
        kind = int(level.canopy[x, y])
        if kind:
            look = self.foliage if kind == trees.BROADLEAF else "green"
            leaves = {"green": "leaves", "budding": "budding leaves", "autumn": "autumn leaves",
                      "bare": "bare boughs"}[look]
            lines.append(f"{'A' if tile.id in trees.TRUNKS else 'Under a'} {LEAF_NAMES[kind]} tree, {leaves}")
        if not tile.walk:
            lines.append("Too deep to wade" if tile.id == T.DEEP_WATER else "Blocks the way")
        else:
            if tile.roof:
                lines.append("Under a roof")
            if tile.soak:
                lines.append("You'd get wet")
            if tile.minutes >= 1.2:
                lines.append("Slow going")
            elif tile.minutes <= 0.45:
                lines.append("Easy going")
        if not here:
            steps = max(abs(x - self.lx), abs(y - self.ly))
            lines.append(f"{steps} step{'s' if steps != 1 else ''} away")
            if not self.local_visible[x, y]:
                lines.append("Remembered")
        return lines

    def describe_world(self, x: int, y: int) -> list[str]:
        w = self.world
        biome = B.BIOMES[w.biome[x, y]]
        site = w.site_at.get((x, y))
        lines = []
        if (x, y) == (self.player.x, self.player.y):
            lines.append("You are here")
        if site is not None:
            lines.append(f"{site.name}, {site.kind}{' (port)' if site.port else ''}")
        lines.append(biome.name + "".join(f", {t}" for t, on in (("river", w.river[x, y]), ("road", w.road[x, y])) if on))
        if biome.id not in B.WATER:
            lines.append(f"Alt {max(0, w.elevation[x, y]):.0f} m")
        if self.visible[x, y]:
            c = self.climate.at(x, y, self.minutes)
            lines.append(f"{c.kind}, {c.air:.0f}°C")
        elif not self.reveal or self.explored[x, y]:
            lines.append("Remembered")
        if (x, y) != (self.player.x, self.player.y):
            hours = self.route_hours(x, y)
            lines.append("No known way there" if hours is None else f"About {hours:.0f} h away" if hours >= 1.5
                         else f"About {hours * 60:.0f} min away")
        return lines

    def costs(self) -> np.ndarray:
        """What each known cell costs to cross, for finding a way; 0 where you can't or don't know."""
        if self.level is not None:
            t = self.level.tiles
            cost = np.round(T.MINUTES[t] * 10 + T.SOAK[t] * WET_DETOUR).astype(np.int32)  # keep dry if you can
            cost[~T.WALK[t]] = 0
        else:
            w = self.world
            cost = travel_cost(w.biome, w.river)
            cost[w.road & (cost > 0)] = round(ROAD_TRAVEL * 10)
        cost[~self.known()] = 0
        return cost

    def route(self, x: int, y: int) -> list[tuple[int, int]]:
        """The quickest way to (x, y) over cells you know, not counting where you stand; empty if
        there's none."""
        start = (self.lx, self.ly) if self.level is not None else (self.player.x, self.player.y)
        if not self.in_map(x, y) or (x, y) == start:
            return []
        cost = self.costs()
        if not cost[x, y]:
            return []
        cost[start] = max(1, int(cost[start]))
        if self.level is not None:          # no steps too steep to climb
            graph = tcod.path.CustomGraph(cost.shape)
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    if dx or dy:
                        graph.add_edge((dx, dy), 3 if dx and dy else 2, cost=cost,
                                       condition=elevation.passable(self.level.elev, self.level.tiles, dx, dy))
        else:
            graph = tcod.path.SimpleGraph(cost=cost, cardinal=2, diagonal=3)
        finder = tcod.path.Pathfinder(graph)
        finder.add_root(start)
        path = finder.path_to((x, y)).tolist()
        return [tuple(p) for p in path[1:]]

    def route_hours(self, x: int, y: int) -> float | None:
        """Roughly how long the way to an overworld region takes, in hours."""
        path = self.route(x, y)
        if not path:
            return None
        cost = self.costs()
        return sum(int(cost[p]) for p in path) / 10

    def step_toward(self, x: int, y: int) -> bool:
        """One step along the way to (x, y). Returns whether you moved."""
        if not self.player.alive:
            return False
        path = self.route(x, y)
        if not path:
            return False
        here = (self.lx, self.ly) if self.level is not None else (self.player.x, self.player.y)
        dx, dy = path[0][0] - here[0], path[0][1] - here[1]
        beast = wild.creature_at(self.level, *path[0]) if self.level is not None else None
        if beast is not None:                 # a walk never starts a fight
            self.say(f"There's {wild.a_name(beast.name)} in the way.")
            self.disturbed = True
            return False
        return self.move_local(dx, dy) if self.level is not None else self.move(dx, dy)

    # ------------------------------------------------------------- time

    def wait(self, hours: float) -> None:
        if self.player.alive:
            self.pass_time(hours)

    def pass_time(self, hours: float, soak: float = 0.0, effort: float = 0.0) -> None:
        """Runs the clock forward an hour at a time at most, so the weather and your body keep up.
        `effort` is how hard you're working (1 is steady walking, 0 is resting)."""
        p = self.player
        left = hours
        while left > 1e-9 and p.alive:
            dt = min(1.0, left)
            left -= dt
            before, before_time = self.now, time_of_day(self.lat, self.minutes)
            tire(p, dt, effort)
            health_before = p.health
            self.minutes += dt * MINUTES_PER_HOUR
            self.now = self.weather()
            if not self.underground:
                self.news(before, before_time)
            for text in expose(p, dt, self.now, self.shelter, indoors=self.indoors, soak=soak,
                               indoor_air=self.indoor_air):
                self.say(text)
                self.disturbed = True       # a warning about your body stops a walk
            soak = 0.0
            for text in sickness.hour(p, self.minutes, dt, health_before):
                self.say(text)
                self.disturbed = True
            self.regrow()
        if self.room_until is not None and self.minutes >= self.room_until:
            self.room_until = None
            if self.player.inventory.take("room key", self.player.inventory.count("room key")):
                self.say("It's mid-morning: your room key goes back to the barkeeper.")
        if self.level is not None:
            if p.alive:
                self.level.scent[self.lx, self.ly] = self.minutes     # wolves can follow you too
            people.advance(self.level, self.minutes, self)
            wild.advance(self.level, self.minutes, self, self.rng)
        self.update_view()
        if self.level is not None:
            wild.notice(self.level, self)

    def news(self, before: Conditions, before_time: str) -> None:
        now, now_time = self.now, time_of_day(self.lat, self.minutes)
        if now_time != before_time and now_time in LIGHT_NEWS:
            self.say(LIGHT_NEWS[now_time])
            self.disturbed = True
        if now.kind == before.kind:
            return
        self.disturbed = True
        if now.kind in WEATHER_NEWS:
            self.say(WEATHER_NEWS[now.kind])
        elif before.raining:
            self.say("The rain stops.")
        elif before.snowing:
            self.say("The snow stops.")
        elif before.kind == "Fog":
            self.say("The fog lifts.")
        elif now.kind == "Clear":
            self.say("The sky clears.")

    def update_view(self) -> None:
        p = self.player
        if self.level is not None:
            level = self.level
            r = self.sight_radius()
            fire = firelight(level)[0] > SEEN_FROM_AFAR
            far = bool(fire.any())       # you can see firelit places beyond your own sight
            seen = tcod.map.compute_fov(T.SEE[level.tiles], (self.lx, self.ly), 0 if far else r,
                                        algorithm=tcod.constants.FOV_SYMMETRIC_SHADOWCAST)
            xs, ys = np.ogrid[: level.width, : level.height]
            round_on_screen = (xs - self.lx) ** 2 + (2 * (ys - self.ly)) ** 2 <= r * r + 1  # rows are twice as tall
            seen &= round_on_screen | fire
            if level.elev.max() > level.elev.min():      # the lie of the land hides what's behind it
                seen = elevation.sightlines(level.elev, (self.lx, self.ly), seen)
            self.local_visible = seen
            level.explored |= self.local_visible
            return
        transparent = ~B.BLOCKS_VIEW[self.world.biome]
        transparent[p.x, p.y] = True
        self.visible = tcod.map.compute_fov(transparent, (p.x, p.y), self.sight_radius(),
                                            algorithm=tcod.constants.FOV_SYMMETRIC_SHADOWCAST)
        self.visible = elevation.world_sightlines(self.world, (p.x, p.y), self.visible)
        self.explored |= self.visible

    # ------------------------------------------------------------- keys

    def close_box(self) -> None:
        """Closes the shop, menu or barrel that's open."""
        modal, self.shop = self.shop, None
        if modal is not None and modal.leave_text:
            self.say(modal.leave_text)

    def handle_key(self, sym: KeySym, mod: int = 0) -> bool:
        """Does what a key press means. Returns False when the game should close."""
        shift = bool(mod & Modifier.SHIFT)
        if sym == FULLSCREEN_KEY or sym in ENTER_KEYS and mod & Modifier.ALT:
            self.menu.toggle_fullscreen()
            return True
        if self.menu.open:
            result = self.menu.handle_key(sym, mod)
            if result == "title":
                self.to_title = True
            return result != "quit"
        self.pending = None
        if self.shop is not None:
            modal = self.shop
            if not modal.handle_key(sym, self) and self.shop is modal:
                self.close_box()
            return True
        if sym == MENU_KEY:
            self.menu.show("pause")
            self.autopath = False
            return True
        if self.panels.handle_key(sym):
            return True
        if sym == OVERLAY_KEY and self.level is None:
            self.overlay = (self.overlay + 1) % len(OVERLAYS)
        elif sym == OVERLAY_KEY:
            self.relief = not self.relief
            self.say("You take in the lie of the land." if self.relief else "You look about you.")
        elif sym == BAG_KEY:
            self.panels.show("inv")
        elif sym == PICKUP_KEY and self.player.alive:
            self.pick_up()
        elif sym == USE_KEY and self.player.alive:
            self.use_menu()
        elif sym == DIG_KEY and self.player.alive:
            self.dig()
        elif sym == REVEAL_KEY:
            if self.level is None:
                self.reveal = not self.reveal
            else:
                self.level.explored[:] = True
        elif sym == LAYER_KEY and self.level is not None:
            self.treetops = not self.treetops
            self.say("You look up at the treetops." if self.treetops else "You look at the ground beneath the trees.")
        elif not self.player.alive:
            pass
        elif sym == KeySym.PERIOD and shift or sym in ENTER_KEYS:   # > or Enter
            if self.level is None:
                self.enter_region()
            else:
                self.use_stairs("down" if sym == KeySym.PERIOD else None)
        elif sym == KeySym.COMMA and shift:                         # <
            if self.level is not None:
                self.use_stairs("up")
        elif sym in MOVES:
            if self.level is None:
                self.move(*MOVES[sym])
            else:
                self.move_local(*MOVES[sym])
        elif sym in WAIT_KEYS:
            if not self.danger():
                self.wait(1)
        elif sym == REST_KEY:
            self.rest()
        return True
