"""Hour-by-hour days for a city's people: game/citylife.py hands them out as each is made.

A routine is a list of (from, to, doing, tiles) or (from, to, doing, tiles, days), the first that
fits the hour (and the day of the week, if it names days) wins; out of all of them, they're at
home, and asleep at night (people.plan). So someone's day goes through many things, not just
work and bed:

- craftsfolk: breakfast, water from the fountain or a sweep of the doorstep, the morning at work,
  dinner at home or a pie from the stalls, the afternoon's work, then the market, the inn or
  supper; on market day (MARKET_DAY) they sell from the square in the afternoon
- merchants: setting up the stall, trading, a bite at the stall, packing up, the inn
- homemakers: breakfast, water, sweeping and scrubbing, the market, dinner, beating the rugs,
  gossip by the fountain, supper
- children: lessons of a weekday morning, if there's a school (else chores), tag after
- labourers, washerwomen, the priest, the bard and mummers, the pit fighters, the guildmaster,
  the alchemist, and the city's own street folk: sweepers, lamplighters, water carriers,
  chimney sweeps, the town crier
- the households in the city's other houses: clerks, porters, maids, seamstresses, messengers,
  elders and widows, each with a day of their own (HOUSEHOLDS)
- the people of the halls (game/halls.py): the bathkeeper, the moneylender, the gravedigger, the
  healer, the matron, the sellswords, the brewer, the tanner, the mage and apprentices, the
  schoolmaster, the master-at-arms and recruits
"""
from __future__ import annotations

import random

import numpy as np

from . import tiles as T

MARKET_DAY = frozenset({"Saturday"})
WEEKDAYS = frozenset({"Monday", "Tuesday", "Wednesday", "Thursday", "Friday"})
STALL_NAMES = ["the fruit stall", "the fishmonger's stall", "the cloth stall", "the spice stall", "the cheese stall",
               "the potter's stall", "the candle stall", "the trinket stall", "the herb stall", "the pie stall"]
HOUSEHOLDS = ("clerk", "porter", "maid", "seamstress", "messenger", "elder", "widow", "porter", "clerk", "maid")


def near(level, tiles: list, kinds, reach: int = 1) -> list:
    t = level.tiles
    kinds = kinds if isinstance(kinds, (tuple, list, set)) else (kinds,)
    return [(x, y) for x, y in tiles if any(level.in_bounds(x + dx, y + dy) and t[x + dx, y + dy] in kinds
                                            for dx in range(-reach, reach + 1) for dy in range(-reach, reach + 1))]


def doorstep(level, house) -> list:
    """Just outside a house's door: where its people sweep, beat rugs and sit in the sun."""
    t = level.tiles
    dx, dy = house.door
    out = [(dx + i, dy + j) for i in (-2, -1, 0, 1, 2) for j in (-1, 0, 1)]
    return [c for c in out if level.in_bounds(*c) and T.WALK[t[c]] and not T.ROOF[t[c]] and not T.WATERY[t[c]]
            and not house.contains(*c)]


def kitchen(level, inside: list) -> list:
    return near(level, inside, (T.HEARTH, T.TABLE)) or inside


class Spots:
    """Where the things people go to are, in one part of a city: worked out once."""

    def __init__(self, level, square: list, streets: list, inn: list, stalls: list):
        t = level.tiles
        self.level = level
        self.square = square
        self.streets = streets
        self.inn = inn
        self.stalls = [(STALL_NAMES[i % len(STALL_NAMES)], s) for i, s in enumerate(stalls) if s]
        self.water = near(level, streets + square, (T.FOUNTAIN, T.WELL), 3) or square
        places = {}
        for p in level.places:
            places.setdefault(p.kind, []).append(p)
        self.places = places
        def floor_of(kind):
            b = next((b for b in level.buildings if b.kind == kind), None)
            return b.floor(t) if b else []
        self.floor_of = floor_of
        church = floor_of("temple") or floor_of("chapel")
        self.pews = [c for c in church if t[c] == T.BENCH] or church
        self.altar = near(level, church, T.ALTAR, 2) or church
        self.garden = next((p.tiles for p in places.get("garden", [])), [])
        self.market = next((p.tiles for p in places.get("market", [])), [])
        self.graves = near(level, next((p.tiles for p in places.get("graveyard", [])), []), T.GRAVE)
        self.yard = next((p.tiles for p in places.get("training yard", [])), [])
        self.bath = near(level, floor_of("bathhouse"), T.POOL)
        self.notice = []                     # standing before the notice board
        if (t == T.NOTICE).any():
            nx, ny = (int(v) for v in np.argwhere(t == T.NOTICE)[0])
            self.notice = [(nx + dx, ny + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)
                           if level.walkable(nx + dx, ny + dy) and not T.ROOF[t[nx + dx, ny + dy]]]
        self.counting = floor_of("counting house")
        self.guild = floor_of("guildhall")
        self.hall = floor_of("adventurers' hall")
        self.school = floor_of("school")
        self.desks = [c for c in self.school if t[c] == T.BENCH] or self.school
        self.healing = floor_of("healer")
        self.pit = next((p.tiles for p in places.get("pitside", [])), [])
        stage = floor_of("playhouse")
        self.audience = [c for c in stage if t[c] == T.BENCH]

    def stall(self, rng: random.Random) -> tuple[str, list]:
        if self.stalls:
            return rng.choice(self.stalls)
        if self.market:
            return "the market row", self.market
        return "the square", self.square

    def any(self, *options) -> list:
        """The first of these that this part of the city has."""
        return next((o for o in options if o), self.streets)


