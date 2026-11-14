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
Rain soaks the ground (game/erosion.py): bare earth turns to mud and dries out again, and heavy
rain washes soil down bare slopes onto the grass below.

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
you walk over to first. q opens the equipment menu: what you have on in each place, what it
all adds up to, and what you could change it for (game/gear.py).

Climbing gear lets you climb onto boulders and rock outcrops (slow, tiring, and you can slip)
and up and down rises too steep to walk. From the top of a rock you see further.

Cold water chills you a little every turn you're in it, and for 30-45 turns after (player.chill).
` opens the dev console (game/devconsole.py): god mode, items, creatures, the clock, the weather.

Local maps are shown whole from the start (m: only what you've seen). Local maps are built when first visited and kept, with what you've explored, for the rest of
the game. The weather and temperature come from the region you're in either way.
"""
from __future__ import annotations

import random

import numpy as np
import tcod
from tcod.event import KeySym, Modifier

from . import biomes as B
from . import carts
from . import combat
from . import devconsole
from . import elevation
from . import eras
from . import erosion
from . import gear
from . import guards
from . import items
from . import people
from . import shop as shops
from . import sickness
from . import tiles as T
from . import trees
from . import wild
from .farming import PETS, crop_stage
from .light import SEEN_FROM_AFAR, firelight
from .climate import (DAYS_PER_SEASON, DAYS_PER_YEAR, MINUTES_PER_DAY, MINUTES_PER_HOUR, Climate, Conditions, hour_of_day,
                      latitude, season_offset, shelter_at, snow_cover, time_of_day)
from .level import Level
from .localgen import LOCAL_H, LOCAL_W, make_level, node_local
from .player import NORMAL, Player, chill, expose, tire
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
SKIP_KEY = KeySym.T       # the time skip: pass the ages (game/eras.py)
FULLSCREEN_KEY = KeySym.F11
OVERLAYS = ["Normal", "Elevation", "Temperature", "Moisture", "Weather"]
PICKUP_KEY, DIG_KEY, BAG_KEY, USE_KEY = KeySym.G, KeySym.X, KeySym.I, KeySym.E
GEAR_KEY = KeySym.Q       # the equipment menu
ATTACK_MINUTES, ATTACK_EFFORT = 0.5, 1.5  # a blow
MEAL_MINUTES = 5
SOUP_MINUTES = 15
DIRECTIONS = {(0, 0): "here", (0, -1): "north", (0, 1): "south", (-1, 0): "west", (1, 0): "east",
              (-1, -1): "north-west", (1, -1): "north-east", (-1, 1): "south-west", (1, 1): "south-east"}
CHOP_MINUTES, CHOP_EFFORT = 20, 2.5     # felling a tree
DIG_MINUTES, DIG_EFFORT = 30, 2.5       # digging a hole
WASH_NEWS_MINUTES = 6 * 60              # how often you're told about the rain washing soil down
GROUNDWATER_STRIKE = 0.45   # a hole over full groundwater fills with water this often
REGROW_MINUTES = 4 * 60                 # dug ground greens over this long after rain first falls on it
WAKE_HOUR = 7                           # sleeping in a bed you've paid for, you sleep till then
ROOM_UNTIL_HOUR = 10                    # and give the key back by then

START_MINUTES = 8 * MINUTES_PER_HOUR  # 08:00 on the first day of spring
YEAR_MINUTES = DAYS_PER_YEAR * MINUTES_PER_DAY
ROAD_TRAVEL = 0.6       # hours per region along a road
RIVER_TRAVEL = 1.0      # extra hours to ford a river where there's no bridge
RIVER_SOAK = 50         # wetness from wading one
NIGHT_SLOWDOWN = 1.5    # travel takes this much longer in the dark
SNOW_SLOWDOWN = {"Snow": 1.3, "Blizzard": 1.8}
SNOWY_GROUND = 1.4      # local steps through lying snow
REST_HOURS = 8
TURN_MINUTES = 6        # a long wait counts as a turn per this many minutes (a step or a blow is one)
WADING = (T.WATER, T.RICE)   # tiles where you stand in water
RIVER_FORD_TURNS = 10   # turns in the water fording a river on the overworld
LANTERN = 6             # how many columns your lantern lights, underground or on a dark night
WET_DETOUR = 4          # a walk to the pointer goes this many tenths of a minute round per point of wetting
LOOKOUT_RANGE = 12     # regions you can see from the top of a tower
ABOVE_GROUND = ("tower", "inn_up")     # floors built over a building: the ground shows around them
LOOKOUT_SIGHT = 1.5    # how much further you see the ground from a rooftop than standing on it
LOCAL_KNOWLEDGE = {"city": 20, "town": 14, "village": 8, "inn": 6, "fort": 10}  # regions around a settlement its people tell you about
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


def forced(c: Conditions, kind: str) -> Conditions:
    """The weather made to be `kind` (the dev console's weather command)."""
    cloud, precip, fog = {"clear": (0.1, 0.0, 0.0), "cloudy": (0.5, 0.0, 0.0), "overcast": (0.8, 0.0, 0.0),
                          "fog": (0.5, 0.0, 0.8), "rain": (0.9, 0.45, 0.0), "storm": (1.0, 0.9, 0.0),
                          "snow": (0.9, 0.45, 0.0), "blizzard": (1.0, 0.9, 0.0)}[kind]
    air, wind = c.air, c.wind
    if kind in ("snow", "blizzard"):
        air = min(air, -2.0)
        wind = max(wind, 45.0) if kind == "blizzard" else wind
    elif kind in ("rain", "storm"):
        air = max(air, 11.0 if kind == "storm" else 2.0)
    light = c.light * (1 - 0.4 * precip - 0.3 * fog)
    return Conditions(air=air, cloud=cloud, precip=precip, wind=wind, fog=fog,
                      light=float(np.clip(light, 0.04, 1.0)), kind=kind.capitalize())


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
        self.washed_said = -1e9            # when you were last told the rain washed mud down
        self.skip_request: tuple | None = None   # (years, change): a time skip main.py is to run
        self.local_visible = np.zeros((1, 1), dtype=bool)
        self.below_visible: np.ndarray | None = None   # the ground you can see from a rooftop
        self.reveal_local = True           # local maps shown whole from the moment you enter (m toggles)
        self.paused = False                # the dev console's time pause: the clock stands still
        self.forced_weather: str | None = None   # and its weather override
        self.console = devconsole.DevConsole(self)   # ` : the dev console
        self.riding = None                 # a cart ride under way (carts.Ride): main.py moves it on
        self.update_view()

    @classmethod
    def new(cls, seed: int | None = None, world: World | None = None,
            spawn: tuple[int, int] | None = None) -> Engine:
        """A fresh world, starting in its best town, or in region `spawn` if one was picked
        (Create a World). The same seed makes the same world (pass `world` if it's already been
        generated from that seed)."""
        if world is None:
            world = generate(random.randrange(2**31) if seed is None else seed)
        start = next((s for s in world.sites if s.kind == "town"), None) or \
            next((s for s in world.sites if s.settled), None)
        if spawn is not None and world.walkable(*spawn):
            x, y = spawn
            site = world.site_at.get((x, y))
            where = site.name if site is not None else f"the {B.BIOMES[world.biome[x, y]].name.lower()}"
        elif start is not None:
            x, y, where = start.x, start.y, start.name
        else:  # no settlements at all: the walkable cell nearest the middle
            cells = np.argwhere(B.TRAVEL[world.biome] > 0)
            x, y = min(map(tuple, cells), key=lambda c: (c[0] - world.width // 2) ** 2 + (c[1] - world.height // 2) ** 2)
            where = "the wilds"
        engine = cls(world, Player(int(x), int(y)), START_MINUTES + world.years * YEAR_MINUTES)
        if world.history:
            engine.say(f"It is the year {world.years + 1:,}, after {eras.history_text(world.history)}.")
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
        if self.forced_weather:
            c = forced(c, self.forced_weather)
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
        if not on_road:
            hours *= 1 - gear.footing(self.player) * 0.5     # good boots, off the road
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
                minutes *= 1 - gear.footing(self.player)       # good boots in lying snow
            elif T.MINUTES[tile] >= 0.8:
                minutes *= 1 - gear.footing(self.player)       # and on rough or slow ground
        return minutes

    @property
    def burdened(self) -> float:
        """How much harder every step is for what you have on (1 is nothing heavy)."""
        return 1.0 + gear.burden(self.player)

    @property
    def on_rock(self) -> int | None:
        """The boulder or rock you're standing on top of, if you've climbed one."""
        if self.level is None:
            return None
        tile = int(self.level.tiles[self.lx, self.ly])
        return tile if tile in elevation.CLIMBABLE else None

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
        if w.river[x, y] and not w.road[x, y] and not (site is not None and site.settled):
            self.cold_water(RIVER_FORD_TURNS)          # wading the river
        self.pass_time(hours, soak, effort=OVERWORLD_EFFORT * (0.7 if w.road[x, y] else 1.0) * self.burdened)
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
        elif erosion.catch_up(self.levels[key], self.minutes):
            self.levels[key]._walk_costs = None
        return self.levels[key]

    def ground_below(self):
        """On a floor above the ground (an inn's rooms, a tower): (the ground level, (dx, dy)),
        where tile (x, y) up here lies over (x + dx, y + dy) down there. Otherwise None."""
        level = self.level
        if level is None or level.key[0] not in ABOVE_GROUND:
            return None
        if level.over is None:
            level.over = self.find_ground(level) or ()
        if not level.over:
            return None
        key, dx, dy = level.over
        ground = self.levels.get(key)
        return None if ground is None else (ground, (dx, dy))

    def find_ground(self, level: Level) -> tuple | None:
        """Where a floor above the ground sits: a tower's floors over the tower, centred on its
        stairs; an inn's rooms over the middle of the inn."""
        first = (level.key[0], *level.key[1:3], 1)
        floor = level if level.key == first else self.levels.get(first)
        if floor is None:
            return None
        down = next((k for pos, k in floor.exits.items() if floor.tiles[pos] == T.STAIRS_DOWN), None)
        ground = self.levels.get(down) if down is not None else None
        stairs = ground.arrival(first) if ground is not None else None
        if stairs is None:
            return None
        cx, cy = stairs
        if level.key[0] == "inn_up":
            b = ground.building_at(*stairs)
            if b is not None:
                cx, cy = b.x0 + b.w // 2, b.y0 + b.h // 2
        return down, cx - level.width // 2, cy - level.height // 2

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
        cart = carts.cart_at(self, nx, ny)
        if cart is not None:                  # a cart: ask the carter for a ride
            return self.board(cart.driver)
        tile = int(level.tiles[nx, ny])
        if tile in trees.KIND and self.player.inventory.count("axe"):
            return self.chop(nx, ny)
        if p.noclip:
            self.lx, self.ly = nx, ny
            self.pass_time(self.step_minutes(T.GRASS, dx, dy) / 60)
            return True
        roped = gear.can_climb(p)
        rock = tile in elevation.CLIMBABLE
        if not T.WALK[tile] and not (rock and roped):
            if rock:
                self.say(f"The {T.TILES[tile].name} is in the way. With climbing gear on you could climb it.")
            else:
                self.say("The water is too deep to wade." if tile == T.DEEP_WATER
                         else f"The {T.TILES[tile].name} is in the way.")
            return False
        dh = int(level.elev[nx, ny]) - int(level.elev[self.lx, self.ly])
        graded = tile in elevation.GRADED and int(level.tiles[self.lx, self.ly]) in elevation.GRADED
        ok, slow, extra, note = elevation.climb(dh, graded, roped)
        if not ok:
            self.say(note)
            return False
        from_rock = self.on_rock is not None
        climbing = (rock and not from_rock) or dh > elevation.MOST_STEP     # hand over hand, up
        if (rock or abs(dh) > elevation.MOST_STEP) and p.stamina < gear.CLIMB_STAMINA:
            self.say("You're too worn out to climb.")
            return False
        if rock:
            more_slow, more_effort = elevation.ALONG_ROCK if from_rock else elevation.CLIMBABLE[tile]
            slow, extra = slow * more_slow, extra + more_effort
            if not from_rock:
                note = f"You climb up onto the {T.TILES[tile].name}."
        elif from_rock and not note:
            note = f"You climb down off the {T.TILES[self.on_rock].name}."
        if climbing and self.slipped(T.TILES[tile].name if rock else "rock face", tile, dx, dy):
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
                       effort=(step_effort(tile) + extra) * self.burdened)
        return True

    def slipped(self, what: str, tile: int, dx: int, dy: int) -> bool:
        """A climb can go wrong: you lose your hold, slide back down and hurt yourself. Returns
        whether you slipped."""
        p, c = self.player, self.now
        wet = not self.underground and (c.raining or c.snowing)
        dark = self.underground or c.light < 0.25
        if self.rng.random() >= gear.slip_chance(p, wet, dark):
            return False
        hurt = self.rng.randint(*gear.FALL)
        p.health -= hurt
        self.say(f"You lose your hold on the {what} and slide back down! ({hurt})")
        self.disturbed = True
        if p.health <= 0 and not p.god:
            p.health, p.alive = 0.0, False
            p.cause = "fell while climbing"
            self.say(f"You {p.cause}.")
        self.pass_time(self.step_minutes(tile, dx, dy) * 2 / 60, effort=2.0 * self.burdened)
        return True

    def ride_step(self) -> bool:
        """The cart goes on a region along the road, and the hours that takes pass. Once it's
        there, you're set down in the town's square. Returns whether the ride's still going."""
        r = self.riding
        if r is None:
            return False
        p = self.player
        if r.steps:
            p.x, p.y = r.steps.pop(0)
            self.pass_time(r.each, effort=0.0)
        if not p.alive:
            self.riding = None
            return False
        if r.steps:
            return True
        self.riding = None
        p.x, p.y = carts.stop(r.dest)
        self.enter_region()
        self.say(f"The cart rolls into {r.dest.name}, and {r.driver.split()[0]} sets you down by the square.")
        return False

    def board(self, driver: str) -> bool:
        """Walking into (or clicking on) a cart: the carter's ride menu."""
        menu = carts.ride_menu(driver, self)
        if menu is not None:
            self.say(f'{driver.split()[0]}: "Need a ride?"')
            self.shop = menu
        self.autopath = False
        return False

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
        self.pass_time(ATTACK_MINUTES / 60, effort=ATTACK_EFFORT * self.burdened)
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
        """What's in a barrel or a chest: a tab to take things out, a tab to put things in."""
        level = self.level
        chest = level.tiles[x, y] == T.CHEST
        store = level.stores.get((x, y))
        if store is None:
            fill = items.fill_chest if chest else items.fill_barrel
            store = level.stores[(x, y)] = fill(level, x, y)
        self.shop = shops.Container("a chest" if chest else "a barrel", store, self.player.inventory)
        self.autopath = False

    open_container = open_barrel

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
        if self.level is None or not self.level.in_bounds(x, y) or not self.known()[x, y]:
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
        cart = carts.cart_at(self, x, y)
        if cart is not None and seen:
            out.append(shops.Option(f"Ride with {cart.driver}",
                                    lambda e, d=cart.driver, c=(x, y): go(*c, lambda e: e.board(d))))
        a = people.actor_at(level, x, y)
        if a is not None and seen and not here:
            first = a.name.split()[0]
            if a.kind in PETS:
                out.append(shops.Option(f"Pet {a.name}", lambda e, a=a: go(a.x, a.y, lambda e: e.talk_to(a), who=a)))
            elif not a.animal:
                if self.at_work(a) and a.kind in ("lumberjack", "barkeeper", "innkeeper", "shopkeeper",
                                                  "blacksmith", "carter"):
                    out.append(shops.Option(f"Trade with {first}",
                                            lambda e, a=a: go(a.x, a.y, lambda e: e.trade_with(a), who=a)))
                out.append(shops.Option(f"Talk to {first}", lambda e, a=a: go(a.x, a.y, lambda e: e.talk_to(a), who=a)))
        tile = int(level.tiles[x, y])
        if tile in T.CONTAINERS:
            out.append(shops.Option(f"Open the {T.TILES[tile].name}", lambda e: go(x, y, lambda e: e.open_barrel(x, y))))
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
        on = gear.worn(p)
        for kind in gear.GEAR:
            if bag.count(kind):
                if kind in on.values():
                    out.append(shops.Option(f"Take off the {kind}", lambda e, k=kind: gear.take_off(e.player, k)))
                else:
                    out.append(shops.Option(f"Wear the {kind}", lambda e, k=kind: gear.wear(e.player, k)))
        out.append(shops.Option("Equipment... (q)", lambda e: e.equipment_menu()))
        if tile not in (T.BED, T.BEDROLL):
            out.append(shops.Option(f"Rest {REST_HOURS} hours", lambda e: e.rest()))
        return out

    def equipment_menu(self) -> None:
        """q: what you have on in each place, and what you could put on instead."""
        self.shop = shops.equipment(self)
        self.autopath = False

    def go_do(self, x: int, y: int, do, on: bool = False, who=None):
        """Does `do` now if (x, y) is in reach (or underfoot, if `on`), or walks you there first."""
        if (on and (x, y) == (self.lx, self.ly)) or (not on and max(abs(x - self.lx), abs(y - self.ly)) <= 1):
            return do(self)
        goal = (x, y)
        if not on and not self.level.walkable(x, y):        # beside it, the nearest side
            sides = [(x + dx, y + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)
                     if (dx or dy) and self.level.walkable(x + dx, y + dy) and self.known()[x + dx, y + dy]]
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
        aquifer = self.world.aquifer
        if aquifer is not None and random.random() < aquifer[self.player.x, self.player.y] * GROUNDWATER_STRIKE:
            level.dug.pop((self.lx, self.ly), None)        # it won't green over: it's a pool now
            level.tiles[self.lx, self.ly] = T.WATER
            self.say("Water seeps up into the hole: you've struck groundwater.")
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

    def soak(self, hours: float) -> None:
        """Rain on the local map you're on: the ground soaks it up, bare earth turns to mud, and
        heavy rain washes soil down bare slopes (game/erosion.py)."""
        level = self.level
        if level is None or not level.surface:
            return
        c = self.now
        changed, washed = erosion.weather(level, self.minutes, hours, c.precip if c.raining else 0.0,
                                          c.air, self.rng)
        if changed:
            level._walk_costs = None
        seen = self.local_visible.shape == level.tiles.shape and any(self.local_visible[s] for s in washed)
        if seen and self.minutes - self.washed_said >= WASH_NEWS_MINUTES:
            self.washed_said = self.minutes
            self.say("The rain washes mud down the slope.")

    # ------------------------------------------------------------- the ages

    def menu_result(self, result: str | None) -> None:
        """What a pick in the pause menu asks of the game (keys and clicks alike)."""
        if result == "title":
            self.to_title = True
        elif result == "skip":
            self.skip_request = self.menu.skip_choice()

    def time_skip(self, years: int, change: str, world: World | None = None) -> None:
        """Pass `years` of `change` (game/eras.py): the world is remade as that era leaves it,
        and you wake in it where you stood, or on the nearest land if the sea has come in.
        Every local map is made afresh; settlements that didn't last are ruins."""
        old = self.world
        if world is None:                  # (game/passage.py hands over the one it already made)
            world = generate(old.seed, old.width, old.height, old.history + ((years, change),), old.tweaks,
                             eras.survivors(old, years))
        news = eras.carry_over(old, world)
        self.world, self.climate = world, Climate(world)
        self.minutes += years * YEAR_MINUTES
        self.levels.clear()
        self.level, self.shop, self.pending, self.goal, self.autopath = None, None, None, None, False
        self.room_until = None
        if self.player.inventory.count("room key"):
            self.player.inventory.take("room key", self.player.inventory.count("room key"))
        self.visited.clear()
        self.explored[:] = False
        p = self.player
        if not world.walkable(p.x, p.y):
            cells = np.argwhere(B.TRAVEL[world.biome] > 0)
            i = int(np.argmin((cells[:, 0] - p.x) ** 2 + (cells[:, 1] - p.y) ** 2))
            p.x, p.y = int(cells[i][0]), int(cells[i][1])
        self.now = self.weather()
        self.say(f"{eras.years_text(years)} pass. It is the year {int(self.minutes // YEAR_MINUTES) + 1:,}.")
        self.say(eras.BY_NAME[change].told)
        for line in news:
            self.say(line)
        self.visit()
        self.update_view()

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
        if not T.WALK[tile] and not (tile in elevation.CLIMBABLE and gear.can_climb(self.player)):
            self.say("The water is too deep to wade." if tile == T.DEEP_WATER
                     else f"The {T.TILES[tile].name} is in the way.")
            return False
        self.player.x, self.player.y = rx, ry
        self.level, self.lx, self.ly = nxt, lx, ly
        self.say(f"You cross into {nxt.name}.")
        if self.site is not None:
            self.visit()
        self.pass_time(self.step_minutes(tile, dx, dy) / 60, float(T.SOAK[tile]),
                       effort=step_effort(tile) * self.burdened)
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
            return self.level.explored | self.reveal_local
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
        if tile.id in WADING:
            water = self.water_temp()
            lines.append(f"Water {water:.0f}°C" + (", cold" if water < 21 else ""))
        if (x, y) in level.silt:
            lines.append("Fresh silt, washed down in the rain")
        if level.soil is not None and erosion.HOLDS_WATER[level.tiles[x, y]]:
            wet = float(level.soil[x, y])
            if wet >= erosion.MUDDY_AT:
                lines.append("Waterlogged")
            elif wet >= erosion.FIRM_AT:
                lines.append("Damp ground")
        someone = people.actor_at(level, x, y)
        if someone is not None and self.local_visible[x, y] and not here:
            lines = people.describe(someone) + lines
        cart = carts.cart_at(self, x, y)
        if cart is not None and self.local_visible[x, y]:
            lines = [f"{cart.driver.split()[0]}'s cart", "On the road" if cart.moving else "Waiting by the square",
                     "Walk into it or click: ride"] + lines
        beast = wild.creature_at(level, x, y)
        if beast is not None and self.local_visible[x, y] and not here:
            lines = wild.describe(beast) + lines
        if level.stores.get((x, y)) is not None and tile.id in T.CONTAINERS:
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
        if here and tile.id in elevation.CLIMBABLE:
            lines.append("You've climbed up on top")
        elif not tile.walk and tile.id in elevation.CLIMBABLE:
            lines.append("Climbable with your gear" if gear.can_climb(self.player) else "Climbable with climbing gear")
        elif not tile.walk:
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
        volcano = w.volcano_at.get((x, y))
        if volcano is not None:
            lines.append(f"{volcano.name}, {volcano.activity(w.tweaks.index('Eruptions'))}")
        if w.spring is not None and w.spring[x, y]:
            lines.append("A spring rises here")
        if w.ash is not None and w.ash[x, y] > 0.25:
            lines.append("Fresh ash lies thick")
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
        if self.level is not None and carts.cart_at(self, *path[0]) is not None and self.pending is None:
            self.say("There's a cart in the way.")
            self.disturbed = True
            return False
        return self.move_local(dx, dy) if self.level is not None else self.move(dx, dy)

    # ------------------------------------------------------------- time

    def wait(self, hours: float) -> None:
        if self.player.alive:
            self.pass_time(hours)

    def water_temp(self) -> float:
        """The water where you are, degrees C: it follows the season's mean air temperature
        rather than the day's swings, and never quite freezes. Underground it's as cold as the
        cave."""
        if self.underground:
            return max(0.5, self.indoor_air - 1)
        w, p = self.world, self.player
        return max(0.5, float(w.temperature[p.x, p.y] + season_offset(self.lat, self.minutes)) - 1)

    @property
    def in_water(self) -> bool:
        return self.level is not None and int(self.level.tiles[self.lx, self.ly]) in WADING

    def cold_water(self, turns: int) -> None:
        """`turns` turns in the water where you are (fording a river)."""
        for text in chill(self.player, turns, self.water_temp(), self.rng):
            self.say(text)

    def pass_time(self, hours: float, soak: float = 0.0, effort: float = 0.0) -> None:
        """Runs the clock forward an hour at a time at most, so the weather and your body keep up.
        `effort` is how hard you're working (1 is steady walking, 0 is resting). Each call is
        a turn (a long one counts a turn per TURN_MINUTES) for cold water and its afterdrop."""
        p = self.player
        if self.paused:                     # the dev console stopped the clock
            self.update_view()
            return
        turns = max(1, round(hours * MINUTES_PER_HOUR / TURN_MINUTES))
        for text in chill(p, turns, self.water_temp() if self.in_water else None, self.rng):
            self.say(text)          # (a walk goes on: the body's own warnings stop it if it gets bad)
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
            self.soak(dt)
        if self.room_until is not None and self.minutes >= self.room_until:
            self.room_until = None
            if self.player.inventory.take("room key", self.player.inventory.count("room key")):
                self.say("It's mid-morning: your room key goes back to the barkeeper.")
        if self.level is not None:
            if p.alive:
                self.level.scent[self.lx, self.ly] = self.minutes     # wolves can follow you too
            people.advance(self.level, self.minutes, self)
            wild.advance(self.level, self.minutes, self, self.rng)
            guards.defend(self.level, self, self.rng, hours * MINUTES_PER_HOUR)
        if p.god:
            self.restore()
        carts.sync(self)
        self.update_view()
        if self.level is not None:
            wild.notice(self.level, self)

    # ------------------------------------------------------------- the dev console

    def restore(self, dry: bool = False) -> None:
        """Health and stamina full, body temperature normal (god mode, or heal)."""
        p = self.player
        p.health, p.stamina, p.body, p.alive = 100.0, 100.0, NORMAL, True
        if dry:
            p.wet = 0.0

    def dev_pass(self, hours: float) -> None:
        """Lets the clock run on, everything going on as it would (an hour at a time)."""
        was, self.paused = self.paused, False
        self.pass_time(hours)
        self.paused = was

    def jump_clock(self, minutes: float) -> None:
        """Moves the clock straight on: the people and creatures here just catch up."""
        self.minutes += minutes
        self.now = self.weather()
        if self.level is not None:
            people.advance(self.level, self.minutes, self)
            wild.advance(self.level, self.minutes, self, self.rng)
        carts.sync(self)
        self.update_view()

    def spawn(self, kind: str, n: int = 1) -> int:
        """Puts n creatures (or animals) of a kind on free ground around you. Returns how many."""
        from .farming import ANIMALS
        level = self.level
        taken = wild.taken_on(level) | {(a.x, a.y) for a in level.actors} | {(self.lx, self.ly)}
        made = 0
        for _ in range(n):
            spot = None
            for r in range(1, 9):
                ring = [(self.lx + dx, self.ly + dy) for dx in range(-r, r + 1) for dy in range(-r, r + 1)
                        if max(abs(dx), abs(dy)) == r]
                self.rng.shuffle(ring)
                spot = next((c for c in ring if level.walkable(*c) and not T.WATERY[level.tiles[c]]
                             and c not in taken and c not in level.exits), None)
                if spot:
                    break
            if spot is None:
                break
            taken.add(spot)
            if kind in ANIMALS:
                level.actors.append(people.Actor(kind, kind, *spot, home=[spot], work=[spot], evening=[spot]))
            else:
                c = wild.Creature(kind, *spot, home=spot, reach=12)
                if kind == "wolf":
                    c.pack = 1 + max((o.pack for o in level.creatures), default=0)
                    c.hunger = 90.0
                elif kind == "goblin":
                    c.role = "guard"
                level.creatures.append(c)
            made += 1
        if level.wild_minutes is None:
            level.wild_minutes = self.minutes
        self.update_view()
        return made

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
            clear = T.SEE[level.tiles]
            rock = self.on_rock
            if rock is not None:           # up on a rock, you look out over the rocks around
                clear = clear | (level.tiles == T.ROCK)
            seen = tcod.map.compute_fov(clear, (self.lx, self.ly), 0 if far else r,
                                        algorithm=tcod.constants.FOV_SYMMETRIC_SHADOWCAST)
            xs, ys = np.ogrid[: level.width, : level.height]
            round_on_screen = (xs - self.lx) ** 2 + (2 * (ys - self.ly)) ** 2 <= r * r + 1  # rows are twice as tall
            seen &= round_on_screen | fire
            if level.elev.max() > level.elev.min():      # the lie of the land hides what's behind it
                eye = elevation.EYE + (elevation.ON_ROCK_EYE[rock] if rock is not None else 0.0)
                seen = elevation.sightlines(level.elev, (self.lx, self.ly), seen, eye)
            self.local_visible = seen
            level.explored |= self.local_visible
            self.below_visible = None
            below = self.ground_below()
            if below is not None and level.lookout:    # up on a roof, out in the open: the land below
                ground, (dx, dy) = below
                ax, ay, far = self.lx + dx, self.ly + dy, r * LOOKOUT_SIGHT
                gx, gy = np.ogrid[: ground.width, : ground.height]
                self.below_visible = (gx - ax) ** 2 + (2 * (gy - ay)) ** 2 <= far * far
                ground.explored |= self.below_visible
            return
        transparent = ~B.BLOCKS_VIEW[self.world.biome]
        transparent[p.x, p.y] = True
        self.visible = tcod.map.compute_fov(transparent, (p.x, p.y), self.sight_radius(),
                                            algorithm=tcod.constants.FOV_SYMMETRIC_SHADOWCAST)
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
        if self.console.open:
            self.console.handle_key(sym, mod)
            return True
        if self.riding is not None and not self.menu.open and sym not in (MENU_KEY, devconsole.CONSOLE_KEY):
            return True                       # on the cart: sit back (Esc for the menu)
        if sym == devconsole.CONSOLE_KEY and not self.menu.open:
            self.console.toggle()
            self.autopath = False
            return True
        if self.menu.open:
            result = self.menu.handle_key(sym, mod)
            self.menu_result(result)
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
        if sym == SKIP_KEY:
            self.menu.open_skip(back_to=None)
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
        elif sym == GEAR_KEY and self.player.alive:
            self.equipment_menu()
        elif sym == DIG_KEY and self.player.alive:
            self.dig()
        elif sym == REVEAL_KEY:
            if self.level is None:
                self.reveal = not self.reveal
            else:
                self.reveal_local = not self.reveal_local
                self.say("You picture the whole of the map." if self.reveal_local else "You keep to what you've seen.")
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
