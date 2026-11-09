"""Drawing: the world map or the local map, filling the whole window, centred on you. The
panels over it (stats, info, minimap, log) are game/hud.py.

The map is coloured a whole view at a time with numpy: biome colours, then rivers, roads and
sites, then the weather and the daylight on what you can see. Places you've seen but can't see
now are drawn grey from memory. The overlays (o) show the raw fields for tuning the
generator: elevation, temperature right now, moisture and weather.

Local maps are drawn the same way, tile by tile: under the open sky they take the region's
daylight, weather and lying snow; under a roof they're lit as if by lamps; underground only
your lantern lights them, fading with distance. Hearths and torches burn with a flickering
light of their own, and water moves: rivers run downstream and the sea rolls. Treetops are a
layer above the ground: seen from above they hide what's under them, except right around you, where you see the trunks
and the shaded ground beneath (v shows the ground everywhere).
"""
from __future__ import annotations

import time

import numpy as np
import tcod

from . import biomes as B
from . import tiles as T
from . import trees
from .farming import CROP_LOOKS
from .light import firelight, flame, flicker
from .engine import OVERLAYS, Engine
from .hud import draw_hud, draw_menu
from .ui import SCREEN_H, SCREEN_W
from .worldgen import SITE_KINDS

MAP_W, MAP_H = SCREEN_W, SCREEN_H      # the map's default size: the whole screen (the panels lie over it)
CURSOR_BG, ROUTE_BG = np.array((200, 190, 90)), np.array((90, 120, 170))
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


def follow(px: int, py: int, cols: int = MAP_W, rows: int = MAP_H) -> tuple[int, int]:
    """The map cell at the top-left of a cols x rows screen, so that (px, py) is in the middle.
    It keeps you in the middle even by the edge of the map (past it is blank), so the panels
    at the sides never cover you."""
    return px - cols // 2, py - rows // 2


def camera(e: Engine) -> tuple[int, int]:
    return follow(e.player.x, e.player.y, e.panels.width, e.panels.height)


def window(ox: int, oy: int, width: int, height: int, cols: int = MAP_W, rows: int = MAP_H):
    """The part of a width x height map on a cols x rows screen from origin (ox, oy): (the map
    slices, the screen cell its top-left lands on, its size)."""
    x0, y0 = max(ox, 0), max(oy, 0)
    x1, y1 = min(ox + cols, width), min(oy + rows, height)
    vw, vh = max(0, x1 - x0), max(0, y1 - y0)
    return (slice(x0, x0 + vw), slice(y0, y0 + vh)), (x0 - ox, y0 - oy), (vw, vh)


def view_origin(e: Engine) -> tuple[int, int]:
    """The map cell at the top-left of the screen."""
    if e.level is None:
        return camera(e)
    return follow(e.lx, e.ly, e.panels.width, e.panels.height)


def map_cell(e: Engine, sx: int, sy: int) -> tuple[int, int] | None:
    """The map cell under screen cell (sx, sy), or None if that's not over the map."""
    if not (0 <= sx < e.panels.width and 0 <= sy < e.panels.height) or e.panels.covers(sx, sy):
        return None
    ox, oy = view_origin(e)
    x, y = ox + sx, oy + sy
    return (x, y) if e.in_map(x, y) else None


def draw_pointer(console: tcod.console.Console, e: Engine) -> None:
    """The cell under the mouse, and while walking there, the way."""
    if e.mouse is None:
        return
    cell = map_cell(e, *e.mouse)
    if cell is None:
        return
    ox, oy = view_origin(e)
    rgb = console.rgb
    if e.autopath and e.goal is not None:
        for x, y in e.route(*e.goal):
            sx, sy = x - ox, y - oy
            if 0 <= sx < e.panels.width and 0 <= sy < e.panels.height:
                rgb["bg"][sx, sy] = (rgb["bg"][sx, sy] * 0.4 + ROUTE_BG * 0.6).astype(np.uint8)
    sx, sy = e.mouse
    rgb["bg"][sx, sy] = (rgb["bg"][sx, sy] * 0.3 + CURSOR_BG * 0.7).astype(np.uint8)
    rgb["fg"][sx, sy] = (20, 20, 20)


# ----------------------------------------------------------------- moving water

WATER_TILES = [T.WATER, T.DEEP_WATER]
SEA_SWELL = (0.45, 0.9)          # the way waves roll where there's no current
RIVER_SPEED, SEA_SPEED = 3.2, 1.4
GLINT = (235, 245, 255)


def unit(dx: float, dy: float) -> tuple[float, float]:
    n = float(np.hypot(dx, dy)) or 1.0
    return dx / n, dy / n