# ----------------------------------------------------------------- the days

def evening(spots: Spots, rng: random.Random, home: list, married: bool, end: float) -> list:
    """From the end of work till bed: supper at home if there's someone to cook it, else the inn
    (or the playhouse, or the square)."""
    if married:
        return [(end, 21, "at supper at home", kitchen(spots.level, home))]
    out = []
    if spots.audience and rng.random() < 0.25:
        out.append((max(end, 19), 22, "watching the players", spots.audience))
    return out + [(end, 21.5, "at {inn}", spots.inn or spots.square)]


def craftsperson(spots: Spots, rng: random.Random, doing: str, house, inside: list, married: bool,
                 shift: tuple) -> list:
    start, end = shift
    lv = spots.level
    stall_name, stall = spots.stall(rng)
    morning = rng.choice([("drawing water at the fountain", spots.water), ("sweeping the doorstep", doorstep(lv, house))])
    dinner = (("at dinner at home", kitchen(lv, inside)) if married or rng.random() < 0.5
              else (f"buying a pie at {stall_name}", stall))
    sell_name, sell = spots.stall(rng)
    return [
        (13, end, "selling wares in the square", spots.square, MARKET_DAY),
        (start - 1, start - 0.5, "breakfasting", kitchen(lv, inside)),
        (start - 0.5, start, *morning),
        (start, 12, doing, inside),
        (12, 13, *dinner),
        (13, end, doing, inside),
        (end, end + 1, f"browsing {sell_name}", sell),
    ] + evening(spots, rng, inside, married, end + 1)


def merchant(spots: Spots, rng: random.Random, stall: list) -> list:
    return [
        (6, 7, "loading a handcart with goods", spots.streets),
        (7, 8, "setting out the stall", stall),
        (8, 12, "minding the stall", stall),
        (12, 13, "eating behind the stall", stall),
        (13, 18, "crying their wares", stall, MARKET_DAY),
        (13, 18, "minding the stall", stall),
        (18, 19, "packing up the stall", stall),
        (19, 21.5, "counting the day's takings at {inn}", spots.inn or spots.square),
    ]


def homemaker(spots: Spots | None, rng: random.Random, inside: list, house, to: str, level) -> list:
    """Someone keeping house: much more to the day than the fire."""
    cook = kitchen(level, inside)
    if spots is None:                    # a town or village house: no square, no stalls
        return [(6, 8, f"cooking breakfast for {to}", cook), (8, 11, "keeping house", inside),
                (11, 13, f"cooking dinner for {to}", cook), (13, 16, "mending by the fire", cook),
                (16, 19, f"preparing supper for {to}", cook), (19, 21, f"at supper with {to}", inside)]
    step = doorstep(level, house) or inside
    stall_name, stall = spots.stall(rng)
    return [
        (9, 12, "at the Saturday market", [c for _, s in spots.stalls for c in s] or spots.square, MARKET_DAY),
        (6, 7, f"cooking breakfast for {to}", cook),
        (7, 7.5, "drawing water at the fountain", spots.water),
        (7.5, 8.5, rng.choice(["sweeping the doorstep", "scrubbing the floor"]), step if rng.random() < 0.6 else inside),
        (8.5, 10, f"browsing {stall_name}", stall),
        (10, 11, "keeping house", inside),
        (11, 13, f"cooking dinner for {to}", cook),
        (13, 14, rng.choice(["beating the rugs", "hanging out the washing"]), step),
        (14, 15.5, "gossiping by the fountain", spots.water),
        (15.5, 16, "mending by the fire", cook),
        (16, 19, f"preparing supper for {to}", cook),
        (19, 21, f"at supper with {to}", inside),
    ]


