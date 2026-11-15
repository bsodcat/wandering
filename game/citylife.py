"""The people of a stone city, and its thieves.

Besides its tradespeople (game/people.py), each part of a city is peopled with:

- craftsfolk (weavers, tailors, potters, chandlers, coopers, cobblers, scribes, carpenters),
  each living and working in one of the houses, at hours of their own
- townsfolk with no trade, who wander the city at times of their own: mostly up and down its
  streets, all over the town, and now and then the stalls in the square, the temple, the
  gallows, the playhouse and the pit, the market row, and the inn of an evening (people.haunt)
- beggars, by the temple doors or in the square
- in a lower quarter, labourers, washerwomen and a ratcatcher living in the hovels (where the
  beggars and thieves sleep, too)
- merchants at the square's stalls and along the market row (they'll trade with you)
- homemakers, married to some of the craftsfolk, who keep house and cook their meals (the
  craftsfolk come home for supper), and their children, who play tag in little bands about the
  streets, the square and the garden, moving on from one spot to another (play)
- on a Sunday morning (09:00-11:00), the service: the priest at the altar of the temple (or a
  chapel), and most of the part's people in the pews (people.sunday)
- whoever keeps its landmarks: a priest, a bard and mummers, pit fighters, a hangman, a
  guildmaster, an alchemist
- thieves, who pass for townsfolk, and guards: two at each gate, one at each of the nearest
  street crossings, and GUARDS_PER_THIEF more for every thief. A third of them keep the night
  watch, and they sleep in the guardhouse
- in the keep: a king (or a prince) and a queen (or a concubine), who keep the hours of a court
  (holding court in the throne room, dining and feasting in the great hall, the library, the
  gardens); the royal guard; a cook, a librarian and servants. Down in the dungeon, a gaoler
  and some prisoners (game/landmarks.py)

Thieves (crime): while they're about, a thief now and then picks the pocket of someone near
them out in the street, when there's no guard close by. Often the victim notices and cries "Thief!": the nearest guards on duty
give chase, and the thief runs. A guard who catches up hauls the thief off to the gaol; one who
can't keep up loses them after CHASE_MINUTES. Each new day, the city's thieves are back up to
their number (there's always someone new). If you see a thief at it, you know them for what
they are.
"""
from __future__ import annotations

import random

import numpy as np

from . import tiles as T
from .people import CRAFTS, FIRST, MOST_STEPS, SPOUSE, Actor, find_path, marry, on_duty, person_name, settle_green

RESIDENTS = 54                # houses with craftsfolk living and working in them, at most
TOWNSFOLK = (25, 37)          # townsfolk with no trade
THIEVES = (1, 4)
GUARDS_PER_THIEF = 2
WANDER = 4                    # the streets count this many times over among an idler's haunts
LABOURERS = 24                # labourers and washerwomen living in a lower quarter's hovels, at most
CHILDREN = 0.3                # how often a family has children
MOST_CHILDREN = 24            # children in a part of a city, at most
PLAY_MINUTES = 0.5            # a child running, a tile
TAG_SIGHT = 12                # how far "it" looks for someone to chase
SCARED = 6                    # how close "it" comes before the others run
ROAM = 20                     # how far from where they're playing the children wander
ANCHOR_HOURS = 1.0            # how long they play in one place before moving on
COUNT_TO = 1.5                # minutes the one tagged waits before giving chase
NIGHT_WATCH = 3               # every third guard keeps the night watch
THEFT_PER_HOUR = 0.6          # chance a thief at it picks a pocket in an hour, if there's one to pick
WARY = 8                      # ... and no guard this close
NOTICED = 0.6                 # chance the victim notices and cries out
ALARM_RANGE = 45              # tiles a cry of "Thief!" carries to the guards
CHASERS = 2                   # guards who answer it
CHASE_MINUTES = 40            # how long a thief runs before they've got away
RUN_MINUTES = 0.45            # a guard running, a tile
FLEE_MINUTES = 0.55           # a thief running, a tile
HEARD = 40                    # tiles from you a cry is heard
RESOLVE_MINUTES = 30          # longer than this at once (resting, away), and a chase just ends
CAUGHT = 0.6                  # ... with the thief caught this often
KINGLY = ["Aldric", "Edmund", "Leofric", "Osric", "Cedric", "Godwin", "Harald", "Alaric"]
QUEENLY = ["Aelfwyn", "Isolde", "Rosamund", "Mathilde", "Elinor", "Gwendolyn", "Ysolde", "Beatrix"]


