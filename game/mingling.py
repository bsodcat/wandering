"""People meeting people: two who come within a step or two of each other, both free, now and
then stop and have a word, a few minutes, then go on their way (they won't stop again for a
while, COOLDOWN). What they do depends on who they are and where (pair_up):

- a merchant and someone at their stall haggle over the goods
- a beggar and someone passing: a coin dropped in the cup (or not)
- a guard and anyone: the guard asks their business; two guards swap the watch's news
- the priest blesses; the ruler and their consort hold court; to anyone else, the ruler's
  someone to bow to
- at the inn they share a drink; homemakers, washerwomen and widows gossip; craftsfolk talk shop;
  sellswords swap tales of the road; everyone else chats about the news of the day (TOPICS)

Close by and in sight (HEAR), you catch some of it in the log, now and then (SAY_EVERY). And
the town crier, in the square, cries the news of the day (CRIES) when you're near.
"""
from __future__ import annotations

import random

from . import tiles as T
from .people import CRAFTS, ROYAL

CHAT_CHANCE = 0.06            # a minute: how likely two free people side by side strike up a talk
CHAT_MINUTES = (2, 7)
COOLDOWN = 50                 # minutes before someone stops to talk again
REACH = 2                     # tiles apart, at most, to talk
HEAR = 10                     # tiles from you that you catch what's said
SAY_EVERY = 5.0               # minutes between the lines you overhear, at least
CRY_EVERY = 45.0              # ... and between the crier's cries
QUIET = 1.0                   # minutes after anything else goes in the log that you overhear nothing
RESOLVE = 30                  # away longer than this, and nobody's in the middle of a talk
BUSY = ("asleep", "playing tag", "at their lessons")
KEEPS_TO = ("prisoner", "gaoler", "patient")      # they don't wander up to anyone
TOPICS = ["the price of bread", "the weather", "the new tax", "wolves on the north road", "a wedding at the temple",
          "last night's play", "the fights at the pit", "a ghost seen in the graveyard", "goblins in the hills",
          "the mage in the tower", "a thief caught at the market", "the harvest", "a fever in the lower quarter",
          "the king's health", "a ship lost at sea", "the guild's prices", "a fire on the far side of town"]
WARES = ["a bolt of cloth", "a basket of apples", "a string of onions", "a pot", "a pair of candles", "a fish",
         "a wheel of cheese", "a bag of salt", "a brass ring"]
SAYINGS = ['"Did you hear about {topic}?"', '"They say {topic} is the talk of {town}."',
           '"Don\'t get me started on {topic}."', '"I blame the guild."', '"Mark my words, it\'ll end badly."']
CRIES = ["Hear ye! By order of the crown, no blades drawn within the walls!",
         "Hear ye! Wolves on the north road: travellers, keep to the carts!",
         "Hear ye! A ballad tonight at the playhouse!",
         "Hear ye! Market day is Saturday: stalls in the square from nine!",
         "Hear ye! The temple bids all to the Sunday service at nine!",
         "Hear ye! A thief taken at the market, to stand in the stocks!",
         "Hear ye! The Adventurers' Hall seeks stout hands for the hills!",
         "Hear ye! The baths are hot, and the bathkeeper bids you come!"]


def first(a) -> str:
    return a.title if a.kind in ROYAL else a.name.split()[0]


def free(a, minutes: float) -> bool:
    return (not a.animal and a.chase is None and a.fleeing is None and a.doing not in BUSY
            and a.kind not in KEEPS_TO and a.talk_until <= minutes and a.chat_after <= minutes
            and not (a.kind == "child" and a.friends))