def waves(gx, gy, dx, dy, speed, seconds) -> np.ndarray:
    """-1..1: the swell over each cell, travelling along (dx, dy)."""
    phase = (gx * dx + 2 * gy * dy) * 0.55 + speckle(gx, gy, 0, 1) * 1.2
    return np.sin(phase - seconds * speed)


def animate_water(ch, fg, bg, wet, w, gx, gy, seconds: float, glints: bool, deep=None) -> None:
    """Ripples on the water: crests that move, colours that swell, and the odd glint of sun."""
    if not wet.any():
        return
    deep = np.zeros_like(wet) if deep is None else deep & wet
    shallow = wet & ~deep
    ch[shallow] = np.where(w[shallow] > 0.55, ord("≈"), ord("~"))
    ch[deep] = np.where(w[deep] > 0.6, ord("~"), ord("≈"))
    fg[wet] = fg[wet] * (0.8 + 0.3 * w[wet])[:, None]
    bg[wet] = bg[wet] * (0.93 + 0.1 * w[wet])[:, None]
    if glints:
        glint = wet & (w > 0.3) & (speckle(gx, gy, int(seconds * 6), 1) < 0.01)
        ch[glint], fg[glint] = ord("·"), GLINT


# ----------------------------------------------------------------- firelight

FIRE_FG, FIRE_BG = np.array((70, 35, 0)), np.array((80, 35, 5))


def burn(ch, fg, bg, t, visible, strength, phase, dark, base_fg, base_bg, seconds: float) -> None:
    """Firelight on what the fires light, and the flames themselves."""
    lit = (strength > 0) & visible
    if not lit.any():
        return
    amount = (strength * flicker(phase, seconds) * dark * lit)[..., None]
    fg += base_fg * amount * 0.9 + amount * FIRE_FG
    bg += base_bg * amount * 0.8 + amount * FIRE_BG
    flames = np.isin(t, [T.HEARTH, T.TORCH, T.OVEN]) & visible
    if flames.any():
        step, colours = flame(phase, seconds)
        fg[flames] = colours[flames]
        bg[flames] = T.BG[t][flames] * (0.8 + 0.4 * flicker(phase, seconds)[flames])[:, None]
        hearth = flames & (t == T.HEARTH)
        ch[hearth] = np.where(step[hearth] % 3 == 0, ord("*"), ord("☼"))


