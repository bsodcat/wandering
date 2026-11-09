"""The game state: the world, the clock, the player, and what keys do.

Two ways to get about:

- The overworld: one region per step, each costing the hours it takes to cross that ground.
  Enter (or >) steps down into the region you're in.
- Local maps: the region tile by tile, each step costing minutes. Walk off an edge and you're
  in the next region's map; < takes you back up to the overworld. Stairs (> and <, or Enter)
  lead down into caves and crypts and up towers.

Local maps are built when first visited and kept, with what you've explored, for the rest of
the game. The weather and temperature come from the region you're in either way.
"""
from __future__ import annotations

import random

import numpy as np
import tcod
from tcod.event import KeySym, Modifier

from . import biomes as B
from . import tiles as T
from .climate import (MINUTES_PER_HOUR, Climate, Conditions, latitude, shelter_at, snow_cover,
                      time_of_day)
from .level import Level
from .localgen import LOCAL_H, LOCAL_W, make_level, node_local
from .player import Player, expose
from .worldgen import World, generate

MOVES = {
    KeySym.UP: (0, -1), KeySym.DOWN: (0, 1), KeySym.LEFT: (-1, 0), KeySym.RIGHT: (1, 0),
    KeySym.KP_8: (0, -1), KeySym.KP_2: (0, 1), KeySym.KP_4: (-1, 0), KeySym.KP_6: (1, 0),
    KeySym.KP_7: (-1, -1), KeySym.KP_9: (1, -1), KeySym.KP_1: (-1, 1), KeySym.KP_3: (1, 1),
    KeySym.W: (0, -1), KeySym.S: (0, 1), KeySym.A: (-1, 0), KeySym.D: (1, 0),
}
WAIT_KEYS = {KeySym.PERIOD, KeySym.KP_5}
ENTER_KEYS = {KeySym.RETURN, KeySym.KP_ENTER}
REST_KEY, OVERLAY_KEY, REVEAL_KEY = KeySym.Z, KeySym.TAB, KeySym.M
QUIT = {KeySym.ESCAPE}
OVERLAYS = ["Normal", "Elevation", "Temperature", "Moisture", "Weather"]

START_MINUTES = 8 * MINUTES_PER_HOUR  # 08:00 on the first day of spring
ROAD_TRAVEL = 0.6       # hours per region along a road
RIVER_TRAVEL = 1.0      # extra hours to ford a river where there's no bridge
RIVER_SOAK = 50         # wetness from wading one
NIGHT_SLOWDOWN = 1.5    # travel takes this much longer in the dark
SNOW_SLOWDOWN = {"Snow": 1.3, "Blizzard": 1.8}
SNOWY_GROUND = 1.4      # local steps through lying snow
REST_HOURS = 8
LANTERN = 6             # how many columns your lantern lights, underground or on a dark night
LOOKOUT_RANGE = 12      # regions you can see from the top of a tower
LOCAL_KNOWLEDGE = {"town": 14, "village": 8, "inn": 6}  # regions around a settlement its people tell you about
SKY = {"Clear": "clear", "Cloudy": "cloudy", "Overcast": "overcast", "Fog": "foggy", "Rain": "raining",
       "Storm": "stormy", "Snow": "snowing", "Blizzard": "a blizzard"}

