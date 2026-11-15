"""The people of a settlement and their animals, and their day.

Each settlement is populated when its map is built:

- towns:    a baker, a butcher, an innkeeper, a shopkeeper (weapons and armour, at the
            armourer's), farmers for the gardens, and a fisherman and a lumberjack if there's
            water to fish and woods to cut
- villages: farmers for the fields, and a fisherman and a lumberjack in the same way
- inns:     an innkeeper, and a barkeeper who lets the rooms upstairs for the night
- every house in a town or village has someone living in it (townsfolk, if there aren't
  tradespeople enough); in a city, the houses nobody lives in are empty and full of junk,
  and some cities have abandoned houses, fallen in (structures.empty_houses)
- cities:   each part has the trades that are in it (game/cities.py), a blacksmith at a
            smithy, archers on the walls, and a crowd of its own: craftsfolk working from
            their houses, townsfolk out and about, beggars, merchants at the stalls, thieves,
            and guards at the gates and crossings, more of them the more thieves there are;
            the keep's king or prince, their queen or concubine and the court
            (game/citylife.py)
- forts:    four guards and three archers, who sleep in the barracks, and a blacksmith (a
            city's watch fort: three guards and two archers)
- carters:  beside a cart while it's in town (game/carts.py); they'll take you to a near town
- animals:  a herd in each pasture (what suits the land, see farming.py), and hens about
            the houses; and in a town, a dog or a cat that follows you about if you're near
            (walk into it to pet it)

The lumberjack keeps an axe leaning by their house, and somewhere in a house in every town
and village there's a shovel (game/items.py).

Everyone lives in a house (the innkeeper at the inn) and keeps hours:

    job          works        then
    baker        04:00-13:00  the evening at the inn (or on the green), bed at 21:00
    fisherman    05:00-15:00
    farmer       06:00-18:00
    lumberjack   07:00-17:00
    butcher      07:00-16:00
    shopkeeper   08:00-18:00  sells weapons and armour, buys trinkets
    innkeeper    07:00-21:00  keeping the inn; sleeps there
    barkeeper    10:00-24:00  behind the bar, letting rooms; sleeps at the inn
    guard        06:00-22:00  at the gate, fighting off what comes near (game/guards.py)
    archer       07:00-19:00  on the walls, shooting what comes near
    blacksmith   07:00-18:00  at the forge; sells iron goods, buys old iron

Some keep other hours: a guard on the night watch, or anyone with a `shift` of their own.
Someone with a `routine` (the court) follows it hour by hour, and someone with `haunts` and
no trade (a city's townsfolk) wanders from one to another of them, a different one every
HAUNT_MINUTES or so, at times of their own.

They walk where they're going a tile at a time as the clock runs, a little under a minute a
tile, wander about while they work, and step round each other and you. If you've been away a
while (or rested), everyone is simply where they'd be by now. Animals amble about their
pasture; hens peck about the houses.

An inn holds INN_CROWD people at most, its innkeeper and barkeeper among them. Whoever's
already inside keeps their place; others who'd have gone there walk the streets (in a city)
or go to the green instead, or home if it's late.

Walk into someone and you talk (the first time, they say who they are), and you step past
each other. Walk into an animal and you push past it.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

import numpy as np
import tcod

from . import tiles as T
from .climate import hour_of_day, weekday
from . import items
from .farming import ANIMALS, PETS, STAGE_WORDS

PERSON = "☺"
WALK_MINUTES = 0.8            # a tile, for people
SNAP_MINUTES = 30             # away longer than this, and everyone is just where they'd be
MOST_STEPS = 60               # steps anyone takes in one go
FOLLOW = 12                   # a pet follows you if you're this close (columns on screen)
HEEL = 2                      # and stays about this far away
BEDTIME = 21
HAUNT_MINUTES = 40            # how long someone with no trade lingers in one place
INN_CROWD = 8                 # people in an inn at once, at most, the innkeeper and barkeeper among them
ROYAL = ("king", "prince", "queen", "concubine")


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
    "innkeeper": Job((240, 190, 80), 7, 21, "keeping the inn",
                     ("Welcome to {inn}! Warm fire, soft beds.", "Rooms are upstairs; see the barkeeper.",
                      "Travellers bring the best stories.", "Wipe your boots, please.")),
    "stablehand": Job((190, 160, 110), 6, 20, "tending the horses",
                      ("A good horse is worth its keep.", "Mind her back legs.", "Saddles are extra.",
                       "They'll carry you twice as fast as your feet, and never complain.")),
    "shopkeeper": Job((190, 195, 215), 8, 18, "minding the shop",
                      ("Good steel, fair prices.", "Wolves about? You'll want a spear.",
                       "Dig anything up, bring it here. I pay fair.", "Mail's dear, but so's your hide.")),
    "barkeeper": Job((220, 150, 200), 10, 24, "serving at the bar",
                     ("What'll it be?", "A bed upstairs? That's {price} coins the night.",
                      "Mind the cellar steps.", "Quiet tonight. Too quiet.")),
    "guard": Job((200, 200, 215), 6, 22, "standing guard",
                 ("Move along.", "Keep your blade sheathed inside the walls.",
                  "Wolves came up to the gate last winter.", "All quiet. Just how I like it.")),
    "archer": Job((150, 195, 120), 7, 19, "keeping watch",
                  ("I can put an arrow through a wolf's eye at fifty paces.", "Nothing gets past the walls.",
                   "Seen goblins on the hills at dusk.", "Keep clear of the butts while we're shooting.")),
    "blacksmith": Job((235, 145, 85), 7, 18, "working the forge",
                      ("Good iron, honest work.", "Need a blade? I've a few on the rack.",
                       "Mind the sparks.", "Hot work, this. Hot work.")),
    "carter": Job((205, 175, 120), 0, 24, "seeing to the cart",
                  ("The road's long, but the cart's quicker than your feet.", "Hop on, if you've the coin.",
                   "Mind the wheel.", "Weather's good for the road.")),
    # a stone city's people (game/citylife.py)
    "townsperson": Job((185, 180, 165), 8, 20, "out and about",
                       ("Busy today, isn't it?", "Mind your purse in the market.", "Have you seen the keep? Grand.",
                        "They hanged a horse thief last spring.", "The ale at {inn} is the best in {town}.")),
    "beggar": Job((140, 130, 115), 7, 21, "begging for coins",
                  ("Spare a coin?", "Bless you, traveller.", "I was a soldier once.", "Cold nights, these.")),
    "thief": Job((185, 180, 165), 10, 26, "loitering",
                 ("Nice boots.", "Lovely day for it.", "Never seen you before.", "Guards everywhere today.")),
    "weaver": Job((175, 150, 205), 7, 17, "at the loom",
                  ("Good wool makes good cloth.", "The loom never sleeps, nor do I.", "Mind the thread.")),
    "tailor": Job((205, 155, 175), 8, 18, "stitching a coat",
                  ("Measure twice, cut once.", "That cloak's seen better days.", "Silk's dear this year.")),
    "potter": Job((195, 135, 95), 7, 16, "at the wheel",
                  ("Clay from the river's the best.", "Cracked another one. Oh well.", "Everyone needs a pot.")),
    "chandler": Job((235, 220, 160), 7, 17, "dipping candles",
                    ("Tallow or wax?", "The temple buys my best candles.", "Long nights mean good trade.")),
    "cooper": Job((175, 125, 75), 7, 17, "hooping a barrel",
                  ("A good barrel keeps for years.", "The inns can't get enough of them.", "Oak, always oak.")),
    "cobbler": Job((160, 120, 90), 8, 18, "mending boots",
                   ("Those boots have walked a long way.", "Good soles, good roads.", "Hobnails? Ask the smith.")),
    "scribe": Job((200, 200, 225), 8, 18, "copying letters",
                  ("Ink and patience.", "I write for those who can't.", "The library's books are the king's.")),
    "carpenter": Job((190, 150, 95), 7, 17, "sawing planks",
                     ("Stone's for walls; wood's for living.", "Measure the beam twice.", "Splinters. Always splinters.")),
    "merchant": Job((225, 195, 120), 8, 18, "minding the stall",
                    ("Fresh from the coast!", "Best prices in {town}, I swear it.", "Buy two, I'll throw in a third.",
                     "Got anything to sell? I'm always buying trinkets.")),
    "guildmaster": Job((230, 200, 150), 9, 17, "keeping the guild's books",
                       ("The guild sets fair prices. Mostly.", "Every trade in {town} pays its dues.")),
    "alchemist": Job((150, 225, 190), 9, 19, "brewing something that smokes",
                     ("Don't touch that.", "Grave dust has its uses.", "One day: gold. One day.",
                      "The fumes? You get used to them.")),
    "priest": Job((240, 235, 200), 6, 20, "tending the altar",
                  ("Peace be with you.", "The gods see all, even in {town}.", "Light a candle for the dead.")),
    "bard": Job((215, 160, 230), 16, 23, "singing on the stage",
                ("A song for a coin?", "Have you heard the one about the drowned king?", "Tonight: a new ballad!")),
    "mummer": Job((230, 140, 170), 16, 23, "playing on the stage",
                  ("Tonight we play the fall of the old kings.", "I'm the villain. I always am.", "Boo me, I dare you.")),
    "pit fighter": Job((215, 110, 90), 14, 21, "fighting in the pit",
                       ("Fancy your chances?", "Two broken ribs last week. Still standing.", "Bet on me.")),
    "hangman": Job((120, 110, 110), 10, 16, "seeing to the gallows",
                   ("Nobody likes me. Nobody likes the work.", "The rope's always ready.", "Keep your nose clean.")),
    "king": Job((255, 215, 90), 9, 12, "holding court",
                ("You stand before the throne of {town}.", "My guards keep the peace. Mostly.",
                 "Thieves, thieves, everywhere thieves.", "You may go.")),
    "prince": Job((250, 200, 120), 9, 12, "holding court",
                  ("My father ruled well. I mean to rule better.", "Speak quickly; the court is waiting.",
                   "{town} prospers, thank the gods.")),
    "queen": Job((235, 170, 215), 10, 12, "at court",
                 ("Welcome to {town}, traveller.", "The library is my refuge.", "Do mind the guards; they're jumpy.")),
    "concubine": Job((240, 160, 190), 10, 12, "at court",
                     ("The court whispers. Don't listen.", "Have you come far?", "The gardens are lovely at dusk.")),
    "cook": Job((235, 200, 160), 5, 20, "cooking for the court",
                ("Out of my kitchen!", "Roast boar again tonight.", "The king likes his pies hot.")),
    "librarian": Job((185, 175, 230), 8, 19, "copying a manuscript",
                     ("Quiet, please.", "Some of these books are older than the walls.", "Don't bend the spines.")),
    "servant": Job((200, 190, 170), 6, 21, "waiting on the court",
                   ("Begging your pardon.", "Busy, busy.", "The queen wants her wine warmed.")),
    "sergeant": Job((210, 205, 190), 6, 22, "going over the watch rolls",
                    ("The watch never sleeps. Well, half of it doesn't.", "Seen any thieves? Tell the guards.",
                     "Mind the racks; those blades are sharp.", "The night watch is short again.")),
    "gaoler": Job((150, 140, 130), 0, 24, "keeping the cells",
                  ("No visitors without leave.", "Quiet down there!", "They all say they're innocent.")),
    "prisoner": Job((150, 150, 140), 0, 24, "sitting in a cell",
                    ("I didn't do it!", "Got any bread?", "They'll hang me, sure as rain.", "Get me out of here.")),
}
CRAFTS = ("weaver", "tailor", "potter", "chandler", "cooper", "cobbler", "scribe", "carpenter")
JOBS.update({
    "homemaker": Job((215, 185, 160), 6, 21, "keeping house",
                     ("Supper's on the fire.", "Wipe your feet!", "My other half works all hours.",
                      "Bread's rising. Don't slam the door.")),
    "child": Job((240, 220, 140), 8, 19, "playing tag",
                 ("You're it!", "Can't catch me!", "My mam says not to talk to strangers.", "Are you a knight?")),
    "priest": Job((240, 235, 200), 6, 20, "tending the altar",
                  ("Peace be with you.", "The gods see all, even in {town}.", "Light a candle for the dead.",
                   "Come on Sunday: the service is at nine.")),
    "labourer": Job((170, 150, 120), 6, 18, "hauling loads",
                    ("Back's not what it was.", "A day's work for a day's bread.", "Mind your feet, I'm carrying.")),
    "washerwoman": Job((190, 200, 215), 6, 16, "washing clothes",
                       ("These won't wash themselves.", "Lye's hard on the hands.", "The river's cold today.")),
    "ratcatcher": Job((135, 125, 105), 18, 26, "hunting rats",
                      ("Big ones in the cellars this year.", "A copper a tail.", "Don't ask what's in the sack.")),
})
JOBS.update({
    # the households in a city's other houses, and its street folk (game/routines.py)
    "clerk": Job((190, 190, 210), 8, 17, "copying ledgers",
                 ("Debits on the left. Always the left.", "Ink on my fingers till the day I die.",
                  "The moneylender pays by the page.")),
    "porter": Job((175, 155, 120), 6, 17, "carrying parcels",
                  ("Mind your back, coming through!", "A copper a load, two up the hill.", "My knees, my knees.")),
    "maid": Job((210, 195, 185), 6, 17, "cleaning",
                ("Wipe your feet.", "The inn's floors don't scrub themselves.", "Spilled ale everywhere, every night.")),
    "seamstress": Job((215, 170, 190), 8, 18, "sewing by the window",
                      ("Hold still, I'll take your measure.", "Fine thread's dear this year.", "Needle and patience.")),
    "messenger": Job((220, 210, 120), 6, 18, "running messages",
                     ("Can't stop!", "A letter for the guildhall, and quick.", "I know every alley in {town}.")),
    "elder": Job((185, 180, 175), 7, 18, "sitting in the sun",
                 ("In my day the walls were half the height.", "I remember the old king.", "Sit, sit. My knees.")),
    "widow": Job((165, 160, 170), 7, 17, "keeping house",
                 ("He's in the graveyard now, my Tam.", "The days are long alone.", "Mind how you go, love.")),
    "street sweeper": Job((170, 165, 140), 5, 18, "sweeping the streets",
                          ("Someone's got to.", "You'd not believe what folk drop.", "Mind the pile.")),
    "lamplighter": Job((245, 215, 120), 17, 20, "lighting the street lamps",
                       ("Dark comes early this time of year.", "Every lamp in the quarter, every night.")),
    "water carrier": Job((150, 190, 230), 5, 18, "carrying water from the fountain",
                         ("Two buckets, forty trips.", "Cleanest water in {town}, from the fountain.")),
    "chimney sweep": Job((95, 90, 90), 6, 17, "sweeping chimneys",
                         ("Soot in my ears, soot in my bread.", "Good luck to shake my hand, they say.")),
    "town crier": Job((235, 190, 110), 7, 18, "crying the news",
                      ("Hear ye, hear ye!", "News for a copper. Good news for two.", "I've the loudest voice in {town}.")),
    # the people of the halls (game/halls.py)
    "bathkeeper": Job((150, 210, 220), 6, 20, "keeping the bathhouse",
                      ("The water's hot. Walk right in.", "Nothing like a soak after the road.", "Towels by the hearth.")),
    "moneylender": Job((225, 205, 110), 8, 18, "counting coins",
                       ("Gold keeps. Nothing else does.", "Interest is only fair.", "Trinkets? I pay better than the stalls.")),
    "gravedigger": Job((140, 130, 115), 6, 18, "tending the graves",
                       ("Six feet. Always six feet.", "They're quiet company.", "Don't walk on the graves.")),
    "healer": Job((175, 230, 175), 6, 20, "tending the sick",
                  ("Sit down, let me look at that.", "Rest and poultices: that's the cure for most things.",
                   "Wolf fever? I can treat that.")),
    "patient": Job((170, 165, 160), 0, 24, "lying abed",
                   ("Ohh, my head.", "The healer says a week more.", "Water, please.")),
    "matron": Job((215, 180, 170), 6, 21, "minding the foundlings",
                  ("Don't run in the halls!", "Twelve mouths and one pot.", "They need a home, every one.")),
    "sellsword": Job((200, 140, 110), 7, 23, "between jobs",
                     ("Need a blade? I'm for hire.", "Goblins, wolves, worse. I've seen it.",
                      "Read the board: there's always work.", "Buy me a drink and I'll tell you a tale.")),
    "brewer": Job((210, 170, 90), 5, 17, "minding the vats",
                  ("The inns drink all I make.", "Barley, hops and patience.", "Taste this. Go on.")),
    "tanner": Job((160, 130, 90), 6, 17, "scraping hides",
                  ("You get used to the smell. Mostly.", "Bring me pelts: I pay well.", "Lye and patience.")),
    "mage": Job((180, 140, 255), 10, 21, "working a spell at the circle",
                ("Do not step on the circle.", "The stars are speaking tonight.", "Strange stones? Bring them to me.",
                 "Magic is mostly reading, I'm sorry to say.")),
    "apprentice": Job((160, 150, 235), 7, 21, "copying spells",
                      ("The master says I'll cast fire by spring.", "I swept the tower twice today.", "Don't tell the master.")),
    "schoolmaster": Job((200, 195, 175), 8, 16, "teaching letters",
                        ("A, B, C: the rest follows.", "Sit still, all of you!", "Can you read, traveller?")),
    "master-at-arms": Job((210, 200, 180), 6, 17, "drilling the recruits",
                          ("Shields up! Up!", "Again! Until you get it right.", "Half these recruits couldn't fight a goose.")),
    "groom": Job((185, 150, 105), 5, 20, "grooming the horses",
                 ("These are the guards' horses. Hands off.", "Mucking out, every morning.",
                  "A warhorse eats twice what you do.", "Want your own? Ask a stablehand at an inn.")),
    "recruit": Job((185, 185, 200), 6, 17, "drilling with the spear",
                   ("My arms ache.", "One day I'll guard the king.", "Don't tell the master-at-arms I sat down.")),
})
STREET_FOLK = ("street sweeper", "lamplighter", "water carrier", "chimney sweep", "town crier")
ROOM_PRICE = 8                # coins for a night upstairs at an inn
EVENING = {"inn": "at {inn}", "green": "chatting on the green", "home": "at supper at home"}
SERVICE = (9, 11)             # the hours of the Sunday service, at a city's temple or chapel
CHURCHGOING = 1.0             # hours before it they set off
CHURCH_WALK = 110             # tiles away at most, the churchgoers
WORSHIP = {"townsperson", "homemaker", "child", "merchant", "baker", "butcher", "shopkeeper", "blacksmith",
           "labourer", "washerwoman", "guildmaster", "alchemist", "servant", "cook", "librarian", "beggar",
           "bard", "mummer", "pit fighter", "hangman", "king", "prince", "queen", "concubine"}   # (and the crafts)
SPOUSE = 0.45                 # how often someone with a house of their own is married, with a homemaker at home
WORSHIP |= set(CRAFTS) | {"clerk", "porter", "maid", "seamstress", "messenger", "elder", "widow", "street sweeper",
                          "lamplighter", "water carrier", "chimney sweep", "town crier", "bathkeeper", "moneylender",
                          "gravedigger", "matron", "brewer", "tanner", "schoolmaster", "recruit", "orphan"}

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
    shift: tuple | None = None      # (start, end) hours of work, if not their trade's (end past 24: overnight)
    routine: list = field(default_factory=list)    # (from, to, doing, tiles): an hour-by-hour day (the court)
    haunts: list = field(default_factory=list)     # (doing, tiles, "day" or "evening"): where an idler goes
    seed: int = 0                   # for an idler's comings and goings
    chase: object = None            # a guard: the thief they're after (game/citylife.py)
    fleeing: float | None = None    # a thief: running from the guards till this minute
    exposed: bool = False           # a thief: seen at it, so known for what they are
    loot: int = 0                   # a thief: coins taken
    friends: list = field(default_factory=list)    # a child: the others they play with (them too)
    it: bool = False                # a child: "it", in a game of tag
    saddled: bool = False           # a horse: saddled, ready to ride (game/horses.py)
    keeper: str = ""                # a horse: whose it is, if not anyone's for the saddling ("the guards")
    talk_until: float = 0.0         # stopped to talk with someone till this minute (game/mingling.py)
    talk_doing: str = ""            # ... "chatting with Bryn"
    partner: object = None          # ... and who with
    chat_after: float = 0.0         # won't stop to talk again before this minute

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
    def shown_kind(self) -> str:
        """What they look like: a thief passes for a townsperson until they're seen at it."""
        return "townsperson" if self.kind == "thief" and not self.exposed else self.kind

    @property
    def title(self) -> str:
        if self.kind in PETS:
            return f"{self.name}, the town {self.kind}"
        if self.animal:
            return f"A {self.kind}"
        if self.kind == "concubine":
            return f"{self.name}, the royal concubine"
        if self.kind in ROYAL:
            return f"{self.kind.capitalize()} {self.name}"
        return f"{self.name}, the {self.shown_kind}"


