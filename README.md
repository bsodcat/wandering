# newrogue

A python-tcod roguelike built world-first. The world is generated from one seed and simulated:
terrain, rivers and lakes, biomes, towns, villages, inns, towers, ruins and caves joined by a
road network, a calendar with seasons, daylight, drifting weather and an air temperature that
comes from all of them. What it's like outside affects your body.

You travel the overworld a region at a time, or step down into any region's local map and
walk it tile by tile: through towns and fields, over bridges, down into caves and crypts and
up watchtowers. Walk off the edge of a local map and you're in the next region.

## Run

```
python -m pip install -r requirements.txt
python main.py          # a random world
python main.py 42       # the same world every time
```

| Key | Overworld | Local map |
| --- | --- | --- |
| arrows, numpad, WASD | travel one region (diagonals on the numpad) | one step |
| Enter or `>` | go into the region you're in | take the stairs you're on |
| `<` | | stairs up; anywhere else on the surface, back to the overworld |
| `.` or numpad 5 | wait an hour | wait an hour |
| `z` | rest 8 hours | rest 8 hours |
| `o` | cycle overlays: Normal, Elevation, Temperature, Moisture, Weather | |
| Tab | right panel: Info, Map, Log, hidden | same |
| `c` | show or hide the stats panel | same |
| PgUp / PgDn, wheel | scroll the Log tab | same |
| `v` | | switch between the treetops and the ground beneath them |
| point with the mouse | the sidebar's Look panel describes that region | the Look panel describes that tile |
| left click | note what's there in the log | note what's there in the log |
| hold right button | walk there over regions you know | walk there over ground you know |
| `m` | reveal the whole map (for development) | reveal this level |
| Esc | pause menu: Resume, Options, Quit | same |
| F11 or Alt+Enter | windowed / fullscreen | same |

## The screen

The window is 120x45 tiles of 10x20 pixels: 1200x900, 4:3. If you resize it, it keeps that
shape. The map fills the whole window, centred on you, and everything else lies on top of it
(`game/ui.py` lays it out, `game/hud.py` draws it). Hiding a panel just uncovers more map: the
window and the map under it stay put.

- **Stats** (left; `c` or its `◄` button hides it, the `►` tab in the corner brings it back):
  bars for health, stamina and wetness, a warmth gauge from cold to hot, what the air feels
  like, clothing, shelter, sight, and a list of your conditions. New stats are a line in
  `hud.BARS`.
- **Right panel**, three tabs (click one, or cycle with Tab, which also hides it; its `►`
  button hides it too):
  - Info: the date and time, where you are, the weather, what's under the pointer (Look),
    and the keys.
  - Map: a minimap of the world as far as you've explored it (towns marked, you blinking),
    and under it either the land around you or the whole of the local map you're on.
  - Log: every message, scrollable with PgUp/PgDn, Home/End or the mouse wheel.
- **Recent messages** run along the bottom between the panels, over a darkened strip of map
  (not while the Log tab is open).

Stamina goes down as you walk, faster on slow ground like bushes or wading, and slower on
the overworld's long steady travel. It comes back while you wait or rest. Below 15 you're
told you're exhausted. It doesn't hold you back yet.

## Options

Esc opens the pause menu; Options sets these (arrow keys or click the `◄ ►`), and they apply
at once and are saved to `%APPDATA%/newrogue/settings.json`:

| Setting | Choices |
| --- | --- |
| Display | Windowed, Fullscreen (also F11 or Alt+Enter) |
| Resolution | 800x600 to 2048x1536, all 4:3. Windowed, it's the window's size; fullscreen, the game is drawn at it and scaled to fill the screen, with black bars at the sides |
| Font | Terminal (the Windows bitmap font), Consolas, Lucida Console, Courier New |
| Font size | Auto, or 8x16 to 20x40. Auto picks the tile that fills the resolution exactly (sharpest); other sizes are drawn at that size and scaled |

`game/display.py` does the window: it draws the 120x45 screen with the font into a frame,
scales the frame to the resolution, and lets SDL fit that to the window or monitor. Mouse
positions go back through the same scaling. TrueType fonts are measured and redrawn so their
letters fill the tiles (libtcod draws Consolas at half size), and block and line characters
are drawn by hand so bars and the minimap join up whatever the font.

## Test

```
python -m unittest discover -s tests
```

## How the world works

**Generation** (`game/worldgen.py`, 256x128 regions, about 0.15 s):

1. Elevation: fractal noise continents, ridged mountain ranges, sea round the edges.
2. Temperature: 28 °C at the equator (the middle row) down to -16 °C at the poles, minus
   6.5 °C per 1000 m of height.
