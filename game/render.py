"""Drawing: the world map or the local map, the sidebar and the message log.

The map is coloured a whole view at a time with numpy: biome colours, then rivers, roads and
sites, then the weather and the daylight on what you can see. Places you've seen but can't see
now are drawn grey from memory. The overlays (Tab) show the raw fields for tuning the
generator: elevation, temperature right now, moisture and weather.

Local maps are drawn the same way, tile by tile: under the open sky they take the region's
daylight, weather and lying snow; under a roof they're lit as if by lamps; underground only
your lantern lights them, fading with distance.
"""
from __future__ import annotations

import numpy as np
import tcod

from . import biomes as B
from . import tiles as T
from .climate import clock_text, date_text, describe_wind, time_of_day
from .engine import OVERLAYS, Engine
from .player import body_status, feels_like, wet_status
from .worldgen import SITE_KINDS

SCREEN_W, SCREEN_H = 100, 45
MAP_W, MAP_H = 74, 39
SIDE_X = MAP_W + 2
LOG_Y = MAP_H + 1

TEXT, DIM, TITLE = (220, 220, 220), (130, 130, 130), (255, 220, 120)
RIVER_FG, ROAD_FG, BRIDGE_FG = (90, 150, 235), (185, 150, 95), (200, 160, 100)


def ramp(values: np.ndarray, stops: list[tuple[float, tuple[int, int, int]]]) -> np.ndarray:
    """Colours for `values`, blended between (value, colour) stops."""
    xs = [v for v, _ in stops]
    return np.stack([np.interp(values, xs, [c[i] for _, c in stops]) for i in range(3)], axis=-1)


ELEVATION = [(-5000, (5, 10, 60)), (-200, (40, 90, 170)), (0, (90, 150, 210)), (1, (60, 140, 60)),
             (1200, (200, 190, 90)), (2600, (130, 90, 60)), (4800, (255, 255, 255))]
TEMPERATURE = [(-35, (120, 40, 160)), (-15, (40, 60, 200)), (0, (90, 200, 230)), (10, (70, 180, 80)),
               (20, (230, 220, 70)), (30, (240, 130, 40)), (40, (200, 30, 30))]
MOISTURE = [(0, (190, 160, 100)), (0.35, (170, 190, 100)), (0.65, (60, 150, 120)), (1, (20, 60, 160))]