# ----------------------------------------------------------------- populating a settlement

def populate(level, site, rng: random.Random) -> None:
    """The people who live and work here, and their animals."""
    t = level.tiles
    buildings = {b.kind: b for b in level.buildings if b.kind in ("inn", "bakery", "butcher", "armoury")}
    houses = [b for b in level.buildings if b.kind == "house"]
    rng.shuffle(houses)
    fields_ = [p for p in level.places if p.kind == "field"]
    water = [p for p in level.places if p.kind in ("pier", "shore")]
    camp = next((p for p in level.places if p.kind == "camp"), None)
    inn = buildings.get("inn")
    smithy = next((b for b in level.buildings if b.kind == "smithy"), None)
    barracks = [b for b in level.buildings if b.kind == "barracks"]
    gates = [p for p in level.places if p.kind == "gate"]
    walls = [p for p in level.places if p.kind == "walls"]
    if site.kind == "fort":
        watch = bool(getattr(site, "ward", ""))
        jobs = ["guard"] * (3 if watch else 4) + ["archer"] * (2 if watch else 3) + ["blacksmith"] * bool(smithy)
    elif site.kind == "city":               # the guards and everyone else: game/citylife.py
        jobs = ["baker", "butcher", "innkeeper", "barkeeper", "shopkeeper"] + ["blacksmith"] * bool(smithy) \
            + ["archer"] * min(2, len(walls))
    elif site.kind == "town":
        jobs = ["baker", "butcher", "innkeeper", "barkeeper", "shopkeeper"] + ["farmer"] * min(2, len(fields_))
    elif site.kind == "village":
        jobs = ["farmer"] * min(3, max(1, len(fields_) - 1))
    else:
        jobs = ["innkeeper", "barkeeper"]
    if site.kind in ("town", "village"):
        jobs += ["fisherman"] * bool(water) + ["lumberjack"] * bool(camp)
    paddock = next((p for p in level.places if p.kind == "pasture" and p.animal == "horse"), None)
    if paddock is not None:
        jobs += ["stablehand"]
    green = settle_green(level)
    evening, evening_kind = (inn.floor(t), "inn") if inn else (green, "green")
    used_names = set()
    for i, job in enumerate(jobs):
        name = person_name(rng, used_names)
        house = None
        if job in ("innkeeper", "barkeeper"):
            if inn is None:
                continue
            # The beds are upstairs for guests: the barkeeper beds down behind the bar, the
            # innkeeper by the hearth.
            near = T.COUNTER if job == "barkeeper" else T.HEARTH
            floor = [c for c in inn.floor(t) if t[c] not in (T.STAIRS_UP, T.STAIRS_DOWN)]
            home = [c for c in floor if any(t[c[0] + dx, c[1] + dy] == near
                                            for dx in (-1, 0, 1) for dy in (-1, 0, 1))] or floor
        elif job == "stablehand" and paddock is not None and not houses:   # sleeps in the hay by the paddock
            home = paddock.tiles
        elif job in ("guard", "archer") and barracks:      # soldiers sleep in the barracks
            home = [c for b in barracks for c in b.floor(t) if t[c] == T.BED] or barracks[0].floor(t)
        elif houses:
            house = houses.pop()
            house.name = f"the {name.split()[1]} house"
            house.owner = job
            home = [c for c in house.floor(t) if t[c] == T.BED] or house.floor(t)
        else:
            home = green
        work = workplace(level, job, i, fields_, water, camp, dict(buildings, smithy=smithy), gates, walls)
        if not work or not home:
            continue
        x, y = work[0]
        worker = Actor(job, name, x, y, home=home, work=work, evening=evening or green,
                       evening_kind=evening_kind if evening else "green")
        level.actors.append(worker)
        if house is not None and rng.random() < SPOUSE:
            marry(level, rng, used_names, worker, house)
        if job == "lumberjack":
            if house is not None:
                lean_axe(level, house)
            else:                         # no house of their own: the axe is left at the camp
                spot = next((c for c in work if not T.ROOF[t[c]]), work[0])
                items.drop(level, *spot, "axe")
    if site.kind == "city":
        from . import citylife
        citylife.populate(level, site, rng, used_names, evening or green, evening_kind if evening else "green")
    for place in (p for p in level.places if p.kind == "stable"):      # the guards' horses and their groom
        stalls = [c for c in place.tiles if T.ROOF[t[c]]] or place.tiles
        yard = [c for c in place.tiles if not T.ROOF[t[c]]] or place.tiles
        for _ in range(4 if site.kind == "city" else 3):
            x, y = rng.choice(place.tiles)
            level.actors.append(Actor("horse", "horse", x, y, home=stalls, work=place.tiles, evening=stalls,
                                      keeper="the guards"))
        x, y = rng.choice(yard)
        level.actors.append(Actor("groom", person_name(rng, used_names), x, y, home=stalls, work=yard, evening=stalls,
                                  routine=[(5, 7, "mucking out the stable", stalls), (7, 12, "grooming the horses", yard),
                                           (12, 13, "eating in the stable", stalls), (13, 17, "exercising a horse", yard),
                                           (17, 20, "feeding the horses", stalls)]))
    for place in (p for p in level.places if p.kind == "pasture"):
        for _ in range(rng.randint(3, 6) if place.animal != "horse" else 2):
            x, y = rng.choice(place.tiles)
            level.actors.append(Actor(place.animal, place.animal, x, y, work=place.tiles))
    if site.kind in ("city", "town", "village") and green:
        yard = settle_yard(level)
        for _ in range(rng.randint(3, 5)):
            x, y = rng.choice(yard)
            level.actors.append(Actor("hen", "hen", x, y, work=yard))
        if site.kind in ("city", "town"):
            pet = rng.choice(PETS)
            x, y = rng.choice(yard)
            level.actors.append(Actor(pet, rng.choice(PET_NAMES[pet]), x, y, work=yard))
    if site.kind in ("town", "village"):               # someone in every house
        for house in houses:
            name = person_name(rng, used_names)
            house.name, house.owner = f"the {name.split()[1]} house", "townsperson"
            inside = house.floor(t)
            beds = [c for c in inside if t[c] == T.BED] or inside
            haunts = [("chatting on the green", green, "any"), ("at home", inside, "day")]
            if inn is not None:
                haunts.append(("at {inn}", inn.floor(t), "evening"))
            level.actors.append(Actor("townsperson", name, *rng.choice(inside), home=beds, work=inside,
                                      evening=evening or green, haunts=haunts,
                                      shift=(rng.randint(6, 9), rng.randint(20, 23)), seed=rng.randrange(1 << 30)))
        houses.clear()
    if site.kind in ("city", "town", "village"):
        from .structures import empty_houses
        empty_houses(level, site, rng)
        rooms = [c for b in level.buildings if b.kind == "house" for c in b.floor(t) if t[c] in (T.WOOD_FLOOR, T.STONE_FLOOR)]
        if rooms:
            items.drop(level, *rng.choice(rooms), "shovel")