def child(spots: Spots, rng: random.Random, inside: list, house) -> list:
    """Lessons of a weekday morning if there's a school, chores at home if not; tag after."""
    out = []
    if spots.school:
        out.append((8, 12, "at their lessons", spots.desks, WEEKDAYS))
    else:
        out.append((8, 10, "doing chores at home", inside, WEEKDAYS))
    out += [(8, 19, "playing tag", spots.streets), (19, 21, "at supper at home", inside)]
    return out


def labourer(spots: Spots, rng: random.Random, work: list, shift: tuple) -> list:
    start, end = shift
    stall_name, stall = spots.stall(rng)
    return [
        (start, 9, "hauling loads", work),
        (9, 10, f"unloading a cart at {stall_name}", stall),
        (10, 12, "hauling loads", work),
        (12, 13, "eating bread by the fountain", spots.water),
        (13, end, "hauling loads", work),
        (end, 21.5, "drinking at {inn}", spots.inn or spots.square),
    ]


def washerwoman(spots: Spots, rng: random.Random, work: list, home: list, shift: tuple) -> list:
    start, end = shift
    return [
        (start, 11, "washing clothes", work),
        (11, 12, "wringing out the washing", work),
        (12, 13, "hanging out the washing", spots.streets),
        (13, end, "washing clothes", work),
        (end, end + 2, "delivering clean linen", spots.streets),
        (end + 2, 21, "at {inn}", spots.inn or spots.square),
    ]


def priest(spots: Spots, altar: list, steps: list) -> list:
    return [
        (6, 7, "saying the morning prayers", altar),
        (7, 12, "tending the altar", altar),
        (12, 13, "giving alms to the poor", steps or altar),
        (13, 16, "visiting the sick", spots.any(spots.healing, spots.streets)),
        (16, 18, "tending the altar", altar),
        (18, 20, "leading the evening prayers", altar),
    ]


def performer(spots: Spots, rng: random.Random, boards: list, kind: str) -> list:
    busk = "singing for coins in the square" if kind == "bard" else "juggling for coins in the square"
    return [
        (9, 12, "rehearsing" if kind == "mummer" else "rehearsing a ballad", boards),
        (12, 14, busk, spots.square),
        (14, 16, "at {inn}", spots.inn or spots.square),
        (16, 23, "singing on the stage" if kind == "bard" else "playing on the stage", boards),
    ]


def pit_fighter(spots: Spots, ring: list) -> list:
    return [
        (8, 11, "training in the yard" if spots.yard else "training by the pit", spots.yard or ring),
        (11, 13, "eating like a horse at {inn}", spots.inn or spots.square),
        (13, 14, "taking bets by the pit", ring),
        (14, 21, "fighting in the pit", ring),
        (21, 23, "nursing bruises at {inn}", spots.inn or spots.square),
    ]


def guildmaster(spots: Spots, hall: list) -> list:
    return [
        (9, 12, "keeping the guild's books", hall),
        (12, 14, "inspecting the market", spots.any(spots.market, [c for _, s in spots.stalls for c in s])),
        (14, 17, "keeping the guild's books", hall),
        (17, 20, "dining at {inn}", spots.inn or spots.square),
    ]


def alchemist(spots: Spots, lab: list, bench: list) -> list:
    return [
        (7, 9, "gathering herbs in the garden" if spots.garden else "buying herbs at the stalls",
         spots.garden or spots.stall(random.Random(len(lab)))[1]),
        (9, 13, "brewing something that smokes", bench),
        (13, 14, "airing out the shop", lab),
        (14, 19, "grinding powders", bench),
    ]


def hangman(spots: Spots, yard: list) -> list:
    return [
        (9, 10, "oiling the gallows rope", yard),
        (10, 12, "seeing to the gallows", yard),
        (12, 13, "eating alone at {inn}", spots.inn or spots.square),
        (13, 16, "watching the stocks", yard),
        (16, 18, "at {inn}", spots.inn or spots.square),
    ]


