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
| Tab | cycle overlays: Normal, Elevation, Temperature, Moisture, Weather | |
| `m` | reveal the whole map (for development) | reveal this level |
| Esc | quit | quit |

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
- Coasts and lakes are shallow near the shore and deep further out.
- Rivers and roads run between fixed "nodes", one per region, with a meander that depends
  only on the two ends, so both sides of a border draw the same line. Wide rivers have a deep
  channel you can't wade; roads over water become bridges. A settlement's node is its middle,
  so its roads lead into the square.
- It's all generated with a 6-tile margin and then cut down, so anything that looks at its
  neighbours (like shallow water by the shore) matches across borders.

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
lantern lights the way. Trees and walls around you give some shelter. How far you see outside
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
game/level.py      a local map and its stairs
game/climate.py    calendar, daylight, weather, temperature
game/player.py     the body: temperature, wetness, health
game/engine.py     game state, travel on both maps, stairs, time and keys
game/render.py     the overworld or local map, overlays, sidebar and log
game/rooms.py      rooms and corridors (crypts)
game/fon.py        reads Windows .fon bitmap fonts (the Terminal font), from Togetherogue
tests/             unittest tests
```