def marry(level, rng: random.Random, used: set, worker: Actor, house, spots=None) -> Actor:
    """A husband or wife for someone with a house: they keep house and cook for them, and the
    worker comes home for supper of an evening."""
    t = level.tiles
    inside = house.floor(t)
    family = worker.name.split()[-1]
    for _ in range(30):
        name = f"{rng.choice(FIRST)} {family}"
        if name not in used and name != worker.name:
            break
    used.add(name)
    kitchen = [c for c in inside if any(level.in_bounds(c[0] + dx, c[1] + dy) and t[c[0] + dx, c[1] + dy]
                                        in (T.HEARTH, T.TABLE) for dx in (-1, 0, 1) for dy in (-1, 0, 1))] or inside
    to = worker.name.split()[0]
    from .routines import homemaker
    spouse = Actor("homemaker", name, *rng.choice(inside), home=worker.home, work=kitchen, evening=inside,
                   routine=homemaker(spots, rng, inside, house, to, level))
    level.actors.append(spouse)
    worker.evening, worker.evening_kind = inside, "home"
    return spouse


PET_NAMES = {"dog": ["Biscuit", "Rufus", "Bramble", "Patch", "Scout", "Moss"],
             "cat": ["Whiskers", "Soot", "Marmalade", "Thistle", "Pip", "Smudge"]}