def household(kind: str, spots: Spots, rng: random.Random, house, inside: list, married: bool) -> list:
    """The day of someone in one of the city's other houses."""
    lv = spots.level
    cook = kitchen(lv, inside)
    step = doorstep(lv, house) or inside
    stall_name, stall = spots.stall(rng)
    wake = rng.choice((6, 6.5, 7))
    days = {
        "clerk": [(wake + 1, 12, "copying ledgers", spots.any(spots.counting, spots.guild, inside)),
                  (12, 13, f"buying a pie at {stall_name}", stall),
                  (13, 17, "copying ledgers", spots.any(spots.counting, spots.guild, inside))],
        "porter": [(wake, 12, "carrying parcels", spots.streets),
                   (12, 13, "eating bread by the fountain", spots.water),
                   (13, 17, "carrying parcels", spots.streets)],
        "maid": [(wake, 11, "cleaning at {inn}" if spots.inn else "scrubbing floors", spots.any(spots.inn, inside)),
                 (11, 12, "scrubbing the bathhouse tiles" if spots.bath else "scrubbing the doorstep",
                  spots.bath or step),
                 (12, 13, "at dinner at home", cook),
                 (13, 17, "cleaning at {inn}" if spots.inn else "scrubbing floors", spots.any(spots.inn, inside))],
        "seamstress": [(wake + 1, 12, "sewing by the window", inside),
                       (12, 13, f"buying thread at {stall_name}", stall),
                       (13, 18, "sewing by the window", inside)],
        "messenger": [(wake, 12, "running messages", spots.streets),
                      (12, 13, "catching their breath by the fountain", spots.water),
                      (13, 18, "running messages", spots.streets)],
        "elder": [(wake + 1, 10, "sitting on the doorstep", step),
                  (10, 12, "feeding the pigeons in the square", spots.square),
                  (12, 14, "napping by the fire", cook),
                  (14, 16, "strolling in the city garden" if spots.garden else "gossiping by the fountain",
                   spots.garden or spots.water),
                  (16, 18, "telling old stories at {inn}", spots.inn or spots.square)],
        "widow": [(wake + 1, 9, "visiting a grave" if spots.graves else "praying at the temple",
                   spots.graves or spots.pews),
                  (9, 11, f"browsing {stall_name}", stall),
                  (11, 15, "keeping house", inside),
                  (15, 17, "gossiping by the fountain", spots.water)],
    }[kind]
    out = [(wake, wake + 1, "breakfasting", cook)] if kind not in ("porter", "maid", "messenger") else []
    out += days
    end = days[-1][1]
    if kind in ("elder", "widow"):
        out.append((end, 21, "at supper at home", cook))
    else:
        out += evening(spots, rng, inside, married, end)
    return out


def street_folk(kind: str, spots: Spots, rng: random.Random, inside: list) -> list:
    """The city's own: sweeping, lamps, water, chimneys, the news."""
    cook = kitchen(spots.level, inside)
    inn = spots.inn or spots.square
    return {
        "street sweeper": [(5, 8, "sweeping the square", spots.square), (8, 12, "sweeping the streets", spots.streets),
                           (12, 13, "at dinner at home", cook), (13, 17, "sweeping the streets", spots.streets),
                           (17, 18, "sweeping the square", spots.square), (18, 21, "at {inn}", inn)],
        "lamplighter": [(4, 6, "putting out the street lamps", spots.streets), (12, 14, "trimming wicks at home", cook),
                        (14, 17, "at {inn}", inn), (17, 20, "lighting the street lamps", spots.streets),
                        (20, 22, "at {inn}", inn)],
        "water carrier": [(5, 12, "carrying water from the fountain", spots.water + spots.streets[:40]),
                          (12, 13, "at dinner at home", cook),
                          (13, 18, "carrying water from the fountain", spots.water + spots.streets[:40]),
                          (18, 21, "at {inn}", inn)],
        "chimney sweep": [(6, 12, "sweeping chimneys", spots.streets), (12, 13, "coughing up soot by the fountain",
                                                                         spots.water),
                          (13, 17, "sweeping chimneys", spots.streets), (17, 21, "at {inn}", inn)],
        "town crier": [(7, 18, "crying the news", spots.square), (18, 21, "at {inn}", inn)],
    }[kind]


# ----------------------------------------------------------------- the people of the halls

def bathkeeper(spots: Spots, floor: list) -> list:
    return [(6, 8, "heating the water", floor), (8, 12, "keeping the bathhouse", floor),
            (12, 13, "scrubbing the tiles", floor), (13, 20, "keeping the bathhouse", floor)]


