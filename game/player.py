"""The player and what the environment does to them.

Three numbers carry it: body temperature, wetness and health. Each hour outside, the air
temperature is turned into what it feels like (wind chill, being wet, the shelter around you)
and clothing is added on top (your everyday clothes, and whatever you've put on over them:
game/gear.py). Inside the comfortable band your body settles back to 37 C;
outside it you cool down or heat up, and past the danger lines you start losing health.
Being dry, sheltered and at a normal temperature heals you slowly.

Cold water (below 21 C) draws heat straight out of you, much faster than air: every turn you
stand or wade in it your body cools 0.13 C (water at 21 C) to 0.35 C (near freezing). Once
you're out, the cold that's soaked into you keeps working for another 30 to 45 turns (the
afterdrop), easing off as you go, and the longer you were in, the harder it bites (`chill`).

Stamina is spent by walking (more on hard ground) and comes back while you wait or rest. It
doesn't hold you back yet; it's there for what comes later.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import gear
from .climate import Conditions
from .items import Inventory

START_COINS = 20

NORMAL = 37.0
COMFORT_LOW, COMFORT_HIGH = 12.0, 29.0   # felt temperature (with clothing) that needs no effort
COLD_DANGER, HOT_DANGER = 35.0, 39.5     # body temperatures that start to hurt
INDOORS = 20.0                           # the air in a settlement's buildings
COLD_WATER = 21.0                        # water colder than this chills you
CHILL_WARMEST, CHILL_COLDEST = 0.13, 0.35   # degrees C a turn, in water at 21 C and at 0 C
AFTERDROP_TURNS = (30, 45)               # turns you keep cooling once you're out
AFTERDROP_SHARE = 0.5                    # the afterdrop starts at this share of the chill in the water,
SOAKED_THROUGH = 10                      # after this many turns in it (less for a quick splash through)
TIRING = 8.0                             # stamina an hour of steady walking costs
RESTING = 20.0                           # stamina an hour of rest brings back


@dataclass
class Player:
    x: int
    y: int
    name: str = "Wanderer"
    health: float = 100.0
    body: float = NORMAL     # body temperature, degrees C
    wet: float = 0.0         # 0 dry .. 100 soaked
    stamina: float = 100.0   # 0 spent .. 100 fresh
    clothing: float = 8.0    # degrees C of insulation from your everyday clothes (gear adds more)
    alive: bool = True
    cause: str = ""          # what killed you
    warned: set = field(default_factory=set)
    inventory: Inventory = field(default_factory=lambda: Inventory(coin=START_COINS))
    wielding: str | None = None   # the weapon in your hand (game/combat.py)
    wearing: dict = field(default_factory=dict)   # where -> the armour you have on there
    sickness: object = None       # game/sickness.py: wolf fever, if a bite went bad
    in_cold_water: float = 0.0    # degrees C a turn the water you're in is taking, 0 when out of it
    cold_turns: int = 0           # turns you've been in it
    afterdrop: int = 0            # turns of cooling left since you came out of cold water
    afterdrop_of: int = 0         # how many turns that afterdrop started with
    afterdrop_rate: float = 0.0   # degrees C a turn it started at
    god: bool = False             # the dev console's god mode: nothing hurts you
    noclip: bool = False          # and noclip: walk through anything


def feels_like(air: float, wind: float, wet: float, shelter: float) -> float:
    """The air temperature as your skin meets it, before clothing."""
    wind = wind * (1 - shelter)
    felt = air
    if air <= 10 and wind > 4.8:  # the wind chill index (Environment Canada's formula)
        v = wind ** 0.16
        felt = 13.12 + 0.6215 * air - 11.37 * v + 0.3965 * air * v
    elif air > 10:
        felt = air - wind * 0.05     # a breeze takes the edge off the heat
    return felt - wet / 100 * 7      # wet clothes pull heat away


def insulation(p: Player) -> float:
    """Degrees C your clothes and what you've got on add to the air you feel."""
    return p.clothing + gear.warmth(p)


def body_status(body: float) -> str:
    for limit, name in ((32, "Hypothermic"), (35, "Freezing"), (36.3, "Cold"), (36.8, "Chilly"),
                        (37.4, "Comfortable"), (38.2, "Warm"), (39.5, "Hot")):
        if body < limit:
            return name
    return "Overheating"


def stamina_status(stamina: float) -> str:
    for limit, name in ((15, "Exhausted"), (40, "Weary"), (75, "Tired")):
        if stamina < limit:
            return name
    return "Fresh"


def tire(p: Player, hours: float, effort: float) -> None:
    """Spends `hours` at `effort` (1 is steady walking, 0 is resting)."""
    if effort > 0:
        p.stamina -= TIRING * effort * hours
    else:
        p.stamina += RESTING * hours
    p.stamina = max(0.0, min(100.0, p.stamina))


def wet_status(wet: float) -> str:
    for limit, name in ((5, "Dry"), (30, "Damp"), (70, "Wet")):
        if wet < limit:
            return name
    return "Soaked"