def lean_axe(level, house) -> None:
    """The lumberjack's axe, leaning by the wall outside their door."""
    t = level.tiles
    dx, dy = house.door
    around = [(dx + i, dy + j) for i in (-2, -1, 0, 1, 2) for j in (-1, 0, 1)]
    spots = [c for c in around if level.in_bounds(*c) and T.WALK[t[c]] and not T.ROOF[t[c]]
             and not T.WATERY[t[c]] and not house.contains(*c)]
    spots.sort(key=lambda c: (t[c] in (T.PATH, T.STREET), abs(c[0] - dx) + abs(c[1] - dy)))
    if spots:
        items.drop(level, *spots[0], "axe")


def person_name(rng: random.Random, used: set) -> str:
    for _ in range(50):
        name = f"{rng.choice(FIRST)} {rng.choice(FAMILY)}"
        if name not in used:
            break
    used.add(name)
    return name


def workplace(level, job: str, i: int, fields_, water, camp, buildings, gates=(), walls=()) -> list:
    t = level.tiles
    if job == "guard":
        return gates[i % len(gates)].tiles if gates else []
    if job == "archer":
        return walls[i % len(walls)].tiles if walls else []
    if job == "farmer":
        return fields_[i % len(fields_)].tiles if fields_ else []
    if job == "fisherman":
        return water[0].tiles if water else []
    if job == "lumberjack":
        return camp.tiles if camp else []
    if job == "stablehand":
        place = next((p for p in level.places if p.kind == "pasture" and p.animal == "horse"), None)
        if place is None:
            return []
        xs, ys = [c[0] for c in place.tiles], [c[1] for c in place.tiles]     # by the paddock fence
        ring = [(x, y) for x in range(min(xs) - 2, max(xs) + 3) for y in range(min(ys) - 2, max(ys) + 3)
                if level.walkable(x, y) and (x, y) not in place.tiles and not T.ROOF[t[x, y]]]
        return ring or place.tiles
    kind = {"baker": "bakery", "butcher": "butcher", "innkeeper": "inn", "barkeeper": "inn",
            "shopkeeper": "armoury", "blacksmith": "smithy"}.get(job)
    if kind is None:
        return []
    b = buildings.get(kind)
    if b is None:
        return []
    floor = b.floor(t)
    if job == "innkeeper":
        return [c for c in floor if t[c] not in (T.STAIRS_UP, T.STAIRS_DOWN)]
    near_counter = [c for c in floor if any(t[c[0] + dx, c[1] + dy] in (T.COUNTER, T.OVEN, T.RACK, T.FORGE, T.ANVIL)
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

def hours(a: Actor) -> tuple[int, int]:
    """(start, end) of their work; an end past 24 runs on past midnight."""
    return a.shift or (JOBS[a.kind].start, JOBS[a.kind].end)


def within(hour: float, start: float, end: float) -> bool:
    return start <= hour < end or start <= hour + 24 < end


def on_duty(a: Actor, minutes: float) -> bool:
    """Whether someone's at work at this time."""
    if a.animal:
        return False
    start, end = hours(a)
    return within(float(hour_of_day(minutes)), start, end)


def plan(a: Actor, hour: float, names: dict) -> tuple[list, str]:
    """(where they should be, what they're doing) at this hour."""
    if a.animal:
        if a.kind == "hen":
            return a.work, "pecking about" if 6 <= hour < 20 else "roosting"
        if a.kind in PETS:
            awake = "nosing about" if a.kind == "dog" else "watching everything"
            return a.work, awake if 6 <= hour < 21 else "curled up asleep"
        return a.work, "grazing" if 6 <= hour < 20 else "resting"
    if a.routine:
        today = names.get("weekday", "")
        for start, end, doing, tiles, *days in a.routine:
            if within(hour, start, end) and tiles and (not days or not today or today in days[0]):
                return tiles, doing.format(**names)
        if hour >= BEDTIME + 1 or hour < 6:
            return a.home, "asleep"
        return a.home, "in their chambers" if a.kind in ROYAL else "at home"
    start, end = hours(a)
    if a.haunts:
        if within(hour, start, end):
            return haunt(a, hour, names)
        return a.home, "asleep" if not within(hour, end - 1, end + 1) else "at home"
    job = JOBS[a.kind]
    if within(hour, start, end):
        return a.work, job.doing.format(**names)
    if a.kind in ("innkeeper", "barkeeper", "gaoler", "prisoner"):
        return a.home, "asleep"
    if end > 24:                         # the night watch: sleep the morning, then a few hours off
        if within(hour, end - 24, end - 16):
            return a.home, "asleep"
        return a.evening, EVENING[a.evening_kind].format(**names)
    if hour >= end and hour < BEDTIME:
        return a.evening, EVENING[a.evening_kind].format(**names)
    return a.home, "asleep" if hour >= BEDTIME + 1 or hour < start - 1 else "at home"


def church_of(level):
    return next((b for b in level.buildings if b.kind in ("temple", "chapel")), None)


def sunday(level, out: list, hour: float, names: dict) -> None:
    """The Sunday service: the priest at the altar, and most of the city in the pews."""
    if names.get("weekday") != "Sunday" or not within(hour, SERVICE[0] - CHURCHGOING, SERVICE[1]):
        return
    church = church_of(level)
    if church is None:
        return
    t = level.tiles
    inside = church.floor(t)
    pews = [c for c in inside if t[c] == T.BENCH] or inside
    altar = [c for c in inside if any(level.in_bounds(c[0] + dx, c[1] + dy) and t[c[0] + dx, c[1] + dy] == T.ALTAR
                                      for dx in (-2, -1, 0, 1, 2) for dy in (-1, 0, 1))] or inside
    room = len(inside)
    dx, dy = church.door
    def far(a):
        return max(abs(a.x - dx), abs(a.y - dy) * 2)
    going = "at the Sunday service" if hour >= SERVICE[0] else "on the way to the Sunday service"
    faithful = sorted((i for i, a in enumerate(level.actors) if a.kind in WORSHIP and a.chase is None
                       and a.fleeing is None and far(a) <= CHURCH_WALK), key=lambda i: far(level.actors[i]))
    for n, i in enumerate(faithful[:room]):
        out[i] = (pews if n < len(pews) else inside, going)
    for i, a in enumerate(level.actors):
        if a.kind == "priest":
            out[i] = (altar, "leading the Sunday service")


def plans(level, hour: float, names: dict) -> list:
    """Everyone's plan(), but with no more than INN_CROWD in the inn: the staff, whoever's
    already inside, then the first to come (the same ones all evening). The rest go elsewhere.
    On a Sunday morning, the city goes to the service (sunday)."""
    out = [plan(a, hour, names) for a in level.actors]
    sunday(level, out, hour, names)
    inn = next((b for b in level.buildings if b.kind == "inn"), None)
    if inn is None:
        return out
    bound = [i for i, (area, _) in enumerate(out) if area and inn.contains(*area[0])
             and not level.actors[i].animal]
    if len(bound) <= INN_CROWD:
        return out
    staff = [i for i in bound if level.actors[i].kind in ("innkeeper", "barkeeper")]
    guests = [i for i in bound if i not in staff]
    day = names.get("day", 0)
    guests.sort(key=lambda i: (not inn.contains(level.actors[i].x, level.actors[i].y),
                               random.Random(f"{level.actors[i].name}{day}").random()))
    away = guests[max(0, INN_CROWD - len(staff)):]
    if not away:
        return out
    if any(b.kind == "guardhouse" for b in level.buildings):    # a city: out walking the streets
        from .citylife import streets
        green, word = streets(level), "wandering the streets"
    else:
        green = getattr(level, "_green", None)
        if green is None:
            green = level._green = settle_green(level)
        word = "chatting on the green"
    for i in away:
        a = level.actors[i]
        if hour >= BEDTIME or hour < 4 or not green:
            out[i] = (a.home, "at home")
        else:
            out[i] = (green, word)
    return out


def haunt(a: Actor, hour: float, names: dict) -> tuple[list, str]:
    """Somewhere an idler goes: one of their haunts, a different one every HAUNT_MINUTES or so
    (each keeps their own times), the evening ones once it's evening."""
    when = "evening" if hour >= 18 or hour < 4 else "day"
    choices = [h for h in a.haunts if h[2] in (when, "any") and h[1]] or [h for h in a.haunts if h[1]]
    if not choices:
        return a.home, "at home"
    slot = int((hour * 60 + a.seed % HAUNT_MINUTES) // HAUNT_MINUTES)
    pick = random.Random(a.seed * 7919 + names.get("day", 0) * 131 + slot).randrange(len(choices))
    doing, tiles, _ = choices[pick]
    return tiles, doing.format(**names)


def names_for(level, engine) -> dict:
    inn = next((b.name for b in level.buildings if b.kind == "inn"), "the inn")
    herd = next((p.animal for p in level.places if p.kind == "pasture"), "sheep")
    crop = T.TILES[level.crop].name if level.crop is not None else "vegetables"
    day = int(engine.minutes // 1440) if engine is not None else 0
    return {"inn": inn, "town": level.name, "crop": crop, "herd": ANIMALS[herd].plural, "price": ROOM_PRICE,
            "day": day, "weekday": weekday(engine.minutes) if engine is not None else ""}


def walk_costs(level) -> np.ndarray:
    """What each tile costs people to walk; 0 where they won't (deep water, walls)."""
    if getattr(level, "_walk_costs", None) is None:
        t = level.tiles
        cost = np.round(T.MINUTES[t] * 10).astype(np.int32)
        cost[~T.WALK[t]] = 0
        cost[t == T.WATER] = 60          # they'd rather not wade
        level._walk_costs = np.ascontiguousarray(cost)
    return level._walk_costs


PATH_MARGIN = (24, 12)        # a path is first looked for within this much of a box round its two ends


def find_path(level, start, goal) -> list:
    """The cheapest way from start to goal. Most walks are short (about a room, a stall, a
    street), so it's first looked for in a window round the two ends, and over the whole map
    only if there's no way within it."""
    cost = walk_costs(level)
    if not cost[goal]:
        return []
    mx, my = PATH_MARGIN
    x0, x1 = max(0, min(start[0], goal[0]) - mx), min(cost.shape[0], max(start[0], goal[0]) + mx + 1)
    y0, y1 = max(0, min(start[1], goal[1]) - my), min(cost.shape[1], max(start[1], goal[1]) + my + 1)
    if (x1 - x0) * (y1 - y0) * 2 < cost.size:
        near = cheapest(cost[x0:x1, y0:y1], (start[0] - x0, start[1] - y0), (goal[0] - x0, goal[1] - y0))
        if near:
            return [(x + x0, y + y0) for x, y in near]
    return cheapest(cost, start, goal)


def cheapest(cost: np.ndarray, start, goal) -> list:
    if not cost[start] or not cost.flags.c_contiguous:
        cost = np.ascontiguousarray(cost).copy()
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
        for a, (area, a.doing) in zip(level.actors, plans(level, hour, names)):
            if a.chase is not None or a.fleeing is not None:
                a.doing = "chasing a thief" if a.chase is not None else "running from the guards"
                continue                       # game/citylife.py moves them
            if a.kind == "child" and a.doing == "playing tag" and a.friends:
                continue                       # ... and children at their games
            if a.talk_until > minutes and a.doing != "asleep" and a.doing != "at the Sunday service":
                a.doing = a.talk_doing         # stopped for a word with someone (game/mingling.py)
                continue
            a.budget = min(a.budget + elapsed, MOST_STEPS * pace(a))
            while a.budget >= pace(a):
                a.budget -= pace(a)
                if a.kind in PETS:
                    pet_step(level, a, area, you, taken, rng)
                else:
                    step(level, a, area, taken, rng)
    level.sim_minutes = minutes


def pace(a: Actor) -> float:
    return ANIMALS[a.kind].minutes if a.animal else WALK_MINUTES


def snap(level, hour: float, names: dict, rng: random.Random, you) -> None:
    """Everyone where they'd be by now."""
    taken = {you} if you else set()
    for a, (area, a.doing) in zip(level.actors, plans(level, hour, names)):
        if not area:
            continue                     # nowhere to be: they stay put
        free = [c for c in area if c not in taken] or area
        a.x, a.y = rng.choice(free)
        taken.add((a.x, a.y))
        a.goal, a.path, a.budget, a.stuck = None, [], 0.0, 0
        a.talk_until, a.partner = 0.0, None


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


def pet_step(level, a: Actor, area: list, you, taken: set, rng: random.Random) -> None:
    """A dog or cat: trots after you if you're near, keeping a step or two off (the dog more
    keenly than the cat), and otherwise wanders about the town."""
    keen = 0.75 if a.kind == "dog" else 0.45
    here = (a.x, a.y)
    def gap(c):
        return max(abs(c[0] - you[0]), abs(c[1] - you[1]) * 2) if you else 0
    near = [c for c in ((a.x + dx, a.y + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1))
            if c != here and level.walkable(*c) and not T.WATERY[level.tiles[c]] and c not in taken]
    if not near:
        return
    if you and HEEL < gap(here) <= FOLLOW:
        if rng.random() < keen:
            move(a, min(near, key=gap), taken)
        return
    if you and gap(here) <= HEEL:
        if rng.random() < 0.15:
            move(a, rng.choice([c for c in near if gap(c) > 0] or near), taken)
        return
    if rng.random() < 0.4:
        home = area_set(a, area)
        inside = [c for c in near if c in home]
        if home and here not in home:
            inside = [min(near, key=lambda c: min(abs(c[0] - h[0]) + abs(c[1] - h[1]) for h in area[::7] or area))]
        if inside:
            move(a, rng.choice(inside), taken)


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
    if a.kind in PETS:
        a.met = True
        return rng.choice(PETTING[a.kind]).format(name=a.name)
    if a.animal:
        info = ANIMALS[a.kind]
        return f"You push past the {a.kind}. It {info.sound}."
    if a.doing == "asleep":
        return f"{a.name} is fast asleep."
    names = names_for(level, engine)
    line = rng.choice(JOBS[a.shown_kind].lines).format(**names)
    if a.fleeing is not None:
        return f"{a.name} shoves past you, running."
    if a.kind in ROYAL:
        if not a.met:
            a.met = True
            return f'{a.title} regards you: "{line}"'
        return f'{a.title}: "{line}"'
    if not a.met:
        a.met = True
        return f'{a.title}: "Hello! I\'m {a.name.split()[0]}. {line}"'
    return f'{a.name.split()[0]}: "{line}"'


PETTING = {
    "dog": ("You pet {name}. Its tail wags so hard its whole back end wiggles.",
            "You scratch {name} behind the ears. It leans into your hand.",
            "{name} rolls over for a belly rub, and you oblige."),
    "cat": ("You pet {name}. It purrs and arches into your hand.",
            "{name} rubs against your legs, then pretends it didn't.",
            "You scratch {name} under the chin. It blinks slowly at you."),
}


def describe(a: Actor) -> list[str]:
    lines = [a.title]
    if a.doing:
        lines.append(a.doing.capitalize())
    return lines


def crop_words(stage: str) -> str:
    return STAGE_WORDS.get(stage, stage)