WEATHER_NEWS = {
    "Rain": "It starts to rain.", "Storm": "A storm breaks overhead.", "Snow": "It begins to snow.",
    "Blizzard": "A blizzard howls in.", "Fog": "Fog rolls in.", "Overcast": "The sky turns grey and heavy.",
}
LIGHT_NEWS = {"Dawn": "The sun comes up.", "Dusk": "The sun is going down.", "Night": "Night falls."}


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
        self.local_visible = np.zeros((1, 1), dtype=bool)
        self.update_view()

    @classmethod
    def new(cls, seed: int | None = None) -> Engine:
        """A fresh world, starting in its best town. The same seed makes the same world."""
        seed = random.randrange(2**31) if seed is None else seed
        world = generate(seed)
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
        return float(min(0.8, max(base if self.level.surface else 0.0, cover * 0.12)))

    @property
    def snowy(self) -> bool:
        return not self.underground and snow_cover(self.world, self.player.x, self.player.y, self.minutes)

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
        self.pass_time(hours, soak)
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
            self.levels[key] = make_level(self.world, key)
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
        tile = int(level.tiles[nx, ny])
        if not T.WALK[tile]:
            self.say("The water is too deep to wade." if tile == T.DEEP_WATER
                     else f"The {T.TILES[tile].name} is in the way.")
            return False
        was_inside = self.indoors
        self.lx, self.ly = nx, ny
        if (nx, ny) in level.exits:
            self.say(f"There are {T.TILES[tile].name} here.")
        elif self.indoors != was_inside and not level.underground:
            self.say("You step inside." if self.indoors else "You step outside.")
        self.pass_time(self.step_minutes(tile, dx, dy) / 60, float(T.SOAK[tile]))
        return True

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
        self.pass_time(self.step_minutes(tile, dx, dy) / 60, float(T.SOAK[tile]))
        return True

    def use_stairs(self, way: str | None = None) -> bool:
        """Takes the stairs you're standing on. `way` is "down", "up" or None for either."""
        level = self.level
        key = level.exits.get((self.lx, self.ly))
        tile = int(level.tiles[self.lx, self.ly])
        if key is None or (way == "down" and tile != T.STAIRS_DOWN) or (way == "up" and tile != T.STAIRS_UP):
            if way == "up" and level.surface and key is None:
                return self.leave_region()
            self.say("There are no stairs here." if key is None else f"These stairs go {'down' if tile == T.STAIRS_DOWN else 'up'}.")
            return False
        nxt = self.get_level(key)
        self.level = nxt
        self.lx, self.ly = nxt.arrival(level.key) or nxt.nearest_walkable(nxt.width / 2, nxt.height / 2)
        self.say(f"You climb {'down' if tile == T.STAIRS_DOWN else 'up'} to {nxt.name}.")
        if nxt.lookout and ("lookout", *nxt.region) not in self.visited:
            self.visited.add(("lookout", *nxt.region))
            self.learn_around(*nxt.region, LOOKOUT_RANGE)
            self.say("From up here you can see for miles around; the land shows on your map.")
        self.pass_time(1 / 60)
        return True

    # ------------------------------------------------------------- time

    def wait(self, hours: float) -> None:
        if self.player.alive:
            self.pass_time(hours)

    def pass_time(self, hours: float, soak: float = 0.0) -> None:
        """Runs the clock forward an hour at a time at most, so the weather and your body keep up."""
        p = self.player
        left = hours
        while left > 1e-9 and p.alive:
            dt = min(1.0, left)
            left -= dt
            before, before_time = self.now, time_of_day(self.lat, self.minutes)
            self.minutes += dt * MINUTES_PER_HOUR
            self.now = self.climate.at(p.x, p.y, self.minutes)
            if not self.underground:
                self.news(before, before_time)
            for text in expose(p, dt, self.now, self.shelter, indoors=self.indoors, soak=soak,
                               indoor_air=self.indoor_air):
                self.say(text)
            soak = 0.0
        self.update_view()

    def news(self, before: Conditions, before_time: str) -> None:
        now, now_time = self.now, time_of_day(self.lat, self.minutes)
        if now_time != before_time and now_time in LIGHT_NEWS:
            self.say(LIGHT_NEWS[now_time])
        if now.kind == before.kind:
            return
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
            seen = tcod.map.compute_fov(T.SEE[level.tiles], (self.lx, self.ly), r,
                                        algorithm=tcod.constants.FOV_SYMMETRIC_SHADOWCAST)
            xs, ys = np.ogrid[: level.width, : level.height]
            round_on_screen = (xs - self.lx) ** 2 + (2 * (ys - self.ly)) ** 2 <= r * r + 1  # rows are twice as tall
            self.local_visible = seen & round_on_screen
            level.explored |= self.local_visible
            return
        transparent = ~B.BLOCKS_VIEW[self.world.biome]
        transparent[p.x, p.y] = True
        self.visible = tcod.map.compute_fov(transparent, (p.x, p.y), self.sight_radius(),
                                            algorithm=tcod.constants.FOV_SYMMETRIC_SHADOWCAST)
        self.explored |= self.visible

    # ------------------------------------------------------------- keys

    def handle_key(self, sym: KeySym, mod: int = 0) -> bool:
        """Does what a key press means. Returns False when the game should close."""
        shift = bool(mod & Modifier.SHIFT)
        if sym in QUIT:
            return False
        if sym == OVERLAY_KEY and self.level is None:
            self.overlay = (self.overlay + 1) % len(OVERLAYS)
        elif sym == REVEAL_KEY:
            if self.level is None:
                self.reveal = not self.reveal
            else:
                self.level.explored[:] = True
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
            self.wait(1)
        elif sym == REST_KEY:
            self.say(f"You rest for {REST_HOURS} hours.")
            self.wait(REST_HOURS)
        return True
