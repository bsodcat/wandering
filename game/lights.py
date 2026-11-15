"""Light to see by: torches and lanterns.

With nothing lit you still make out what's right around you (BARE: 3 tiles), underground and on
a dark night. A lit torch lets you see 6 tiles, a lantern 9.

- A torch burns 2 to 16 hours. A bought one has 6 hours in it; one you make (game/crafting.py)
  takes what its fuel gives. Fuel adds hours, more for the better fuel: pitch 5, animal fat 3, a
  flask of oil 7, up to 16. In heavy rain a torch burns half as fast again. When it's nearly out
  and you've oil or fat with you, you feed it without thinking (the longest-burning first);
  otherwise it gutters and is gone.
- A lantern isn't made, only bought. It burns oil (10 hours a flask) or animal fat (5), up to 16,
  refilled the same way, and the rain doesn't touch it. Run dry, it goes out but you keep it.

Only one light burns at a time; you hold it (Player.light, Player.light_hours).
"""
from __future__ import annotations

BARE, TORCH_SIGHT, LANTERN_SIGHT = 3, 6, 9
SIGHT = {None: BARE, "torch": TORCH_SIGHT, "lantern": LANTERN_SIGHT}
MOST_HOURS = 16.0
LEAST_HOURS = 2.0
BOUGHT_TORCH = 6.0                                     # hours in a torch from a shop
TORCH_FUEL = {"flask of oil": 7.0, "pitch": 5.0, "animal fat": 3.0}   # hours each adds, best first
LANTERN_FUEL = {"flask of oil": 10.0, "animal fat": 5.0}
RAIN_BURN = 1.5                                        # a torch burns this much faster in heavy rain
LOW = 0.25                                             # hours left at which you top it up


def fuels(kind: str) -> dict:
    return TORCH_FUEL if kind == "torch" else LANTERN_FUEL


def sight(p) -> int:
    """How many tiles you see by your own light (or by none)."""
    return SIGHT.get(p.light, BARE) if p.light_hours > 0 else BARE


def light(p, kind: str) -> str:
    """Lights a torch from your bag, or your lantern if there's fuel for it."""
    bag = p.inventory
    if p.light == kind:
        return f"Your {kind}'s already lit."
    if not bag.count(kind):
        return f"You haven't got a {kind}."
    if kind == "torch":
        put_out(p)
        bag.take("torch")
        del p.torch_hours[bag.count("torch") + 1:]     # (torches given away took theirs with them)
        p.light, p.light_hours = "torch", p.torch_hours.pop(0) if p.torch_hours else BOUGHT_TORCH
        return f"You light a torch ({p.light_hours:.0f} hours in it)."
    hours = p.lantern_hours
    if hours <= 0:
        hours = refill(p, "lantern", 0.0)[0]
        if hours <= 0:
            return "Your lantern's dry: it needs oil or animal fat."
    put_out(p)
    p.light, p.light_hours = "lantern", hours
    return f"You light your lantern ({hours:.0f} hours of fuel)."


def put_out(p) -> str:
    """Puts out what's lit: a torch goes back in the bag (keeping what's left in it), a lantern
    keeps its fuel."""
    if p.light is None:
        return "Nothing's lit."
    kind = p.light
    if kind == "torch":
        if p.light_hours >= 0.5:
            p.inventory.add("torch")
            p.torch_hours.insert(0, p.light_hours)
    else:
        p.lantern_hours = p.light_hours
    p.light, p.light_hours = None, 0.0
    return f"You put out the {kind}."


def refill(p, kind: str, hours: float) -> tuple[float, str]:
    """Feeds a light from your bag until it's at least LOW: (hours now, what you used, or "")."""
    used = ""
    for fuel, adds in fuels(kind).items():
        while hours < LOW + 1e-9 and p.inventory.count(fuel) and hours + adds <= MOST_HOURS + 1e-9:
            p.inventory.take(fuel)
            hours += adds
            used = fuel
        if hours >= LOW:
            break
    return min(MOST_HOURS, hours), used


def burn(p, hours: float, heavy_rain: bool) -> list[str]:
    """The light burns for `hours`; it's topped up from your bag when it runs low, or goes out."""
    if p.light is None:
        return []
    kind = p.light
    rate = RAIN_BURN if kind == "torch" and heavy_rain else 1.0
    p.light_hours -= hours * rate
    if p.light_hours > LOW:
        return []
    p.light_hours, used = refill(p, kind, max(0.0, p.light_hours))
    if used:
        how = "smear animal fat on" if used == "animal fat" else "daub pitch on" if used == "pitch" else \
            "pour oil into" if kind == "lantern" else "soak oil into"
        return [f"You {how} your {kind} before it goes out."]
    if p.light_hours > 0:
        return []
    p.light, p.light_hours = None, 0.0
    if kind == "torch":
        return ["Your torch gutters out."]
    p.lantern_hours = 0.0
    return ["Your lantern sputters and goes out: it's out of fuel."]


def status(p) -> str:
    """'Torch 5.2 h', for the stats panel; '' with nothing lit."""
    if p.light is None:
        return ""
    return f"{p.light.capitalize()} {p.light_hours:.1f} h"


def add_fuel(p, kind: str, fuel: str) -> str:
    """Tops up the lit torch or your lantern by hand with one fuel."""
    adds = fuels(kind).get(fuel)
    if adds is None:
        return f"You can't burn {fuel} in a {kind}."
    lit = p.light == kind
    have = p.light_hours if lit else p.lantern_hours if kind == "lantern" else 0.0
    if have + adds > MOST_HOURS + 1e-9:
        return f"Your {kind} is as full as it'll get."
    if not p.inventory.take(fuel):
        return f"You haven't got any {fuel}."
    if lit:
        p.light_hours = have + adds
    else:
        p.lantern_hours = have + adds
    return f"You fuel your {kind}: {have + adds:.0f} hours."