def building(level, kind: str, name: str | None = None):
    return next((b for b in level.buildings if b.kind == kind and (name is None or b.name == name)), None)


def floor(level, kind: str, name: str | None = None) -> list:
    b = building(level, kind, name)
    return b.floor(level.tiles) if b else []


def near(level, tiles: list, tile: int, reach: int = 1) -> list:
    """Of `tiles`, those within `reach` of one of a kind of tile."""
    t = level.tiles
    return [(x, y) for x, y in tiles if any(level.in_bounds(x + dx, y + dy) and t[x + dx, y + dy] == tile
                                            for dx in range(-reach, reach + 1) for dy in range(-reach, reach + 1))]


def streets(level) -> list:
    """Street tiles to wander (and run) along: a fair sample of them."""
    if getattr(level, "_streets", None) is None:
        cells = [tuple(int(v) for v in c) for c in np.argwhere(level.tiles == T.STREET)] or             [tuple(int(v) for v in c) for c in np.argwhere(T.WALK[level.tiles] & ~T.WATERY[level.tiles])]
        level._streets = random.Random(len(cells)).sample(cells, min(500, len(cells)))
    return level._streets


# ----------------------------------------------------------------- peopling a part of a city

def populate(level, site, rng: random.Random, used: set, evening: list, evening_kind: str) -> None:
    t = level.tiles
    houses = [b for b in level.buildings if b.kind == "house" and not b.owner and b.name != "a hovel"]
    hovels = [b for b in level.buildings if b.kind == "house" and not b.owner and b.name == "a hovel"]
    rng.shuffle(houses)
    rng.shuffle(hovels)
    square = settle_green(level)
    places = {}
    for p in level.places:
        places.setdefault(p.kind, []).append(p)
    inn = evening if evening_kind == "inn" else square
    walk = streets(level)

    def add(kind: str, name: str, home: list, work: list, **kw) -> Actor | None:
        if not home or not work:
            return None
        x, y = rng.choice(work)
        a = Actor(kind, name, x, y, home=home, work=work, evening=kw.pop("evening", inn),
                  evening_kind=kw.pop("evening_kind", evening_kind), **kw)
        level.actors.append(a)
        return a

    def hovel() -> list:
        """A bedroll in one of the lower quarter's hovels (or a house, if there are none)."""
        if not hovels:
            return lodging()
        b = hovels.pop()
        return [c for c in b.floor(t) if t[c] == T.BEDROLL] or b.floor(t)

    def lodging() -> list:
        """A bed in one of the houses left over (or shared, once they're all taken)."""
        house = houses.pop() if houses else rng.choice([b for b in level.buildings if b.kind == "house"] or [None])
        if house is None:
            return square
        return [c for c in house.floor(t) if t[c] == T.BED] or house.floor(t)

    # where the idle go: mostly the streets, all over town; the square only for its stalls
    from .landmarks import square_stalls
    stalls = [c for s in square_stalls(level) for c in s] or square
    haunts = [("browsing the market", stalls, "day"), ("at {inn}", inn, "evening")]
    haunts += [("wandering the streets", walk, "any")] * WANDER
    garden = next((p.tiles for p in level.places if p.kind == "garden"), None)
    if garden:
        haunts.append(("strolling in the city garden", garden, "day"))
    temple = building(level, "temple")
    if temple:
        pews = [c for c in temple.floor(t) if t[c] == T.BENCH]
        haunts.append((f"praying at {temple.name}", pews or temple.floor(t), "day"))
    if temple is None:
        temple = building(level, "chapel")
    stage = floor(level, "playhouse")
    if stage:
        haunts.append(("watching the players", [c for c in stage if t[c] != T.STAGE], "evening"))
    for kind, doing, when in (("pitside", "watching the fights", "any"), ("gallows", "gawking at the gallows", "day"),
                              ("market", "haggling at the market row", "day"), ("crossing", "idling at the crossing", "day")):
        for p in places.get(kind, [])[:2]:
            haunts.append((doing, p.tiles, when))

    # craftsfolk in their houses, some married (a homemaker at home), some with children
    kids = []
    for house in houses[:RESIDENTS]:
        craft = rng.choice(CRAFTS)
        name = person_name(rng, used)
        house.name, house.owner = f"the {name.split()[1]} house", craft
        inside = house.floor(t)
        beds = [c for c in inside if t[c] == T.BED] or inside
        start = rng.randint(6, 9)
        worker = add(craft, name, beds, inside, shift=(start, start + rng.randint(8, 10)))
        if worker is None or rng.random() >= SPOUSE:
            continue
        marry(level, rng, used, worker, house)
        for _ in range(rng.randint(1, 2) if rng.random() < CHILDREN * 2 else 0):
            if len(kids) < MOST_CHILDREN:
                kid = f"{rng.choice(FIRST)} {name.split()[-1]}"
                used.add(kid)
                kids.append(add("child", kid, beds, walk, evening=inside, evening_kind="home"))
    del houses[:RESIDENTS]
    playmates([k for k in kids if k is not None], rng)
    # the lower quarter: labourers, washerwomen, a ratcatcher
    if hovels:
        wash = near(level, walk + square, T.FOUNTAIN, 3) + near(level, walk, T.WELL, 3)
        water = [tuple(int(v) for v in c) for c in np.argwhere(T.WATERY[t])]
        shore = [c for c in near(level, walk, T.BRIDGE, 2)] or wash or square
        for _ in range(min(len(hovels) // 2, LABOURERS)):
            job = rng.choice(("labourer", "labourer", "washerwoman"))
            add(job, person_name(rng, used), hovel(), walk if job == "labourer" else (shore if water else wash or square),
                shift=(rng.randint(5, 7), rng.randint(15, 18)))
        add("ratcatcher", person_name(rng, used), hovel(), walk)
    # townsfolk with no trade, and beggars
    for _ in range(rng.randint(*TOWNSFOLK)):
        add("townsperson", person_name(rng, used), lodging(), square, haunts=haunts,
            shift=(rng.randint(6, 10), rng.randint(20, 24)), seed=rng.randrange(1 << 30))
    steps = []
    if temple:
        dx, dy = temple.door
        steps = [(x, y) for x in range(dx - 3, dx + 4) for y in range(dy - 2, dy + 3)
                 if level.walkable(x, y) and not T.ROOF[t[x, y]]]
    begging = [("begging in the square", square, "any")] + ([("begging at the temple doors", steps, "any")] if steps else [])
    sleep_rough = (places.get("crossing") or [None])[0]
    for _ in range(1 + bool(temple)):
        add("beggar", person_name(rng, used), hovel() if hovels else sleep_rough.tiles if sleep_rough else square, square,
            haunts=begging, shift=(7, 21), seed=rng.randrange(1 << 30))
    # thieves, and the guards to match
    level.thieves = rng.randint(*THIEVES)
    for _ in range(level.thieves):
        thief(level, rng, used, hovel(), haunts)
    bunks = [c for c in floor(level, "guardhouse") if t[c] == T.BED]
    room = floor(level, "guardhouse") or square
    shifts = [0, 0]           # each bunk shared by a day guard and a night guard, who sleep at different times
    posts = [g.tiles for g in places.get("gate", []) for _ in range(2)][:6]
    posts += [c.tiles for c in places.get("crossing", [])]
    roving = [c.tiles for c in places.get("crossing", [])] or [square]
    posts += [roving[i % len(roving)] if i % 2 else square for i in range(GUARDS_PER_THIEF * level.thieves)]
    for i, post in enumerate(posts):
        night = i % NIGHT_WATCH == NIGHT_WATCH - 1
        bed = [bunks[shifts[night] % len(bunks)]] if bunks else room
        shifts[night] += 1
        add("guard", person_name(rng, used), bed, post, shift=(21, 30) if night else None)
    # merchants at the stalls
    from .landmarks import square_stalls
    for stall in square_stalls(level)[:3]:
        add("merchant", person_name(rng, used), lodging(), stall)
    for p in places.get("market", []):
        for i in range(min(4, max(1, len(p.tiles) // 6))):
            add("merchant", person_name(rng, used), lodging(), p.tiles[i::4])
    # whoever keeps the landmarks
    if temple:
        inside = temple.floor(t)
        add("priest", person_name(rng, used), inside, near(level, inside, T.ALTAR, 2) or inside)
    if stage:
        boards = [c for c in stage if t[c] == T.STAGE]
        add("bard", person_name(rng, used), lodging(), boards)
        for _ in range(2):
            add("mummer", person_name(rng, used), lodging(), boards)
    for p in places.get("pit", []):
        for _ in range(2):
            add("pit fighter", person_name(rng, used), lodging(), p.tiles)
    for p in places.get("gallows", []):
        add("hangman", person_name(rng, used), lodging(), p.tiles)
    hall = building(level, "guildhall")
    if hall:
        add("guildmaster", person_name(rng, used), lodging(), hall.floor(t))
    lab = floor(level, "alchemist")
    if lab:
        add("alchemist", person_name(rng, used), lab, near(level, lab, T.COUNTER) or lab)
    court(level, site, rng, used, add)


def playmates(kids: list, rng: random.Random) -> None:
    """The children in twos, threes and fours, each little band with one of them "it"."""
    rng.shuffle(kids)
    while kids:
        n = min(len(kids), rng.randint(2, 4))
        if len(kids) - n == 1:
            n += 1                         # nobody plays tag on their own
        band, kids = kids[:n], kids[n:]
        for k in band:
            k.friends, k.it = band, False
        band[0].it = True


def thief(level, rng: random.Random, used: set, home: list, haunts: list, at=None) -> Actor:
    """A thief: passes for a townsperson, about the busy places from late morning till after
    midnight."""
    work = haunts[0][1]
    x, y = at or rng.choice(work)
    a = Actor("thief", person_name(rng, used), x, y, home=home, work=work, evening=work, haunts=haunts,
              shift=(10, 26), seed=rng.randrange(1 << 30))
    level.actors.append(a)
    return a


def court(level, site, rng: random.Random, used: set, add) -> None:
    """The keep's people: the ruler and their consort, the royal guard, the household."""
    t = level.tiles
    throne = building(level, "throne room")
    if throne is None:
        return
    room = throne.floor(t)
    seat = near(level, room, T.THRONE) or room
    hall = floor(level, "great hall")
    seats = [c for c in hall if t[c] == T.BENCH] or hall
    chambers = floor(level, "royal chambers")
    beds = [c for c in chambers if t[c] == T.BED] or chambers
    books = floor(level, "library")
    yard = next((p.tiles for p in level.places if p.kind == "keep"), room)
    gate = next((p.tiles for p in level.places if p.kind == "keep gate"), yard)
    ruler = "king" if rng.random() < 0.6 else "prince"
    rname = f"{rng.choice(KINGLY)} of {site.name}"
    add(ruler, rname, beds[:1], seat, routine=[
        (7, 9, "breaking fast in the great hall", seats), (9, 12, "holding court", seat),
        (12, 14, "dining in the great hall", seats), (14, 16, "reading in the library", books),
        (16, 18, "walking in the gardens", yard), (18, 21, "feasting in the great hall", seats)])
    consort = "queen" if ruler == "king" and rng.random() < 0.65 else "concubine"
    cname = f"{rng.choice(QUEENLY)} of {site.name}" if consort == "queen" else person_name(rng, used)
    add(consort, cname, beds[1:2] or beds, room, routine=[
        (8, 10, "in the royal chambers", chambers), (10, 12, "at court", near(level, room, T.THRONE, 3) or room),
        (12, 14, "dining in the great hall", seats), (14, 17, "walking in the gardens", yard),
        (17, 18, "reading in the library", books), (18, 21, "feasting in the great hall", seats)])
    barracks = building(level, "barracks", "the keep's barracks")
    bunks = [c for c in barracks.floor(t) if t[c] == T.BED] if barracks else []
    bunks = bunks or yard
    for i, post in enumerate([near(level, room, T.THRONE, 4) or room] * 2 + [gate] * 4):
        add("guard", person_name(rng, used), bunks, post, shift=(21, 30) if i >= 4 else None)
    add("cook", person_name(rng, used), seats, near(level, hall, T.HEARTH, 2) or hall)
    if books:
        add("librarian", person_name(rng, used), books, books)
    for _ in range(2):
        add("servant", person_name(rng, used), seats, hall, routine=[
            (6, 14, "waiting on the court", hall), (14, 17, "tidying the royal chambers", chambers),
            (17, 21, "serving at the feast", hall)])


# ----------------------------------------------------------------- children at play

def play(level, engine, rng: random.Random, elapsed: float) -> None:
    """`elapsed` minutes of tag: whoever's "it" runs after the nearest of the others, who run
    off when it comes close; a tag, and the tagged one's it. Each band plays about one spot a
    while (a street, the square, the garden), then moves on somewhere else in the city."""
    kids = [a for a in level.actors if a.kind == "child" and a.doing == "playing tag"]
    if not kids:
        return
    spots = streets(level)
    taken = {(a.x, a.y) for a in level.actors}
    if engine.level is level:
        taken.add((engine.lx, engine.ly))
    seen_bands = set()
    for k in kids:
        band = [b for b in (k.friends or [k]) if b in kids]
        if id(k.friends) in seen_bands or not band:
            continue
        seen_bands.add(id(k.friends))
        lead = band[0]
        if lead.goal is None or rng.random() < elapsed / (ANCHOR_HOURS * 60):
            lead.goal = rng.choice(spots)
        anchor = lead.goal
        if elapsed > RESOLVE_MINUTES:                    # away a while: they're somewhere else by now
            for b in band:
                near_ = [c for c in spots if abs(c[0] - anchor[0]) + abs(c[1] - anchor[1]) < ROAM] or [anchor]
                c = rng.choice(near_)
                if c not in taken:
                    taken.discard((b.x, b.y))
                    b.x, b.y = c
                    taken.add(c)
            continue
        it = next((b for b in band if b.it), band[0])
        for b in k.friends:                              # one "it" to a band, whoever's off elsewhere
            b.it = b is it
        for b in band:
            b.budget = min(b.budget + elapsed, MOST_STEPS * PLAY_MINUTES)
        for _ in range(int(max(b.budget for b in band) / PLAY_MINUTES)):
            others = [b for b in band if b is not it]
            for b in band:
                if b.budget < PLAY_MINUTES:
                    continue
                b.budget -= PLAY_MINUTES
                if b is it:
                    prey = [o for o in others if gap(o, b) <= TAG_SIGHT]
                    goal = min(prey, key=lambda o: gap(o, b)) if prey else None
                    hop(level, b, (goal.x, goal.y) if goal else anchor, taken, rng, toward=True)
                    if goal is not None and gap(goal, b) <= 1:
                        it.it, goal.it = False, True
                        goal.budget = -COUNT_TO               # no tag-backs: they count to three first
                        if seen(engine, level, (b.x, b.y)) and rng.random() < 0.3:
                            engine.say(f'"Tag! You\'re it!" shrieks {b.name.split()[0]}, and {goal.name.split()[0]} '
                                       f'chases after the others.')
                        it = goal
                        break
                elif gap(b, it) <= SCARED:
                    hop(level, b, (it.x, it.y), taken, rng, toward=False, anchor=anchor)
                elif rng.random() < 0.4:
                    hop(level, b, anchor, taken, rng, toward=True)


def hop(level, a: Actor, target: tuple, taken: set, rng: random.Random, toward: bool, anchor=None) -> None:
    """A step toward (or away from) somewhere, out in the open, never far from where they're
    playing."""
    t = level.tiles
    here = max(abs(a.x - target[0]), abs(a.y - target[1]))
    best, score = None, None
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            c = (a.x + dx, a.y + dy)
            if (dx or dy) and c not in taken and level.walkable(*c) and not T.WATERY[t[c]] and not T.ROOF[t[c]]:
                d = max(abs(c[0] - target[0]), abs(c[1] - target[1]))
                if anchor is not None and max(abs(c[0] - anchor[0]), abs(c[1] - anchor[1])) > ROAM:
                    continue
                s = (d if toward else -d) + rng.random() * 0.5
                if score is None or s < score:
                    best, score = c, s
    if best is None:
        return
    if toward and max(abs(best[0] - target[0]), abs(best[1] - target[1])) > here:
        return
    taken.discard((a.x, a.y))
    a.x, a.y = best
    taken.add(best)


# ----------------------------------------------------------------- crime

def seen(engine, level, *cells) -> bool:
    vis = getattr(engine, "local_visible", None)
    if engine.level is not level or vis is None or vis.shape != level.tiles.shape:
        return False
    return any(bool(vis[c]) for c in cells)


def heard(engine, level, c) -> bool:
    return engine.level is level and max(abs(c[0] - engine.lx), abs(c[1] - engine.ly) * 2) <= HEARD


def gap(a, b) -> int:
    return max(abs(a.x - b.x), abs(a.y - b.y))


def crime(level, engine, rng: random.Random, elapsed: float) -> None:
    """`elapsed` minutes of the city's thieves at work, and the guards after them."""
    if not level.thieves:
        return
    restock(level, engine, rng)
    people_here = [a for a in level.actors if not a.animal]
    if elapsed > RESOLVE_MINUTES:
        for th in [a for a in people_here if a.fleeing is not None]:
            settle(level, engine, th, rng.random() < CAUGHT)
        return
    t = level.tiles
    for th in [a for a in people_here if a.kind == "thief" and a.fleeing is None and on_duty(a, engine.minutes)]:
        if rng.random() >= 1 - (1 - THEFT_PER_HOUR) ** (elapsed / 60):
            continue
        if any(g.kind == "guard" and g.doing != "asleep" and gap(g, th) <= WARY for g in people_here):
            continue                            # not with a guard looking on
        marks = [a for a in people_here if a is not th and a.kind not in ("guard", "archer", "thief")
                 and a.doing != "asleep" and gap(a, th) <= 2 and not T.ROOF[t[a.x, a.y]]]
        if not marks:
            continue
        victim = rng.choice(marks)
        th.loot += rng.randint(1, 8)
        if rng.random() < NOTICED:
            alarm(level, engine, th, victim, rng)
        elif seen(engine, level, (th.x, th.y)):
            th.exposed = True
            engine.say(f"You see {th.name} lift a purse from {victim.name}'s belt, unnoticed.")
    chase(level, engine, rng, elapsed)


def alarm(level, engine, th: Actor, victim: Actor, rng: random.Random) -> None:
    """The victim cries out: the nearest guards on duty give chase, and the thief runs."""
    th.exposed = True
    th.fleeing = engine.minutes + CHASE_MINUTES
    th.path, th.goal = [], None
    guards = sorted((a for a in level.actors if a.kind == "guard" and a.chase is None and a.doing != "asleep"
                     and on_duty(a, engine.minutes) and gap(a, th) <= ALARM_RANGE), key=lambda a: gap(a, th))
    for g in guards[:CHASERS]:
        g.chase, g.path, g.goal = th, [], None
    first = victim.name.split()[0]
    if seen(engine, level, (victim.x, victim.y), (th.x, th.y)):
        after = f" {guards[0].name}, the guard, gives chase." if guards else " No guard comes."
        engine.say(f'"Thief!" cries {first}, as {th.name} bolts.{after}')
    elif heard(engine, level, (victim.x, victim.y)):
        engine.say('Somewhere nearby, someone cries "Thief!"')


def chase(level, engine, rng: random.Random, elapsed: float) -> None:
    """The guards run the thieves down, and the thieves run for it."""
    taken = {(a.x, a.y) for a in level.actors}
    if engine.level is level:
        taken.add((engine.lx, engine.ly))
    for th in [a for a in level.actors if a.fleeing is not None]:
        if engine.minutes >= th.fleeing:
            settle(level, engine, th, False)
            continue
        run(level, th, flee_goal(level, th, rng), taken, elapsed, FLEE_MINUTES)
    for g in [a for a in level.actors if a.chase is not None]:
        th = g.chase
        if th not in level.actors or th.fleeing is None:
            g.chase, g.path, g.goal = None, [], None
            continue
        if gap(g, th) <= 1:
            settle(level, engine, th, True, g)
            continue
        if g.path and max(abs(g.path[-1][0] - th.x), abs(g.path[-1][1] - th.y)) > 2:
            g.path = []
        run(level, g, (th.x, th.y), taken, elapsed, RUN_MINUTES)
        if gap(g, th) <= 1:
            settle(level, engine, th, True, g)


def flee_goal(level, th: Actor, rng: random.Random) -> tuple:
    """Somewhere well away to run to: a far street, a new one once they're there."""
    if th.goal is None or (th.x, th.y) == th.goal:
        far = [c for c in streets(level) if max(abs(c[0] - th.x), abs(c[1] - th.y) * 2) > 30]
        th.goal, th.path = (rng.choice(far) if far else rng.choice(streets(level))), []
    return th.goal


def run(level, a: Actor, goal: tuple, taken: set, elapsed: float, pace: float) -> None:
    a.budget = min(a.budget + elapsed, MOST_STEPS * pace)
    while a.budget >= pace:
        a.budget -= pace
        if not a.path:
            a.path = find_path(level, (a.x, a.y), goal)
            if not a.path:
                return
        nxt = a.path[0]
        if nxt in taken and nxt != goal:          # someone in the way: round them
            here = max(abs(a.x - goal[0]), abs(a.y - goal[1]))
            side = [(a.x + dx, a.y + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if dx or dy]
            side = [c for c in side if c not in taken and level.walkable(*c) and not T.WATERY[level.tiles[c]]
                    and max(abs(c[0] - goal[0]), abs(c[1] - goal[1])) <= here]
            if not side:
                a.stuck += 1
                if a.stuck > 2:
                    a.path, a.stuck = [], 0
                continue
            nxt = min(side, key=lambda c: (max(abs(c[0] - goal[0]), abs(c[1] - goal[1])),
                                           abs(c[0] - goal[0]) + abs(c[1] - goal[1])))
            a.path = []
            taken.discard((a.x, a.y))
            a.x, a.y = nxt
            taken.add(nxt)
            continue
        if nxt == goal and nxt in taken:
            return                              # caught up (game: settle)
        a.path.pop(0)
        taken.discard((a.x, a.y))
        a.x, a.y = nxt
        taken.add(nxt)
        a.stuck = 0


def settle(level, engine, th: Actor, caught: bool, by: Actor | None = None) -> None:
    """A chase ends: the thief's hauled off to the gaol, or they've got away."""
    chasers = [a for a in level.actors if a.chase is th]
    for g in chasers:
        g.chase, g.path, g.goal = None, [], None
    if caught:
        by = by or (chasers[0] if chasers else None)
        if th in level.actors:
            level.actors.remove(th)
        level.arrests += 1
        if seen(engine, level, (th.x, th.y)) or (by is not None and seen(engine, level, (by.x, by.y))):
            who = by.name if by is not None else "A guard"
            engine.say(f"{who} collars {th.name} and hauls them off to the gaol.")
        return
    th.fleeing, th.path, th.goal = None, [], None
    if seen(engine, level, (th.x, th.y)):
        engine.say(f"{th.name} gives the guards the slip and vanishes into the crowd.")


def restock(level, engine, rng: random.Random) -> None:
    """A new day: the city's thieves are back up to their number."""
    day = int(engine.minutes // 1440)
    if level.crime_day == day:
        return
    first = level.crime_day < 0
    level.crime_day = day
    if first:
        return
    have = sum(a.kind == "thief" for a in level.actors)
    like = next((a for a in level.actors if a.kind == "townsperson"), None)
    if like is None:
        return
    gates = [p for p in level.places if p.kind == "gate"]
    used = {a.name for a in level.actors}
    for _ in range(level.thieves - have):
        at = rng.choice(rng.choice(gates).tiles) if gates else None
        thief(level, rng, used, like.home, like.haunts, at)