3. Moisture: wet near coasts and in the rain belts (the tropics and about 60°), dry around 30°.
4. Drainage: a priority-flood from the sea routes every cell downhill and fills basins, which
   become lakes. Rain gathered from upstream decides where the rivers run; each cell keeps
   its flow direction for local maps later.
5. Biomes from altitude, temperature and moisture (`game/biomes.py`): oceans, lakes, beach,
   glacier, tundra, taiga, steppe, grassland, shrubland, forest, swamp, desert, savanna,
   jungle, hills, mountains and snowy peaks.
6. People and roads (`plan_people`), in the order a land gets settled:
   - Towns where farmland, a mild climate and water meet, at least 16 regions apart.
   - Highways: a minimum spanning tree over the towns by walking time, so every town you can
     walk to is on the network, plus a direct road wherever the network makes a trip 45%
     longer. Roads avoid mountains and river crossings where they can, and later roads
     follow earlier ones, so they merge into trunk routes.
   - Villages near roads and water, each with a track out to the nearest road or settlement.
   - Inns every 24 regions or so along long highways.
   - Watchtowers on hills and mountains within sight of a road.
   - Ruins out in the country and caves where high ground meets low.
   - Towns and villages on the sea are ports.

   Every road step is kept as an edge (`road_edges`, highway or track), and rivers keep their
   width, so local maps can draw both.

**Simulation** (`game/climate.py`) is a pure function of place and time, so nothing needs saving:

- A 120-day year: four 30-day seasons. The south has summer while the north has winter, and
  seasons swing harder toward the poles. Days are long in summer and short in winter.
- Weather is 3D noise drifting east, so fronts move across the map. Clouds build over wet ground,
  rain falls under the thickest (snow at 0 °C or below), and storms bring wind. Mountains are
  windier, and fog settles on calm, damp mornings.
- Air temperature = the yearly mean + the season + the time of day (damped by cloud) - rain.
- Light comes from the sun and is dimmed by cloud, rain and fog.

**The player** (`game/player.py`): body temperature, wetness and health. Each hour, wind chill,
wet clothes and shelter turn the air into what it feels like, and clothing adds 8 °C. Outside
the comfortable band your body cools or heats; below 35 °C or above 39.5 °C you lose health.
Rain soaks you (less under trees), wading a river soaks you at once, and warmth and wind dry you.
Settlements are indoors: warm and dry, and you heal faster.

**Travel** (`game/engine.py`): each step crosses one region and costs that ground's hours.
Roads take 0.6 h, forest 2 h, mountains 4 h and peaks 8 h. Fording a river adds 1 h. It's
1.5x slower at night and slower in snow. How far you can see depends on the light, fog and
rain, and is further from high ground. Mountains block the view. The first time you visit a
settlement, its people tell you about the land around it.

## Local maps

Each region opens into a 96x48 local map (`game/localgen.py`), built the first time you go
there and kept with what you've explored.

**Land** is a function of global tile coordinates, so neighbouring regions join without a seam:

- Each tile takes the biome of the region its noise-jittered position falls in, so biome
  borders wander instead of following the region grid.
- Each biome has a ground tile and layers of cover in clusters: trees with clearings in a
  forest, copses on grassland, reeds and pools in a swamp, cliffs along ridges in mountains.
- Trees come in two layers, as in Dwarf Fortress (`game/trees.py`). The trunk (`O`) stands on
  the ground: you can't walk through it, but you can see past it. No two trunks touch. The
  crown spreads over the tiles around it on the layer above: broadleaf crowns 2 columns out,
  pines narrower, jungle trees wider. You walk under the leaves. They shade the ground, keep
  off the rain and lying snow, and add shelter.
- Broadleaf trees follow the seasons: buds in spring, green in summer, red and gold in autumn,
  bare boughs in winter (branch glyphs pointing back to the trunk). Pines, jungle trees and
  trees in the tropics stay green.
- Coasts and lakes are shallow near the shore and deep further out.
- Rivers and roads run between fixed "nodes", one per region, with a meander that depends
  only on the two ends, so both sides of a border draw the same line. Wide rivers have a deep
  channel you can't wade; roads over water become bridges. A settlement's node is its middle,
  so its roads lead into the square.
- It's all generated with a 6-tile margin and then cut down, so anything that looks at its
  neighbours (like shallow water by the shore) matches across borders, and leaves reach
  across from trees in the next region.

Trees never block a way in. After the structures are built, every trunk within about 3
columns of a door, stairs, a well, a gate or the step outside a door is felled. No leaves hang
over buildings, streets, roads, paths, docks or bridges, or right over an entrance.