def expose(p: Player, hours: float, c: Conditions, shelter: float, indoors: bool = False,
           soak: float = 0.0, indoor_air: float = INDOORS) -> list[str]:
    """Spends `hours` in these conditions. `soak` is wetness added at once (wading a river).
    Indoors (under a roof or underground) the weather can't reach you and the air is
    `indoor_air`. Returns the messages worth telling the player."""
    msgs: list[str] = []
    if not p.alive:
        return msgs
    p.wet = min(100.0, p.wet + soak)
    left = hours
    while left > 1e-6 and p.alive:
        dt = min(1.0, left)
        left -= dt
        if indoors:
            felt, rain = indoor_air, 0.0
        else:
            felt = feels_like(c.air, c.wind, p.wet, shelter)
            rain = c.precip * (1 - shelter) * (12 if c.snowing else 45)
            if c.fog > 0.4:
                rain += 3 * (1 - shelter)
            rain *= 1 - gear.cover(p)            # a cloak or a hat keeps some of it off
        effective = felt + insulation(p)
        # wetness: rain soaks in, warmth and wind dry you off
        drying = 3 + max(c.air if not indoors else indoor_air, 0) * 0.35 + (0 if indoors else c.wind * 0.05)
        if indoors and indoor_air >= 16:
            drying += 20   # a warm room with a fire
        p.wet = min(100.0, max(0.0, p.wet + (rain - (drying if rain < 1 else drying * 0.2)) * dt))
        # body temperature
        if effective < COMFORT_LOW:
            p.body -= (COMFORT_LOW - effective) * 0.03 * dt
        elif effective > COMFORT_HIGH:
            p.body += (effective - COMFORT_HIGH) * 0.05 * dt
        elif not p.in_cold_water:             # standing in cold water, you don't warm back up
            p.body += (NORMAL - p.body) * min(1.0, 0.7 * dt)
        p.body = max(25.0, min(44.0, p.body))
        # health
        if p.body < COLD_DANGER:
            p.health -= (COLD_DANGER - p.body) * 6 * dt
            p.cause = "froze to death"
        elif p.body > HOT_DANGER:
            p.health -= (p.body - HOT_DANGER) * 8 * dt
            p.cause = "died of heatstroke"
        elif 36.3 <= p.body <= 37.6 and p.wet < 30:
            p.health = min(100.0, p.health + (6 if indoors and indoor_air >= 16 else 2) * dt)
        if p.health <= 0 and not p.god:
            p.health, p.alive = 0.0, False
            msgs.append(f"You {p.cause}.")
    msgs += warnings(p)
    return msgs


def chill_rate(water: float) -> float:
    """Degrees C a turn that water at this temperature draws out of you: none at 21 C or warmer,
    0.13 just under that, rising to 0.35 at freezing."""
    if water >= COLD_WATER:
        return 0.0
    cold = min(1.0, max(0.0, (COLD_WATER - water) / COLD_WATER))
    return CHILL_WARMEST + cold * (CHILL_COLDEST - CHILL_WARMEST)


def chill(p: Player, turns: int, water: float | None, rng) -> list[str]:
    """`turns` turns, in water at `water` degrees C (None: out of the water). In cold water you
    cool every turn; out of it, the afterdrop goes on cooling you, less each turn, till it's done.
    Returns what's worth telling the player."""
    msgs: list[str] = []
    if not p.alive or turns <= 0:
        return msgs
    rate = chill_rate(water) if water is not None else 0.0
    if rate > 0:
        if not p.in_cold_water:
            msgs.append("The water is bitterly cold." if water < 8 else "The cold water takes your breath away."
                        if water < 15 else "The water is cold.")
        p.in_cold_water = rate
        p.cold_turns += turns
        p.afterdrop = 0
        p.body -= rate * turns
    else:
        if p.in_cold_water:                      # just out: the cold soaked into you keeps working
            p.afterdrop = p.afterdrop_of = rng.randint(*AFTERDROP_TURNS)
            p.afterdrop_rate = p.in_cold_water * AFTERDROP_SHARE * min(1.0, p.cold_turns / SOAKED_THROUGH)
            p.in_cold_water, p.cold_turns = 0.0, 0
            msgs.append("You come out of the cold water shivering; the chill goes on sinking in.")
        for _ in range(min(turns, p.afterdrop)):
            p.body -= p.afterdrop_rate * p.afterdrop / max(1, p.afterdrop_of)   # easing off as it goes
            p.afterdrop -= 1
        if turns and p.afterdrop == 0 and p.afterdrop_of:
            p.afterdrop_of = 0
            msgs.append("The shivering eases.")
    p.body = max(25.0, p.body)
    return msgs


def chill_status(p: Player) -> str:
    if p.in_cold_water:
        return "In cold water"
    if p.afterdrop:
        return "Chilled to the bone"
    return ""


def warnings(p: Player) -> list[str]:
    """Each warning once, until the danger passes."""
    out = []
    checks = [  # key, starts when, ends when, message at the start, message at the end
        ("cold", p.body < 36.3, p.body >= 36.6, "You're getting cold.", "You've warmed up."),
        ("freezing", p.body < COLD_DANGER, p.body >= 35.5, "You're freezing! Find shelter.", None),
        ("hot", p.body > 38.2, p.body <= 37.9, "You're overheating.", "You've cooled down."),
        ("heatstroke", p.body > HOT_DANGER, p.body <= 39.0, "Heatstroke! Get out of the sun.", None),
        ("soaked", p.wet >= 70, p.wet < 5, "You're soaked through.", "You've dried off."),
        ("exhausted", p.stamina < 15, p.stamina >= 40, "You're exhausted.", "You've got your strength back."),
    ]
    for key, on, off, start, end in checks:
        if on and key not in p.warned:
            p.warned.add(key)
            out.append(start)
        elif off and key in p.warned:
            p.warned.discard(key)
            if end:
                out.append(end)
    return out
