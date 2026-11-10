# Wandering

**Gathering to Aevum: The Necromancer's Key**
*Chapter II: Wandering the Mundane*

Version 1.3.0. Windows players can download the exe from the
[Releases](https://github.com/bsodcat/wandering/releases) page and run it; nothing else
to install. Settings are kept in `%APPDATA%/newrogue/settings.json`.

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
python main.py          # the title screen
python main.py 42       # straight into world 42 (the same world every time)
```

To build the exe yourself: `python -m PyInstaller --onefile --windowed --name wandering main.py`
(it lands in `dist/`).

## The title screen

The game opens on its title screen (`game/title.py`), over a world drifting slowly past:

- **New Game**: a random world, straight away.
- **Create a World**: type a seed (or press `R` for a random one) and see the whole world it
  makes before you start: its biomes, rivers and settlements, how many towns, villages and inns
  there are, and the town you'll start in. The same seed always makes the same world.
- **Dev Arena**: a 256x256 test ground with one of everything (see below).
- **Options**: the display options.
- **About**: what the game is, and who made it.
- **Quit Game**.

Under the choices are the keys for the menus and for playing, with the keys picked out.
Up/Down (or W/S) choose, Enter picks, Esc goes back, and the mouse points and clicks. In a
game, the pause menu's **Main menu** brings you back here.

## The dev arena

A 256x256 local map for testing (`game/arena.py`), always the same, always fair weather on a
summer's morning, and explored from the start:

- **The gallery**, north of where you start: every tile in the game on its own flagstone, a
  row for each kind: ground, trees, ways, building, furniture and trades, fields. Under it,
  every item lies ready to pick up, the axe and the shovel among them.
- **A hill**, north-east: 14 levels high, steeper on its north side, for climbing and for
  seeing over.
- **A dig site**: the dirt patch in the north-west has something buried under every other tile.
- **Pens**, south: one of each of the townsfolk (baker, butcher, innkeeper, barkeeper,
  shopkeeper, farmer, fisherman, lumberjack), each with a bit of their trade, then one of every animal, the dog
  and the cat among them.
- **Ground**, north-west: a patch of every kind of ground, and a broadleaf wood, a pine wood
  and a jungle.
- **Water**, east: a river with a bridge, and a lake with a beach and a pier.
- **The wilds**, west: a fenced wood with a pack of three wolves and the rabbits, squirrels
  and birds they hunt.
- **A goblin cave**, below the wilds: two guards inside the door (sleeping in shifts), a
  patrol, a hunter and a cook at their fire with bedrolls, food and a barrel of loot, rats,
  and a roost of sleeping bats in the far corner by a pool.
- **A town and a village**, far south: built and peopled the same way as in the world, with
  an inn, a bakery, a butcher's, houses, fields, pastures and a lumber camp.

It's fine all day but for a shower at six in the evening, so dug ground grows back overnight.
The town's inn has its upstairs and cellar. Point at anything to name it. The gallery's
stairs lead nowhere; leave by Esc, then Main menu.

| Key | Overworld | Local map |
| --- | --- | --- |
| arrows, numpad, WASD | travel one region (diagonals on the numpad) | one step |
| Enter or `>` | go into the region you're in | take the stairs you're on |
| `<` | | stairs up; anywhere else on the surface, back to the overworld |
| `.` or numpad 5 | wait an hour | wait an hour |
| `z` | rest 8 hours | rest 8 hours; on a bed upstairs at an inn with a room key, sleep till morning |
| `o` | cycle overlays: Normal, Elevation, Temperature, Moisture, Weather | relief view: each tile's height |
| `g` | | pick up what's at your feet |
| `x` | | dig where you stand (needs a shovel) |
| `i` | the Inv tab: what you carry | same |
| `e` | | the use menu: what you can do here and next to you (talk, trade, pet, attack, open a barrel, sleep, pick up, eat, wield, wear) |
| walk into... | | a person: talk (or trade, if they trade); a dog or cat: pet it; a creature: strike it; a tree, with an axe: fell it |
| Tab | right panel: Info, Map, Log, Inv, hidden | same |
| `c` | show or hide the stats panel | same |
| PgUp / PgDn, wheel | scroll the Log tab | same |
| `v` | | switch between the treetops and the ground beneath them |
| point with the mouse | the sidebar's Look panel describes that region | the Look panel describes that tile |
| left click | note what's there in the log | note what's there in the log |
| hold right button | walk there over regions you know | walk there over ground you know |
| `m` | reveal the whole map (for development) | reveal this level |
| Esc | pause menu: Resume, Options, Main menu, Quit | same |
| F11 or Alt+Enter | windowed / fullscreen | same |

## The screen

The screen is as many tiles as fit the window: 120x45 by default (1200x900 with Terminal), and
more if you make the window bigger, wider or taller, or maximise it. Tiles always stay their
pixel-sharp size, so a bigger window shows more of the world rather than bigger pixels. The map
fills the whole screen, centred on you, and the panels lie on top of it pinned to the left and
right edges (`game/ui.py` lays it out, `game/hud.py` draws it). Hiding a panel just uncovers
more map: the window and the map under it stay put.

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

Options (on the title screen, or Esc in a game) sets these (arrow keys or click the `◄ ►`), and they apply
at once and are saved to `%APPDATA%/newrogue/settings.json`:

| Setting | Choices |
| --- | --- |
| Display | Windowed, Fullscreen (also F11 or Alt+Enter) |
| Font | Terminal (the Windows bitmap font), Consolas, Lucida Console, Courier New |
| Font size | Auto, or 6x12 to 20x40: the size of a tile, drawn at exactly that many pixels. Auto keeps Terminal at its own 10x20 when the default 120x45 screen fits, and otherwise picks the biggest size that does |
| Scale | Auto, 1x, 2x, 3x, 4x. Always a whole number with every pixel repeated, so small fonts stay pixel-sharp. Auto is the biggest at which the default 120x45 screen fits the window; whatever room is left becomes more tiles |

The window starts at the default screen's size times the scale (within the usable part of
your screen), and from then on you can resize, maximise or snap it to any shape: the screen
gains or loses whole tiles, and less than a tile left over at the edges is black. Fullscreen
fills the monitor the same way. The screen never gets smaller than 80x30 tiles; in a window
too small even for that, it's shrunk to fit and smoothed. The note under the options box says
what you've got ("200x53 tiles of 10x20, shown 1x, pixel-sharp").

`game/display.py` does the window: it measures the screen through SDL, works out how many
tiles fit at the scale (`grid`), draws them with the font into a picture of exactly that many
pixels, and copies it into the window at the whole-number scale. When the window changes
shape the screen is rebuilt at the new size. Mouse positions go back through the same scaling. TrueType fonts are measured and redrawn so their
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

**Elevation** (`game/elevation.py`). Every tile of a local map has a height in levels of 20 m:
the world's elevation smoothed between region middles, plus rolling hills, gentle on the plains
and rough in the hills and mountains. It runs on across region borders like the land.
- Neighbouring tiles are never more than two levels apart, so there's always a way up.
  Settlements are levelled.
- A step up a level is a slope (slower, and tiring). Two levels is a steep scramble that takes
  far longer. Steeper than that can't be climbed. Roads, streets and paths are graded, so
  they're never worse than a slope. Going down is quicker than going up. A walk to the pointer
  finds a way round anything too steep.
- Sight: you see a tile only if the ground between doesn't rise above the line from your eyes
  to it. From a hilltop you see far; a ridge hides what's beyond it, and from the edge of a
  drop you can't see its foot. The overworld does the same with the world's elevation, and
  climbing there costs hours (2.5 h per 1000 m up, less on roads).
- Ground above you is drawn brighter and ground below you darker, and the foot of a rise lies
  in its shadow. `o` shows the relief: each tile's height (its last digit) on a colour from low
  to high. The stats panel shows your height in metres.

**Things and tools** (`game/items.py`). You start with 20 coins.
- `g` picks up what's lying at your feet, and the Inv tab (`i`) shows what you carry.
- **Axe**: one leans by every lumberjack's house. Walk into a tree with it to fell it: 20
  minutes of hard work for 2 logs (3 from a jungle tree), leaving a stump. Its leaves come off
  the layer above.
- **Shovel**: there's one in a house in every town and village. `x` digs where you stand, on
  open ground (grass, dirt, sand, mud, snow): half an hour's work. You only find what was buried
  there: coins, arrowheads, pottery, old bones, rusty daggers, fairly often a trinket (a brass
  button, a bone die, a tin whistle...), and only under a town, now and then a silver or gold
  ring. There's more in old ruins. Digging leaves turned earth (`░`) but doesn't change the
  height.
- Dug ground waits for rain. Four hours after the first rain falls on it, grass grows back.

**Shops** (`game/shop.py`). Walk into someone who trades, while they're at work, and their shop
opens: Up/Down or the mouse to choose, Enter to trade, Esc to leave.
- A **lumberjack** buys logs at 3 coins each, once you've cut some.
- An **innkeeper** serves hot soup for 4 coins: it warms you, and treats wolf fever.
- A town's **shopkeeper** (at the armourer's, 08:00-18:00) sells common weapons and armour,
  and buys trinkets and rings.
- A **barkeeper** lets a room upstairs for 8 coins. You get a room key, good till 10:00 the
  next morning. Sleep (`z`) in any bed upstairs and you sleep till 07:00, waking rested.
  Without a key the beds are off limits.

**Inns** have two more floors: stairs up to a corridor of guest rooms with a bed in each, and
down to a stone cellar of barrels. Each inn has an innkeeper (07:00-21:00) and a barkeeper
(10:00-24:00, behind the bar).

**The use menu** (`e`, or a left click on something you can use). It lists what you can do:
talk to someone, trade, pet a dog, attack a creature, open a barrel, sleep or rest in a bed,
pick things up, take the stairs, fell a tree, dig, eat, wield a weapon, wear armour. Pick
something out of reach and you walk over to it first (a walk stops if a creature's in the
way: it never starts a fight). Clicking on plain ground still just notes it in the log.

**Barrels** hold things: food in cellars and houses, odds and ends in sheds, loot in a goblin
camp. Open one from the use menu to take things out or put things in; it keeps what you leave.

**Fighting** (`game/combat.py`). Walk into a creature to strike it. A blow lands by chance
(the weapon's, less how nimble the creature is) and does the weapon's damage; blows at you are
cut by your armour.

| Weapon | Damage | | Armour | Stops |
| --- | --- | --- | --- | --- |
| fists | 1-3 | | padded jerkin (6 coins) | 1 |
| club (3 coins) | 2-5 | | leather coat (12) | 2 |
| dagger (6) | 2-4, quick | | mail shirt (30) | 3 |
| spear (9) | 3-7 | | iron helm (10) | 1, on your head |
| short sword (16) | 3-8 | | wooden shield (6) | 1, and turns aside one blow in six |
| axe, shovel, rusty dagger, crude knife | 2-6, 1-4, 1-3, 1-4 | | | |

Wield one weapon, and wear one piece of armour in each place, from the use menu. Food (roast
meat, apples, bread, salt fish) gives back stamina and a little health. You can't rest or wait
with wolves or goblins about.

**Wild things** (`game/wild.py`) live on the local maps, and act as the clock runs:
- **Small game**: rabbits and birds in the open, squirrels in the woods, rats in caves. They
  nibble about, leaving a scent where they go, and run from anything that hunts them.
  Squirrels run up the nearest tree; birds fly over anything.
- **Wolves** keep a territory in the forests and wilds (about half of forest regions have a
  pack), and commonly den in caves, mostly in packs of two to five, rarely alone. The pack
  roams behind its leader along trails it has worn before. Hungry, they follow the freshest
  scent, then stalk what they find, slowly and low, until they're close enough to rush it.
  They only go for you if they're very hungry and there are two or more of them, or you've
  hurt one. They flee if hurt (and a hurt wolf goes slowly), outnumbered (a wanderer with a
  real weapon and body armour counts as two), or left alone; a trail gone cold, they lose
  interest and go home.
- **Bats** roost in clusters deep in caves, asleep, until you come near or something makes a
  noise; then they all wake, shrieking. They flit about over anything in the way, keeping off
  you, and settle back to sleep when it's quiet. Hurt or corner one and the bats around it
  swarm you together for a while.
- **Goblins** live in some caves: guards at the way in, sleeping in shifts; patrols walking
  the passages; and deep down a camp with a fire, bedrolls, a pile of food and a barrel of
  loot, where hunters bring rats and bats (and any carcass they find) for the cook to roast.
  They sleep through the day, wake if you come close, go to look at any noise (a fight,
  shrieking bats, an alarm), shout the alarm when they see you and fight, but run when badly
  hurt or outnumbered two to one. Each carries a few things you can take once it's dead.

**Wolf fever** (`game/sickness.py`). Now and then (3%) a wolf's bite goes bad. Half a day
later the fever comes on: you stop healing and lose a little health every hour. Left a week,
it takes hold, and you lose health fast until you die of it. A bowl of hot soup from an
innkeeper treats it: you start to feel better and heal again (up to 75), but it takes two or
three days of good sleep (a rest of six hours or more, or a bed at an inn, on different days)
before the fever breaks.

**Pets.** Every town has a dog or a cat with a name. It wanders the town, and when you're
near it trots after you, keeping a step or two off (the dog more keenly than the cat). Walk
into it to pet it.

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
| Town | paved square with a well and market stalls, a named inn (bar, kegs, tables, beds, a sign by the door), a bakery with bread ovens, a butcher's with meat hooks, 11-16 houses with hearths, beds and tables, doors facing the square, streets to every door, vegetable gardens and a pasture outside, docks if it's a port, a lumber camp if it's wooded |
| Village | a green with a well, 4-7 houses, paths, larger fields of the grain that suits the climate, a pasture or two, docks on the coast, a lumber camp if it's wooded |
| Inn | a big named inn on the road, a paddock with horses, a well |
| Tower | a round stone watchtower; stairs up to a room, then the roof, where you can see the land for miles around |
| Ruins | roofless stone buildings, tumbled and overgrown; the biggest has stairs down to a crypt (rooms and corridors) |
| Cave | a rocky outcrop with a way down into 1-3 cave levels (cellular automaton caverns with pools) |

**People and animals** (`game/people.py`, `game/farming.py`). Settlements are lived in:

| Who | Where | Works |
| --- | --- | --- |
| Baker | the bakery, by the ovens | 04:00-13:00 |
| Fisherman | the end of the pier, or a spot on the bank of the nearest river, lake or sea | 05:00-15:00 |
| Farmer | the fields (towns: the gardens) | 06:00-18:00 |
| Lumberjack | the lumber camp: a woodpile and fresh stumps where the woods are thickest | 07:00-17:00 |
| Butcher | the butcher's, by the counter | 07:00-16:00 |
| Innkeeper | behind the bar; sleeps at the inn | 09:00-24:00 |

Towns have a baker, a butcher, an innkeeper and farmers; villages have farmers; both have a
fisherman if there's water to fish and a lumberjack if there are woods to cut. Everyone has a
name and a house. After work they spend the evening at the inn (or on the village green) and
go to bed at 21:00. They walk where they're going as the clock runs, wander about while they
work, and step round each other. If you've been away or rested, everyone is just where they'd
be by now. Point at someone to see who they are and what they're doing; walk into them to
talk (the first time, they introduce themselves) and step past each other.

Fields and herds suit the climate (the yearly mean temperature and how wet it is):

| Grain | Where | Herd | Where |
| --- | --- | --- | --- |
| Wheat | temperate lands | Cows | grassland, savanna |
| Rye | the cold north, taiga, uplands | Sheep | hills, steppe |
| Rice paddies | hot and wet | Goats | mountains, desert, scrub |
| Millet | hot and dry | Pigs | forest, jungle, swamp |
| | | Reindeer | tundra, taiga, the cold |

Pastures are fenced with a trough; hens peck about the houses everywhere. Grain fields go
through the year: green shoots in spring, tall and green, ripe and gold at midsummer, stubble
after the harvest, then fallow until spring (always growing in the tropics; rice paddies are
flooded while the rice comes up).

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
game/people.py     townsfolk and animals: who lives where, their hours, walking, talking
game/wild.py       wolves, small game, bats and goblins: where they live, how they behave
game/combat.py     weapons, armour, and how blows land
game/sickness.py   wolf fever, soup and sleep
game/items.py      things you carry, dig up and find in barrels
game/shop.py       shops, the use menu and barrels
game/farming.py    which grain and herd suit a climate, and the fields through the year
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