def pair_up(level, a, b, rng: random.Random, names: dict) -> tuple[str, str, str]:
    """(what a's doing, what b's doing, what you'd hear) when a and b stop to talk."""
    if b.kind == "merchant" and a.kind != "merchant":
        a, b = b, a
        swap = True
    else:
        swap = False
    if b.kind == "beggar" and a.kind not in ("beggar", "thief"):
        a, b, swap = b, a, not swap
    if b.kind == "guard" and a.kind != "guard":
        a, b, swap = b, a, not swap
    if b.kind in ROYAL and a.kind not in ROYAL:
        a, b, swap = b, a, not swap
    if b.kind == "priest":
        a, b, swap = b, a, not swap
    fa, fb = first(a), first(b)
    inn = next((x for x in level.buildings if x.kind == "inn"), None)
    topic = rng.choice(TOPICS)
    if a.kind == "merchant":
        ware = rng.choice(WARES)
        out = (f"haggling with {fb}", f"haggling with {fa} over {ware}",
               f'{fb} haggles with {fa} over {ware}. "{rng.randint(2, 9)} coppers? You must be joking!"')
    elif a.kind == "beggar":
        if rng.random() < 0.5:
            out = (f"thanking {fb}", f"giving {fa} a coin", f"{fb} drops a coin into {fa}'s cup. \"Bless you!\"")
        else:
            out = (f"begging from {fb}", f"waving {fa} off", f'{fa} holds out a cup to {fb}, who shakes their head.')
    elif a.kind == "guard":
        if b.kind == "guard":
            out = (f"swapping the watch's news with {fb}", f"swapping the watch's news with {fa}",
                   f"{fa} and {fb}, the guards, swap news of the watch.")
        else:
            out = (f"questioning {fb}", "answering the guard's questions",
                   f'{fa}, the guard, stops {fb}: "And what\'s your business in {names["town"]}?"')
    elif a.kind in ROYAL:
        if b.kind in ROYAL:
            out = (f"in quiet talk with {fb}", f"in quiet talk with {fa}", f"{fa} and {fb} talk quietly together.")
        else:
            out = (f"speaking with {fb}", f"bowing to {fa}", f"{fb} bows low to {fa}.")
    elif a.kind == "priest":
        out = (f"blessing {fb}", f"taking a blessing from {fa}", f"{fa}, the priest, blesses {fb}.")
    elif inn is not None and inn.contains(a.x, a.y):
        out = (f"sharing a drink with {fb}", f"sharing a drink with {fa}", f"{fa} and {fb} raise their cups to {topic}.")
    elif a.kind in ("homemaker", "washerwoman", "widow", "maid", "elder") and \
            b.kind in ("homemaker", "washerwoman", "widow", "maid", "elder"):
        out = (f"gossiping with {fb}", f"gossiping with {fa}",
               f"{fa} leans close to {fb}: " + rng.choice(SAYINGS).format(topic=topic, town=names["town"]))
    elif a.kind in CRAFTS and b.kind in CRAFTS:
        out = (f"talking shop with {fb}", f"talking shop with {fa}",
               f"{fa}, the {a.kind}, and {fb}, the {b.kind}, grumble about the guild's prices.")
    elif a.kind in ("sellsword", "recruit") and b.kind in ("sellsword", "recruit"):
        out = (f"swapping tales with {fb}", f"swapping tales with {fa}",
               f"{fa} tells {fb} of a goblin ten feet tall. {fb} doesn't believe a word.")
    else:
        out = (f"chatting with {fb}", f"chatting with {fa}",
               f"{fa} and {fb} stop to talk about {topic}. " + rng.choice(SAYINGS).format(topic=topic, town=names["town"]))
    return (out[1], out[0], out[2]) if swap else out


def seen(engine, level, a) -> bool:
    vis = getattr(engine, "local_visible", None)
    return (engine.level is level and vis is not None and vis.shape == level.tiles.shape and bool(vis[a.x, a.y])
            and max(abs(a.x - engine.lx), abs(a.y - engine.ly)) <= HEAR)


def mingle(level, engine, rng: random.Random, elapsed: float) -> None:
    """`elapsed` minutes of people stopping to talk, and the crier crying."""
    people_here = [a for a in level.actors if not a.animal]
    if not people_here:
        return
    now = engine.minutes
    if elapsed > RESOLVE:
        for a in people_here:
            a.talk_until, a.partner = 0.0, None
        return
    from .people import names_for
    names = names_for(level, engine)
    cells = {}
    for a in people_here:
        if a.partner is not None and a.talk_until <= now:
            a.partner = None
        if free(a, now):
            cells[(a.x, a.y)] = a
    chance = 1 - (1 - CHAT_CHANCE) ** elapsed
    heard = getattr(level, "_heard_at", -1e9)
    if now - getattr(engine, "said_at", -1e9) < QUIET:
        heard = now                     # you've just been told something: the chatter can wait
    for (x, y), a in list(cells.items()):
        if a.talk_until > now or rng.random() >= chance:
            continue
        near = [cells[(x + dx, y + dy)] for dx in range(-REACH, REACH + 1) for dy in range(-REACH, REACH + 1)
                if (dx or dy) and (x + dx, y + dy) in cells]
        near = [b for b in near if b.talk_until <= now and b is not a]
        if not near:
            continue
        b = rng.choice(near)
        doing_a, doing_b, line = pair_up(level, a, b, rng, names)
        until = now + rng.uniform(*CHAT_MINUTES)
        for who, doing, other in ((a, doing_a, b), (b, doing_b, a)):
            who.talk_until, who.talk_doing, who.partner = until, doing, other
            who.chat_after = until + COOLDOWN
            who.doing = doing
            who.path, who.goal = [], None
        if now - heard >= SAY_EVERY and (seen(engine, level, a) or seen(engine, level, b)):
            engine.say(line, ambient=True)
            heard = now
    level._heard_at = heard
    crier = next((a for a in people_here if a.kind == "town crier" and a.doing == "crying the news"), None)
    quiet = now - getattr(engine, "said_at", -1e9) < QUIET
    if crier is not None and not quiet and seen(engine, level, crier) and now - getattr(level, "_cried_at", -1e9) >= CRY_EVERY:
        level._cried_at = now
        engine.say(f"{crier.name}, the town crier, rings a bell: \"{rng.choice(CRIES)}\"", ambient=True)