def moneylender(spots: Spots, desk: list) -> list:
    return [(8, 12, "counting coins", desk), (12, 13, "dining at {inn}", spots.inn or spots.square),
            (13, 17, "lending at interest", desk), (17, 18, "locking the strongboxes", desk)]


def gravedigger(spots: Spots, ground: list) -> list:
    return [(6, 11, "digging a grave", ground), (11, 13, "tending the graves", ground),
            (13, 14, "eating by the graveyard gate", ground), (14, 18, "tending the graves", ground),
            (18, 21, "drinking alone at {inn}", spots.inn or spots.square)]


def healer(spots: Spots, floor: list, beds: list) -> list:
    return [(6, 8, "grinding herbs for poultices", floor), (8, 12, "tending the sick", beds or floor),
            (12, 13, "buying herbs at the stalls", spots.stall(random.Random(len(floor)))[1]),
            (13, 20, "tending the sick", beds or floor)]


def matron(spots: Spots, floor: list) -> list:
    return [(6, 8, "waking the foundlings", floor), (8, 12, "scrubbing the foundling house", floor),
            (12, 13, "feeding the foundlings", floor), (13, 15, "begging alms in the square", spots.square),
            (15, 21, "minding the foundlings", floor)]


def sellsword(spots: Spots, rng: random.Random, hall: list) -> list:
    """An adventurer between jobs: the notice board, practice, a drink, a tale."""
    return [(7, 9, "reading the notice board", spots.notice or hall),
            (9, 12, "sparring in the training yard" if spots.yard else "sharpening a blade",
             spots.yard or hall),
            (12, 14, "eating at the Adventurers' Hall", hall),
            (14, 17, rng.choice(["haggling for gear at the stalls", "watching the fights", "at the bathhouse"]),
             rng.choice([spots.stall(rng)[1], spots.pit or spots.square, spots.bath or spots.square])),
            (17, 23, "swapping tales at the Adventurers' Hall", hall)]


def brewer(spots: Spots, floor: list) -> list:
    return [(5, 9, "stirring the mash", floor), (9, 12, "minding the vats", floor),
            (12, 13, "rolling a barrel to {inn}", spots.inn or spots.streets),
            (13, 17, "minding the vats", floor), (17, 21, "tasting the wares at {inn}", spots.inn or spots.square)]


def tanner(spots: Spots, floor: list) -> list:
    return [(6, 12, "scraping hides", floor), (12, 13, "washing the stink off at the fountain", spots.water),
            (13, 17, "working hides in the vats", floor), (17, 21, "at {inn}, sitting alone", spots.inn or spots.square)]


def mage(spots: Spots, circle: list, books: list, room: list) -> list:
    return [(0, 3, "watching the stars from the tower", room), (10, 13, "teaching the apprentices", circle or room),
            (13, 14, "dining in the tower", room), (14, 18, "poring over old books", books or room),
            (18, 21, "working a spell at the circle", circle or room), (21, 24, "watching the stars from the tower", room)]


def apprentice(spots: Spots, rng: random.Random, circle: list, books: list, room: list) -> list:
    return [(7, 10, "sweeping the tower floor", room), (10, 13, "at their lessons", circle or room),
            (13, 14, "fetching the mage's dinner", spots.stall(rng)[1]),
            (14, 18, "copying spells", books or room), (18, 21, "holding the candles for the mage", circle or room),
            (21, 22, "at {inn}", spots.inn or spots.square)]


def schoolmaster(spots: Spots, desk: list, room: list) -> list:
    return [(8, 12, "teaching letters", desk, WEEKDAYS), (12, 13, "at dinner at {inn}", spots.inn or spots.square),
            (13, 16, "marking slates", desk, WEEKDAYS), (16, 18, "reading in the city garden" if spots.garden
                                                          else "reading at {inn}", spots.garden or spots.inn or room)]


def master_at_arms(spots: Spots, yard: list) -> list:
    return [(6, 12, "drilling the recruits", yard), (12, 13, "eating with the guards", spots.inn or spots.square),
            (13, 17, "drilling the recruits", yard), (17, 21, "at {inn}", spots.inn or spots.square)]


def recruit(spots: Spots, rng: random.Random, yard: list) -> list:
    return [(6, 7, "running laps", spots.streets), (7, 12, "drilling with the spear", yard),
            (12, 13, "wolfing down dinner", spots.inn or spots.square),
            (13, 15, "shooting at the butts", yard), (15, 17, "polishing armour", yard),
            (17, 21, "drinking at {inn}", spots.inn or spots.square)]