**Fire and water.**
- Every house, inn and shed in a settlement has a torch (`¡`) on the wall beside its door, and
  towers have one too. Ruins have none.
- Hearths and torches light what they can see, fading with distance (`game/light.py`).
  Hearths light the room they're in; torches light the ground outside. Each fire flickers to
  its own rhythm, and everything it lights flickers with it. Hearth flames dance between `☼`
  and `*`.
- Firelight matters most in the dark: at night you can see firelit places beyond your
  lantern, so a town shows its lights from across the map.
- Water moves. Ripples run downstream along a region's river, the sea and lakes swell more
  slowly, and in sunshine the water glints. On the overworld, rivers shimmer the way they
  flow and the sea rolls.
- The window redraws 15 times a second for this, whether or not you press anything.

**The mouse.** Point at anything on the map and the Look panel in the sidebar says what you
know about it.
- On a local map: the tile, where stairs lead, the tree overhead and its leaves, whether it
  blocks the way, gets you wet or is slow going, how many steps away it is, and whether you
  can see it now or only remember it.
- On the overworld: the site, the biome, rivers and roads, the height, the weather there if
  you can see it, and about how long it would take to get there.

Hold the right button to walk to the place you pressed on, along the quickest way over ground
you've seen. Routes go round water when there's a dry way. Moving the mouse while you hold
the button steers the walk. The walk stops when you let go, press a key, arrive, cross into
another map, or when something needs your attention: a change in the weather, nightfall, or a
warning about your body.

From above, the treetops hide what's under them, except in a small circle around you, where
you see the trunks and the shaded ground. `v` shows the ground everywhere, with the shade of
the leaves.

**Structures** (`game/structures.py`) grow out from the middle of a site and keep 4 tiles from
the edges:

| Site | Local map |
| --- | --- |
| Town | paved square with a well and market stalls, an inn, 11-16 houses with hearths, beds and tables, doors facing the square, streets to every door, fenced fields outside, docks if it's a port |
| Village | a green with a well, 4-7 houses, paths, larger fields, docks on the coast |
| Inn | a big inn on the road, a fenced paddock, a well |
| Tower | a round stone watchtower; stairs up to a room, then the roof, where you can see the land for miles around |
| Ruins | roofless stone buildings, tumbled and overgrown; the biggest has stairs down to a crypt (rooms and corridors) |
| Cave | a rocky outcrop with a way down into 1-3 cave levels (cellular automaton caverns with pools) |

**Levels** (`game/level.py`) are named by keys like `("region", x, y)`, `("cave", x, y, 2)` or
`("tower", x, y, 1)`. Stairs are exits pointing at another key, and you arrive at the exit
that leads back. The same key always builds the same level.

**On a local map**, steps cost minutes: 0.35 on a street, 1.5 through bushes, 2.5 wading. It's
slower in the dark and through lying snow. Snow lies on the ground when the season's mean
temperature in that region is below freezing. Under a roof you're indoors: out of the weather,
at the level's indoor temperature (warm in settlements, cool in towers). Underground you're
out of the weather but it's cold (caves are 10 °C and colder further down), and only your
lantern lights the way. Trees and walls around you give some shelter, and more under leaves. How far you see outside
follows the daylight, fog and rain.

`game/rooms.py` (rooms and corridors) builds the crypts.

## Layout

```
main.py            the window and the event loop
game/worldgen.py   the world generator: terrain, climate, water, biomes, people and roads
game/biomes.py     biome table: looks, travel time, shelter
game/localgen.py   region local maps: seamless terrain, rivers, roads
game/structures.py towns, villages, inns, docks, towers, ruins, caves, and the levels below and above
game/tiles.py      local tile table: looks, walking, sight, step time, roofs
game/trees.py      trunks and crowns, seasons, keeping ways in clear
game/light.py      firelight from hearths and torches, and how it flickers
game/level.py      a local map, its stairs and its canopy layer
game/climate.py    calendar, daylight, weather, temperature
game/player.py     the body: temperature, wetness, health
game/engine.py     game state, travel on both maps, stairs, time and keys
game/render.py     the overworld or local map, overlays, water and fire, the mouse pointer
game/ui.py         the screen layout: which panels are open, what's under a screen cell
game/hud.py        the panels: stats, Info/Map/Log, recent messages
game/options.py    settings, the pause menu and options screen
game/display.py    the window: fonts, resolution, fullscreen, scaling, mouse positions
game/rooms.py      rooms and corridors (crypts)
game/fon.py        reads Windows .fon bitmap fonts (the Terminal font), from Togetherogue
tests/             unittest tests
```