def camera(e: Engine) -> tuple[int, int]:
    w, p = e.world, e.player
    return (int(np.clip(p.x - MAP_W // 2, 0, max(0, w.width - MAP_W))),
            int(np.clip(p.y - MAP_H // 2, 0, max(0, w.height - MAP_H))))


def follow(px: int, py: int, width: int, height: int) -> tuple[int, int]:
    """The top-left of a MAP_W x MAP_H view that keeps (px, py) in the middle where it can."""
    return (int(np.clip(px - MAP_W // 2, 0, max(0, width - MAP_W))),
            int(np.clip(py - MAP_H // 2, 0, max(0, height - MAP_H))))


def speckle(xs: np.ndarray, ys: np.ndarray, minutes: float, period: int = 60) -> np.ndarray:
    """A steady pseudo-random 0..1 per cell, changing every `period` minutes, for raindrops."""
    h = (xs * 374761393 + ys * 668265263 + (int(minutes) // period) * 2147483647) & 0xFFFFFFFF
    h = (h ^ (h >> 13)) * 1274126177 & 0xFFFFFFFF
    return (h & 0xFFFF) / 0xFFFF


def draw_map(console: tcod.console.Console, e: Engine) -> None:
    w = e.world
    cx, cy = camera(e)
    vw, vh = min(MAP_W, w.width), min(MAP_H, w.height)
    view = (slice(cx, cx + vw), slice(cy, cy + vh))
    biome = w.biome[view]
    ch = B.CHAR[biome].copy()
    fg = B.FG[biome].copy()
    bg = B.BG[biome].copy()

    river, road = w.river[view], w.road[view]
    ch[river], fg[river] = ord("~"), RIVER_FG
    bg[river] = bg[river] * 0.5 + np.array((20, 50, 110)) * 0.5
    ch[road], fg[road] = ord("·"), ROAD_FG
    bridge = road & river
    ch[bridge], fg[bridge] = ord("="), BRIDGE_FG
    for s in w.sites:
        if cx <= s.x < cx + vw and cy <= s.y < cy + vh:
            char, colour, _, _ = SITE_KINDS[s.kind]
            ch[s.x - cx, s.y - cy], fg[s.x - cx, s.y - cy] = ord(char), colour

    xs = np.arange(cx, cx + vw)[:, None]
    ys = np.arange(cy, cy + vh)[None, :]
    f = e.climate.fields(xs, ys, e.minutes)
    mode = OVERLAYS[e.overlay]

    if mode == "Normal":
        visible = e.visible[view] | e.reveal
        seen = e.explored[view] | e.reveal
        # weather you can see: rain and snow scattered over the ground, fog greying it out
        falling = (f["precip"] > 0.15) & (speckle(xs, ys, e.minutes) < f["precip"] * 0.45) & visible
        snow = falling & (f["air"] <= 0.5)
        rain = falling & ~snow
        ch[rain], fg[rain] = ord(","), (120, 165, 235)
        ch[snow], fg[snow] = ord("*"), (240, 240, 255)
        fog = f["fog"][..., None] * 0.65
        fg = fg * (1 - fog) + 170 * fog
        bg = bg * (1 - fog) + 120 * fog
        # daylight: dim and blue at night, a warm cast at dawn and dusk
        light = f["light"][..., None]
        dusk = (np.clip(1 - np.abs(f["sun"] - 0.45) / 0.35, 0, 1) * (f["sun"] > 0))[..., None]
        fg = fg * (0.3 + 0.7 * light) + dusk * np.array((30, 10, -10))
        bg = bg * (0.15 + 0.85 * light) + (1 - light) * np.array((0, 0, 18)) + dusk * np.array((25, 8, -5))
        # memory: seen before, not in view now
        memory = seen & ~visible
        base_fg, base_bg = B.FG[biome][memory], B.BG[biome][memory]
        fg[memory] = base_fg * 0.35 + base_fg.mean(axis=-1, keepdims=True) * 0.15 + 12
        bg[memory] = base_bg * 0.18 + 5
        hidden = ~seen
        ch[hidden], fg[hidden], bg[hidden] = ord(" "), 0, 0
    else:
        if mode == "Elevation":
            bg = ramp(w.elevation[view], ELEVATION)
        elif mode == "Temperature":
            bg = ramp(f["air"], TEMPERATURE)
        elif mode == "Moisture":
            bg = ramp(w.moisture[view], MOISTURE)
        elif mode == "Weather":
            cloud = f["cloud"][..., None]
            bg = (60, 110, 190) * (1 - cloud) + np.array((150, 150, 160)) * cloud
            wet = (f["precip"] > 0.15)
            bg[wet & (f["air"] > 0.5)] = (40, 70, 200)
            bg[wet & (f["air"] > 0.5) & (f["precip"] > 0.7)] = (110, 40, 170)
            bg[wet & (f["air"] <= 0.5)] = (235, 235, 250)
            fogged = f["fog"] > 0.4
            bg[fogged] = (200, 200, 200)
        fg = bg * 0.45 + 70

    out = console.rgb[:vw, :vh]
    out["ch"] = ch
    out["fg"] = np.clip(fg, 0, 255).astype(np.uint8)
    out["bg"] = np.clip(bg, 0, 255).astype(np.uint8)
    p = e.player
    console.print(p.x - cx, p.y - cy, "@", fg=(255, 255, 255) if p.alive else (200, 60, 60))


SNOW_FG, SNOW_BG = np.array((235, 240, 250)), np.array((170, 178, 195))
LANTERN_GLOW = 5   # tiles your lantern brightens on a dark night outdoors


def draw_local(console: tcod.console.Console, e: Engine) -> None:
    level = e.level
    cx, cy = follow(e.lx, e.ly, level.width, level.height)
    vw, vh = min(MAP_W, level.width), min(MAP_H, level.height)
    view = (slice(cx, cx + vw), slice(cy, cy + vh))
    t = level.tiles[view]
    ch, fg, bg = T.CHAR[t].copy(), T.FG[t].copy(), T.BG[t].copy()
    visible = e.local_visible[view]
    seen = level.explored[view]
    xs = np.arange(cx, cx + vw)[:, None] + np.zeros((1, vh), int)
    ys = np.arange(cy, cy + vh)[None, :] + np.zeros((vw, 1), int)
    dist = np.sqrt((xs - e.lx) ** 2 + (2 * (ys - e.ly)) ** 2)
    c = e.now
    if level.underground:
        light = np.clip(1.15 - dist / (2 * e.sight_radius() + 2), 0.12, 1)[..., None]
        fg, bg = fg * light, bg * light
    else:
        sky = ~T.ROOF[t]
        if e.snowy:
            snowed = sky & T.SNOWS_ON[t]
            fg[snowed] = fg[snowed] * 0.2 + SNOW_FG * 0.8
            bg[snowed] = SNOW_BG
        gx, gy = xs + level.region[0] * 1000, ys + level.region[1] * 1000
        if c.precip > 0.15:
            falling = sky & visible & (speckle(gx, gy, e.minutes, 5) < c.precip * 0.3) & T.WALK[t]
            ch[falling] = ord("*") if c.snowing else ord(",")
            fg[falling] = (240, 240, 255) if c.snowing else (120, 165, 235)
        if c.fog > 0:
            fog = c.fog * 0.65
            fg[sky] = fg[sky] * (1 - fog) + 170 * fog
            bg[sky] = bg[sky] * (1 - fog) + 120 * fog
        light = np.where(sky, c.light, max(0.5, c.light * 0.8))[..., None]
        sun = float(c.light)
        dusk = float(np.clip(1 - abs(sun - 0.45) / 0.35, 0, 1)) if 0.1 < sun < 0.9 else 0.0
        warm = sky[..., None] * dusk
        fg = fg * (0.3 + 0.7 * light) + warm * np.array((30, 10, -10))
        bg = bg * (0.15 + 0.85 * light) + (1 - light) * np.array((0, 0, 18)) + warm * np.array((25, 8, -5))
        if c.light < 0.4:   # your lantern
            glow = np.clip(1 - dist / (2 * LANTERN_GLOW), 0, 1)[..., None] * (0.4 - c.light)
            fg, bg = fg + T.FG[t] * glow, bg + T.BG[t] * glow
    hearth = (t == T.HEARTH) & visible
    fg[hearth], bg[hearth] = T.FG[T.HEARTH], T.BG[T.HEARTH]
    memory = seen & ~visible
    fg[memory] = T.FG[t][memory] * 0.35 + T.FG[t][memory].mean(axis=-1, keepdims=True) * 0.15 + 12
    bg[memory] = T.BG[t][memory] * 0.18 + 5
    hidden = ~seen
    ch[hidden], fg[hidden], bg[hidden] = ord(" "), 0, 0
    out = console.rgb[:vw, :vh]
    out["ch"] = ch
    out["fg"] = np.clip(fg, 0, 255).astype(np.uint8)
    out["bg"] = np.clip(bg, 0, 255).astype(np.uint8)
    p = e.player
    console.print(e.lx - cx, e.ly - cy, "@", fg=(255, 255, 255) if p.alive else (200, 60, 60))


def bar(console, x: int, y: int, width: int, value: float, top: float, colour) -> None:
    filled = int(round(width * max(0.0, min(1.0, value / top))))
    console.print(x, y, "█" * filled, fg=colour)
    console.print(x + filled, y, "░" * (width - filled), fg=(60, 60, 60))


def draw_sidebar(console: tcod.console.Console, e: Engine) -> None:
    x, y = SIDE_X, 0
    p, w, c = e.player, e.world, e.now

    def line(text: str, colour=TEXT) -> None:
        nonlocal y
        console.print(x, y, text[: SCREEN_W - x], fg=colour)
        y += 1

    line(date_text(e.minutes), TITLE)
    line(f"{clock_text(e.minutes)}  {time_of_day(e.lat, e.minutes)}")
    y += 1
    site = e.site
    if e.level is not None and not e.level.surface:
        line(e.level.name, TITLE)
        line("Underground" if e.underground else ("Indoors" if e.indoors else "Out in the open"), DIM)
        line(e.tile.name.capitalize(), DIM)
    else:
        line(site.name if site else e.biome.name, TITLE)
        if site:
            line(f"{site.kind.title()}{' (port)' if site.port else ''}, {e.biome.name.lower()}", DIM)
        extras = [t for t, on in (("river", w.river[p.x, p.y]), ("road", w.road[p.x, p.y])) if on]
        line(f"Alt {max(0, w.elevation[p.x, p.y]):.0f} m" + (f"  {', '.join(extras)}" if extras else ""), DIM)
        if e.level is not None:
            line(e.tile.name.capitalize() + ("  indoors" if e.indoors else ""), DIM)
    y += 1
    if e.indoors and e.level is not None:
        line(f"Air   {e.indoor_air:5.1f}°C")
        line(f"Outside {c.air:5.1f}°C", DIM)
        line("Underground" if e.underground else f"Indoors; {c.kind.lower()} outside")
        line("No wind", DIM)
    else:
        felt = feels_like(c.air, c.wind, p.wet, e.shelter)
        line(f"Air   {c.air:5.1f}°C")
        line(f"Feels {felt:5.1f}°C", DIM)
        line(c.kind)
        line(f"{describe_wind(c.wind)} {c.wind:.0f} km/h", DIM)
    line(f"Sight {e.sight_radius()}  Shelter {e.shelter:.0%}", DIM)
    y += 1
    line(f"Health {p.health:5.1f}")
    bar(console, x, y, 22, p.health, 100, (200, 60, 60)); y += 1
    line(f"Body {p.body:4.1f}°C {body_status(p.body)}")
    line(f"Wet  {p.wet:3.0f}%  {wet_status(p.wet)}")
    bar(console, x, y, 22, p.wet, 100, (70, 120, 220)); y += 1
    y += 1
    if e.level is None:
        line(f"Overlay: {OVERLAYS[e.overlay]}", DIM)
        line(f"Map: {'revealed' if e.reveal else 'explored'}", DIM)
        keys = ("arrows/numpad/wasd go", "> Enter go into region", ". or 5  wait an hour",
                "z      rest 8 hours", "Tab    overlays", "m      reveal map", "Esc    quit")
    else:
        line(f"Region {p.x},{p.y}  at {e.lx},{e.ly}", DIM)
        keys = ("arrows/numpad/wasd go", "> <    stairs down/up", "<      (no stairs) map",
                ". or 5  wait an hour", "z      rest 8 hours", "m      reveal level", "Esc    quit")
    y = SCREEN_H - len(keys) - 1
    for text in keys + (f"Seed {w.seed}",):
        line(text, DIM)


def draw_log(console: tcod.console.Console, e: Engine) -> None:
    lines = e.messages[-(SCREEN_H - LOG_Y):]
    if lines and e.repeats > 1:
        lines = lines[:-1] + [f"{lines[-1]} (x{e.repeats})"]
    for i, text in enumerate(lines):
        age = len(lines) - 1 - i
        shade = max(90, 230 - age * 35)
        console.print(1, LOG_Y + i, text[: MAP_W - 1], fg=(shade, shade, shade))


def draw(console: tcod.console.Console, e: Engine) -> None:
    console.clear()
    if e.level is None:
        draw_map(console, e)
    else:
        draw_local(console, e)
    console.rgb["ch"][MAP_W, :] = ord("│")
    console.rgb["fg"][MAP_W, :] = (60, 60, 70)
    console.rgb["ch"][:MAP_W, MAP_H] = ord("─")
    console.rgb["fg"][:MAP_W, MAP_H] = (60, 60, 70)
    console.rgb["ch"][MAP_W, MAP_H] = ord("┤")
    draw_sidebar(console, e)
    draw_log(console, e)
    if not e.player.alive:
        text = f" You {e.player.cause}. Esc quits. "
        console.print(max(0, (MAP_W - len(text)) // 2), MAP_H // 2, text, fg=(255, 255, 255), bg=(120, 20, 20))