def speckle(xs: np.ndarray, ys: np.ndarray, minutes: float, period: int = 60) -> np.ndarray:
    """A steady pseudo-random 0..1 per cell, changing every `period` minutes, for raindrops."""
    h = (xs * 374761393 + ys * 668265263 + (int(minutes) // period) * 2147483647) & 0xFFFFFFFF
    h = (h ^ (h >> 13)) * 1274126177 & 0xFFFFFFFF
    return (h & 0xFFFF) / 0xFFFF


def draw_map(console: tcod.console.Console, e: Engine, seconds: float = 0.0) -> None:
    w = e.world
    ox, oy = camera(e)
    view, (sx0, sy0), (vw, vh) = window(ox, oy, w.width, w.height, console.width, console.height)
    cx, cy = view[0].start, view[1].start
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
        # moving water: rivers run the way they flow, the sea swells
        sea = np.isin(biome, B.WATER) & visible & ~falling
        running = river & visible & ~falling & ~bridge
        gx, gy = xs + np.zeros_like(biome), ys + np.zeros_like(biome)
        swell = waves(gx, gy, *unit(*SEA_SWELL), SEA_SPEED, seconds)
        fx, fy = w.flow_dx[view].astype(float), w.flow_dy[view].astype(float)
        norm = np.hypot(fx, fy) + 1e-9
        flow = waves(gx, gy, fx / norm, fy / norm, RIVER_SPEED, seconds)
        fg[sea] = fg[sea] * (0.85 + 0.25 * swell[sea])[:, None]
        bg[sea] = bg[sea] * (0.93 + 0.1 * swell[sea])[:, None]
        crest = sea & (swell > 0.75)
        ch[crest] = ord("~")
        fg[running] = fg[running] * (0.8 + 0.3 * flow[running])[:, None]
        ch[running & (flow > 0.6)] = ord("≈")
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

    out = console.rgb[sx0: sx0 + vw, sy0: sy0 + vh]
    out["ch"] = ch
    out["fg"] = np.clip(fg, 0, 255).astype(np.uint8)
    out["bg"] = np.clip(bg, 0, 255).astype(np.uint8)
    p = e.player
    console.print(p.x - ox, p.y - oy, "@", fg=(255, 255, 255) if p.alive else (200, 60, 60))


SNOW_FG, SNOW_BG = np.array((235, 240, 250)), np.array((170, 178, 195))
LANTERN_GLOW = 5   # tiles your lantern brightens on a dark night outdoors
CUTAWAY = 4.3      # how far around you (in columns) you see under the treetops

# Leaves seen from above: (glyph, second glyph, how often the first, fg, bg)
LEAVES = {
    (trees.BROADLEAF, "green"): ("♣", "♣", 1.0, [(60, 150, 60), (75, 160, 65), (50, 135, 55)], (22, 58, 26)),
    (trees.BROADLEAF, "budding"): ("♣", "·", 0.7, [(150, 205, 95), (120, 190, 80)], (35, 64, 30)),
    (trees.BROADLEAF, "autumn"): ("♣", "♣", 1.0, [(205, 120, 45), (215, 175, 55), (170, 65, 35)], (62, 42, 22)),
    (trees.PINE, None): ("♠", "♠", 1.0, [(45, 115, 75), (55, 125, 80)], (14, 42, 28)),
    (trees.JUNGLE, None): ("♣", "♠", 0.6, [(45, 175, 75), (70, 190, 60)], (10, 62, 26)),
}
BARE_FG = np.array((125, 95, 65))


def leaf_layer(canopy, boughs, look: str, gx, gy):
    """Glyphs and colours for the treetops, and which tiles you can see the ground through
    (bare boughs in winter)."""
    ch = np.zeros(canopy.shape, np.int32)
    fg = np.zeros(canopy.shape + (3,))
    bg = np.zeros(canopy.shape + (3,))
    r = speckle(gx, gy, 0, 1)
    for (kind, when), (first, second, share, colours, back) in LEAVES.items():
        here = canopy == kind
        if when is not None:
            if look != when:
                continue
        if not here.any():
            continue
        ch[here] = np.where(r[here] < share, ord(first), ord(second))
        pick = np.minimum((r[here] * 7919 % 1 * len(colours)).astype(int), len(colours) - 1)
        fg[here] = np.array(colours)[pick]
        bg[here] = back
    bare = (canopy == trees.BROADLEAF) & (look == "bare")
    ch[bare], fg[bare] = boughs[bare], BARE_FG
    return ch, fg, bg, bare


def draw_local(console: tcod.console.Console, e: Engine, seconds: float = 0.0) -> None:
    level = e.level
    ox, oy = follow(e.lx, e.ly, console.width, console.height)
    view, (sx0, sy0), (vw, vh) = window(ox, oy, level.width, level.height, console.width, console.height)
    cx, cy = view[0].start, view[1].start
    t = level.tiles[view]
    ch, fg, bg = T.CHAR[t].copy(), T.FG[t].copy(), T.BG[t].copy()
    if not level.underground:                     # the fields through the year
        stage = e.crop_stage
        for tile in T.FIELDS:
            look = CROP_LOOKS.get((tile, stage))
            here = t == tile
            if look is not None and here.any():
                ch[here], fg[here], bg[here] = ord(look[0]), look[1], look[2]
    base_fg, base_bg = fg, bg                     # what's remembered once out of sight
    visible = e.local_visible[view]
    seen = level.explored[view]
    xs = np.arange(cx, cx + vw)[:, None] + np.zeros((1, vh), int)
    ys = np.arange(cy, cy + vh)[None, :] + np.zeros((vw, 1), int)
    dist = np.sqrt((xs - e.lx) ** 2 + (2 * (ys - e.ly)) ** 2)
    c = e.now
    gx, gy = xs + level.region[0] * 1000, ys + level.region[1] * 1000
    region = level.region
    if level.surface and e.world.river[region]:
        current, speed = unit(float(e.world.flow_dx[region]), float(e.world.flow_dy[region])), RIVER_SPEED
    else:
        current, speed = unit(*SEA_SWELL), SEA_SPEED * (0.5 if level.underground else 1.0)
    wet = np.isin(t, WATER_TILES) & visible
    animate_water(ch, fg, bg, wet, waves(gx, gy, *current, speed, seconds), gx, gy, seconds,
                  glints=not level.underground and c.light > 0.45 and c.precip < 0.15, deep=t == T.DEEP_WATER)
    if level.underground:
        light = np.clip(1.15 - dist / (2 * e.sight_radius() + 2), 0.12, 1)[..., None]
        fg, bg = fg * light, bg * light
    else:
        sky = ~T.ROOF[t]
        canopy = level.canopy[view]
        leaf_ch, leaf_fg, leaf_bg, bare = leaf_layer(canopy, level.boughs[view], e.foliage, gx, gy)
        leaves = canopy > 0
        dense = leaves & ~bare                     # keeps the rain and snow off the ground
        shown = leaves & (dist > CUTAWAY) if e.treetops else np.zeros_like(leaves)
        if e.snowy:
            snowed = sky & T.SNOWS_ON[t] & ~dense & ~shown
            fg[snowed] = fg[snowed] * 0.2 + SNOW_FG * 0.8
            bg[snowed] = SNOW_BG
            leaf_fg[leaves] = leaf_fg[leaves] * 0.45 + SNOW_FG * 0.55
            leaf_bg[dense] = leaf_bg[dense] * 0.6 + SNOW_BG * 0.4
        shade = leaves & ~shown & ~bare           # the ground in the shadow of the leaves
        fg[shade], bg[shade] = fg[shade] * 0.75, bg[shade] * 0.6
        ch[shown], fg[shown] = leaf_ch[shown], leaf_fg[shown]
        thick = shown & ~bare
        bg[thick] = leaf_bg[thick]
        base_fg, base_bg = fg.copy(), bg.copy()
        if c.precip > 0.15:
            falling = sky & visible & (speckle(gx, gy, e.minutes, 5) < c.precip * 0.3) & (T.WALK[t] | shown)
            falling &= ~(dense & ~shown)
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
            fg, bg = fg + base_fg * glow, bg + base_bg * glow
    strength, phase = firelight(level)
    if level.underground:
        dark = 0.6
    else:   # firelight shows most in the dark; under a roof there's always some to see by
        dark = np.where(sky, 1 - c.light, max(0.35, 1 - max(0.5, c.light * 0.8)))
    burn(ch, fg, bg, t, visible, strength[view], phase[view], dark, base_fg, base_bg, seconds)
    memory = seen & ~visible
    fg[memory] = base_fg[memory] * 0.35 + base_fg[memory].mean(axis=-1, keepdims=True) * 0.15 + 12
    bg[memory] = base_bg[memory] * 0.18 + 5
    hidden = ~seen
    ch[hidden], fg[hidden], bg[hidden] = ord(" "), 0, 0
    out = console.rgb[sx0: sx0 + vw, sy0: sy0 + vh]
    out["ch"] = ch
    out["fg"] = np.clip(fg, 0, 255).astype(np.uint8)
    out["bg"] = np.clip(bg, 0, 255).astype(np.uint8)
    draw_actors(console, e, ox, oy, shown if not level.underground else None)
    p = e.player
    console.print(e.lx - ox, e.ly - oy, "@", fg=(255, 255, 255) if p.alive else (200, 60, 60))


def draw_actors(console, e: Engine, ox: int, oy: int, canopy_shown) -> None:
    """People and animals you can see, dimmed by the dark but brighter by firelight. Anyone under
    the treetops (seen from above) is hidden by the leaves."""
    level = e.level
    strength, _ = firelight(level)
    for a in level.actors:
        if not (level.in_bounds(a.x, a.y) and e.local_visible[a.x, a.y]):
            continue
        sx, sy = a.x - ox, a.y - oy
        if not (0 <= sx < console.width and 0 <= sy < console.height):
            continue
        if canopy_shown is not None:
            vx, vy = a.x - max(ox, 0), a.y - max(oy, 0)
            if 0 <= vx < canopy_shown.shape[0] and 0 <= vy < canopy_shown.shape[1] and canopy_shown[vx, vy]:
                continue
        light = 1.0 if level.underground else (max(0.5, e.now.light * 0.8) if T.ROOF[level.tiles[a.x, a.y]]
                                               else e.now.light)
        bright = min(1.0, max(0.4, light, float(strength[a.x, a.y]) * 1.2))
        console.rgb["ch"][sx, sy] = ord(a.char)
        console.rgb["fg"][sx, sy] = tuple(int(c * bright) for c in a.colour)


def draw(console: tcod.console.Console, e: Engine, seconds: float | None = None) -> None:
    """Draws everything: the map, then the panels over it. `seconds` is the wall clock, for what
    moves on its own: water and fire."""
    seconds = time.monotonic() if seconds is None else seconds
    e.panels.width, e.panels.height = console.width, console.height    # however big the screen is now
    e.menu.cols, e.menu.rows = console.width, console.height
    console.clear()
    if e.level is None:
        draw_map(console, e, seconds)
    else:
        draw_local(console, e, seconds)
    draw_pointer(console, e)
    cell = map_cell(e, *e.mouse) if e.mouse else None
    draw_hud(console, e, e.describe(*cell) if cell else [], seconds)
    if not e.player.alive:
        text = f" You {e.player.cause}. Esc quits. "
        console.print(max(0, (console.width - len(text)) // 2), console.height // 2 - 3, text, fg=(255, 255, 255), bg=(120, 20, 20))
    draw_menu(console, e.menu)
