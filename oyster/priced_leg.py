"""A single tap as it flows through the pricing phases."""

from __future__ import annotations

from dataclasses import dataclass

from oyster.model import Trip
from oyster.money import Money


@dataclass
class PricedLeg:
    """One tap after single-fare pricing, carrying each phase's running charge."""

    trip: Trip
    pool: str  # "rail" or "bus"
    peak: bool
    route: str
    zones_label: str
    chosen_zones: tuple[int, ...]  # the chosen endpoint zones (rail only)
    includes_zone1: bool
    start_zones: tuple[int, ...]  # zones of the start station (rail only)
    single_fare: Money  # full fare before any loyalty discount / hopper / cap
    pre_cap_charge: Money  # post-loyalty-discount + post-hopper charge fed to capping
    bypass_cap: bool = False  # commuter-club in-band rail legs are charged £0, skip capping
    charged: Money = Money.ZERO  # final amount billed, set by the cap engine
